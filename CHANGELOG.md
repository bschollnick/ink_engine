# Release Notes

**Date Created:** 2026-09-20  
**Last Updated:** 2026-09-26  
**Last Reviewed:** 2026-09-20

`ink_engine` began inside QuickBBS, a photo gallery application, as its
interactive-fiction feature. It was extracted into its own repository on
2026-09-08, once nothing in it depended on that application.

Versions before 1.0.0 were never published: the engine was a package
inside QuickBBS and had no release of its own. They are reconstructed
here from commit history so the path to 1.0.0 is legible.

---

## Unreleased

- Fixed: literal text or a string value that spells a control marker
  ("done", "end", "ev", "str", "#", ...) is now text. `~ temp a = "done"`
  used to end the story at that line.
- Scheduling: `EffectKind.RUN_STORY_HANDLER` and the binding
  `schedule_story_handler(handler, argument, minutes, event_id)` queue a
  handler the game registers by name, for a delayed change that is more
  than one flag.
- Scheduling: the binding `schedule_move(character_id, location_id,
  minutes, event_id)` queues a `MOVE_CHARACTER` effect; `""` removes the
  character when it fires.
- `location_graph` details accept `entrance` (a boolean): an indoor place
  that is the way into a building, or into a unit inside one.
  `location_graph.buildings(config)` groups a map into a tree of buildings
  by its entrances, nesting a building whose entrance is reached from
  inside another, and lists the indoor places no entrance leads to. A
  `building` detail names a building's main entrance, giving it further
  entrances and places inside it of any terrain, and an exit's `through`
  names a place the journey passes through.
  `tools/map_layout_v2.py` groups a map by this tree when it declares any
  entrance: a nested building shows as its own closed marker inside its
  open parent, a building with no room but its entrance opens to itself,
  and every place has a larger click target.
- `benchmarks/plugin_turn_cost.py` no longer needs a consuming application.
  By default it measures a synthetic town built from every generic engine
  plugin (`--scale` multiplies its size); `--game` measures any game folder
  or bundle with the plugins its manifest declares.
- `Condition.clock_reached(state_key, path)`: true once the clock reaches a
  minute a scene stored in a plugin's state, such as a character who
  arrives "from next Monday".
- `CharacterOccupancy` records the location each character held just before
  their most recent placement; `previous_location(character_id)` reads it.
  After a move it is where they arrived from; after a placement at the same
  place it equals `where_is`, so the two differing means "just arrived".
  Saved games without the record answer `""` until the next placement.
- `CharacterOccupancy.assigned_location(character_id)`: the location the
  story last put a character at with `set_location`. A schedule's
  `recompute()` moves a character without changing it, so a resolver can
  fall back to where a scene sent them.
- `InkRuntimeState.start_interlude(knot)` runs a knot as a tunnel inserted
  into the current turn and offers the turn's choices again when its `->->`
  returns. `->-> elsewhere`, or the story ending, discards them.
  `InterludeError` is raised, before anything changes, for an unknown knot
  or a turn with no choices. Saved state gains an `interludes` key; a save
  without it loads with none pending.
- `InkRuntimeState.knot_choices(knot)` lists the choices a knot would
  offer now, evaluated on a copy of the state. `Choice.target_path` is a
  choice target's path, which `start_interlude()` accepts.
- Side panels: a game's `panel_context()` may return `panel_slots`,
  sections drawn below the active tab's, and `compass_sections()` scans
  them. An action section (`ACTIONS_LAYOUT`, built by `actions_section()`)
  names a menu knot; `fill_action_sections()` lists its choices grouped by
  their `# group:` tag, each group's picture from its `# image:` tag, and
  `find_action()` looks one up to pass to `start_interlude()`.

- `InkRuntimeState.choose_path(path, *arguments)`: standard Ink's
  `ChoosePathString`. Jumps to a knot or stitch by name, resetting the call
  stack (tunnels, function frames, temporary variables, interludes),
  clearing the current choices and advancing the turn count. An unknown
  path raises `InkPathError`, and an argument that is not an int, float,
  string, bool or LIST value raises `TypeError`, before anything changes.
- Panel commands can play a story turn. A game's `panel_command()` may
  answer a dict, `{"knot": str, "message": str, "label": str}` (`message`
  and `label` optional), instead of a message string.
  `GamePanel.command_result()` reads either answer as a `CommandResult`,
  and `play_reaction(state, result)` plays a knot answer with
  `choose_path()` and `continue_story()`. `GamePanel.command()` still
  answers the message.
- `if_session.SAVE_FORMAT_VERSION` is 3: a save carries the engine's
  `interludes`. A version 2 save loads with no interlude pending; a
  version 3 save is refused by a reader of version 2.

