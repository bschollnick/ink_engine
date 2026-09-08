"""The plugin contract: one dataclass, no trust concept, no host-UI
awareness. See claude_docs/plans/ink_engine_standalone_extraction.md in the
QuickBBS repository for the design rationale (the OLD system's
EngineAPIDescriptor/PluginContext/synthetic-namespace machinery this
replaces, and why each cut was made).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: A game session's persisted state, keyed by each stateful plugin's own
#: `state_key`. A plain dict -- no wrapper class. A plugin reading another
#: plugin's slice does `engine_state.get(other_plugin.state_key, {})`
#: directly; there is no dynamic ownership-resolution mechanism, since the
#: owning plugin's state_key is always known statically by whoever imports
#: it (see the design doc's "also_reads was dead generality" finding).
EngineState = dict[str, Any]


@dataclass(frozen=True)
class Plugin:
    """A discoverable ink_engine plugin.

    A plugin with no `init_state`/`bind` is a pure-function plugin -- its
    `bindings` dict is complete on its own (e.g. a plugin exposing only
    stateless EXTERNAL functions with no per-session data). A plugin that
    also sets `state_key`/`init_state`/`bind` additionally owns one named
    slice of the running game's `EngineState`.

    ink_engine has no concept of trust, host UI features (sidebars,
    panels), or config storage -- deciding which sources are safe to load
    at all is entirely the host application's job, upstream of ever
    calling `discover_plugins()`. `validate_config` is a contract slot the
    HOST calls when it owns config storage (e.g. QuickBBS's own
    `StorySystemConfig.clean()`); ink_engine itself never calls it.

    Attributes:
        name: A unique, stable identifier for this plugin (e.g.
            "scheduling"). Referenced by a host's own config-opt-in
            storage; must be unique across every source a single
            `discover_plugins()` call scans.
        display_name: A human-readable label, for a host's own admin/UI
            surfaces. Never read by ink_engine itself.
        bindings: This plugin's stateless EXTERNAL functions, keyed by the
            Ink function name they implement.
        validate_config: An optional validator for whatever config shape
            a host lets an author attach to this plugin. Called by the
            HOST, never by ink_engine.
        state_key: The key this plugin's own state occupies in a
            session's `EngineState`, or `None` for a stateless plugin.
        init_state: Returns this plugin's own fresh state dict the first
            time a session touches it, or `None` for a stateless plugin.
        bind: `(own_state, engine_state) -> dict[str, Callable]` --
            builds this plugin's stateful EXTERNAL bindings. Always this
            exact two-argument shape; a plugin needing another plugin's
            state reads `engine_state.get(other_state_key, {})` directly
            inside its own `bind`. `None` for a stateless plugin.

    Raises:
        ValueError: `state_key`/`init_state`/`bind` are not all set
            together or all left unset (enforced in `__post_init__`).
    """

    name: str
    display_name: str
    bindings: dict[str, Callable[..., Any]] = field(default_factory=dict)
    validate_config: Callable[[Any], None] | None = None
    state_key: str | None = None
    init_state: Callable[[], dict[str, Any]] | None = None
    bind: Callable[[dict[str, Any], EngineState], dict[str, Callable[..., Any]]] | None = None

    def __post_init__(self) -> None:
        stateful_fields = (self.state_key, self.init_state, self.bind)
        if any(stateful_fields) and not all(stateful_fields):
            raise ValueError(f"Plugin '{self.name}': state_key/init_state/bind must all be set together or not at all")
