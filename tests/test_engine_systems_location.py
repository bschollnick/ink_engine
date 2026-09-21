"""The two independent LocationSystem layers (ink_engine.engine_plugins.
location_graph, ink_engine.engine_plugins.character_occupancy).

Pure-function coverage — no application framework needed. SimpleTestCase throughout.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from unittest import TestCase as SimpleTestCase

import ink_engine.engine_plugins.character_occupancy as character_occupancy_module
import ink_engine.engine_plugins.location_graph as location_graph_module
from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.engine_plugins.character_occupancy import (
    CHARACTER_OCCUPANCY,
    Condition,
    ScheduleRule,
    UnknownLocationError,
    resolve_present_characters,
    resolve_schedule,
)
from ink_engine.engine_plugins.location_graph import LocationGraph
from ink_engine.engine_plugins.scheduling import (
    EIGHT_AM,
    EIGHT_PM,
    MINUTES_PER_DAY,
    NOON,
    SIX_AM,
    SIX_PM,
)

_LOCATION_CONFIG = {
    "locations": {
        "outside_hospital": {
            "known_by_default": True,
            "edges": [{"to": "hospital_foyer"}],
        },
        "hospital_foyer": {
            "known_by_default": False,
            "edges": [{"to": "sacred_clearing", "requires_known": True}],
        },
        "sacred_clearing": {
            "known_by_default": False,
            "edges": [],
        },
    },
}


MAP = LocationGraph(name="test_map", config=_LOCATION_CONFIG)


def _map_slot():
    return MAP.init_state(None)


class LocationGraphInitialStateTests(SimpleTestCase):
    """A fresh slot seeds every known_by_default location, and nothing
    else, plus the map's whole vocabulary."""

    def test_only_known_by_default_locations_start_known(self):
        slot = _map_slot()
        self.assertTrue(MAP.is_known(slot, "outside_hospital"))
        self.assertFalse(MAP.is_known(slot, "hospital_foyer"))
        self.assertFalse(MAP.is_known(slot, "sacred_clearing"))

    def test_the_vocabulary_is_in_the_slot_for_dependent_plugins(self):
        """Occupancy checks a write against `declared`, read from the
        session state, so the map must be there and not only on the
        instance."""
        slot = _map_slot()
        self.assertEqual(slot["declared"], sorted(_LOCATION_CONFIG["locations"]))
        self.assertTrue(MAP.declares(slot, "hospital_foyer"))
        self.assertFalse(MAP.declares(slot, "nowhere"))

    def test_a_map_less_plugin_declares_nothing(self):
        slot = LocationGraph().init_state(None)
        self.assertEqual(slot["declared"], [])


class DiscoveryTests(SimpleTestCase):
    """set_known() discovers and forgets; set_all_known() is the whole map."""

    def test_set_known_discovers_a_location(self):
        slot = _map_slot()
        MAP.set_known(slot, "hospital_foyer")
        self.assertTrue(MAP.is_known(slot, "hospital_foyer"))

    def test_forgetting_removes_a_known_location(self):
        slot = _map_slot()
        MAP.set_known(slot, "hospital_foyer")
        MAP.set_known(slot, "hospital_foyer", False)
        self.assertFalse(MAP.is_known(slot, "hospital_foyer"))

    def test_forgetting_can_revoke_a_known_by_default_location(self):
        """A known_by_default location is not privileged."""
        slot = _map_slot()
        MAP.set_known(slot, "outside_hospital", False)
        self.assertFalse(MAP.is_known(slot, "outside_hospital"))

    def test_forgetting_an_unknown_location_is_a_no_op(self):
        slot = _map_slot()
        MAP.set_known(slot, "sacred_clearing", False)
        self.assertFalse(MAP.is_known(slot, "sacred_clearing"))

    def test_set_all_known_true_marks_every_declared_location_known(self):
        slot = _map_slot()
        MAP.set_all_known(slot, True)
        for location_id in _LOCATION_CONFIG["locations"]:
            self.assertTrue(MAP.is_known(slot, location_id), location_id)

    def test_set_all_known_false_clears_every_location_including_known_by_default(self):
        """False is 'forget everything', not 'reset to a new game'."""
        slot = _map_slot()
        MAP.set_all_known(slot, False)
        self.assertEqual(slot["known"], [])
        self.assertTrue(MAP.is_known(_map_slot(), "outside_hospital"))

    def test_known_is_saved_sorted(self):
        slot = _map_slot()
        MAP.set_known(slot, "sacred_clearing")
        MAP.set_known(slot, "hospital_foyer")
        self.assertEqual(slot["known"], sorted(slot["known"]))


