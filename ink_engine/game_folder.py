"""Resolving a game folder's own compiled story file and reading a small,
fixed set of single-field manifest values.

A game is unplayable without a real, existing compiled `.inkj` (compiled
`.ink.json`) file, and there is no way around that requirement here —
this engine has no Ink compiler of its own, and compiling one from
source would need a real Ink compiler like `inklecate` present, which
this module deliberately does not attempt.

`_read_manifest_string_field()` below is a shared helper for reading a
single named field out of a game folder's `__init__.py` manifest,
deliberately NOT a general-purpose manifest parser — a host application
needing other manifest data is expected to bring its own reader.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

#: The compiled-story file extension this engine plays. `.ink` (uncompiled
#: source) is never accepted here — see this module's own docstring.
COMPILED_STORY_SUFFIX = ".inkj"

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


class GameFolderError(Exception):
    """A game folder has no real, resolvable compiled story file."""


def find_main_story_file(game_dir: Path) -> Path:
    """Return a game folder's own compiled story file.

    If exactly one `.inkj` file exists directly under `game_dir`, that
    file is assumed to be the story — no manifest read needed at all, the
    common case for a real game folder. Only when the folder has zero or
    more than one `.inkj` file does this fall back to reading
    `MAIN_STORY_FILE` from `__init__.py`'s own manifest (parsed via `ast`,
    never imported — a game folder is untrusted content, matching every
    other manifest read in this library), to disambiguate which one is
    authoritative — any other `.inkj` file present is not a valid
    fallback.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The resolved, real compiled story file's path.

    Raises:
        GameFolderError: No `.inkj` file could be resolved — the folder
            has zero, or more than one with no `MAIN_STORY_FILE` (or a
            `MAIN_STORY_FILE` naming a file that does not exist) to
            disambiguate. A `.ink` (uncompiled source) file present with
            no compiled counterpart is exactly this case: it is not a
            valid story on its own, regardless of how it got there.
    """
    candidates = sorted(game_dir.glob(f"*{COMPILED_STORY_SUFFIX}"))
    if len(candidates) == 1:
        return candidates[0]

    main_story_file = _read_manifest_string_field(game_dir, "MAIN_STORY_FILE")
    if not main_story_file:
        if not candidates:
            raise GameFolderError(f"Game folder '{game_dir.name}' has no {COMPILED_STORY_SUFFIX} file and no MAIN_STORY_FILE in __init__.py")
        raise GameFolderError(
            f"Game folder '{game_dir.name}' has {len(candidates)} {COMPILED_STORY_SUFFIX} files "
            "and no MAIN_STORY_FILE in __init__.py to disambiguate which one is the real story"
        )

    main_story_path = game_dir / main_story_file
    if not main_story_path.is_file():
        raise GameFolderError(f"Game folder '{game_dir.name}': MAIN_STORY_FILE '{main_story_file}' does not exist in this folder")
    return main_story_path


def read_play_layout(game_dir: Path) -> str | None:
    """Read a game folder's own `PLAY_LAYOUT` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal string value assigned to `PLAY_LAYOUT`, or None if the
        manifest has no such field (or no manifest at all). Falling back
        to a default layout name for None is the caller's own decision —
        this function has no opinion on what layouts exist or which one
        is default, matching how `ink_engine` has no host-UI opinions
        anywhere else in this library.
    """
    return _read_manifest_string_field(game_dir, PLAY_LAYOUT_FIELD)


def read_required_plugins(game_dir: Path) -> list[str]:
    """Read a game folder's own `REQUIRED_PLUGINS` manifest field, if any.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The literal list of plugin-name strings assigned to
        `REQUIRED_PLUGINS`, or `[]` if the manifest has no such field (or
        no manifest at all, or a non-list/non-string-list value).
    """
    return _read_manifest_string_list_field(game_dir, REQUIRED_PLUGINS_FIELD)


#: Returned by `_read_manifest_field()` when the field is absent, the
#: manifest is missing/unparseable, or its value is not a plain literal
#: -- distinct from a real `None`/`False`/`0` a manifest might legitimately
#: assign, so a caller can tell "not found" apart from "found and is
#: `None`".
_FIELD_NOT_FOUND = object()


def _read_manifest_field(game_dir: Path, field_name: str) -> Any:
    """Read one literal field's raw value from `game_dir/__init__.py`, as data.

    Scoped to reading exactly one named field at a time — not a
    general-purpose manifest reader (a host application needing other
    manifest data is expected to bring its own reader). Shared by every
    public single-field reader in this module (`find_main_story_file()`'s
    own `MAIN_STORY_FILE` read, `read_play_layout()`, `read_required_plugins()`)
    rather than each writing its own one-off `ast`-parsing loop; each
    caller does its own type check on the result.

    Args:
        game_dir: The game folder's real filesystem path.
        field_name: The top-level manifest name to read (e.g.
            `"MAIN_STORY_FILE"`, `"PLAY_LAYOUT"`, `"REQUIRED_PLUGINS"`).

    Returns:
        The literal value assigned to `field_name` at the top level of
        `__init__.py`, or `_FIELD_NOT_FOUND` if the file is missing,
        cannot be parsed, or assigns no such name to a literal value.
    """
    init_path = game_dir / "__init__.py"
    if not init_path.is_file():
        return _FIELD_NOT_FOUND
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except (SyntaxError, UnicodeDecodeError):
        return _FIELD_NOT_FOUND

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == field_name for target in node.targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except ValueError:
            return _FIELD_NOT_FOUND
    return _FIELD_NOT_FOUND


def _read_manifest_string_field(game_dir: Path, field_name: str) -> str | None:
    """Read one literal string field from `game_dir/__init__.py`.

    Args:
        game_dir: The game folder's real filesystem path.
        field_name: The top-level manifest name to read.

    Returns:
        The literal string value assigned to `field_name`, or None if
        absent or assigned something other than a string.
    """
    value = _read_manifest_field(game_dir, field_name)
    return value if isinstance(value, str) else None


def _read_manifest_string_list_field(game_dir: Path, field_name: str) -> list[str]:
    """Read one literal list-of-strings field from `game_dir/__init__.py`.

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
