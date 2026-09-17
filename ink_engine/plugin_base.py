"""The base a stateful plugin inherits: the slot dict IS the state.

A plugin is an instance of a `StatefulPlugin` subclass. Two things live on
it, kept apart by where they are stored:

- **State** is the plain JSON dict the engine allocates under `state_key`
  (the "slot"), never wrapped in another object. Every reader and writer
  takes the slot as its first argument and works on it directly.
- **Definition** is everything the instance holds as attributes: config, a
  rule table, registries of story functions. It is built once at import,
  shared by every session, and never enters the slot. Construction checks
  that `init_state()` is JSON-safe, which is where a definition object
  leaking into state shows up.

One method plays every role the plugin needs. A method `(self, slot,
*args)` is the typed reader a caller uses; marked `@query` it is also
published in `Plugin.queries` under the `(slot, *args)` contract; marked
`@external` it is also the Ink EXTERNAL of the same name. A binding that
must see the whole session (another plugin's slot, the LIST tables) is
marked `@external(needs_context=True)` and takes a `BindingContext` in
place of the slot.

Typing: a subclass declares its slot's shape as a `TypedDict` in
`slot_type` and the matching empty-value factories in `fields`. The two
are checked against each other at construction, so a field name typo
fails at import.
"""

from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.plugin import VOID, EngineState, ListDefs, Plugin

SlotT = TypeVar("SlotT", bound=Mapping[str, Any])

#: Marker attribute set by `@external`; its value is an `ExternalMarker`.
_EXTERNAL_MARKER = "_ink_external"
#: Marker attribute set by `@query`; its value is True.
_QUERY_MARKER = "_ink_query"


@dataclass(frozen=True, slots=True)
class ExternalMarker:
    """What `@external` records on a method.

    Attributes:
        needs_context: The method takes a `BindingContext` rather than
            the bare slot.
        returns_nothing: The method is annotated `-> None`; its binding
            returns `VOID`, since Ink has no void EXTERNAL return.
    """

    needs_context: bool
    returns_nothing: bool


def external(
    method: Callable[..., Any] | None = None,
    *,
    needs_context: bool = False,
) -> Any:
    """Mark a method as an Ink EXTERNAL binding named after the method.

    Usable bare (`@external`) or with the flag
    (`@external(needs_context=True)`). The method must carry a return
    annotation: `-> None` makes the binding return `VOID`; anything else
    is returned to Ink as is.

    Args:
        method: The method, when used as a bare decorator.
        needs_context: Pass a `BindingContext` as the first argument
            instead of the slot, for a binding that reads another
            plugin's slot or the LIST tables.

    Returns:
        The marked method, or the decorator when called with the flag.

    Raises:
        TypeError: The method has no return annotation.
    """

    def mark(function: Callable[..., Any]) -> Callable[..., Any]:
        annotations = inspect.get_annotations(function)
        if "return" not in annotations:
            raise TypeError(f"@external method '{function.__qualname__}' needs a return annotation ('-> None' for a writer)")
        returns_nothing = annotations["return"] in (None, "None", type(None))
        setattr(function, _EXTERNAL_MARKER, ExternalMarker(needs_context=needs_context, returns_nothing=returns_nothing))
        return function

    if method is not None:
        return mark(method)
    return mark


