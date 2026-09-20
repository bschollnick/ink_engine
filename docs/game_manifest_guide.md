# Writing a Game Manifest

**Date Created:** 2026-09-13  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-19

Every game folder holds a `manifest.yaml` describing the game: its title,
which story file to play, what media it ships, and what the engine must
switch on to run it. This guide covers every field and how to fill it in.

To pack a finished game into a distributable `.zip`, see
[Building a Game Bundle](building_a_game_bundle.md). This guide is the
reference for the fields that build reads.

**Who reads it.** The manifest belongs to preparing and playing a game,
not to running a story. The interpreter never sees it: hand
`load_story_root()` a parsed `.inkj` and a story plays with no manifest
and no game folder at all.

Two layers above that do read it, and they ask different things:

- **The engine**, internally — `media_resolver.py` resolves a game's cover
  and prose stylesheet, and `bundler.py` decides what goes into a `.zip`.
- **A player application** — the standalone player and QuickBBS both ask
  which story to play, which layout to use, which plugins the game wants,
  and what to tell the player before starting.

So a field here is read by one or both, never by the interpreter. Where
that matters for a particular field, its own section says so.

The manifest is plain YAML. Nothing in it executes, so a bad value can
never be a security problem.

Most fields are optional and fall back to a documented default when
absent. Three do not, and a game that gets them wrong raises
`GameFolderError` rather than loading:

| Field | Raises when |
|---|---|
| `MAIN_STORY_FILE` | absent, or naming a file the game does not contain |
| `MANIFEST_VERSION` | declaring a version newer than this engine understands |
| `ENGINE_FORMAT` | naming a story format other than `ink` |

`MANIFEST_VERSION` and `ENGINE_FORMAT` raise only on a *wrong* value;
leaving either out is fine. `MAIN_STORY_FILE` is the one field every
manifest must carry.

## 1. The smallest manifest that works

```yaml
MANIFEST_VERSION: 1
GAME_TITLE: The Lighthouse
MAIN_STORY_FILE: lighthouse.inkj
```

That is enough to play. Everything else adds capability.

## 2. A game folder

```
lighthouse/
├── manifest.yaml     the file this guide is about
├── __init__.py       only if you ship Python code (see below)
├── lighthouse.inkj   the compiled story
└── images/           whatever your story's tags point at
```

**`__init__.py` is needed only if your game ships Python code.** It is
Python's package initialization file: the folder is a Python package
because the file is there, which is how a game's own plugins or its
`sidebar.py` get imported. A game that ships neither plays without it.
Include it if you ship either, or if you might later.

**The story must be compiled.** The engine plays compiled JSON and has no
Ink compiler of its own, so run `inklecate` over your `.ink` source and
point `MAIN_STORY_FILE` at the result. A folder containing only `.ink`
cannot be played.

**`.inkj` and `.ink.json` are the same file, differently named.**
`inklecate` writes `.ink.json` by default; this layout prefers the shorter
`.inkj`, which is what these examples use and what a game folder is
expected to ship. Neither is enforced: `MAIN_STORY_FILE` is taken
literally, so `MAIN_STORY_FILE: lighthouse.ink.json` plays exactly as
`lighthouse.inkj` does. Rename the compiler's output or point the field at
it — either works.

---

## 3. Fields

### 3.1 Identity

```yaml
MANIFEST_VERSION: 1
GAME_TITLE: The Lighthouse
GAME_AUTHOR: A. Marlow
GAME_VERSION: "1.2"
GAME_DESCRIPTION: >
  A keeper, a storm, and a light that has started answering back.
  Three endings, roughly an hour.
```

| Field | Required | Notes |
|---|---|---|
| `MANIFEST_VERSION` | Recommended | The manifest format's version, currently `1`. Declaring it lets the format change later without guessing what an old file meant. A version above what the engine supports raises. |
| `GAME_TITLE` | Recommended | Shown wherever the game is listed. Falls back to the folder name. |
| `GAME_AUTHOR` | Optional | Leave it out entirely rather than inventing one. |
| `GAME_VERSION` | Recommended | **Your** version, not the engine's — any string. Quote it: unquoted, YAML reads it as a number and a trailing zero is lost, so `1.10` ships as `1.1`. |
| `GAME_DESCRIPTION` | Optional | A sentence or two. `>` lets you wrap across lines naturally. |

