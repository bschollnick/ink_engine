"""CharacterOccupancy: who's at which location right now.

**This module depends on the map; the map does not depend on it.** "Who
is at which location" presupposes a set of locations, so a story using
occupancy is expected to declare its places through `location_graph.py`,
and placing a character somewhere the map never declared raises
`UnknownLocationError` rather than being stored. A mistyped location id
that IS stored fails silently forever after: `characters_at()` answers
with an empty list, indistinguishable from "nobody is here". A story
wanting only the map never has to adopt occupancy.

The map reaches this module as a plain `engine_state` read keyed by
`location_graph.STATE_KEY` (imported directly), not an import of
`location_graph`'s own functions: the vocabulary is read from the
session's own location state, so a story that declares no map is simply
unchecked rather than broken.

**What this framework replaces**: hand-written per-character
`_place_now()` Ink functions, each re-deriving "where is this person
right now" from schedule/story-flag logic. Here a character's schedule
RULE is plain, closed, JSON-safe DATA (a `ScheduleRule`, from
`schedule_rules`) evaluated by one generic function (`resolve_schedule()`).
Those names are re-exported here so a story imports one module.

**SchedulingSystem is an optional dependency, not a hard one.** A story
can track a character's location as a flat "wherever it was last
explicitly set" value (`place()`/`where_is()` alone) or layer a
`ScheduleRule` on top that resolves against a clock tick and session
flags. `resolve_schedule()` takes a plain integer tick, not a
`SchedulingState` -- this module does not import
`engine_plugins.scheduling` at all.

**How the two halves fit together**: the slot is the live layer -- the
one record of where each character is, player and NPC alike. A story's
own scheduler revises it: `recompute()` resolves every schedule-driven
character and writes the answer in. Reads then come from the store
rather than re-resolving, though `resolve_schedule()` and
`resolve_present_characters()` are both public for a story that prefers
resolving on read.

**No config, deliberately.** A schedule is built as `ScheduleRule`
objects holding `Condition` objects, in Python, by the story that owns
them. There is no JSON shape to check: `Condition` carries an Enum member
and has no serialization to config. A validator for a schedule-shaped
config once existed and silently drifted two condition kinds behind this
module, because nothing could call it. Add one only alongside a real
config reader, never on its own.
"""

from __future__ import annotations

from typing import Any, TypedDict

from ink_engine.engine_plugins.location_graph import STATE_KEY as _LOCATION_STATE_KEY
from ink_engine.engine_plugins.schedule_rules import (
    Condition,
    ConditionKind,
    EvalContext,
    QueryRegistry,
    ScheduleRule,
    StoryRuleRegistry,
    StoryValueRegistry,
    UnknownQueryError,
    engine_query_registry,
    evaluate_condition,
    resolve_schedule,
)
from ink_engine.plugin_base import BindingContext, StatefulPlugin, external, query

__all__ = [
    "Condition",
    "ConditionKind",
    "EvalContext",
    "QueryRegistry",
    "ScheduleRule",
    "StoryRuleRegistry",
    "StoryValueRegistry",
    "UnknownQueryError",
    "engine_query_registry",
    "evaluate_condition",
    "resolve_schedule",
    "STATE_KEY",
    "OccupancySlot",
    "UnknownLocationError",
    "CharacterOccupancy",
    "CHARACTER_OCCUPANCY",
    "PLUGIN",
    "resolve_present_characters",
]

# The state slot this plugin owns, named as a module constant so a
# dependent plugin can read it via `engine_state.get(STATE_KEY, {})`
# without a hardcoded string literal.
STATE_KEY = "character_occupancy"


class OccupancySlot(TypedDict):
    """A session's live occupancy layer.

    Attributes:
        locations: character_id -> location_id, for every character whose
            location is currently known. A character absent from
            `locations` is not present anywhere -- either never placed, or
            cleared by `place(..., None)`.
    """

    locations: dict[str, str]


class UnknownLocationError(ValueError):
    """A character was placed at a location the story never declared.

    Fatal rather than a warning. An unknown location id fails silently
    everywhere else -- `characters_at()` returns an empty list and
    `is_at()` returns False, both indistinguishable from "nobody is here"
    -- so a typo silently removes characters and the content gated on
    their presence for the rest of the playthrough. A player cannot
    detect that; a stopped game they can.

    Raised only when the story declares a map at all. A story that
    declares none may track its places some other way, which this module
    supports.
    """


