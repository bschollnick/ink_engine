# Tests

**Date Created:** 2026-09-20  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-20

42 files, 1058 collected tests. Run them all:

```bash
poetry run python -m pytest tests/ -q
```

## How these tests are written

**The reference runtime decides what is correct.** For engine behaviour,
the expected transcript is captured from a real `inklecate` build's `-p`
play-mode output *before* any assertion is written, then the same story
is driven turn by turn through `continue_story()` and `choose()`. When
this engine and inkle's disagree, inkle's is right and this engine is
fixed. Eleven files carry transcripts captured this way.

**Stories are compiled, not mocked.** `tests/fixtures/` holds 130 files:
`.ink` sources paired with the `.ink.json` that `inklecate` produced from
them. A test that needs a story reads one of those, so what is under test
is the same JSON a shipped game would carry.

**Plugin tests invent their own vocabulary.** A quest, item or skill
identifier in a test is made up for that test. No test names a real
game's content, so the engine never learns a story's vocabulary and the
tests run on any machine.

**Two tests are opt-in** because they reach outside the repository:

| Test | Needs | Enable with |
|---|---|---|
| `test_vendored_standard_is_current.py` | network access to inkle's documentation | `INK_ENGINE_CHECK_UPSTREAM=1` |
| `test_engine_path_sweep.py` | a large real story on disk | `INK_ENGINE_SWEEP_STORY=<path>` |

Both skip rather than fail when what they need is absent, so an ordinary
run stays green offline.

## The test files

| File | What it protects |
|---|---|
| `test_bundle_integrity.py` | Bundle tamper evidence: the story, directory and zip-comment hashes, and bundle version recognition. |
| `test_bundler.py` | Building a game bundle, where `manifest.yaml` decides what ships: contents selection, stale sources, plan verification, the command line. |
| `test_character_creation.py` | `answers_to_globals()`: turning a player's pre-game answers into Ink globals, including `add_to` ordering and reading the story's own declared base. |
| `test_discovery_mount.py` | Mounting a game for import and releasing it, purging `sys.modules` so a second game sharing a package name cannot get the first one's code. |
| `test_engine_characters.py` | The characters plugin: per-character storage and known-state. Guards that location is *not* stored here but read through to occupancy. |
| `test_engine_choices.py` | Diverts and `[choice-only]` choices, driven turn by turn against compiled JSON with inklecate transcripts. |
| `test_engine_costs.py` | The cost table plugin: what an action costs and whether it can be afforded. |
| `test_engine_external_and_validation.py` | `EXTERNAL` fallback resolution and whole-story validation: `find_unbound_externals()`, `UnboundExternalError`. |
| `test_engine_functions_threads.py` | Ink functions and threads, end to end against compiled JSON with inklecate transcripts. |
| `test_engine_lists.py` | Ink `LIST`s end to end, plus `apply_native_function()` for the LIST operator family. |
| `test_engine_location_graph_config.py` | The closed config schema the location graph declares, tested through `validate_location_graph()`. |
| `test_engine_metadata_tags.py` | Tags and the remaining evaluation-stack operations, against compiled JSON with inklecate transcripts. |
| `test_engine_output_stream.py` | Glue and newline assembly in `OutputStream`, against controlled token sequences and `glue.ink.json`. |
| `test_engine_path_sweep_fixture.py` | Every container path in the committed sweep fixture resolves back to itself — the invariant `visit_counts` save and restore depends on. |
| `test_engine_path_sweep.py` | The same container-path round trip over a large real story. Opt-in; see above. |
| `test_engine_paths.py` | Container addressing: `Path`, `resolve_path()` and `InkPathError` against hand-inspected indices. |
| `test_engine_reference_parameters.py` | `ref` parameter write-back and the LIST traversal built on it, including `^` intersection and whole-valued float printing. |
| `test_engine_rng.py` | Sequences, cycles, shuffles and the seeded RNG; `NetRandom` against output captured from a real .NET run. |
| `test_engine_serialization.py` | `to_dict()`/`from_dict()` round trip: a rebuilt state must produce output and choices identical to a control run. |
| `test_engine_session_isolation.py` | One state per playthrough: overlapping turns raise `ConcurrentPlaythroughError`, while sequential hand-off between threads stays allowed. |
| `test_engine_start_new_story.py` | `start_new_story()` as the shared new-game entry point, covering the initial-globals seam once for both applications. |
| `test_engine_systems_inventory.py` | The inventory plugin: stack limits, worn-slot capacity, containers, and the full and closed error paths. |
| `test_engine_systems_location.py` | The two independent location layers: the graph's topology and known-ness, and occupancy's who-is-where and schedule resolution. |
| `test_engine_systems_quests.py` | The quest plugin: stages, goals, parent and child quests, journal entries, unreachable goals. |
| `test_engine_systems_scheduling.py` | The scheduling plugin: clock derivation, day of week, hour of day, day-phase boundaries and scheduled effects. |
| `test_engine_systems_skills.py` | The skills plugin: per-character levels under arbitrary names, and roll-under checks through `CheckResult`. |
| `test_engine_trust_gate.py` | The trust gate and real `EXTERNAL` dispatch: a bound name reaches Python, an unbound one always falls back to the story's Ink stub. |
| `test_engine_tunnels.py` | The call stack and tunnels, end to end against compiled JSON with inklecate transcripts. |
| `test_engine_variables.py` | Variables and the evaluation stack, end to end plus direct `apply_native_function()` operator coverage. |
| `test_file_game_saves.py` | `GameSavesDirectory`, the file-backed store: on-disk layout, unreadable files, and the validation keeping a save inside its own game's directory. |
| `test_game_folder.py` | Resolving a game folder's compiled story and reading its `manifest.yaml`: cover image, engine format, extra files, supported-version check. |
| `test_game_media_resolver.py` | A game answering for its own media tags, over both a directory and a zip, so the engine learns none of a game's key-to-folder rules. |
| `test_game_panel.py` | Calling a game's own side-panel hooks, against real module objects rather than mocks. |
| `test_game_saves.py` | `if_session.game_saves` logic against an in-memory store: envelope versioning, slot validation, quicksave, labels and limits, delete. |
| `test_game_source.py` | A directory and a bundle answering identically through `GameSource`, plus path normalisation. |
| `test_media_resolver.py` | The shared media-tag parser and filesystem resolver: `parse_media_tags()`, `find_cover_image()`, `find_prose_styles()`. |
| `test_plugin_base.py` | `StatefulPlugin`: what a subclass inherits and what construction refuses, using purpose-built plugins so the base class is what is proven. |
| `test_plugin_contract.py` | The plugin contract itself — `plugin.py`, `discovery.py`, `binding.py` — with discovery exercised against real temporary packages. |
| `test_session_layering.py` | An AST guard that `if_session` imports the engine and the engine never imports `if_session`, so the session library stays relocatable. |
| `test_session_state.py` | The save envelope, transcript and turn context, especially the round trip that catches the two applications drifting apart. |
| `test_shipped_plugins_certification.py` | Every discovered plugin against the declared contract, naming no plugin, so a newly added one is certified the day it lands. |
| `test_vendored_standard_is_current.py` | Whether inkle's documentation has moved since the pinned snapshot, comparing normalised text rather than bytes. Opt-in; see above. |
