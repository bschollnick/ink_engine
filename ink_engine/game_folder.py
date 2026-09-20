"""Resolving a game folder's own compiled story file and reading its manifest.

A game needs a real, existing compiled story: this engine has no Ink
compiler of its own. `.inkj` and `.ink.json` are the same thing under
different names — `inklecate` writes the latter, this layout prefers the
former, and neither is enforced. `MAIN_STORY_FILE` is taken literally and
checked only for existence.

**The manifest is `manifest.yaml`** — plain data with no execution path.
`read_manifest()` is the one reader every typed accessor here builds on,
and it parses the file **once per call, not once per field**.

A game folder is an importable Python package: its `__init__.py`,
Python's package initialization file, is what lets its plugins and
`sidebar.py` load by ordinary import.

`read_module_literals()` remains for reading literal assignments out of a
game's other `.py` files — via `ast`, **never imported or exec'd, since a
game folder is untrusted content**.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from ink_engine.game_source import (
    DirectoryGameSource,
    GameSource,
    GameSourceError,
    as_source,
)

#: The compiled-story extension this layout prefers. A convention, not a
#: check: nothing here rejects another name, and `.ink.json` plays exactly
#: the same. Used in an error message and in bundle fingerprinting.
COMPILED_STORY_SUFFIX = ".inkj"

#: A game folder's manifest. Plain data: unlike the `__init__.py` it
#: replaced, it has no execution path at all, so reading it cannot run
#: anything even in principle.
MANIFEST_FILENAME = "manifest.yaml"

#: Parsed manifests, keyed by path, each with the `st_mtime_ns` it was
#: read at. Typed readers each want one field, so without this a caller
#: reading five fields parses the file five times — measured at 2.7 ms a
#: parse on a real game's manifest.
_MANIFEST_CACHE: dict[tuple[str, str | int], tuple[int, dict[str, Any]]] = {}

#: The manifest field naming which layout template a game wants — read
#: the same way as `MAIN_STORY_FILE`, via `_read_manifest_string_field()`.
#: Falling back to a default for an absent/unknown value is the CALLER's
#: job (this module has no opinion on what layouts exist or which is
#: default), matching how `find_main_story_file()` itself never invents a
#: story file.
PLAY_LAYOUT_FIELD = "PLAY_LAYOUT"

#: The manifest field naming which plugins a game wants active — a plain
#: list of plugin names, e.g. `["scheduling", "occupancy"]`.
REQUIRED_PLUGINS_FIELD = "REQUIRED_PLUGINS"

#: Manifest field naming the questions a game asks before its first turn.
NEW_GAME_FIELDS_FIELD = "NEW_GAME_FIELDS"

#: The manifest schema's own version. Read before anything else in the
#: file is interpreted, so the schema can change without a reader having
#: to guess which shape it is looking at.
MANIFEST_VERSION_FIELD = "MANIFEST_VERSION"

#: The manifest schema version this engine understands.
SUPPORTED_MANIFEST_VERSION = 1

#: The story format this engine plays. A manifest declaring anything else
#: names a game this engine cannot run.
SUPPORTED_ENGINE_FORMAT = "ink"

#: The story format a game is written in. `"ink"` is the only value this
#: engine plays; the field exists so another engine can announce itself
#: rather than `.inkj` being assumed everywhere.
ENGINE_FORMAT_FIELD = "ENGINE_FORMAT"

#: The game's own version, author-declared. Nothing derives it — it is
#: how a save, a bundle, or a listing can say which build it came from.
GAME_VERSION_FIELD = "GAME_VERSION"

#: A sentence or two about what the game is, for a library picker or a
#: bundle's companion readme.
GAME_DESCRIPTION_FIELD = "GAME_DESCRIPTION"

#: The game's cover image, relative to the game folder. Declaring it
#: replaces `find_cover_image()`'s filename-and-extension probing.
COVER_IMAGE_FIELD = "COVER_IMAGE"

#: The game's prose stylesheet, relative to the game folder. Declaring it
#: replaces the hardcoded `styles.css` convention.
PROSE_STYLES_FIELD = "PROSE_STYLES"

#: A game's own declaration that it loads something over the network --
#: a CDN font, a remote image. Self-declared and advisory: nothing here
#: verifies it, and nothing restricts what a game may reach. An
#: application uses it to tell the player before they start.
#:
#: Absent means False, so a game that says nothing is treated as
#: self-contained.
USES_NETWORK_RESOURCES_FIELD = "USES_NETWORK_RESOURCES"

#: A Markdown file, relative to the game folder, explaining what the
#: game's plugins do and why running them needs permission. Shown when a
#: game that declares `REQUIRED_PLUGINS` has not been trusted.
#:
#: The game writes it because only the game knows what its plugins mean:
#: an application can list names, but not that a missing occupancy plugin means no
#: character is anywhere. A game declaring none gets the application's own
#: fallback, which lists the names.
#:
#: Optional, so `MANIFEST_VERSION` does not change: a reader that does not
#: know this field ignores it, which is the correct behaviour.
PLUGIN_DENIED_SCREEN_FIELD = "PLUGIN_DENIED_SCREEN"

#: The manifest field naming the media directories a game ships — a list
#: of directory paths relative to the game folder, e.g. `["Images", "UI"]`.
#: Each is bundled whole; a game with no media declares none.
MEDIA_DIRECTORIES_FIELD = "MEDIA_DIRECTORIES"

#: The manifest field naming extra files a game ships that nothing else
#: in the manifest implies — a prose stylesheet, a cover image, a font.
#: Paths relative to the game folder.
EXTRA_FILES_FIELD = "EXTRA_FILES"


class GameFolderError(Exception):
    """A game folder has no real, resolvable compiled story file."""


def check_manifest_supported(game_dir: GameSource | Path) -> None:
    """Check a game declares nothing this engine cannot honour.

    Two fields exist to be checked, and are worthless unchecked: a
    manifest written to a future schema would be read as this one and
    silently misinterpreted, and a game in another story format would be
    loaded as Ink and fail somewhere further in, with an error naming
    nothing useful. Both are caught here instead, before a game opens.

    A field a manifest omits is accepted: games predate both fields, and
    absence is not a claim about anything.

    Args:
        game_dir: The game's source, or its directory.

    Raises:
        GameFolderError: The manifest declares a schema version or a
            story format this engine does not support.
    """
    source = as_source(game_dir)

    version = read_manifest_version(game_dir)
    if version is not None and version > SUPPORTED_MANIFEST_VERSION:
        raise GameFolderError(
            f"Game '{source.name}' declares {MANIFEST_VERSION_FIELD} {version}, "
            f"but this engine understands up to {SUPPORTED_MANIFEST_VERSION} — it needs a newer player"
        )

    story_format = read_engine_format(game_dir)
    if story_format is not None and story_format != SUPPORTED_ENGINE_FORMAT:
        raise GameFolderError(
            f"Game '{source.name}' is written for the '{story_format}' story format, "
            f"which this engine cannot play (it plays '{SUPPORTED_ENGINE_FORMAT}')"
        )


def find_main_story_file(game_dir: GameSource | Path) -> str:
    """Return the compiled story a game declares.

    The manifest's `MAIN_STORY_FILE` names it. Nothing is scanned or
    guessed: a game folder holds its media and, often, the per-chapter
    files a build left beside the combined story, so inferring which one
    plays means walking content to answer a question the manifest already
    answers.

    Args:
        game_dir: The game's source, or its directory.

    Returns:
        The story's path, relative to the game's root.

    Raises:
        GameFolderError: The manifest declares no `MAIN_STORY_FILE`, or
            names one the game does not contain.
    """
    source = as_source(game_dir)
    main_story_file = _read_manifest_string_field(game_dir, "MAIN_STORY_FILE")
    if not main_story_file:
        raise GameFolderError(f"Game '{source.name}' declares no MAIN_STORY_FILE in {MANIFEST_FILENAME}")
    if not source.exists(main_story_file):
        raise GameFolderError(f"Game '{source.name}': MAIN_STORY_FILE '{main_story_file}' does not exist in it")
    return main_story_file


def read_uses_network_resources(game_dir: GameSource | Path) -> bool:
    """Read a game folder's own `USES_NETWORK_RESOURCES` declaration.

    Self-declared and advisory. Nothing here checks whether it is true,
    and nothing prevents a game from reaching the network whatever it
    says — a game's stylesheet is handed to the application as CSS text,
    and CSS can name a remote font.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        True only when the manifest declares the field as a YAML boolean
        true. Absent, or any other value, answers False: a game that says
        nothing is treated as self-contained.
    """
    return _read_manifest_field(game_dir, USES_NETWORK_RESOURCES_FIELD) is True


def read_play_layout(game_dir: GameSource | Path) -> str | None:
    """Read a game folder's own `PLAY_LAYOUT` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal string value assigned to `PLAY_LAYOUT`, or None if the
        manifest has no such field (or no manifest at all).
    """
    return _read_manifest_string_field(game_dir, PLAY_LAYOUT_FIELD)


def read_media_directories(game_dir: GameSource | Path) -> list[str]:
    """Read a game folder's own `MEDIA_DIRECTORIES` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal list of directory paths, or `[]` if the manifest has no
        such field (or no manifest at all, or a non-list value).
    """
    return _read_manifest_string_list_field(game_dir, MEDIA_DIRECTORIES_FIELD)


def read_extra_files(game_dir: GameSource | Path) -> list[str]:
    """Read a game folder's own `EXTRA_FILES` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal list of file paths, or `[]` if the manifest has no such
        field (or no manifest at all, or a non-list value).
    """
    return _read_manifest_string_list_field(game_dir, EXTRA_FILES_FIELD)


def read_manifest_version(game_dir: GameSource | Path) -> int | None:
    """Read the manifest's own schema version.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The declared version, or None if the manifest declares none (or
        declares a non-integer). A manifest with no version predates
        versioning; a caller decides whether that is acceptable.
    """
    value = _read_manifest_field(game_dir, MANIFEST_VERSION_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_engine_format(game_dir: GameSource | Path) -> str | None:
    """Read which story format this game is written in.

    Returns:
        The declared format (`"ink"`), or None if the manifest declares
        none — in which case a caller may assume Ink, since that is what
        every game predating this field is.
    """
    return _read_manifest_string_field(game_dir, ENGINE_FORMAT_FIELD)


def read_game_version(game_dir: GameSource | Path) -> str | None:
    """Read the game's own author-declared version, or None."""
    value = _read_manifest_field(game_dir, GAME_VERSION_FIELD)
    return str(value) if value is not _FIELD_NOT_FOUND and value is not None else None