# Removable once resolve_schedule() takes fewer parameters: this passes
# every one of them through, plus location_id.
def resolve_present_characters(  # pylint: disable=too-many-arguments
    location_id: str,
    schedules: dict[str, tuple[ScheduleRule, ...]],
    flags: frozenset[str],
    clock: int,
    *,
    story_rules: StoryRuleRegistry | None = None,
    story_values: StoryValueRegistry | None = None,
    engine_state: dict[str, Any] | None = None,
) -> list[str]:
    """Return every schedule-driven character currently resolved to `location_id`.

    The schedule-driven counterpart to `characters_at()`, which covers
    only the store's explicitly-set locations. A character placed via
    `place()` with no ScheduleRule is not covered here -- fold in a
    `characters_at()` result separately if a story mixes both kinds at one
    location.

    Args:
        location_id: The location to check.
        schedules: character_id -> that character's ScheduleRule tuple.
        flags: The set of currently-set session-flag names, shared across
            every character's schedule evaluation.
        clock: The current absolute tick count, passed through unchanged
            to each `resolve_schedule()` call.
        story_rules: The registry of named boolean functions of `clock`.
        story_values: The registry of named int-or-str-valued functions
            of `clock`.
        engine_state: Other plugins' serialized state, keyed by state
            slot, for ENGINE_STATE and QUERY nodes.

    Returns:
        The character ids whose `resolve_schedule()` result equals
        `location_id`, in `schedules`' iteration order.
    """
    return [
        character_id
        for character_id, rules in schedules.items()
        if resolve_schedule(rules, flags=flags, clock=clock, story_rules=story_rules, story_values=story_values, engine_state=engine_state)
        == location_id
    ]


