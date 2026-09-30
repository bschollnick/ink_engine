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
            "exits": [{"to": "hospital_foyer"}],
        },
        "hospital_foyer": {
            "known_by_default": False,
            "exits": [{"to": "stone_circle", "requires_known": True}],
        },
        "stone_circle": {
            "known_by_default": False,
            "exits": [],
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
        self.assertFalse(MAP.is_known(slot, "stone_circle"))

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
        MAP.set_known(slot, "stone_circle", False)
        self.assertFalse(MAP.is_known(slot, "stone_circle"))

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
        MAP.set_known(slot, "stone_circle")
        MAP.set_known(slot, "hospital_foyer")
        self.assertEqual(slot["known"], sorted(slot["known"]))


class ReachableExitsTests(SimpleTestCase):
    """reachable_exits() applies the real requires_known gating."""

    def test_exit_with_no_requires_known_is_always_reachable(self):
        self.assertEqual(MAP.reachable_exits(_map_slot(), "outside_hospital"), ["hospital_foyer"])

    def test_requires_known_exit_is_hidden_until_the_destination_is_known(self):
        self.assertEqual(MAP.reachable_exits(_map_slot(), "hospital_foyer"), [])

    def test_requires_known_exit_appears_once_the_destination_is_known(self):
        slot = _map_slot()
        MAP.set_known(slot, "stone_circle")
        self.assertEqual(MAP.reachable_exits(slot, "hospital_foyer"), ["stone_circle"])

    def test_undeclared_location_has_no_exits(self):
        self.assertEqual(MAP.reachable_exits(_map_slot(), "nonexistent"), [])


class LocationGraphSerializationTests(SimpleTestCase):
    """The slot round-trips through plain JSON."""

    def test_round_trips_through_real_json(self):
        slot = _map_slot()
        MAP.set_known(slot, "hospital_foyer")
        restored = json.loads(json.dumps(slot))
        self.assertTrue(MAP.is_known(restored, "hospital_foyer"))
        self.assertTrue(MAP.is_known(restored, "outside_hospital"))
        self.assertFalse(MAP.is_known(restored, "stone_circle"))

    def test_a_bad_map_fails_at_construction(self):
        with self.assertRaises(SystemConfigValidationError):
            LocationGraph(name="broken", config={"locations": {"a": {"exits": [{"to": "nowhere"}]}}})


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
            ScheduleRule(condition=Condition.flag_is_set("zali_met"), location_id="cottage"),
            ScheduleRule(condition=None, location_id=None),
        )
        self.assertIsNone(resolve_schedule(rules, flags=frozenset(), clock=0))
        self.assertEqual(resolve_schedule(rules, flags=frozenset({"zali_met"}), clock=0), "cottage")

    def test_nina_style_shop_hours_split(self):
        """Real shape: `{ is_shop_open_now(): ~ return 371 } ~ return 462`
        — a time-of-day range gates the primary place, else a fixed
        fallback. Shop hours 8:00am-6:00pm."""
        rules = (
            ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="radio_lobby"),
            ScheduleRule(condition=None, location_id="flat_three"),
        )
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=EIGHT_AM + 20), "radio_lobby")
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=EIGHT_PM + 50), "flat_three")

    def test_doctor_kay_style_multi_condition_priority_chain(self):
        """Real shape: school-hours-afternoon -> school; school-hours ->
        hospital; not-day AND (deal-made OR charmed) -> hotel; else
        absent. First matching rule wins, in declared order."""
        rules = (
            ScheduleRule(
                condition=Condition.all_of(Condition.minute_in_range(EIGHT_AM, SIX_PM), Condition.minute_in_range(NOON, MINUTES_PER_DAY)),
                location_id="infirmary",
            ),
            ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="clinic_office"),
            ScheduleRule(
                condition=Condition.all_of(
                    Condition.negate(Condition.minute_in_range(SIX_AM, EIGHT_PM)),
                    Condition.any_of(Condition.flag_is_set("deal_made"), Condition.flag_is_set("charmed")),
                ),
                location_id="inn_room",
            ),
            ScheduleRule(condition=None, location_id=None),
        )
        # Afternoon school hours (12:30, in both ranges) -> school.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=NOON + 30), "infirmary")
        # Morning school hours (08:20, only in the first range) -> hospital.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=EIGHT_AM + 20), "clinic_office")
        # Night, charmed -> hotel.
        self.assertEqual(resolve_schedule(rules, flags=frozenset({"charmed"}), clock=0), "inn_room")
        # Night, not charmed/deal-made -> absent.
        self.assertIsNone(resolve_schedule(rules, flags=frozenset(), clock=0))

    def test_empty_schedule_with_no_fallback_resolves_to_none(self):
        """No rules at all resolves to None, matching source's own
        "not trackable" convention for a character with no real
        whereNow() override."""
        self.assertIsNone(resolve_schedule((), flags=frozenset(), clock=0))

    def test_resolve_schedule_reduces_absolute_clock_to_minute_of_day_itself(self):
        """The caller passes the absolute clock in minutes, as the
        scheduling plugin keeps it; resolve_schedule() reduces it to the
        minute of the day itself."""
        rules = (ScheduleRule(condition=Condition.minute_in_range(EIGHT_AM, SIX_PM), location_id="daytime_spot"),)
        # 08:20 on day 5 -> same result as 08:20 on day 0.
        self.assertEqual(resolve_schedule(rules, flags=frozenset(), clock=5 * MINUTES_PER_DAY + EIGHT_AM + 20), "daytime_spot")
        self.assertIsNone(resolve_schedule(rules, flags=frozenset(), clock=5 * MINUTES_PER_DAY + SIX_PM))


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
        self.assertEqual(resolve_present_characters("the_square", schedules, flags=frozenset(), clock=EIGHT_AM + 20), ["alice"])
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


