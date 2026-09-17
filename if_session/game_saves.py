"""One definition of game saves, labels, export envelopes and quicksave.

An application needs more than a save's contents: numbered save slots, a
label for each, a portable file to export, validation of one a player
brings back, and a quicksave. That work was written twice -- once in the
desktop player, once in the web application -- and the two copies
diverged while both claimed to write version 1, so neither could read the
other's files.

This module owns that work; an application supplies only storage, through
`GameSavesProtocol`. `GameSavesDirectory` is a working implementation for an
application that has no storage opinion of its own.

Nothing here reads a clock or touches a story engine. `saved_at` is passed
in, and the saved state is an opaque dict.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from if_session.session_state import SaveFormatError, read_saved_state

#: The export envelope's own version, bumped when its shape changes. The
#: state inside carries its own separate `save_format_version`: this one
#: names the export file's format, that one names the saved session.
SAVE_ENVELOPE_VERSION = 1

#: The quicksave's save slot number. Negative, so it is outside every
#: numbered range and the ordinary `0 <= gamesave_slot < maximum_gamesave_slots`
#: check rejects it for free wherever a player save slot is expected.
QUICKSAVE_SLOT = -1

#: The label a quicksave carries, since the player is never asked for one.
QUICKSAVE_LABEL = "Quicksave"

#: How many characters of a player-supplied label to keep.
DEFAULT_LABEL_CHARACTER_LIMIT = 100

#: A `game_id` `GameSavesDirectory` will use as a directory name.
_SAFE_GAME_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class GameSaveError(Exception):
    """A user-facing problem with a game save operation."""


@runtime_checkable
class GameSavesProtocol(Protocol):
    """Where an application keeps its game saves.

    Game saves are plain JSON-ready dicts rather than bytes, so a database
    application can hand its column straight back without serializing and
    re-parsing. A file application does its own `json.dumps` inside
    `write_game_save`.

    `game_id` partitions the saves. Its meaning is the application's --
    a folder name, a bundle digest, a story slug -- and this module never
    interprets it.
    """

    def read_game_save(self, game_id: str, gamesave_slot: int) -> dict[str, Any] | None:
        """Return the game save in `gamesave_slot`, or None when empty.

        Storage that cannot be read answers None as well: an unreadable
        save slot reads as an empty one rather than raising.
        """

    def write_game_save(self, game_id: str, game_save: dict[str, Any]) -> None:
        """Write `game_save`, replacing whatever its slot held."""

    def delete_game_save(self, game_id: str, gamesave_slot: int) -> None:
        """Delete `gamesave_slot`. Deleting an empty slot is not an error."""

    def game_save_exists(self, game_id: str, gamesave_slot: int) -> bool:
        """Return whether `gamesave_slot` holds a game save.

        Separate from `read_game_save` so answering it need not load a
        state blob -- the question a quicksave button asks every turn.
        """

    def summarize_game_saves(self, game_id: str) -> list[dict[str, Any]]:
        """Return a summary per OCCUPIED save slot.

        Each is `{gamesave_slot, label, saved_at, turn_count, game_build}`,
        excluding the quicksave. No state blobs, so a database can answer from the
        small columns alone.
        """


class GameSavesDirectory:
    """Game saves as JSON files under a game's own directory.

    The default for an application with no storage opinion: point it at a
    directory and saving works, with no file handling of its own. An
    application that needs somewhere else -- a database, a cloud bucket --
    implements `GameSavesProtocol` instead.
    """

    def __init__(self, saves_directory: Path) -> None:
        """Keep game saves beneath `saves_directory`, created on demand."""
        self.saves_directory = Path(saves_directory)

    def _game_save_path(self, game_id: str, gamesave_slot: int) -> Path:
        """Return one save slot's own file path.

        Raises:
            GameSaveError: `game_id` is not usable as a directory name.
        """
        if not _SAFE_GAME_ID.match(game_id) or game_id in {".", ".."}:
            raise GameSaveError(f"Game id {game_id!r} is not a usable folder name")
        name = "quicksave.json" if gamesave_slot == QUICKSAVE_SLOT else f"gamesave{gamesave_slot}.json"
        return self.saves_directory / game_id / name

    def read_game_save(self, game_id: str, gamesave_slot: int) -> dict[str, Any] | None:
        """Return the game save, or None when empty or unreadable."""
        path = self._game_save_path(game_id, gamesave_slot)
        try:
            game_save = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        return game_save if isinstance(game_save, dict) else None

    def write_game_save(self, game_id: str, game_save: dict[str, Any]) -> None:
        """Write `game_save` as JSON, creating the game's directory."""
        path = self._game_save_path(game_id, game_save["gamesave_slot"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(game_save), encoding="utf-8")

    def delete_game_save(self, game_id: str, gamesave_slot: int) -> None:
        """Delete this save slot's file if it exists."""
        self._game_save_path(game_id, gamesave_slot).unlink(missing_ok=True)

    def game_save_exists(self, game_id: str, gamesave_slot: int) -> bool:
        """Return whether this save slot's file exists, without parsing it."""
        return self._game_save_path(game_id, gamesave_slot).is_file()

    def summarize_game_saves(self, game_id: str) -> list[dict[str, Any]]:
        """Return a summary per occupied numbered save slot, lowest first."""
        directory = self._game_save_path(game_id, 0).parent
        summaries: list[dict[str, Any]] = []
        for path in sorted(directory.glob("gamesave*.json")):
            try:
                game_save = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError):
                continue
            if isinstance(game_save, dict) and isinstance(game_save.get("gamesave_slot"), int):
                summaries.append(
                    {
                        "gamesave_slot": game_save["gamesave_slot"],
                        "label": game_save.get("label", ""),
                        "saved_at": game_save.get("saved_at"),
                        "turn_count": game_save.get("turn_count"),
                        "game_build": game_save.get("game_build", ""),
                    }
                )
        return sorted(summaries, key=lambda summary: summary["gamesave_slot"])