### Fixed
- **A tunnel to a divert-target variable (`-> where ->`) stopped the
  story.** The tunnel now runs the variable's target and returns, as
  inklecate's runtime does.
- **A variable printed inside a choice's tag moved into the choice's
  text.** `+ [Wave # image: {season}/a.jpg]` now gives the text "Wave" and
  the tag `image: Winter/a.jpg`.
- **A tag inside an Ink function body raised `InkPathError`.** It is now
  one of the turn's tags, as a tag outside a function is.

### Documentation
- `refresh_choices()` replays the turn, so the turn's assignments and
  `EXTERNAL` calls before its choices run a second time. The bindings
  guide and the standard-Ink comparison said nothing changed but the
  choices; both now say what it does.

---

## 1.0.0 — 2026-09-20

First public release, on PyPI as `ink-engine`.

**What it is.** A Python interpreter for compiled Ink, written against
inkle's own published documentation rather than ported from their C#,
and pinned to `"inkVersion": 21`. Its only dependency is PyYAML.

Shipping at this release: **8 plugins publishing 61 bindings**, 3 plugin
helper modules, a game bundler, a session library, and 1065 tests.

Where each plugin and helper came from:

| Module | Kind | Added | Version |
|---|---|---|---|
| `skills.py` | plugin | 2026-08-24 | 0.3.1 |
| `scheduling.py` | plugin | 2026-08-24 | 0.3.1 |
| `location_graph.py` | plugin | 2026-08-24 | 0.3.1 |
| `character_occupancy.py` | plugin | 2026-08-24 | 0.3.1 |
| `inventory.py` | plugin | 2026-09-07 | 0.4.0 |
| `quests.py` | plugin | 2026-09-07 | 0.4.0 |
| `characters.py` | plugin | 2026-09-07 | 0.4.0 |
| `costs.py` | plugin | 2026-09-07 | 0.4.0 |
| `containers.py` | helper | 2026-09-07 | 0.4.0 |
| `item_text.py` | helper | 2026-09-07 | 0.4.0 |
| `schedule_rules.py` | helper | 2026-09-12 | 0.6.0 |

The first ten were written inside QuickBBS and moved here at 0.5.0.
A helper publishes no bindings of its own; a plugin calls it.

### Packaging
- Published as `ink-engine`, requiring Python 3.12 to 3.14.
- Licensed **BSD 3-Clause**. Earlier metadata claimed MIT with no licence
  file present; the licence now ships inside the wheel.
- `py.typed` in both packages, so type checkers use the annotations.
- `ink-bundle` installs as a command.

### Added
- `ink-bundle build` now will offer to create the `__init__.py` file, if
  it does not exist when bundling.
- `answers_to_globals()` in the session library: turning the answers a
  player gives before turn one into the Ink globals the story reads,
  including `add_to` ordering and reading the story's own declared base
  rather than assuming `0`.

### Documentation
- `docs/building_a_game_bundle.md`, a walkthrough for an Ink author
  packing a game to distribute. Every command output in it is pasted
  from a real run.
- A vocabulary section covering names that mean something else in
  inkle's runtime, to eliminate confusion for Ink developers examining
  this library.
- `tests/README.md` and `if_session/README.md`.
- Enhanced the organization of the manifest guide.

### Fixed
- **The bundler demanded `__init__.py` from every game**, including ones
  shipping no Python code at all, contradicting the manifest guide. It
  now asks only when the game ships Python code.
- **A directory named `__init__.py` satisfied the package check**, so a
  game shipping Python could build a bundle that could not load it.
- A vendored-documentation guard: the snapshot is checked out read-only
  and a `pre-commit` hook refuses staged changes inside it.

---

## 0.9.0 — 2026-09-17

The version number caught up with the work; nothing had been bumped
during development.

- Game saves became part of the session library: numbered slots, labels,
  quicksave, export files, and validation of a save a player brings back.
- More tests, and corrections to test documentation.

---

## 0.8.0 — 2026-09-15

**Added session library.** QuickBBS and IF Player both were creating
code that should have been part of the ink engine, which now has been
split out and made into the session library. This is not exactly ink
engine code, this is effectively a co-partner: it handles the save and
restore functionality, the transcript, and contains the current turn
context.

- A one-way dependency, enforced by `tests/test_session_layering.py`:
  the session library imports the engine, never the reverse.
- `open_stream()` on `GameSource`, so large media is streamed rather
  than read whole.
- `PATH_CACHE_SIZE`, bounding the cache of parsed path strings.
- `recorded_hashes()`, reading a bundle's integrity hashes back out.