class ClockReachedConditionTests(SimpleTestCase):
    """CLOCK_REACHED compares the clock with a minute a scene stored."""

    STATE: ClassVar[dict[str, Any]] = {"characters": {"attributes": {"alice": {"arrives_at": 600, "arrived": True}}}}

    def _resolve(self, clock, path=("attributes", "alice", "arrives_at")):
        """Resolve a one-rule schedule gated on the stored minute at `clock`."""
        return resolve_schedule(
            (
                ScheduleRule(condition=Condition.clock_reached("characters", path), location_id="the_shop"),
                ScheduleRule(condition=None, location_id="home"),
            ),
            flags=frozenset(),
            clock=clock,
            engine_state=self.STATE,
        )

    def test_before_the_stored_minute_it_is_false(self):
        """One minute early is not yet."""
        self.assertEqual(self._resolve(599), "home")

    def test_at_and_after_the_stored_minute_it_is_true(self):
        """The stored minute itself counts, and so does any later one."""
        self.assertEqual(self._resolve(600), "the_shop")
        self.assertEqual(self._resolve(10_000), "the_shop")

    def test_nothing_stored_is_never_reached(self):
        """A time no scene has recorded yet leaves the rule false forever."""
        self.assertEqual(self._resolve(10_000, path=("attributes", "bob", "arrives_at")), "home")

    def test_a_boolean_is_not_a_time(self):
        """True is not minute 1; a flag stored at the path does not count."""
        self.assertEqual(self._resolve(10_000, path=("attributes", "alice", "arrived")), "home")


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
        CHARACTER_OCCUPANCY.recompute(slot, schedules, flags=frozenset(), clock=NOON, story_rules=story_rules)
        self.assertEqual(slot["locations"], {"alice": "the_square", "bob": "the_shop"})