class ReachableEdgesTests(SimpleTestCase):
    """reachable_edges() applies the real requires_known gating."""

    def test_edge_with_no_requires_known_is_always_reachable(self):
        self.assertEqual(MAP.reachable_edges(_map_slot(), "outside_hospital"), ["hospital_foyer"])

    def test_requires_known_edge_is_hidden_until_the_destination_is_known(self):
        self.assertEqual(MAP.reachable_edges(_map_slot(), "hospital_foyer"), [])

    def test_requires_known_edge_appears_once_the_destination_is_known(self):
        slot = _map_slot()
        MAP.set_known(slot, "sacred_clearing")
        self.assertEqual(MAP.reachable_edges(slot, "hospital_foyer"), ["sacred_clearing"])

    def test_undeclared_location_has_no_edges(self):
        self.assertEqual(MAP.reachable_edges(_map_slot(), "nonexistent"), [])


class LocationGraphSerializationTests(SimpleTestCase):
    """The slot round-trips through plain JSON."""

    def test_round_trips_through_real_json(self):
        slot = _map_slot()
        MAP.set_known(slot, "hospital_foyer")
        restored = json.loads(json.dumps(slot))
        self.assertTrue(MAP.is_known(restored, "hospital_foyer"))
        self.assertTrue(MAP.is_known(restored, "outside_hospital"))
        self.assertFalse(MAP.is_known(restored, "sacred_clearing"))

    def test_a_bad_map_fails_at_construction(self):
        with self.assertRaises(SystemConfigValidationError):
            LocationGraph(name="broken", config={"locations": {"a": {"edges": [{"to": "nowhere"}]}}})


class PlaceAttributeTests(SimpleTestCase):
    """A place's own story-set facts, apart from what the config declared."""

    def test_read_write_exists(self):
        slot = _map_slot()
        self.assertFalse(MAP.read_attribute(slot, "hospital_foyer", "door_open"))
        self.assertFalse(MAP.attribute_exists(slot, "hospital_foyer", "door_open"))
        MAP.set_attribute(slot, "hospital_foyer", "door_open", False)
        self.assertTrue(MAP.attribute_exists(slot, "hospital_foyer", "door_open"))
        MAP.set_attribute(slot, "hospital_foyer", "door_open", True)
        self.assertTrue(MAP.read_attribute(slot, "hospital_foyer", "door_open"))

    def test_the_published_queries_are_the_readers(self):
        slot = _map_slot()
        MAP.set_attribute(slot, "hospital_foyer", "door_open", True)
        queries = MAP.plugin().queries
        self.assertEqual(sorted(queries), ["is_known", "read_attribute"])
        self.assertTrue(queries["read_attribute"](slot, "hospital_foyer", "door_open"))
        self.assertTrue(queries["is_known"](slot, "outside_hospital"))


