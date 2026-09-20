"""Tests for `if_session.game_saves`.

Everything here runs against `GameSavesInMemory`, an in-memory
implementation, so the pure logic is proven without a filesystem. The
pre-supplied `GameSavesDirectory` has its own tests in
`test_file_game_saves.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
from if_session.game_saves import (
    DEFAULT_LABEL_CHARACTER_LIMIT,
    QUICKSAVE_LABEL,
    QUICKSAVE_SLOT,
    SAVE_ENVELOPE_VERSION,
    GameSaveError,
    GameSavesProtocol,
    delete_game_save,
    export_game_save,
    has_quicksave,
    import_game_save,
    is_from_another_build,
    list_game_saves,
    load_game_save,
    quickload,
    quicksave,
    save_game,
)
from if_session.session_state import SAVE_FORMAT_VERSION, SaveFormatError

MAX_SLOTS = 5
GAME = "thehauntedhouse"
WHEN = "2026-09-16T12:00:00Z"


class GameSavesInMemory:
    """An in-memory implementation, for testing the logic above it."""

    def __init__(self) -> None:
        self.saves: dict[tuple[str, int], dict[str, Any]] = {}
        self.reads: list[tuple[str, int]] = []

    def read_game_save(self, game_id: str, gamesave_slot: int) -> dict[str, Any] | None:
        self.reads.append((game_id, gamesave_slot))
        return self.saves.get((game_id, gamesave_slot))

    def write_game_save(self, game_id: str, game_save: dict[str, Any]) -> None:
        self.saves[(game_id, game_save["gamesave_slot"])] = game_save

    def delete_game_save(self, game_id: str, gamesave_slot: int) -> None:
        self.saves.pop((game_id, gamesave_slot), None)

    def game_save_exists(self, game_id: str, gamesave_slot: int) -> bool:
        return (game_id, gamesave_slot) in self.saves

    def summarize_game_saves(self, game_id: str) -> list[dict[str, Any]]:
        return [
            {
                "gamesave_slot": save["gamesave_slot"],
                "label": save["label"],
                "saved_at": save["saved_at"],
                "turn_count": save["turn_count"],
                "game_build": save.get("game_build", ""),
            }
            for (stored_game, slot), save in sorted(self.saves.items())
            if stored_game == game_id and slot != QUICKSAVE_SLOT
        ]


@pytest.fixture(name="game_saves_in_memory")
def fixture_game_saves_in_memory() -> GameSavesInMemory:
    return GameSavesInMemory()


def a_state(turn_count: int = 7) -> dict[str, Any]:
    """Return a minimal session state the library will accept."""
    return {"turn_count": turn_count, "save_format_version": SAVE_FORMAT_VERSION}


def test_the_fake_satisfies_the_protocol() -> None:
    """The fake must be a real implementation, or these tests prove nothing."""
    assert isinstance(GameSavesInMemory(), GameSavesProtocol)


class TestSaveGame:
    def test_a_saved_game_can_be_loaded_back(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "Before the bridge", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS) == a_state()

    def test_the_game_save_carries_every_documented_field(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = save_game(
            GAME, 2, a_state(turn_count=41), "Mid-game", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN
        )
        assert written == {
            "gamesave_slot": 2,
            "label": "Mid-game",
            "saved_at": WHEN,
            "turn_count": 41,
            "game_build": "",
            "state": a_state(turn_count=41),
        }

    def test_turn_count_is_lifted_out_of_the_state(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """No implementation should have to know where turn_count lives."""
        written = save_game(GAME, 0, a_state(turn_count=99), "x", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert written["turn_count"] == 99

    def test_a_state_without_a_turn_count_saves_with_none(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = save_game(
            GAME,
            0,
            {"save_format_version": SAVE_FORMAT_VERSION},
            "x",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
        )
        assert written["turn_count"] is None

    def test_a_long_label_is_truncated(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = save_game(GAME, 0, a_state(), "x" * 500, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert len(written["label"]) == DEFAULT_LABEL_CHARACTER_LIMIT

    def test_the_label_limit_can_be_lowered(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = save_game(
            GAME,
            0,
            a_state(),
            "x" * 50,
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            label_character_limit=10,
        )
        assert written["label"] == "x" * 10

    def test_saving_again_replaces_the_previous_save(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 1, a_state(turn_count=1), "First", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        save_game(GAME, 1, a_state(turn_count=2), "Second", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert load_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 2

    def test_saving_is_a_snapshot_not_a_live_link(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """Playing on after a save must not change what the save holds."""
        live = a_state(turn_count=5)
        save_game(GAME, 0, live, "Snapshot", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        live["turn_count"] = 6
        assert load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 5

    def test_games_do_not_share_save_slots(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game("one", 0, a_state(turn_count=1), "A", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        save_game("two", 0, a_state(turn_count=2), "B", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert load_game_save("one", 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 1

    @pytest.mark.parametrize("bad_slot", [-1, 5, 99, QUICKSAVE_SLOT])
    def test_an_out_of_range_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory, bad_slot: int) -> None:
        with pytest.raises(GameSaveError, match="out of range"):
            save_game(GAME, bad_slot, a_state(), "x", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    def test_an_out_of_range_save_writes_nothing(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError):
            save_game(GAME, 9, a_state(), "x", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert game_saves_in_memory.saves == {}


class TestLoadGameSave:
    def test_an_empty_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="is empty"):
            load_game_save(GAME, 3, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_an_out_of_range_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="out of range"):
            load_game_save(GAME, 9, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_a_game_save_holding_no_state_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """A truncated or hand-edited save must not raise KeyError.

        This is the `if_player` quickload defect, guarded at the shared
        level so neither application can reintroduce it.
        """
        game_saves_in_memory.saves[(GAME, 0)] = {"gamesave_slot": 0, "label": "x", "saved_at": WHEN, "turn_count": None}
        with pytest.raises(GameSaveError, match="damaged"):
            load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_a_state_that_is_not_a_dict_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        game_saves_in_memory.saves[(GAME, 0)] = {"gamesave_slot": 0, "label": "", "saved_at": WHEN, "turn_count": 1, "state": "nope"}
        with pytest.raises(GameSaveError, match="damaged"):
            load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_a_future_format_propagates_rather_than_being_wrapped(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """Loading must NOT wrap SaveFormatError; importing must.

        The save operation succeeded and the state is merely unreadable,
        which an application shows with its own dedicated UI.
        """
        game_saves_in_memory.saves[(GAME, 0)] = {
            "gamesave_slot": 0,
            "label": "",
            "saved_at": WHEN,
            "turn_count": 1,
            "state": {"save_format_version": SAVE_FORMAT_VERSION + 1},
        }
        with pytest.raises(SaveFormatError):
            load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_loading_does_not_change_the_save(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "Keep", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        before = dict(game_saves_in_memory.saves[(GAME, 0)])
        load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert game_saves_in_memory.saves[(GAME, 0)] == before


class TestListGameSaves:
    def test_the_listing_is_dense_even_when_empty(self, game_saves_in_memory: GameSavesInMemory) -> None:
        listing = list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert [entry["gamesave_slot"] for entry in listing] == [0, 1, 2, 3, 4]
        assert all(entry["used"] is False for entry in listing)

    def test_an_empty_slot_reports_none_for_everything_else(self, game_saves_in_memory: GameSavesInMemory) -> None:
        entry = list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)[0]
        assert entry == {
            "gamesave_slot": 0,
            "used": False,
            "label": None,
            "saved_at": None,
            "turn_count": None,
            "game_build": "",
        }

    def test_an_occupied_slot_reports_its_own_summary(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 2, a_state(turn_count=12), "Here", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        entry = list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)[2]
        assert entry == {
            "gamesave_slot": 2,
            "used": True,
            "label": "Here",
            "saved_at": WHEN,
            "turn_count": 12,
            "game_build": "",
        }

    def test_gaps_stay_in_place(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "A", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        save_game(GAME, 4, a_state(), "E", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert [e["used"] for e in list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)] == [
            True,
            False,
            False,
            False,
            True,
        ]

    def test_the_quicksave_never_appears(self, game_saves_in_memory: GameSavesInMemory) -> None:
        quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        listing = list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert len(listing) == MAX_SLOTS
        assert all(entry["used"] is False for entry in listing)

    def test_a_save_beyond_the_current_maximum_is_not_listed(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """Lowering the maximum must not surface a slot the UI cannot address."""
        save_game(GAME, 4, a_state(), "High", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        listing = list_game_saves(GAME, saves_in=game_saves_in_memory, maximum_gamesave_slots=3)
        assert len(listing) == 3
        assert all(entry["used"] is False for entry in listing)


class TestDeleteGameSave:
    def test_a_deleted_slot_reads_as_empty(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 1, a_state(), "Gone", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        delete_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        with pytest.raises(GameSaveError, match="is empty"):
            load_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_deleting_an_empty_slot_is_not_an_error(self, game_saves_in_memory: GameSavesInMemory) -> None:
        delete_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_deleting_leaves_the_other_slots_alone(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "Keep", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        save_game(GAME, 1, a_state(), "Drop", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        delete_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS) == a_state()

    def test_an_out_of_range_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="out of range"):
            delete_game_save(GAME, 9, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)


class TestExportGameSave:
    def test_the_envelope_carries_every_documented_key(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "Exported", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        envelope = export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert envelope == {
            "if_save_version": SAVE_ENVELOPE_VERSION,
            "game_id": GAME,
            "label": "Exported",
            "saved_at": WHEN,
            "metadata": {},
            "game_build": "",
            "state": a_state(),
        }

    def test_metadata_is_carried_verbatim(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "x", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        envelope = export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, metadata={"ink_version": "21"})
        assert envelope["metadata"] == {"ink_version": "21"}

    def test_an_empty_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="is empty"):
            export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_a_damaged_save_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        game_saves_in_memory.saves[(GAME, 0)] = {"gamesave_slot": 0, "label": "x", "saved_at": WHEN, "turn_count": None}
        with pytest.raises(GameSaveError, match="damaged"):
            export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

    def test_an_out_of_range_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="out of range"):
            export_game_save(GAME, 9, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)


class TestImportGameSave:
    def an_envelope(self, **overrides: Any) -> dict[str, Any]:
        envelope = {
            "if_save_version": SAVE_ENVELOPE_VERSION,
            "game_id": GAME,
            "label": "From a file",
            "saved_at": WHEN,
            "metadata": {},
            "game_build": "",
            "state": a_state(),
        }
        envelope.update(overrides)
        return envelope

    def test_a_valid_envelope_is_written(self, game_saves_in_memory: GameSavesInMemory) -> None:
        import_game_save(
            GAME, 3, self.an_envelope(), saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at="2026-09-16T13:00:00Z"
        )
        assert load_game_save(GAME, 3, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS) == a_state()

    def test_the_import_time_is_recorded_not_the_export_time(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = import_game_save(
            GAME, 0, self.an_envelope(), saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at="2026-09-16T13:00:00Z"
        )
        assert written["saved_at"] == "2026-09-16T13:00:00Z"

    def test_the_envelopes_own_label_is_used_by_default(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = import_game_save(GAME, 0, self.an_envelope(), saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        assert written["label"] == "From a file"

    def test_a_supplied_label_overrides_the_envelopes(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """QuickBBS posts a label alongside the file; that one must win."""
        written = import_game_save(
            GAME,
            0,
            self.an_envelope(),
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            label="My own name",
        )
        assert written["label"] == "My own name"

    def test_an_empty_supplied_label_still_overrides(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """An empty string is a choice; only None means 'use the envelope'."""
        written = import_game_save(
            GAME,
            0,
            self.an_envelope(),
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            label="",
        )
        assert written["label"] == ""

    def test_a_long_label_is_truncated(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = import_game_save(
            GAME,
            0,
            self.an_envelope(label="y" * 500),
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
        )
        assert len(written["label"]) == DEFAULT_LABEL_CHARACTER_LIMIT

    @pytest.mark.parametrize(
        "envelope",
        ["not a dict", 42, None, [], {"if_save_version": 99}, {"if_save_version": None}, {}],
        ids=["string", "int", "none", "list", "wrong-version", "null-version", "empty"],
    )
    def test_an_unrecognized_file_is_refused(self, game_saves_in_memory: GameSavesInMemory, envelope: object) -> None:
        with pytest.raises(GameSaveError, match="Not a recognized save file"):
            import_game_save(GAME, 0, envelope, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    def test_a_save_from_another_game_is_refused_by_name(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="different game"):
            import_game_save(
                GAME,
                0,
                self.an_envelope(game_id="someothergame"),
                saves_in=game_saves_in_memory,
                maximum_gamesave_slots=MAX_SLOTS,
                saved_at=WHEN,
            )

    def test_a_missing_state_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        envelope = self.an_envelope()
        del envelope["state"]
        with pytest.raises(GameSaveError, match="Not a recognized save file"):
            import_game_save(GAME, 0, envelope, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    def test_a_future_format_is_wrapped_as_an_import_failure(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """Importing wraps SaveFormatError; loading does not."""
        envelope = self.an_envelope(state={"save_format_version": SAVE_FORMAT_VERSION + 1})
        with pytest.raises(GameSaveError):
            import_game_save(GAME, 0, envelope, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    def test_an_out_of_range_slot_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="out of range"):
            import_game_save(GAME, 9, self.an_envelope(), saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)

    @pytest.mark.parametrize(
        "bad",
        ["not a dict", {"if_save_version": 99}, {"if_save_version": SAVE_ENVELOPE_VERSION, "game_id": "other"}],
        ids=["not-a-dict", "wrong-version", "wrong-game"],
    )
    def test_a_rejected_import_leaves_the_existing_save_intact(self, game_saves_in_memory: GameSavesInMemory, bad: object) -> None:
        """The whole point of validating before writing."""
        save_game(GAME, 1, a_state(turn_count=42), "Precious", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        with pytest.raises(GameSaveError):
            import_game_save(GAME, 1, bad, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at="later")
        assert game_saves_in_memory.saves[(GAME, 1)]["label"] == "Precious"
        assert load_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 42


class TestRoundTrip:
    def test_export_delete_import_into_another_slot_preserves_the_state(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """The test neither application had, and the one that would have
        caught the game_name/story_slug divergence."""
        original = a_state(turn_count=33)
        save_game(GAME, 0, original, "Original", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        envelope = export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        delete_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)

        import_game_save(GAME, 4, envelope, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at="2026-09-16T14:00:00Z")
        assert load_game_save(GAME, 4, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS) == original

    def test_a_reexported_save_matches_except_for_its_new_slot_metadata(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(), "Original", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        first = export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        import_game_save(GAME, 1, first, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        second = export_game_save(GAME, 1, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert first == second


class TestQuicksave:
    def test_a_quicksave_can_be_loaded_back(self, game_saves_in_memory: GameSavesInMemory) -> None:
        quicksave(GAME, a_state(turn_count=3), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert quickload(GAME, saves_in=game_saves_in_memory)["turn_count"] == 3

    def test_it_carries_its_own_label_and_time(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert written["label"] == QUICKSAVE_LABEL
        assert written["saved_at"] == WHEN

    def test_it_lands_in_the_reserved_slot(self, game_saves_in_memory: GameSavesInMemory) -> None:
        written = quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert written["gamesave_slot"] == QUICKSAVE_SLOT

    def test_quicksaving_again_replaces_the_previous_one(self, game_saves_in_memory: GameSavesInMemory) -> None:
        quicksave(GAME, a_state(turn_count=1), saves_in=game_saves_in_memory, saved_at=WHEN)
        quicksave(GAME, a_state(turn_count=2), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert quickload(GAME, saves_in=game_saves_in_memory)["turn_count"] == 2

    def test_it_never_touches_a_numbered_slot(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(turn_count=1), "Mine", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        quicksave(GAME, a_state(turn_count=2), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 1

    def test_quickloading_with_no_quicksave_says_so(self, game_saves_in_memory: GameSavesInMemory) -> None:
        with pytest.raises(GameSaveError, match="No quicksave exists"):
            quickload(GAME, saves_in=game_saves_in_memory)

    def test_a_quicksave_holding_no_state_is_refused(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """The exact `if_player` defect: valid JSON with no state key."""
        game_saves_in_memory.saves[(GAME, QUICKSAVE_SLOT)] = {"gamesave_slot": QUICKSAVE_SLOT, "label": QUICKSAVE_LABEL}
        with pytest.raises(GameSaveError, match="damaged"):
            quickload(GAME, saves_in=game_saves_in_memory)

    def test_has_quicksave_is_false_before_and_true_after(self, game_saves_in_memory: GameSavesInMemory) -> None:
        assert has_quicksave(GAME, saves_in=game_saves_in_memory) is False
        quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert has_quicksave(GAME, saves_in=game_saves_in_memory) is True

    def test_has_quicksave_does_not_read_the_state(self, game_saves_in_memory: GameSavesInMemory) -> None:
        """It must answer from existence alone, not by loading a blob."""
        quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        game_saves_in_memory.reads.clear()
        has_quicksave(GAME, saves_in=game_saves_in_memory)
        assert game_saves_in_memory.reads == []

    def test_one_games_quicksave_is_not_anothers(self, game_saves_in_memory: GameSavesInMemory) -> None:
        quicksave("one", a_state(), saves_in=game_saves_in_memory, saved_at=WHEN)
        assert has_quicksave("two", saves_in=game_saves_in_memory) is False


class TestSnapshotIsolation:
    """A save is a copy in both directions, whatever the implementation.

    A file-backed implementation gets this free from `json.dumps`; an
    in-memory or ORM-backed one does not, so the library owns it.
    """

    def test_playing_on_after_saving_does_not_change_the_save(self, game_saves_in_memory: GameSavesInMemory) -> None:
        live = a_state(turn_count=5)
        save_game(GAME, 0, live, "Snapshot", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        live["turn_count"] = 6
        live.setdefault("engine_state", {})["added"] = True
        loaded = load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert loaded["turn_count"] == 5
        assert "engine_state" not in loaded

    def test_mutating_a_loaded_state_does_not_change_the_save(self, game_saves_in_memory: GameSavesInMemory) -> None:
        save_game(GAME, 0, a_state(turn_count=5), "Snapshot", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        loaded = load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        loaded["turn_count"] = 999
        assert load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)["turn_count"] == 5

    def test_a_quicksave_is_isolated_the_same_way(self, game_saves_in_memory: GameSavesInMemory) -> None:
        live = a_state(turn_count=1)
        quicksave(GAME, live, saves_in=game_saves_in_memory, saved_at=WHEN)
        live["turn_count"] = 2
        assert quickload(GAME, saves_in=game_saves_in_memory)["turn_count"] == 1

    def test_a_nested_structure_is_copied_not_shared(self, game_saves_in_memory: GameSavesInMemory) -> None:
        live: dict[str, Any] = {
            "turn_count": 1,
            "save_format_version": SAVE_FORMAT_VERSION,
            "engine_state": {"inventory": ["lantern"]},
        }
        save_game(GAME, 0, live, "Nested", saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS, saved_at=WHEN)
        live["engine_state"]["inventory"].append("rope")
        loaded = load_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert loaded["engine_state"]["inventory"] == ["lantern"]


class TestBuildComparison:
    """A rebuilt game keeps its saves; the caution says they are older.

    `game_identity()` no longer changes when a game is rebuilt, so a
    corrected typo does not orphan every save. The recorded build is what
    tells one build from another.
    """

    def test_a_save_records_the_build_that_made_it(self, game_saves_in_memory: FakeGameSaves) -> None:
        written = save_game(
            GAME,
            0,
            a_state(),
            "x",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="aaaa1111",
        )
        assert written["game_build"] == "aaaa1111"

    def test_the_same_build_is_not_flagged(self, game_saves_in_memory: FakeGameSaves) -> None:
        written = save_game(
            GAME,
            0,
            a_state(),
            "x",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="aaaa1111",
        )
        assert is_from_another_build(written, "aaaa1111") is False

    def test_a_different_build_is_flagged(self, game_saves_in_memory: FakeGameSaves) -> None:
        written = save_game(
            GAME,
            0,
            a_state(),
            "x",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="aaaa1111",
        )
        assert is_from_another_build(written, "bbbb2222") is True

    def test_a_save_from_before_builds_were_recorded_is_not_flagged(self) -> None:
        """Guessing would caution about every pre-existing save."""
        assert is_from_another_build({"label": "old"}, "aaaa1111") is False

    def test_an_unknown_current_build_is_not_flagged(self) -> None:
        """A directory game has no build; comparison means nothing there."""
        assert is_from_another_build({"game_build": "aaaa1111"}, "") is False

    def test_a_quicksave_records_its_build_too(self, game_saves_in_memory: FakeGameSaves) -> None:
        written = quicksave(GAME, a_state(), saves_in=game_saves_in_memory, saved_at=WHEN, game_build="aaaa1111")
        assert is_from_another_build(written, "bbbb2222") is True

    def test_an_exported_file_carries_the_build(self, game_saves_in_memory: FakeGameSaves) -> None:
        save_game(
            GAME,
            0,
            a_state(),
            "x",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="aaaa1111",
        )
        envelope = export_game_save(GAME, 0, saves_in=game_saves_in_memory, maximum_gamesave_slots=MAX_SLOTS)
        assert envelope["game_build"] == "aaaa1111"

    def test_an_imported_save_keeps_the_build_that_made_it(self, game_saves_in_memory: FakeGameSaves) -> None:
        """Importing copies a file; it does not re-make the save."""
        envelope = {
            "if_save_version": SAVE_ENVELOPE_VERSION,
            "game_id": GAME,
            "label": "From a file",
            "saved_at": WHEN,
            "metadata": {},
            "game_build": "aaaa1111",
            "state": a_state(),
        }
        written = import_game_save(
            GAME,
            0,
            envelope,
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at="2026-09-16T13:00:00Z",
        )
        assert written["game_build"] == "aaaa1111"
        assert is_from_another_build(written, "bbbb2222") is True

    def test_saving_again_brings_a_slot_up_to_date(self, game_saves_in_memory: FakeGameSaves) -> None:
        """The repair the caution tells a player about."""
        save_game(
            GAME,
            0,
            a_state(),
            "old",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="aaaa1111",
        )
        written = save_game(
            GAME,
            0,
            a_state(),
            "new",
            saves_in=game_saves_in_memory,
            maximum_gamesave_slots=MAX_SLOTS,
            saved_at=WHEN,
            game_build="bbbb2222",
        )
        assert is_from_another_build(written, "bbbb2222") is False
