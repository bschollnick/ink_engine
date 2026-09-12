"""Calling a game's own side-panel hooks.

A game folder may ship a `sidebar.py` exposing `panel_context()`,
`panel_action()` and `panel_command()`; a host renders whatever data they
return beside the story text. This module is the shared calling
convention, so every host invokes them identically.

A hook supplies data, never markup -- what a host renders from it is its
own business. This module never imports a game's code: it calls a module
the host already imported, having made its own trust decision upstream.
Every hook is optional, and one that raises is logged and treated as
absent, so a decorative panel cannot take down the story.
"""

from __future__ import annotations

import logging
from types import ModuleType
from typing import Any

from ink_engine.plugin import EngineState

#: The names a game's own `sidebar.py` may define. A game defines the ones
#: it wants; every one is optional.
PANEL_CONTEXT_HOOK = "panel_context"
PANEL_ACTION_HOOK = "panel_action"
PANEL_COMMAND_HOOK = "panel_command"


def run_panel_hook(
    module: ModuleType | None,
    hook_name: str,
    *,
    engine_state: EngineState,
    globals_: dict[str, Any],
    bindings: dict[str, Any],
    default: Any,
    logger: logging.Logger | None = None,
    **extra_args: str,
) -> Any:
    """Call one of a game's own panel hooks, or answer `default`.

    Hooks are invoked by keyword, so each author's parameter order is
    their own business and a wrong name fails loudly instead of binding
    the wrong value by position.

    Args:
        module: The game's already-imported `sidebar` module, or None.
        hook_name: Which hook to call -- one of the `*_HOOK` constants.
        engine_state: The session's live plugin-state dict. A hook may
            mutate it; `panel_command` is expected to.
        globals_: The runtime's Ink globals, likewise mutable.
        bindings: The session's real EXTERNAL bindings, so a hook can ask
            what the story can.
        default: The answer when the hook is absent, raises, or answers
            the wrong type. Also fixes that expected type: the hook's
            answer must be an instance of `type(default)`, with None
            meaning any dict.
        logger: Where to report a raising hook.
        **extra_args: Further named arguments this hook takes.

    Returns:
        The hook's answer if it ran and matched the expected type, else
        `default`.
    """
    hook = getattr(module, hook_name, None) if module is not None else None
    if not callable(hook):
        return default

    try:
        result = hook(engine_state=engine_state, globals_=globals_, bindings=bindings, **extra_args)
    except Exception:  # pylint: disable=broad-except
        (logger or logging.getLogger(__name__)).exception("ink_engine.game_panel: %s failed; treating the panel as absent", hook_name)
        return default

    expected_type = dict if default is None else type(default)
    return result if isinstance(result, expected_type) else default


def panel_context(
    module: ModuleType | None,
    *,
    engine_state: EngineState,
    globals_: dict[str, Any],
    bindings: dict[str, Any],
    logger: logging.Logger | None = None,
) -> dict[str, Any] | None:
    """Ask a game for the data its side panel should render.

    Read-only by contract: nothing returned here is persisted.

    Args:
        module: The game's `sidebar` module, or None.
        engine_state: The session's live plugin-state dict.
        globals_: The runtime's Ink globals.
        bindings: The session's real EXTERNAL bindings.
        logger: Where to report a raising hook.

    Returns:
        The panel's data, or None when this game supplies no panel.
    """
    return run_panel_hook(
        module,
        PANEL_CONTEXT_HOOK,
        engine_state=engine_state,
        globals_=globals_,
        bindings=bindings,
        default=None,
        logger=logger,
    )


def panel_action(
    module: ModuleType | None,
    *,
    engine_state: EngineState,
    globals_: dict[str, Any],
    bindings: dict[str, Any],
    action_id: str,
    target_id: str,
    logger: logging.Logger | None = None,
) -> str:
    """Run one of a panel's read-only row actions (e.g. "examine").

    Args:
        module: The game's `sidebar` module, or None.
        engine_state: The session's live plugin-state dict.
        globals_: The runtime's Ink globals.
        bindings: The session's real EXTERNAL bindings.
        action_id: Which action the row offered.
        target_id: What it was invoked on.
        logger: Where to report a raising hook.

    Returns:
        The text to show, or "" when unrecognised or unavailable.
    """
    return run_panel_hook(
        module,
        PANEL_ACTION_HOOK,
        engine_state=engine_state,
        globals_=globals_,
        bindings=bindings,
        default="",
        logger=logger,
        action_id=action_id,
        target_id=target_id,
    )


def panel_command(
    module: ModuleType | None,
    *,
    engine_state: EngineState,
    globals_: dict[str, Any],
    bindings: dict[str, Any],
    command_id: str,
    target_id: str,
    logger: logging.Logger | None = None,
) -> str:
    """Run one of a panel's state-changing commands (e.g. "use", "cast").

    Expected to mutate `engine_state`, and may mutate `globals_`; a host
    persists both as it would after a mid-turn binding call. Does not
    advance the story -- a panel command is not a choice.

    Args:
        module: The game's `sidebar` module, or None.
        engine_state: The session's live plugin-state dict.
        globals_: The runtime's Ink globals.
        bindings: The session's real EXTERNAL bindings.
        command_id: Which command the row offered.
        target_id: What it was invoked on.
        logger: Where to report a raising hook.

    Returns:
        A short result message, or "" when unrecognised or unavailable.
        A raising command answers "" and may leave state partly mutated,
        as a raising EXTERNAL binding mid-turn would.
    """
    return run_panel_hook(
        module,
        PANEL_COMMAND_HOOK,
        engine_state=engine_state,
        globals_=globals_,
        bindings=bindings,
        default="",
        logger=logger,
        command_id=command_id,
        target_id=target_id,
    )