def read_game_description(game_dir: GameSource | Path) -> str | None:
    """Read the game's own description, or None."""
    return _read_manifest_string_field(game_dir, GAME_DESCRIPTION_FIELD)


def read_cover_image(game_dir: GameSource | Path) -> str | None:
    """Read the game's declared cover image path, or None."""
    return _read_manifest_string_field(game_dir, COVER_IMAGE_FIELD)


def read_prose_styles(game_dir: GameSource | Path) -> str | None:
    """Read the game's declared prose stylesheet path, or None."""
    return _read_manifest_string_field(game_dir, PROSE_STYLES_FIELD)


def read_plugin_denied_screen(game_dir: GameSource | Path) -> str | None:
    """Read the game's declared plugin-denied screen path, or None."""
    return _read_manifest_string_field(game_dir, PLUGIN_DENIED_SCREEN_FIELD)


def find_plugin_denied_screen(game_dir: GameSource | Path) -> str | None:
    """Return the game's plugin-denied screen text, or None.

    Args:
        game_dir: The game's source, or its directory.

    Returns:
        The Markdown the game ships for this, or None when it declares
        none or names a file it does not contain -- a missing screen is a
        gap the application fills, never a reason a game cannot be opened.
    """
    source = as_source(game_dir)
    declared = read_plugin_denied_screen(source)
    if not declared or not source.exists(declared):
        return None
    try:
        return source.read_text(declared)
    except GameSourceError:
        return None


