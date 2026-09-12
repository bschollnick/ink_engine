"""SchedulingSystem: a generic clock/timed-event framework.

A reusable engine service a story builds its time-driven behaviour on.
This module has zero knowledge of what a "character", a "flag" or a
"location" means in any story; it understands only a clock and a queue of
(due_time, effect) pairs, where an effect is one of a small, closed,
non-executable vocabulary (`EffectKind` below) -- plain data the CALLER
interprets and applies.

**Baseline unit is minutes, not an arbitrary "tick"**: the slot's `clock`
and every `clock` argument below is a count of real minutes (1440/day),
matching everyday clock/calendar arithmetic. A story with a coarser or
finer native clock converts at its own boundary; this module is never
written in terms of a story-specific tick size.

**Generic calendar/day-phase helpers, not story business rules**: this
module owns the `datetime`-like primitives every story needs
(`is_weekday`, `hour_of_day`, `is_morning`/`is_afternoon`/`is_evening`/
`is_night`/`is_day`), with default boundaries overridable per-story via
`DayPhaseBoundaries`. Open-hours rules like "is this shop open" are story
data and belong in a story's own scheduling module built on these.

**`advance()` only REPORTS fired effects**; the caller applies each one
to whatever state model it uses.

**The Enum never enters the slot.** `Effect` and `EffectKind` are the
API's value types; the slot holds each pending event as a plain record
with the kind's string value. A record whose kind is unknown raises when
it fires, not when the save loads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict

from ink_engine.plugin import EngineState
from ink_engine.plugin_base import StatefulPlugin, external, query

#: Where this plugin's state lives in a session's `EngineState`. Published
#: so a dependent plugin reads the clock by constant rather than by a
#: copied string literal.
STATE_KEY = "scheduling"


class EffectKind(Enum):
    """The 3 timed-event effects in the original source (`time.js`'s
    `movePersonfterTime`/`setPersonFlagAfterTime`/`setPlaceFlagAfterTime`)
    -- a closed, non-`eval` vocabulary. Extend only by adding another named
    kind here, never by accepting an arbitrary string/code payload."""

    MOVE_CHARACTER = "move_character"
    SET_PERSON_FLAG = "set_person_flag"
    SET_PLACE_FLAG = "set_place_flag"


@dataclass(frozen=True)
class Effect:
    """One timed event's effect, as plain, JSON-safe data -- never code.

    Args:
        kind: Which of the 3 closed effect kinds this is.
        target: The subject of the effect -- a character id for
            MOVE_CHARACTER/SET_PERSON_FLAG, a place id for SET_PLACE_FLAG.
            Never looked up here, only reported back.
        payload: The effect's arguments (e.g. {"place_id": "hotel_room"}
            for MOVE_CHARACTER, {"flag": "met_the_stranger", "value":
            True} for SET_PERSON_FLAG/SET_PLACE_FLAG) -- plain JSON-safe
            values only.
    """

    kind: EffectKind
    target: str
    payload: dict[str, Any] = field(default_factory=dict)


class EffectRecord(TypedDict):
    """An `Effect` as the slot holds it: the kind by its string value."""

    kind: str
    target: str
    payload: dict[str, Any]


class PendingRecord(TypedDict):
    """One entry in the timed-event queue."""

    due_time: int
    effect: EffectRecord


class SchedulingSlot(TypedDict):
    """A session's clock and pending timed-event queue.

    Attributes:
        clock: The current time, in whole minutes since an arbitrary
            session-defined epoch.
        pending: The timed-event queue, each entry a (due_time, effect)
            record -- a non-`eval` port of source's `vTimedEvent` array of
            `TimedEvent(evt, time)` objects.
    """

    clock: int
    pending: list[PendingRecord]


def _record(effect: Effect) -> EffectRecord:
    """Take an effect apart into the JSON-safe record the slot holds."""
    return {"kind": effect.kind.value, "target": effect.target, "payload": dict(effect.payload)}


def _effect(record: EffectRecord) -> Effect:
    """Rebuild an effect from the record the slot holds.

    Raises:
        ValueError: The record's kind is not one this vocabulary knows.
    """
    return Effect(kind=EffectKind(record["kind"]), target=str(record["target"]), payload=dict(record.get("payload", {})))


def clock_of(engine_state: EngineState) -> int:
    """Return the current clock, from a full session state.

    For a plugin that needs the time but does not own it.

    Args:
        engine_state: The full session state, not this plugin's slot.

    Returns:
        The clock value, or 0 when this plugin holds no state.
    """
    return int(engine_state.get(STATE_KEY, {}).get("clock", 0))


MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 1440

# Named minute deltas for jump_clock() below — the round-unit
# advance/rewind a cheat menu or debug tool wants. A story with its own
# jump amounts defines those itself.
ONE_HOUR = MINUTES_PER_HOUR
ONE_DAY = MINUTES_PER_DAY

# Named minute-of-day constants for every whole hour, so a schedule rule
# built with Condition.minute_in_range() reads as a clock time instead of
# a number a reader has to divide by 60. Sub-hour boundaries are ordinary
# arithmetic on top of these, e.g. `EIGHT_AM + 15` for 8:15am.
MIDNIGHT = 0 * MINUTES_PER_HOUR
ONE_AM = 1 * MINUTES_PER_HOUR
TWO_AM = 2 * MINUTES_PER_HOUR
THREE_AM = 3 * MINUTES_PER_HOUR
FOUR_AM = 4 * MINUTES_PER_HOUR
FIVE_AM = 5 * MINUTES_PER_HOUR
SIX_AM = 6 * MINUTES_PER_HOUR
SEVEN_AM = 7 * MINUTES_PER_HOUR
EIGHT_AM = 8 * MINUTES_PER_HOUR
NINE_AM = 9 * MINUTES_PER_HOUR
TEN_AM = 10 * MINUTES_PER_HOUR
ELEVEN_AM = 11 * MINUTES_PER_HOUR
NOON = 12 * MINUTES_PER_HOUR
ONE_PM = 13 * MINUTES_PER_HOUR
TWO_PM = 14 * MINUTES_PER_HOUR
THREE_PM = 15 * MINUTES_PER_HOUR
FOUR_PM = 16 * MINUTES_PER_HOUR
FIVE_PM = 17 * MINUTES_PER_HOUR
SIX_PM = 18 * MINUTES_PER_HOUR
SEVEN_PM = 19 * MINUTES_PER_HOUR
EIGHT_PM = 20 * MINUTES_PER_HOUR
NINE_PM = 21 * MINUTES_PER_HOUR
TEN_PM = 22 * MINUTES_PER_HOUR
ELEVEN_PM = 23 * MINUTES_PER_HOUR


def minute_of_day(clock: int) -> int:
    """Return the minute-of-day (0-1439) for `clock`.

    Args:
        clock: The current absolute clock value, in minutes.

    Returns:
        `clock` reduced to its position within a 1440-minute day.
    """
    return clock % MINUTES_PER_DAY


def hour_of_day(clock: int) -> int:
    """Return the hour of the day (0-23) for `clock`.

    Args:
        clock: The current absolute clock value, in minutes.

    Returns:
        The hour of the day, 0-23.
    """
    return minute_of_day(clock) // MINUTES_PER_HOUR


def day_of_week(clock: int) -> int:
    """Return the day of the week for `clock` (0=Monday .. 6=Sunday).

    Args:
        clock: The current absolute clock value, in minutes.

    Returns:
        The day of the week, 0 (Monday) through 6 (Sunday).
    """
    return (clock // MINUTES_PER_DAY) % 7


def is_weekday(clock: int) -> bool:
    """Return whether `clock` falls on a weekday (Monday-Friday).

    Args:
        clock: The current absolute clock value, in minutes.

    Returns:
        True if `day_of_week(clock)` is Monday (0) through Friday (4).
    """
    return day_of_week(clock) <= 4


@dataclass(frozen=True)
class DayPhaseBoundaries:
    """The minute-of-day cutoffs the generic day-phase helpers below use.

    Defaults are provided, but a story with its own notion of when
    "morning"/"night" begin (a vampire story where night runs 20:00-8:00)
    builds its own instance and passes it explicitly.

    Args:
        morning_start: Minute-of-day morning begins (default 6:00).
        afternoon_start: Minute-of-day afternoon begins (default 12:00).
        evening_start: Minute-of-day evening begins (default 17:00).
        night_start: Minute-of-day night begins (default 21:00); night is
            understood to wrap past midnight into `morning_start`.
    """

    morning_start: int = 6 * MINUTES_PER_HOUR
    afternoon_start: int = 12 * MINUTES_PER_HOUR
    evening_start: int = 17 * MINUTES_PER_HOUR
    night_start: int = 21 * MINUTES_PER_HOUR


DEFAULT_DAY_PHASES = DayPhaseBoundaries()


def is_morning(clock: int, boundaries: DayPhaseBoundaries = DEFAULT_DAY_PHASES) -> bool:
    """Return whether `clock` falls within the morning phase.

    Args:
        clock: The current absolute clock value, in minutes.
        boundaries: The day-phase cutoffs to use (default 6:00-12:00 morning).

    Returns:
        True if the minute-of-day is in `[morning_start, afternoon_start)`.
    """
    minute = minute_of_day(clock)
    return boundaries.morning_start <= minute < boundaries.afternoon_start


def is_afternoon(clock: int, boundaries: DayPhaseBoundaries = DEFAULT_DAY_PHASES) -> bool:
    """Return whether `clock` falls within the afternoon phase.

    Args:
        clock: The current absolute clock value, in minutes.
        boundaries: The day-phase cutoffs to use (default 12:00-17:00 afternoon).

    Returns:
        True if the minute-of-day is in `[afternoon_start, evening_start)`.
    """
    minute = minute_of_day(clock)
    return boundaries.afternoon_start <= minute < boundaries.evening_start


def is_evening(clock: int, boundaries: DayPhaseBoundaries = DEFAULT_DAY_PHASES) -> bool:
    """Return whether `clock` falls within the evening phase.

    Args:
        clock: The current absolute clock value, in minutes.
        boundaries: The day-phase cutoffs to use (default 17:00-21:00 evening).

    Returns:
        True if the minute-of-day is in `[evening_start, night_start)`.
    """
    minute = minute_of_day(clock)
    return boundaries.evening_start <= minute < boundaries.night_start


def is_night(clock: int, boundaries: DayPhaseBoundaries = DEFAULT_DAY_PHASES) -> bool:
    """Return whether `clock` falls within the night phase.

    Handles wraparound past midnight: with night_start=20:00 and
    morning_start=8:00, night covers 20:00-24:00 AND 0:00-8:00.

    Args:
        clock: The current absolute clock value, in minutes.
        boundaries: The day-phase cutoffs to use (default 21:00-6:00 night).

    Returns:
        True if the minute-of-day falls outside
        `[morning_start, night_start)`.
    """
    minute = minute_of_day(clock)
    return not boundaries.morning_start <= minute < boundaries.night_start


def is_day(clock: int, boundaries: DayPhaseBoundaries = DEFAULT_DAY_PHASES) -> bool:
    """Return whether `clock` falls within the daytime portion of its day.

    Args:
        clock: The current absolute clock value, in minutes.
        boundaries: The day-phase cutoffs to use (default 6:00-21:00 day).

    Returns:
        True whenever `is_night()` is False for the same clock/boundaries.
    """
    return not is_night(clock, boundaries)


class Scheduling(StatefulPlugin[SchedulingSlot]):
    """The engine-owned clock and its timed-event queue.

    The clock is engine-owned state rather than a value each story threads
    through every time-dependent call. A story whose native time unit is
    not minutes converts at its own boundary and keeps its own calendar
    semantics on top; this plugin owns only "what time is it" and "time
    passed". The day-phase helpers above are published as stateless
    bindings, each taking the clock value Ink passes.
    """

    name = "scheduling"
    display_name = "Scheduling"
    state_key = STATE_KEY
    slot_type = SchedulingSlot
    fields = {"clock": int, "pending": list}
    stateless_bindings = {
        "is_day": is_day,
        "is_morning": is_morning,
        "is_afternoon": is_afternoon,
        "is_evening": is_evening,
        "is_night": is_night,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "is_weekday": is_weekday,
    }

    @query
    @external
    def clock(self, slot: SchedulingSlot) -> int:
        """Return the current absolute clock, in minutes.

        Args:
            slot: This session's slot.

        Returns:
            The clock value, 0 for a session that has not advanced.
        """
        return int(slot.get("clock", 0))

    def schedule_effect(self, slot: SchedulingSlot, effect: Effect, minutes_from_now: int) -> None:
        """Queue an effect to fire `minutes_from_now` minutes after the current clock.

        A non-`eval` port of source's `startTimedEvent(evt, cnt)`
        (`time.js`) -- `minutes_from_now` mirrors `cnt`, an offset from
        the current clock rather than an absolute time.

        Args:
            slot: This session's slot.
            effect: The closed-vocabulary effect to fire once due.
            minutes_from_now: How many minutes from the clock until this
                effect becomes due.
        """
        slot.setdefault("pending", []).append({"due_time": self.clock(slot) + minutes_from_now, "effect": _record(effect)})

    def pending_effects(self, slot: SchedulingSlot) -> list[tuple[int, Effect]]:
        """Return every queued effect with its due time, in queue order.

        Args:
            slot: This session's slot.

        Returns:
            `(due_time, effect)` pairs.
        """
        return [(int(record["due_time"]), _effect(record["effect"])) for record in slot.get("pending", [])]

    def advance(self, slot: SchedulingSlot, minutes: int) -> list[Effect]:
        """Advance the clock by `minutes` and report every effect now due.

        A non-`eval` port of source's `passTime()` -> `nTime += ...` ->
        `checkTimedEvents()` sequence (`time.js`) -- every due event fires
        once, then is removed from the queue. This does NOT apply any
        effect to any character/flag/place state; the caller interprets
        and applies each returned Effect against whatever state model it
        uses.

        Args:
            slot: This session's slot.
            minutes: How many minutes to advance the clock by -- the
                caller decides how many minutes a turn or action
                corresponds to.

        Returns:
            The effects that became due this advance, in the order they
            were scheduled. Anything not yet due stays queued.
        """
        new_clock = self.clock(slot) + minutes
        fired: list[Effect] = []
        still_pending: list[PendingRecord] = []
        for record in slot.get("pending", []):
            if int(record["due_time"]) <= new_clock:
                fired.append(_effect(record["effect"]))
            else:
                still_pending.append(record)
        slot["clock"] = new_clock
        slot["pending"] = still_pending
        return fired

    @external
    def advance_clock(self, slot: SchedulingSlot, minutes: int) -> int:
        """EXTERNAL `advance_clock(minutes)`: move the clock forward.

        This binding DISCARDS any effects that fire; call `advance()`
        directly to receive them.

        Args:
            slot: This session's slot.
            minutes: How many minutes pass.

        Returns:
            The new clock value.
        """
        self.advance(slot, minutes)
        return self.clock(slot)

    @external
    def set_clock(self, slot: SchedulingSlot, clock: int) -> int:
        """Set the clock outright, firing nothing.

        For a story restoring a saved time or applying its own jump or
        rewind; the queue is kept as it is.

        Args:
            slot: This session's slot.
            clock: The new absolute clock value.

        Returns:
            The new clock value.
        """
        slot["clock"] = clock
        return clock

    def jump_clock(self, slot: SchedulingSlot, delta: int) -> int:
        """Jump the clock by `delta` minutes in one step, firing nothing.

        A hard jump/rewind, not simulated time passing: no pending timed
        event fires or is checked in either direction. Call `advance()`
        separately to fire what is due.

        Args:
            slot: This session's slot.
            delta: The signed minute delta (positive forward, negative
                backward).

        Returns:
            The new clock value.
        """
        return self.set_clock(slot, self.clock(slot) + delta)


SCHEDULING = Scheduling()
PLUGIN = SCHEDULING.plugin()
