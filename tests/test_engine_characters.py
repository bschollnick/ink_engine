"""`engine_plugins.characters` -- per-character keyed storage, known-state,
and the delegating location read.

The property worth guarding hardest is what this plugin does NOT store: a
character's location lives in the occupancy plugin, and
`current_location()` must read through to it rather than keeping a copy.
A regression there would reintroduce a two-records-of-one-fact bug and
would not otherwise show up as a failure.

Generic fixtures only -- no story names.
"""

from __future__ import annotations

import json
from unittest import TestCase as SimpleTestCase

from ink_engine.engine_plugins.characters import CHARACTERS, PLUGIN


def _slot():
    return CHARACTERS.init_state(None)


class AttributeTests(SimpleTestCase):
    """The storage this plugin actually owns."""

    def test_a_stored_attribute_reads_back(self):
        """The base case."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag12", True)
        self.assertTrue(CHARACTERS.read_attribute(slot, "alice", "flag12"))

    def test_attributes_are_per_character(self):
        """The point of keying by character: the same attribute name on two
        characters is two independent facts."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag1", True)
        CHARACTERS.set_attribute(slot, "bob", "flag1", False)
        self.assertTrue(CHARACTERS.read_attribute(slot, "alice", "flag1"))
        self.assertFalse(CHARACTERS.read_attribute(slot, "bob", "flag1"))

    def test_an_unset_attribute_reads_as_false_by_default(self):
        """Story content asks about facts that have not happened far more
        often than ones that have, so absence must not raise."""
        self.assertFalse(CHARACTERS.read_attribute(_slot(), "alice", "never_set"))

    def test_an_explicit_default_is_honoured(self):
        """A counter starting at 0, a name starting empty."""
        self.assertEqual(CHARACTERS.read_attribute(_slot(), "alice", "stage", 0), 0)
        self.assertEqual(CHARACTERS.read_attribute(_slot(), "alice", "title", ""), "")

    def test_existence_is_distinct_from_truthiness(self):
        """A flag explicitly set False is not the same as one never set --
        a story that must tell those apart has no other way to."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "agreed", False)
        self.assertFalse(CHARACTERS.read_attribute(slot, "alice", "agreed"))
        self.assertTrue(CHARACTERS.attribute_exists(slot, "alice", "agreed"))
        self.assertFalse(CHARACTERS.attribute_exists(slot, "alice", "never_set"))

    def test_values_may_be_any_json_safe_scalar(self):
        """Numbered flags are booleans, but stages are numbers and some
        facts are text; all must survive."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag", True)
        CHARACTERS.set_attribute(slot, "alice", "stage", 3)
        CHARACTERS.set_attribute(slot, "alice", "fraction", 2.2)
        CHARACTERS.set_attribute(slot, "alice", "note", "hello")
        self.assertEqual(CHARACTERS.attributes(slot, "alice"), {"flag": True, "stage": 3, "fraction": 2.2, "note": "hello"})

    def test_state_is_keyed_by_character_first(self):
        """The storage shape is load-bearing, not incidental: a path into
        it must read as the sentence the caller is saying --
        `(character, "attributes", name)`. Schedule conditions address it
        by that path, so flipping the nesting would silently break them."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag12", True)
        self.assertEqual(slot["records"], {"alice": {"attributes": {"flag12": True}}})

    def test_clearing_removes_only_that_character(self):
        """One character's reset must not disturb another's."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag", True)
        CHARACTERS.set_attribute(slot, "bob", "flag", True)
        CHARACTERS.clear_attributes(slot, "alice")
        self.assertFalse(CHARACTERS.read_attribute(slot, "alice", "flag"))
        self.assertTrue(CHARACTERS.read_attribute(slot, "bob", "flag"))

    def test_clearing_attributes_keeps_known_state(self):
        """Forgetting the details about someone is not the same as never
        having met them."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag", True)
        CHARACTERS.set_character_known(slot, "alice", True)
        CHARACTERS.clear_attributes(slot, "alice")
        self.assertTrue(CHARACTERS.character_known(slot, "alice"))

    def test_attributes_returns_an_independent_copy(self):
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag", True)
        snapshot = CHARACTERS.attributes(slot, "alice")
        snapshot["flag"] = False
        self.assertTrue(CHARACTERS.read_attribute(slot, "alice", "flag"))


class KnownStateTests(SimpleTestCase):
    """"Have I met this person" -- the one uniform question worth its own
    vocabulary, mirroring `location_graph`'s own known-set."""

    def test_a_character_starts_unknown_and_becomes_known(self):
        slot = _slot()
        self.assertFalse(CHARACTERS.character_known(slot, "alice"))
        CHARACTERS.set_character_known(slot, "alice", True)
        self.assertTrue(CHARACTERS.character_known(slot, "alice"))

    def test_known_state_can_be_taken_back(self):
        """An erased memory, a mistaken identity."""
        slot = _slot()
        CHARACTERS.set_character_known(slot, "alice", True)
        CHARACTERS.set_character_known(slot, "alice", False)
        self.assertFalse(CHARACTERS.character_known(slot, "alice"))

    def test_marking_known_twice_is_harmless(self):
        """Story content re-runs; a second introduction must not error."""
        slot = _slot()
        CHARACTERS.set_character_known(slot, "alice", True)
        CHARACTERS.set_character_known(slot, "alice", True)
        self.assertEqual(CHARACTERS.known_characters(slot), ["alice"])

    def test_forgetting_someone_never_met_is_harmless(self):
        slot = _slot()
        CHARACTERS.set_character_known(slot, "alice", False)
        self.assertEqual(CHARACTERS.known_characters(slot), [])

    def test_known_state_does_not_disturb_attributes(self):
        """The two halves of this plugin are independent."""
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag", True)
        CHARACTERS.set_character_known(slot, "alice", True)
        self.assertTrue(CHARACTERS.read_attribute(slot, "alice", "flag"))

    def test_the_saved_form_is_stable(self):
        """`known` is a set in spirit; saving it unordered would produce a
        different payload on every save for identical state, which makes
        saves diff noisily and hides real changes."""
        first, second = _slot(), _slot()
        CHARACTERS.set_character_known(first, "bob", True)
        CHARACTERS.set_character_known(first, "alice", True)
        CHARACTERS.set_character_known(second, "alice", True)
        CHARACTERS.set_character_known(second, "bob", True)
        self.assertEqual(first, second)


