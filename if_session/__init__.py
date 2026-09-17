"""The session library: what an application needs around a story engine.

A story engine answers what the story does next. Everything an APPLICATION needs
around that -- composing a save, capping a transcript, shaping one turn
for a UI -- is the same work whichever application does it, and was written
twice: once in `if_player`, once in QuickBBS.

This package owns that work. It ships in the `ink_engine` repo because
that is the one package both applications already depend on, but it is a TENANT
of this repo, not part of the interpreter:

1. **One-way dependency.** This package imports the story engine. The
   engine never imports this package. `tests/test_session_layering.py`
   fails if that reverses -- a cycle is what turns a future relocation
   into a rewrite.
2. **Talk through `StoryEngine`, never to `InkRuntimeState`.** Every
   Ink-specific type touched here is a line to rewrite when a second
   engine arrives.
"""

from if_session.game_saves import (
    DEFAULT_LABEL_CHARACTER_LIMIT,
    QUICKSAVE_LABEL,
    QUICKSAVE_SLOT,
    SAVE_ENVELOPE_VERSION,
    GameSavesDirectory,
    GameSaveError,
    GameSavesProtocol,
    delete_game_save,
    export_game_save,
    has_quicksave,
    import_game_save,
    list_game_saves,
    load_game_save,
    quickload,
    quicksave,
    save_game,
)
from if_session.session_state import (
    SAVE_FORMAT_VERSION,
    SaveFormatError,
    StoryEngine,
    append_transcript_entry,
    build_saved_state,
    read_saved_state,
    turn_context,
)

__all__ = [
    "DEFAULT_LABEL_CHARACTER_LIMIT",
    "QUICKSAVE_LABEL",
    "QUICKSAVE_SLOT",
    "SAVE_ENVELOPE_VERSION",
    "SAVE_FORMAT_VERSION",
    "GameSavesDirectory",
    "GameSaveError",
    "GameSavesProtocol",
    "SaveFormatError",
    "StoryEngine",
    "append_transcript_entry",
    "build_saved_state",
    "delete_game_save",
    "export_game_save",
    "has_quicksave",
    "import_game_save",
    "list_game_saves",
    "load_game_save",
    "quickload",
    "quicksave",
    "read_saved_state",
    "save_game",
    "turn_context",
]
