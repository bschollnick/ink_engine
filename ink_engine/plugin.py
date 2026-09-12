"""The plugin contract: one dataclass, no trust concept, no host-UI
awareness.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

#: A game session's persisted state, keyed by each stateful plugin's own
#: `state_key`. A plain dict, so a host can persist it as JSON.
#:
#: The KEYS are contract (each plugin publishes its own `STATE_KEY`); what
#: a plugin stores UNDER its key is private to that plugin. Reach a
#: plugin's own data through the accessor it publishes, never by indexing
#: into its stored shape -- otherwise a plugin cannot change how it
#: serializes without breaking every consumer that guessed.
EngineState = dict[str, Any]

#: A story's compiled LIST definitions: `{list_name: {item_name: value}}`,
#: as produced by `ink_engine.engine.load_list_defs()`. Identical for every
#: session of a given story and never mutated.
ListDefs = dict[str, dict[str, int]]

#: What a binding returns when it has nothing to say. Ink has no void
#: EXTERNAL: every bound function must return something, and a story
#: calling one with `~` discards it. The value is arbitrary, which is
#: exactly why it should be named once -- engine plugins returned 1 and
#: game plugins 0 for the same "no answer", and a reader could not tell
#: whether the difference meant anything.
VOID = 1

#: One question a plugin can answer about its own state, given that
#: plugin's own slot and whatever arguments the question takes.
StateQuery = Callable[..., Any]


@dataclass(frozen=True)
class Plugin:
    """A discoverable ink_engine plugin.

    Setting `state_key`/`init_state`/`bind` (all three, or none) makes a
    plugin stateful: it owns one named slice of the session's
    `EngineState`. Otherwise `bindings` is its complete surface.

    ink_engine has no concept of trust, host UI, or config storage.

    Attributes:
        name: Unique, stable identifier, e.g. "scheduling". Must be
            unique across every source one `discover_plugins()` call
            scans.
        display_name: Human-readable label for a host's own UI. Never
            read by ink_engine.
        bindings: Stateless EXTERNAL functions, keyed by the Ink function
            name each implements.
        validate_config: Optional validator for whatever config shape a
            host attaches to this plugin. Called by the host, never here.
        state_key: Where this plugin's state lives in `EngineState`, or
            None when stateless.

            It need not equal `name`, and two plugins may share one key
            deliberately -- a game's plugin extending a generic one
            operates on the same store. So `EngineState` keys are not a
            list of active plugin names; deriving one from the other
            activates the wrong plugin. Plugins sharing a key merge in
            `active_names` order, so a later one's bindings win a
            collision: that is how a game overrides a generic binding.
        init_state: `(config) -> dict`, building this plugin's fresh state
            on first use, or None when stateless. Set with `state_key`,
            never alone. `config` is the host's config for this plugin,
            `default_config` when the host attaches none, or None; a
            plugin that seeds nothing ignores it.

            A plugin may own state without binding anything: one whose
            data exists for a dependent plugin to read has state_key and
            init_state but no `bind`. Requiring a no-op `bind` for that
            case only obscured which plugins really answer Ink calls.
        default_config: What `init_state` is given when the host attaches
            no config. A plugin whose fresh slot needs seeding declares it
            here so that, when it shares a slot with another plugin, the
            allocation step knows which of them builds the slot.
        bind: `(own_state, engine_state, list_defs) -> dict[str, Callable]`,
            building the stateful bindings; None when stateless. Always
            this exact shape, used or not, so nothing dispatches on what a
            plugin declares and a wrong signature fails at bind time. Read
            another plugin's state with
            `engine_state.get(other_state_key, {})`.

            `list_defs` is the story's compiled LIST tables. It is an
            argument rather than an `engine_state` entry so it has no
            lifetime beyond the call: it cannot be read late from a
            closure, and cannot reach a host's saved data.
        queries: Questions this plugin can answer about its own state,
            by name. Each takes this plugin's own slot followed by the
            question's arguments, and answers from the plugin's accessor
            rather than from any caller-supplied path.

            This is what lets declarative data -- a schedule rule, say --
            ask about a plugin without naming how it stores anything. A
            plugin that publishes no queries simply cannot be asked, which
            is the right default for one whose state is nobody else's
            business.

    Raises:
        ValueError: `state_key` and `init_state` are not set together, or
            `bind` is set without them.
    """

    name: str
    display_name: str
    bindings: dict[str, Callable[..., Any]] = field(default_factory=dict)
    validate_config: Callable[[Any], None] | None = None
    state_key: str | None = None
    init_state: Callable[[Any], dict[str, Any]] | None = None
    bind: Callable[[dict[str, Any], EngineState, ListDefs], dict[str, Callable[..., Any]]] | None = None
    queries: dict[str, StateQuery] = field(default_factory=dict)
    default_config: Any = None

    def __post_init__(self) -> None:
        owns_state = (self.state_key, self.init_state)
        if any(owns_state) and not all(owns_state):
            raise ValueError(f"Plugin '{self.name}': state_key and init_state must be set together or not at all")
        if self.bind is not None and not all(owns_state):
            raise ValueError(f"Plugin '{self.name}': bind needs state_key and init_state — it is handed the state they declare")