class DelegationTests(SimpleTestCase):
    """What this plugin deliberately does NOT own."""

    def test_location_is_read_from_the_occupancy_slot(self):
        """The load-bearing property: a character's location is answered
        from the plugin that owns it, so there is exactly one record of
        it."""
        slot = _slot()
        occupancy = {"locations": {"alice": "the_square"}}
        bindings = PLUGIN.bind(slot, {"characters": slot, "character_occupancy": occupancy}, {})
        self.assertEqual(bindings["current_location"]("alice"), "the_square")
        occupancy["locations"]["alice"] = "the_shop"
        self.assertEqual(bindings["current_location"]("alice"), "the_shop", "tracked live, not a snapshot taken at bind time")

    def test_an_unplaced_character_reads_as_empty(self):
        """Matches the empty-string convention story bindings use, since
        Ink has no None."""
        slot = _slot()
        self.assertEqual(PLUGIN.bind(slot, {"character_occupancy": {"locations": {}}}, {})["current_location"]("alice"), "")
        self.assertEqual(PLUGIN.bind(slot, {}, {})["current_location"]("alice"), "")

    def test_this_plugin_stores_no_location_of_its_own(self):
        """Stated as a test so it cannot be quietly changed: the slot this
        plugin owns has no location in it at all."""
        self.assertEqual(sorted(_slot()), ["known", "records"])


class SerializationTests(SimpleTestCase):
    """State must survive a session save/load like every other plugin's."""

    def test_round_trips_through_real_json(self):
        slot = _slot()
        CHARACTERS.set_attribute(slot, "alice", "flag12", True)
        CHARACTERS.set_attribute(slot, "bob", "stage", 3)
        CHARACTERS.set_character_known(slot, "alice", True)
        restored = json.loads(json.dumps(slot))
        self.assertTrue(CHARACTERS.read_attribute(restored, "alice", "flag12"))
        self.assertEqual(CHARACTERS.read_attribute(restored, "bob", "stage"), 3)
        self.assertEqual(CHARACTERS.known_characters(restored), ["alice"])


class BindingTests(SimpleTestCase):
    """The EXTERNAL surface a story actually calls."""

    def setUp(self):
        self.slot = PLUGIN.init_state(None)
        self.bindings = PLUGIN.bind(self.slot, {"characters": self.slot}, {})

    def test_the_bindings_are_published_under_the_method_names(self):
        self.assertEqual(
            sorted(self.bindings),
            ["attribute_exists", "character_known", "clear_attributes", "current_location", "read_attribute", "set_attribute", "set_character_known"],
        )

    def test_writes_persist_into_the_session_slot(self):
        """A binding that did not write through would lose everything at
        the end of the request."""
        self.bindings["set_attribute"]("alice", "flag12", True)
        self.assertTrue(self.slot["records"]["alice"]["attributes"]["flag12"])

    def test_the_full_attribute_surface_round_trips(self):
        """set/read/exists/clear through the bindings, as Ink uses them."""
        self.bindings["set_attribute"]("alice", "flag12", True)
        self.assertTrue(self.bindings["read_attribute"]("alice", "flag12"))
        self.assertTrue(self.bindings["attribute_exists"]("alice", "flag12"))
        self.bindings["clear_attributes"]("alice")
        self.assertFalse(self.bindings["attribute_exists"]("alice", "flag12"))

    def test_known_state_round_trips_through_the_bindings(self):
        """A getter plus one boolean-taking setter, mirroring the map's."""
        self.assertFalse(self.bindings["character_known"]("alice"))
        self.bindings["set_character_known"]("alice", True)
        self.assertTrue(self.bindings["character_known"]("alice"))
        self.bindings["set_character_known"]("alice", False)
        self.assertFalse(self.bindings["character_known"]("alice"))

    def test_the_published_queries_are_the_readers(self):
        self.bindings["set_attribute"]("alice", "stage", 4)
        queries = PLUGIN.queries
        self.assertEqual(sorted(queries), ["attribute_exists", "character_known", "read_attribute"])
        self.assertEqual(queries["read_attribute"](self.slot, "alice", "stage"), 4)

    def test_the_plugin_declares_its_own_state_slot(self):
        self.assertEqual(PLUGIN.state_key, "characters")
