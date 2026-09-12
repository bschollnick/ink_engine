"""Every shipped plugin, certified against the contract it declares.

`test_plugin_contract.py` proves the MECHANISM works, using purpose-built
plugins defined in that file. This module proves the plugins the library
actually ships satisfy that mechanism — a different question, and the one
that breaks. A contract change can leave every mechanism test green while
a shipped plugin no longer conforms, because nothing here asserted that it
did.

**Why this file must not know any plugin's name.** Each test walks
whatever `discover_plugins(ENGINE_PLUGIN_PACKAGE)` returns and asserts the
contract against all of them, so a plugin added later is certified the day
it lands with no edit here. A test naming one plugin certifies that plugin
and quietly exempts the rest.

**Why the library certifies itself.** A game's own suite covers that
game's use of the API, which overlaps this but is not a substitute: a
consumer exercises the parts it happens to use, so a capability no game
calls is uncertified exactly when a refactor is most likely to break it.
The library must be able to answer "do the plugins still work" without
running a game's tests.

This is deliberately breadth, not depth. Per-plugin behaviour lives in
that plugin's own test module; what is proved here is that every shipped
plugin is discoverable, allocates and round-trips its state, binds without
error, and answers its declared queries.
"""

from __future__ import annotations

import inspect
import json
from typing import Any
from unittest import TestCase

from ink_engine.binding import resolve_bindings
from ink_engine.discovery import ENGINE_PLUGIN_PACKAGE, discover_plugins
from ink_engine.plugin import Plugin

SHIPPED_PLUGINS: dict[str, Plugin] = discover_plugins([ENGINE_PLUGIN_PACKAGE])


def _unknown_arguments_for(query: Any) -> list[str]:
    """Return one placeholder per required argument a query takes.

    Every shipped query names things — a character, a place, an attribute
    — so a string that cannot match anything is a valid value for each.
    Derived from the signature so a query's arity is never duplicated as
    a literal in a test.

    Args:
        query: The query callable, whose first parameter is its plugin's
            own slot and is therefore skipped.

    Returns:
        Placeholder arguments to pass after the slot.
    """
    parameters = list(inspect.signature(query).parameters.values())[1:]
    required = [
        parameter
        for parameter in parameters
        if parameter.default is inspect.Parameter.empty and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]
    return ["certification_no_such_identifier"] * len(required)


def _fresh_state() -> dict[str, Any]:
    """Return a session state with every shipped plugin's slot allocated.

    Returns:
        The engine state after binding every shipped plugin once.
    """
    state: dict[str, Any] = {}
    resolve_bindings(SHIPPED_PLUGINS, list(SHIPPED_PLUGINS), state, list_defs={})
    return state


class ShippedPluginsDiscoveryTests(TestCase):
    """The library's own plugin package resolves to real plugins."""

    def test_the_shipped_package_yields_plugins(self):
        """An empty result would make every other test here vacuous, so it
        is asserted rather than assumed."""
        self.assertTrue(SHIPPED_PLUGINS, "the engine's own plugin package discovered nothing")

    def test_every_discovered_plugin_is_a_plugin_instance(self):
        """Discovery returns the contract type, not whatever a module
        happened to name `PLUGIN`."""
        for name, plugin in SHIPPED_PLUGINS.items():
            with self.subTest(plugin=name):
                self.assertIsInstance(plugin, Plugin)

    def test_every_plugin_is_keyed_by_its_own_name(self):
        """The registry key and the plugin's own `name` must agree, since
        a manifest names plugins by the latter and activation looks them
        up by the former."""
        for key, plugin in SHIPPED_PLUGINS.items():
            with self.subTest(plugin=key):
                self.assertEqual(key, plugin.name)

    def test_every_plugin_declares_a_display_name(self):
        """A host renders this; an empty one is a silent blank in a UI."""
        for name, plugin in SHIPPED_PLUGINS.items():
            with self.subTest(plugin=name):
                self.assertTrue(plugin.display_name.strip(), f"'{name}' declares an empty display_name")


class ShippedPluginsStateTests(TestCase):
    """Every stateful shipped plugin allocates and persists real state."""

    def test_every_stateful_plugin_allocates_its_slot(self):
        """Binding a fresh session must create each declared slot — a
        plugin whose slot is missing reads its own state as absent."""
        state = _fresh_state()
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.state_key is None:
                continue
            with self.subTest(plugin=name):
                self.assertIn(plugin.state_key, state)

    def test_every_plugins_initial_state_is_json_safe(self):
        """A host persists session state as JSON. A plugin whose fresh
        state holds a set or a dataclass breaks saving for every story
        that activates it, which no in-memory test would notice."""
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.init_state is None:
                continue
            with self.subTest(plugin=name):
                json.dumps(plugin.init_state(None))

    def test_the_whole_session_state_is_json_safe(self):
        """The per-plugin check above passes even if two plugins sharing
        one slot merge into something unserializable, so the assembled
        state is checked as a whole too."""
        json.dumps(_fresh_state())

    def test_a_fresh_session_state_round_trips_through_json(self):
        """Saving and reloading must return the same state. A value that
        serializes but does not compare equal after reload (a tuple
        becoming a list, say) is a save-corruption bug."""
        state = _fresh_state()
        self.assertEqual(json.loads(json.dumps(state)), state)

    def test_rebinding_reuses_existing_state_rather_than_resetting_it(self):
        """Every turn rebinds. A plugin that reinitialises its slot on
        rebind silently discards the session's progress."""
        state = _fresh_state()
        for plugin in SHIPPED_PLUGINS.values():
            if plugin.state_key is not None:
                state[plugin.state_key]["certification_marker"] = 1
        resolve_bindings(SHIPPED_PLUGINS, list(SHIPPED_PLUGINS), state, list_defs={})
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.state_key is None:
                continue
            with self.subTest(plugin=name):
                self.assertEqual(state[plugin.state_key].get("certification_marker"), 1)


