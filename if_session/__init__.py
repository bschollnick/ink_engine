"""The session library: what a host needs around a story engine.

A story engine answers what the story does next. Everything a HOST needs
around that -- composing a save, capping a transcript, shaping one turn
for a UI -- is the same work whichever host does it, and was written
twice: once in `if_player`, once in QuickBBS.

This package owns that work. It ships in the `ink_engine` repo because
that is the one package both hosts already depend on, but it is a TENANT
of this repo, not part of the interpreter:

1. **One-way dependency.** This package imports the story engine. The
   engine never imports this package. `tests/test_session_layering.py`
   fails if that reverses -- a cycle is what turns a future relocation
   into a rewrite.
2. **Talk through `StoryEngine`, never to `InkRuntimeState`.** Every
   Ink-specific type touched here is a line to rewrite when a second
   engine arrives.

See `if_player/claude_docs/plans/consumer_standardization.md`.
"""

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
    "SAVE_FORMAT_VERSION",
    "SaveFormatError",
    "StoryEngine",
    "append_transcript_entry",
    "build_saved_state",
    "read_saved_state",
    "turn_context",
]
