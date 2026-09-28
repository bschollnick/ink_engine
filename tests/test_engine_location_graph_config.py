"""The closed config schema `location_graph` declares for its own config.

Covers the validator directly (a pure function, no application framework
needed). An application's own enforcement of when it runs -- on a
model's save, say -- is that application's concern and is tested there.
"""

from __future__ import annotations

from unittest import TestCase as SimpleTestCase

from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.engine_plugins.location_graph import (
    EXIT_POSITIONS,
    RETURN_DIRECTION,
    add_missing_return_exits,
    validate_location_graph,
)

_VALID_LOCATION_GRAPH = {
    "locations": {
        "outside_hospital": {
            "known_by_default": True,
            "exits": [{"to": "hospital_foyer", "requires_known": False}],
        },
        "hospital_foyer": {
            "known_by_default": False,
            "exits": [],
        },
    },
}


class ValidateLocationGraphTests(SimpleTestCase):
    """Direct unit coverage of the one real registered validator."""

    def test_real_shape_from_a_converted_games_own_config_passes(self):
        """A shape modeled directly on a real converted game's own
        location_scenes.ink pattern (a named location, a known-by-default
        gate, real outgoing exits to other declared locations) validates
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

    def test_exit_to_an_undeclared_location_is_rejected(self):
        """A real, closed graph — no dangling exits to a location_id that
        was never itself declared under "locations"."""
        config = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "nonexistent"}]},
            },
        }
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_known_by_default_must_be_a_real_bool_not_a_truthy_value(self):
        """A closed schema rejects "truthy but not actually a bool" (e.g.
        the string "true", or 1) rather than silently coercing it — the
        plan's own "never arbitrary JSON interpreted flexibly" requirement
        means a wrong type is a real error, not a convenience cast."""
        config = {"locations": {"a": {"known_by_default": "true", "exits": []}}}
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_exits_must_be_a_list(self):
        """A non-list "exits" value is rejected."""
        config = {"locations": {"a": {"known_by_default": True, "exits": "not-a-list"}}}
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
                    "location_id": "infirmary",
                },
                {
                    "condition": {"kind": "minute_in_range", "minute_low": 480, "minute_high": 1080},  # 8:00am-6:00pm
                    "location_id": "clinic_office",
                },
                {
                    "condition": {
                        "kind": "and",
                        "clauses": [
                            {"kind": "not", "clauses": [{"kind": "minute_in_range", "minute_low": 360, "minute_high": 1200}]},  # 6:00am-8:00pm
                            {"kind": "or", "clauses": [{"kind": "flag", "flag": "deal_made"}, {"kind": "flag", "flag": "charmed"}]},
                        ],
                    },
                    "location_id": "inn_room",
                },
                {"condition": None, "location_id": None},
            ],
        },
    },
}


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
                    "entrance": True,
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

    def test_entrance_must_be_a_boolean(self):
        """`entrance` is a flag, like `lit`."""
        for bad in ("yes", 1):
            with self.subTest(entrance=bad), self.assertRaises(SystemConfigValidationError):
                validate_location_graph(self._config({"entrance": bad}))

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


def _one_location_with_exits(exits: list) -> dict:
    """Return a two-location config whose first location declares `exits`."""
    return {
        "locations": {
            "a": {"known_by_default": True, "exits": exits},
            "b": {"known_by_default": True},
        }
    }


class ExitPositionTests(SimpleTestCase):
    """The closed set of positions an exit may occupy."""

    def test_every_return_direction_is_its_own_return(self):
        for position in EXIT_POSITIONS:
            self.assertEqual(RETURN_DIRECTION[RETURN_DIRECTION[position]], position)

    def test_every_return_direction_is_itself_a_position(self):
        for returning in RETURN_DIRECTION.values():
            self.assertIn(returning, EXIT_POSITIONS)

    def test_an_unknown_position_is_rejected(self):
        config = _one_location_with_exits([{"to": "b", "position": "widdershins"}])
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_two_exits_cannot_share_a_position_from_one_location(self):
        config = _one_location_with_exits([{"to": "b", "position": "s"}, {"to": "b", "position": "s"}])
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)

    def test_the_same_position_from_different_locations_is_fine(self):
        config = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "b", "position": "s"}]},
                "b": {"known_by_default": True, "exits": [{"to": "a", "position": "s"}]},
            }
        }
        validate_location_graph(config)


class ExitSchemaTests(SimpleTestCase):
    """The optional fields an exit may carry."""

    def test_an_exit_with_only_a_destination_still_validates(self):
        validate_location_graph(_one_location_with_exits([{"to": "b"}]))

    def test_an_arrival_knot_without_travel_text_is_rejected(self):
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(_one_location_with_exits([{"to": "b", "arrival_knot": "k"}]))

    def test_travel_text_without_an_arrival_knot_is_rejected(self):
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(_one_location_with_exits([{"to": "b", "travel_text": "You walk."}]))

    def test_an_arrival_knot_and_travel_text_together_validate(self):
        validate_location_graph(_one_location_with_exits([{"to": "b", "arrival_knot": "k", "travel_text": "You walk."}]))

    def test_a_non_boolean_gate_is_rejected(self):
        for field in ("sealed", "one_way", "show_when_blocked", "requires_known"):
            with self.subTest(field=field), self.assertRaises(SystemConfigValidationError):
                validate_location_graph(_one_location_with_exits([{"to": "b", field: "yes"}]))

    def test_a_non_string_unlocked_by_is_rejected(self):
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(_one_location_with_exits([{"to": "b", "unlocked_by": 7}]))


class LocationArrivalTests(SimpleTestCase):
    """A location's own `arrival_knot` and `arrival_text`."""

    def _config(self, **hall: object) -> dict:
        return {"locations": {"hall": {"known_by_default": True, **hall}}}

    def test_an_arrival_knot_and_text_validate(self):
        validate_location_graph(self._config(arrival_knot="hall", arrival_text="You come in."))

    def test_an_arrival_knot_alone_validates(self):
        validate_location_graph(self._config(arrival_knot="hall"))

    def test_arrival_text_without_a_knot_is_rejected(self):
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config(arrival_text="You come in."))

    def test_a_non_string_arrival_knot_is_rejected(self):
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(self._config(arrival_knot=3))


