# ink-engine

A standalone, Django-free Ink interactive-fiction interpreter and plugin engine.

`ink-engine` runs compiled Ink stories (`.ink.json`/`.inkj`) and provides a minimal
plugin contract for applications (games) to extend the interpreter with their
own stateful mechanics — inventory, scheduling, character occupancy, and so on —
without the engine itself knowing anything about Django, trust/security gating,
or any particular application's UI conventions.

**This is a library for developers, not an app for players.** There is no
UI here, no way to double-click your way into playing a story — `ink-engine`
is the interpreter a application embeds to *add* Ink support to itself.
If you're looking to actually play an Ink story, or ship one:

- **[if_player](https://github.com/bschollnick/if-player)** — a standalone, native desktop player built
  on this engine, for playing `.inkj` game folders directly (with image/video
  support), no server or account required.
- **[QuickBBS](https://github.com/bschollnick/quickbbs)** — a self-hosted
  gallery/file-browser app that also plays Ink stories online, through an
  ordinary browser, for multiple users.

Both are real applications built on top of `ink-engine`'s public API;
this repository is where you'd start if you're building a *third* one, or
contributing to the interpreter itself.

## Design

- **Zero runtime dependencies.** The interpreter and plugin contract are pure
  Python stdlib.
- **No trust concept.** `ink-engine` scans and loads exactly the sources it is
  given (`discover_plugins(sources)`) — deciding *which* sources are safe to
  load is entirely the application's responsibility, upstream of ever
  calling into this library.
- **One dataclass, two functions.** `Plugin` describes a discoverable unit of
  Ink `EXTERNAL` bindings, optionally with a private per-session state slice.
  `discover_plugins()` finds them; `resolve_bindings()` builds the real
  bindings dict for one game session.

## Using the engine

The core interpreter is `InkRuntimeState`. Build one from a compiled story's
parsed JSON, then alternate `continue_story()` (runs until the next choice
point or the story ends) with `choose(index)` (picks one of the choices just
offered):

```python
import json
from ink_engine.engine import InkRuntimeState, load_story_root, load_list_defs

with open("hello.ink.json") as f:
    compiled = json.load(f)

root = load_story_root(compiled)
list_defs = load_list_defs(compiled)

state = InkRuntimeState(root, list_defs)
state.continue_story()          # run the opening turn

print(state.last_turn_text)     # the text just produced
for i, choice in enumerate(state.current_choices):
    print(i, choice.text)

state.choose(0)                 # pick the first choice
state.continue_story()          # run to the next stopping point

print(state.last_turn_text)
print(state.done)               # True once the story reaches -> END
```

A fresh `InkRuntimeState` produces no text until the first `continue_story()`
call — the constructor only runs the story's own global-variable
initialization (`VAR` declarations), matching the real Ink engine's own
`ResetGlobals` behavior.

**Saving and resuming**: `state.to_dict()` returns a plain, JSON-safe dict of
everything needed to resume later; `InkRuntimeState.from_dict(root, data,
list_defs, engine_bindings=...)` rebuilds an equivalent state from it. `root`/
`list_defs` come from re-loading the same compiled story JSON — they are not
themselves part of the saved data, since they never change for a given
compiled story.

**Adding EXTERNAL bindings**: pass `engine_bindings={"function_name":
callable, ...}` to the constructor (or `from_dict`) to make Python callables
reachable from `EXTERNAL function_name(...)` calls in the Ink source. See
`ink_engine/plugin.py` and `ink_engine/discovery.py` for the higher-level
`Plugin`/`discover_plugins()` machinery that assembles this dict from a
application's own stateful plugins (inventory, quests, skills, etc. —
see `ink_engine/engine_plugins/`), rather than building `engine_bindings` by
hand.

## Limitations

Coming from inkle's Ink? `docs/ink_engine_vs_standard_ink.md` is the
high-level tour of what this engine adds and where it diverges. The list
below is the canonical short form.

- **Compiled Ink only — this library has no Ink compiler.** `ink-engine`
  reads the same JSON `inklecate`/Inky produce; it never parses `.ink`
  source text. A `.ink` file with no compiled counterpart is not playable
  here, and there is no way around that short of running a real Ink
  compiler yourself first (see **Compiling stories** below). This is a
  permanent, deliberate scope boundary, not a missing feature planned for
  later.
- **`ink_engine/game_folder.py`'s own `.inkj` convention is a game-folder
  concept, not an engine requirement.** `find_main_story_file()` looks for
  files ending in `.inkj` specifically (a convention this project's own
  game-folder layout chose); the interpreter itself (`load_story_root()`/
  `load_list_defs()`) only needs parsed JSON and does not care what the
  file was named — inklecate's own default output extension is
  `.ink.json`, and that works identically if you load it yourself.
- **No async/threading model of its own.** `InkRuntimeState` is a plain
  Python object with ordinary mutable attributes — a application is
  responsible for whatever concurrency safety its own environment needs
  around a shared instance.

## Compiling stories

Ink source (`.ink`) must be compiled to JSON before `ink-engine` can play it.
Two ways to do that:

1. **[Inky](https://github.com/inkle/inky)** — the official Ink editor, with
   a built-in compiler and live preview. The easiest path for authoring and
   testing a story before shipping it.
2. **`inklecate`** — the command-line compiler from
   [inkle/ink](https://github.com/inkle/ink) (MIT licensed), for scripting a
   build step:

   ```bash
   inklecate -o story.ink.json story.ink
   ```

   `inklecate -p story.ink` also runs the story directly in a terminal
   play-mode, useful for a quick sanity check independent of this engine
   entirely.

Either way, the *compiled JSON* is what this library reads — check that
output into your game folder (or generate it as part of your own build), not
the `.ink` source.

## Quickstart: a tiny example story

Both files below are also checked in under [`examples/`](examples/)
(`hello.ink` and its compiled `hello.ink.json`), ready to run without
compiling anything yourself first.

Save this as `hello.ink`:

```ink
You wake in a small stone room. A single door stands to the north.

* [Try the door]
    The door creaks open. Morning light spills in.
    -> ending
* [Look around first]
    Dust, cobwebs, an old chest in the corner.
    -> ending

=== ending ===
You step outside, blinking in the sun.
-> END
```

Compile it:

```bash
inklecate -o hello.ink.json hello.ink
```

Play it with the engine:

```python
import json
from ink_engine.engine import InkRuntimeState, load_story_root, load_list_defs

with open("hello.ink.json") as f:
    compiled = json.load(f)

state = InkRuntimeState(load_story_root(compiled), load_list_defs(compiled))
state.continue_story()
print(state.last_turn_text)
# You wake in a small stone room. A single door stands to the north.

for i, choice in enumerate(state.current_choices):
    print(i, choice.text)
# 0 Try the door
# 1 Look around first

state.choose(0)
state.continue_story()
print(state.last_turn_text)
# The door creaks open. Morning light spills in.
# You step outside, blinking in the sun.

print(state.done)
# True
```
