"""Take one exit: set where the story is going, then choose to go there.

An application that offers movement outside the story's own choice list —
an exits panel, a map — needs the move to be narrated and to advance the
turn like any other choice. Two things make that work, and both are easy
to get wrong on your own, which is why this module exists.

**A destination must be a `ResolvedDivertTarget`.** Three values look
like a divert target and only one is. A knot name as a plain string
fails loudly at runtime ("the variable didn't contain a divert target,
it contained 'foo'"). A `DivertTargetValue`, the literal token as it
appears in compiled JSON, does not move the story: the divert goes
nowhere, and a turn left with no choices raises `StoryRuntimeError`.
`build_divert_target()` returns the third, which works.

**The move has to be a real choice, and the choice must be unguarded.**
Taking it advances `turn_count` and the visit counts exactly as a player
picking it would. Guarding it behind a flag does not work: after a move,
the turn began inside the previous location, so `refresh_choices()`
replays through the movement knot rather than re-evaluating the guard —
the first move succeeds and every later one silently relocates the
player with no text and no turn. An unguarded choice is present in every
turn's list already, so no refresh is needed.

The story supplies one knot for arriving anywhere:

```ink
=== movement ===
{travel_text}
-> destination
```

offered from each location as `+ [GO] -> movement`. An application that
draws its own exits panel hides that choice from the list it shows, so a
player never sees it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ink_engine.engine import (
    InkRuntimeState,
    ResolvedDivertTarget,
    UnknownDivertTargetError,
    resolve_divert_target,
)

#: The globals a story's movement knot reads. A game that names its own
#: may pass them to `take_exit()` instead.
DESTINATION_GLOBAL = "destination"
TRAVEL_TEXT_GLOBAL = "travel_text"

#: The choice each location offers for leaving it.
MOVE_CHOICE_TEXT = "GO"


class TravelError(Exception):
    """A move could not be taken."""


@dataclass(frozen=True, slots=True)
class StoryNames:
    """What a story calls the globals and choice `take_exit()` drives.

    A game that names its own passes one of these; the defaults match the
    pattern in this module's docstring.
    """

    destination: str = DESTINATION_GLOBAL
    travel_text: str = TRAVEL_TEXT_GLOBAL
    move_choice: str = MOVE_CHOICE_TEXT


def build_divert_target(state: InkRuntimeState, knot_name: str) -> ResolvedDivertTarget:
    """Return a divert target a story can follow to `knot_name`.

    Args:
        state: The session, for its story root.
        knot_name: The knot to arrive at.

    Returns:
        The target, ready to write into a story global.

    Raises:
        TravelError: If the story has no such knot. Raised here because
            the alternative is a divert that goes nowhere.
    """
    try:
        return resolve_divert_target(state.root, knot_name)
    except UnknownDivertTargetError as error:
        raise TravelError(str(error)) from error


def take_exit(
    state: InkRuntimeState,
    arrival_knot: str,
    travel_text: str,
    *,
    names: StoryNames | None = None,
) -> str:
    """Move the story to `arrival_knot`, narrating `travel_text` on the way.

    Writes both into the story's globals, then takes the story's
    movement choice. The turn advances exactly as it would had the
    player picked that choice themselves.

    Args:
        state: The session to move.
        arrival_knot: The knot to arrive at.
        travel_text: The prose for taking this exit.
        names: What the story calls its movement globals and choice.
            Defaults to the names in this module's constants.

    Returns:
        The text of the turn, which begins with `travel_text` and
        continues with whatever the arrival knot prints.

    Raises:
        TravelError: If the knot does not exist, or this turn offers no
            movement choice — which means the location is missing the
            `+ [GO] -> movement` line the module docstring shows.
            Either is raised before the story is changed.
    """
    names = names or StoryNames()
    move_index = next((index for index, choice in enumerate(state.current_choices) if choice.text == names.move_choice), None)
    if move_index is None:
        raise TravelError(f"this turn offers no '{names.move_choice}' choice; offered {[choice.text for choice in state.current_choices]}")
    state.globals[names.destination] = build_divert_target(state, arrival_knot)
    state.globals[names.travel_text] = travel_text
    state.choose(move_index)
    return state.continue_story()
