"""SchedulingSystem (ink_engine.engine_plugins.scheduling).

No application framework needed. SimpleTestCase throughout.
"""

from __future__ import annotations

import json
from unittest import TestCase as SimpleTestCase

from ink_engine.engine_plugins.scheduling import (
    ONE_DAY,
    ONE_HOUR,
    PLUGIN,
    SCHEDULING,
    DayPhaseBoundaries,
    Effect,
    EffectKind,
    clock_of,
    day_of_week,
    hour_of_day,
    is_afternoon,
    is_day,
    is_evening,
    is_morning,
    is_night,
    is_weekday,
    minute_of_day,
)


def _slot(clock: int = 0):
    slot = SCHEDULING.init_state(None)
    slot["clock"] = clock
    return slot


class ScheduleEffectTests(SimpleTestCase):
    """schedule_effect() queues a timed event in the slot."""

    def test_queues_effect_at_the_right_due_time(self):
        """due_time is the current clock plus minutes_from_now, not an
        absolute time the caller must compute itself."""
        slot = _slot(100)
        effect = Effect(kind=EffectKind.SET_PERSON_FLAG, target="brenda", payload={"flag": "brenda_flag1", "value": True})
        SCHEDULING.schedule_effect(slot, effect, minutes_from_now=288)
        self.assertEqual(SCHEDULING.pending_effects(slot), [(388, effect)])

    def test_the_enum_never_enters_the_slot(self):
        """The slot holds the kind's string value; the Enum is rebuilt at
        the one reader that needs it."""
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.MOVE_CHARACTER, "davy", {"place_id": "robbins_house"}), 10)
        self.assertEqual(slot["pending"][0]["effect"]["kind"], "move_character")
        json.dumps(slot)


class AdvanceTests(SimpleTestCase):
    """advance() fires exactly the effects that are due, and only reports
    them -- it never applies anything to any character/flag/place state
    itself; applying a fired effect is the caller's own job."""

    def test_advancing_past_the_due_time_fires_the_effect(self):
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.MOVE_CHARACTER, "davy", {"place_id": "robbins_house"}), 10)
        fired = SCHEDULING.advance(slot, minutes=10)
        self.assertEqual(SCHEDULING.clock(slot), 10)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].target, "davy")
        self.assertEqual(slot["pending"], [])

    def test_advancing_short_of_the_due_time_fires_nothing(self):
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.SET_PLACE_FLAG, "hidden_room", {"flag": "known", "value": True}), 100)
        fired = SCHEDULING.advance(slot, minutes=50)
        self.assertEqual(SCHEDULING.clock(slot), 50)
        self.assertEqual(fired, [])
        self.assertEqual(len(slot["pending"]), 1)

    def test_multiple_due_effects_fire_in_scheduled_order(self):
        """Mirrors source's own vTimedEvent array semantics -- events are
        checked/fired in the order they were queued."""
        slot = _slot()
        first = Effect(EffectKind.SET_PERSON_FLAG, "a", {"flag": "x", "value": True})
        second = Effect(EffectKind.SET_PERSON_FLAG, "b", {"flag": "y", "value": True})
        SCHEDULING.schedule_effect(slot, first, 5)
        SCHEDULING.schedule_effect(slot, second, 5)
        self.assertEqual(SCHEDULING.advance(slot, minutes=5), [first, second])

    def test_advance_never_applies_an_effect_only_reports_it(self):
        """The ONLY thing advance() ever produces is the list it returns;
        nothing about "brenda" exists anywhere except inside that value."""
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.SET_PERSON_FLAG, "brenda", {"flag": "brenda_flag1", "value": True}), 10)
        fired = SCHEDULING.advance(slot, minutes=10)
        self.assertIsInstance(fired[0], Effect)
        self.assertEqual(fired[0].payload, {"flag": "brenda_flag1", "value": True})
        self.assertEqual(slot["pending"], [])

    def test_an_effect_not_yet_due_survives_multiple_advances(self):
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.MOVE_CHARACTER, "kate", {"place_id": "hotel_bar"}), 20)
        self.assertEqual(SCHEDULING.advance(slot, minutes=5), [])
        self.assertEqual(SCHEDULING.advance(slot, minutes=5), [])
        self.assertEqual(SCHEDULING.clock(slot), 10)
        self.assertEqual(len(slot["pending"]), 1)
        self.assertEqual(len(SCHEDULING.advance(slot, minutes=10)), 1)
        self.assertEqual(SCHEDULING.clock(slot), 20)

    def test_a_corrupt_kind_raises_when_it_fires_not_when_it_loads(self):
        """The trade-off of keeping the Enum out of the slot, pinned."""
        slot = _slot()
        slot["pending"].append({"due_time": 1, "effect": {"kind": "no_such_kind", "target": "x", "payload": {}}})
        PLUGIN.bind(slot, {}, {})  # loads fine
        with self.assertRaises(ValueError):
            SCHEDULING.advance(slot, minutes=5)


