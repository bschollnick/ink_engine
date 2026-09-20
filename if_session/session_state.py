"""One definition of a save envelope, a transcript, and a turn.

Each of these was written twice -- once per application -- and the duplication
fails silently: `from_dict()` reads every field with `data.get(key,
default)`, so a renamed key is not an error, it is a default. Rename
`output_tokens` and every save loads with an empty output stream and no
exception. One definition, plus a version marker, turns that into a
refusal.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ink_engine.media_resolver import parse_media_tags

#: The envelope's own version, bumped when its SHAPE changes -- a key
#: added, renamed or given a new meaning. It sits on the envelope rather
#: than inside the engine's `to_dict()`: the engine's serialization is one
#: component of a save, not the save.
#:
#: 2: a game is a verified bundle rather than a scanned directory, so a
#: save's media references and plugin state no longer mean what they did
#: under the directory layout.
SAVE_FORMAT_VERSION = 2

#: Keys this library layers onto the engine's own serialization. Named so
#: a reader can see what the application owns without diffing two dicts.
ENVELOPE_KEYS = ("transcript", "previous_state", "engine_state", "save_format_version")


class SaveFormatError(Exception):
    """A save cannot be read as this version of the envelope."""


@runtime_checkable
class StoryEngine(Protocol):
    """What this library needs of a story engine.

    Every member below is one an application actually calls today, traced at the
    call sites -- not a guess at what a story engine might offer. A second
    IF engine plugs in by implementing these.

    Two things are deliberately absent. **Ink globals** are read by panel
    hooks and character creation, but they are Ink-shaped and have no
    obvious equivalent elsewhere; an application reaches them directly and that is
    a known extraction cost, named rather than pretended away. **Plugin
    bindings** are threaded through opaquely, because whether the
    capability system is format-neutral is still open.
    """

    @property
    def last_turn_text(self) -> str:
        """The text this turn produced."""

    @property
    def current_choices(self) -> list[Any]:
        """This turn's choices. Each carries at least `.text`."""

    @property
    def done(self) -> bool:
        """Whether the story has reached an ending."""

    @property
    def turn_count(self) -> int:
        """A counter that only increases, for staleness guards."""

    @property
    def current_tags(self) -> list[str]:
        """This turn's own tags, for media resolution."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the runtime state."""


class MediaResolver(Protocol):  # pylint: disable=too-few-public-methods
    """Turns a turn's media tags into references an application can display."""

    def resolve(self, requests: list[tuple[str, str]]) -> list[str]:
        """Return one displayable reference per request that resolves."""


def build_saved_state(
    state: StoryEngine,
    previous_state: dict[str, Any] | None,
    transcript: list[dict[str, object]],
    engine_state: dict[str, Any],
) -> dict[str, Any]:
    """Compose one session's full persistable state.

    The engine's own serialization plus the application keys it has no use for:
    `transcript` is a UI affordance, `previous_state` is undo,
    `engine_state` is the plugin slot bag.

    Args:
        state: The story engine to serialize.
        previous_state: The one-level undo target -- this same shape,
            nested -- or None.
        transcript: The rolling turn history, already capped.
        engine_state: This session's per-plugin state.

    Returns:
        The dict to persist.
    """
    data = state.to_dict()
    data["transcript"] = transcript
    data["previous_state"] = previous_state
    data["engine_state"] = engine_state
    data["save_format_version"] = SAVE_FORMAT_VERSION
    return data


def read_saved_state(data: dict[str, Any]) -> dict[str, Any]:
    """Return `data` if this library can read it, else refuse.

    A save written before versioning carries no marker. Those are read as
    version 1, which is what they are: the marker was added without
    changing the shape.

    Args:
        data: A previously-saved envelope.

    Returns:
        The same dict, unchanged.

    Raises:
        SaveFormatError: The save is from a newer format than this
            library understands.
    """
    version = data.get("save_format_version", 1)
    if not isinstance(version, int) or version > SAVE_FORMAT_VERSION:
        raise SaveFormatError(
            f"this save is version {version!r}; this player reads up to {SAVE_FORMAT_VERSION}. A newer version is needed to open it."
        )
    return data


def append_transcript_entry(
    transcript: list[dict[str, object]],
    text: str,
    chosen_label: str | None,
    *,
    cap: int,
) -> list[dict[str, object]]:
    """Append one turn, dropping the oldest to stay within `cap`.

    Args:
        transcript: The existing transcript, oldest first.
        text: This turn's own text.
        chosen_label: The choice that led here, or None for the opening
            turn.
        cap: How many turns to keep. Passed in rather than read from a
            module constant, so how long a transcript runs stays the
            embedding application's decision.

    Returns:
        A new list; the argument is not mutated.
    """
    updated: list[dict[str, object]] = [*transcript, {"text": text, "chosen_label": chosen_label}]
    if 0 < cap < len(updated):
        updated = updated[-cap:]
    return updated


def turn_context(
    state: StoryEngine,
    *,
    resolver: MediaResolver,
    transcript: list[dict[str, object]] | None = None,
    can_undo: bool = False,
) -> dict[str, Any]:
    """Build one turn's display context.

    This dict is the contract between a story engine and every application UI. A
    application adds its own keys on top -- QuickBBS layers `story` and `user`
    for its templates -- but the seven below mean the same thing
    everywhere.

    Args:
        state: The story engine, already advanced to this turn.
        resolver: Turns this turn's tags into displayable references. A
            Protocol, so a filesystem application and a database application inject
            their own without forking this function.
        transcript: The rolling history, or None for none.
        can_undo: Whether an undo target exists.

    Returns:
        `{text, choices, done, turn_count, image_urls, transcript,
        can_undo}`. Each choice is `{index, text, image_urls}` -- a dict
        rather than a pair, because a choice can carry its own pictures
        (standard Ink choice tags, which is how a game asks the player to
        pick a character by appearance).
    """
    return {
        "text": state.last_turn_text,
        "choices": [
            {
                "index": index,
                "text": choice.text,
                "image_urls": resolver.resolve(parse_media_tags(getattr(choice, "tags", []))),
            }
            for index, choice in enumerate(state.current_choices)
        ],
        "done": state.done and not state.current_choices,
        "turn_count": state.turn_count,
        "image_urls": resolver.resolve(parse_media_tags(state.current_tags)),
        "transcript": transcript or [],
        "can_undo": can_undo,
    }
