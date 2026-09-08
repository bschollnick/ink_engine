"""The closed, per-system config schema for a host's own config store.

Covers engine_config_schemas.py's own validators directly (pure functions,
no host framework needed). A host application's own enforcement of when
these validators run (e.g. on save, via a model's own clean() dispatch)
is that host's own concern and is tested in that host's own test suite.
"""

from __future__ import annotations

from unittest import TestCase as SimpleTestCase

from ink_engine.engine_config_schemas import (
    SystemConfigValidationError,
    validate_character_occupancy,
    validate_location_graph,
)

_VALID_LOCATION_GRAPH = {
    "locations": {
        "outside_hospital": {
            "known_by_default": True,
            "edges": [{"to": "hospital_foyer", "requires_known": False}],
        },
        "hospital_foyer": {
            "known_by_default": False,
            "edges": [],
        },
    },
}


class ValidateLocationGraphTests(SimpleTestCase):
    """Direct unit coverage of the one real registered validator."""

    def test_real_shape_from_a_converted_games_own_config_passes(self):
        """A shape modeled directly on a real converted game's own
        location_scenes.ink pattern (a named location, a known-by-default
        gate, real outgoing edges to other declared locations) validates
        cleanly."""
        validate_location_graph(_VALID_LOCATION_GRAPH)

    def test_top_level_must_be_an_object(self):
        """A list (or any non-dict) top-level value is rejected."""
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(["not", "an", "object"])

    def test_locations_must_not_be_empty(self):
        """An empty "locations" dict is rejected — a real config declares
        at least one real location."""
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph({"locations": {}})

    def test_edge_to_an_undeclared_location_is_rejected(self):
        """A real, closed graph — no dangling edges to a location_id that
        was never itself declared under "locations"."""
        config = {
            "locations": {
                "a": {"known_by_default": True, "edges": [{"to": "nonexistent"}]},
            },
        }
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_known_by_default_must_be_a_real_bool_not_a_truthy_value(self):
        """A closed schema rejects "truthy but not actually a bool" (e.g.
        the string "true", or 1) rather than silently coercing it — the
        plan's own "never arbitrary JSON interpreted flexibly" requirement
        means a wrong type is a real error, not a convenience cast."""
        config = {"locations": {"a": {"known_by_default": "true", "edges": []}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_edges_must_be_a_list(self):
        """A non-list "edges" value is rejected."""
        config = {"locations": {"a": {"known_by_default": True, "edges": "not-a-list"}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)


# Bare minute-of-day integers below (not scheduling.py's named hour
# constants like EIGHT_AM/SIX_PM) because this is real serialized JSON
# config data, which can't reference a Python constant. Each range is
# commented with the real clock time it represents so the fixture stays
# readable anyway.
_VALID_CHARACTER_OCCUPANCY = {
    "characters": {
        "npc_id": {
            "schedule": [
                {
                    "condition": {
                        "kind": "and",
                        "clauses": [
                            {"kind": "minute_in_range", "minute_low": 480, "minute_high": 1080},  # 8:00am-6:00pm
                            {"kind": "minute_in_range", "minute_low": 720, "minute_high": 1440},  # noon-midnight
                        ],
                    },
                    "location_id": "school_nurse_office",
                },
                {
                    "condition": {"kind": "minute_in_range", "minute_low": 480, "minute_high": 1080},  # 8:00am-6:00pm
                    "location_id": "hospital_office",
                },
                {
                    "condition": {
                        "kind": "and",
                        "clauses": [
                            {"kind": "not", "clauses": [{"kind": "minute_in_range", "minute_low": 360, "minute_high": 1200}]},  # 6:00am-8:00pm
                            {"kind": "or", "clauses": [{"kind": "flag", "flag": "deal_made"}, {"kind": "flag", "flag": "charmed"}]},
                        ],
                    },
                    "location_id": "hotel_room",
                },
                {"condition": None, "location_id": None},
            ],
        },
    },
}


class ValidateCharacterOccupancyTests(SimpleTestCase):
    """Direct unit coverage of the character_occupancy validator, against
    a real Doctor-Kay-shaped multi-condition priority chain."""

    def test_real_doctor_kay_shape_passes(self):
        """The exact multi-condition priority chain shape real
        _place_now() functions already use validates cleanly."""
        validate_character_occupancy(_VALID_CHARACTER_OCCUPANCY)

    def test_top_level_must_be_an_object(self):
        """A list (or any non-dict) top-level value is rejected."""
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(["not", "an", "object"])

    def test_characters_must_not_be_empty(self):
        """An empty "characters" dict is rejected."""
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy({"characters": {}})

    def test_schedule_must_not_be_empty(self):
        """A character with no schedule rules at all is rejected — every
        real character has at least a fallback rule."""
        config = {"characters": {"a": {"schedule": []}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(config)

    def test_missing_location_id_is_rejected(self):
        """location_id must be present (even if null) — a rule without it
        at all is a real shape error, not "assume absent"."""
        config = {"characters": {"a": {"schedule": [{"condition": None}]}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(config)

    def test_unknown_condition_kind_is_rejected(self):
        """A condition kind outside the closed vocabulary is rejected —
        never silently ignored or treated as always-true/false."""
        config = {"characters": {"a": {"schedule": [{"condition": {"kind": "eval"}, "location_id": "x"}]}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(config)

    def test_minute_in_range_bounds_must_be_in_0_to_1440(self):
        """A minute_low/minute_high outside the real 0-1440 minute-per-day
        range is rejected, not silently clamped."""
        config = {
            "characters": {
                "a": {
                    "schedule": [
                        {"condition": {"kind": "minute_in_range", "minute_low": 0, "minute_high": 9999}, "location_id": "x"},
                    ],
                },
            },
        }
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(config)

    def test_not_condition_requires_exactly_one_clause(self):
        """A "not" with 0 or 2+ clauses is rejected — it inverts exactly
        one child condition, matching character_occupancy.Condition.negate()."""
        config = {
            "characters": {
                "a": {
                    "schedule": [
                        {
                            "condition": {"kind": "not", "clauses": [{"kind": "flag", "flag": "x"}, {"kind": "flag", "flag": "y"}]},
                            "location_id": "z",
                        },
                    ],
                },
            },
        }
        with self.assertRaises(SystemConfigValidationError):
            validate_character_occupancy(config)


class LocationDetailsValidationTests(SimpleTestCase):
    """`details` is where everything else about a location lives.

    It exists so a game has ONE declared home for its per-location facts.
    Before it, the reference game kept discovery in its location module,
    place numbers in its occupancy module and outdoor flags in its
    scheduling module — three structures, two different keys — and the
    vocabularies drifted until 95 ids a character could be placed at were
    absent from the map entirely.

    The engine defines a few keys and validates their types; every other
    key is the story's own and is kept as long as its value is a plain
    JSON-safe scalar. That boundary is what keeps this from becoming the
    "arbitrary JSON interpreted flexibly" this module exists to prevent.
    """

    @staticmethod
    def _config(details):
        """Return a one-location config carrying `details`.

        Args:
            details: The details dict to validate.

        Returns:
            A `location_graph` config shaped around it.
        """
        return {"locations": {"cellar": {"known_by_default": True, "details": details}}}

    def test_the_engine_defined_keys_are_accepted(self):
        """A location may declare all of them at once."""
        validate_location_graph(
            self._config(
                {
                    "name": "Police Station - Jail Cell",
                    "description": "A cell.",
                    "external_identifier": [260, 261],
                    "terrain": "indoor",
                    "region": "Police Station",
                    "lit": True,
                    "visits": 0,
                }
            )
        )

    def test_a_story_may_add_its_own_keys(self):
        """Anything the engine does not define is the game's, kept as-is."""
        validate_location_graph(self._config({"story_scene": "cell_guarded", "story_place": 261}))

    def test_a_story_key_may_not_hold_a_structure(self):
        """Scalars only — a nested structure here would be config the
        engine stores without ever validating its shape."""
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config({"story_scenes": {"nested": "dict"}}))

    def test_an_unknown_terrain_is_rejected(self):
        """Terrain fixes the movement cost of arriving, so an unrecognised
        one would silently charge the default instead of what was meant."""
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config({"terrain": "swamp"}))

    def test_visited_cannot_be_declared(self):
        """`visited` is derived from `visits`. Declaring both would let one
        fact have two sources that can disagree."""
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config({"visited": True}))

    def test_visits_must_be_a_non_negative_integer(self):
        """It is a count of entries, so `true` and -1 are both mistakes."""
        for bad in (True, -1, "twice"):
            with self.subTest(visits=bad), self.assertRaises(SystemConfigValidationError):
                validate_location_graph(self._config({"visits": bad}))

    def test_an_external_identifier_is_a_list(self):
        """A list because one location can be several ids upstream — a room
        and that same room mid-scene are one place to stand."""
        validate_location_graph(self._config({"external_identifier": ["room_a", 12]}))
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config({"external_identifier": 260}))