class CharacterOccupancy(StatefulPlugin[OccupancySlot]):
    """Where every tracked character is right now.

    A game extends this by subclassing: keep every inherited binding, add
    its own recompute over its own schedules, and activate the subclass
    in place of this plugin.
    """

    name = "character_occupancy"
    display_name = "Character occupancy"
    state_key = STATE_KEY
    slot_type = OccupancySlot
    fields = {"locations": dict}

    def place(
        self,
        slot: OccupancySlot,
        character_id: str,
        location_id: str | None,
        known_locations: frozenset[str] | None = None,
    ) -> None:
        """Place a character at a location, or remove them from the world.

        Checked on write, the only moment a bad value is still
        attributable: once a wrong id is in the store, every later symptom
        (an empty `characters_at()`, a False `is_at()`) looks like a
        character legitimately being elsewhere.

        Args:
            slot: This session's slot.
            character_id: The character to move.
            location_id: The location to place them at, or None to mark
                them absent (removes any existing entry).
            known_locations: Every location this story declares, or None
                to skip the check. A story that declares no locations
                tracks its map some other way, which this module supports.

        Raises:
            UnknownLocationError: If `location_id` is not among
                `known_locations`. Fatal rather than logged: the
                alternative is a playthrough that silently loses
                characters.
        """
        if location_id is not None and known_locations and location_id not in known_locations:
            raise UnknownLocationError(
                f"cannot place {character_id!r} at unknown location {location_id!r}: "
                f"this story declares no such location (it declares {', '.join(sorted(known_locations)[:5])}"
                f"{', …' if len(known_locations) > 5 else ''})"
            )
        locations = slot.setdefault("locations", {})
        if location_id is None:
            locations.pop(character_id, None)
        else:
            locations[character_id] = location_id

    @external(needs_context=True)
    def set_location(self, context: BindingContext[OccupancySlot], character_id: str, location_id: str) -> None:
        """EXTERNAL `set_location(character_id, location_id)`: `place()` for Ink.

        Ink VARs carry no None, so an empty string removes the character
        from the world. The location vocabulary is the map's declared
        set, read from the session's `location_graph` slot; a story with
        no map slot is not checked.

        Args:
            context: This session.
            character_id: The character to move.
            location_id: Where to place them, or "" to remove them.

        Raises:
            UnknownLocationError: If the story declares its locations and
                this is not one of them.
        """
        known_locations = frozenset(context.slot_of(_LOCATION_STATE_KEY).get("declared", ()))
        self.place(context.slot, character_id, location_id or None, known_locations)

    @query
    @external
    def where_is(self, slot: OccupancySlot, character_id: str, default: str | None = "") -> str | None:
        """Return a character's current location from the occupancy store.

        A plain read of the store -- it never evaluates a ScheduleRule. A
        schedule-driven character answers correctly here because the
        story's scheduler wrote their resolved location in, so the value
        is as fresh as the last recompute.

        Args:
            slot: This session's slot.
            character_id: The character to look up.
            default: What to answer for a character placed nowhere. The
                empty string, so Ink (which has no None) gets a value it
                can compare; a Python caller that wants None passes it.

        Returns:
            The character's current location id, or `default`.
        """
        return slot.get("locations", {}).get(character_id, default)

    @query
    @external
    def is_at(self, slot: OccupancySlot, character_id: str, location_id: str) -> bool:
        """Return whether a character is at a given location.

        The boolean counterpart to `where_is()`. Both read the same store;
        this one exists because "is X here" is the question most story
        content asks, and spelling it as an equality at each call site
        invites the subtly different "is X anywhere at all" to creep in
        as a substitute -- a story that conflates them reports characters
        as present across the whole map.

        Args:
            slot: This session's slot.
            character_id: The character to check.
            location_id: The location to check them against.

        Returns:
            True if the character's stored location equals `location_id`.
            A character who is nowhere is never "at" anywhere, including
            at "".
        """
        return slot.get("locations", {}).get(character_id) == location_id

    @query
    @external
    def is_with(self, slot: OccupancySlot, character_id: str, other_character_id: str) -> bool:
        """Return whether two characters are at the same location.

        The store-based form of "is X here", where "here" is wherever
        another character (typically the player) is. Two absent
        characters are not together, they are both nowhere.

        Args:
            slot: This session's slot.
            character_id: The character being asked about.
            other_character_id: The character whose location defines
                "here" -- usually the player.

        Returns:
            True if both are placed and their locations are equal.
        """
        locations = slot.get("locations", {})
        location = locations.get(other_character_id)
        return location is not None and locations.get(character_id) == location

    @query
    @external
    def is_anywhere(self, slot: OccupancySlot, character_id: str) -> bool:
        """Return whether a character is placed anywhere at all.

        Distinct from `is_at()`: this asks only whether the character
        exists in the world right now, not where. Right for gating on
        "has this character been removed / not yet introduced", wrong as
        a stand-in for presence at a place.

        Args:
            slot: This session's slot.
            character_id: The character to check.

        Returns:
            True if the store holds any location for them.
        """
        return character_id in slot.get("locations", {})

    @query
    def characters_at(self, slot: OccupancySlot, location_id: str) -> list[str]:
        """Return every character currently at `location_id`.

        Reads the occupancy store and nothing else -- it never evaluates
        a ScheduleRule. Schedule-driven characters appear here once the
        story's scheduler has written their resolved locations in.

        Args:
            slot: This session's slot.
            location_id: The location to check.

        Returns:
            The character ids currently at `location_id`, in insertion
            order.
        """
        return [character_id for character_id, current_location in slot.get("locations", {}).items() if current_location == location_id]

    @external
    def who_is_at(self, slot: OccupancySlot, location_id: str) -> str:
        """EXTERNAL `who_is_at(location_id)`: `characters_at()` for Ink.

        Ink has no list return, so the ids are joined with ","; the caller
        splits it. A character_id containing "," is excluded rather than
        joined ambiguously: a character_id is an arbitrary string an
        author writes, not a validated identifier.

        Args:
            slot: This session's slot.
            location_id: The location to check.

        Returns:
            The ids joined with ",", or "" if nobody is there.
        """
        return ",".join(character_id for character_id in self.characters_at(slot, location_id) if "," not in character_id)

    def recompute(  # pylint: disable=too-many-arguments
        self,
        slot: OccupancySlot,
        schedules: dict[str, tuple[ScheduleRule, ...]],
        flags: frozenset[str],
        clock: int,
        *,
        story_rules: StoryRuleRegistry | None = None,
        story_values: StoryValueRegistry | None = None,
        engine_state: dict[str, Any] | None = None,
    ) -> None:
        """Re-resolve every scheduled character and write the results into the store.

        The write-back sibling of `resolve_present_characters()`, which
        answers "who is at this place right now" without touching the
        store. A story calls this whenever it wants the store brought up
        to date -- typically on entering a location -- after which every
        `where_is()`/`characters_at()` read reflects the same single
        moment.

        A character whose schedule resolves to None is cleared rather than
        left as a stale entry. Characters absent from `schedules` -- those
        placed explicitly via `set_location()`, the player included -- are
        untouched.

        The pylint argument-count disable above holds for the reason given
        on `resolve_present_characters()`.

        Args:
            slot: This session's slot, written in place.
            schedules: character_id -> that character's ScheduleRule tuple.
            flags: The set of currently-set session-flag names.
            clock: The current absolute tick count.
            story_rules: The registry of named boolean functions of `clock`.
            story_values: The registry of named int-or-str-valued
                functions of `clock`.
            engine_state: Other plugins' serialized state, keyed by state
                slot.
        """
        locations = slot.setdefault("locations", {})
        for character_id, rules in schedules.items():
            resolved = resolve_schedule(rules, flags=flags, clock=clock, story_rules=story_rules, story_values=story_values, engine_state=engine_state)
            if resolved is None:
                locations.pop(character_id, None)
            else:
                locations[character_id] = resolved


CHARACTER_OCCUPANCY = CharacterOccupancy()
PLUGIN = CHARACTER_OCCUPANCY.plugin()