class OccupancyStoreTests(SimpleTestCase):
    """set_location()/where_is()/characters_at() over the session's own slot."""

    def test_place_then_where_is(self):
        """A character's explicitly-set location is readable back."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "miller", "mill_house")
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(slot, "miller"), "mill_house")

    def test_clearing_a_location_with_none_removes_it(self):
        """Passing location_id=None removes the character's entry entirely."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "miller", "mill_house")
        CHARACTER_OCCUPANCY.place(slot, "miller", None)
        self.assertNotIn("miller", slot["locations"])
        self.assertIsNone(CHARACTER_OCCUPANCY.where_is(slot, "miller", default=None))

    def test_a_placement_records_the_location_held_before_it(self):
        """A move records the location left; placing again at the same place records that place."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "courier", "foyer")
        self.assertEqual(CHARACTER_OCCUPANCY.previous_location(slot, "courier"), "")
        CHARACTER_OCCUPANCY.place(slot, "courier", "street")
        self.assertEqual(CHARACTER_OCCUPANCY.previous_location(slot, "courier"), "foyer")
        CHARACTER_OCCUPANCY.place(slot, "courier", "street")
        self.assertEqual(CHARACTER_OCCUPANCY.previous_location(slot, "courier"), "street")

    def test_a_removal_leaves_the_record_alone(self):
        """Removing a character keeps the last record; placing them again records nothing new to leave from."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "courier", "foyer")
        CHARACTER_OCCUPANCY.place(slot, "courier", "street")
        CHARACTER_OCCUPANCY.place(slot, "courier", None)
        CHARACTER_OCCUPANCY.place(slot, "courier", "bakery")
        self.assertEqual(CHARACTER_OCCUPANCY.previous_location(slot, "courier"), "foyer")

    def test_a_slot_saved_before_previous_locations_existed_still_answers(self):
        """A loaded slot with no `previous_locations` answers the default, and records the next move."""
        slot = {"locations": {"courier": "foyer"}}
        self.assertIsNone(CHARACTER_OCCUPANCY.previous_location(slot, "courier", default=None))
        CHARACTER_OCCUPANCY.place(slot, "courier", "street")
        self.assertEqual(CHARACTER_OCCUPANCY.previous_location(slot, "courier"), "foyer")

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
        CHARACTER_OCCUPANCY.place(slot, "miller", "mill_house")
        CHARACTER_OCCUPANCY.place(slot, "baker", "mill_house")
        CHARACTER_OCCUPANCY.place(slot, "weaver", "elsewhere")
        self.assertEqual(CHARACTER_OCCUPANCY.characters_at(slot, "mill_house"), ["miller", "baker"])

    def test_an_undeclared_location_is_refused_when_the_story_declares_a_map(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        with self.assertRaises(UnknownLocationError):
            CHARACTER_OCCUPANCY.place(slot, "miller", "robins_house", frozenset({"mill_house"}))
        CHARACTER_OCCUPANCY.place(slot, "miller", "anywhere", None)

    def test_the_slot_round_trips_through_real_json(self):
        """A real json.dumps/json.loads round-trip preserves every
        explicitly-set character location."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        CHARACTER_OCCUPANCY.place(slot, "miller", "mill_house")
        restored = json.loads(json.dumps(slot))
        self.assertEqual(CHARACTER_OCCUPANCY.where_is(restored, "miller"), "mill_house")


class OccupancyBindingTests(SimpleTestCase):
    """The Ink surface: the same methods over the session's live slot."""

    def test_the_bindings_are_published_under_the_method_names(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        self.assertEqual(
            sorted(bindings), ["assigned_location", "is_anywhere", "is_at", "is_with", "previous_location", "set_location", "where_is", "who_is_at"]
        )

    def test_set_location_clears_with_an_empty_string(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        bindings["set_location"]("miller", "mill_house")
        self.assertEqual(bindings["where_is"]("miller"), "mill_house")
        bindings["set_location"]("miller", "")
        self.assertEqual(bindings["where_is"]("miller"), "")

    def test_set_location_checks_the_maps_vocabulary(self):
        slot = CHARACTER_OCCUPANCY.init_state(None)
        engine_state = {"character_occupancy": slot, location_graph_module.STATE_KEY: {"declared": ["cellar"]}}
        bindings = CHARACTER_OCCUPANCY.bind(slot, engine_state, {})
        with self.assertRaises(UnknownLocationError):
            bindings["set_location"]("miller", "celler")

    def test_who_is_at_joins_for_ink(self):
        slot = {"locations": {"miller": "house", "baker": "house", "odd,name": "house"}}
        self.assertEqual(CHARACTER_OCCUPANCY.bind(slot, {}, {})["who_is_at"]("house"), "miller,baker")


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


GATED_MAP = {
    "locations": {
        "hall": {
            "known_by_default": True,
            "details": {"name": "Hall"},
            "exits": [
                {"to": "yard", "position": "s", "label": "the yard"},
                {"to": "crypt", "position": "n", "label": "the crypt door", "unlocked_by": "crypt_door_open", "show_when_blocked": True},
                {"to": "vault", "position": "e", "label": "the vault", "sealed": True},
                {"to": "attic", "position": "up", "label": "the attic", "requires_known": True},
            ],
        },
        "yard": {"known_by_default": True, "details": {"name": "Yard"}},
        "crypt": {"known_by_default": True, "details": {"name": "Crypt"}},
        "vault": {"known_by_default": True, "details": {"name": "Vault"}},
        "attic": {"known_by_default": False, "details": {"name": "Attic"}},
    }
}
GATED = LocationGraph(name="gated", config=GATED_MAP)


def _gated_slot():
    return GATED.init_state(GATED_MAP)


class ExitsFromTests(SimpleTestCase):
    """exits_from() applies every gate and renders what a panel needs."""

    def test_an_ungated_exit_is_listed_and_passable(self):
        exits = {exit_["to"]: exit_ for exit_ in GATED.exits_from(_gated_slot(), "hall")}
        self.assertTrue(exits["yard"]["passable"])
        self.assertEqual(exits["yard"]["label"], "the yard")
        self.assertEqual(exits["yard"]["position"], "s")

    def test_a_sealed_exit_is_never_listed(self):
        destinations = [exit_["to"] for exit_ in GATED.exits_from(_gated_slot(), "hall")]
        self.assertNotIn("vault", destinations)

    def test_a_requires_known_exit_is_hidden_until_the_destination_is_known(self):
        slot = _gated_slot()
        self.assertNotIn("attic", [exit_["to"] for exit_ in GATED.exits_from(slot, "hall")])
        GATED.set_known(slot, "attic", True)
        self.assertIn("attic", [exit_["to"] for exit_ in GATED.exits_from(slot, "hall")])

    def test_an_unlocked_by_exit_shows_blocked_then_passable(self):
        slot = _gated_slot()
        blocked = [exit_ for exit_ in GATED.exits_from(slot, "hall") if exit_["to"] == "crypt"]
        self.assertEqual(len(blocked), 1)
        self.assertFalse(blocked[0]["passable"])
        GATED.set_attribute(slot, "crypt", "crypt_door_open", True)
        opened = [exit_ for exit_ in GATED.exits_from(slot, "hall") if exit_["to"] == "crypt"]
        self.assertTrue(opened[0]["passable"])

    def test_an_opened_gate_survives_a_save_and_reload(self):
        slot = _gated_slot()
        GATED.set_attribute(slot, "crypt", "crypt_door_open", True)
        reloaded = json.loads(json.dumps(slot))
        opened = [exit_ for exit_ in GATED.exits_from(reloaded, "hall") if exit_["to"] == "crypt"]
        self.assertTrue(opened[0]["passable"])

    def test_two_exits_gate_independently_on_different_attributes(self):
        config = {
            "locations": {
                "outside": {
                    "known_by_default": True,
                    "exits": [
                        {"to": "crypt", "position": "n", "unlocked_by": "front_open"},
                        {"to": "crypt", "position": "s", "unlocked_by": "back_open"},
                    ],
                },
                "crypt": {"known_by_default": True},
            }
        }
        graph = LocationGraph(name="two_doors", config=config)
        slot = graph.init_state(config)
        graph.set_attribute(slot, "crypt", "front_open", True)
        positions = [exit_["position"] for exit_ in graph.exits_from(slot, "outside")]
        self.assertEqual(positions, ["n"])

    def test_a_label_falls_back_to_the_destination_name_then_its_id(self):
        config = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "named"}, {"to": "bare"}]},
                "named": {"known_by_default": True, "details": {"name": "The Inn"}},
                "bare": {"known_by_default": True},
            }
        }
        graph = LocationGraph(name="labels", config=config)
        labels = {exit_["to"]: exit_["label"] for exit_ in graph.exits_from(graph.init_state(config), "a")}
        self.assertEqual(labels["named"], "The Inn")
        self.assertEqual(labels["bare"], "bare")

    def test_an_undeclared_location_has_no_exits(self):
        self.assertEqual(GATED.exits_from(_gated_slot(), "nonexistent"), [])

    def test_exits_from_agrees_with_reachable_exits_on_ungated_exits(self):
        slot = _map_slot()
        passable = [exit_["to"] for exit_ in MAP.exits_from(slot, "outside_hospital") if exit_["passable"]]
        self.assertEqual(passable, MAP.reachable_exits(slot, "outside_hospital"))


