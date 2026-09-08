"""ink_engine -- a standalone, Django-free Ink interactive-fiction interpreter
and plugin engine.

Public surface (populated as Steps 1-4 of the extraction plan land):
    - engine: the Ink interpreter itself (InkRuntimeState, load_story_root, ...)
    - plugin: Plugin, EngineState
    - discovery: discover_plugins
    - binding: resolve_bindings
"""

from __future__ import annotations

__all__: list[str] = []