class ShippedPluginsBindingTests(TestCase):
    """Every shipped plugin binds, and the assembled surface is coherent."""

    def test_binding_every_shipped_plugin_at_once_succeeds(self):
        """The combination is what a host actually activates; a plugin
        that binds alone but raises beside another is broken in practice."""
        resolve_bindings(SHIPPED_PLUGINS, list(SHIPPED_PLUGINS), {}, list_defs={})

    def test_every_binding_is_callable(self):
        """A binding is handed to the Ink runtime and invoked; a
        non-callable entry fails only when a story reaches that line."""
        bindings = resolve_bindings(SHIPPED_PLUGINS, list(SHIPPED_PLUGINS), {}, list_defs={})
        for name, function in bindings.items():
            with self.subTest(binding=name):
                self.assertTrue(callable(function), f"binding '{name}' is not callable")

    def test_each_plugin_binds_in_isolation(self):
        """A plugin reading another's slot must tolerate that slot being
        absent, since a story may activate it alone."""
        for name, plugin in SHIPPED_PLUGINS.items():
            with self.subTest(plugin=name):
                resolve_bindings(SHIPPED_PLUGINS, [name], {}, list_defs={})

    def test_no_two_shipped_plugins_collide_on_a_binding_name(self):
        """A later plugin overriding an earlier one's binding is a real
        feature, but between the library's OWN plugins it is an accident:
        one of them would be permanently shadowed."""
        seen: dict[str, str] = {}
        for name in SHIPPED_PLUGINS:
            for binding_name in resolve_bindings(SHIPPED_PLUGINS, [name], {}, list_defs={}):
                owner = seen.get(binding_name)
                self.assertIsNone(owner, f"'{binding_name}' is declared by both '{owner}' and '{name}'")
                seen[binding_name] = name

    def test_bind_receives_the_full_three_argument_shape(self):
        """`Plugin.bind` is always `(own_state, engine_state, list_defs)`.
        A plugin written to an older signature raises at bind time, and
        this proves the shipped ones are all current."""
        tables = {"Certification": {"item": 1}}
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.bind is None:
                continue
            with self.subTest(plugin=name):
                state: dict[str, Any] = {}
                resolve_bindings(SHIPPED_PLUGINS, [name], state, list_defs=tables)


class ShippedPluginsQueryTests(TestCase):
    """Every declared query answers from its own plugin's slot."""

    def test_every_declared_query_is_callable(self):
        for name, plugin in SHIPPED_PLUGINS.items():
            for query_name, query in plugin.queries.items():
                with self.subTest(plugin=name, query=query_name):
                    self.assertTrue(callable(query))

    def test_a_plugin_declaring_queries_also_owns_state(self):
        """A query is defined as a question about the plugin's OWN slot,
        so a stateless plugin declaring one has nothing to answer from."""
        for name, plugin in SHIPPED_PLUGINS.items():
            if not plugin.queries:
                continue
            with self.subTest(plugin=name):
                self.assertIsNotNone(plugin.state_key, f"'{name}' declares queries but owns no state")

    def test_every_query_answers_against_a_fresh_slot_without_raising(self):
        """A query is called with unknown identifiers during play — a
        character not yet met, a place not yet found. Answering "no"
        rather than raising is the contract, so each is called against a
        brand-new slot with identifiers that cannot exist.

        Arity comes from each query's own signature rather than a fixed
        guess, so a query taking two names is certified the same way as
        one taking a single id, with no list to keep in step here."""
        state = _fresh_state()
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.state_key is None:
                continue
            slot = state[plugin.state_key]
            for query_name, query in plugin.queries.items():
                with self.subTest(plugin=name, query=query_name):
                    query(slot, *_unknown_arguments_for(query))


class ShippedPluginsValidatorTests(TestCase):
    """A declared config validator must really validate."""

    def test_every_declared_validator_rejects_a_non_object_config(self):
        """Config arrives as decoded JSON from a host's store. A validator
        that accepts a list or a string is not closing the shape it
        exists to close."""
        for name, plugin in SHIPPED_PLUGINS.items():
            if plugin.validate_config is None:
                continue
            with self.subTest(plugin=name):
                with self.assertRaises(Exception):
                    plugin.validate_config(["not", "an", "object"])
