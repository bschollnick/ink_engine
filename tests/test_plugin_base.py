"""`StatefulPlugin`: what a subclass inherits, and what construction refuses.

Purpose-built plugins are defined here so the tests prove the BASE, not
any shipped plugin; the shipped ones are certified separately.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Callable
from typing import Any, ClassVar, TypedDict
from unittest import TestCase

from ink_engine.binding import AmbiguousSlotConfigError, resolve_bindings
from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.plugin import VOID, Plugin
from ink_engine.plugin_base import BindingContext, StatefulPlugin, external, query


class LedgerSlot(TypedDict):
    """A tiny slot: named balances and a per-session note."""

    balances: dict[str, float]
    note: str


class Ledger(StatefulPlugin[LedgerSlot]):
    """The purpose-built plugin every test here binds."""

    name = "ledger"
    display_name = "Ledger"
    state_key = "ledger"
    slot_type = LedgerSlot
    fields: ClassVar[dict[str, Callable[[], Any]]] = {"balances": dict, "note": str}

    def validate_config(self, config: Any) -> None:
        if not isinstance(config, dict):
            raise SystemConfigValidationError("ledger config must be an object")

    def seed(self, slot: LedgerSlot, config: Any) -> None:
        if config:
            slot["balances"].update(config)

    @query
    @external
    def balance(self, slot: LedgerSlot, account: str, default: float = 0) -> float:
        return slot["balances"].get(account, default)

    @external
    def deposit(self, slot: LedgerSlot, account: str, amount: float) -> None:
        slot["balances"][account] = slot["balances"].get(account, 0) + amount

    @external(needs_context=True)
    def clock_hour(self, context: BindingContext, default: int = -1) -> int:
        return context.slot_of("clock").get("hour", default)


class Vault(Ledger):
    """A game's extension: inherits every binding, overrides one, adds one."""

    name = "vault"
    display_name = "Vault"

    def balance(self, slot: LedgerSlot, account: str, default: float = 0) -> float:
        return round(super().balance(slot, account, default))

    @external
    def seal(self, slot: LedgerSlot) -> None:
        slot["note"] = "sealed"


class ConstructionTests(TestCase):
    """What the base refuses at import, so a mistake never reaches play."""

    def test_fields_and_slot_type_must_agree(self):
        class Mismatched(Ledger):
            fields: ClassVar[dict[str, Callable[[], Any]]] = {"balances": dict}

        with self.assertRaises(TypeError) as caught:
            Mismatched()
        self.assertIn("slot_type", str(caught.exception))

    def test_a_missing_slot_type_is_refused(self):
        class Undeclared(StatefulPlugin[dict[str, Any]]):
            name = "undeclared"
            display_name = "Undeclared"
            state_key = "undeclared"

        with self.assertRaises(TypeError):
            Undeclared()

    def test_a_definition_object_leaking_into_state_is_refused(self):
        class Leaky(Ledger):
            fields: ClassVar[dict[str, Callable[[], Any]]] = {"balances": dict, "note": object}

        with self.assertRaises(TypeError) as caught:
            Leaky()
        self.assertIn("JSON", str(caught.exception))

    def test_a_query_taking_star_args_is_refused(self):
        with self.assertRaises(TypeError):

            class Vague(Ledger):
                @query
                def anything(self, slot: LedgerSlot, *names: str) -> int:
                    return len(names)

    def test_an_external_without_a_return_annotation_is_refused(self):
        with self.assertRaises(TypeError):

            class Unannotated(Ledger):
                @external
                def mystery(self, slot):
                    return 1

    def test_a_bad_definition_config_fails_at_construction(self):
        with self.assertRaises(SystemConfigValidationError):
            Ledger(config=["not", "an", "object"])

    def test_a_plugin_taking_no_config_refuses_a_non_empty_one(self):
        class Plain(StatefulPlugin[LedgerSlot]):
            name = "plain"
            display_name = "Plain"
            state_key = "plain"
            slot_type = LedgerSlot
            fields: ClassVar[dict[str, Callable[[], Any]]] = {"balances": dict, "note": str}

        Plain().validate_config({})
        Plain().validate_config(None)
        with self.assertRaises(SystemConfigValidationError):
            Plain().validate_config({"anything": 1})