_STAGE_MAP = {
    "locations": {
        "gate": {"known_by_default": True, "exits": [{"to": "yard"}, {"to": "duel", "label": "draw your sword"}]},
        "yard": {"known_by_default": True, "exits": [{"to": "gate"}]},
        "duel": {"known_by_default": True, "details": {"event": True}, "exits": [{"to": "yard"}]},
    }
}
STAGE = LocationGraph(name="stage", config=_STAGE_MAP)


class EventTests(SimpleTestCase):
    """A location declaring `details.event` is a scene, not a place."""

    def test_no_exit_leads_into_an_event(self):
        """Neither exit list offers the event; the scene that starts it offers a story choice."""
        slot = STAGE.plugin().init_state(None)
        self.assertEqual([exit_["to"] for exit_ in STAGE.exits_from(slot, "gate")], ["yard"])
        self.assertEqual(STAGE.reachable_exits(slot, "gate"), ["yard"])

    def test_an_event_keeps_its_own_exits(self):
        """Leaving an event is ordinary movement."""
        slot = STAGE.plugin().init_state(None)
        self.assertEqual(STAGE.reachable_exits(slot, "duel"), ["yard"])

    def test_without_events_drops_the_event_and_every_exit_into_it(self):
        """A map drawing holds only the places."""
        drawn = location_graph_module.without_events(_STAGE_MAP)
        self.assertEqual(sorted(drawn["locations"]), ["gate", "yard"])
        self.assertEqual(drawn["locations"]["gate"]["exits"], [{"to": "yard"}])
        self.assertIn("duel", _STAGE_MAP["locations"])

    def test_event_must_be_a_boolean(self):
        """`event` is validated like `lit`."""
        with self.assertRaises(SystemConfigValidationError):
            location_graph_module.validate_location_graph({"locations": {"duel": {"details": {"event": "yes"}}}})


class AssignedLocationTests(SimpleTestCase):
    """`set_location` records where the story put a character; `place()` alone does not."""

    def test_a_schedule_move_keeps_the_assignment(self):
        """A scene assigns the classroom; a schedule sends the teacher home; the assignment stays."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        bindings["set_location"]("teacher", "classroom")
        CHARACTER_OCCUPANCY.place(slot, "teacher", "home")
        self.assertEqual(bindings["where_is"]("teacher"), "home")
        self.assertEqual(bindings["assigned_location"]("teacher"), "classroom")

    def test_removing_a_character_is_recorded(self):
        """`set_location(x, "")` records an empty assignment, distinct from never being placed."""
        slot = CHARACTER_OCCUPANCY.init_state(None)
        bindings = CHARACTER_OCCUPANCY.bind(slot, {}, {})
        self.assertIsNone(CHARACTER_OCCUPANCY.assigned_location(slot, "teacher", default=None))
        bindings["set_location"]("teacher", "classroom")
        bindings["set_location"]("teacher", "")
        self.assertEqual(CHARACTER_OCCUPANCY.assigned_location(slot, "teacher", default=None), "")
