"""ink_engine -- a standalone Ink interactive-fiction interpreter and plugin
engine, with no web framework or database of its own.

Public surface:
    - engine: the Ink interpreter itself (InkRuntimeState, load_story_root, ...)
    - plugin: Plugin, EngineState
    - discovery: discover_plugins
    - binding: resolve_bindings
"""

from __future__ import annotations

__all__: list[str] = []