class DerivedContractTests(TestCase):
    """The `Plugin` descriptor and bindings are built, not written."""

    def test_plugin_is_built_from_class_attributes_and_marked_methods(self):
        descriptor = Ledger().plugin()
        self.assertIsInstance(descriptor, Plugin)
        self.assertEqual((descriptor.name, descriptor.display_name, descriptor.state_key), ("ledger", "Ledger", "ledger"))
        self.assertEqual(sorted(descriptor.queries), ["balance"])
        self.assertIsNotNone(descriptor.validate_config)

    def test_init_state_has_every_declared_field_empty(self):
        self.assertEqual(Ledger().init_state(None), {"balances": {}, "note": ""})

    def test_bind_publishes_every_external_under_the_method_name(self):
        slot = Ledger().init_state(None)
        bindings = Ledger().bind(slot, {"ledger": slot, "clock": {"hour": 9}}, {})
        self.assertEqual(sorted(bindings), ["balance", "clock_hour", "deposit"])
        bindings["deposit"]("cash", 5)
        self.assertEqual(bindings["balance"]("cash"), 5)
        self.assertEqual(bindings["clock_hour"](), 9)

    def test_a_writer_returns_void_to_ink(self):
        slot = Ledger().init_state(None)
        self.assertIs(Ledger().bind(slot, {}, {})["deposit"]("cash", 1), VOID)

    def test_a_write_lands_in_the_live_slot(self):
        """No write-back step: the slot handed to bind() is the state."""
        engine_state: dict[str, Any] = {}
        bindings = resolve_bindings({"ledger": Ledger().plugin()}, ["ledger"], engine_state)
        bindings["deposit"]("cash", 2)
        self.assertEqual(engine_state["ledger"]["balances"], {"cash": 2})

    def test_a_query_reports_its_real_signature(self):
        """A caller learns the arity from the signature; `self` is gone."""
        signature = inspect.signature(Ledger().plugin().queries["balance"])
        self.assertEqual(list(signature.parameters), ["slot", "account", "default"])

    def test_a_query_answers_from_the_slot(self):
        plugin = Ledger()
        slot = plugin.init_state({"cash": 3})
        self.assertEqual(plugin.plugin().queries["balance"](slot, "cash"), 3)

    def test_the_same_method_is_the_python_reader(self):
        plugin = Ledger()
        slot = plugin.init_state(None)
        plugin.deposit(slot, "cash", 7)
        self.assertEqual(plugin.balance(slot, "cash"), 7)

    def test_an_older_save_missing_a_field_is_repaired_on_bind(self):
        old_save: dict[str, Any] = {"balances": {"cash": 1}}
        Ledger().bind(old_save, {}, {})
        self.assertEqual(old_save, {"balances": {"cash": 1}, "note": ""})

    def test_rebinding_never_resets_the_slot(self):
        engine_state: dict[str, Any] = {}
        plugins = {"ledger": Ledger().plugin()}
        resolve_bindings(plugins, ["ledger"], engine_state)["deposit"]("cash", 4)
        before = copy.deepcopy(engine_state)
        resolve_bindings(plugins, ["ledger"], engine_state)
        self.assertEqual(engine_state, before)

    def test_the_slot_round_trips_through_json(self):
        engine_state: dict[str, Any] = {}
        resolve_bindings({"ledger": Ledger().plugin()}, ["ledger"], engine_state)["deposit"]("cash", 4)
        self.assertEqual(json.loads(json.dumps(engine_state)), engine_state)