def is_from_another_build(game_save: dict[str, Any], game_build: str) -> bool:
    """Return whether this save was made by a different build of the game.

    A rebuilt game keeps its identity, so its saves still load. The story
    itself may have moved on underneath them, which an application warns
    about rather than refusing -- most such saves still play.

    Args:
        game_save: A stored game save, or an exported envelope.
        game_build: What `game_build()` answers for the game in hand.

    Returns:
        False when either side is unknown: a save written before builds
        were recorded cannot be judged, and guessing would warn about
        every old save.
    """
    recorded = game_save.get("game_build") or ""
    if not recorded or not game_build:
        return False
    return bool(recorded != game_build)


def _check_gamesave_slot(gamesave_slot: int, maximum_gamesave_slots: int) -> None:
    """Raise unless `gamesave_slot` is a valid player save slot.

    Raises:
        GameSaveError: `gamesave_slot` is outside
            `0..maximum_gamesave_slots-1`. The quicksave's own negative
            number fails here too, which is the point.
    """
    if not 0 <= gamesave_slot < maximum_gamesave_slots:
        raise GameSaveError(f"Save slot {gamesave_slot} is out of range (0-{maximum_gamesave_slots - 1})")


# pylint: disable=too-many-arguments
# A private composer of one record; each argument is a distinct field of
# that record. Removable if the record ever becomes a dataclass.
def _build_game_save(
    gamesave_slot: int,
    state: dict[str, Any],
    label: str,
    saved_at: str,
    label_character_limit: int,
    *,
    game_build: str = "",
) -> dict[str, Any]:
    """Return the game save an application persists for one save slot.

    `turn_count` is lifted out of `state` here so no application has to
    know where it lives. `state` is deep-copied: a save is a snapshot,
    and the caller goes on playing with the dict it passed in.
    """
    return {
        "gamesave_slot": gamesave_slot,
        "label": label[:label_character_limit],
        "saved_at": saved_at,
        "turn_count": state.get("turn_count"),
        "game_build": game_build,
        "state": copy.deepcopy(state),
    }


def _read_saved_game_state(game_id: str, gamesave_slot: int, *, saves_in: GameSavesProtocol) -> dict[str, Any]:
    """Return the state stored in one save slot, whatever its number.

    Shared by `load_game_save` and `quickload` so the quicksave gets the
    same guards a numbered save slot has.

    Raises:
        GameSaveError: The save slot is empty, or holds no state.
    """
    game_save = saves_in.read_game_save(game_id, gamesave_slot)
    if game_save is None:
        if gamesave_slot == QUICKSAVE_SLOT:
            raise GameSaveError("No quicksave exists")
        raise GameSaveError(f"Save slot {gamesave_slot} is empty")
    state = game_save.get("state")
    if not isinstance(state, dict):
        raise GameSaveError("This save is damaged and cannot be read")
    return read_saved_state(copy.deepcopy(state))


