"""Binding resolution: build the real Ink EXTERNAL bindings dict for one
game session from a fixed set of active plugins.

ink_engine has no opinion on enable/disable, trust, or per-story opt-in --
the caller decides exactly which plugin names are active for this session
and hands them in as `active_names`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

from ink_engine.plugin import EngineState, ListDefs, Plugin


class AmbiguousSlotConfigError(ValueError):
    """Two plugins sharing one slot both claim to seed it."""


def _config_for(plugin: Plugin, name: str, application_configs: Mapping[str, Any]) -> Any:
    """Return the config a plugin would seed its slot from, or None.

    An application entry that is empty (`{}` or None) means "nothing attached"
    and defers to the plugin's own `default_config`.

    Args:
        plugin: The plugin.
        name: Its activation name, the key an application stores config under.
        application_configs: Config per plugin name, from the application.

    Returns:
        The application's config, else `plugin.default_config`, else None.
    """
    attached = application_configs.get(name)
    if attached not in (None, {}):
        return attached
    return plugin.default_config


def allocate_state(
    plugins: Mapping[str, Plugin],
    active_names: Iterable[str],
    engine_state: EngineState,
    *,
    configs: Mapping[str, Any] | None = None,
) -> None:
    """Allocate every missing slot, independent of activation order.

    Of the active plugins sharing one slot, those carrying a config (a
    application entry, else `default_config`) are its seeders. Exactly one seeder
    builds the slot with `validate_config(config)` then
    `init_state(config)`; with no seeder the first tenant builds it from
    `init_state(None)`; two seeders is an error, since whichever won would
    be an accident of ordering. A slot already present (a resumed save) is
    left alone: no validation, no re-seeding.

    Args:
        plugins: Every discoverable plugin, by name.
        active_names: Which plugins contribute to this session.
        engine_state: The session's mutable, JSON-safe state dict.
        configs: Config per plugin name, from the application, or None.

    Raises:
        KeyError: `active_names` holds a plugin discovery never found.
        AmbiguousSlotConfigError: Two tenants of one slot both carry a
            config.
        SystemConfigValidationError: A config failed its plugin's
            validator.
    """
    application_configs: Mapping[str, Any] = configs if configs is not None else {}
    tenants: dict[str, list[tuple[str, Plugin]]] = {}
    for name in active_names:
        plugin = plugins[name]
        if plugin.state_key is not None and plugin.init_state is not None and plugin.state_key not in engine_state:
            tenants.setdefault(plugin.state_key, []).append((name, plugin))
    for state_key, owners in tenants.items():
        seeders = [(name, plugin, config) for name, plugin in owners if (config := _config_for(plugin, name, application_configs)) is not None]
        if len(seeders) > 1:
            seeder_names = ", ".join(repr(name) for name, _, _ in seeders)
            raise AmbiguousSlotConfigError(
                f"slot '{state_key}' has more than one config-bearing plugin active ({seeder_names}); activate one, or give only one a config"
            )
        if seeders:
            _, plugin, config = seeders[0]
            if plugin.validate_config is not None:
                plugin.validate_config(config)
        else:
            _, plugin = owners[0]
            config = None
        assert plugin.init_state is not None  # every tenant was filtered on it
        engine_state[state_key] = plugin.init_state(config)


def resolve_bindings(
    plugins: Mapping[str, Plugin],
    active_names: Iterable[str],
    engine_state: EngineState,
    *,
    list_defs: ListDefs | None = None,
    configs: Mapping[str, Any] | None = None,
) -> dict[str, Callable[..., Any]]:
    """Build the real EXTERNAL bindings for one game session.

    Two phases: `allocate_state()` creates every slot the active plugins
    own, so allocation never depends on the order names are given in;
    then each active plugin's bindings are merged in order.

    Args:
        plugins: Every discoverable plugin, by name.
        active_names: Which plugins contribute to this session, in merge
            order -- a later name's bindings win a key collision.
        engine_state: The session's mutable, JSON-safe state dict,
            written in place by any stateful plugin.
        list_defs: The story's compiled LIST definitions, passed to every
            `bind()`. Omit only when no story is in play: a plugin given
            `{}` answers as though the story declared no LISTs.
        configs: Config per plugin name, from the application's own store, or
            None when the application keeps none; every plugin then seeds from
            its `default_config`.

    Returns:
        The bindings dict for this session.

    Raises:
        KeyError: `active_names` holds a plugin discovery never found.
        AmbiguousSlotConfigError: See `allocate_state()`.
        SystemConfigValidationError: A config failed its plugin's
            validator.
    """
    names = list(active_names)
    allocate_state(plugins, names, engine_state, configs=configs)
    resolved: dict[str, Callable[..., Any]] = {}
    tables: ListDefs = list_defs if list_defs is not None else {}
    for name in names:
        plugin = plugins[name]
        resolved.update(plugin.bindings)
        if plugin.bind is not None:
            assert plugin.state_key is not None  # enforced by Plugin.__post_init__
            resolved.update(plugin.bind(engine_state[plugin.state_key], engine_state, tables))
    return resolved


class ManifestMismatchError(ValueError):
    """A plugin is in use but the game's manifest does not declare it."""


