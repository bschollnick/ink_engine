"""Binding resolution: build the real Ink EXTERNAL bindings dict for one
game session from a fixed set of active plugins.

ink_engine has no opinion on enable/disable, trust, or per-story opt-in --
the caller decides exactly which plugin names are active for this session
and hands them in as `active_names`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from ink_engine.plugin import EngineState, Plugin


def resolve_bindings(
    plugins: dict[str, Plugin],
    active_names: Iterable[str],
    engine_state: EngineState,
) -> dict[str, Callable[..., Any]]:
    """Build the real EXTERNAL bindings for one game session.

    For each name in `active_names` (already filtered/ordered by the
    caller -- ink_engine has no opinion on enable/disable, trust, or
    per-story opt-in; those are host concerns), merge that plugin's
    stateless `bindings`, and if it declares `bind`, allocate
    `engine_state[state_key]` via `init_state()` on first use and call
    `plugin.bind(own_state, engine_state)` -- always this exact
    two-argument shape, regardless of what the plugin itself does or
    does not read from `engine_state`.

    Args:
        plugins: Every discoverable plugin, by name (typically
            `discover_plugins()`'s own return value).
        active_names: Exactly which plugin names should contribute
            bindings to this session, in the order their bindings should
            be merged (a later name's bindings win on a key collision,
            matching plain dict.update() semantics).
        engine_state: The session's own mutable, JSON-safe state dict.
            Mutated in place by any stateful plugin's own
            `init_state()`/`bind()` -- the caller's own reference already
            reflects every write once this call is done.

    Returns:
        The real bindings dict for this session.

    Raises:
        KeyError: `active_names` names a plugin not present in `plugins`
            -- a real, loud misconfiguration (a name the host itself
            promised was active but never actually resolved via
            discovery), never silently skipped.
    """
    resolved: dict[str, Callable[..., Any]] = {}
    for name in active_names:
        plugin = plugins[name]
        resolved.update(plugin.bindings)
        if plugin.bind is not None:
            assert plugin.state_key is not None and plugin.init_state is not None  # enforced by Plugin.__post_init__
            own_state = engine_state.setdefault(plugin.state_key, plugin.init_state())
            resolved.update(plugin.bind(own_state, engine_state))
    return resolved