def list_game_saves(game_id: str, *, saves_in: GameSavesProtocol, maximum_gamesave_slots: int) -> list[dict[str, Any]]:
    """Return every numbered save slot, occupied or not, lowest first.

    Args:
        game_id: Which game's saves to list.
        saves_in: Where the game saves are kept.
        maximum_gamesave_slots: How many numbered save slots this
            application offers.

    Returns:
        Exactly `maximum_gamesave_slots` entries `{gamesave_slot, used,
        label, saved_at, turn_count, game_build}`. An empty save slot has `used`
        False and None for the rest. Dense, so a UI can render the list
        directly rather than filling the gaps itself.
    """
    occupied = {
        summary["gamesave_slot"]: summary
        for summary in saves_in.summarize_game_saves(game_id)
        if 0 <= summary["gamesave_slot"] < maximum_gamesave_slots
    }
    game_saves: list[dict[str, Any]] = []
    for gamesave_slot in range(maximum_gamesave_slots):
        summary = occupied.get(gamesave_slot)
        if summary is None:
            game_saves.append(
                {
                    "gamesave_slot": gamesave_slot,
                    "used": False,
                    "label": None,
                    "saved_at": None,
                    "turn_count": None,
                    "game_build": "",
                }
            )
        else:
            game_saves.append(
                {
                    "gamesave_slot": gamesave_slot,
                    "used": True,
                    "label": summary.get("label", ""),
                    "saved_at": summary.get("saved_at"),
                    "turn_count": summary.get("turn_count"),
                    "game_build": summary.get("game_build", ""),
                }
            )
    return game_saves


# pylint: disable=too-many-arguments
# Four of the eight are keyword-only injected collaborators, which is
# how this module avoids module-level state. Removable if the
# collaborators are ever grouped into one object.
def save_game(
    game_id: str,
    gamesave_slot: int,
    state: dict[str, Any],
    label: str,
    *,
    saves_in: GameSavesProtocol,
    maximum_gamesave_slots: int,
    saved_at: str,
    label_character_limit: int = DEFAULT_LABEL_CHARACTER_LIMIT,
    game_build: str = "",
) -> dict[str, Any]:
    """Snapshot `state` into one numbered save slot.

    A copy, not a live link: playing on afterward never changes this save
    until the next explicit save.

    Args:
        game_id: Which game's saves to write to.
        gamesave_slot: The save slot number to write.
        state: The full session state to store.
        label: The player's own label, truncated to
            `label_character_limit`.
        saves_in: Where the game saves are kept.
        maximum_gamesave_slots: How many numbered save slots this
            application offers.
        saved_at: When this save happened, ISO-8601.
        label_character_limit: How many characters of `label` to keep.

    Returns:
        The game save written.

    Raises:
        GameSaveError: `gamesave_slot` is outside the valid range.
    """
    _check_gamesave_slot(gamesave_slot, maximum_gamesave_slots)
    game_save = _build_game_save(gamesave_slot, state, label, saved_at, label_character_limit, game_build=game_build)
    saves_in.write_game_save(game_id, game_save)
    return game_save


def load_game_save(
    game_id: str,
    gamesave_slot: int,
    *,
    saves_in: GameSavesProtocol,
    maximum_gamesave_slots: int,
) -> dict[str, Any]:
    """Return one save slot's own state, ready to resume from.

    Loading never changes the save.

    Args:
        game_id: Which game's saves to read.
        gamesave_slot: The save slot number to read.
        saves_in: Where the game saves are kept.
        maximum_gamesave_slots: How many numbered save slots this
            application offers.

    Returns:
        The saved state dict.

    Raises:
        GameSaveError: `gamesave_slot` is out of range, empty, or damaged.
        SaveFormatError: The state is from a newer format than this
            library reads. Deliberately NOT wrapped: the save operation
            succeeded and the save is simply unreadable, which is a
            distinct situation an application shows differently.
    """
    _check_gamesave_slot(gamesave_slot, maximum_gamesave_slots)
    return _read_saved_game_state(game_id, gamesave_slot, saves_in=saves_in)


def delete_game_save(
    game_id: str,
    gamesave_slot: int,
    *,
    saves_in: GameSavesProtocol,
    maximum_gamesave_slots: int,
) -> None:
    """Empty one numbered save slot. Deleting an empty one does nothing.

    Raises:
        GameSaveError: `gamesave_slot` is outside the valid range.
    """
    _check_gamesave_slot(gamesave_slot, maximum_gamesave_slots)
    saves_in.delete_game_save(game_id, gamesave_slot)


