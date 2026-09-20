"""The cost table: what an action costs, and whether it can be afforded.

Consolidates a resource-cost rule (e.g. "first use costs X, every use
after costs Y") into one authoritative table, instead of the same
number scattered across an ad hoc if-chain, a helper function, and
literal comparisons repeated across many story files -- a shape where a
missed case can leave one action priced only by a stray literal.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import TestCase as SimpleTestCase

from ink_engine.binding import resolve_bindings
from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.engine_plugins.costs import (
    COST_TABLE,
    PLUGIN,
    CostTable,
    validate_cost_table,
)

CONFIG = {
    "costs": {
        "spell.charm": {"resource": "mana", "amount": 10, "variants": {"cheaper": 9}},
        "spell.transform": {"resource": "mana", "amount": 20, "variants": {"first": 10}},
        "turn.indoor": {"resource": "time", "amount": 1},
    }
}

PRICED = CostTable(name="priced", display_name="Priced", config=CONFIG)


class CostLookupTests(SimpleTestCase):
    """Reading a cost, with and without a variant."""

    def setUp(self):
        self.slot = PRICED.init_state(None)

    def test_a_declared_cost_is_returned(self):
        """The ordinary case."""
        self.assertEqual(PRICED.cost_of(self.slot, "spell.transform"), 20)
        self.assertEqual(PRICED.resource_of(self.slot, "spell.transform"), "mana")

    def test_a_variant_overrides_the_base_amount(self):
        """A conditional price stays data: the caller names the variant
        when its condition holds, and the table holds only the number."""
        self.assertEqual(PRICED.cost_of(self.slot, "spell.transform", "first"), 10)
        self.assertEqual(PRICED.cost_of(self.slot, "spell.charm", "cheaper"), 9)

    def test_an_undeclared_variant_falls_back_to_the_base(self):
        """So a caller may always pass its variant without first checking
        whether this particular cost declares one."""
        self.assertEqual(PRICED.cost_of(self.slot, "turn.indoor", "first"), 1)

    def test_an_undeclared_key_costs_the_caller_s_default(self):
        """Asking about an unpriced action is a real question, not an
        error -- a story may price an action only once it exists."""
        self.assertEqual(PRICED.cost_of(self.slot, "spell.nothing", default=-1), -1)
        self.assertEqual(PRICED.cost_of(self.slot, "spell.nothing"), 0)

    def test_declared_prices_never_enter_the_slot(self):
        """They are definition: a new version's prices reach every save."""
        self.assertEqual(self.slot, {"costs": {}})


class AffordabilityTests(SimpleTestCase):
    """The comparison, asked the same way by every caller."""

    def setUp(self):
        self.slot = PRICED.init_state(None)

    def test_affordability_follows_the_variant(self):
        """The case this table was built for: 15 mana cannot pay for an
        ordinary transform but can pay for a character's first."""
        self.assertFalse(PRICED.can_afford(self.slot, "spell.transform", 15))
        self.assertTrue(PRICED.can_afford(self.slot, "spell.transform", 15, "first"))

    def test_exactly_enough_is_enough(self):
        """The boundary, pinned so it cannot drift to a strict >."""
        self.assertTrue(PRICED.can_afford(self.slot, "spell.transform", 20))

    def test_an_unpriced_action_is_never_affordable(self):
        """A key nobody declared is a typo or an unconverted action, not a
        freebie -- answering True would make every misspelling silently
        free. A real freebie is priced 0 explicitly."""
        self.assertFalse(PRICED.can_afford(self.slot, "spell.nothing", 0))
        self.assertFalse(PRICED.can_afford(self.slot, "spell.nothing", 999))

    def test_an_explicit_zero_price_is_affordable_with_nothing(self):
        """The deliberate freebie, which must stay distinguishable."""
        slot = PRICED.init_state(None)
        PRICED.set_cost(slot, "spell.gratis", "mana", 0)
        self.assertTrue(PRICED.can_afford(slot, "spell.gratis", 0))

    def test_is_priced_separates_unpriced_from_free(self):
        slot = PRICED.init_state(None)
        PRICED.set_cost(slot, "spell.gratis", "mana", 0)
        self.assertTrue(PRICED.is_priced(slot, "spell.gratis"))
        self.assertFalse(PRICED.is_priced(slot, "spell.nothing"))