def query(method: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a method `(self, slot, *args)` as a published query.

    Args:
        method: The method to publish under its own name.

    Returns:
        The same method, marked.

    Raises:
        TypeError: The method takes `*args` or `**kwargs`, which would
            leave a caller unable to learn its arity.
    """
    for parameter in inspect.signature(method).parameters.values():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise TypeError(f"@query method '{method.__qualname__}' must declare every argument by name, not '*{parameter.name}'")
    setattr(method, _QUERY_MARKER, True)
    return method


@dataclass(frozen=True, slots=True)
class BindingContext(Generic[SlotT]):
    """One session, as seen by a binding that needs more than its slot.

    Attributes:
        slot: This plugin's own live slot.
        engine_state: The whole session state, for reading another
            plugin's slot by its `state_key`.
        list_defs: The story's compiled LIST tables.
    """

    slot: SlotT
    engine_state: EngineState
    list_defs: ListDefs

    def slot_of(self, state_key: str) -> dict[str, Any]:
        """Return another plugin's slot, or an empty dict when it is not active.

        Args:
            state_key: That plugin's `state_key`.

        Returns:
            The live slot dict, or `{}`.
        """
        return self.engine_state.get(state_key, {})


def _call_returning_void(method: Callable[..., Any], *args: Any) -> Any:
    """Call a writer and hand Ink `VOID` in place of its None.

    `args` is the bound instance, the slot or context, then Ink's own
    arguments.
    """
    method(*args)
    return VOID


class StatefulPlugin(Generic[SlotT]):
    """Base for a plugin that owns one JSON slot in the session state.

    Subclass, set the class attributes, write methods that take the slot,
    mark the Ink-callable ones `@external` and the askable ones `@query`,
    and export `PLUGIN = YourPlugin().plugin()`.

    Class attributes:
        name: The plugin's unique name. Overridable per instance, so a
            game can ship a configured copy of a generic plugin under its
            own name.
        display_name: Human-readable label. Overridable per instance.
        state_key: Where the slot lives in the session state.
        slot_type: The `TypedDict` describing the slot's top-level shape.
        fields: `{field_name: empty_value_factory}` for every key of
            `slot_type`. `init_state()` builds the slot from it and
            `bind()` re-applies it with `setdefault`, so a save written
            before a field existed still loads.
        default_config: What `init_state()` seeds a brand-new slot from
            when the application attaches no config. For state-like config only:
            values play then changes, or values another plugin reads from
            this slot. Definition-like config (a price list) belongs in
            the constructor's `config` and is read live from the instance;
            a plugin whose config must be seeded sets
            `self.default_config = config` in its constructor.
        stateless_bindings: Plain functions needing no state, by Ink name.

    Instance attributes:
        config: The definition config the constructor was given, or None.
            Validated at construction, so a bad config fails at import.
    """

    name: str
    display_name: str
    state_key: str
    slot_type: ClassVar[type]
    fields: ClassVar[dict[str, Callable[[], Any]]] = {}
    default_config: Any = None
    stateless_bindings: ClassVar[dict[str, Callable[..., Any]]] = {}

    def __init__(self, *, name: str | None = None, display_name: str | None = None, config: Any = None) -> None:
        """Build one plugin definition.

        Args:
            name: Override the class's `name`.
            display_name: Override the class's `display_name`.
            config: This plugin's definition config, or None.

        Raises:
            TypeError: `fields` and `slot_type` disagree about the slot's
                keys, or `init_state()` is not JSON-safe.
            SystemConfigValidationError: `config` fails `validate_config`.
        """
        if name is not None:
            self.name = name
        if display_name is not None:
            self.display_name = display_name
        self.config = config
        if config is not None:
            self.validate_config(config)
        self._check_slot_declaration()
        # Resolved once: bind() runs every turn and must not re-walk the MRO.
        self._externals: dict[str, tuple[Callable[..., Any], ExternalMarker]] = {}
        self._queries: dict[str, Callable[..., Any]] = {}
        for attribute_name, (function, external_marker, is_query) in _marked_methods(type(self)).items():
            if external_marker is not None:
                self._externals[attribute_name] = (function, external_marker)
            if is_query:
                self._queries[attribute_name] = function
        try:
            json.dumps(self.init_state(None))
        except (TypeError, ValueError) as error:
            raise TypeError(f"plugin '{self.name}': init_state() is not JSON-safe; a definition object is leaking into state ({error})") from error

    # -- what a subclass overrides ------------------------------------------

    def validate_config(self, config: Any) -> None:
        """Validate a config value. Override in a plugin that takes config.

        The default accepts only "no config", so a plugin that declares
        none cannot be handed one silently.

        Args:
            config: The decoded config.

        Raises:
            SystemConfigValidationError: The plugin takes no config and
                was given a non-empty one.
        """
        if config not in (None, {}):
            raise SystemConfigValidationError(f"plugin '{self.name}' takes no config")

    def seed(self, slot: SlotT, config: Any) -> None:
        """Write state-like config into a brand-new slot. Override to use it.

        Called once, by `init_state()`, with the application's config for this
        plugin or `default_config`. Never called on a resumed save.

        Args:
            slot: The fresh slot, every declared field already present.
            config: The config to seed from, or None.
        """

    # -- the contract, derived ----------------------------------------------

    def init_state(self, config: Any = None) -> dict[str, Any]:
        """Return a fresh slot: every declared field empty, then seeded.

        Args:
            config: The application's config for this plugin, or None to seed
                from `default_config`.

        Returns:
            A JSON-safe dict.
        """
        slot: Any = {field_name: make_empty() for field_name, make_empty in self.fields.items()}
        self.seed(slot, self.default_config if config is None else config)
        return slot

    def ensure_shape(self, slot: dict[str, Any]) -> None:
        """Add any declared field a loaded slot lacks, in place.

        Args:
            slot: This plugin's live slot.
        """
        for field_name, make_empty in self.fields.items():
            slot.setdefault(field_name, make_empty())

    def bind(self, slot: dict[str, Any], engine_state: EngineState, list_defs: ListDefs) -> dict[str, Callable[..., Any]]:
        """Build this session's EXTERNAL bindings from the marked methods.

        `Plugin.bind`'s exact signature. Override, calling `super().bind()`,
        only to add a binding that cannot be expressed as a method.

        Args:
            slot: This plugin's live slot.
            engine_state: The whole session state.
            list_defs: The story's LIST tables.

        Returns:
            `{ink_name: callable}` for every `@external` method.
        """
        self.ensure_shape(slot)
        context: BindingContext[Any] = BindingContext(slot=slot, engine_state=engine_state, list_defs=list_defs)
        bindings: dict[str, Callable[..., Any]] = {}
        for ink_name, (method, marker) in self._externals.items():
            first_argument = context if marker.needs_context else slot
            if marker.returns_nothing:
                bindings[ink_name] = functools.partial(_call_returning_void, method, self, first_argument)
            else:
                bindings[ink_name] = functools.partial(method, self, first_argument)
        return bindings

    def queries(self) -> dict[str, Callable[..., Any]]:
        """Return every `@query` method as a `(slot, *args)` callable.

        Returns:
            `{query_name: callable}`; each reports its real signature to
            `inspect.signature`, with `self` already bound.
        """
        return {query_name: functools.partial(method, self) for query_name, method in self._queries.items()}

    def plugin(self) -> Plugin:
        """Return the discovery descriptor for this plugin.

        Returns:
            A `Plugin` built from the class attributes and marked methods.
        """
        return Plugin(
            name=self.name,
            display_name=self.display_name,
            bindings=dict(self.stateless_bindings),
            validate_config=self.validate_config,
            state_key=self.state_key,
            init_state=self.init_state,
            bind=self.bind,
            queries=self.queries(),
            default_config=self.default_config,
        )

    # -- construction checks ------------------------------------------------

    def _check_slot_declaration(self) -> None:
        """Refuse a `fields` table that disagrees with `slot_type`.

        Raises:
            TypeError: `slot_type` is missing, or the two key sets differ.
        """
        slot_type = getattr(type(self), "slot_type", None)
        if slot_type is None:
            raise TypeError(f"plugin '{self.name}': declare the slot's shape as `slot_type` (a TypedDict)")
        declared = set(getattr(slot_type, "__required_keys__", ())) | set(getattr(slot_type, "__optional_keys__", ()))
        if declared != set(self.fields):
            raise TypeError(f"plugin '{self.name}': `fields` keys {sorted(self.fields)} do not match `slot_type` keys {sorted(declared)}")


def _marked_methods(plugin_class: type) -> dict[str, tuple[Callable[..., Any], ExternalMarker | None, bool]]:
    """Return every marked method of a class, by attribute name.

    The marker is taken from whichever class in the hierarchy declared
    it; the function is the most-derived definition. So a subclass that
    overrides a marked method keeps it published under the same Ink name
    without repeating the decorator, and cannot silently unpublish it.

    Args:
        plugin_class: The `StatefulPlugin` subclass.

    Returns:
        `{attribute_name: (function, external_marker, is_query)}`.
    """
    external_markers: dict[str, ExternalMarker] = {}
    query_names: set[str] = set()
    for klass in plugin_class.__mro__:
        for attribute_name, value in vars(klass).items():
            marker = getattr(value, _EXTERNAL_MARKER, None)
            if marker is not None:
                external_markers.setdefault(attribute_name, marker)
            if getattr(value, _QUERY_MARKER, False):
                query_names.add(attribute_name)
    return {
        attribute_name: (getattr(plugin_class, attribute_name), external_markers.get(attribute_name), attribute_name in query_names)
        for attribute_name in external_markers.keys() | query_names
    }
