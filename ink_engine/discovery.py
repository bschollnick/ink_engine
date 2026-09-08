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


def _scan_directory(directory: Path) -> list[Plugin]:
    """Scan a directory of independent `.py` files (a real Python
    package already on `sys.path` -- e.g. `ink_engine`'s own
    `engine_plugins/`), importing each by its ordinary dotted path.

    No `importlib.util.spec_from_file_location` anywhere here -- this
    path is only ever used for files genuinely inside an already-
    importable package, never for loading something outside the Python
    import system by raw filesystem path (see module docstring; that
    concern is pushed entirely to the caller, via module-mode sources).

    Args:
        directory: A real package directory (must have an `__init__.py`
            already importable via the normal Python import system).

    Returns:
        Every `Plugin` declared by any `.py` file directly inside it.
    """
    package_name = _package_name_for(directory)
    found: list[Plugin] = []
    for module_info in pkgutil.iter_modules([str(directory)]):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        found.extend(_plugins_from_module(module))
    return found


def _package_name_for(directory: Path) -> str:
    """Resolve a directory's own real, already-importable dotted package
    name, by finding it in `sys.modules` via its `__init__.py`'s package.

    Args:
        directory: A directory expected to already be a real, imported
            Python package (has an `__init__.py`, was imported via the
            ordinary Python import system before `discover_plugins()` was
            ever called with it).

    Returns:
        The dotted package name.

    Raises:
        ValueError: `directory` has no `__init__.py`, or is not a
            package Python has already imported (never resolved by raw
            filesystem inspection -- if it isn't already importable, it
            was never a valid directory-mode source to begin with).
    """
    init_file = directory / "__init__.py"
    if not init_file.exists():
        raise ValueError(f"'{directory}' has no __init__.py -- not a real Python package, cannot be scanned as a directory source")

    for name, module in sys.modules.items():
        module_file = getattr(module, "__file__", None)
        if module_file is not None and Path(module_file).resolve() == init_file.resolve():
            return name
    raise ValueError(f"'{directory}' is not an already-imported Python package -- import it before passing it to discover_plugins()")


def discover_plugins(sources: list[Path | str]) -> dict[str, Plugin]:
    """Scan every source and merge the `Plugin` objects each one exposes.

    Args:
        sources: Each entry is either a `Path` to a directory of
            independent `.py` files (a real, already-importable Python
            package -- each file scanned for a top-level `PLUGIN: Plugin`
            or `PLUGINS: list[Plugin]`), or a `str` naming a single
            already-importable dotted module (imported via plain
            `importlib.import_module`, then scanned the same way). No
            source is ever treated specially based on its origin -- the
            caller decides what to pass and in what order; results are
            merged as given. Making anything importable at all (via
            `sys.path`, a real install, or any other means) is entirely
            the caller's responsibility -- this function never does more
            than one `importlib.import_module()` call per module-mode
            source, and never touches the filesystem directly for a
            module-mode source at all.

    Returns:
        Every discovered `Plugin`, keyed by its own `name`.

    Raises:
        ValueError: two sources declare a `Plugin` with the same `name`.
    """
    plugins: dict[str, Plugin] = {}
    for source in sources:
        found = _scan_directory(source) if isinstance(source, Path) else _plugins_from_module(importlib.import_module(source))
        for plugin in found:
            if plugin.name in plugins:
                raise ValueError(f"Duplicate plugin name '{plugin.name}' (from source '{source}')")
            plugins[plugin.name] = plugin
    return plugins
