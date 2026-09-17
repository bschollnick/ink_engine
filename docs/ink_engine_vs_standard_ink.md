# ink_engine vs. standard Ink

For Ink authors and developers who know inkle's Ink and want to know what
changes here. `ink_engine` is a from-scratch Python runtime for compiled
Ink, written against inkle's own docs — vendored in
[`inkles-ink-standard/`](inkles-ink-standard/) and pinned at
`"inkVersion": 21`.

**Your Ink is still Ink.** The language is unchanged: knots, stitches,
weave, tunnels, threads, LISTs, functions, sequences, glue and tags all
behave as the reference runtime does, and conformance is held to captured
real `inklecate` transcripts rather than to opinion. What follows is what
sits on top, and the short list of what is missing.

This is the high-level map. The detailed guides are
[`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md) (bindings
and plugins), [`game_manifest_guide.md`](game_manifest_guide.md) (game
folders) and
[`ink_pitfalls_and_debugging.md`](ink_pitfalls_and_debugging.md)
(standard-Ink traps).

---

## 1. It ships compiled stories

`ink_engine` runs the JSON `inklecate` or Inky produce, and never parses
`.ink` source. Compile first, then ship the compiled story.

That is the point, not a restriction. A released game ships only the
compiled story: the source is not in the box, so it cannot be read or
edited in the field, and what you tested is exactly what runs. Startup has
no compile step, and loading can be lazy — a story's knots are built on
first use rather than all at once.

The ink engine takes the compiled `.inkj` / `.ink.json`, and that's it.

## 2. What it adds

### A plugin system, where stock Ink gives you one `EXTERNAL` at a time

In standard Ink, every `EXTERNAL` is a function the application binds by hand,
one at a time, with its state kept wherever the application happens to keep it.

Here, a plugin is a unit that owns both: the functions your story calls
*and* the state behind them, saved and restored with the story. Eleven
ship with the engine, publishing 47 bindings your `.ink` can call
directly — inventory, quests, skills and skill checks, characters and
their attributes, character occupancy ("who is where"), a location graph,
containers, item text, costs and affordability, and a clock with
scheduled effects.

So `{has_item("player", "lantern")}` or `~ start_quest("rescue")` works
without you writing the Python behind it. A game can price the shipped
ones to its own world, or extend one with vocabulary of its own. See
[`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md).

### A game is a folder, or a bundle

A game can be nothing more than a compiled `.inkj`, or that story plus
whatever it needs around it — art, sound, video, settings. Either way it
can live as a folder, or as a single bundled file.

The engine only ever reads a game's files, never writes them, and it reads
directories and game bundles both the same way. So the bundle is a
first-class citizen, not a packaging step on the way back to a directory:
it is played as it sits, never unpacked, and a game runs either way
unchanged. See [`game_manifest_guide.md`](game_manifest_guide.md).

### Save slots, quicksave and export files

Standard Ink gives you two calls, `state.ToJson()` and
`state.LoadJson()`, which serialize the runtime state to a string and
read it back. Everything else a player would recognise as saving is
yours to write: slots, the label on each one, a quicksave, a save file
they can keep or send to a friend, and the check that a file they hand
back belongs to this game. Upstream provides none of those, so every
project writes them again.

This engine ships them:

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

See [`ink_engine_bindings_guide.md`](ink_engine_bindings_guide.md#6-saving-a-game).

### Catching the binding mistakes Ink makes silent

An `EXTERNAL` declared in Ink with a working fallback, but never actually
wired up, is invisible in standard Ink: the fallback answers plausibly and
play continues. `strict_externals` turns that into an error naming the
function. The engine will also list a story's unbound `EXTERNAL`s before
you run it, and a game that declares required plugins fails loudly if one
is missing rather than playing on stubs.

### The player can act alongside the story

An application can give the player things to do alongside the story — an inventory
panel, a spell menu — and then have the current turn's choices re-evaluated
in place. Cast a spell from the sidebar and the choice it unlocks appears
without the story advancing a turn.

This is standard Ink code throughout. The choice is an ordinary guarded
choice, written exactly as the language defines it — the action just
refreshes the node without advancing the clock. The turn count, the text
already on screen and the player's position are all untouched; the list of
available choices is simply rebuilt against the new state. The same story
runs unmodified on an application that offers no panels at all.

Character creation works the same way: the answers a player gives before
the story opens are already in your `VAR`s on turn one, so no prologue
knot exists just to set them.

## 3. Where it diverges

Here are the differences between this engine and the standard Ink runtime.
Mostly things a story author never touches.

**Three application APIs are unbuilt:** variable observers, `ChoosePathString`,
and named flows. Each was evaluated and deferred because inkle documents
little more than the signature — whether an observer fires on assignment
or only on change, whether a jump resets the call stack, is left unstated.
An application can already reread variables each turn and reposition by restoring
a save. Better documentation or a real use case reopens the question.

**A misspelled function name degrades instead of raising.** Where the
reference runtime reports an unresolvable function call as a story error,
this engine interpolates `0` and plays on, so `{caclulate_total()}` prints
`0` with no warning. An unaccountable `0` in your prose is worth
spellchecking before you debug the arithmetic. A misspelled `EXTERNAL`
still raises here.

**Saves are this engine's own format, not inkle's.** The tradeoff is
deliberate: the save restores the full position including mid-tunnel and
mid-function stopping points, stores the RNG seed so a resumed save
continues the same random sequence rather than re-rolling, and carries
every plugin's own state with it. The cost is that a save does not move
between this engine and the C# runtime. What the engine builds on top of
that format — slots, labels, quicksave, export files — is described
above under "Save slots, quicksave and export files".

**Randomness matches the reference.** `RANDOM()` uses a bit-exact port of
.NET's `System.Random`, verified against captured C# output. Shuffle
ordering (`{~a|b|c}`) reproduces Ink's documented semantics, and in our
testing it matches `inklecate`'s own output.

**Concurrency is the application's to choose.** A runtime state is a plain Python
object with no locking of its own, which is the right default for the
single-session applications built on it so far — a desktop player, a
request-scoped web view. An application that wants to share one instance across
threads wraps it in whatever its own platform already uses, rather than
paying for a synchronization model it does not need.