`GAME_VERSION` matters more than it looks. It is how a save, a bundle, or
a listing says which build it came from — without it there is no way to
tell a player their save is from an older version of your game.

### 3.2 The story

```yaml
ENGINE_FORMAT: ink
MAIN_STORY_FILE: lighthouse.inkj
PLAY_LAYOUT: three_column
```

| Field | Required | Notes |
|---|---|---|
| `ENGINE_FORMAT` | Optional | The story format. `ink` is the only one supported, and is assumed if absent; any other value raises. |
| `MAIN_STORY_FILE` | **Required** | The compiled story to play, relative to the game folder. |
| `PLAY_LAYOUT` | Optional | `classic` (single column) or `three_column` (controls, story, side panel). Defaults to `classic`. |

**`MAIN_STORY_FILE` is always required.** The engine never scans or
guesses, even when a folder holds exactly one `.inkj`: a game folder also
holds media and, often, the per-chapter files a build left beside the
combined story, so inferring which one plays means walking content to
answer a question the manifest already answers. Omit it and loading
raises.

### 3.3 Media

```yaml
MEDIA_DIRECTORIES:
  - images
  - audio
COVER_IMAGE: images/cover.png
PROSE_STYLES: theme.css
```

| Field | Required | Notes |
|---|---|---|
| `MEDIA_DIRECTORIES` | If you ship media | Directories holding anything your story's tags point at. Each is included whole. |
| `COVER_IMAGE` | Optional | Shown in a game list. Without it the engine looks for `cover.png`/`.jpg`/`.gif`/`.webp` in the folder root and in `images/`. |
| `PROSE_STYLES` | Optional | A CSS file styling your prose. Defaults to `styles.css` if present. |
| `USES_NETWORK_RESOURCES` | Optional | Declare `true` if your game loads anything over the network. Advisory: an application tells the player, nothing restricts it. |

**List every directory your tags reach.** An image tag can be built while
the game runs — `# image: {character}/portrait.jpg` resolves differently
per playthrough — so the engine cannot work out which files a story will
actually use by reading it. Anything in a directory you do not list is
simply absent when a player reaches it.

### 3.4 Extra files

```yaml
EXTRA_FILES:
  - credits.txt
  - LICENCE
```

Individual files that are not media and not code. Paths must stay inside
the game folder; anything pointing outside is refused.

**This field is about bundling, not about play.** It decides what
`ink-bundle` packs into a `.zip` — nothing reads it while a story runs. A
file listed here is carried along; making it *do* something is up to the
application playing the game.

**Fonts are not supported this way.** A game's `styles.css` is handed to
the application as CSS *text*, injected into a `<style>` element in the
page. A relative `url()` inside it resolves against that page's own
document, not against your game folder, so `src: url("fonts/serif.woff2")`
looks for the file beside the application's HTML and does not find it. A
bundled game has no filesystem path at all — its media reaches the page as
`data:` URIs.

If you need a custom face today, embed it in `styles.css` as a `data:` URI:

```css
@font-face {
  font-family: "GameSerif";
  src: url("data:font/woff2;base64,<base64 of the font>") format("woff2");
}
```

That travels with the CSS text and works for both a folder and a bundle.
Otherwise name a family the reader's system already has.

### 3.5 Network resources

```yaml
USES_NETWORK_RESOURCES: true
```

Declare this when your game loads anything from the network — a CDN font,
a remote image. Absent means `false`, so a self-contained game says
nothing.

An application uses it to tell the player before they start. The player
that ships with this engine shows:

> This game uses resources from the network, such as fonts or images.
> Playing it will make requests to servers outside your computer.

**It is a declaration, not a restriction.** Nothing verifies it and
nothing blocks what a game loads: your `styles.css` reaches the page as
CSS text, and CSS can name a remote font whatever this field says.
Declaring it honestly is what makes it useful — a reader who sees no
notice should be able to trust that.

### 3.6 Plugins

```yaml
REQUIRED_PLUGINS:
  - quests
  - skills
```

