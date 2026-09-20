# Building a Game Bundle

**Date Created:** 2026-09-20  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-20

**Who reads it.** An Ink author who has a game that plays and wants to
hand it to someone else. It assumes you can compile your story and have
written a `manifest.yaml`; it does not assume you know Python or have
read the engine's other documentation.

A bundle is your game packed into one `.zip` that the engine plays
without unpacking. You do not have to build one — the engine plays a
game folder just as happily, and
[what a folder and a bundle each are](ink_engine_vs_standard_ink.md#a-game-is-a-folder-or-a-bundle)
explains why you might still want to.

---

## Before you start

Three things have to be true. The first two are about the game folder,
which
[Section 2, A game folder](game_manifest_guide.md#2-a-game-folder)
describes in full.

1. **The story is compiled.** The engine plays compiled JSON
   (`.inkj` or `.ink.json`) and has no compiler. Run `inklecate` first.
   See [Section 3.2, The story](game_manifest_guide.md#32-the-story).
2. **If your game ships Python code, the folder holds an `__init__.py`.**
   This is Python's package initialization file, and its presence is what
   lets your plugins or `sidebar.py` be imported from the bundle. A game
   that is only a story and its media imports nothing and does not need
   one. The bundler asks for it only when your game ships a `.py` file
   or declares `REQUIRED_PLUGINS`, so you will be told if it is needed.
   See
   [Section 2, A game folder](game_manifest_guide.md#2-a-game-folder).
3. **`manifest.yaml` names the story.** `MAIN_STORY_FILE` is always
   required; nothing is guessed or scanned for. See
   [Section 3.2, The story](game_manifest_guide.md#32-the-story).

A minimal folder:

```
lantern/
    manifest.yaml
    __init__.py         <- only if the game ships Python code
    lantern.ink          <- your source; not shipped
    lantern.inkj         <- compiled; shipped
    media/
        art/cover.png
```

---

## Step 1 — Look before you build

`inspect` reports what would ship. It creates no bundle and changes
nothing in the game folder, so it is safe to run at any point:

```bash
ink-bundle inspect lantern
```

```
Game folder : lantern
Package name: lantern
Main story  : lantern.inkj

Included: 4 files, 700 B

  by manifest declaration:
         1  MAIN_STORY_FILE
         1  MEDIA_DIRECTORIES: media
         1  game package
         1  manifest

  by file type:
         1  .inkj
         1  .png
         1  .py
         1  .yaml

Bundle would be playable.
```

Read the `by manifest declaration` list against what you expect. This is
where a misspelled directory shows up — as a line missing here, rather
than as missing art halfway through someone's playthrough.

If a required piece is absent, `inspect` says so instead:

```
Would NOT produce a playable bundle:
    - no __init__.py: this game ships Python code, so it needs Python's
      package initialization file for its plugins and sidebar to import
```

### What gets in

The manifest decides, not the folder. A bundle carries:

| Included | Declared by |
|---|---|
| `manifest.yaml` | always |
| The compiled story | `MAIN_STORY_FILE` — [Section 3.2](game_manifest_guide.md#32-the-story) |
| Every top-level `.py` | the game's own package |
| Media directories | `MEDIA_DIRECTORIES` — [Section 3.3, Media](game_manifest_guide.md#33-media) |
| Anything else you name | `EXTRA_FILES` — [Section 3.4, Extra files](game_manifest_guide.md#34-extra-files) |

Everything undeclared is simply absent: your `.ink` source, editor
caches, notes.

**Every top-level `.py` ships**, so a `test_game.py` sitting beside the
manifest travels to your players. Keep test files in a subdirectory.

---

## Step 2 — Build it

```bash
ink-bundle build lantern
```

```
Wrote lantern.zip (1.4 KB, 4 files)
Compression: 204.5% of uncompressed size
```

The bundle lands beside the game folder. Useful options:

| Option | Does |
|---|---|
| `-o PATH`, `--output PATH` | Write somewhere else. Default is `<game_dir>/../<package>.zip`. |
| `--package-name NAME` | Set the top-level directory inside the zip. Defaults to the folder's name. |
| `-q`, `--quiet` | Print only the final result. |
| `--allow-stale` | Build even though the story looks out of date. See below. |
| `--create-package-marker` | Write `__init__.py` without asking. For scripts. |

### If it offers to create `__init__.py`

`__init__.py` is Python's **package initialization file**. Python imports
a folder as a package only when it contains one, which is how your
game's plugins and `sidebar.py` are loaded out of the bundle.

When your game ships Python code and the folder has none, `build` asks
before doing anything:

```
This game ships Python code, and Python imports a folder as a package
only when it contains __init__.py, its package initialization file.
Create /path/to/lantern/__init__.py? [y/N]
```

Answering `y` writes it and carries on. Answering anything else writes
nothing and stops, so you can create it yourself: `touch lantern/__init__.py`
does the same job.

Nothing is overwritten: if a *directory* named `__init__.py` is in the
way, the build stops and says so rather than touching it.

Run from a script, where nothing can answer, `build` reports the problem
and stops instead of waiting. Pass `--create-package-marker` to have it
written without asking.

### If it refuses because the story is stale

```
Refusing to build a bundle from a stale story.

WARNING: 1 .ink source(s) are newer than lantern.inkj.
         The bundle would ship the PREVIOUSLY compiled content.
         lantern.ink
         Recompile, or pass --allow-stale to bundle anyway.
```

Your `.ink` file has changed since you last compiled, so the bundle
would carry the older story. Recompile and build again. `--allow-stale`
exists for when you know the source is ahead on purpose.

### What else the build writes

A **companion readme** appears beside the bundle — `lantern.md` for
`lantern.zip`. It is regenerated on every build, and every value in it
comes from the manifest or the hashes just computed, so it cannot
disagree with the bundle it describes.

```markdown
# lantern

**Bundle:** `lantern.zip` (1.4 KB, 4 files)  
**Version:** 1.0

## Verification

| Value | SHA-256 |
|---|---|
| Story (`lantern.inkj`) | `72be63f7...` |
| Bundle directory | `0b39489e...` |
| Manifest | `8c638eaa...` |
```

Publish it wherever you publish the bundle. Its purpose is that the
hashes travel *separately* from the archive: a bundle's own recorded
hashes prove only that nobody has touched it since it was built, because
anyone who rewrites the archive recomputes them too. A hash you
published elsewhere is the one an attacker cannot reach. It is also what
a person wants before opening a `.zip` — what this game is, who wrote
it, how big it is.

---

## Step 3 — Verify what you built

```bash
ink-bundle verify lantern.zip
```

```
Bundle  : lantern.zip
Entries : 4
Size    : 1.4 KB
Title   : The Lantern
Story   : lantern.inkj
Layout  : (application default)

Integrity: all recorded hashes match.
Companion readme: lantern.md

Bundle opens correctly.
```

Check `Title` is your game's name rather than `(untitled)`. Untitled
means `GAME_TITLE` is missing or misspelled in the manifest — see
[Section 3.1, Identity](game_manifest_guide.md#31-identity). Nothing
rejects an unknown key, so a typo is silent until you look here.

A modified bundle fails, and says which of the three hashes disagreed:

```
INTEGRITY CHECK FAILED — this bundle has been modified since it was built:
    - archive comment records no manifest hash
    - BUNDLE_DIRECTORY_SHA256 does not match the bundle's contents
    - STORY_SHA256 does not match 'lantern.inkj'
```

`verify` exits non-zero on failure, so a release script can depend on
it.

---

## Releasing a new version

Set `GAME_VERSION` in the manifest before you build. It is how a save, a
bundle or a listing says which build it came from; without it there is no
way to tell a player their save predates the game they are holding.

**Quote it.** YAML reads an unquoted version as a number, and a number
loses the trailing zero:

```yaml
# Wrong — YAML makes this the number 1.1
GAME_VERSION: 1.10
```

```yaml
# Right — quoted, so it stays the text you wrote
GAME_VERSION: "1.10"
```

Nothing warns you. The bundle builds, and the companion readme beside it
publishes `**Version:** 1.1` to your players while your manifest says
`1.10`.

What is lost is a trailing zero after the decimal point, so `1.10`
becomes `1.1` and `1.20` becomes `1.2`. Versions with nothing to lose
come through unchanged — `1.0`, `2`, `0.9` — as does any three-part
version like `1.2.3`, which is not a number in the first place. Quoting
every version is simpler than remembering which forms are safe. See
[Section 3.1, Identity](game_manifest_guide.md#31-identity).

Two manifest fields are written *by* the build — `STORY_SHA256` and
`BUNDLE_DIRECTORY_SHA256`. Do not write or edit them yourself and do not
copy them into a manifest you are authoring; editing either makes the
bundle fail verification. See
[Section 4, Fields you do not write](game_manifest_guide.md#4-fields-you-do-not-write).

---

## Where to look next

- [Writing a Game Manifest](game_manifest_guide.md) — every field, in
  full.
- [A game is a folder, or a bundle](ink_engine_vs_standard_ink.md#a-game-is-a-folder-or-a-bundle)
  — what the two forms are and why both are read identically.
- [The plugin and binding guide](ink_engine_bindings_guide.md) — if your
  game ships its own Python.
