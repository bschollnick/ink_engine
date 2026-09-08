"""Generic, game-agnostic engine plugins that ship with ink_engine itself.

Each module here may declare a top-level `PLUGIN: Plugin` (or `PLUGINS:
list[Plugin]`) for discover_plugins() to find. A module with no such
declaration is plain library code, imported directly by whichever plugin
or host application needs it -- not every file here is itself discoverable.
"""

from __future__ import annotations