def export_game_save(
    game_id: str,
    gamesave_slot: int,
    *,
    saves_in: GameSavesProtocol,
    maximum_gamesave_slots: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one game save as a portable envelope, ready to write to a file.

    Args:
        game_id: Which game's saves to read.
        gamesave_slot: The save slot number to export.
        saves_in: Where the game saves are kept.
        maximum_gamesave_slots: How many numbered save slots this
            application offers.
        metadata: Anything the application wants to record alongside the
            save. Opaque and advisory: it is never validated on import,
            and never restored, because it describes the installation
            that wrote the file rather than the save itself.

    Returns:
        `{if_save_version, game_id, label, saved_at, metadata, state}`.

    Raises:
        GameSaveError: `gamesave_slot` is out of range, empty, or damaged.
    """
    _check_gamesave_slot(gamesave_slot, maximum_gamesave_slots)
    game_save = saves_in.read_game_save(game_id, gamesave_slot)
    if game_save is None:
        raise GameSaveError(f"Save slot {gamesave_slot} is empty")
    state = game_save.get("state")
    if not isinstance(state, dict):
        raise GameSaveError("This save is damaged and cannot be read")
    return {
        "if_save_version": SAVE_ENVELOPE_VERSION,
        "game_id": game_id,
        "label": game_save.get("label", ""),
        "saved_at": game_save.get("saved_at"),
        "metadata": metadata or {},
        "game_build": game_save.get("game_build", ""),
        "state": state,
    }


# pylint: disable=too-many-arguments
# Four of the eight are keyword-only injected collaborators, which is
# how this module avoids module-level state. Removable if the
# collaborators are ever grouped into one object.
def import_game_save(
    game_id: str,
    gamesave_slot: int,
    envelope: object,
    *,
    saves_in: GameSavesProtocol,
    maximum_gamesave_slots: int,
    saved_at: str,
    label: str | None = None,
    label_character_limit: int = DEFAULT_LABEL_CHARACTER_LIMIT,
) -> dict[str, Any]:
    """Validate an exported envelope and write it into one save slot.

    Everything is checked before anything is written, so a save that
    cannot be read never overwrites one that could.

    Args:
        game_id: The game the envelope must name.
        gamesave_slot: The save slot number to write.
        envelope: A decoded JSON file, of unknown trustworthiness --
            typed `object` because validating it is this function's job.
        saves_in: Where the game saves are kept.
        maximum_gamesave_slots: How many numbered save slots this
            application offers.
        saved_at: When this import happened, ISO-8601.
        label: A label to use instead of the envelope's own.
        label_character_limit: How many characters of the label to keep.

    Returns:
        The game save written.

    Raises:
        GameSaveError: `gamesave_slot` is out of range, or the envelope is
            not a recognized save file, names a different game, or holds a
            state this application cannot read. A format problem is
            reported as an import failure, since that is what the player
            attempted; `load_game_save` makes the opposite choice.
    """
    _check_gamesave_slot(gamesave_slot, maximum_gamesave_slots)
    if not isinstance(envelope, dict) or envelope.get("if_save_version") != SAVE_ENVELOPE_VERSION:
        raise GameSaveError("Not a recognized save file")
    if envelope.get("game_id") != game_id:
        raise GameSaveError("This save file is from a different game")
    state = envelope.get("state")
    if not isinstance(state, dict):
        raise GameSaveError("Not a recognized save file")
    try:
        read_saved_state(state)
    except SaveFormatError as error:
        raise GameSaveError(str(error)) from error
    chosen_label = label if label is not None else str(envelope.get("label", ""))
    return save_game(
        game_id,
        gamesave_slot,
        state,
        chosen_label,
        saves_in=saves_in,
        maximum_gamesave_slots=maximum_gamesave_slots,
        saved_at=saved_at,
        label_character_limit=label_character_limit,
        # The file's own build, not this game's: the save is still from
        # whichever build made it, and that is what the caution compares.
        game_build=str(envelope.get("game_build", "")),
    )


def quicksave(
    game_id: str,
    state: dict[str, Any],
    *,
    saves_in: GameSavesProtocol,
    saved_at: str,
    game_build: str = "",
) -> dict[str, Any]:
    """Snapshot `state` into the one quicksave, replacing any previous one.

    Never touches a numbered save slot.

    Returns:
        The game save written.
    """
    game_save = _build_game_save(
        QUICKSAVE_SLOT,
        state,
        QUICKSAVE_LABEL,
        saved_at,
        DEFAULT_LABEL_CHARACTER_LIMIT,
        game_build=game_build,
    )
    saves_in.write_game_save(game_id, game_save)
    return game_save


def quickload(game_id: str, *, saves_in: GameSavesProtocol) -> dict[str, Any]:
    """Return the quicksave's own state, ready to resume from.

    Returns:
        The saved state dict.

    Raises:
        GameSaveError: There is no quicksave, or it is damaged.
        SaveFormatError: The state is from a newer format, as in
            `load_game_save`.
    """
    return _read_saved_game_state(game_id, QUICKSAVE_SLOT, saves_in=saves_in)


def has_quicksave(game_id: str, *, saves_in: GameSavesProtocol) -> bool:
    """Return whether this game has a quicksave to load."""
    return saves_in.game_save_exists(game_id, QUICKSAVE_SLOT)
