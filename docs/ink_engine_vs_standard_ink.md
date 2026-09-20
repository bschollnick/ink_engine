# ink_engine vs. standard Ink

**Date Created:** 2026-09-15  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-19

For Ink authors and developers who know inkle's Ink and want to know what
the differences are between the implementations. `ink_engine` is a
from-scratch Python runtime for compiled Ink, written against inkle's own
docs — vendored in [`inkles-ink-standard/`](inkles-ink-standard/) and
pinned at `"inkVersion": 21`.

The language is unchanged: knots, stitches, weave, tunnels, threads,
LISTs, functions, sequences, glue and tags all behave as inkle's own
runtime does. This is some highlights of the differences between our ink
engine and the standard inkle implementation.

To help ensure the ink engine is matching the inkle standard
implementation of ink, we base our implementation off of their standard
documentation (not code!), we also have a suite of tests that we run
comparing behavior from our ink engine vs the inkle engine. When we
disagree, we examine the results, and match the inkle standard.

If you hit behaviour that differs from `inklecate` and it is not in the
list below, treat it as a bug to report rather than a known limitation.

This is the high-level map. The detailed guides are
[`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md) (bindings
and plugins), [`game_manifest_guide.md`](game_manifest_guide.md) (game
folders), [`building_a_game_bundle.md`](building_a_game_bundle.md)
(packing a game to distribute) and
[`ink_when_it_compiles_but_is_wrong.md`](ink_when_it_compiles_but_is_wrong.md)
(Ink: when it compiles but is wrong).

---

## 1. `ink_engine` plays compiled stories only

`ink_engine` plays the JSON that `inklecate` or Inky produces. It has no
Ink compiler and no `.ink` parser, so you compile your source first and
ship the compiled story.

A released game therefore contains only the compiled story, so nobody can
read or edit the source in the field.

## 2. What `ink_engine` adds

### Words that mean something else here

Some of this engine's names are also names in inkle's runtime, where
they mean something unrelated. The collisions below affect a developer
who has read inkle's `ArchitectureAndDevOverview`; an Ink author who has
only written `.ink` files will never have encountered the runtime
meanings.

| Word | In inkle's runtime | Here |
|---|---|---|
| container | `Runtime.Container`, the compiled node holding content and named sub-content. Knots, stitches and choices all compile down to these. | A thing in the game world that holds other things -- a chest, a basket, a glass case. `containers.py`, and `Inventory`'s container methods. |
| state | `story.state`, the Ink runtime's own position, variables and visit counts, saved with `state.ToJson()`. | A plugin's saved data: the JSON dictionary the engine allocates for it, keyed by `state_key`. |

Neither engine name refers to the inkle one. `Runtime.Container` has no
Ink-level syntax, and `story.state` is an application-side C# object, so
a story cannot name either one. The engine's containers are reached from
Python through `Inventory`, not from Ink -- `inventory.py` publishes no
container binding.

The Ink language's own vocabulary is untouched -- knot, stitch, weave,
divert, tunnel, thread, glue, `LIST` and tag all mean exactly what
inkle's documentation says they mean.

### A plugin system

In standard Ink, every `EXTERNAL` is a function the application binds by
hand, one at a time, and the state behind it lives wherever the
application happens to put it. Nothing ties the two together, so saving
that state is the application's problem.

A plugin here owns both: the functions your story calls and the state
behind them, saved and restored with the story. Eight plugins and three
plugin helpers ship with the engine, publishing 61 bindings between them
when all eight are active — inventory, quests, skills, characters,
character occupancy ("who is where"), a location graph, costs, and a
clock with scheduled effects. A game activates only the plugins it
needs, so the available bindings will vary depending on your plugin
choices.

`{has_item("player", "lantern")}` or `~ start_quest("rescue")` works
without you writing the Python behind it.

**[`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md) is the
full documentation**: how to switch a plugin on, what each one offers,
how to extend one, and how to write your own.

### A game is a folder, or a bundle

A game can be nothing more than a compiled `.inkj`, or that story plus
whatever it needs around it — art, sound, video, settings. It ships in one
of two forms:

- **A game folder** is an ordinary directory on disk. It holds
  `manifest.yaml`, the story that manifest names, and any media the game
  uses. It also holds whatever the author keeps alongside them —
  uncompiled `.ink` source, tests, editor files — none of which the engine
  reads. This is the form you develop in.