class ResolveScheduleTests(SimpleTestCase):
    """resolve_schedule() against real _place_now() shapes, per
    a converted game's own globals file."""

    def test_zali_style_single_flag_fixed_place(self):
        """Real shape: `{ zali_met: ~ return 220 } ~ return 0` — one flag
        gates one fixed place, else absent."""
        rules = (
            ScheduleRule(condition=Condition.flag_is_set("zali_met"), location_id="zali_house"),
            ScheduleRule(condition=None, location_id=None),
        )
        self.assertIsNone(resolve_schedule(rules, flags=frozenset(), clock=0))
        self.assertEqual(resolve_schedule(rules, flags=frozenset({"zali_met"}), clock=0), "zali_house")

    def test_nina_style_shop_hours_split(self):
        """Real shape: `{ is_shop_open_now(): ~ return 371 } ~ return 462`
        — a time-of-day range gates the primary place, else a fixed
        fallback. Shop hours per source's own isShopOpen(): tick 96-216,
        i.e. 8:00am-6:00pm."""
        rules = (
            ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="tv_station_reception"),
            ScheduleRule(condition=None, location_id="ninas_apartment"),
        )
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=100), "tv_station_reception")
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=250), "ninas_apartment")

    def test_doctor_kay_style_multi_condition_priority_chain(self):
        """Real shape: school-hours-afternoon -> school; school-hours ->
        hospital; not-day AND (deal-made OR charmed) -> hotel; else
        absent. First matching rule wins, in declared order."""
        rules = (
            ScheduleRule(
                condition=Condition.all_of(Condition.minute_in_range(EIGHT_AM, SIX_PM), Condition.minute_in_range(NOON, MINUTES_PER_DAY)),
                location_id="school_nurse_office",
            ),
            ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="hospital_office"),
            ScheduleRule(
                condition=Condition.all_of(
                    Condition.negate(Condition.minute_in_range(SIX_AM, EIGHT_PM)),
                    Condition.any_of(Condition.flag_is_set("deal_made"), Condition.flag_is_set("charmed")),
                ),
                location_id="hotel_room",
            ),
            ScheduleRule(condition=None, location_id=None),
        )
        # Afternoon school hours (tick 150, in both ranges) -> school.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=150), "school_nurse_office")
        # Morning school hours (tick 100, only in the first range) -> hospital.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=100), "hospital_office")
        # Night, charmed -> hotel.
        self.assertEqual(resolve_schedule(rules, flags=frozenset({"charmed"}), clock=0), "hotel_room")
        # Night, not charmed/deal-made -> absent.
        self.assertIsNone(resolve_schedule(rules, flags=frozenset(), clock=0))

    def test_empty_schedule_with_no_fallback_resolves_to_none(self):
        """No rules at all resolves to None, matching source's own
        "not trackable" convention for a character with no real
        whereNow() override."""
        self.assertIsNone(resolve_schedule((), flags=frozenset(), clock=0))

    def test_resolve_schedule_reduces_absolute_clock_to_minute_of_day_itself(self):
        """The caller passes a raw absolute clock value (matching
        SchedulingState.clock) with zero coupling to that module —
        resolve_schedule() does the tick-to-minute reduction itself."""
        rules = (ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="daytime_spot"),)
        # Day 5 (5 * 288 = 1440), tick-of-day 100 -> same result as day 0.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=1440 + 100), "daytime_spot")


