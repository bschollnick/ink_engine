# Release Notes

**Date Created:** 2026-09-20  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-20

`ink_engine` began inside QuickBBS, a photo gallery application, as its
interactive-fiction feature. It was extracted into its own repository on
2026-09-08, once nothing in it depended on that application.

Versions before 1.0.0 were never published: the engine was a package
inside QuickBBS and had no release of its own. They are reconstructed
here from commit history so the path to 1.0.0 is legible.

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