- **A bundle** is that same game packed into a single `.zip`, containing
  exactly one top-level directory. It carries only what the manifest
  declares: the manifest, the story named by `MAIN_STORY_FILE`, every
  top-level `.py` (the game's own package), every directory in
  `MEDIA_DIRECTORIES`, and every path in `EXTRA_FILES`. Anything
  undeclared — `.ink` source, a `tests/` directory, editor caches — is
  simply absent. Note that *every* top-level `.py` ships as part of the
  game package, so a test file sitting beside the manifest travels with
  it; keep test files in a subdirectory. This is the form you distribute.

**The difference is what is present, not how it is read.** Both are read
through the same interface, by the same relative paths, returning the same
bytes — `as_source()` picks the implementation from the path, and a `.zip`
suffix is what makes it a bundle. A bundle is played exactly where it
sits and is never unpacked, so nothing is written to disk to play one.
The engine only ever reads a game's files.

**You can distribute a folder.** The engine plays one exactly as it plays
a bundle, so nothing obliges you to pack a game up. A bundle is the
suggestion rather than the requirement, for three reasons: it is one file
instead of a tree, it is smaller, and it leaves out source a player was
never meant to receive. You can reach the same result with a folder by
pruning it yourself before you ship — the outcome is equivalent, and
keeping it right on every release becomes your job. `ink-bundle`, the
bundler that ships with the engine, does that pruning from the manifest
instead: `ink-bundle inspect` reports what would ship without writing
anything, `build` writes the `.zip`, and `verify` reads a built one back.

Building one is described in
[`building_a_game_bundle.md`](building_a_game_bundle.md); the manifest
fields it reads are in
[`game_manifest_guide.md`](game_manifest_guide.md).

### Save slots, quicksave and export files

Standard Ink gives you `state.ToJson()` and `state.LoadJson()`, which
serialize the runtime state to a string and read it back. Slots, labels,
quicksave, export files, and validating a file a player hands back are
all yours to write. This engine ships them:

```python
from if_session import GameSavesDirectory, save_game, load_game_save

game_saves_directory = GameSavesDirectory(Path("saves"))
save_game("thehauntedhouse", 0, state, "Before the bridge",
          saves_in=game_saves_directory, maximum_gamesave_slots=5, saved_at=when)
```

That gives you numbered slots with labels, a quicksave in a reserved slot
of its own, a slot listing that includes the empty slots so it renders
directly as a save menu, and export files carrying a version and
validated before they overwrite anything. Plugin state is in the save,
so it needs no separate tracking; in standard Ink it does, because
`ToJson()` does not know about an `EXTERNAL`'s state.

To keep saves somewhere other than a folder — a database, a cloud
bucket, inside an archive — implement five methods (`read_game_save`,
`write_game_save`, `delete_game_save`, `game_save_exists`,
`summarize_game_saves`) and pass the result as `saves_in=`. Slots, labels,
quicksave, export and validation are unaffected by that choice. The
desktop player uses the folder-based one unchanged; the web application
implements those five against its database.

See [`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md#5-saving-a-game).

### Unwired `EXTERNAL`s can be made an error

Ink lets you give an `EXTERNAL` a fallback: an Ink function that runs when
nothing binds the real one. That fallback usually returns a default —
`false`, `0`, an empty string — which is indistinguishable from a real
answer. So in standard Ink a binding you forgot to wire up looks exactly
like one that works and is telling you no.

`ink_engine` gives you three ways to catch that:

- `strict_externals` raises `UnboundExternalError` instead of running the
  fallback, naming the function.
- The engine can list a story's unbound `EXTERNAL`s before you run it.
- A game that declares required plugins fails to start when one is
  missing, rather than playing on fallbacks.

### The application can act between turns

An application can give the player things to do alongside the story — an inventory
panel, a spell menu — and then have the current turn's choices re-evaluated
in place. Cast a spell from the sidebar and the choice it unlocks appears
without the story advancing a turn.

The choice is an ordinary guarded choice, written as the language
defines it. The turn count, the text already shown and the player's
position are unchanged; only the list of available choices is rebuilt. The
same story runs unmodified on an application that offers no panels.

Character creation works the same way: the answers a player gives before
the story opens are already in your `VAR`s on turn one, so no prologue
knot exists just to set them.

## 3. Where `ink_engine` diverges

Differences between this engine and the standard Ink runtime. Most of
these a story author never touches.

**Three application APIs are unbuilt:** variable observers, `ChoosePathString`,
and named flows. Each was evaluated and deferred because inkle documents
little more than the signature — whether an observer fires on assignment
or only on change, whether a jump resets the call stack, is left unstated.
An application can already reread variables each turn and reposition by restoring
a save. Better documentation or a real use case reopens the question.

**A misspelled function name degrades instead of raising.** Where the
reference runtime reports an unresolvable function call as a story error,
this engine interpolates `0` and plays on, so `{caclulate_total()}` prints
`0` with no warning. If an unexplained `0` appears in your prose, check
the spelling of the function names near it. A misspelled `EXTERNAL` still
raises.

**Saves are this engine's own format, not inkle's.** The save restores
the full position including mid-tunnel and mid-function stopping points,
stores the RNG seed so a resumed save continues the same random sequence,
and carries every plugin's state. The cost is that a save does not move
between this engine and the C# runtime. What the engine builds on top of
that format — slots, labels, quicksave, export files — is described
above under "Save slots, quicksave and export files".

**A fractional number prints more digits than the reference does.** The
C# runtime carries a single-precision float, so `{POW(2, 0.5)}` prints
`1.4142135`; this engine carries a Python float and prints
`1.4142135623730951`. Whole values agree (`{POW(3, 2)}` is `9` in both).
Where the exact digits matter in prose, round explicitly.

**Randomness matches the reference.** `RANDOM()` uses a bit-exact port of
.NET's `System.Random`, verified against captured C# output. Shuffle
ordering (`{~a|b|c}`) reproduces Ink's documented semantics, and in our
testing it matches `inklecate`'s own output.

**Give each player their own `InkRuntimeState`.** The object holds the
whole playthrough — position, call stack, variables — and mutates it in
place with no internal locking. One state plays one story at a time.

**A turn entered while another is still running raises
`ConcurrentPlaythroughError`.** The engine refuses the overlapping call
rather than letting two threads interleave and corrupt the playthrough,
so the thread already mid-turn finishes unharmed. The check costs one
uncontended lock per turn and is not a substitute for giving each player
their own state — it reports the mistake instead of leaving you to find
it in a damaged save.

Handing one state between threads *sequentially* is fine, and is not
refused: a worker pool or `asyncio.to_thread` that runs one turn at a
time on whatever thread is free works as expected. Only overlap is
refused.

The compiled story itself is read-only, so several states may share one
`load_story_root()` result safely. It is the state that must not be
played twice at once. Both shipped applications get this for free —
`if_player` keeps one state per open game, and QuickBBS rebuilds one per
HTTP request from the database.
