"""Plugin discovery: scan a flat, host-supplied list of sources and merge
the `Plugin` objects each one exposes.

No trust concept exists anywhere in this module -- every source given is
scanned unconditionally; deciding WHICH sources are safe to pass is
entirely the caller's responsibility. No distinction is made between
"generic" and "game-specific" sources either -- that split is purely a
convention in how the caller assembles its own sources list.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path
from types import ModuleType

from ink_engine.plugin import Plugin

#: The engine's own shipped plugin package — the generic, story-agnostic
#: mechanics available to every game, whichever one is loaded. Hosts pass
#: this as a source rather than each computing the same directory path.
ENGINE_PLUGIN_PACKAGE = "ink_engine.engine_plugins"


def make_game_folder_importable(game_dir: Path) -> str:
    """Make one game folder importable, and return its dotted name.

    A game folder is already a real package on disk; it needs only its
    parent on `sys.path` for ordinary import to find it. The insertion is
    idempotent and per distinct parent, so many game folders sharing one
    parent cost one entry.

    This is packaging, not permission: whether `game_dir` is safe to
    import is the host's decision, made before calling.

    Args:
        game_dir: The game folder's path (must contain `__init__.py`).

    Returns:
        The folder's bare name, ready to pass to `discover_plugins()`.
    """
    parent = str(game_dir.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return game_dir.name


def _plugins_from_module(module: ModuleType) -> list[Plugin]:
    """Return the `Plugin` objects a module exposes via a top-level
    `PLUGIN: Plugin` or `PLUGINS: list[Plugin]` attribute.

    A module with neither attribute contributes nothing -- it is plain
    library code, not itself discoverable (e.g. a plugin's own supporting
    dataclasses/helpers, imported directly by whichever plugin needs
    them, never scanned for a `Plugin` of their own).

    Args:
        module: The already-imported module to inspect.

    Returns:
        Zero or more `Plugin` objects, in declaration order (`PLUGIN`
        first if both are somehow set, then `PLUGINS`' own list order).
    """
    found: list[Plugin] = []
    single = getattr(module, "PLUGIN", None)
    if isinstance(single, Plugin):
        found.append(single)
    many = getattr(module, "PLUGINS", None)
    if isinstance(many, list):
        found.extend(p for p in many if isinstance(p, Plugin))
    return found


def _plugins_from_source(source: str) -> list[Plugin]:
    """Import one dotted name and return every `Plugin` it exposes.

    A plain MODULE is simply scanned. A PACKAGE is scanned first, and if
    its own `__init__.py` declares plugins that is taken as its COMPLETE
    answer -- a game folder that re-exports its submodules' plugins as
    one `PLUGINS` list has already said what it offers, and walking its
    submodules as well would find each of them twice. Only a package
    that declares nothing itself is walked one level deep, each `.py`
    file inside it imported by its real dotted path and scanned. Modules
    whose name begins with `_` are skipped as private.

    Args:
        source: An importable dotted name — either a package
            (`"ink_engine.engine_plugins"`, `"mygame"`) or a single
            module (`"mygame.plugins"`).

    Returns:
        Every `Plugin` found, in import order.
    """
    module = importlib.import_module(source)
    declared = _plugins_from_module(module)

    search_paths = getattr(module, "__path__", None)
    if search_paths is None or declared:
        return declared

    found: list[Plugin] = []
    for module_info in pkgutil.iter_modules(list(search_paths)):
        if module_info.name.startswith("_"):
            continue
        found.extend(_plugins_from_module(importlib.import_module(f"{source}.{module_info.name}")))
    return found


def discover_plugins(sources: list[str]) -> dict[str, Plugin]:
    """Scan every source and merge the `Plugin` objects each one exposes.

    Args:
        sources: Importable dotted names, each a package or a single
            module (see `_plugins_from_source` for how each is scanned).
            Results merge in the order given. Making a name importable is
            the caller's job: for a folder outside the import path, call
            `make_game_folder_importable()` first and pass what it
            returns.

    Returns:
        Every discovered `Plugin`, keyed by its own `name`.

    Raises:
        ValueError: two sources declare a `Plugin` with the same `name`.
        ModuleNotFoundError: a source names something not importable.
    """
    plugins: dict[str, Plugin] = {}
    for source in sources:
        for plugin in _plugins_from_source(source):
            if plugin.name in plugins:
                raise ValueError(f"Duplicate plugin name '{plugin.name}' (from source '{source}')")
            plugins[plugin.name] = plugin
    return plugins
