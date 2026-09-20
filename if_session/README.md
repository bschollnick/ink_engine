# `if_session` — the session library

**Date Created:** 2026-09-20  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-20

## Why this is here

A story engine answers one question: what does the story do next.

Everything an application needs *around* that answer — composing a save,
capping a transcript, turning one turn into something a user interface
can show, turning a new player's answers into starting variables — is
the same work whichever application does it. It was written twice: once
in `if_player`, the desktop player, and once in QuickBBS, the web
application.

The two copies diverged. Both claimed to write save version 1, and
neither could read the other's files. That is the failure this package
exists to prevent: one definition, in one place, that both applications
call.

## Why it is not part of `ink_engine`

`ink_engine` is an Ink interpreter. None of this is interpretation —
save slots, quicksave, export envelopes and character-creation forms are
application concerns that would exist unchanged around a different
engine.

So this package ships in the `ink_engine` repository without being part
of the engine. It is here because `ink_engine` is the one package both
applications already depend on, which makes it the only place shared
code can live without inventing a fourth repository for it. It is a
tenant of the repository, not part of the interpreter.

Two rules keep that distinction real rather than aspirational:

1. **The dependency runs one way.** This package imports the engine; the
   engine never imports this package. `tests/test_session_layering.py`
   reads both trees with `ast` and fails if that reverses. A cycle is
   what would turn a future move into a rewrite.
2. **Talk through `StoryEngine`, not `InkRuntimeState`.** Every
   Ink-specific type touched here is a line to rewrite when a second
   engine arrives, so the modules talk to a narrow protocol instead.

When a second engine does arrive, this package moves out as a package
relocation rather than an untangling.

## What is in it

| Module | Owns |
|---|---|
| `game_saves.py` | Numbered save slots, labels, quicksave, export files, and validation of a save a player brings back. Storage is the application's, supplied through `GameSavesProtocol`; `GameSavesDirectory` is a working file-backed implementation for an application with no storage opinion of its own. |
| `session_state.py` | The save envelope, the transcript, and one turn's context. A version marker turns a renamed field into a refusal instead of a silent default. |
| `character_creation.py` | `answers_to_globals()`: turning the answers a player gives before turn one into the Ink globals the story reads. It builds no form — how the question is asked stays with the application. |

Everything is re-exported from the package, so
`from if_session import save_game` works.

## What it deliberately does not do

- **It does not read a clock.** `saved_at` is passed in, so a save's
  timestamp comes from the application.
- **It does not interpret the saved state.** To this package the state
  is an opaque dictionary that the engine wrote.
- **It does not draw anything.** No form, no widget, no template.

## Tests

`tests/test_game_saves.py`, `tests/test_file_game_saves.py`,
`tests/test_session_state.py`, `tests/test_character_creation.py`, and
the layering guard in `tests/test_session_layering.py`.