class SerializationTests(SimpleTestCase):
    """The slot round-trips cleanly through plain JSON."""

    def test_round_trips_pending_effects(self):
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.SET_PLACE_FLAG, "sacred_clearing", {"flag": "tunnel_known", "value": True}), 30)
        restored = json.loads(json.dumps(slot))
        self.assertEqual(SCHEDULING.clock(restored), 0)
        ((due_time, effect),) = SCHEDULING.pending_effects(restored)
        self.assertEqual(due_time, 30)
        self.assertEqual(effect.kind, EffectKind.SET_PLACE_FLAG)
        self.assertEqual(effect.target, "sacred_clearing")

    def test_clock_of_reads_the_slot_from_the_whole_session(self):
        self.assertEqual(clock_of({"scheduling": {"clock": 42}}), 42)
        self.assertEqual(clock_of({}), 0)


class JumpClockTests(SimpleTestCase):
    """jump_clock() -- a hard clock jump/rewind for a cheat menu or debug
    tool, using minutes (ONE_HOUR=60, ONE_DAY=1440)."""

    def test_forward_jump_adds_the_delta(self):
        slot = _slot(100)
        self.assertEqual(SCHEDULING.jump_clock(slot, ONE_HOUR), 160)

    def test_backward_jump_subtracts_via_a_negative_delta(self):
        slot = _slot(100)
        self.assertEqual(SCHEDULING.jump_clock(slot, -ONE_HOUR), 40)

    def test_one_day_is_1440_minutes(self):
        self.assertEqual(ONE_DAY, 1440)

    def test_jump_clock_fires_nothing_in_either_direction(self):
        """A hard jump, not simulated time passing; a caller wanting due
        effects to fire calls advance() separately."""
        slot = _slot()
        SCHEDULING.schedule_effect(slot, Effect(EffectKind.SET_PERSON_FLAG, "brenda", {"flag": "x", "value": True}), 10)
        SCHEDULING.jump_clock(slot, ONE_DAY)
        self.assertEqual(len(slot["pending"]), 1)
        SCHEDULING.jump_clock(slot, -2 * ONE_DAY)
        self.assertEqual(len(slot["pending"]), 1)


class CalendarPrimitiveTests(SimpleTestCase):
    """The generic, datetime-like primitives every story can use directly."""

    def test_minute_of_day_wraps_at_1440(self):
        self.assertEqual(minute_of_day(0), 0)
        self.assertEqual(minute_of_day(1439), 1439)
        self.assertEqual(minute_of_day(1440), 0)
        self.assertEqual(minute_of_day(1440 + 90), 90)

    def test_hour_of_day_divides_minutes_by_sixty(self):
        self.assertEqual(hour_of_day(0), 0)
        self.assertEqual(hour_of_day(59), 0)
        self.assertEqual(hour_of_day(60), 1)
        self.assertEqual(hour_of_day(23 * 60 + 59), 23)

    def test_day_of_week_zero_is_monday(self):
        self.assertEqual(day_of_week(0), 0)
        self.assertEqual(day_of_week(ONE_DAY), 1)
        self.assertEqual(day_of_week(ONE_DAY * 6), 6)
        self.assertEqual(day_of_week(ONE_DAY * 7), 0)

    def test_is_weekday_true_monday_through_friday(self):
        self.assertEqual([is_weekday(ONE_DAY * day) for day in range(7)], [True, True, True, True, True, False, False])


class DayPhaseTests(SimpleTestCase):
    """is_morning/is_afternoon/is_evening/is_night/is_day -- generic
    day-phase buckets with common-sense default boundaries, overridable
    per-story via DayPhaseBoundaries."""

    def test_default_boundaries_partition_the_day(self):
        for minute in range(0, 1440, 13):
            phases = [is_morning(minute), is_afternoon(minute), is_evening(minute), is_night(minute)]
            self.assertEqual(sum(phases), 1, f"minute {minute} matched {sum(phases)} phases, expected exactly 1")

    def test_is_day_is_the_negation_of_is_night(self):
        for minute in range(0, 1440, 13):
            self.assertEqual(is_day(minute), not is_night(minute))

    def test_morning_default_window(self):
        self.assertFalse(is_morning(5 * 60 + 59))
        self.assertTrue(is_morning(6 * 60))
        self.assertTrue(is_morning(11 * 60 + 59))
        self.assertFalse(is_morning(12 * 60))

    def test_night_default_window_wraps_past_midnight(self):
        self.assertFalse(is_night(20 * 60 + 59))
        self.assertTrue(is_night(21 * 60))
        self.assertTrue(is_night(23 * 60 + 59))
        self.assertTrue(is_night(0))
        self.assertTrue(is_night(5 * 60 + 59))
        self.assertFalse(is_night(6 * 60))

    def test_custom_boundaries_for_a_vampire_themed_story(self):
        vampire_phases = DayPhaseBoundaries(morning_start=8 * 60, afternoon_start=12 * 60, evening_start=16 * 60, night_start=20 * 60)
        self.assertFalse(is_night(19 * 60 + 59, vampire_phases))
        self.assertTrue(is_night(20 * 60, vampire_phases))
        self.assertTrue(is_night(7 * 60 + 59, vampire_phases))
        self.assertFalse(is_night(8 * 60, vampire_phases))