The engine's built-in mechanics your story calls. The full set:

| Name | What it tracks |
|---|---|
| `characters` | Named characters and arbitrary attributes on them |
| `character_occupancy` | Who is where, and who is with whom |
| `cost_table` | Prices, and whether the player can afford something |
| `inventory` | Who holds what, stacks, and container contents |
| `location_graph` | Places, how they connect, and which are known |
| `quests` | Quests and their stages |
| `scheduling` | An in-game clock and calendar |
| `skills` | Skill levels and checks against them |

List only what you use — an unlisted plugin is not loaded, and your
story's calls into it fall back to whatever your Ink code does without
it.

**`PLUGIN_DENIED_SCREEN` names a Markdown file**, relative to the game
folder, shown when a game that declares `REQUIRED_PLUGINS` has not been
trusted:

```yaml
PLUGIN_DENIED_SCREEN: why_plugins.md
```

Say what the player loses by declining. `character_occupancy` missing
means no character is anywhere, so half your scenes will look empty —
write that, because the application can only show the plugin's name.
Leave the field out and the name is all the player gets. It is optional,
and a reader that does not know the field ignores it.

**If you ship your own plugin that replaces a built-in one, list only
yours.** Your plugin and the built-in it replaces answer the same
function names and share the same stored state, so listing both means
whichever loads last silently wins — and it is not always the one you
meant. The order of this list is the order they load: later entries win
a collision.

### 3.7 Character creation

Questions asked before the story starts. Each answer is written into an
Ink variable your story can read from its first line.

```yaml
NEW_GAME_FIELDS:
  - var: player_name
    type: text
    label: What should we call you?
    default: Morgan

  - var: hard_mode
    type: checkbox
    label: Play with limited supplies?
    default: false

  - var: starting_role
    type: radio_image
    label: Who were you before the storm?
    default:
      starting_role: keeper
    options:
      - value:
          starting_role: keeper
        label: The keeper
        image: role_keeper.png
      - value:
          starting_role: sailor
        label: A sailor
        image: role_sailor.png
```

Three types:

- **`text`** — free text. `default` is a string.
- **`checkbox`** — a yes/no. `default` is `true` or `false`.
- **`radio_image`** — a picture-and-label choice. Each option's `value`
  is a map of variables to set, so one choice can set several at once.
  Images are files in your game folder, named like any other media.

Two extras a checkbox can carry:

```yaml
  - var: veteran
    type: checkbox
    label: Start as a veteran?
    default: false
    linked_vars:
      starting_rank:
        "True": captain
        "False": deckhand

  - var: found_purse
    type: checkbox
    label: Start with extra coin?
    default: false
    add_to:
      player_money: 50
```

- **`linked_vars`** sets *other* variables based on the answer. **Quote
  the `"True"` and `"False"` keys.** Unquoted, YAML reads them as
  booleans and the lookup silently fails to match, leaving the linked
  variable at whatever your story declared.
- **`add_to`** adds to a variable your story already declared, rather
  than replacing it — so the story stays the single source of the base
  value. It is applied **after every other field has been read**, so it
  adds to whatever they settled on: if a `radio_image` choice sets the
  same variable, `add_to` adds to that, not to the story's own default.

A question the player never answers takes its declared `default`, so a
game opened without asking behaves exactly as though every default was
chosen.

---

## 4. Fields you do not write

A bundled game's manifest carries two more fields, added when the bundle
is built:

```yaml
STORY_SHA256: ...
BUNDLE_DIRECTORY_SHA256: ...
```

They record what the bundle contained at build time, so a later reader
can tell whether anything has changed since. **Do not edit them and do
not copy them into a manifest you are writing** — editing either makes
the bundle fail verification.

---

## 5. Checking your manifest

```
ink-bundle inspect path/to/your-game
```

Reports what the manifest declares, what would ship, and — most usefully
— anything it names that does not exist. A directory you meant to list
but misspelled shows up here rather than as missing art mid-playthrough.

`inspect` only reports; it writes no files. Building the bundle and checking a built one
are `ink-bundle build` and `ink-bundle verify`, both walked through in
[Building a Game Bundle](building_a_game_bundle.md).