def check_required_plugins(
    plugins: Mapping[str, Plugin],
    required_names: Iterable[str],
    active_names: Iterable[str],
    *,
    game_plugin_names: Iterable[str] = (),
    root: Any = None,
) -> None:
    """Check a game's manifest against the plugins actually in use.

    Anything in use the manifest does not name is a real defect, and the
    failure is silent: an unbound EXTERNAL falls through to its ink stub
    and answers plausibly. Hence raising here.

    Three ways a plugin can be in use without being declared, all checked:

    1. The application activates a name the manifest omits.
    2. The game's own package exports a `Plugin` the manifest omits.
    3. The story calls an EXTERNAL that only an undeclared plugin
       provides.

    Args:
        plugins: Every discovered plugin, by name.
        required_names: What the game's manifest declares.
        active_names: What the application is about to activate.
        game_plugin_names: Names the game's own package exports, if the
            caller knows them.
        root: The compiled story, for the EXTERNAL-coverage check. Skipped
            when None.

    Raises:
        ManifestMismatchError: Naming every undeclared plugin and how each
            was found to be in use.
    """
    required = set(required_names)
    problems: list[str] = []

    for name in sorted(set(active_names) - required):
        problems.append(f"{name!r} is being activated but the manifest does not list it")

    for name in sorted(set(game_plugin_names) - required):
        problems.append(f"{name!r} is exported by the game but the manifest does not list it")

    if root is not None:
        # Deferred: engine imports this module's siblings.
        from ink_engine.engine import (  # pylint: disable=import-outside-toplevel
            external_call_names,
        )

        called = external_call_names(root)
        # Only names NOTHING declared can provide: a game commonly ships
        # its own plugin answering the same Ink function a generic one
        # could, and that is the game overriding the engine, not a gap.
        already_covered: set[str] = set()
        for name in required & set(plugins):
            already_covered |= _binding_names(plugins[name])
        uncovered = called - already_covered
        for name in sorted(set(plugins) - required):
            covered = sorted(_binding_names(plugins[name]) & uncovered)
            if covered:
                problems.append(
                    f"{name!r} is the only provider of EXTERNALs the story calls ({', '.join(covered[:3])}) but the manifest does not list it"
                )

    if problems:
        raise ManifestMismatchError("; ".join(problems))


def _binding_names(plugin: Plugin) -> set[str]:
    """Return every Ink function name a plugin can bind.

    A stateful plugin's names come from calling its `bind` on a throwaway
    state, which is the only way to learn them and costs one allocation.

    Args:
        plugin: The plugin to inspect.

    Returns:
        The binding names, or an empty set if `bind` cannot run.
    """
    names = set(plugin.bindings)
    if plugin.bind is None or plugin.init_state is None:
        return names
    try:
        names |= set(plugin.bind(plugin.init_state(None), {}, {}))
    # A plugin needing real state must not break the check.
    except Exception:  # pylint: disable=broad-except
        pass
    return names