def plugin_denied_text(game_dir: GameSource | Path) -> str:
    """Return what to show when a game's plugins have not been trusted.

    The game's own screen when it ships one, else a plain listing of what
    it declares. An application renders the result as Markdown.

    Args:
        game_dir: The game's source, or its directory.

    Returns:
        Markdown. Never empty: a game with neither a screen nor declared
        plugins should not be reaching this, but says so rather than
        rendering blank.
    """
    source = as_source(game_dir)
    provided = find_plugin_denied_screen(source)
    if provided:
        return provided

    required = read_required_plugins(source)
    if not required:
        return "This game needs no plugins, so nothing needs your permission."

    names = "\n".join(f"- `{name}`" for name in required)
    return (
        f"## This game needs {len(required)} plugin"
        f"{'s' if len(required) != 1 else ''} to run\n\n"
        f"{names}\n\n"
        "These are real Python modules that ship with the game, and running "
        "the game runs them. They can do anything a program on this computer "
        "can do.\n\n"
        "The game does not explain what its own plugins do, so this list is "
        "all the detail available."
    )


def read_required_plugins(game_dir: GameSource | Path) -> list[str]:
    """Read a game folder's own `REQUIRED_PLUGINS` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal list of plugin-name strings assigned to
        `REQUIRED_PLUGINS`, or `[]` if the manifest has no such field (or
        no manifest at all, or a non-list/non-string-list value).
    """
    return _read_manifest_string_list_field(game_dir, REQUIRED_PLUGINS_FIELD)


def read_new_game_fields(game_dir: GameSource | Path) -> list[dict[str, Any]]:
    """Read a game's own `NEW_GAME_FIELDS`, the questions it asks first.

    Each entry names an Ink variable and how to ask for it. An
    application renders them; `if_session.character_creation` turns the
    answers into the variables the story reads.

    Args:
        game_dir: The game folder, or its source.

    Returns:
        The declared list, or `[]` when the manifest has no such field,
        has no manifest at all, or declares something that is not a list
        of mappings.
    """
    value = _read_manifest_field(game_dir, NEW_GAME_FIELDS_FIELD)
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, dict)]


