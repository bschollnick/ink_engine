"""Resolving a game folder's own compiled story file and reading literal
values out of a game folder's own `.py` files (manifest or otherwise).

A game needs a real, existing compiled `.inkj` file: this engine has no
Ink compiler of its own.

`read_module_literals()` is the shared primitive every reader here builds
on: every top-level literal assignment in one `.py` file, read as data
via `ast` — **never imported or exec'd, since a game folder is untrusted
content**.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, NamedTuple

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
    file is the story. Only with zero or several does this fall back to
    `MAIN_STORY_FILE` in `__init__.py` (parsed via `ast`, never imported
    — a game folder is untrusted content).

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The resolved, real compiled story file's path.

    Raises:
        GameFolderError: No `.inkj` file could be resolved — zero, or
            several with no usable `MAIN_STORY_FILE` to disambiguate. An
            uncompiled `.ink` with no compiled counterpart is this case.
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
        manifest has no such field (or no manifest at all).
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
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
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


def _read_manifest_field(game_dir: Path, field_name: str) -> Any:
    """Read one literal field's raw value from `game_dir/__init__.py`, as data.

    Returns `_FIELD_NOT_FOUND` if the file is missing, cannot be parsed,
    or assigns no such name to a literal value.
    """
    return read_module_literals(game_dir / "__init__.py").literals.get(field_name, _FIELD_NOT_FOUND)


def _read_manifest_string_field(game_dir: Path, field_name: str) -> str | None:
    """Read one literal string field from `game_dir/__init__.py`.

    None if absent or assigned something other than a string.
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
