# ink-engine

**Date Created:** 2026-09-15
**Last Updated:** 2026-09-20
**Last Reviewed:** 2026-09-19

A standalone Ink interactive-fiction interpreter and plugin engine, with no
web framework or database of its own.

`ink-engine` runs compiled Ink stories (`.ink.json`/`.inkj`) and provides a minimal
plugin contract for applications (games) to extend the interpreter with their
own stateful mechanics — inventory, scheduling, character occupancy, and so on —
without the engine itself knowing anything about how it is embedded:
trust and security gating, storage, or any particular application's user
interface conventions.

**This is a library for developers, not an app for players.** It has no
user interface and nothing to run on its own — `ink-engine` is the
interpreter an application embeds to *add* Ink support to itself.
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

- **The only third-party dependency is `pyyaml`.** The interpreter and the
  plugin contract are pure Python stdlib: `ink_engine.engine`, `plugin` and
  `discovery` import with nothing installed. `pyyaml` is needed only to read
  a game's `manifest.yaml` — `game_folder.py`, `game_source.py`,
  `bundler.py` and `bundle_integrity.py`.
- **You decide what gets loaded.** `ink-engine` scans exactly the sources you
  pass to `discover_plugins(sources)` — it never searches for plugins on its
  own. Which sources are safe to load is a policy decision that belongs to
  your application, not to a library that cannot know your users.
- **The plugin contract is small.** `Plugin` describes a discoverable unit
  of Ink `EXTERNAL` bindings, optionally with a private per-session state
  slice.
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
`Plugin`/`discover_plugins()` machinery that assembles this dict from an
application's own stateful plugins (inventory, quests, skills, etc. —
see `ink_engine/engine_plugins/`), rather than building `engine_bindings` by
hand.

## Limitations

`docs/ink_engine_vs_standard_ink.md` covers what this engine adds and
where it diverges, for anyone coming from inkle's Ink. The list below is
the short form.

- **Compiled Ink only — this library has no Ink compiler.** `ink-engine`
  reads the JSON that `inklecate` or Inky produces, and has no `.ink`
  parser. A `.ink` file with no compiled counterpart is not playable
  here, and there is no way around that short of running a real Ink
  compiler yourself first (see **Compiling stories** below). A compiler
  will not be added; compile with `inklecate` or Inky and ship the
  result.
- **`.inkj` and `.ink.json` are the same thing.** Both name a compiled Ink
  story; only the filename differs. `inklecate`'s default output extension
  is `.ink.json`, and this project's game-folder layout prefers the shorter
  `.inkj` — so that is what the documentation and examples use, and what a
  game folder is expected to ship.

  Neither is enforced. The interpreter (`load_story_root()`/
  `load_list_defs()`) takes parsed JSON and never sees a filename at all.
  `find_main_story_file()` returns whatever `MAIN_STORY_FILE` names,
  checking only that the file exists — `.ink.json`, `.inkj` or any other
  name loads identically. The `.inkj` suffix appears in one error message
  and in bundle fingerprinting, never as a check on what may play.
- **One playthrough per `InkRuntimeState`.** The object is plain Python
  with ordinary mutable attributes and no internal locking, so give each
  player their own. A turn entered while another is still running on the
  same state raises `ConcurrentPlaythroughError` rather than corrupting
  it; running turns on it one at a time from different threads is fine.
  A compiled story root is read-only and may be shared by any number of
  states.

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

## Distributing a game

A game is a folder, and `ink-bundle` packs one into a single `.zip` that
the engine plays without unpacking:

```bash
ink-bundle inspect my-game    # report what would ship; writes no files
ink-bundle build   my-game    # write the .zip
ink-bundle verify  my-game.zip
```

`docs/building_a_game_bundle.md` walks through it, and
`docs/game_manifest_guide.md` documents the manifest fields that decide
what ships.

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

---

## A note on this project

I am not an Ink author. Any mistakes in the code or the documentation are
mine, not the language's. Please feel free to submit documentation and code
errors.

This library has no connection to inkle. It is entirely reverse engineered
from the inkle standard documentation and from comparing the results of
compiled Ink run through both engines.