class ResolvePresentCharactersTests(SimpleTestCase):
    """resolve_present_characters() — the schedule-driven inverse of
    resolve_schedule(): given a place, who's there right now, across
    several characters at once. Synthetic character/place names
    throughout (per the location-dispatch design work's
    own generic-vs-bridge rule) — nothing here is game-specific."""

    def test_returns_every_character_currently_resolved_to_the_place(self):
        """Two characters both resolve to the same place; a third does
        not — only the first two are returned, in schedules' own order."""
        schedules = {
            "alice": (ScheduleRule(condition=None, location_id="the_square"),),
            "bob": (ScheduleRule(condition=None, location_id="the_square"),),
            "carol": (ScheduleRule(condition=None, location_id="elsewhere"),),
        }
        self.assertEqual(
            resolve_present_characters("the_square", schedules, flags=frozenset(), clock=0),
            ["alice", "bob"],
        )

    def test_nobody_present_returns_an_empty_list(self):
        """No character's schedule resolves to this place -> empty list,
        not None (unlike resolve_schedule() itself, this always returns a
        list since it's answering "who," not "where")."""
        schedules = {"alice": (ScheduleRule(condition=None, location_id="elsewhere"),)}
        self.assertEqual(resolve_present_characters("the_square", schedules, flags=frozenset(), clock=0), [])

    def test_empty_schedules_dict_returns_an_empty_list(self):
        """No characters at all -> empty list."""
        self.assertEqual(resolve_present_characters("the_square", {}, flags=frozenset(), clock=0), [])

    def test_respects_each_characters_own_flag_and_clock_gated_schedule(self):
        """Each character's own real Condition tree is evaluated
        independently against the SAME shared flags/clock — a
        time-of-day split for one character doesn't affect another's own
        unconditional rule."""
        schedules = {
            "alice": (
                ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="the_square"),
                ScheduleRule(condition=None, location_id="home"),
            ),
            "bob": (ScheduleRule(condition=Condition.flag_is_set("bob_out"), location_id="the_square"),),
        }
        # Daytime, bob_out not set: only alice is at the square.
        self.assertEqual(resolve_present_characters("the_square", schedules, flags=frozenset(), clock=100), ["alice"])
        # Night, bob_out set: only bob is at the square (alice is home).
        self.assertEqual(
            resolve_present_characters("the_square", schedules, flags=frozenset({"bob_out"}), clock=0),
            ["bob"],
        )

    def test_delegates_to_story_rules_and_story_values_per_character(self):
        """A character's own STORY_RULE/STORY_VALUE nodes resolve through
        the same shared registries every other resolve_schedule() caller
        uses — no separate registry concept for the multi-character case."""
        schedules = {
            "alice": (ScheduleRule(condition=Condition.story_rule("shop_is_open"), location_id="the_shop"),),
            "bob": (ScheduleRule(condition=Condition.story_value("hour", ">", 12), location_id="the_shop"),),
        }
        story_rules = {"shop_is_open": lambda clock: clock == 999}
        story_values = {"hour": lambda clock: 13 if clock == 999 else 0}
        self.assertEqual(
            resolve_present_characters("the_shop", schedules, flags=frozenset(), clock=999, story_rules=story_rules, story_values=story_values),
            ["alice", "bob"],
        )
        self.assertEqual(
            resolve_present_characters("the_shop", schedules, flags=frozenset(), clock=0, story_rules=story_rules, story_values=story_values),
            [],
        )