class ReturnExitTests(SimpleTestCase):
    """add_missing_return_exits() fills in the journey back."""

    def test_a_return_arrives_through_the_origin_arrival_knot(self):
        config = {
            "locations": {
                "hall": {
                    "known_by_default": True,
                    "arrival_knot": "hall_knot",
                    "arrival_text": "You go back in.",
                    "exits": [{"to": "yard", "position": "s", "arrival_knot": "yard_knot", "travel_text": "Out."}],
                },
                "yard": {"known_by_default": True},
            }
        }
        filled = add_missing_return_exits(config)
        validate_location_graph(filled)
        returning = filled["locations"]["yard"]["exits"][0]
        self.assertEqual(returning["arrival_knot"], "hall_knot")
        self.assertEqual(returning["travel_text"], "You go back in.")

    def test_a_return_without_arrival_text_travels_silently(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "arrival_knot": "hall_knot", "exits": [{"to": "yard", "position": "s"}]},
                "yard": {"known_by_default": True},
            }
        }
        returning = add_missing_return_exits(config)["locations"]["yard"]["exits"][0]
        self.assertEqual(returning["travel_text"], "")

    def test_a_return_into_a_location_with_no_arrival_knot_has_none(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "exits": [{"to": "yard", "position": "s"}]},
                "yard": {"known_by_default": True},
            }
        }
        returning = add_missing_return_exits(config)["locations"]["yard"]["exits"][0]
        self.assertNotIn("arrival_knot", returning)
        self.assertNotIn("travel_text", returning)

    def test_a_two_way_exit_gains_its_return(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "details": {"name": "Hall"}, "exits": [{"to": "yard", "position": "s", "label": "the yard"}]},
                "yard": {"known_by_default": True, "details": {"name": "Yard"}},
            }
        }
        filled = add_missing_return_exits(config)
        returning = filled["locations"]["yard"]["exits"]
        self.assertEqual(len(returning), 1)
        self.assertEqual(returning[0]["to"], "hall")
        self.assertEqual(returning[0]["position"], "n")
        self.assertEqual(returning[0]["label"], "Hall")

    def test_a_one_way_exit_gains_nothing(self):
        config = {
            "locations": {
                "attic": {"known_by_default": True, "exits": [{"to": "cellar", "position": "down", "one_way": True}]},
                "cellar": {"known_by_default": True},
            }
        }
        filled = add_missing_return_exits(config)
        self.assertEqual(filled["locations"]["cellar"].get("exits"), [])

    def test_a_declared_return_is_never_overwritten(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "exits": [{"to": "yard", "position": "s"}]},
                "yard": {"known_by_default": True, "exits": [{"to": "hall", "position": "n", "label": "the long way round"}]},
            }
        }
        filled = add_missing_return_exits(config)
        self.assertEqual(len(filled["locations"]["yard"]["exits"]), 1)
        self.assertEqual(filled["locations"]["yard"]["exits"][0]["label"], "the long way round")

    def test_an_exit_with_no_position_gains_nothing(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "exits": [{"to": "yard", "label": "walk over"}]},
                "yard": {"known_by_default": True},
            }
        }
        self.assertEqual(add_missing_return_exits(config)["locations"]["yard"].get("exits"), [])

    def test_the_original_config_is_not_modified(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "exits": [{"to": "yard", "position": "s"}]},
                "yard": {"known_by_default": True},
            }
        }
        add_missing_return_exits(config)
        self.assertNotIn("exits", config["locations"]["yard"])

    def test_the_filled_config_still_validates(self):
        config = {
            "locations": {
                "hall": {"known_by_default": True, "exits": [{"to": "yard", "position": "s"}]},
                "yard": {"known_by_default": True},
            }
        }
        validate_location_graph(add_missing_return_exits(config))