class CostMutationTests(SimpleTestCase):
    """Prices that change during play live in the slot and win."""

    def test_set_cost_writes_the_slot_and_shadows_the_declared_price(self):
        slot = PRICED.init_state(None)
        PRICED.set_cost(slot, "spell.transform", "mana", 30)
        self.assertEqual(PRICED.cost_of(slot, "spell.transform"), 30)
        self.assertEqual(slot["costs"]["spell.transform"]["amount"], 30)

    def test_changing_the_base_keeps_the_variants(self):
        """A price rise should not silently discard the discount that
        already applied to it."""
        slot = PRICED.init_state(None)
        PRICED.set_cost(slot, "spell.transform", "mana", 30)
        self.assertEqual(PRICED.cost_of(slot, "spell.transform", "first"), 10)

    def test_a_cost_may_be_declared_that_did_not_exist(self):
        """A story may price an action only once it becomes available."""
        slot = COST_TABLE.init_state(None)
        COST_TABLE.set_cost(slot, "spell.wealth", "mana", 1)
        self.assertEqual(COST_TABLE.cost_of(slot, "spell.wealth"), 1)

    def test_declare_replaces_the_whole_entry(self):
        slot = PRICED.init_state(None)
        PRICED.declare(slot, "spell.transform", resource="mana", amount=5)
        self.assertEqual(PRICED.cost_of(slot, "spell.transform", "first"), 5, "the old variants are gone")

    def test_play_time_changes_survive_a_json_round_trip(self):
        slot = PRICED.init_state(None)
        PRICED.set_cost(slot, "spell.transform", "mana", 30)
        reloaded = json.loads(json.dumps(slot))
        self.assertEqual(PRICED.cost_of(reloaded, "spell.transform", "first"), 10)
        self.assertEqual(PRICED.cost_of(reloaded, "spell.transform"), 30)


class BindingTests(SimpleTestCase):
    """The Ink bindings are the same methods, over the session's own slot."""

    def test_the_bindings_answer_from_the_slot(self):
        """No rebuild per call -- the dict IS the session's live state."""
        slot = PRICED.init_state(None)
        bindings = PRICED.bind(slot, {}, {})
        self.assertEqual(sorted(bindings), ["can_afford", "cost_of", "is_priced", "set_cost"])
        self.assertEqual(bindings["cost_of"]("spell.transform", "first"), 10)
        self.assertTrue(bindings["can_afford"]("spell.transform", 15, "first"))
        self.assertFalse(bindings["can_afford"]("spell.transform", 15))

    def test_a_write_lands_in_the_session_state(self):
        """So it is already persisted when the turn ends, with no
        write-back step for a caller to forget."""
        slot = COST_TABLE.init_state(None)
        COST_TABLE.bind(slot, {}, {})["set_cost"]("spell.wealth", "mana", 1)
        self.assertEqual(slot["costs"]["spell.wealth"], {"resource": "mana", "amount": 1})

    def test_the_published_queries_are_the_readers(self):
        slot = PRICED.init_state(None)
        queries = PRICED.plugin().queries
        self.assertEqual(sorted(queries), ["cost_of", "is_priced", "resource_of"])
        self.assertEqual(queries["cost_of"](slot, "spell.charm", "cheaper"), 9)


class HostConfigTests(SimpleTestCase):
    """An application-attached price list is seeded into the slot at session start."""

    def test_a_host_config_is_declared_into_a_fresh_slot(self):
        engine_state: dict[str, Any] = {}
        bindings = resolve_bindings({"cost_table": PLUGIN}, ["cost_table"], engine_state, configs={"cost_table": CONFIG})
        self.assertEqual(bindings["cost_of"]("spell.transform", "first"), 10)
        self.assertEqual(engine_state["cost_table"]["costs"]["spell.charm"]["variants"], {"cheaper": 9})

    def test_a_bad_host_config_is_rejected_at_session_start(self):
        with self.assertRaises(SystemConfigValidationError):
            resolve_bindings({"cost_table": PLUGIN}, ["cost_table"], {}, configs={"cost_table": {"costs": {"x": {"amount": 1}}}})


class CostTableConfigValidationTests(SimpleTestCase):
    """The config is a closed schema, like every other system's."""

    def test_a_real_config_is_accepted(self):
        """Including an empty table: a story may opt in and price nothing yet."""
        validate_cost_table(CONFIG)
        validate_cost_table({})

    def test_a_bad_declared_config_fails_at_construction(self):
        with self.assertRaises(SystemConfigValidationError):
            CostTable(name="broken", config={"costs": {"x": {"resource": "mana"}}})

    def test_a_cost_needs_a_resource_and_an_amount(self):
        """Without them a cost cannot be paid or compared."""
        for bad in ({"resource": "mana"}, {"amount": 10}):
            with self.subTest(cost=bad), self.assertRaises(SystemConfigValidationError):
                validate_cost_table({"costs": {"x": bad}})

    def test_an_amount_must_be_a_number(self):
        """`True` is rejected explicitly: it is an int subclass in Python,
        and a boolean where a price belongs is a mistake."""
        for bad in (True, "ten", None):
            with self.subTest(amount=bad), self.assertRaises(SystemConfigValidationError):
                validate_cost_table({"costs": {"x": {"resource": "mana", "amount": bad}}})

    def test_variants_must_be_names_mapped_to_numbers(self):
        """The variant is a name the caller passes; its value is a price."""
        with self.assertRaises(SystemConfigValidationError):
            validate_cost_table({"costs": {"x": {"resource": "mana", "amount": 1, "variants": {"a": "cheap"}}}})
        with self.assertRaises(SystemConfigValidationError):
            validate_cost_table({"costs": {"x": {"resource": "mana", "amount": 1, "variants": [1, 2]}}})