class EngineStateConditionTests(SimpleTestCase):
    """ENGINE_STATE lets a schedule read a fact from the plugin that owns
    it, instead of the story reading it out, passing its NAME in as a
    flag, and the schedule testing membership."""

    STATE: ClassVar[dict[str, Any]] = {"characters": {"attributes": {"alice": {"deal_made": True, "stage": 3}}, "known": ["alice"]}}

    def _resolve(self, condition, engine_state=None):
        """Resolve a one-rule schedule under `condition`."""
        return resolve_schedule(
            (ScheduleRule(condition=condition, location_id="the_shop"), ScheduleRule(condition=None, location_id="home")),
            flags=frozenset(),
            clock=0,
            engine_state=engine_state if engine_state is not None else self.STATE,
        )

    def test_a_true_attribute_selects_its_branch(self):
        """The base case: the schedule reads the characters plugin
        directly, with nothing threaded through the flag set."""
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "alice", "deal_made"))), "the_shop")

    def test_a_missing_path_is_false_rather_than_an_error(self):
        """Story content asks about facts that have not happened yet; a
        character with no attributes must answer no, not crash mid-turn."""
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "bob", "deal_made"))), "home")
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "alice", "never_set"))), "home")

    def test_an_absent_state_slot_is_false_rather_than_an_error(self):
        """A story that has not opted into the owning plugin at all."""
        self.assertEqual(self._resolve(Condition.engine_state("nonexistent", ("a", "b")), engine_state={}), "home")

    def test_a_non_mapping_partway_down_the_path_is_false(self):
        """Walking into a scalar must stop, not raise."""
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "alice", "deal_made", "deeper"))), "home")

    def test_it_compares_values_not_just_truthiness(self):
        """The same node handles "stage is at least 3", which is what
        replaces a story pre-computing that into a boolean flag."""
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "alice", "stage"), ">=", 3)), "the_shop")
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("attributes", "alice", "stage"), ">=", 4)), "home")

    def test_known_state_is_readable_through_the_same_kind(self):
        """No `CHARACTER_KNOWN` kind is needed: known-state is a list in
        the same slot, so one generic kind reaches it."""
        state = {"characters": {"attributes": {}, "known": ["alice"]}}
        self.assertEqual(self._resolve(Condition.engine_state("characters", ("known",), "contains", "alice"), state), "the_shop")

    def test_an_absent_value_compares_as_its_zero_not_as_nothing(self):
        """A fact that has not happened must equal its zero value.

        `charm_level == 0` means "uncharmed", and that has to hold for a
        character nobody ever charmed — whose attribute was never written.
        Treating an unresolved path as None instead made every such
        condition false, which silently inverted schedules that gate on a
        zero state. This test pins that behavior."""
        self.assertEqual(
            self._resolve(Condition.engine_state("characters", ("records", "nobody", "attributes", "charm_level"), "==", 0), {}), "the_shop"
        )

    def test_the_absent_value_is_configurable(self):
        """Where absence genuinely differs from a stored value, a caller
        can say what missing is worth."""
        condition = Condition.engine_state("characters", ("records", "nobody", "attributes", "stage"), "==", -1, missing=-1)
        self.assertEqual(self._resolve(condition, {}), "the_shop")

    def test_an_unsupported_operator_is_rejected_at_build_time(self):
        """A bad operator must fail where it is written, not silently
        mis-answer inside a player's turn."""
        with self.assertRaises(ValueError):
            Condition.engine_state("characters", ("attributes", "alice", "x"), "~=", 1)

    def test_it_composes_with_the_other_kinds(self):
        """ENGINE_STATE is an ordinary node: combinators must accept it."""
        condition = Condition.all_of(
            Condition.engine_state("characters", ("attributes", "alice", "deal_made")),
            Condition.negate(Condition.flag_is_set("blocked")),
        )
        self.assertEqual(self._resolve(condition), "the_shop")

    def test_a_schedule_with_no_engine_state_nodes_needs_no_state(self):
        """Backward compatibility: every existing schedule keeps working
        without passing anything."""
        rules = (ScheduleRule(condition=Condition.flag_is_set("open"), location_id="the_shop"),)
        self.assertEqual(resolve_schedule(rules, flags=frozenset({"open"}), clock=0), "the_shop")