class BindingTests(SimpleTestCase):
    """The Ink surface: the clock over the slot, the day-phase helpers stateless."""

    def test_the_bindings_are_published_under_the_method_names(self):
        slot = PLUGIN.init_state(None)
        self.assertEqual(
            sorted(PLUGIN.bind(slot, {}, {})),
            ["advance_clock", "cancel_event_now", "clock", "event_pending", "schedule_person_flag", "set_clock"],
        )
        self.assertEqual(
            sorted(PLUGIN.bindings), ["day_of_week", "hour_of_day", "is_afternoon", "is_day", "is_evening", "is_morning", "is_night", "is_weekday"]
        )

    def test_advancing_the_clock_keeps_a_co_tenants_keys(self):
        """A plugin sharing this slot keeps its own keys: nothing here
        rewrites the whole slot."""
        slot = PLUGIN.init_state(None)
        slot["a_co_tenant_key"] = "belongs to another plugin"
        bindings = PLUGIN.bind(slot, {}, {})
        self.assertEqual(bindings["advance_clock"](60), 60)
        self.assertEqual(bindings["set_clock"](5), 5)
        self.assertEqual(slot["a_co_tenant_key"], "belongs to another plugin")
        self.assertEqual(bindings["clock"](), 5)


class NamedEventTests(SimpleTestCase):
    """`event_id`, cancellation, and replace-on-rearm."""

    def _slot(self) -> dict:
        return {"clock": 0, "pending": []}

    def _flag_effect(self) -> Effect:
        return Effect(kind=EffectKind.SET_PERSON_FLAG, target="hannah", payload={"flag": "call_ready", "value": True})

    def test_a_named_event_is_pending_until_it_fires(self):
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 35, event_id="hannah_call")
        self.assertTrue(SCHEDULING.event_is_pending(slot, "hannah_call"))
        self.assertEqual(SCHEDULING.advance(slot, 20), [], "not due yet")
        self.assertTrue(SCHEDULING.event_is_pending(slot, "hannah_call"))
        fired = SCHEDULING.advance(slot, 20)
        self.assertEqual([effect.target for effect in fired], ["hannah"])
        self.assertFalse(SCHEDULING.event_is_pending(slot, "hannah_call"), "a fired event has left the queue")

    def test_rearming_the_same_name_replaces_rather_than_duplicates(self):
        """A timer armed twice must still fire once."""
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10, event_id="dup")
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10, event_id="dup")
        self.assertEqual(len(slot["pending"]), 1)

    def test_replace_false_queues_both(self):
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10, event_id="dup")
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10, event_id="dup", replace=False)
        self.assertEqual(len(slot["pending"]), 2)

    def test_cancelling_removes_it_and_reports_how_many(self):
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10, event_id="doomed")
        self.assertEqual(SCHEDULING.cancel_event(slot, "doomed"), 1)
        self.assertFalse(SCHEDULING.event_is_pending(slot, "doomed"))
        self.assertEqual(SCHEDULING.cancel_event(slot, "doomed"), 0, "cancelling nothing is not an error")

    def test_an_unnamed_event_still_fires_and_is_never_cancelled_by_name(self):
        """Records written before named events existed have no id."""
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 10)
        self.assertNotIn("event_id", slot["pending"][0])
        self.assertEqual(SCHEDULING.cancel_event(slot, ""), 0)
        self.assertEqual(len(SCHEDULING.advance(slot, 10)), 1)

    def test_a_pending_event_survives_a_save_round_trip(self):
        slot = self._slot()
        SCHEDULING.schedule_effect(slot, self._flag_effect(), 35, event_id="hannah_call")
        restored = json.loads(json.dumps(slot))
        self.assertTrue(SCHEDULING.event_is_pending(restored, "hannah_call"))
        self.assertEqual([effect.target for effect in SCHEDULING.advance(restored, 35)], ["hannah"])