#: Returned by `_read_manifest_field()` when the field is absent, the
#: manifest is missing/unparseable, or its value is not a plain literal
#: -- distinct from a real `None`/`False`/`0` a manifest might legitimately
#: assign, so a caller CAN tell "not found" apart from "found and is
#: `None`".
_FIELD_NOT_FOUND = object()


class ModuleLiterals(NamedTuple):
    """The result of `read_module_literals()`.

    Args:
        literals: `{name: literal value}` for every top-level assignment
            whose value is a Python literal.
        skipped: Every top-level assignment target whose value was NOT a
            plain literal (e.g. a function call, a name reference), for a
            caller that wants to react to a field it expected to be one.
    """

    literals: dict[str, Any]
    skipped: frozenset[str]


def read_module_literals(path: Path) -> ModuleLiterals:
    """Read every top-level literal assignment from one `.py` file, as data.

    Handles both plain assignment (`NAME = ...`) and annotated assignment
    (`NAME: Type = ...`); a bare annotation with no value contributes
    nothing. A name assigned a non-literal expression is omitted from
    `.literals` (see `.skipped`), never raised.

    Never imports or executes the file — `path` lives in untrusted
    content, so it is parsed as data via `ast.literal_eval` only.

    Args:
        path: The `.py` file to read.

    Returns:
        A `ModuleLiterals(literals, skipped)`. Both empty if the file
        doesn't exist, can't be parsed, or declares no assignments at all.
    """
    if not path.is_file():
        return ModuleLiterals({}, frozenset())
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ModuleLiterals({}, frozenset())
    return parse_module_literals(source, filename=str(path))


def parse_module_literals(source: str, *, filename: str = "<manifest>") -> ModuleLiterals:
    """Read every top-level literal assignment from Python source text.

    The text-level half of `read_module_literals()`, for a caller holding
    source that is not a file on disk -- a manifest read out of a bundle,
    say. Same contract: parsed as data, never imported or executed.

    Args:
        source: The Python source text.
        filename: Name used in parse errors only.

    Returns:
        A `ModuleLiterals(literals, skipped)`, both empty if `source` does
        not parse.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return ModuleLiterals({}, frozenset())

    literals: dict[str, Any] = {}
    skipped: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr]
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        elif isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        else:
            continue

        # A bare annotation (`NAME: dict[str, str]`) declares a type but
        # no value; there is nothing to evaluate, and nothing to skip —
        # this is not a field a game author was trying to give a value.
        if value_node is None:
            continue

        for target in targets:
            name = getattr(target, "id", None)
            if name is None:
                continue
            try:
                literals[name] = ast.literal_eval(value_node)
            except ValueError:
                skipped.add(name)
    return ModuleLiterals(literals, frozenset(skipped))


def read_manifest(game_dir: GameSource | Path) -> dict[str, Any]:
    """Read a game folder's whole manifest, in one parse.

    Every typed reader in this module goes through here, and the result
    is cached per path against the file's modification time — so a caller
    wanting five fields parses once, and an edited manifest is picked up
    without a restart.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        Every top-level key the manifest declares. Empty if the file is
        absent, unreadable, not a YAML mapping, or malformed — a game
        folder is untrusted content, so a bad manifest yields nothing
        rather than raising, and each typed reader applies its own
        absent-field policy.
    """
    source = as_source(game_dir)
    stamp = source.fingerprint(MANIFEST_FILENAME)
    if stamp == 0:
        return {}

    key = (source.name, id(source) if not isinstance(source, DirectoryGameSource) else str(source.root))
    cached = _MANIFEST_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    try:
        loaded = yaml.safe_load(source.read_text(MANIFEST_FILENAME))
    except (GameSourceError, yaml.YAMLError):
        return {}
    parsed: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
    _MANIFEST_CACHE[key] = (stamp, parsed)
    return parsed


def _read_manifest_field(game_dir: GameSource | Path, field_name: str) -> Any:
    """Read one field's raw value from the manifest.

    Returns `_FIELD_NOT_FOUND` if the manifest is missing, unparseable,
    or declares no such key.
    """
    return read_manifest(game_dir).get(field_name, _FIELD_NOT_FOUND)


def _read_manifest_string_field(game_dir: GameSource | Path, field_name: str) -> str | None:
    """Read one string field from the manifest.

    None if absent or declared as something other than a string.
    """
    value = _read_manifest_field(game_dir, field_name)
    return value if isinstance(value, str) else None


def _read_manifest_string_list_field(game_dir: GameSource | Path, field_name: str) -> list[str]:
    """Read one list-of-strings field from the manifest.

    Args:
        game_dir: The game folder's real filesystem path.
        field_name: The top-level manifest name to read.

    Returns:
        The literal list of strings assigned to `field_name`, or `[]` if
        absent or assigned something other than a list of strings.
    """
    value = _read_manifest_field(game_dir, field_name)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return []