class PresenceQueryTests(SimpleTestCase):
    """`is_at()`, `is_with()` and `is_anywhere()` — the three distinct
    presence questions, kept apart on purpose.

    A story that conflates "is X at this place" with "is X anywhere at
    all" reports characters as present across the whole map, so these
    tests pin the difference rather than just the happy path."""

    def setUp(self):
        self.slot = {"locations": {"alice": "the_square", "player": "the_square", "bob": "the_shop"}}

    def test_is_at_is_true_only_at_that_location(self):
        """The place-specific question."""
        self.assertTrue(CHARACTER_OCCUPANCY.is_at(self.slot, "alice", "the_square"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_at(self.slot, "alice", "the_shop"))

    def test_is_at_is_false_for_an_unplaced_character(self):
        """Nowhere is not "at" anywhere — including not at ""."""
        self.assertFalse(CHARACTER_OCCUPANCY.is_at(self.slot, "carol", "the_square"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_at(self.slot, "carol", ""))

    def test_is_anywhere_ignores_which_location(self):
        """The existence question: true wherever they are."""
        self.assertTrue(CHARACTER_OCCUPANCY.is_anywhere(self.slot, "bob"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_anywhere(self.slot, "carol"))

    def test_is_anywhere_is_not_a_substitute_for_is_at(self):
        """The distinction that matters: Bob is somewhere, but not where
        Alice is. Using `is_anywhere` for presence would call him here."""
        self.assertTrue(CHARACTER_OCCUPANCY.is_anywhere(self.slot, "bob"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_at(self.slot, "bob", "the_square"))

    def test_is_with_compares_two_characters_locations(self):
        """ "Is X here", where here means wherever the player is."""
        self.assertTrue(CHARACTER_OCCUPANCY.is_with(self.slot, "alice", "player"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_with(self.slot, "bob", "player"))

    def test_is_with_is_false_when_either_is_unplaced(self):
        """Two absent characters are not together; they are both nowhere."""
        self.assertFalse(CHARACTER_OCCUPANCY.is_with(self.slot, "carol", "player"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_with({"locations": {"alice": "the_square"}}, "alice", "player"))
        self.assertFalse(CHARACTER_OCCUPANCY.is_with({"locations": {}}, "carol", "dave"))

    def test_is_with_agrees_with_is_at_on_the_players_own_location(self):
        """The two spellings of the same question must not diverge."""
        for character_id in ("alice", "bob", "carol"):
            self.assertEqual(
                CHARACTER_OCCUPANCY.is_with(self.slot, character_id, "player"),
                CHARACTER_OCCUPANCY.is_at(self.slot, character_id, CHARACTER_OCCUPANCY.where_is(self.slot, "player")),
                character_id,
            )


class RecomputeOccupancyTests(SimpleTestCase):
    """recompute() is the scheduler's write-back: it resolves every
    scheduled character and pushes the answers into the store, so later
    where_is()/characters_at() reads see one consistent moment."""

    def test_every_scheduled_character_is_written_into_the_store(self):
        """The point of the write-back — after one recompute, a plain
        store read answers for a character who was never explicitly
        placed."""
        schedules = {
            "alice": (ScheduleRule(condition=None, location_id="the_square"),),
            "bob": (ScheduleRule(condition=None, location_id="the_shop"),),
        }
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=0)
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "alice"), "the_square")
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "bob"), "the_shop")
        self.assertEqual(CHARACTER_OCCUPANCY.characters_at(slot, "the_square"), ["alice"])

    def test_a_none_resolution_clears_the_previous_entry(self):
        """ "Nowhere" is an answer, not a reason to leave yesterday's
        location behind — the stale-entry bug this write-back exists to
        prevent."""
        schedules = {
            "alice": (
                ScheduleRule(condition=Condition.flag_is_set("alice_out"), location_id="the_square"),
                ScheduleRule(condition=None, location_id=None),
            )
        }
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset({"alice_out"}), clock=0)
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "alice"), "the_square")
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=0)
        self.assertIsNone(CHARACTER_OCCUPANCY.where_is(slot, "alice", default=None))

    def test_an_unchanged_location_stays_put(self):
        """Recomputing repeatedly is safe — a character whose schedule
        still resolves the same way keeps the same entry, so a story may
        recompute as often as it likes."""
        schedules = {"alice": (ScheduleRule(condition=None, location_id="the_square"),)}
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=0)
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=1)
        self.assertEqual(slot["locations"], {"alice": "the_square"})

    def test_characters_outside_the_schedules_are_left_untouched(self):
        """Explicitly-placed characters — the player above all — are not
        in any schedule table and must survive a recompute."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "player", "the_square")
        schedules = {"alice": (ScheduleRule(condition=None, location_id="the_shop"),)}
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=0)
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "player"), "the_square")

    def test_flags_clock_and_registries_reach_every_character(self):
        """The resolution inputs are shared across the whole pass, exactly
        as resolve_present_characters() shares them."""
        schedules = {
            "alice": (
                ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="the_square"),
                ScheduleRule(condition=None, location_id="home"),
            ),
            "bob": (
                ScheduleRule(condition=Condition.story_rule("shop_is_open"), location_id="the_shop"),
                ScheduleRule(condition=None, location_id="home"),
            ),
        }
        story_rules = {"shop_is_open": lambda clock: True}
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=NOON // 5, story_rules=story_rules)
        self.assertEqual(slot["locations"], {"alice": "the_square", "bob": "the_shop"})


class OccupancyStoreTests(SimpleTestCase):
    """set_location()/where_is()/characters_at() over the session's own slot."""

    def test_place_then_where_is(self):
        """A character's explicitly-set location is readable back."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "davy", "robbins_house")
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "davy"), "robbins_house")

    def test_clearing_a_location_with_none_removes_it(self):
        """Passing location_id=None removes the character's entry entirely."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "davy", "robbins_house")
        CHARACTER_OCCUPANCY.place(slot, "davy", None)
        self.assertNotIn("davy", slot["locations"])
        self.assertIsNone(CHARACTER_OCCUPANCY.where_is(slot, "davy", default=None))

    def test_unset_character_answers_the_default(self):
        """A character never placed anywhere answers the caller's own
        "nowhere": "" for Ink, None for a Python caller that asks."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "nobody"), "")
        self.assertIsNone(CHARACTER_OCCUPANCY.where_is(slot, "nobody", default=None))

    def test_characters_at_returns_every_character_at_a_location(self):
        """characters_at() lists every character explicitly placed at a
        given location, excluding characters placed elsewhere."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "davy", "robbins_house")
        CHARACTER_OCCUPANCY.place(slot, "mrs_robbins", "robbins_house")
        CHARACTER_OCCUPANCY.place(slot, "tina", "elsewhere")
        self.assertEqual(CHARACTER_OCCUPANCY.characters_at(slot, "robbins_house"), ["davy", "mrs_robbins"])

    def test_an_undeclared_location_is_refused_when_the_story_declares_a_map(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        with self.assertRaises(UnknownLocationError):
            CHARACTER_OCCUPANCY.place(slot, "davy", "robins_house", frozenset({"robbins_house"}))
        CHARACTER_OCCUPANCY.place(slot, "davy", "anywhere", None)

    def test_the_slot_round_trips_through_real_json(self):
        """A real json.dumps/json.loads round-trip preserves every
        explicitly-set character location."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "davy", "robbins_house")
        restored = json.loads(json.dumps(slot))
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(restored, "davy"), "robbins_house")


class OccupancyBindingTests(SimpleTestCase):
    """The Ink surface: the same methods over the session's live slot."""

    def test_the_bindings_are_published_under_the_method_names(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        self.assertEqual(sorted(bindings), ["is_anywhere", "is_at", "is_with", "set_location", "where_is", "who_is_at"])

    def test_set_location_clears_with_an_empty_string(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        bindings["set_location"]("davy", "robbins_house")
        self.assertEqual(bindings["where_is"]("davy"), "robbins_house")
        bindings["set_location"]("davy", "")
        self.assertEqual(bindings["where_is"]("davy"), "")

    def test_set_location_checks_the_maps_vocabulary(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        engine_state = {"character_occupancy": slot, location_graph_module.STATE_KEY: {"declared": ["cellar"]}}
        bindings = CHARACTER_OCCUPANCY.bind(slot, engine_state, {})
        with self.assertRaises(UnknownLocationError):
            bindings["set_location"]("davy", "celler")

    def test_who_is_at_joins_for_ink(self):
        slot = {"locations": {"davy": "house", "mrs_robbins": "house", "odd,name": "house"}}
        self.assertEqual(CHARACTER_OCCUPANCY.bind(slot, {}, {})["who_is_at"]("house"), "davy,mrs_robbins")


class LayeredIndependenceTests(SimpleTestCase):
    """location_graph and character_occupancy must be usable completely
    independently."""

    def test_character_occupancy_never_imports_location_graph(self):
        """A structural proof, not just a docstring claim: the occupancy
        module's own namespace holds no reference to the location_graph
        module."""
        self.assertNotIn(location_graph_module, character_occupancy_module.__dict__.values())

    def test_occupancy_accepts_plain_strings_never_a_location_graph_type(self):
        """A story tracking locations with its own scheme (not
        location_graph.py's config shape at all) can still use occupancy
        tracking — location ids are plain strings here."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "some_npc", "a-location-id-from-any-scheme-at-all")
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "some_npc"), "a-location-id-from-any-scheme-at-all")


class LocationDetailsTests(SimpleTestCase):
    """Declared details reach the session, and survive a round-trip."""

    CONFIG: ClassVar[dict[str, Any]] = {
        "locations": {
            "cellar": {"known_by_default": True, "details": {"name": "The Cellar", "terrain": "indoor", "external_identifier": [12]}},
            "moor": {"details": {"terrain": "hills", "story_scene": "storm"}},
            "void": {},
        }
    }
    DETAILED = LocationGraph(name="detailed_map", config=CONFIG)

    def test_details_are_carried_into_the_session_state(self):
        """A dependent system reads one place for everything about a
        location, rather than a structure per consumer."""
        slot = self.DETAILED.init_state(None)
        self.assertEqual(self.DETAILED.detail(slot, "cellar", "name"), "The Cellar")
        self.assertEqual(self.DETAILED.detail(slot, "cellar", "external_identifier"), [12])
        self.assertEqual(self.DETAILED.detail(slot, "moor", "story_scene"), "storm", "a story's own key is kept as declared")
        self.assertIsNone(self.DETAILED.detail(slot, "void", "terrain"), "a location declaring nothing has no details")

    def test_movement_cost_comes_from_terrain(self):
        slot = self.DETAILED.init_state(None)
        self.assertEqual(self.DETAILED.movement_cost(slot, "cellar"), 1)
        self.assertEqual(self.DETAILED.movement_cost(slot, "moor"), 4)
        self.assertEqual(self.DETAILED.movement_cost(slot, "void"), 1, "no terrain declared falls back to the default")

    def test_details_survive_a_serialization_round_trip(self):
        slot = json.loads(json.dumps(self.DETAILED.init_state(None)))
        self.assertEqual(self.DETAILED.detail(slot, "cellar", "name"), "The Cellar")
        self.assertEqual(self.DETAILED.movement_cost(slot, "moor"), 4)

    def test_discovery_changes_keep_the_details(self):
        slot = self.DETAILED.init_state(None)
        self.DETAILED.set_known(slot, "moor")
        self.DETAILED.set_known(slot, "cellar", False)
        self.assertEqual(self.DETAILED.detail(slot, "cellar", "name"), "The Cellar")
        self.assertEqual(slot["declared"], ["cellar", "moor", "void"])


class LocationVisitTests(SimpleTestCase):
    """Visits are counted; "has been here" is derived from the count."""

    SIMPLE = LocationGraph(name="simple_map", config={"locations": {"cellar": {"known_by_default": True}}})

    def test_a_new_game_has_visited_nothing(self):
        slot = self.SIMPLE.init_state(None)
        self.assertEqual(self.SIMPLE.visit_count(slot, "cellar"), 0)
        self.assertFalse(self.SIMPLE.has_visited(slot, "cellar"))

    def test_visits_accumulate_and_the_boolean_follows(self):
        slot = self.SIMPLE.init_state(None)
        self.SIMPLE.record_visit(slot, "cellar")
        self.assertEqual(self.SIMPLE.record_visit(slot, "cellar"), 2)
        self.assertEqual(self.SIMPLE.visit_count(slot, "cellar"), 2)
        self.assertTrue(self.SIMPLE.has_visited(slot, "cellar"))

    def test_a_story_may_declare_starting_visits(self):
        """A story resuming mid-narrative can say a place is already
        known to the character."""
        resumed = LocationGraph(name="resumed_map", config={"locations": {"cellar": {"details": {"visits": 3}}}})
        slot = resumed.init_state(None)
        self.assertEqual(resumed.visit_count(slot, "cellar"), 3)
        self.assertTrue(resumed.has_visited(slot, "cellar"))

    def test_visits_survive_a_round_trip(self):
        slot = self.SIMPLE.init_state(None)
        self.SIMPLE.record_visit(slot, "cellar")
        self.assertEqual(self.SIMPLE.visit_count(json.loads(json.dumps(slot)), "cellar"), 1)