---

## 0.7.0 — 2026-09-14

**Games became distributable.** Two changes, together.

- **`manifest.yaml` replaced `__init__.py` as the metadata file.** A
  game's declarations are now read as data instead of being imported as
  Python, so reading a manifest cannot execute anything.
- **The bundler**, with `ink-bundle inspect`, `build` and `verify`. A
  game packs into a single `.zip` the engine plays without unpacking.
  Integrity is recorded in three hashes, and a companion readme is
  written beside the bundle so the hashes can travel separately from it.
- `GameSource` abstracts where a game's files live, with
  `DirectoryGameSource` and `ZipGameSource` answering identically.
- `MountedGame`, a context manager that imports a game's modules and
  releases them afterwards, purging `sys.modules` so a second game
  sharing a package name cannot pick up the first one's code.
- `refresh_choices()`, re-evaluating the current turn's choices when
  application state changes mid-turn — a spell cast from a sidebar can
  unlock a choice without the story advancing a turn.
- `listing_cache` on a game source, for media resolvers to index files.

---

## 0.6.0 — 2026-09-12

**The plugin system became what it is now.** `StatefulPlugin` became
the base class every plugin inherits, with `@external` marking what a
story may call and `@query` what an application may read.

- All ten plugin modules converted: inventory, quests, skills,
  characters, character occupancy, location graph, costs, scheduling,
  plus the container and item-text helpers.
- Plugin state moved from dataclasses to `TypedDict`, so a slot is plain
  JSON that saves and restores without conversion.
- `schedule_rules.py`, describing where a character is as ordered data
  rather than code, so a schedule serialises with a save.
- Game side-panel hooks (`panel_context`, `panel_action`,
  `panel_command`), letting a game offer an application things to render
  beside the story.
- `benchmarks/plugin_turn_cost.py`, measuring what the plugin layer
  costs per turn.

---

## 0.5.0 — 2026-09-08 (first version in this repository)

**Extracted from QuickBBS into its own repository.** The move took
`engine.py` (4204 lines by then) and all ten plugin modules out of the
application. What remained behind was QuickBBS's own trust gating,
ingestion and user interface.

- **`UnboundExternalError`**: an `EXTERNAL` call with neither a bound
  Python callable nor a resolvable Ink fallback now raises, matching
  inklecate's own runtime error instead of silently pushing `0`.
- `docs/ink_engine_bindings_guide.md` and the Ink pitfalls guide, with
  every Ink-language claim re-verified against real inklecate and
  attributed to either the compiler or this engine.
- inkle's own documentation vendored under `docs/inkles-ink-standard/`
  as a pinned, dated snapshot.
- `examples/`, with a quickstart story that runs.
- Media resolution extended to prose stylesheets.

---

> **Everything below this line predates the split.** Versions 0.2.0
> through 0.4.0 were developed inside the QuickBBS repository, as the
> `quickbbs/interactive_fiction/` application. There was no `ink_engine`
> repository yet, and no release of any kind. See 0.5.0 above for the
> extraction.

## 0.4.0 — 2026-09-07 (in the QuickBBS repository)

Plugins became a directory of their own inside the QuickBBS application,
separating engine-level systems from one game's content.
`engine_systems/` was renamed `engine_plugins/`, carrying the four
modules already there.

Six arrived with the rename: the **inventory**, **quests**,
**characters** and **costs** plugins, and the **containers** and
**item_text** helpers.

---

## 0.3.1 — 2026-08-24 (in the QuickBBS repository)

**The first four plugins**, as `engine_systems/`: **skills**,
**scheduling**, **location_graph** and **character_occupancy**. Engine
systems began to separate from one game's own content.

---

## 0.3.0 — 2026-08-21 (in the QuickBBS repository)

Story content was re-anchored onto QuickBBS's `DirectoryIndex` and
`FileIndex`, replacing the earlier `Story`/`StoryBlob`/`StoryImageBlob`
models, so a game's files lived where the rest of the gallery's files
did. Web ingestion was brought up to spec for `.inkj` files.

---

## 0.2.0 — 2026-08-17 (in the QuickBBS repository)

The beginning: an Ink interpreter inside QuickBBS's new
`interactive_fiction` application, `engine.py` at 3706 lines, alongside
the models, ingestion and administration that made it playable in a
browser.

---

## Versioning

From 1.0.0 this project follows [semantic versioning](https://semver.org):
the major version changes when something published breaks, the minor when
capability is added compatibly, the patch for corrections.

The engine's own version is not Ink's. `"inkVersion": 21` is the compiled
story format this engine reads, and is set by inkle.
