"""Tests for `GameSavesDirectory`, the pre-supplied file-backed solution.

The logic above it is proven against an in-memory fake in
`test_game_saves.py`. These cover what only a real filesystem can: the
on-disk layout, directory creation, unreadable files, and the game-id
validation that keeps a save inside its own directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from if_session.game_saves import (
    QUICKSAVE_SLOT,
    GameSavesDirectory,
    GameSaveError,
    GameSavesProtocol,
    has_quicksave,
    list_game_saves,
    load_game_save,
    quickload,
    quicksave,
    save_game,
)
from if_session.session_state import SAVE_FORMAT_VERSION

MAX_SLOTS = 5
GAME = "thehauntedhouse"
WHEN = "2026-09-16T12:00:00Z"


@pytest.fixture(name="game_saves_directory")
def fixture_game_saves_directory(tmp_path: Path) -> GameSavesDirectory:
    return GameSavesDirectory(tmp_path / "saves")


def a_state(turn_count: int = 7) -> dict[str, Any]:
    return {"turn_count": turn_count, "save_format_version": SAVE_FORMAT_VERSION}


def test_it_satisfies_the_protocol(tmp_path: Path) -> None:
    assert isinstance(GameSavesDirectory(tmp_path), GameSavesProtocol)


class TestOnDiskLayout:
    def test_a_save_lands_in_the_games_own_directory(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert (tmp_path / "saves" / GAME / "gamesave0.json").is_file()

    def test_each_slot_is_its_own_file(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        for slot in range(3):
            save_game(GAME, slot, a_state(), f"Save {slot}", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        written = sorted(p.name for p in (tmp_path / "saves" / GAME).iterdir())
        assert written == ["gamesave0.json", "gamesave1.json", "gamesave2.json"]

    def test_the_quicksave_has_its_own_name(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        """Not `gamesave-1.json`, which reads as a mistake."""
        quicksave(GAME, a_state(), saves_in=game_saves_directory, saved_at=WHEN)
        assert (tmp_path / "saves" / GAME / "quicksave.json").is_file()

    def test_each_game_gets_its_own_directory(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        save_game("one", 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        save_game("two", 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert sorted(p.name for p in (tmp_path / "saves").iterdir()) == ["one", "two"]

    def test_the_file_is_readable_json_holding_the_game_save(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        save_game(GAME, 0, a_state(turn_count=12), "Readable", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        written = json.loads((tmp_path / "saves" / GAME / "gamesave0.json").read_text(encoding="utf-8"))
        assert written == {
            "gamesave_slot": 0,
            "label": "Readable",
            "saved_at": WHEN,
            "turn_count": 12,
            "game_build": "",
            "state": a_state(turn_count=12),
        }


class TestDirectoryCreation:
    def test_the_directory_is_created_on_demand(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        """The caller never calls mkdir; that is the point of this class."""
        assert not (tmp_path / "saves").exists()
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert (tmp_path / "saves" / GAME).is_dir()

    def test_missing_intermediate_directories_are_created(self, tmp_path: Path) -> None:
        game_saves_directory = GameSavesDirectory(tmp_path / "deeply" / "nested" / "saves")
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert (tmp_path / "deeply" / "nested" / "saves" / GAME / "gamesave0.json").is_file()

    def test_a_string_path_works_as_well_as_a_path(self, tmp_path: Path) -> None:
        game_saves_directory = GameSavesDirectory(str(tmp_path / "saves"))  # type: ignore[arg-type]
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert (tmp_path / "saves" / GAME / "gamesave0.json").is_file()


class TestGameIdValidation:
    """A game id becomes a directory name, so it must stay one segment.

    `if_player` is safe today only because `game_identity()` is its sole
    producer. A solution offered to any caller has no such guarantee, so
    it refuses rather than silently sanitizing -- two games quietly
    sharing a directory is worse than an error.
    """

    @pytest.mark.parametrize(
        "bad_id",
        ["../escape", "../../etc", "/etc/passwd", ".", "..", "", "a/b", "a\\b", "with space", "semi;colon"],
        ids=["parent", "traversal", "absolute", "dot", "dotdot", "empty", "slash", "backslash", "space", "punctuation"],
    )
    def test_an_unusable_game_id_is_refused(self, game_saves_directory: GameSavesDirectory, bad_id: str) -> None:
        with pytest.raises(GameSaveError, match="not a usable folder name"):
            save_game(bad_id, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    def test_a_refused_game_id_writes_nothing_anywhere(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        with pytest.raises(GameSaveError):
            save_game("../escape", 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert list(tmp_path.rglob("*.json")) == []

    @pytest.mark.parametrize(
        "good_id",
        ["thehauntedhouse", "the-haunted-house", "the_haunted_house", "game.v2", "UPPERCASE", "a1b2c3", "0"],
        ids=["plain", "hyphen", "underscore", "dot", "uppercase", "alphanumeric", "digit"],
    )
    def test_an_ordinary_folder_name_is_accepted(self, game_saves_directory: GameSavesDirectory, good_id: str) -> None:
        save_game(good_id, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert load_game_save(good_id, 0, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS) == a_state()

    def test_reading_an_unusable_game_id_is_refused_too(self, game_saves_directory: GameSavesDirectory) -> None:
        """Not only the write path, or a read could still escape."""
        with pytest.raises(GameSaveError, match="not a usable folder name"):
            load_game_save("../escape", 0, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS)


class TestUnreadableFiles:
    """A damaged file reads as an empty slot, never an exception.

    This preserves `if_player`'s existing tested behaviour: a corrupt
    save must not stop the save menu from rendering.
    """

    def _write_raw(self, tmp_path: Path, name: str, contents: str) -> None:
        directory = tmp_path / "saves" / GAME
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(contents, encoding="utf-8")

    @pytest.mark.parametrize(
        "contents",
        ["{not json", "", "null", "[1, 2, 3]", '"a string"', "42"],
        ids=["malformed", "empty", "null", "list", "string", "number"],
    )
    def test_an_unreadable_file_reads_as_an_empty_slot(
        self, game_saves_directory: GameSavesDirectory, tmp_path: Path, contents: str
    ) -> None:
        self._write_raw(tmp_path, "gamesave0.json", contents)
        assert game_saves_directory.read_game_save(GAME, 0) is None

    def test_an_unreadable_file_is_listed_as_unused(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        self._write_raw(tmp_path, "gamesave0.json", "{not json")
        assert list_game_saves(GAME, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS)[0]["used"] is False

    def test_one_unreadable_file_does_not_hide_the_others(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        save_game(GAME, 1, a_state(), "Fine", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        self._write_raw(tmp_path, "gamesave0.json", "{not json")
        listing = list_game_saves(GAME, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS)
        assert listing[0]["used"] is False
        assert listing[1]["used"] is True

    def test_a_quicksave_holding_no_state_is_refused_cleanly(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        """The `if_player` defect, against a real file this time.

        `save_slots_api.py:383` indexed `envelope["state"]` bare, so this
        raised KeyError out of a layer documented as never raising.
        """
        self._write_raw(tmp_path, "quicksave.json", json.dumps({"label": "Quicksave"}))
        with pytest.raises(GameSaveError, match="damaged"):
            quickload(GAME, saves_in=game_saves_directory)

    def test_an_unrelated_json_file_is_ignored_by_the_listing(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        self._write_raw(tmp_path, "notes.json", json.dumps({"whatever": True}))
        assert all(e["used"] is False for e in list_game_saves(GAME, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS))


class TestMissingDirectories:
    def test_listing_a_game_that_was_never_saved_is_empty_not_an_error(self, game_saves_directory: GameSavesDirectory) -> None:
        listing = list_game_saves("neverplayed", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS)
        assert len(listing) == MAX_SLOTS
        assert all(entry["used"] is False for entry in listing)

    def test_summarizing_a_missing_directory_is_empty(self, game_saves_directory: GameSavesDirectory) -> None:
        assert game_saves_directory.summarize_game_saves("neverplayed") == []

    def test_has_quicksave_is_false_with_no_directory(self, game_saves_directory: GameSavesDirectory) -> None:
        assert has_quicksave("neverplayed", saves_in=game_saves_directory) is False

    def test_deleting_from_a_missing_directory_is_not_an_error(self, game_saves_directory: GameSavesDirectory) -> None:
        game_saves_directory.delete_game_save("neverplayed", 0)


class TestQuicksaveOnDisk:
    def test_a_quicksave_round_trips(self, game_saves_directory: GameSavesDirectory) -> None:
        quicksave(GAME, a_state(turn_count=3), saves_in=game_saves_directory, saved_at=WHEN)
        assert quickload(GAME, saves_in=game_saves_directory)["turn_count"] == 3

    def test_it_does_not_appear_among_the_numbered_saves(self, game_saves_directory: GameSavesDirectory) -> None:
        quicksave(GAME, a_state(), saves_in=game_saves_directory, saved_at=WHEN)
        assert all(e["used"] is False for e in list_game_saves(GAME, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS))

    def test_it_does_not_overwrite_a_numbered_save(self, game_saves_directory: GameSavesDirectory) -> None:
        save_game(GAME, 0, a_state(turn_count=1), "Mine", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        quicksave(GAME, a_state(turn_count=2), saves_in=game_saves_directory, saved_at=WHEN)
        assert load_game_save(GAME, 0, saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 1

    def test_has_quicksave_does_not_parse_the_file(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        """It answers from existence, so even a damaged file counts."""
        directory = tmp_path / "saves" / GAME
        directory.mkdir(parents=True)
        (directory / "quicksave.json").write_text("{not json", encoding="utf-8")
        assert has_quicksave(GAME, saves_in=game_saves_directory) is True


class TestDeletion:
    def test_a_deleted_file_is_gone_from_disk(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        game_saves_directory.delete_game_save(GAME, 0)
        assert not (tmp_path / "saves" / GAME / "gamesave0.json").exists()

    def test_deleting_the_quicksave_targets_its_own_file(self, game_saves_directory: GameSavesDirectory, tmp_path: Path) -> None:
        quicksave(GAME, a_state(), saves_in=game_saves_directory, saved_at=WHEN)
        save_game(GAME, 0, a_state(), "Keep", saves_in=game_saves_directory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        game_saves_directory.delete_game_save(GAME, QUICKSAVE_SLOT)
        assert not (tmp_path / "saves" / GAME / "quicksave.json").exists()
        assert (tmp_path / "saves" / GAME / "gamesave0.json").is_file()