class ExtensionTests(TestCase):
    """A game extends an engine plugin by instantiating or subclassing it."""

    def test_instantiating_with_a_new_name_republishes_the_bindings(self):
        renamed = Ledger(name="house_ledger", display_name="House ledger").plugin()
        self.assertEqual(renamed.name, "house_ledger")
        self.assertEqual(sorted(renamed.bind(renamed.init_state(None), {}, {})), ["balance", "clock_hour", "deposit"])

    def test_a_subclass_inherits_overrides_and_adds_bindings(self):
        slot = Vault().init_state(None)
        bindings = Vault().bind(slot, {}, {})
        self.assertEqual(sorted(bindings), ["balance", "clock_hour", "deposit", "seal"])
        bindings["deposit"]("cash", 2.6)
        self.assertEqual(bindings["balance"]("cash"), 3)
        bindings["seal"]()
        self.assertEqual(slot["note"], "sealed")

    def test_an_override_without_the_decorator_stays_published(self):
        """The Ink name is the parent's contract; a subclass cannot
        unpublish it by forgetting the marker."""
        self.assertIn("balance", Vault().plugin().queries)


class AllocationTests(TestCase):
    """`allocate_state()`: slots are built once, independent of order."""

    def _plugins(self) -> dict[str, Plugin]:
        generic = Ledger().plugin()
        seeded = Ledger(name="seeded_ledger").plugin()
        return {"ledger": generic, "seeded_ledger": seeded}

    def test_a_host_config_seeds_the_slot_in_either_activation_order(self):
        for order in (["ledger", "seeded_ledger"], ["seeded_ledger", "ledger"]):
            with self.subTest(order=order):
                engine_state: dict[str, Any] = {}
                resolve_bindings(self._plugins(), order, engine_state, configs={"seeded_ledger": {"cash": 10}})
                self.assertEqual(engine_state["ledger"]["balances"], {"cash": 10})

    def test_a_default_config_seeds_when_the_host_attaches_none(self):
        class Funded(Ledger):
            name = "funded"
            default_config: ClassVar[dict[str, int]] = {"cash": 50}

        engine_state: dict[str, Any] = {}
        resolve_bindings({"funded": Funded().plugin()}, ["funded"], engine_state)
        self.assertEqual(engine_state["ledger"]["balances"], {"cash": 50})

    def test_an_empty_application_entry_defers_to_the_default_config(self):
        class Funded(Ledger):
            name = "funded"
            default_config: ClassVar[dict[str, int]] = {"cash": 50}

        engine_state: dict[str, Any] = {}
        resolve_bindings({"funded": Funded().plugin()}, ["funded"], engine_state, configs={"funded": {}})
        self.assertEqual(engine_state["ledger"]["balances"], {"cash": 50})

    def test_two_seeders_on_one_slot_are_refused_in_both_orders(self):
        for order in (["ledger", "seeded_ledger"], ["seeded_ledger", "ledger"]):
            with self.subTest(order=order), self.assertRaises(AmbiguousSlotConfigError):
                resolve_bindings(self._plugins(), order, {}, configs={"ledger": {"cash": 1}, "seeded_ledger": {"cash": 2}})

    def test_a_host_config_is_validated_before_seeding(self):
        with self.assertRaises(SystemConfigValidationError):
            resolve_bindings(self._plugins(), ["ledger"], {}, configs={"ledger": ["bad"]})

    def test_a_resumed_save_is_never_reseeded(self):
        engine_state: dict[str, Any] = {"ledger": {"balances": {"cash": 1}, "note": "played"}}
        resolve_bindings(self._plugins(), ["ledger"], engine_state, configs={"ledger": {"cash": 99}})
        self.assertEqual(engine_state["ledger"], {"balances": {"cash": 1}, "note": "played"})

    def test_a_slot_is_allocated_before_any_plugin_binds(self):
        """A binding that reads another plugin's slot sees it on the very
        first bind, whichever plugin is named first."""

        class ClockSlot(TypedDict):
            hour: int

        class Clock(StatefulPlugin[ClockSlot]):
            name = "clock"
            display_name = "Clock"
            state_key = "clock"
            slot_type = ClockSlot
            fields: ClassVar[dict[str, Callable[[], Any]]] = {"hour": lambda: 9}

        seen: list[Any] = []

        class Watcher(Ledger):
            name = "watcher"

            def bind(self, slot, engine_state, list_defs):
                seen.append(engine_state.get("clock"))
                return super().bind(slot, engine_state, list_defs)

        resolve_bindings({"watcher": Watcher().plugin(), "clock": Clock().plugin()}, ["watcher", "clock"], {})
        self.assertEqual(seen, [{"hour": 9}])
