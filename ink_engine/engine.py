"""Ink runtime engine: a from-scratch interpreter for compiled Ink
story JSON.

Builds the Container tree from a compiled story's JSON and resolves
dotted path strings (e.g. "start.0.g-0.2") to the content they address;
advances a Pointer through that tree leaf-by-leaf, following diverts,
evaluating the expression stack, collecting choice text, pruning
once-only choices by visit count, and assembling the visible turn text
using Ink's real newline/glue-suppression rules. Implements variables,
the call stack (tunnels, function calls, threads), LISTs,
sequences/shuffles/RNG, EXTERNAL function dispatch, and tags.

JSON encoding (matches inkle's own reference runtime):
- A container is a JSON list. All elements except the last are positional
  content (index-addressed). The last element, if a dict, is the
  "terminator": its keys are named content (e.g. sub-containers, knots)
  except for "#n" (this container's own name) and "#f" (count flags).
- A leaf string starting with "^" is literal text (the caret is stripped).
  A bare "\\n" is a newline. A leaf string "<>" is glue. Everything else at
  leaf level not otherwise recognized is stored as an opaque placeholder
  so path resolution still works.

Output-stream handling ports the C# reference runtime's
StoryState.PushToOutputStream / TrySplittingHeadTailWhitespace /
PushToOutputStreamIndividual / RemoveExistingGlue /
TrimNewlinesFromOutputStream, and the function-call-frame trim
(functionTrimIndex in the C# source), applied as a CallFrame pops.
"""

# pylint: disable=too-many-lines
# This module is the whole Ink interpreter, mirroring the real engine's
# Story.cs/StoryState.cs. Splitting it would fragment tightly coupled
# interpreter state across files with no real separation of concerns.

from __future__ import annotations

import functools
import math
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ink_engine.rng import NetRandom, RandomEngine, time_seed

#: How many parsed path strings to keep. A compiled story repeats the same
#: few paths tens of thousands of times, so a small cache catches nearly
#: all of it; the bound matters because a worker process loads many games
#: over its life and an unbounded cache would never release any of them.
PATH_CACHE_SIZE = 256


class InkPathError(ValueError):
    """Raised when a path string cannot be resolved against a container tree."""


class ConcurrentPlaythroughError(RuntimeError):
    """Raised when a second thread drives one `InkRuntimeState`.

    A state holds one whole playthrough and mutates it in place with no
    internal locking, so two threads driving it corrupt the call stack --
    sometimes raising from deep inside the interpreter, sometimes just
    losing turns. This check turns that into an error naming the real
    mistake, at the point it is made.

    Give each playthrough its own state. A compiled story root is
    read-only and may be shared by any number of them.
    """


class _TurnGuard:
    """Releases a state when its outermost turn returns.

    Nested because `refresh_choices()` calls `continue_story()`, and
    `continue_story()` calls `to_dict()`: only the outermost exit clears
    the running thread.
    """

    __slots__ = ("_state",)

    def __init__(self, state: InkRuntimeState) -> None:
        self._state = state

    def __enter__(self) -> _TurnGuard:
        return self

    def __exit__(self, *_exc: Any) -> None:
        state = self._state
        with state._turn_guard_lock:  # pylint: disable=protected-access
            state._turn_depth -= 1  # pylint: disable=protected-access
            if state._turn_depth == 0:  # pylint: disable=protected-access
                state._running_thread = None  # pylint: disable=protected-access


def _one_turn_at_a_time(method: Callable[..., Any]) -> Callable[..., Any]:
    """Refuse a call that overlaps a turn already running on this state."""

    @functools.wraps(method)
    def guarded(self: InkRuntimeState, *args: Any, **kwargs: Any) -> Any:
        with self._claim_thread():  # pylint: disable=protected-access
            return method(self, *args, **kwargs)

    return guarded


class UnboundExternalError(ValueError):
    """Raised when an EXTERNAL call cannot reach a bound Python callable.

    Two cases raise it. Unconditionally: the call has neither a binding
    nor a resolvable Ink fallback, matching inklecate's own runtime error.
    Under `strict_externals`: the call has no binding but does have a
    fallback, which would otherwise be taken silently.
    """


class _Unresolved:  # pylint: disable=too-few-public-methods
    """Sentinel distinguishing "never looked up" from a cached `None` on
    `_resolved_target_cache`.
    """


_UNRESOLVED = _Unresolved()


def _container_path(container: Container) -> str:
    """Reconstruct a container's absolute dotted path string.

    Ports Object.path (ink-engine-runtime/Object.cs)'s container-side
    component: each step up the parent chain is the child's own "#n"
    name, else its positional index.

    The exact string is load-bearing — shuffle-index selection and state
    serialization both address content by it.

    Args:
        container: The container to compute a path string for.

    Returns:
        The dotted path string from the story root to container.

    Raises:
        InkPathError: If container is not reachable from its own parent
            chain by name or by position — a malformed tree, which cannot
            occur for a container produced by load_story_root().
    """
    components: list[str] = []
    current = container
    while current.parent is not None:
        parent = current.parent
        if current.name is not None:
            components.append(current.name)
        elif current in parent.content:
            components.append(str(parent.content.index(current)))
        else:
            raise InkPathError(f"Container {current!r} is not reachable from its own parent {parent!r} by name or position")
        current = parent
    return ".".join(reversed(components))


@dataclass
class PathComponent:
    """One dotted segment of an Ink path: either a list index or a name.

    Args:
        index: The positional index into a container's content list, or
            None if this component addresses named content instead.
        name: The named-content key, or None if this component is an
            index. The literal name "^" (PARENT_NAME) addresses the
            parent container instead of a real named child.
    """

    index: int | None = None
    name: str | None = None

    PARENT_NAME = "^"

    @property
    def is_index(self) -> bool:
        """Return True if this component addresses content by list index."""
        return self.index is not None

    @property
    def is_parent(self) -> bool:
        """Return True if this component is the "^" parent-container marker."""
        return self.name == self.PARENT_NAME

    @staticmethod
    def parse(raw: str) -> PathComponent:
        """Parse a single dotted-path segment into index or name form.

        Args:
            raw: One segment of a dotted path string, e.g. "0", "g-0", or "^".

        Returns:
            A PathComponent addressing that segment by index (if raw is a
            plain non-negative integer) or by name otherwise.
        """
        if raw.isdigit():
            return PathComponent(index=int(raw))
        return PathComponent(name=raw)

    def __str__(self) -> str:
        """Return this component's dotted-path string form: index or name."""
        return str(self.index) if self.is_index else (self.name or "")


@dataclass
class Path:
    """A parsed Ink path: a sequence of components, absolute or relative.

    Args:
        components: The parsed path segments, in root-to-leaf order.
        is_relative: True if the original string began with ".", meaning
            resolution starts from a given container rather than the
            story root.
    """

    components: list[PathComponent] = field(default_factory=list)
    is_relative: bool = False

    @staticmethod
    @functools.lru_cache(maxsize=PATH_CACHE_SIZE)
    def parse(raw: str) -> Path:
        """Parse a dotted Ink path string into a Path.

        Cached: a compiled story repeats the same few path strings tens of
        thousands of times (`.^.b` alone appears 11,434 times in one real
        game, and 90% of all path strings are repeats), and the result is
        never mutated -- every consumer only reads `.components`.

        Args:
            raw: A path string as it appears in compiled JSON, e.g.
                "start.0.g-0.2" or ".^.b" (relative, one level up, then "b").

        Returns:
            The parsed Path. The SAME object for the same string, so
            callers must continue to treat it as read-only.
        """
        is_relative = raw.startswith(".")
        stripped = raw[1:] if is_relative else raw
        components = [PathComponent.parse(part) for part in stripped.split(".") if part]
        return Path(components=components, is_relative=is_relative)

    def __str__(self) -> str:
        """Return the dotted path string, prefixed with "." if relative."""
        prefix = "." if self.is_relative else ""
        return prefix + ".".join(str(c) for c in self.components)


@dataclass
class Divert:
    """An unconditional or conditional `->` jump to another path.

    Args:
        target_path: Where to jump to. When is_variable_target is True
            this is a placeholder holding a variable NAME instead, and
            the real destination is read at follow-time.
        is_conditional: True if a truthy value must be popped off the eval
            stack first to decide whether to follow this divert.
        pushes_tunnel: True for a `->t->` tunnel-push divert: pushes a
            return-address frame so a later `->->` resumes after this
            divert instead of ending the story.
        is_variable_target: True for `{"->": "varName", "var": true}`.
            The named variable holds a DivertTargetValue whose own
            target_path is the real destination. Ports
            Divert.hasVariableTarget (ink-engine-runtime/Divert.cs).
    """

    target_path: Path
    is_conditional: bool = False
    pushes_tunnel: bool = False
    is_variable_target: bool = False
    # Populated on first resolution by `_resolve_target()`, reused
    # thereafter. Safe because the compiled tree is built once by
    # `load_story_root()` and never mutated afterward, so this Divert's
    # holder (its fixed position in that tree) and `target_path` both stay
    # constant. A resolution failure caches as `None`, distinguished from
    # "not looked up yet" by the `_UNRESOLVED` sentinel. Never used for an
    # `is_variable_target=True` divert: its destination is read from a
    # variable at follow-time and never passed through `_resolve_target()`.
    _resolved_target_cache: Any = _UNRESOLVED


@dataclass
class ChoicePoint:
    """A `*`/`+` choice, addressed by the flags bitmask compiled into "flg".

    Bit values (matching the compiled JSON convention): 1=has_condition,
    2=has_start_content, 4=has_choice_only_content, 8=is_invisible_default,
    16=once_only.

    Args:
        target_path: Where choosing this choice diverts to.
        flags: The raw compiled flags bitmask.
    """

    target_path: Path
    flags: int = 0
    # See Divert._resolved_target_cache — identical caching, same safety
    # argument (fixed position in the never-mutated tree).
    _resolved_target_cache: Any = _UNRESOLVED

    @property
    def has_condition(self) -> bool:
        """Return whether a condition must be popped off the eval stack."""
        return bool(self.flags & 1)

    @property
    def has_start_content(self) -> bool:
        """Return whether this choice has text shown before the brackets."""
        return bool(self.flags & 2)

    @property
    def has_choice_only_content(self) -> bool:
        """Return whether this choice has bracketed choice-only text."""
        return bool(self.flags & 4)

    @property
    def is_invisible_default(self) -> bool:
        """Return whether this choice is auto-followed instead of shown."""
        return bool(self.flags & 8)

    @property
    def once_only(self) -> bool:
        """Return whether this choice is hidden once its target has been visited."""
        return bool(self.flags & 16)


@dataclass
class VariableReference:
    """A `{VAR?: name}` read of a global or temporary variable's current value.

    Args:
        name: The variable's name.
    """

    name: str


#: context_index for a temp in the outermost scope (self.temps), which no
#: call frame owns. 0 already means "a global".
OUTERMOST_TEMP_SCOPE = -2


@dataclass
class VariablePointer:
    """A `{"^var": name, "ci": index}` pointer to a variable, not its value.

    What a `ref` parameter binds. Assigning through one writes to the
    variable it names rather than to a local copy, so the caller sees the
    change.

    Args:
        name: The pointed-to variable's name.
        context_index: Which scope owns it -- -1 while unresolved (the
            compiler's own placeholder), 0 for a global,
            OUTERMOST_TEMP_SCOPE for a temp held outside any call frame,
            otherwise the 1-based call-frame index whose temps hold it.
    """

    name: str
    context_index: int = -1


@dataclass
class VariableAssignment:
    """A `{VAR=: name}` (global) or `{temp=: name}` (local) variable write.

    Args:
        name: The variable's name.
        is_global: True for a `VAR=` global assignment, False for `temp=`.
        is_new_declaration: True if this is the variable's first
            declaration (no "re" key in the compiled JSON, or "re" false);
            False for a reassignment to an already-declared variable.
            Parsed faithfully but not yet acted on: `_write_variable`
            branches only on `is_global`. Ink itself uses the flag to
            order global declarations and to notify variable observers,
            neither of which this interpreter implements.
    """

    name: str
    is_global: bool
    is_new_declaration: bool


@dataclass
class DivertTargetValue:
    """A `{"^->": path}` literal divert-target value token as it appears
    in a container's content list before dispatch (e.g. `-> knot_name`
    used as an expression, or `TURNS_SINCE(-> knot_name)`'s argument).

    Args:
        target_path: The path this value points at.
    """

    target_path: Path
    # See Divert._resolved_target_cache — identical caching, same safety
    # argument (fixed position in the never-mutated tree).
    _resolved_target_cache: Any = _UNRESOLVED


@dataclass
class ResolvedDivertTarget:
    """The dispatched, eval-stack-resident form of a DivertTargetValue:
    the same first-class Ink value, but with its (possibly relative)
    target_path already resolved to the Container it addresses.

    Args:
        container: The resolved container, or None if target_path failed
            to resolve (an unreachable or malformed target degrades to
            None rather than raising).
    """

    container: Container | None


class Void:  # pylint: disable=too-few-public-methods
    """The implicit return of a function falling off its own body without
    an explicit "~ret" (ink-engine-runtime/Story.cs).

    Must stay distinct from the integer 0: EVAL_OUTPUT prints a bare `0`
    as the literal text "0", where inklecate prints nothing.
    """


VOID = Void()


@dataclass
class ReadCountTarget:
    """A `{"CNT?": path}` bare read-count reference (e.g. `{knot_name}`
    used as a value — how many times knot_name has been visited).

    Args:
        target_path: The path whose visit count is being read.
    """

    target_path: Path
    # See Divert._resolved_target_cache — identical caching, same safety
    # argument (fixed position in the never-mutated tree).
    _resolved_target_cache: Any = _UNRESOLVED


@dataclass
class FunctionCall:
    """A `{"f()": path}` call to an `== function ==` knot, or a
    `{"x()": name, "exArgs": n}` call to an EXTERNAL-declared function.

    Args:
        target_path: The function's target path, absolute or relative
            (see `_call_function`, which resolves it).
        is_external: True for "x()". Dispatch is identical either way;
            the flag exists so validation can check EXTERNAL fallbacks
            without flagging a typo'd ordinary call as unbound.
        external_arg_count: The declared arity from "exArgs" on an "x()"
            call, else None. Only the Python-callable branch needs it
            (see `_call_function`).
    """

    target_path: Path
    is_external: bool = False
    external_arg_count: int | None = None
    # See Divert._resolved_target_cache — identical caching, same safety
    # argument (fixed position in the never-mutated tree).
    _resolved_target_cache: Any = _UNRESOLVED


@functools.lru_cache(maxsize=4096)
def _list_value_entries_as_dict(entries: tuple[tuple[tuple[str, str], int], ...]) -> dict[tuple[str, str], int]:
    """Build the {(origin_name, item_name): int_value} dict for a ListValue's entries.

    Cacheable because ListValue is frozen/hashable, and one value is
    often tested repeatedly within a turn.
    """
    return dict(entries)


@dataclass(frozen=True)
class ListValue:
    """An Ink LIST value: an ordered set of (origin, item) flags with
    integer values, e.g. `(Coins, Notes)` from `LIST Wallet = Coins, Notes,
    Cards`.

    Ports the observable behavior of ink-engine-runtime/InkList.cs: a
    Dictionary<InkListItem, int> keyed by (originName, itemName), plus the
    origin list names for LIST_ALL/LIST_INVERT/empty-value display
    (InkList.origins). Keyed by plain (origin, item) tuples rather than a
    custom InkListItem type, tuples already being hashable and comparable.

    Args:
        entries: This value's items, as {(origin_name, item_name): int_value}.
        origin_names: The list definition name(s) this value is known to
            come from — needed even for an empty value (e.g. a bare `VAR w
            = ()` typed to a specific list) so LIST_ALL/LIST_INVERT and
            item-addition (`+= someItem`) know which listDefs to consult.
    """

    entries: tuple[tuple[tuple[str, str], int], ...] = ()
    origin_names: tuple[str, ...] = ()

    @staticmethod
    def single(origin: str, item: str, value: int, origin_names: tuple[str, ...] | None = None) -> ListValue:
        """Build a single-item ListValue, e.g. for a bare `Coins` reference.

        Args:
            origin: The item's origin list name.
            item: The item's own name.
            value: The item's integer value (from listDefs).
            origin_names: The value's known origins; defaults to (origin,)
                when not given (the common case — a literal item reference
                is only ever known to come from its own origin).

        Returns:
            A ListValue with exactly one entry.
        """
        return ListValue(entries=(((origin, item), value),), origin_names=origin_names or (origin,))

    def as_dict(self) -> dict[tuple[str, str], int]:
        """Return entries as {(origin_name, item_name): int_value}."""
        return _list_value_entries_as_dict(self.entries)

    @property
    def ordered_entries(self) -> list[tuple[tuple[str, str], int]]:
        """Return entries sorted as real Ink orders them for display/min/max.

        Ports InkList.orderedItems: ascending by value, then by origin
        name to break ties consistently for mixed-list values.

        Returns:
            entries sorted ascending by (value, origin_name).
        """
        return sorted(self.entries, key=lambda pair: (pair[1], pair[0][0]))

    def to_display_string(self) -> str:
        """Return this value's display form, e.g. "Coins, Notes".

        Ports InkList.ToString(): item names only (no origin qualifier),
        comma-joined, in orderedItems order.

        Returns:
            The comma-joined item names, or "" for an empty value.
        """
        return ", ".join(item_name for (_, item_name), _ in self.ordered_entries)


@dataclass
class Choice:
    """One choice offered to the player at a decision point.

    Args:
        text: The choice's display text (already whitespace-cleaned).
        target: The container choosing this choice diverts to, already
            resolved (a ChoicePoint's target path may be relative to the
            choice point's own container, e.g. ".^.c-0", so resolution
            happens once at choice-creation time rather than being redone
            later against the wrong start container).
        tags: Tags written inside this choice's own brackets, in source
            order (`* [Go north # image: north.jpg]`). Standard Ink:
            these belong to the choice, not the content it leads to, and
            never appear in `text`.
    """

    text: str
    target: Container
    tags: list[str] = field(default_factory=list)


class Container:
    """A node in the compiled story's content tree.

    Args:
        name: This container's own name (from a "#n" terminator entry),
            or None for unnamed containers (most positional containers).
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name
        self.parent: Container | None = None
        self.content: list[Any] = []
        self.named_content: dict[str, Any] = {}
        self.count_flags: int = 0

    @property
    def visits_should_be_counted(self) -> bool:
        """Return whether visiting this container bumps its visit count.

        Ports Container.visitsShouldBeCounted, bit 1 of the compiled "#f"
        flags (Container.CountFlags.Visits).
        """
        return bool(self.count_flags & 1)

    @property
    def turn_index_should_be_counted(self) -> bool:
        """Return whether visiting this container records the turn index.

        Ports Container.turnIndexShouldBeCounted, bit 2 of "#f"
        (Container.CountFlags.Turns).
        """
        return bool(self.count_flags & 2)

    @property
    def counting_at_start_only(self) -> bool:
        """Return whether a visit counts only when entered at the start.

        Ports Container.countingAtStartOnly, bit 4 of "#f"
        (Container.CountFlags.CountStartOnly) — set for once-only choice
        gathers/knots so re-entering partway through (e.g. resuming after
        a tunnel return) doesn't count as a fresh visit.
        """
        return bool(self.count_flags & 4)

    def add_content(self, item: Any) -> None:
        """Append a positionally-addressed child to this container.

        Args:
            item: The child object (Container, str, or other leaf value).
                If it is itself a Container, its parent is set to self.
        """
        if isinstance(item, Container):
            item.parent = self
        self.content.append(item)

    def add_named_content(self, name: str, item: Any) -> None:
        """Register a named child, addressable by name in a path component.

        Args:
            name: The key this child is addressed by (a knot/stitch/label name).
            item: The child object. If it is itself a Container, its
                parent is set to self.
        """
        if isinstance(item, Container):
            item.parent = self
        self.named_content[name] = item

    def content_with_component(self, component: PathComponent) -> Any:
        """Resolve a single path component against this container's children.

        Args:
            component: The path segment to resolve (index, name, or parent marker).

        Returns:
            The matching child (index-addressed, named, or the parent
            container), or None if no such child exists.
        """
        if component.is_parent:
            return self.parent
        if component.is_index:
            assert component.index is not None
            if 0 <= component.index < len(self.content):
                return self.content[component.index]
            return None
        assert component.name is not None
        return self.named_content.get(component.name)


def load_story_root(story_json: dict[str, Any], *, full_build: bool = True) -> Container:
    """Build the story's Container tree from its compiled JSON.

    Args:
        story_json: The parsed top-level compiled-Ink JSON object (must
            contain a "root" key holding the container list).
        full_build: Build the whole tree up front. An application that holds one
            story for a session wants this. An application that rebuilds per
            request can pass False to build only the top level, each knot
            then being built whole the first time a path names it --
            `story_json` must stay alive for as long as the tree does,
            since the deferred children reference it.

    Returns:
        The root Container of the story's content tree.

    Raises:
        InkPathError: If the JSON has no "root" key.
    """
    if "root" not in story_json:
        raise InkPathError("Compiled story JSON has no 'root' key")
    if full_build:
        return _load_container(story_json["root"])
    return _load_container_lazily(story_json["root"])


def load_list_defs(story_json: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Extract the story's LIST definitions from its compiled JSON.

    Args:
        story_json: The parsed top-level compiled-Ink JSON object.

    Returns:
        {list_name: {item_name: int_value}}, or {} if the story declares
        no LISTs (the "listDefs" key is always present but may be empty).
    """
    return story_json.get("listDefs", {})


def retrieve_python_list(list_defs: dict[str, dict[str, int]], list_name: str) -> dict[str, int]:
    """Return one declared LIST's own item table, as plain Python.

    Supplies `store_python_list` with the item table it needs to build a
    `ListValue`.

    Args:
        list_defs: A `load_list_defs()` result — every LIST the story
            declares.
        list_name: The one LIST whose item table is wanted, e.g.
            "AllCharacters".

    Returns:
        {item_name: int_value} for that LIST, or {} if the story declares
        no LIST by that name.
    """
    return list_defs.get(list_name, {})


def store_python_list(list_name: str, item_names: Iterable[str], item_values: dict[str, int]) -> ListValue:
    """Build a real `ListValue` from a plain Python collection of item names.

    The write-side counterpart to `retrieve_python_list`. An EXTERNAL
    binding's return value is pushed onto the eval stack uncoerced, so
    the result works anywhere an Ink-built LIST value would — including
    the LIST operators (`?`/`+`/`-`/comparisons), which a comma-joined
    string would not support.

    Args:
        list_name: The LIST these items belong to, e.g. "AllCharacters" —
            becomes the built value's own `origin_names`.
        item_names: The item names to include. A name absent from
            `item_values` is skipped rather than raising — live session
            data may name something the LIST declaration does not carry.
        item_values: That LIST's item table, a `retrieve_python_list`
            result.

    Returns:
        A `ListValue` with one entry per name in `item_names` that
        `item_values` recognizes.
    """
    entries = tuple((list_name, name) for name in item_names if name in item_values)
    return ListValue(entries=tuple((entry, item_values[entry[1]]) for entry in entries), origin_names=(list_name,))


def find_unbound_externals(root: Container) -> list[str]:
    """Find every EXTERNAL-declared function with no resolvable ink fallback.

    Compiled Ink JSON erases the EXTERNAL declaration itself; only the
    call site survives. Each still needs a same-named
    `=== function name(...) ===` in the tree — the fallback used when no
    application function is bound. An application validating an uploaded story can use
    this to check every EXTERNAL has one.

    Args:
        root: The story's root Container (from load_story_root()).

    Returns:
        The sorted, de-duplicated list of EXTERNAL function names with no
        resolvable fallback — empty if every EXTERNAL call site resolves.
    """
    unbound = [name for name in external_call_names(root) if not isinstance(resolve_path(root, Path.parse(name)), Container)]
    return sorted(unbound)


def external_call_names(root: Container) -> set[str]:
    """Return every EXTERNAL function name the story calls.

    Whether each has an application binding, or an ink fallback, is a separate
    question -- this only reports what the story asks for.

    Args:
        root: The story's root container. Must be fully built: this walks
            the tree, and a lazily-built one would answer only for the
            knots that happen to have been visited.

    Returns:
        The de-duplicated EXTERNAL target names.

    Raises:
        InkPathError: `root` still has unbuilt children. Answering from a
            partial tree would report an incomplete set, and the caller
            that cares -- upload validation -- would pass a story whose
            EXTERNALs have no fallback.
    """
    if isinstance(root, LazyContainer) and root.has_deferred_content:
        raise InkPathError(
            "external_call_names() needs a fully built story: this root still has unbuilt "
            "children, so the answer would be incomplete. Load it with full_build=True."
        )

    external_names: set[str] = set()

    def walk(container: Container) -> None:
        for item in container.content:
            if isinstance(item, Container):
                walk(item)
            elif isinstance(item, FunctionCall) and item.is_external:
                external_names.add(str(item.target_path))
        for item in container.named_content.values():
            if isinstance(item, Container):
                walk(item)

    walk(root)
    return external_names


def start_new_story(
    root: Container,
    list_defs: dict[str, dict[str, int]] | None = None,
    *,
    engine_bindings: dict[str, Callable[..., Any]] | None = None,
    initial_globals: dict[str, Any] | None = None,
    strict_externals: bool = False,
) -> InkRuntimeState:
    """Build a fresh `InkRuntimeState` and run it to its first stop point.

    Args:
        root: The story's root Container (`load_story_root()`'s result).
        list_defs: The story's LIST definitions.
        engine_bindings: The EXTERNAL bindings for this session.
        initial_globals: Ink VAR values applied BEFORE the opening
            `continue_story()` call, e.g. a character-creation answer.
            None leaves the story's own declared VAR defaults untouched.
        strict_externals: Raise `UnboundExternalError` when an EXTERNAL
            has no bound callable, rather than falling through to the
            story's own Ink fallback.

    Returns:
        The new state, already advanced through its opening turn.
    """
    state = InkRuntimeState(root, list_defs, engine_bindings=engine_bindings, strict_externals=strict_externals)
    if initial_globals:
        state.globals.update(initial_globals)
    state.continue_story()
    return state


class LazyContainer(Container):
    """A container whose named-only children are built on first access.

    A story's knots are named-only children of the root: present in
    `named_content`, absent from `content` (verified against a real game:
    4,712 of 4,712). Deferring them therefore cannot disturb any
    positional index, which `_container_path()` depends on.

    The whole of a child's subtree is built at once, never partially, so
    every direct `.content` read elsewhere in the interpreter sees a
    complete container or no container at all.
    """

    def __init__(self, name: str | None = None) -> None:
        super().__init__(name)
        #: name -> the raw compiled JSON for a child not yet built. A
        #: reference into the already-parsed story, not a copy.
        self._deferred: dict[str, Any] = {}

    def defer_named_content(self, name: str, raw: Any) -> None:
        """Record a named child to build when something first asks for it."""
        self._deferred[name] = raw

    @property
    def has_deferred_content(self) -> bool:
        """Whether any named child is still unbuilt."""
        return bool(self._deferred)

    def _materialize(self, name: str) -> Any:
        """Build one deferred child, or return it if already built."""
        raw = self._deferred.pop(name)
        loaded = _load_object(raw)
        if isinstance(loaded, Container):
            loaded.name = name  # pylint: disable=attribute-defined-outside-init
        self.add_named_content(name, loaded)
        return loaded

    def materialize_all(self) -> None:
        """Build every remaining deferred child.

        For the callers that must see a whole tree, chiefly the EXTERNAL
        walk. One level suffices: a child is built by `_load_object()` as
        an ordinary Container, complete with its own subtree, so only the
        root ever defers anything.
        """
        for name in list(self._deferred):
            self._materialize(name)

    def content_with_component(self, component: PathComponent) -> Any:
        """Resolve one path component, building the child if deferred."""
        if not component.is_parent and not component.is_index:
            assert component.name is not None
            if component.name in self._deferred:
                return self._materialize(component.name)
        return super().content_with_component(component)


def _load_container(obj: list[Any]) -> Container:
    """Recursively build a Container from its compiled-JSON list form.

    Args:
        obj: The container's JSON list: positional content followed by an
            optional terminator dict of named content / "#n" / "#f".

    Returns:
        The constructed Container, with parent pointers set on every
        Container-typed child.
    """
    container = Container()

    positional = obj
    terminator = None
    if obj and isinstance(obj[-1], dict):
        positional = obj[:-1]
        terminator = obj[-1]

    for item in positional:
        loaded = _load_object(item)
        container.add_content(loaded)
        if isinstance(loaded, Container) and loaded.name:
            # Ports Container.TryAddNamedOnlyContent: a positionally-added
            # child that is itself a named container (a `- (label)` gather,
            # a `=== knot ===` inside a weave) must also be registered as
            # named content on its parent whether or not the terminator
            # dict lists it, or a name-only target such as
            # TURNS_SINCE(-> label) fails to resolve.
            container.add_named_content(loaded.name, loaded)

    if terminator:
        for key, value in terminator.items():
            if key == "#n":
                container.name = value
            elif key == "#f":
                container.count_flags = value
            else:
                loaded_named = _load_object(value)
                if isinstance(loaded_named, Container):
                    # Ports JsonSerialisation.JArrayToContainer's
                    # `namedSubContainer.name = keyVal.Key`: a
                    # terminator-dict-only named child takes its .name
                    # from the dict key unconditionally, compiled output
                    # never repeating that name as the child's own "#n".
                    # Otherwise it has no name and no positional slot,
                    # making it unreachable by _container_path(), which
                    # matches real Ink in using name-else-positional-index
                    # and never a named_content lookup.
                    loaded_named.name = key  # pylint: disable=attribute-defined-outside-init
                container.add_named_content(key, loaded_named)

    return container


def _load_container_lazily(obj: list[Any]) -> LazyContainer:
    """Build one container, deferring its named-only children.

    Positional content is built in full: it carries the indices
    `_container_path()` addresses by. Only terminator-dict entries -- the
    story's knots -- are deferred, and each is built whole when asked for.

    Args:
        obj: The container's JSON list, as `_load_container()` takes.

    Returns:
        The container, with `named_content` keys absent until first
        access. `content` is complete.
    """
    container = LazyContainer()

    positional = obj
    terminator = None
    if obj and isinstance(obj[-1], dict):
        positional = obj[:-1]
        terminator = obj[-1]

    for item in positional:
        loaded = _load_object(item)
        container.add_content(loaded)
        if isinstance(loaded, Container) and loaded.name:
            container.add_named_content(loaded.name, loaded)

    if terminator:
        for key, value in terminator.items():
            if key == "#n":
                container.name = value
            elif key == "#f":
                container.count_flags = value
            else:
                container.defer_named_content(key, value)

    return container


def _load_object(obj: Any) -> Any:
    """Convert one compiled-JSON token into its runtime representation.

    Containers become nested Containers; text/newline leaves become
    unwrapped strings; divert and choice-point dicts become typed objects.
    Every other leaf token is left as its raw JSON form, handled
    downstream by the code that needs it.

    Args:
        obj: A single element from a container's content list.

    Returns:
        A nested Container for list tokens; the stripped string for
        text/newline tokens; a Divert or ChoicePoint for those dict forms;
        the raw JSON token unchanged otherwise.
    """
    # Ordered by how often each type actually occurs in compiled output:
    # str 66%, dict 23%, list 4%. The three are mutually exclusive, so the
    # order changes only how many checks a token costs, never its result.
    if isinstance(obj, str):
        return obj[1:] if obj.startswith("^") else obj
    if isinstance(obj, dict):
        return _load_dict_object(obj)
    if isinstance(obj, list):
        return _load_container(obj)
    return obj


def _load_dict_object(obj: dict[str, Any]) -> Any:
    """Convert one compiled-JSON dict-form leaf into its typed runtime object.

    Args:
        obj: A dict-form leaf token (divert, choice point, variable
            reference/assignment — every other recognized dict shape
            passes through unchanged as an opaque placeholder).

    Returns:
        The matching typed object, or obj unchanged if no known key is present.
    """
    for key, builder in _DICT_OBJECT_BUILDERS:
        if key in obj:
            return builder(obj)
    return obj


def _load_list_value(obj: dict[str, Any]) -> ListValue:
    """Build a ListValue from a `{"list": {"Origin.Item": value, ...}}` leaf.

    Args:
        obj: The dict-form leaf token. "origins" holds the value's known
            origin list name(s) even when "list" itself is empty (a typed
            empty value, e.g. from `VAR w = ()`: {"list": {}, "origins": [...]}).

    Returns:
        The ListValue, with each "Origin.Item" key split on its first "."
        (origin/item names themselves never contain "." in compiled
        output).
    """
    entries = []
    for qualified_name, value in obj["list"].items():
        origin, _, item = qualified_name.partition(".")
        entries.append(((origin, item), int(value)))
    origin_names = tuple(obj.get("origins", []))
    if not origin_names:
        origin_names = tuple(dict.fromkeys(origin for (origin, _), _ in entries))
    return ListValue(entries=tuple(entries), origin_names=origin_names)


def _load_divert(obj: dict[str, Any]) -> Divert:
    """Build a Divert from a `{"->": target, "c": bool, "var": bool}` leaf.

    Args:
        obj: The dict-form leaf token. A "var": true entry means target is
            a variable *name* to read at follow-time (ports
            Divert.hasVariableTarget — ink-engine-runtime/Divert.cs), not
            a path string.

    Returns:
        The Divert. For a variable-target divert, target_path holds a
        single-name-component placeholder Path (never resolved as a
        path — is_variable_target routes _follow_divert to read the
        real target from a variable instead), so the field stays
        well-typed without needing Optional.
    """
    target = str(obj["->"])
    if obj.get("var", False):
        return Divert(target_path=Path(components=[PathComponent(name=target)]), is_variable_target=True)
    return Divert(target_path=Path.parse(target), is_conditional=bool(obj.get("c", False)))


_DICT_OBJECT_BUILDERS: list[tuple[str, Any]] = [
    ("->", _load_divert),
    ("->t->", lambda obj: Divert(target_path=Path.parse(str(obj["->t->"])), pushes_tunnel=True)),
    ("*", lambda obj: ChoicePoint(target_path=Path.parse(str(obj["*"])), flags=int(obj.get("flg", 0)))),
    ("VAR?", lambda obj: VariableReference(name=str(obj["VAR?"]))),
    ("^var", lambda obj: VariablePointer(name=str(obj["^var"]), context_index=int(obj.get("ci", -1)))),
    (
        "VAR=",
        lambda obj: VariableAssignment(name=str(obj["VAR="]), is_global=True, is_new_declaration=not obj.get("re", False)),
    ),
    (
        "temp=",
        lambda obj: VariableAssignment(name=str(obj["temp="]), is_global=False, is_new_declaration=not obj.get("re", False)),
    ),
    ("f()", lambda obj: FunctionCall(target_path=Path.parse(str(obj["f()"])))),
    # {"x()": name, "exArgs": n} — a call to an EXTERNAL-declared
    # function, dispatched through the same FunctionCall/_call_function
    # machinery as an ordinary "f()" call, since Ink's compiler erases the
    # distinction down to "call this top-level function by name". x()'s
    # target is always a bare declared name, never relative, so
    # _resolve_target's absolute-path handling suffices. A missing entry
    # here would make external calls silently no-op through
    # _dispatch_literal_content's opaque-token branch.
    ("x()", lambda obj: FunctionCall(target_path=Path.parse(str(obj["x()"])), is_external=True, external_arg_count=obj.get("exArgs"))),
    ("list", _load_list_value),
    ("^->", lambda obj: DivertTargetValue(target_path=Path.parse(str(obj["^->"])))),
    ("CNT?", lambda obj: ReadCountTarget(target_path=Path.parse(str(obj["CNT?"])))),
]


def resolve_path(start: Container, path: Path) -> Container | Any | None:
    """Resolve a parsed Path to the content it addresses, starting from start.

    Args:
        start: The container resolution begins from — the story root for
            an absolute path, or the "current" container for a relative one.
        path: The parsed path to resolve.

    Returns:
        The resolved content (a Container or a leaf value), or None if any
        component along the path fails to resolve.
    """
    current: Any = start
    for component in path.components:
        if not isinstance(current, Container):
            return None
        current = current.content_with_component(component)
        if current is None:
            return None
    return current


GLUE = "<>"
NEWLINE = "\n"


def _is_whitespace_only(text: str) -> bool:
    """Return whether `text` is non-empty and made only of spaces/tabs.

    `text` is a leaf text token, any "^" marker already stripped.
    """
    return bool(text) and all(c in (" ", "\t") for c in text)


def _scan_newline_run(indices: range, text: str) -> tuple[int, int]:
    """Scan a run of spaces/tabs/newlines from one end of text, in the given order.

    Shared by the head (forward) and tail (backward) scans in
    _split_head_tail_whitespace: walks indices in the order given, treating
    inline whitespace as transparent, and stops at the first character
    that is neither whitespace nor a newline.

    Args:
        indices: The index sequence to scan, e.g. range(len(text)) for a
            forward (head) scan or range(len(text) - 1, -1, -1) for a
            backward (tail) scan.
        text: The text being scanned.

    Returns:
        A (first_newline, last_newline) pair of indices in scan order
        (i.e. for a backward scan, first_newline is the newline closest to
        the end of the string), or (-1, -1) if no newline was found before
        real content.
    """
    first_newline = -1
    last_newline = -1
    for i in indices:
        c = text[i]
        if c == NEWLINE:
            if first_newline == -1:
                first_newline = i
            last_newline = i
        elif c in (" ", "\t"):
            continue
        else:
            break
    return first_newline, last_newline


def _split_head_tail_whitespace(text: str) -> list[str] | None:
    """Split leading/trailing run-of-newlines-and-spaces off a text token.

    Ports StoryState.TrySplittingHeadTailWhitespace from the C# reference
    runtime (ink-engine-runtime/StoryState.cs): excess newlines at the head
    or tail of a string are collapsed to a single "\\n" each (with any
    surrounding spaces/tabs kept as their own separate token), so each
    piece can be pushed through the same glue/newline-dedup logic as if it
    had arrived as a separate token. Interior newlines are left untouched.

    Args:
        text: A leaf text token (already had any "^" marker stripped).

    Returns:
        None if no head/tail newline run was found (nothing to split); a
        list of the substrings, in order, resulting from the split.
    """
    length = len(text)

    head_first_newline, head_last_newline = _scan_newline_run(range(length), text)
    tail_last_newline, tail_first_newline = _scan_newline_run(range(length - 1, -1, -1), text)

    if head_first_newline == -1 and tail_last_newline == -1:
        return None

    pieces: list[str] = []
    inner_start = 0
    inner_end = length

    if head_first_newline != -1:
        if head_first_newline > 0:
            pieces.append(text[:head_first_newline])
        pieces.append(NEWLINE)
        inner_start = head_last_newline + 1

    if tail_last_newline != -1:
        inner_end = tail_first_newline

    if inner_end > inner_start:
        pieces.append(text[inner_start:inner_end])

    if tail_last_newline != -1 and tail_first_newline > head_last_newline:
        pieces.append(NEWLINE)
        if tail_last_newline < length - 1:
            pieces.append(text[tail_last_newline + 1 :])

    return pieces


class OutputStream:
    """Assembles visible turn text from leaf tokens using Ink's real
    glue/newline-suppression rules.
    """

    def __init__(self) -> None:
        self.tokens: list[str] = []

    @classmethod
    def from_tokens(cls, tokens: list[str]) -> OutputStream:
        """Build a stream over an existing token list.

        The sanctioned way `tokens` shrinks from outside `push()`; see
        `__init__`'s cache note.

        Args:
            tokens: The tokens the new stream owns. Taken as given, not
                copied -- pass a copy where the caller keeps its own.

        Returns:
            The stream, with its glue cache unset.
        """
        stream = cls()
        stream.tokens = tokens
        return stream

    @property
    def ends_in_newline(self) -> bool:
        """Return whether the stream currently ends in a newline.

        Mirrors StoryState.outputStreamEndsInNewline: scans backward past
        glue, stopping at the first non-whitespace text.

        Returns:
            True if the most recent non-glue text token is a newline;
            False otherwise, including for an empty stream.
        """
        for token in reversed(self.tokens):
            if token == GLUE:
                continue
            if token == NEWLINE:
                return True
            if not _is_whitespace_only(token):
                break
        return False

    @property
    def contains_content(self) -> bool:
        """Return whether the stream holds any real (non-whitespace) text."""
        return any(token != GLUE and not _is_whitespace_only(token) and token != NEWLINE for token in self.tokens)

    def _remove_existing_glue(self) -> None:
        """Drop trailing glue tokens, per RemoveExistingGlue in the C# source.

        Called only when non-whitespace text is about to be appended while
        a glue-trim is active — that text has "consumed" the glue's join,
        so the glue marker itself is no longer needed in the stream.
        """
        while self.tokens and self.tokens[-1] == GLUE:
            self.tokens.pop()

    def trim_newlines_from_end(self) -> None:
        """Remove a trailing run of newline/whitespace text.

        Ports TrimNewlinesFromOutputStream. Called when new glue arrives,
        so glue always eats the whitespace immediately before it, and as a
        function's call frame pops (C#'s functionTrimIndex).
        """
        remove_from = -1
        for i in range(len(self.tokens) - 1, -1, -1):
            token = self.tokens[i]
            if token == GLUE:
                break
            if _is_whitespace_only(token):
                continue
            if token == NEWLINE:
                remove_from = i
            else:
                break
        if remove_from >= 0:
            del self.tokens[remove_from:]

    def _latest_glue_index(self) -> int:
        """Find the index of the most recent still-active glue token.

        Ports the backward scan in PushToOutputStreamIndividual. This
        stream carries no ControlCommand tokens, so unlike the C# source
        there is no BeginString boundary to stop at.

        Returns:
            The index of the most recent glue token, or -1 if the stream
            has no trailing glue (i.e. it was already closed off by real
            text, or none was ever pushed).
        """
        for i in range(len(self.tokens) - 1, -1, -1):
            if self.tokens[i] == GLUE:
                return i
        return -1

    def push(self, token: str) -> None:
        """Push one leaf token (text, newline, or glue) onto the stream.

        Ports StoryState.PushToOutputStreamIndividual: glue triggers a
        backward trim of trailing whitespace/newlines; while a glue token
        is still "open" (nothing real has been pushed since it arrived),
        every subsequent newline is suppressed outright, and the first
        non-whitespace text closes the glue by removing its marker.
        Outside of an open glue, ordinary newline dedup/no-leading-newline
        rules apply.

        Args:
            token: A text/newline leaf value (already "^"-stripped) or the
                literal glue marker "<>".
        """
        if token == GLUE:
            self.trim_newlines_from_end()
            self.tokens.append(GLUE)
            return

        glue_index = self._latest_glue_index()
        if glue_index != -1:
            if token == NEWLINE:
                return
            if not _is_whitespace_only(token):
                self._remove_existing_glue()
            self.tokens.append(token)
            return

        if token == NEWLINE:
            if self.ends_in_newline or not self.contains_content:
                return
            self.tokens.append(NEWLINE)
            return

        self.tokens.append(token)

    def push_text(self, text: str) -> None:
        """Push a raw leaf text token, splitting head/tail newline runs first.

        Args:
            text: The leaf text value (already "^"-stripped if it came
                from a "^"-marked JSON string). Plain "\\n" tokens should
                be passed straight to push(), not through here.
        """
        pieces = _split_head_tail_whitespace(text)
        if pieces is None:
            self.push(text)
            return
        for piece in pieces:
            self.push(piece)

    def get_string_value(self) -> str:
        """Return the assembled text as a STRING VALUE, uncleaned.

        The display-time whitespace pass (`get_text`) must not run here.
        Ports Story.cs's `EndString` case, which builds the value with a
        plain `sb.Append(c.ToString())` and no cleaning: a string being
        pushed onto the evaluation stack is data, not output, so
        `"A " + who` has to keep the space `CleanOutputWhitespace` would
        drop from the end of a run.

        Returns:
            The assembled text with glue markers omitted and whitespace
            left exactly as written.
        """
        return "".join(token for token in self.tokens if token != GLUE)

    def get_text(self) -> str:
        """Return the assembled visible text for everything pushed so far.

        Ports Runtime.State.CleanOutputWhitespace: a display-time pass
        over the joined text collapsing any run of inline spaces/tabs to a
        single space, unless it sits at the start of a line.

        Returns:
            The assembled, whitespace-cleaned visible text, glue markers
            omitted.
        """
        joined = "".join(token for token in self.tokens if token != GLUE)

        output: list[str] = []
        whitespace_start = -1
        line_start = 0
        for i, char in enumerate(joined):
            is_inline_whitespace = char in (" ", "\t")

            if is_inline_whitespace and whitespace_start == -1:
                whitespace_start = i

            if not is_inline_whitespace:
                if char != NEWLINE and whitespace_start > 0 and whitespace_start != line_start:
                    output.append(" ")
                whitespace_start = -1

            if char == NEWLINE:
                line_start = i + 1

            if not is_inline_whitespace:
                output.append(char)

        return "".join(output)


DONE_COMMANDS = frozenset({"done", "end"})
EVAL_START = "ev"
EVAL_END = "/ev"
STRING_START = "str"
STRING_END = "/str"
EVAL_OUTPUT = "out"
POP_TUNNEL = "->->"
FUNCTION_RETURN = "~ret"
VOID_POP = "pop"
START_THREAD = "thread"
DUPLICATE_TOP = "du"
CHOICE_COUNT = "choiceCnt"
TURNS = "turn"
TURNS_SINCE = "turns"
READ_COUNT = "readc"
VISIT_INDEX = "visit"
RANDOM = "rnd"
SEED_RANDOM = "srnd"
SEQUENCE_SHUFFLE = "seq"
LIST_RANDOM = "lrnd"
LIST_RANGE = "range"
LIST_FROM_INT = "listInt"
NO_OP = "nop"
#: The placeholder a function with no return value pushes ("ev","void","/ev").
VOID_OPERAND = "void"
BEGIN_TAG = "#"
END_TAG = "/#"

#: Markers that push a value onto the eval stack rather than producing
#: text. Grouped so the several places that must treat them alike read
#: one definition instead of repeating the membership by hand -- a token
#: added to one list and missed in another is captured as literal choice
#: text and shown to the player, with nothing raising.
STORY_METADATA_COMMANDS = frozenset({CHOICE_COUNT, TURNS, TURNS_SINCE, READ_COUNT, VISIT_INDEX})
RNG_COMMANDS = frozenset({RANDOM, SEED_RANDOM, SEQUENCE_SHUFFLE, LIST_RANDOM})
#: LIST-valued ControlCommands. Separate from the LIST *operators* in
#: LIST_NATIVE_FUNCTION_ARITY: the compiler emits these as bare markers,
#: not NativeFunctionCalls.
LIST_COMMANDS = frozenset({LIST_RANGE, LIST_FROM_INT})
EVAL_STACK_COMMANDS = STORY_METADATA_COMMANDS | RNG_COMMANDS | LIST_COMMANDS | {EVAL_OUTPUT}

# The full set of bare-string ControlCommand markers compiled JSON can
# emit, matching the reference runtime's CommandType enum. Everything
# here is a control-command marker, never display text: an unrecognized
# bare token such as "nop" would render as literal text in the output
# stream.
CONTROL_COMMAND_MARKERS = frozenset(
    {
        "ev",
        "out",
        "/ev",
        "du",
        "pop",
        "~ret",
        "str",
        "/str",
        NO_OP,
        "choiceCnt",
        "turn",
        "turns",
        "readc",
        RANDOM,
        SEED_RANDOM,
        "visit",
        SEQUENCE_SHUFFLE,
        "thread",
        "done",
        "end",
        LIST_FROM_INT,
        LIST_RANGE,
        LIST_RANDOM,
        "#",
        "/#",
    }
)

# Native-function operator set for arithmetic/comparison/logic on
# Int/Float/String/Bool, ported from NativeFunctionCall.cs's op tables.
# Excludes list ops (?, !?, ^, LIST_*, in their own table below) and the
# two DivertTargetValue-only ops (Equal/NotEquals on divert targets).
NATIVE_FUNCTION_ARITY = {
    "+": 2,
    "-": 2,
    "/": 2,
    "*": 2,
    "%": 2,
    "_": 1,  # Negate
    "==": 2,
    ">": 2,
    "<": 2,
    ">=": 2,
    "<=": 2,
    "!=": 2,
    "!": 1,
    "&&": 2,
    "||": 2,
    "MIN": 2,
    "MAX": 2,
    "POW": 2,
    "FLOOR": 1,
    "CEILING": 1,
    "INT": 1,
    "FLOAT": 1,
}

# LIST operator set, ported from NativeFunctionCall.cs's
# AddListBinaryOp/AddListUnaryOp call sites. LIST_RANGE/LIST_RANDOM are
# absent because the real engine does not treat them as
# NativeFunctionCall operators: they are
# ControlCommand.ListRange/ListRandom, dispatched from LIST_COMMANDS and
# RNG_COMMANDS respectively.
#: The compiled name for the intersection operator. A bare "^" would
#: collide with the literal-text marker, so the compiler emits "L^".
INTERSECTION_ALIASES = {"L^": "^"}

LIST_NATIVE_FUNCTION_ARITY = {
    "+": 2,
    "-": 2,
    "?": 2,
    "!?": 2,
    # The compiler emits the intersection operator as "L^", not "^" -- a bare
    # "^" would collide with the literal-text marker. Both names are accepted.
    "^": 2,
    "L^": 2,
    "==": 2,
    "!=": 2,
    ">": 2,
    "<": 2,
    ">=": 2,
    "<=": 2,
    "&&": 2,
    "||": 2,
    "LIST_MIN": 1,
    "LIST_MAX": 1,
    "LIST_ALL": 1,
    "LIST_COUNT": 1,
    "LIST_VALUE": 1,
    "LIST_INVERT": 1,
}
NATIVE_FUNCTION_ARITY.update(LIST_NATIVE_FUNCTION_ARITY)


def _coerce_native_function_operands(args: list[Any]) -> tuple[type, list[Any]]:
    """Coerce operands to the operation's shared type, per NativeFunctionCall.cs.

    "Higher level" types infect both sides so a binary op always runs on
    matching types: bool coerces to int first (the C# source likewise
    never operates directly on a bool), then int < float < str, so any
    float or str operand promotes both sides to that type.

    Args:
        args: One or two operand values (bool/int/float/str).

    Returns:
        (coerced_type, coerced_args) — coerced_type is bool, int, float,
        or str; coerced_args holds args cast to that type.
    """
    types = [bool if isinstance(a, bool) else type(a) for a in args]
    if str in types:
        target: type = str
    elif float in types:
        target = float
    else:
        target = int
    coerced = [target(a) for a in args]
    return target, coerced


def _is_truthy(value: Any) -> bool:
    """Return whether a popped eval-stack value counts as true.

    Ports Story.IsTruthy (ink-engine-runtime/Story.cs): bool/int/float
    are truthy iff nonzero (bool included, since Python bools are ints);
    str is truthy iff non-empty; ListValue is truthy iff it has at least
    one entry. DivertTargetValue truthiness is a compile-time error in
    real Ink ("did you intend a function call?") and doesn't arise here
    since nothing ever pushes one onto the eval stack.

    Args:
        value: A value popped off the eval stack.

    Returns:
        The value's truthiness.
    """
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, ListValue):
        return len(value.entries) > 0
    return bool(value)


def _display_string(value: Any) -> str:
    """Render a popped eval-stack value as it appears in visible story text.

    Args:
        value: Any value that can reach the output stream via EVAL_OUTPUT.

    Returns:
        value.to_display_string() for a ListValue (item names only, no
        Python repr/dataclass noise); "true"/"false" for a bool (Python's
        str(bool) capitalizes, which real Ink never does); a whole-valued
        float without its ".0" (`{POW(3,2)}` prints "9", not "9.0");
        str(value) for everything else.
    """
    if isinstance(value, ListValue):
        return value.to_display_string()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def apply_native_function(name: str, args: list[Any], list_defs: dict[str, dict[str, int]] | None = None) -> Any:
    """Apply one native-function operator to its popped operands.

    Args:
        name: The operator's compiled-JSON symbol (e.g. "+", "==", "MOD").
        args: The operands, already popped off the eval stack in push
            order (args[0] pushed first).
        list_defs: The story's LIST definitions ({list_name: {item_name:
            int_value}}), needed only when args contains a ListValue and
            name is LIST_ALL/LIST_INVERT (see _list_unary_op). Defaults to
            {} — every other operator/type combination ignores this
            argument entirely.

    Returns:
        The operation's result (bool/int/float/str/ListValue).

    Raises:
        InkPathError: If name is a binary/unary-only string op not valid
            for the coerced operand type (e.g. "-" on strings), or an
            unsupported string-comparison-family op reaches string
            operands without a defined behavior here.
    """
    if any(isinstance(a, ListValue) for a in args):
        return _apply_list_native_function(name, args, list_defs or {})

    target, coerced = _coerce_native_function_operands(args)

    if target is str:
        return _apply_string_native_function(name, coerced)
    return _apply_numeric_native_function(name, coerced, is_float=target is float)


def _apply_string_native_function(name: str, args: list[Any]) -> Any:
    """Apply a string-typed native function (Add=concat, Equal, NotEquals only).

    Args:
        name: The operator symbol.
        args: One or two string operands.

    Returns:
        The result (str for "+", bool for "=="/"!=").

    Raises:
        InkPathError: If name has no defined string operation. Matches
            the C# source's AddStringBinaryOp calls: only +, ==, !=.
            Has/Hasnt (?, !?) are excluded for strings; the LIST-typed
            ?/!? family goes through _apply_list_native_function.
    """
    if name == "+":
        return args[0] + args[1]
    if name == "==":
        return args[0] == args[1]
    if name == "!=":
        return args[0] != args[1]
    raise InkPathError(f"Native function {name!r} is not defined for string operands")


def _list_binary_op(name: str, first: ListValue, second: ListValue) -> Any:
    """Apply a two-LIST-operand native function.

    Ports InkList's Union/Without/Contains/Intersect/GreaterThan/
    LessThan/(Not)Equals/And/Or line-for-line, including the comparison
    operators (<, >=, <=) that follow from the same min/max-item logic
    as (>).

    Args:
        name: The operator symbol.
        first: The left operand.
        second: The right operand.

    Returns:
        A ListValue for +/-/^ (set operations); bool for every comparison
        and Has/Hasnt/And/Or.

    Raises:
        InkPathError: If name has no defined two-LIST operation.
    """
    first_map, second_map = first.as_dict(), second.as_dict()
    ops: dict[str, Any] = {
        "+": lambda: ListValue(
            entries=tuple({**first_map, **second_map}.items()),
            origin_names=tuple(dict.fromkeys(first.origin_names + second.origin_names)),
        ),
        "-": lambda: ListValue(entries=tuple((k, v) for k, v in first_map.items() if k not in second_map), origin_names=first.origin_names),
        "^": lambda: ListValue(entries=tuple((k, v) for k, v in first_map.items() if k in second_map), origin_names=first.origin_names),
        "?": lambda: bool(second_map) and set(second_map) <= set(first_map),
        "!?": lambda: not (bool(second_map) and set(second_map) <= set(first_map)),
        "==": lambda: first_map == second_map,
        "!=": lambda: first_map != second_map,
        "&&": lambda: bool(first_map) and bool(second_map),
        "||": lambda: bool(first_map) or bool(second_map),
    }
    # The compiler emits intersection as "L^"; ops defines it once as "^".
    op = ops.get(INTERSECTION_ALIASES.get(name, name))
    if op is not None:
        return op()
    return _list_comparison_op(name, first, second)


def _list_comparison_op(name: str, first: ListValue, second: ListValue) -> bool:
    """Apply a LIST magnitude comparison (>, <, >=, <=).

    Ports InkList.GreaterThan/LessThan/GreaterThanOrEquals/
    LessThanOrEquals: an empty operand decides every one of these
    comparisons by count alone, before any item value is looked at.

    Args:
        name: The comparison operator symbol.
        first: The left operand.
        second: The right operand.

    Returns:
        The comparison result.
    """
    first_entries, second_entries = first.ordered_entries, second.ordered_entries

    def greater_than() -> bool:
        if not first_entries:
            return False
        if not second_entries:
            return True
        return first_entries[0][1] > second_entries[-1][1]

    def less_than() -> bool:
        if not second_entries:
            return False
        if not first_entries:
            return True
        return first_entries[-1][1] < second_entries[0][1]

    def greater_or_equal() -> bool:
        if not first_entries:
            return False
        if not second_entries:
            return True
        return first_entries[0][1] >= second_entries[0][1] and first_entries[-1][1] >= second_entries[-1][1]

    def less_or_equal() -> bool:
        if not second_entries:
            return False
        if not first_entries:
            return True
        return first_entries[-1][1] <= second_entries[-1][1] and first_entries[0][1] <= second_entries[0][1]

    comparisons = {">": greater_than, "<": less_than, ">=": greater_or_equal, "<=": less_or_equal}
    comparison = comparisons.get(name)
    if comparison is None:
        raise InkPathError(f"Native function {name!r} is not defined for LIST operands")
    return comparison()


def _list_unary_op(name: str, value: ListValue, list_defs: dict[str, dict[str, int]]) -> Any:
    """Apply a one-LIST-operand native function.

    Ports InkList.minItem/maxItem/all/inverse (ink-engine-runtime/InkList.cs)
    for LIST_MIN, LIST_MAX, LIST_ALL, LIST_COUNT, LIST_VALUE, and
    LIST_INVERT.

    Args:
        name: The operator symbol.
        value: The single LIST operand.
        list_defs: The story's LIST definitions ({list_name: {item_name:
            int_value}}), needed by LIST_ALL/LIST_INVERT to enumerate every
            item of value's origin list(s), not just the ones value
            currently holds.

    Returns:
        A ListValue for LIST_MIN/LIST_MAX/LIST_ALL/LIST_INVERT; int for
        LIST_COUNT/LIST_VALUE.

    Raises:
        InkPathError: If name has no defined one-LIST operation.
    """
    entries = value.ordered_entries
    if name == "LIST_MIN":
        return ListValue(entries=(entries[0],), origin_names=value.origin_names) if entries else ListValue()
    if name == "LIST_MAX":
        return ListValue(entries=(entries[-1],), origin_names=value.origin_names) if entries else ListValue()
    if name == "LIST_COUNT":
        return len(entries)
    if name == "LIST_VALUE":
        return entries[0][1] if entries else 0
    if name == "!":
        # `not <list>` is emptiness, as an int: real Ink prints 1 for an
        # empty list and 0 for a non-empty one. Raising instead would be
        # swallowed by _apply_operator_defensively, leaving the guard in a
        # recursive list traversal with nothing to test.
        return 1 if not entries else 0
    if name in ("LIST_ALL", "LIST_INVERT"):
        held = value.as_dict()
        result: dict[tuple[str, str], int] = {}
        for origin in value.origin_names:
            for item_name, item_value in list_defs.get(origin, {}).items():
                key = (origin, item_name)
                if name == "LIST_ALL" or key not in held:
                    result[key] = item_value
        return ListValue(entries=tuple(result.items()), origin_names=value.origin_names)
    raise InkPathError(f"Native function {name!r} is not defined for LIST operands")


def _apply_list_native_function(name: str, args: list[Any], list_defs: dict[str, dict[str, int]]) -> Any:
    """Apply one LIST-typed native function.

    A LIST operand takes dispatch priority over
    `_coerce_native_function_operands`' numeric/string coercion, matching
    NativeFunctionCall's CallType resolution.

    Args:
        name: The operator symbol.
        args: One or two operands, at least one a ListValue (the caller
            checks). A mixed binary op such as LIST against a bare int has
            no defined operation here and raises.
        list_defs: The story's LIST definitions, needed by the unary
            LIST_ALL/LIST_INVERT ops (see _list_unary_op).

    Returns:
        See _list_unary_op/_list_binary_op.

    Raises:
        InkPathError: If any operand isn't a ListValue, or name has no
            defined LIST operation.
    """
    if not all(isinstance(a, ListValue) for a in args):
        raise InkPathError(f"Native function {name!r} requires all LIST operands, got {args!r}")
    if len(args) == 1:
        return _list_unary_op(name, args[0], list_defs)
    return _list_binary_op(name, args[0], args[1])


def _numeric_native_functions(is_float: bool) -> dict[str, Any]:
    """Build the operator-name -> callable table for numeric operands.

    int and float behavior diverges only for FLOOR/CEILING/INT (identity
    on ints, real work on floats) and "/" (truncating for ints), matching
    the C# source's separate AddIntUnaryOp/AddFloatUnaryOp and
    AddIntBinaryOp/AddFloatBinaryOp call sites for each op.

    Args:
        is_float: True to build the float-operand table, False for int.

    Returns:
        A dict mapping operator symbol to a callable taking (first,
        second) — second is unused (may be None) for unary operators.
    """
    identity = (lambda x, _y: x) if not is_float else None
    return {
        "+": lambda x, y: x + y,
        "-": lambda x, y: x - y,
        "*": lambda x, y: x * y,
        "/": (lambda x, y: x / y) if is_float else (lambda x, y: int(x / y)),
        "%": lambda x, y: x % y,
        "_": lambda x, _y: -x,
        "==": lambda x, y: x == y,
        ">": lambda x, y: x > y,
        "<": lambda x, y: x < y,
        ">=": lambda x, y: x >= y,
        "<=": lambda x, y: x <= y,
        "!=": lambda x, y: x != y,
        "!": lambda x, _y: x == 0,
        "&&": lambda x, y: x != 0 and y != 0,
        "||": lambda x, y: x != 0 or y != 0,
        "MIN": min,
        "MAX": max,
        "POW": lambda x, y: float(x**y),
        "FLOOR": identity or (lambda x, _y: float(math.floor(x))),
        "CEILING": identity or (lambda x, _y: float(math.ceil(x))),
        "INT": identity or (lambda x, _y: int(x)),
        "FLOAT": lambda x, _y: float(x),
    }


#: The int- and float-operand operator tables, built once. Both are
#: constants -- every entry is a pure function closing over nothing but
#: `is_float`, which has exactly two values -- so rebuilding them per
#: operation was pure waste in the interpreter's hottest path.
_INT_NATIVE_FUNCTIONS = _numeric_native_functions(False)
_FLOAT_NATIVE_FUNCTIONS = _numeric_native_functions(True)


def _apply_numeric_native_function(name: str, args: list[Any], is_float: bool) -> Any:
    """Apply an int- or float-typed native function.

    Args:
        name: The operator symbol.
        args: One or two int/float operands (already coerced to a
            matching type by the caller).
        is_float: True if args are float (changes Floor/Ceiling/Int/Float
            unary op behavior and division semantics to match the C#
            source's separate int/float operator tables).

    Returns:
        The operation's result.

    Raises:
        InkPathError: If name has no defined numeric operation.
    """
    first = args[0]
    second = args[1] if len(args) == 2 else None
    op = (_FLOAT_NATIVE_FUNCTIONS if is_float else _INT_NATIVE_FUNCTIONS).get(name)
    if op is None:
        raise InkPathError(f"Native function {name!r} is not defined for numeric operands")
    return op(first, second)


@dataclass
class Pointer:
    """A container plus an index into its content: "the next thing to run."

    Args:
        container: The container being stepped through, or None if this
            pointer has run off the end of the story.
        index: The position within container.content this pointer
            addresses.
    """

    container: Container | None
    index: int = 0

    def resolve(self) -> Any:
        """Return the content this pointer currently addresses.

        Returns:
            container.content[index]; the container itself if index is
            negative (meaning "the container as a whole"); or None if this
            pointer has no container or index is out of range.
        """
        if self.container is None:
            return None
        if self.index < 0:
            return self.container
        if self.index >= len(self.container.content):
            return None
        return self.container.content[self.index]

    def copy(self) -> Pointer:
        """Return a shallow copy: a new Pointer with the same container and index."""
        return Pointer(self.container, self.index)

    @staticmethod
    def start_of(container: Container) -> Pointer:
        """Build a pointer to the first content item of container.

        Args:
            container: The container to point into.

        Returns:
            A Pointer at index 0 of container.
        """
        return Pointer(container, 0)


@dataclass
class CallFrame:
    """One `== function ==` call-stack frame.

    Only functions use this; tunnels use the simpler `tunnel_stack`.

    Args:
        return_pointer: Where to resume the caller once this frame pops
            (via FUNCTION_RETURN or falling off the end of the function's
            container).
        temps: This call's own local `temp=` scope, separate from
            `InkRuntimeState.temps`, which backs the outermost level.
    """

    return_pointer: Pointer
    temps: dict[str, Any] = field(default_factory=dict)


#: The plain scalar fields a save carries: (saved key, attribute name,
#: how to coerce on load, default when a save predates the field). Both
#: halves of serialization read this one list, so a field cannot be
#: written and then not read back -- the mismatch that survives a
#: round-trip test unnoticed, because a key absent from BOTH halves
#: round-trips perfectly while silently dropping real data.
#:
#: Only fields whose default is a constant belong here. `story_seed`
#: defaults to whatever the live instance already generated, and
#: `string_capture_eval_depth` falls back to a value derived from other
#: restored state; both stay explicit below.
_SCALAR_STATE_FIELDS: tuple[tuple[str, str, Callable[[Any], Any], Any], ...] = (
    ("turn_count", "turn_count", int, -1),
    ("previous_random", "previous_random", int, 0),
    ("done", "done", bool, False),
    ("last_turn_text", "last_turn_text", str, ""),
    ("eval_run_depth", "_eval_run_depth", int, 0),
    ("pending_thread", "_pending_thread", bool, False),
    ("in_tag", "_in_tag", bool, False),
)


# Mirrors the real engine's StoryState, which has the same dozens of
# fields; not removable while this class owns the whole interpreter.
class InkRuntimeState:  # pylint: disable=too-many-instance-attributes
    """Tracks one story's playthrough position, output, and choices.

    Runs the compiled "global decl" container once at construction to
    initialize VAR declarations (ports Story.ResetGlobals).

    Args:
        root: The story's root Container (from load_story_root()).
        list_defs: The story's LIST definitions (from load_list_defs()),
            {list_name: {item_name: int_value}}. Defaults to {} for
            stories with no LIST declarations.
        engine_bindings: Real Python callables to dispatch EXTERNAL calls
            to, keyed by the exact function name declared in the story.
            None/empty by default; whether to pass real bindings is the
            application's decision. Every bound callable must be
            stateless (see _call_function).
        random_engine: A factory taking a seed and returning a
            `RandomEngine`, called fresh each time a seeded sequence is
            needed. Defaults to `NetRandom`, which reproduces the .NET
            generator inklecate runs — override only to match a
            different story format's reference implementation.
    """

    def __init__(
        self,
        root: Container,
        list_defs: dict[str, dict[str, int]] | None = None,
        engine_bindings: dict[str, Callable[..., Any]] | None = None,
        random_engine: Callable[[int], RandomEngine] = NetRandom,
        *,
        strict_externals: bool = False,
    ) -> None:
        self.root = root
        self.list_defs = list_defs or {}
        self.engine_bindings = engine_bindings or {}
        self.random_engine = random_engine
        # Live application setting, never serialized -- it says how this process
        # should react to a gap, not anything about the story's progress.
        self.strict_externals = strict_externals
        self.pointer: Pointer | None = Pointer.start_of(root)
        self.previous_pointer: Pointer | None = None
        self.output = OutputStream()
        self.current_choices: list[Choice] = []
        # Per-turn, reset alongside current_choices in continue_story();
        # never shown to the player. Flag 0x8: auto-followed if no other
        # choice was generated this turn, otherwise dropped — an invisible
        # default among real choices is not a fallback.
        self._invisible_default_choices: list[Choice] = []
        self.visit_counts: dict[int, int] = {}
        self.visit_turns: dict[int, int] = {}
        # visit_counts/visit_turns are keyed by id(container), and Python
        # has no id() -> object map, so serialization cannot recover the
        # containers from those keys alone. Holding them here -- strongly,
        # which also prevents an id being reused while a key still names
        # it -- replaces walking the whole tree to find them again.
        self._visited_containers: dict[int, Container] = {}
        self.current_tags: list[str] = []
        self._in_tag = False
        self._tag_buffer = OutputStream()
        # Tags written inside a choice's own brackets, collected while its
        # text is evaluated and handed to the Choice built from it.
        self._pending_choice_tags: list[str] = []
        self._choice_tag_buffer: OutputStream | None = None
        # This turn's own starting state, for refresh_choices().
        self._turn_start: dict[str, Any] | None = None
        self.done = False
        self._eval_run_depth = 0
        self.globals: dict[str, Any] = {}
        self.temps: dict[str, Any] = {}
        self.eval_stack: list[Any] = []
        self._string_capture_stack: list[OutputStream] = []
        # Parallel to _string_capture_stack: _eval_run_depth at the moment
        # each entry's "str" marker was processed. Needed to tell literal
        # text that collides with an operator/EVAL_OUTPUT token's bare
        # string (e.g. "?", "out") apart from that same token used as real
        # eval-run machinery, both of which can appear inside one capture.
        # A bare `_eval_run_depth > 0` check is insufficient: the capture's
        # own baseline depth is already > 0 whenever it is nested inside a
        # choice/tag's surrounding "ev" (the common case). Comparing
        # against the recorded baseline distinguishes "inside the nested
        # eval run this capture opened" from "back at this capture's own
        # text level".
        self._string_capture_eval_depth: list[int] = []
        self.tunnel_stack: list[Pointer] = []
        self.call_stack: list[CallFrame] = []
        self._pending_thread = False
        self.turn_count = -1
        self.story_seed = self.random_engine(time_seed()).next() % 100
        self.previous_random = 0
        self.last_turn_text = ""
        self._turn_guard_lock = threading.Lock()
        self._running_thread: int | None = None
        self._turn_depth = 0
        self._register_list_item_globals()
        self._run_global_decl()

    def _register_list_item_globals(self) -> None:
        """Pre-register every LIST item name as a single-item-value global.

        Ports the observable effect of ListDefinitionsOrigin's item
        lookup: a bare item name compiles to an ordinary VariableReference,
        so it must be a resolvable global before any story content runs.

        Real Ink treats two LISTs sharing an item name as a compile-time
        ambiguity error; here a later origin's item silently wins.
        """
        for list_name, items in self.list_defs.items():
            for item_name, value in items.items():
                self.globals[item_name] = ListValue.single(list_name, item_name, int(value))

    def _visit_count(self, container: Container) -> int:
        """Return how many times `container` has been stepped into, 0 if never."""
        return self.visit_counts.get(id(container), 0)

    def _record_visit(self, container: Container, at_start: bool = True) -> None:
        """Increment container's visit count and/or record this turn's
        index against it, gated by its compiled count-flags.

        Ports Story.VisitContainer's gating
        (`if (!container.countingAtStartOnly || atStart)`): a container
        flagged counting-at-start-only (a once-only choice gather/knot)
        counts a visit only when entered at its own first content item,
        not when resumed or stepped past partway through. Visit count and
        turn index are gated independently by the
        visits_should_be_counted/turn_index_should_be_counted bits.

        Args:
            container: The container being entered.
            at_start: True if this visit enters container at its own index
                0 — the ordinary case, since descending into a container
                lands on its first item and a divert/choice target is
                always Pointer.start_of(target). Only matters for a
                container flagged counting_at_start_only.
        """
        if container.counting_at_start_only and not at_start:
            return
        if container.visits_should_be_counted:
            self.visit_counts[id(container)] = self._visit_count(container) + 1
            self._visited_containers[id(container)] = container
        if container.turn_index_should_be_counted:
            self.visit_turns[id(container)] = self.turn_count
            self._visited_containers[id(container)] = container

    def _run_global_decl(self) -> None:
        """Run the compiled "global decl" container once, if present.

        Ports Story.ResetGlobals: VAR declarations compile into a
        container named "global decl", which must run once before play
        starts so `self.globals` holds each VAR's initial value.
        self.pointer and self.done are restored afterwards.
        """
        # Through content_with_component(), not a bare named_content read:
        # on a lazily-built tree the knot is deferred until something asks
        # for it by name, and a direct dict read would silently answer None
        # -- skipping every VAR initialisation in the story.
        global_decl = self.root.content_with_component(PathComponent(name="global decl"))
        if not isinstance(global_decl, Container):
            return

        original_pointer = self.pointer
        self.pointer = Pointer.start_of(global_decl)
        while not self.done and self.pointer is not None:
            if self._step():
                break
        self.pointer = original_pointer
        self.done = False

    def _pop_eval_stack(self, default: Any = 0) -> Any:
        """Pop one value off eval_stack, returning `default` if it is empty.

        A recognized-but-unimplemented token can fail to push the value a
        later token pops; tolerating that keeps it from crashing the turn.
        """
        return self.eval_stack.pop() if self.eval_stack else default

    def _duplicate_top_of_eval_stack(self) -> None:
        """Push a copy of eval_stack's top value, tolerating an empty stack.

        Ports ControlCommand.CommandType.Duplicate, shared by
        _handle_string_content's DUPLICATE_TOP branch and
        _handle_eval_run_command's: a switch-on-value construct's "du"
        token can be reached at either eval-run depth, depending on
        whether the switch sits inside an outer, still-open eval bracket.
        """
        if self.eval_stack:
            self.eval_stack.append(self.eval_stack[-1])

    @property
    def _current_temps(self) -> dict[str, Any]:
        """Return the temp-variable scope for the innermost active call frame.

        Tunnels push no CallFrame, so a tunnel body shares the outermost
        flat scope -- real Ink likewise gives a tunnel no new scope.

        Returns:
            self.call_stack[-1].temps if a function call is active,
            otherwise self.temps (the outermost scope).
        """
        if self.call_stack:
            return self.call_stack[-1].temps
        return self.temps

    def _read_variable(self, name: str) -> Any:
        """Look up a variable's current value by name.

        Checks the current call frame's temps before globals, matching
        the reference's declared-shadowing order (a temp can shadow a
        global of the same name).

        Args:
            name: The variable's name.

        Returns:
            Its current value, or 0 if never declared (matches
            VariablesState's own "Variable not found... default value of
            0" warning-and-continue behavior rather than raising).
        """
        temps = self._current_temps
        if name in temps:
            return temps[name]
        if name in self.globals:
            return self.globals[name]
        return 0

    def _resolve_variable_pointer(self, pointer: VariablePointer) -> VariablePointer:
        """Return `pointer` with its context_index bound to a real scope.

        Ports Story.ResolveVariablePointer. An already-resolved pointer is
        returned unchanged, so re-pushing one (passing a `ref` parameter
        straight on to another `ref` parameter) keeps pointing at the
        original variable rather than at the intermediate name.

        Args:
            pointer: The pointer as loaded, usually with context_index -1.

        Returns:
            A pointer whose context_index is 0 for a global, or the
            1-based call-frame index whose temps hold the name.
        """
        if pointer.context_index != -1:
            return pointer
        existing = self._current_temps.get(pointer.name)
        if isinstance(existing, VariablePointer):
            # Passing a `ref` parameter straight on to another `ref`
            # parameter forwards the ORIGINAL pointer. Re-resolving to the
            # current frame instead would move the target one level deeper
            # per recursion, so upstream's pop()/reach() pair would write
            # to a fresh scope each time and never drain its list.
            return self._resolve_variable_pointer(existing)
        # Otherwise bind to the scope holding the name right now: the
        # caller's, since the callee's frame is not pushed until after its
        # arguments are evaluated.
        if pointer.name in self._current_temps:
            # A temp held outside any call frame needs its own marker: 0
            # already means "a global", and the frame indices start at 1.
            scope = len(self.call_stack) or OUTERMOST_TEMP_SCOPE
            return VariablePointer(name=pointer.name, context_index=scope)
        return VariablePointer(name=pointer.name, context_index=0)

    def _pointer_scope(self, pointer: VariablePointer) -> dict[str, Any]:
        """Return the variable dict a resolved pointer addresses.

        Args:
            pointer: A pointer whose context_index has been resolved.

        Returns:
            self.globals for context_index 0, self.temps for the outermost
            temp scope, otherwise that call frame's own temps (falling back
            to globals if the frame has since been popped).
        """
        if pointer.context_index == OUTERMOST_TEMP_SCOPE:
            return self.temps
        if pointer.context_index <= 0:
            return self.globals
        index = pointer.context_index - 1
        if index < len(self.call_stack):
            return self.call_stack[index].temps
        return self.globals

    def _read_through_pointer(self, value: Any) -> Any:
        """Return the pointed-to value if `value` is a pointer, else `value`.

        Args:
            value: Anything just read out of a variable.

        Returns:
            The referenced variable's current value for a VariablePointer;
            `value` unchanged otherwise.
        """
        if not isinstance(value, VariablePointer):
            return value
        resolved = self._resolve_variable_pointer(value)
        return self._pointer_scope(resolved).get(resolved.name, 0)

    def _write_through_pointer(self, pointer: VariablePointer, value: Any) -> None:
        """Store `value` in the variable `pointer` addresses.

        Args:
            pointer: The `ref` parameter's pointer.
            value: The value to store in the pointed-to variable.
        """
        resolved = self._resolve_variable_pointer(pointer)
        self._pointer_scope(resolved)[resolved.name] = value

    def _write_variable(self, assignment: VariableAssignment, value: Any) -> None:
        """Store a value under a VariableAssignment's target name.

        Args:
            assignment: The assignment being performed (says whether it's
                a global VAR= or a local temp=).
            value: The value popped off eval_stack to store.
        """
        existing = self._current_temps.get(assignment.name)
        if isinstance(existing, VariablePointer) and not assignment.is_new_declaration:
            # `existing` is a bound `ref` parameter and this is a
            # REASSIGNMENT ("re": true), so it writes to the caller's
            # variable. The initial `{"temp=": name}` that binds the
            # parameter has no "re" and must store the pointer itself.
            self._write_through_pointer(existing, value)
            return
        if assignment.is_global:
            self.globals[assignment.name] = value
        else:
            self._current_temps[assignment.name] = value

    @staticmethod
    def _resolve_target(holder: Container, root: Container, path: Path) -> Any | None:
        """Resolve a Divert/ChoicePoint target path to the content it addresses.

        Ports Object.ResolvePath: absolute paths resolve from root,
        relative ones from holder. A leading "^" is NOT a step up to
        `holder.parent` — it only marks the path relative and is
        discarded, so `.^.c-0` addresses content within holder itself.

        Args:
            holder: The container that directly holds the Divert/
                ChoicePoint whose target_path is being resolved.
            root: The story's root container, used for absolute paths.
            path: The target path (relative or absolute).

        Returns:
            The resolved content (usually a Container), or None if any
            component fails to resolve.
        """
        if not path.is_relative:
            return resolve_path(root, path)
        components = path.components
        if components and components[0].is_parent:
            components = components[1:]
        return resolve_path(holder, Path(components=components, is_relative=True))

    def _resolve_target_cached(
        self, owner: Divert | ChoicePoint | FunctionCall | ReadCountTarget | DivertTargetValue, holder: Container, path: Path
    ) -> Any | None:
        """Resolve `owner.target_path` (== `path`), memoized on `owner` itself.

        Only valid where the answer is fixed for the life of the loaded
        tree. A variable-target divert, or a path derived from
        `owner.target_path` rather than equal to it, must use the
        uncached `_resolve_target()` — `owner`'s cache would answer a
        different question.

        Args:
            owner: The object whose own `target_path` is being resolved.
            holder: The container directly holding `owner` (see
                `_resolve_target()`).
            path: `owner.target_path` itself, not a path derived from it.

        Returns:
            The resolved content, or None if resolution fails — either
            way, cached on `owner`.
        """
        cached = owner._resolved_target_cache  # pylint: disable=protected-access
        if cached is not _UNRESOLVED:
            return cached
        resolved = self._resolve_target(holder, self.root, path)
        owner._resolved_target_cache = resolved  # pylint: disable=protected-access
        return resolved

    def _visit_changed_containers_due_to_divert(self) -> None:
        """Record visits for ancestor containers newly entered by a jump.

        Ports VisitChangedContainersDueToDivert. `_descend_into_containers`
        records only containers below the new pointer, so this walks up its
        parent chain, skipping any ancestor the previous pointer already
        had (which would otherwise be double-counted).

        An ancestor counts as entered-at-start only if the child pointing
        into it is that ancestor's `content[0]` and every ancestor closer
        to the leaf was too (ports the allChildrenEnteredAtStart latch),
        which matters only for a `counting_at_start_only` container.
        """
        pointer = self.pointer
        if pointer is None or pointer.container is None:
            return

        previous_ancestors: set[int] = set()
        if self.previous_pointer is not None and self.previous_pointer.container is not None:
            resolved = self.previous_pointer.resolve()
            ancestor: Container | None = resolved if isinstance(resolved, Container) else self.previous_pointer.container
            while ancestor is not None:
                previous_ancestors.add(id(ancestor))
                ancestor = ancestor.parent

        child: Any = pointer.resolve()
        current_ancestor: Container | None = pointer.container
        all_at_start = True
        while current_ancestor is not None and (id(current_ancestor) not in previous_ancestors or current_ancestor.counting_at_start_only):
            # Ports the C# loop condition: an already-"open" ancestor is
            # still re-evaluated when flagged counting_at_start_only,
            # since a loop-back divert (`-> start` from a container nested
            # under `start`) must record a fresh at-start visit for
            # `start`, even though it is still open in the previous
            # pointer's ancestry.
            entering_at_start = bool(current_ancestor.content) and child is current_ancestor.content[0] and all_at_start
            all_at_start = entering_at_start
            self._record_visit(current_ancestor, at_start=entering_at_start)
            child = current_ancestor
            current_ancestor = current_ancestor.parent

    def _divert_start(self, divert: Divert, holder: Container) -> Pointer:
        """Resolve a Divert's target path to a starting Pointer.

        Ports Divert.target_pointer's is_index special case. Without it, a
        divert whose target path ends in an index rather than a name
        resolves to a null pointer.

        Args:
            divert: The divert being followed.
            holder: The container that directly holds this divert object
                (used as the resolution start for a relative target path).

        Returns:
            A Pointer at the start of the target container; or, if the
            target path's last component is an index (meaning "resume
            inside this container at this position", not "enter this
            leaf as a container"), a Pointer at that index within the
            leaf's own parent container; or a null Pointer if resolution
            failed entirely.
        """
        if divert.is_variable_target:
            # Ports the variable-target branch of Story's Divert
            # handling: the "path" is a variable name, whose current value
            # must be a ResolvedDivertTarget (a DivertTargetValue already
            # resolved at push time). Ink's empty-bracket choice syntax
            # `* text[]` exercises this.
            assert divert.target_path.components[0].name is not None
            var_name = divert.target_path.components[0].name
            value = self._read_variable(var_name)
            if not isinstance(value, ResolvedDivertTarget) or value.container is None:
                return Pointer(None)
            return Pointer.start_of(value.container)

        target = self._resolve_target_cached(divert, holder, divert.target_path)
        if isinstance(target, Container):
            return Pointer.start_of(target)

        components = divert.target_path.components
        if target is not None and components and components[-1].is_index:
            parent_path = Path(components=components[:-1], is_relative=divert.target_path.is_relative)
            if parent_path.components:
                parent = self._resolve_target(holder, self.root, parent_path)
            else:
                parent = holder if divert.target_path.is_relative else self.root
            if isinstance(parent, Container):
                assert components[-1].index is not None
                return Pointer(parent, components[-1].index)

        return Pointer(None)

    def _follow_divert(self, divert: Divert, holder: Container) -> None:
        """Update self.pointer for one Divert encountered while stepping.

        Args:
            divert: The divert being processed.
            holder: The container directly holding this divert (used to
                resolve its target path if relative).
        """
        if self._pending_thread:
            self._pending_thread = False
            assert self.pointer is not None
            self.pointer = self._advance_past(self.pointer)
            self._run_thread(divert, holder)
            return

        if divert.is_conditional and not _is_truthy(self._pop_eval_stack()):
            assert self.pointer is not None
            self.pointer = self._advance_past(self.pointer)
            return

        if divert.pushes_tunnel:
            # Ports CallStack.push(PushPopType.Tunnel): a `-> knot ->`
            # divert pushes the position right after itself as a return
            # address before jumping, so a later `->->` (PopTunnel)
            # resumes here instead of ending the story. Function frames
            # are handled separately, via call_stack.
            assert self.pointer is not None
            return_address = self._advance_past(self.pointer)
            assert return_address is not None
            self.tunnel_stack.append(return_address)

        self.previous_pointer = self.pointer
        self.pointer = self._divert_start(divert, holder)
        self._visit_changed_containers_due_to_divert()

    def _run_thread(self, divert: Divert, holder: Container) -> None:
        """Run a `<- knot` thread as an isolated sub-walk to its own stop point.

        Ports StartThread: a thread runs immediately and synchronously,
        stepping its own independent Pointer from the divert's target
        until it falls off the end (silently discarded) or reaches its own
        choice points, which are appended to self.current_choices. Running
        at the "thread" marker means its choices land BEFORE the main
        flow's, and choosing one abandons the main flow's pending choices
        and position.

        A bare DONE_COMMANDS inside the thread ends only the thread's
        sub-walk; self.done is never touched, so the main flow's
        "-> DONE" still runs.

        Args:
            divert: The thread's own target divert (the one immediately
                following the "thread" marker).
            holder: The container directly holding this divert (used to
                resolve its target path if relative).
        """
        target = self._resolve_target_cached(divert, holder, divert.target_path)
        if not isinstance(target, Container):
            return

        thread_pointer: Pointer | None = Pointer.start_of(target)
        thread_done = False
        while not thread_done and thread_pointer is not None:
            thread_pointer = self._descend_into_containers(thread_pointer)
            thread_container = thread_pointer.container
            assert thread_container is not None
            if thread_pointer.index >= len(thread_container.content):
                break
            content = thread_pointer.resolve()
            if content is None:
                thread_pointer = self._advance_pointer(thread_pointer)
                continue
            if isinstance(content, str) and content in DONE_COMMANDS:
                break
            saved_pointer = self.pointer
            self.pointer = thread_pointer
            thread_done = self._dispatch_content(content, thread_pointer, thread_container)
            thread_pointer = self.pointer
            self.pointer = saved_pointer

    def _pop_tunnel(self) -> None:
        """Handle "->->" (PopTunnel), plain or with an override target.

        Ports the PopTunnel branch of
        Story._perform_logic_and_flow_control: pops one value off
        eval_stack, then resumes at the most recently pushed tunnel return
        address. The compiler emits a void before a plain `->->`, and the
        divert target before `->-> elsewhere` (WritingWithInk.md,
        "Tunnels can return elsewhere").

        An override consumes its tunnel frame rather than pushing a new
        one, so the next `->->` returns to the caller one level further
        out.

        An empty tunnel_stack ends the story rather than raising, as
        DONE_COMMANDS does for unexpected ends.
        """
        override = self._pop_eval_stack()
        if not self.tunnel_stack:
            self.done = True
            return
        return_pointer = self.tunnel_stack.pop()
        if isinstance(override, ResolvedDivertTarget) and override.container is not None:
            self.pointer = Pointer.start_of(override.container)
            self._visit_changed_containers_due_to_divert()
            return
        self.pointer = return_pointer

    def _call_function(self, call: FunctionCall, holder: Container) -> None:
        """Push a CallFrame and jump into a `{"f()": path}` function call.

        Ports the Function branch of CallStack.Push. Arguments are
        already on eval_stack; the body's leading `temp=` assignments pop
        them, so Ink-side arity is never needed here.

        A target may be relative (".^.^.^" for direct recursion), so it
        resolves via `_resolve_target`, not a bare `root.named_content`
        lookup.

        EXTERNAL dispatch: a Python callable in `engine_bindings` under
        the target name wins over the Ink fallback. It needs real arity —
        `call.external_arg_count` values are popped and passed
        positionally in push order. Bound callables must be stateless:
        argument values in, one value out. A non-EXTERNAL unresolved call
        degrades to pushing 0.

        Args:
            call: The function call being processed.
            holder: The container directly holding this call (used to
                resolve its target path if relative).

        Raises:
            UnboundExternalError: The call is EXTERNAL and neither a
                bound Python callable nor an Ink fallback exists for it;
                or `strict_externals` is set and no callable is bound,
                whether or not a fallback exists.
        """
        if call.is_external:
            binding = self.engine_bindings.get(str(call.target_path))
            if binding is not None:
                arg_count = call.external_arg_count or 0
                args = [self.eval_stack.pop() for _ in range(arg_count)]
                args.reverse()
                self.eval_stack.append(binding(*args))
                assert self.pointer is not None
                self.pointer = self._advance_past(self.pointer)
                return
            if self.strict_externals:
                # An unwired binding whose story ships a fallback is
                # invisible otherwise: the fallback answers plausibly and
                # play continues.
                raise UnboundExternalError(f"EXTERNAL '{call.target_path}' has no bound Python callable (strict_externals=True)")

        target = self._resolve_target_cached(call, holder, call.target_path)
        if not isinstance(target, Container):
            if call.is_external:
                raise UnboundExternalError(f"Missing function binding for external: '{call.target_path}', and no fallback ink function found.")
            # An unresolvable ordinary function name is a story error in
            # real Ink; degrade to 0 rather than crash.
            self.eval_stack.append(0)
            assert self.pointer is not None
            self.pointer = self._advance_past(self.pointer)
            return

        assert self.pointer is not None
        return_pointer = self._advance_past(self.pointer)
        assert return_pointer is not None
        self.call_stack.append(CallFrame(return_pointer=return_pointer))
        self.pointer = Pointer.start_of(target)
        self._visit_changed_containers_due_to_divert()

    def _return_from_function(self) -> None:
        """Handle a bare "~ret" (function return) control command.

        Ports the Function branch of
        Story._perform_logic_and_flow_control popping a CallFrame: the
        return value is already on eval_stack, pushed by the preceding
        "ev...{VAR?: name}.../ev" run, so this only restores self.pointer
        to the frame's return address. An empty call_stack (a "~ret"
        outside any call, not produced by well-formed compiled output)
        ends the story rather than raising, as _pop_tunnel does.
        """
        if not self.call_stack:
            self.done = True
            return
        frame = self.call_stack.pop()
        self.pointer = frame.return_pointer
        # C#'s functionTrimIndex: newlines the function's own body emitted
        # are dropped as its frame pops, so a call mid-line (`Before
        # {emit()} after.`) leaves the caller's line unbroken.
        self.output.trim_newlines_from_end()

    def _advance_past(self, pointer: Pointer) -> Pointer | None:
        """Move one content item past pointer, walking up ended containers.

        Ports the non-call-stack portion of Story._next_content: increments
        pointer.index; if that runs past the end of container.content,
        walks up to the parent container and continues from just after the
        child that ended, repeating until a valid position is found or the
        story root has no parent left to walk up to.

        Args:
            pointer: The current position (must have a container).

        Returns:
            The next Pointer, or None if the story has no more content
            anywhere above pointer.
        """
        current = pointer.copy()
        current.index += 1
        while current.container is not None and current.index >= len(current.container.content):
            ancestor = current.container.parent
            if ancestor is None or current.container not in ancestor.content:
                # No positional sibling to advance to: either the story
                # root, or a container reached by named/knot addressing
                # rather than positional nesting (falling off the end of a
                # knot with no divert). Both mean the story has run out of
                # content, which real Ink treats as falling off the end
                # rather than an error.
                return None
            child_index = ancestor.content.index(current.container)
            current = Pointer(ancestor, child_index + 1)
        return current

    def _advance_pointer(self, pointer: Pointer) -> Pointer | None:
        """Advance the live self.pointer, popping a function frame if needed.

        The one place that tells end-of-story from an implicit Void
        return: both reach `_advance_past()`'s "no sibling, no parent"
        case, but with a CallFrame active it means the call is over. The
        story has genuinely ended only when call_stack is empty too.

        Args:
            pointer: The current pointer to advance from.

        Returns:
            The next Pointer; or, if a function frame popped, that frame's
            return_pointer; or None if the story has genuinely ended.
        """
        result = self._advance_past(pointer)
        while result is None and self.call_stack:
            self.eval_stack.append(VOID)
            frame = self.call_stack.pop()
            result = frame.return_pointer
            self.output.trim_newlines_from_end()
        return result

    def _descend_into_containers(self, pointer: Pointer) -> Pointer:
        """Step into nested empty-index containers until content is reached.

        A pointer whose resolved content is itself a Container (Ink nests
        containers for grouping, e.g. a choice's own sub-container) doesn't
        point at real leaf content yet — descend to that container's first
        item, recording a visit for each container entered along the way.

        Args:
            pointer: The position to descend from.

        Returns:
            A Pointer at real leaf content (or an empty container with no
            content of its own, left as-is).
        """
        current = pointer
        content = current.resolve()
        while isinstance(content, Container):
            self._record_visit(content)
            if not content.content:
                break
            current = Pointer.start_of(content)
            content = current.resolve()
        return current

    def _process_choice_point(self, choice_point: ChoicePoint, holder: Container) -> None:
        """Evaluate a ChoicePoint and append a Choice if it should be shown.

        Ports Story.ProcessChoice: pops eval_stack in the fixed order the
        compiler emits pushes in — condition value first (pushed last, so
        on top), then choice-only text, then start text, matching the C#
        source's hasChoiceOnlyContent-before-hasStartContent field order.
        The pops happen whether or not the choice is shown.

        Args:
            choice_point: The choice point being processed.
            holder: The container that directly holds this choice point
                (used to resolve its target path if relative).
        """
        show_choice = True
        if choice_point.has_condition and not _is_truthy(self._pop_eval_stack()):
            show_choice = False

        choice_only_text = self._pop_eval_stack(default="") if choice_point.has_choice_only_content else ""
        start_text = self._pop_eval_stack(default="") if choice_point.has_start_content else ""
        # Claimed here, beside the pops and for the same reason: these were
        # collected while THIS choice's text was evaluated, so a choice that
        # is never shown must still take them rather than leave them for
        # whichever choice is built next.
        tags = self._pending_choice_tags
        self._pending_choice_tags = []

        if not show_choice:
            return

        target = self._resolve_target_cached(choice_point, holder, choice_point.target_path)
        if not isinstance(target, Container):
            return

        if choice_point.once_only and self._visit_count(target) > 0:
            return

        text = (str(start_text) + str(choice_only_text)).strip()
        choice = Choice(text=text, target=target, tags=tags)
        if choice_point.is_invisible_default:
            self._invisible_default_choices.append(choice)
        else:
            self.current_choices.append(choice)

    def _handle_string_in_capture(self, content: str) -> None:
        """Push one leaf token into the innermost active string-capture stream.

        Args:
            content: The leaf value to capture (text, glue, or newline).
        """
        capture = self._string_capture_stack[-1]
        if content in (GLUE, NEWLINE):
            capture.push(content)
        else:
            capture.push_text(content)

    def _handle_string_capture_command(self, content: str) -> bool:
        """Handle one string leaf token belonging to the str/.../str family.

        Args:
            content: The leaf value.

        Returns:
            True if content was a string-capture marker or was consumed by
            an active capture; False if the caller should try other
            eval-run command types instead.
        """
        if content == STRING_START:
            # Ports BeginString/EndString: text between str and /str is
            # captured into its own OutputStream, so it still gets real
            # glue/newline handling, then closed into a single string
            # value pushed onto eval_stack when /str arrives.
            self._string_capture_stack.append(OutputStream())
            self._string_capture_eval_depth.append(self._eval_run_depth)
            return True
        if content == STRING_END:
            captured = self._string_capture_stack.pop()
            self._string_capture_eval_depth.pop()
            self.eval_stack.append(captured.get_string_value())
            return True
        if self._string_capture_stack:
            # A tag written inside a choice's own brackets (`* [Go #
            # image: x.jpg]`) compiles to "#"/"/#" around its text INSIDE
            # the choice-text capture. Collect it as a tag: swallowing the
            # markers alone would leave the tag's text in the choice's
            # visible label.
            if content == BEGIN_TAG:
                self._choice_tag_buffer = OutputStream()
                return True
            if content == END_TAG and self._choice_tag_buffer is not None:
                self._pending_choice_tags.append(self._choice_tag_buffer.get_text().strip())
                self._choice_tag_buffer = None
                return True
            if self._choice_tag_buffer is not None and content not in CONTROL_COMMAND_MARKERS:
                self._choice_tag_buffer.push_text(content)
                return True
            if content in CONTROL_COMMAND_MARKERS and content != EVAL_OUTPUT:
                # A bare "nop" can appear inside an active str/../str
                # capture, not just at the main-stream level — e.g. as a
                # branch separator in a conditional-choice-text construct
                # (`* [Follow {cond:A|B}]`). It is consumed silently here,
                # as the main-stream branch does, rather than captured as
                # text. No depth gate is needed: a bare "nop" is
                # unambiguous at any depth, real choice/tag text never
                # legally containing one.
                #
                # EVAL_OUTPUT ("out") is excluded from this unconditional
                # path despite being in CONTROL_COMMAND_MARKERS: it is
                # depth-sensitive, always marking a nested eval run's
                # output, so it must fall through to the depth-gated check
                # below. Swallowing it here would discard the interpolated
                # VAR's value before _handle_eval_run_command's EVAL_OUTPUT
                # handling ever saw it.
                return True
            if self._eval_run_depth > self._string_capture_eval_depth[-1] and (content in NATIVE_FUNCTION_ARITY or content in EVAL_STACK_COMMANDS):
                # A choice-text conditional's inline condition check
                # (`{lvl == 2:"A"|B}` inside `* [...]`) or a plain
                # `{var}`/`{expr}` interpolation compiles to a nested
                # "ev"/"/ev" pair inside the outer choice-text "str"/"/str"
                # capture. The operator/EVAL_OUTPUT tokens of that inner
                # run (the bare string "==", or "out") are eval-stack
                # machinery, not text, and must reach their normal
                # handlers rather than being captured as literal text.
                #
                # The gate compares _eval_run_depth against the baseline
                # recorded for this specific capture
                # (_string_capture_eval_depth[-1]), not a bare `> 0`:
                # several of these bare-string markers are also valid
                # literal text characters at the capture's own base level,
                # which is commonly > 0 already because of a choice/tag's
                # surrounding "ev" run. In a capture like `"str",
                # "^Obey the ", "ev", {VAR?:...}, "out", "/ev", "^?",
                # "/str"`, depth is 1 at the base level and only rises to
                # 2 inside the nested "ev"/"/ev". A bare `> 0` check would
                # match the literal "?" after that block, since it collides
                # with LIST_NATIVE_FUNCTION_ARITY's "?" contains-operator,
                # though it is plain punctuation there. The per-capture
                # baseline routes that "?" to plain-text capture while
                # still routing "out"/"==" to eval-stack handling inside
                # the nested run.
                return False
            self._handle_string_in_capture(content)
            return True
        return False

    def _handle_eval_run_command(self, content: str) -> bool:
        """Handle one string leaf token while inside an "ev".."/ev" run.

        Args:
            content: The leaf value (an operator symbol, EVAL_OUTPUT, a
                string-capture marker, or an eval-run-local literal).

        Returns:
            True if content was recognized and handled here; False if the
            caller should fall through to ordinary main-stream handling
            (only possible for EVAL_START/EVAL_END themselves, handled by
            the caller, not this method).
        """
        if self._handle_string_capture_command(content):
            return True
        if content == EVAL_OUTPUT:
            if self.eval_stack:
                # A `ref` parameter on the stack is a pointer; printing it
                # prints the variable it addresses.
                value = self._read_through_pointer(self._pop_eval_stack())
                if not isinstance(value, Void):
                    # The innermost active capture context wins. A
                    # `{var}`/`{expr}` interpolation inside an active
                    # str/../str capture (a choice-text VAR interpolation,
                    # `* [Obey the {officer_title}?]`) must write into that
                    # capture's OutputStream; writing to self.output would
                    # lose the interpolated text and everything captured
                    # after it in the same run. String capture takes
                    # priority over tag capture, since an interpolation can
                    # sit inside a str/../str run that is itself part of a
                    # tag's text (`{cond:"a {var}"|"b"}`).
                    if self._string_capture_stack:
                        self._handle_string_in_capture(_display_string(value))
                    elif self._in_tag:
                        self._tag_buffer.push_text(_display_string(value))
                    else:
                        self.output.push_text(_display_string(value))
            return True
        if content == VOID_POP:
            # A void function call (`~ bump()`, no `~return`) still leaves
            # a value on eval_stack, for symmetry with non-void calls via
            # real Ink's implicit Void return, and the compiler emits a
            # bare "pop" right after to discard it. _pop_eval_stack()
            # tolerates an empty stack, though a well-formed call always
            # leaves something.
            self._pop_eval_stack()
            return True
        if content == DUPLICATE_TOP:
            # A switch-on-value construct's per-branch "du" can execute at
            # eval-run depth > 0, the whole switch weave container being
            # nestable inside an outer, still-open "ev" bracket, so it
            # needs handling here as well as in _handle_string_content's
            # main-stream branch.
            self._duplicate_top_of_eval_stack()
            return True
        return self._handle_eval_run_command_tail(content)

    def _handle_eval_run_command_tail(self, content: str) -> bool:
        """Handle the story-metadata/RNG/native-function tail of an eval
        run command, once the always-present markers (string-capture,
        EVAL_OUTPUT, VOID_POP, DUPLICATE_TOP) are ruled out.

        Args:
            content: The leaf value, already confirmed not one of the
                markers _handle_eval_run_command itself handles.

        Returns:
            True (every case here is either handled or the intentional
            unreachable-literal fallthrough, both treated as consumed).
        """
        for group, handler in (
            (STORY_METADATA_COMMANDS, self._handle_story_metadata_command),
            (RNG_COMMANDS, self._handle_rng_command),
            (LIST_COMMANDS, self._handle_list_command),
            (NATIVE_FUNCTION_ARITY, self._apply_operator_defensively),
        ):
            if content in group:
                handler(content)
                return True
        if content == NO_OP:
            # Genuinely nothing to do -- the compiler emits it as a
            # placeholder. Named here so it is consumed deliberately
            # rather than by the fallthrough below.
            return True
        if content in CONTROL_COMMAND_MARKERS:
            # A marker listed as recognized but with no branch above would
            # otherwise be consumed in silence, leaving its operands on the
            # eval stack for the next pop to mistake for a result -- wrong
            # output, no error. LIST_RANGE shipped that way.
            raise InkPathError(f"ControlCommand {content!r} is recognized but has no handler")
        if self._eval_run_depth > 0 and not self._string_capture_stack:
            if self.call_stack and content != VOID_OPERAND:
                # Prose in a function body called from inside an eval run
                # (`Before {emit()} after.`). It is output, not an operand:
                # the call frame is what distinguishes the two, since both
                # arrive at eval-run depth.
                self.output.push_text(content)
                return True
            # A bare string operand, unwrapped by str/../str: LIST(n)
            # compiles its list name this way (`"^Nums", 3, "listInt"`).
            # Inside a capture the same token is text, handled above.
            self.eval_stack.append(content)
            return True
        # Plain literal values (int/float) are dispatched in
        # _dispatch_content by Python type, not as strings. Treated as
        # consumed.
        return True

    def _handle_story_metadata_command(self, name: str) -> None:
        """Handle CHOICE_COUNT/TURNS/TURNS_SINCE/ReadCount/VisitIndex.

        Each of these bare ControlCommand markers pushes a single int onto
        eval_stack, computed from story-level bookkeeping this module
        tracks (current_choices, turn_count, visit_counts, visit_turns).
        Each ports its own distinct C# Story.cs case, documented below.

        Args:
            name: One of CHOICE_COUNT, TURNS, TURNS_SINCE, READ_COUNT, VISIT_INDEX.
        """
        if name == CHOICE_COUNT:
            # Ports ControlCommand.CommandType.ChoiceCount: the number of
            # choices generated so far this turn (C# reads
            # state.generatedChoices.Count). It is always read before any
            # later-in-the-turn ChoicePoint runs, so len(current_choices)
            # at this moment is the right count, not a cross-turn total.
            self.eval_stack.append(len(self.current_choices))
        elif name == TURNS:
            # Ports ControlCommand.CommandType.Turns: state.currentTurnIndex+1.
            self.eval_stack.append(self.turn_count + 1)
        elif name == TURNS_SINCE:
            self._push_turns_since()
        elif name == READ_COUNT:
            self._push_read_count()
        else:
            # VISIT_INDEX. Ports ControlCommand.CommandType.VisitIndex:
            # the current container's visit count minus 1, converting
            # count to a zero-based index. This is the read behind
            # sequences (`{a|b|c}`, capped via MIN) and cycles
            # (`{&a|b|c}`, wrapped via %); a silent no-op here would make
            # every sequence and cycle read 0.
            assert self.pointer is not None and self.pointer.container is not None
            self.eval_stack.append(self._visit_count(self.pointer.container) - 1)

    def _pop_resolved_divert_target(self) -> Container | None:
        """Pop a ResolvedDivertTarget off eval_stack and unwrap it.

        Shared by _push_turns_since()/_push_read_count(), which consume a
        DivertTargetValue's dispatched (container-resolved) form alike.

        Returns:
            The wrapped container, or None if the popped value was not a
            ResolvedDivertTarget or wrapped a failed resolution.
        """
        target = self._pop_eval_stack(default=None)
        if isinstance(target, ResolvedDivertTarget):
            return target.container
        return None

    def _push_turns_since(self) -> None:
        """Handle a bare "turns" (TURNS_SINCE) command.

        Ports StoryState.TurnsSinceForContainer: pops a
        ResolvedDivertTarget (pushed by _dispatch_literal_content's
        DivertTargetValue branch) and pushes how many turns have elapsed
        since that container was last visited, or -1 if never visited. An
        unresolvable target also yields -1, matching the real engine's own
        "failed to find container... assume -1/unknown" fallback.
        """
        target = self._pop_resolved_divert_target()
        if target is None or id(target) not in self.visit_turns:
            self.eval_stack.append(-1)
            return
        self.eval_stack.append(self.turn_count - self.visit_turns[id(target)])

    def _push_read_count(self) -> None:
        """Handle a bare "readc" (ReadCount) command.

        Ports StoryState.VisitCountForContainer via the explicit
        READ_COUNT(-> knot) syntax: pops a ResolvedDivertTarget and pushes
        its visit count, or 0 if never visited or unresolvable, matching
        the real engine's "assume 0, default to allowing entry" fallback.
        """
        target = self._pop_resolved_divert_target()
        self.eval_stack.append(self._visit_count(target) if target is not None else 0)

    def _handle_rng_command(self, name: str) -> None:
        """Handle "rnd" (RANDOM), "srnd" (SEED_RANDOM), "seq"
        (SequenceShuffleIndex, the `{~a|b|c}` shuffle operator), or
        "lrnd" (LIST_RANDOM).

        Ports the Random/SeedRandom/SequenceShuffleIndex/ListRandom
        branches of Story._perform_logic_and_flow_control. Draws from
        `self.random_engine`, which by default reproduces the .NET
        generator so results match real inklecate output for the same
        story_seed.

        Args:
            name: One of RNG_COMMANDS.
        """
        if name == LIST_RANDOM:
            self._push_list_random()
            return
        if name == SEED_RANDOM:
            # SEED_RANDOM(seed): pops the new seed, resets previous_random
            # to 0 (a fresh reseed discards the running RNG state), and
            # pushes a Void placeholder for the compiler's trailing bare
            # "pop" to discard (SEED_RANDOM returns nothing in real Ink).
            self.story_seed = int(self._pop_eval_stack(default=0))
            self.previous_random = 0
            self.eval_stack.append(0)
            return

        if name == RANDOM:
            # RANDOM(min, max): operands pushed min-then-max, so max is on
            # top and popped first.
            max_value = int(self._pop_eval_stack(default=0))
            min_value = int(self._pop_eval_stack(default=0))
            random_range = max_value - min_value + 1
            if random_range <= 0:
                self.eval_stack.append(min_value)
                return
            result_seed = self.story_seed + self.previous_random
            next_random = self.random_engine(result_seed).next()
            self.eval_stack.append((next_random % random_range) + min_value)
            self.previous_random = next_random
            return

        # "seq": SequenceShuffleIndex for `{~a|b|c}`. Operands pushed
        # visit-count-then-num-elements (compiled as "visit", N, "seq"),
        # so num_elements is popped first.
        num_elements = int(self._pop_eval_stack(default=1))
        seq_count = int(self._pop_eval_stack(default=0))
        if num_elements <= 0:
            self.eval_stack.append(0)
            return
        loop_index = seq_count // num_elements
        iteration_index = seq_count % num_elements
        self.eval_stack.append(self._shuffle_index(num_elements, loop_index, iteration_index))

    def _shuffle_index(self, num_elements: int, loop_index: int, iteration_index: int) -> int:
        """Compute which element `{~a|b|c}` should resolve to this visit.

        Modeled on Story.NextSequenceShuffleIndex: derives a seed from the
        current container's path (a character-sum hash), the number of
        completed shuffle passes, and story_seed, then draws without
        replacement from the element indices until iteration_index is
        reached. Reproduces Ink's documented
        shuffle/shuffle-once/shuffle-stopping semantics; the exact hash
        has not been diffed against the C# source.

        Args:
            num_elements: How many alternatives the shuffle has.
            loop_index: How many full shuffle cycles have completed.
            iteration_index: Which draw within the current cycle this is.

        Returns:
            The chosen element's index.
        """
        assert self.pointer is not None and self.pointer.container is not None
        try:
            path_str = _container_path(self.pointer.container)
        except InkPathError:
            # A malformed container tree cannot occur for anything
            # load_story_root() produces, but degrades to an empty path
            # string rather than crashing the turn if it somehow does;
            # only which element this one shuffle picks is affected.
            path_str = ""
        sequence_hash = sum(ord(c) for c in path_str)
        random_seed = sequence_hash + loop_index + self.story_seed
        rng = self.random_engine(random_seed)
        unpicked = list(range(num_elements))
        chosen_index = unpicked[0]
        for i in range(iteration_index + 1):
            chosen = rng.next() % len(unpicked)
            chosen_index = unpicked.pop(chosen)
            if i == iteration_index:
                break
        return chosen_index

    def _push_list_random(self) -> None:
        """Handle "lrnd" (LIST_RANDOM(list)).

        Ports the ListRandom branch of
        Story._perform_logic_and_flow_control: pops a ListValue and, if
        non-empty, picks one entry at random by index into entries in
        their original insertion order — matching .NET Dictionary
        enumeration order for a freshly-built InkList — then pushes a
        single-item ListValue holding it. An empty list, or a popped value
        that is not a ListValue, yields an empty ListValue rather than
        crashing.
        """
        value = self._pop_eval_stack(default=None)
        if not isinstance(value, ListValue) or not value.entries:
            self.eval_stack.append(ListValue())
            return
        result_seed = self.story_seed + self.previous_random
        next_random = self.random_engine(result_seed).next()
        chosen_key, chosen_value = value.entries[next_random % len(value.entries)]
        self.eval_stack.append(ListValue(entries=((chosen_key, chosen_value),), origin_names=(chosen_key[0],)))
        self.previous_random = next_random

    def _handle_list_command(self, name: str) -> None:
        """Handle "range" (LIST_RANGE) or "listInt" (LIST(n)).

        Args:
            name: The control-command marker.
        """
        if name == LIST_RANGE:
            self._push_list_range()
            return
        self._push_list_from_int()

    def _push_list_range(self) -> None:
        """Handle "range" (LIST_RANGE(list, min, max)).

        Ports the ListRange branch of
        Story._perform_logic_and_flow_control: pops max, min and the
        source list, then pushes every entry whose value falls within the
        inclusive bounds. Bounds may be ints or list items -- an item
        contributes its own integer value, so
        `LIST_RANGE(chain, LIST_MIN(chain), x)` works. Out-of-range bounds
        clamp rather than raising (WritingWithInk.md, "a portion of the
        full list"); a non-ListValue source yields an empty ListValue.
        """
        max_bound = self._coerce_list_bound(self._pop_eval_stack(default=None))
        min_bound = self._coerce_list_bound(self._pop_eval_stack(default=None))
        value = self._pop_eval_stack(default=None)
        if not isinstance(value, ListValue) or min_bound is None or max_bound is None:
            self.eval_stack.append(ListValue())
            return
        within = tuple(entry for entry in value.ordered_entries if min_bound <= entry[1] <= max_bound)
        self.eval_stack.append(ListValue(entries=within, origin_names=value.origin_names))

    @staticmethod
    def _coerce_list_bound(bound: Any) -> int | None:
        """Return a LIST_RANGE bound as an int, or None if it is unusable.

        Args:
            bound: A popped int, float or single-item ListValue.

        Returns:
            The bound's integer value; for a ListValue, its highest entry
            (InkList.maxItem, as ListRange uses). None for an empty
            ListValue or a value that is not numeric.
        """
        if isinstance(bound, ListValue):
            entries = bound.ordered_entries
            return entries[-1][1] if entries else None
        if isinstance(bound, bool) or not isinstance(bound, (int, float)):
            return None
        return int(bound)

    def _push_list_from_int(self) -> None:
        """Handle "listInt" (LIST(n), the int-to-list-item conversion).

        Ports the ListFromInt branch of
        Story._perform_logic_and_flow_control: the compiler pushes the
        list name then the integer (`"^Nums", 3, "listInt"`), so the
        integer pops first. Pushes the single item of that list holding
        that value. A name that is not a known list, or a value no item
        holds, yields an empty ListValue -- matching the reference
        runtime, which pushes InkList's null value rather than raising.
        """
        int_value = self._pop_eval_stack(default=None)
        list_name = self._pop_eval_stack(default=None)
        if isinstance(list_name, ListValue):
            origins = list_name.origin_names
            list_name = origins[0] if origins else None
        if not isinstance(list_name, str) or isinstance(int_value, bool) or not isinstance(int_value, (int, float)):
            self.eval_stack.append(ListValue())
            return
        int_value = int(int_value)
        for item_name, item_value in self.list_defs.get(list_name, {}).items():
            if item_value == int_value:
                self.eval_stack.append(ListValue.single(list_name, item_name, item_value))
                return
        self.eval_stack.append(ListValue())

    def _apply_operator_defensively(self, name: str) -> None:
        """Pop operands for one native-function operator and push its result.

        A no-op when the operands are absent or do not coerce cleanly,
        which real content does reach (an empty-stack "MIN", a None from
        an unassigned variable).

        Args:
            name: The operator symbol.
        """
        arity = NATIVE_FUNCTION_ARITY[name]
        if len(self.eval_stack) < arity:
            return
        args = [self._read_through_pointer(self.eval_stack.pop()) for _ in range(arity)]
        args.reverse()
        try:
            result = apply_native_function(name, args, self.list_defs)
        except (InkPathError, TypeError, ValueError):
            return
        self.eval_stack.append(result)

    def _handle_tag_command(self, content: str) -> bool:
        """Handle one main-stream token belonging to the "#"/.../"/#"
        tag-capture family.

        Ports the BeginTag/EndTag branches of Story.cs: text between "#"
        and "/#" is excluded from visible output (StoryState.currentText's
        "inTag" skip) and collected into current_tags instead.

        Args:
            content: The leaf value.

        Returns:
            True if content was a tag marker or was consumed by an active
            tag capture; False if the caller should try other main-stream
            handling instead.
        """
        if content == BEGIN_TAG:
            self._in_tag = True
            self._tag_buffer = OutputStream()
            return True
        if content == END_TAG:
            self.current_tags.append(self._tag_buffer.get_text())
            self._in_tag = False
            return True
        if self._in_tag:
            if content in CONTROL_COMMAND_MARKERS:
                # A bare "nop" can appear inside an active tag capture,
                # not just the main stream or a str/../str capture. An
                # inline conditional inside a tag (`# image:
                # {cond:a.jpg|b.jpg}`) is not wrapped in ev/../ev by the
                # compiler, so it runs at main-stream depth while _in_tag
                # is True and must be consumed silently rather than
                # captured as literal tag text.
                return True
            if content in (GLUE, NEWLINE):
                self._tag_buffer.push(content)
            else:
                self._tag_buffer.push_text(content)
            return True
        return False

    def _handle_string_content(self, content: str) -> bool:
        """Process one string leaf token: a control-command marker, operator,
        text, or a stop signal.

        Args:
            content: The string leaf value at the current pointer.

        Returns:
            True if this token ends the story (a DONE_COMMANDS marker);
            False otherwise.
        """
        if content in DONE_COMMANDS:
            self.done = True
            return True
        if content == EVAL_START:
            self._eval_run_depth += 1
        elif content == EVAL_END:
            self._eval_run_depth -= 1
        elif self._eval_run_depth > 0 or self._string_capture_stack:
            # A string-capture run (str/.../str) is in principle reachable
            # from outside "ev".."/ev", though compiled output only ever
            # nests it inside one; the _string_capture_stack check ensures
            # a capture in progress is never abandoned.
            self._handle_eval_run_command(content)
        elif content == START_THREAD:
            # A bare "thread" marker is always immediately followed by the
            # Divert it applies to (`<- knot` compiles to "thread" then
            # {"->": knot}). The flag tells _follow_divert to run that one
            # Divert as an isolated sub-walk (_run_thread) instead of
            # jumping the main self.pointer.
            self._pending_thread = True
        elif content == DUPLICATE_TOP:
            # Ports ControlCommand.CommandType.Duplicate: a switch-on-value
            # construct (`{x: - 1: ... - 2: ...}`) pushes the switch value
            # once and re-tests it per branch, so every branch but the last
            # duplicates it rather than consuming the original. As a no-op,
            # the first branch's "==" would consume the shared value,
            # leaving nothing for later branches.
            self._duplicate_top_of_eval_stack()
        elif content == VOID_POP:
            # A switch-on-value construct's trailing bare "pop", outside
            # any "ev".."/ev" bracket, discards the duplicated switch value
            # when no branch matched. This is the main-stream form of the
            # "pop" _handle_eval_run_command handles for a void call; as a
            # silent no-op it would leave a stale value on eval_stack to
            # corrupt the next eval run.
            self._pop_eval_stack()
        elif self._handle_tag_command(content):
            pass
        elif content in CONTROL_COMMAND_MARKERS:
            # A ControlCommand marker with no main-stream behavior of its
            # own (e.g. "nop"). Recognized and consumed silently here
            # rather than falling through to push_text() below, which
            # would leak the marker into visible output as literal text.
            pass
        elif content in (GLUE, NEWLINE):
            self.output.push(content)
        else:
            self.output.push_text(content)
        return False

    def _dispatch_content(self, content: Any, pointer: Pointer, holder: Container) -> bool:
        """Handle one resolved content item, advancing self.pointer as needed.

        Args:
            content: The resolved content at pointer (never None — the
                caller handles that case, since it needs no dispatch at
                all beyond advancing).
            pointer: The current pointer (guaranteed non-None by the
                caller, unlike self.pointer's declared type).
            holder: The container pointer is currently in (== pointer.container).

        Returns:
            True if this content item ends the story (a DONE_COMMANDS
            marker); False otherwise. self.pointer is left at the next
            position to process (which may itself be None, meaning the
            story ran out of content here).
        """
        if content in (POP_TUNNEL, FUNCTION_RETURN):
            # Handled here, not in _handle_string_content: both set
            # self.pointer themselves, like the Divert/ChoicePoint jumps
            # below, so neither may also go through the plain-string
            # branch's unconditional auto-advance, which would skip past
            # the jump target.
            if content == POP_TUNNEL:
                self._pop_tunnel()
            else:
                self._return_from_function()
            return False

        if isinstance(content, str):
            if self._handle_string_content(content):
                return True
            self.pointer = self._advance_pointer(pointer)
            return False

        if isinstance(content, Divert):
            self._follow_divert(content, holder)
            return False

        if isinstance(content, FunctionCall):
            self._call_function(content, holder)
            return False

        if isinstance(content, ChoicePoint):
            self._process_choice_point(content, holder)
        else:
            self._dispatch_literal_content(content, holder)

        self.pointer = self._advance_pointer(pointer)
        return False

    def _dispatch_literal_content(self, content: Any, holder: Container) -> None:
        """Push (or apply) one eval-stack-bound literal/reference token.

        Args:
            content: The resolved content item (never a ChoicePoint,
                Divert, FunctionCall, POP_TUNNEL/FUNCTION_RETURN marker,
                or plain str — all handled by the caller before this is
                reached).
            holder: The container content is directly nested in, needed
                to resolve ReadCountTarget/DivertTargetValue's (possibly
                relative) target paths.
        """
        if isinstance(content, (int, float, bool, ListValue)):
            # A numeric/bool/LIST literal, pushed as-is regardless of
            # _eval_run_depth: the compiled format never emits a bare
            # number or list outside "ev".."/ev", so it can only legally
            # appear inside an eval run.
            self.eval_stack.append(content)
        elif isinstance(content, VariablePointer):
            # A `ref` argument: push the pointer, not the value. ci == -1
            # is the compiler's unresolved placeholder, so bind it to the
            # scope that actually holds the name at the moment of the call.
            self.eval_stack.append(self._resolve_variable_pointer(content))
        elif isinstance(content, VariableReference):
            # A name bound to a `ref` parameter pushes the POINTER, not the
            # value: passing it on to another `ref` parameter must forward
            # the original target. Operators and output dereference it at
            # the point a value is actually needed.
            self.eval_stack.append(self._read_variable(content.name))
        elif isinstance(content, VariableAssignment):
            self._write_variable(content, self._pop_eval_stack())
        elif isinstance(content, ReadCountTarget):
            # A bare `{knot_name}` read-count reference resolves to its
            # visit-count int at push time: {"CNT?": path} is the entire
            # operation, immediately followed by "out", not a marker a
            # later "readc" ControlCommand consumes the way
            # TURNS_SINCE/RANDOM's bare-marker operators are. Resolved
            # against holder because the path can be relative
            # ({"CNT?": ".^"}).
            resolved = self._resolve_target_cached(content, holder, content.target_path)
            self.eval_stack.append(self._visit_count(resolved) if isinstance(resolved, Container) else 0)
        elif isinstance(content, DivertTargetValue):
            # A `-> knot_name` literal used as an expression:
            # TURNS_SINCE(-> knot_name)'s argument, or the value behind a
            # `{"->": "$r", "var": true}` variable-target divert (Ink's
            # empty-bracket choice syntax `* text[]`). Resolved eagerly
            # against holder into a ResolvedDivertTarget wrapping the
            # Container rather than the raw Path, since both consumers
            # want container identity: TURNS_SINCE/ReadCount directly, and
            # a variable-target divert via Pointer.start_of(container).
            # The target path can be relative, so resolution needs the
            # holder context.
            resolved = self._resolve_target_cached(content, holder, content.target_path)
            self.eval_stack.append(ResolvedDivertTarget(container=resolved if isinstance(resolved, Container) else None))
        # else: an unrecognised opaque leaf token is skipped.

    def _step(self) -> bool:
        """Process one content item at the current pointer.

        Returns:
            True if the story has reached a stopping point this step
            (a choice point was reached with choices pending after this
            container, the story ended, or the pointer ran out); False to
            keep stepping.
        """
        if self.pointer is None or self.pointer.container is None:
            self.done = True
            return True

        self.pointer = self._descend_into_containers(self.pointer)
        pointer = self.pointer
        assert pointer.container is not None
        if pointer.index >= len(pointer.container.content):
            # Ports the "ran off the end, walk up to the parent" branch of
            # Story._next_content, reached whenever a jump (a
            # variable-target divert, e.g. `* text[]`) lands on an empty
            # container: a compiler-emitted anonymous return-address
            # marker (`[{"#n": "$r1"}]`) with no content of its own, whose
            # real destination is whatever follows it positionally in its
            # parent. An out-of-range index alone does not mean the story
            # is over — that holds only for the outermost container with
            # no parent left. _advance_pointer draws that distinction,
            # returning None only when there is truly nowhere left to go,
            # including popping an active function call frame.
            self.pointer = self._advance_pointer(pointer)
            return self.pointer is None

        content = pointer.resolve()

        if content is None:
            # A real "null" JSON leaf is a legitimate no-op token, not an
            # ended story — only an out-of-range index, checked above,
            # means that.
            self.pointer = self._advance_pointer(self.pointer)
            return self.pointer is None

        story_ended = self._dispatch_content(content, pointer, pointer.container)
        return story_ended or self.pointer is None or self.pointer.container is None

    def _follow_invisible_default_if_only_choice(self) -> bool:
        """Auto-follow a pending invisible-default choice, if it's the only one.

        Flag 0x8: an invisible-default choice is not presented to the
        player and is auto-followed only when no other choice was
        generated. If even one real choice exists, every invisible default
        this turn is dropped, neither shown nor followed. Unlike
        `choose()`, this does not increment `turn_count`: auto-following
        is not a player turn.

        Returns:
            True if an invisible-default choice was followed (the caller
            should keep stepping instead of treating this as a real stop);
            False otherwise (a real stopping point, or the story is
            already done — nothing to auto-follow).
        """
        if self.done or self.current_choices or not self._invisible_default_choices:
            self._invisible_default_choices = []
            return False

        target = self._invisible_default_choices[0].target
        self._invisible_default_choices = []
        self.previous_pointer = self.pointer
        self.pointer = Pointer.start_of(target)
        self._visit_changed_containers_due_to_divert()
        return True

    def _claim_thread(self) -> _TurnGuard:
        """Refuse a turn that overlaps one already running on this state.

        Detects overlap, not ownership: handing a state between threads
        sequentially (a worker pool, `asyncio.to_thread`) is fine, and
        only a turn entered while another is still running is refused.

        Returns:
            A context manager that releases the state on exit.

        Raises:
            ConcurrentPlaythroughError: Another turn is already running.
        """
        caller = threading.get_ident()
        with self._turn_guard_lock:
            running = self._running_thread
            if running is not None and running != caller:
                raise ConcurrentPlaythroughError(
                    f"a turn is already running on this InkRuntimeState (thread {running}); "
                    f"thread {caller} must use its own state "
                    "(the compiled story root is safe to share)"
                )
            self._running_thread = caller
            self._turn_depth += 1
        return _TurnGuard(self)

    @_one_turn_at_a_time
    def continue_story(self) -> str:
        """Advance the story until the next stopping point.

        A stopping point is DONE/END being reached (self.done) or the
        pointer running off the end of all content. ChoicePoints along the
        way are recorded in current_choices but do not halt continuation,
        a container typically holding several sibling choices in a row.
        Mirrors Story.continue_() in scope, without the
        newline-lookahead/glue-rewind snapshotting the real engine uses,
        which is unnecessary here since each turn's leaf run ends cleanly
        at DONE/END.

        Returns:
            The newly produced visible text for this turn (since the last
            continue_story()/choose() call).
        """
        # Kept so refresh_choices() can replay this turn after an application
        # changes state mid-turn; taken here, before anything runs, since
        # by the end the position is past the choices being re-evaluated.
        self._turn_start = self.to_dict()
        self.current_choices = []
        self._invisible_default_choices = []
        # current_tags is per-turn, not cumulative: inklecate's own
        # transcript shows each tagged turn's "# tags:" line carrying only
        # that turn's tags. Without this reset, _handle_tag_command's
        # append-only current_tags would leave every tag ever encountered
        # active for the rest of the story.
        self.current_tags = []
        start_length = len(self.output.tokens)
        while not self.done:
            if self._step():
                if self._follow_invisible_default_if_only_choice():
                    continue
                break
        # The slice is already a fresh, independent list, and `get_text()`
        # reads only `self.tokens` without touching the glue cache, so it
        # can be assigned to a bare OutputStream directly rather than
        # copied token by token.
        new_tokens = self.output.tokens[start_length:]
        self.last_turn_text = OutputStream.from_tokens(new_tokens).get_text()
        # Keep only this turn's tokens: nothing reads the accumulated
        # prefix, and retaining it would make to_dict() re-serialize the
        # whole history every turn, growing saved state without bound.
        # `new_tokens` is not referenced again, so `self.output` takes
        # ownership of it directly.
        self.output.tokens = new_tokens
        return self.last_turn_text

    @_one_turn_at_a_time
    def refresh_choices(self) -> None:
        """Re-evaluate this turn's choices against state changed mid-turn.

        An application that lets the player act outside the story — an inventory
        panel, a spell menu — can change what the current turn's choices
        should offer after they were evaluated. Replaying the turn from
        its own start re-runs those conditions; nothing is advanced, so
        the turn count, the visible text and the player's position are
        all the same afterwards.

        Does nothing before the first turn has run.
        """
        if self._turn_start is None:
            return
        turn_start = self._turn_start
        text, output = self.last_turn_text, self.output
        # Visit counts key on object identity, so a replay would count
        # this turn's containers a second time and retire any once-only
        # choice the player has not actually taken.
        visits, visit_turns = dict(self.visit_counts), dict(self.visit_turns)

        # Whatever the application changed is the whole point of replaying, so
        # the story's own variables are carried forward rather than rolled
        # back with the position.
        current_globals = dict(self.globals)
        self._restore_from(
            InkRuntimeState.from_dict(
                self.root,
                turn_start,
                self.list_defs,
                self.engine_bindings,
                strict_externals=self.strict_externals,
            )
        )
        self.globals = current_globals
        self.visit_counts, self.visit_turns = visits, visit_turns

        self.continue_story()
        # The replay re-emits this turn's text; the application has already shown
        # it, so the original output is kept and only the choices are new.
        self.last_turn_text, self.output = text, output

    def _restore_from(self, other: InkRuntimeState) -> None:
        """Adopt another state's position and variables, in place.

        Args:
            other: The state to copy from.
        """
        self.__dict__.update(other.__dict__)

    @_one_turn_at_a_time
    def choose(self, index: int) -> None:
        """Select one of the currently offered choices and follow its target.

        Args:
            index: The index into current_choices to select.

        Raises:
            IndexError: If index is out of range for current_choices.
        """
        choice = self.current_choices[index]
        self.previous_pointer = self.pointer
        self.pointer = Pointer.start_of(choice.target)
        self.done = False
        self.turn_count += 1
        self._visit_changed_containers_due_to_divert()
        self.current_choices = []

    def _serialize_pointer(self, pointer: Pointer | None) -> dict[str, Any] | None:
        """Convert a Pointer to a plain, JSON-safe dict.

        Args:
            pointer: The pointer to serialize, or None.

        Returns:
            {"path": <container's absolute path string>, "index": int},
            or None if pointer is None or its container is None (a
            pointer that's run off the end of the story — nothing to
            resume from).
        """
        if pointer is None or pointer.container is None:
            return None
        return {"path": _container_path(pointer.container), "index": pointer.index}

    def _deserialize_pointer(self, data: dict[str, Any] | None) -> Pointer | None:
        """Convert a _serialize_pointer() dict back to a live Pointer.

        Args:
            data: The serialized form, or None.

        Returns:
            A Pointer with container resolved against self.root, or None
            if data is None or its path no longer resolves (the story was
            edited since the save). Degrades rather than raising; recovery
            belongs to a save-compatibility path upstream.
        """
        if data is None:
            return None
        target = resolve_path(self.root, Path.parse(str(data["path"])))
        if not isinstance(target, Container):
            return None
        return Pointer(container=target, index=int(data["index"]))

    def _serialize_value(self, value: Any) -> Any:
        """Convert one globals/temps/eval_stack entry to a JSON-safe form.

        Args:
            value: A bool/int/float/str/ListValue/ResolvedDivertTarget/
                VariablePointer/Void — every type this module's dispatch
                code can leave on eval_stack or store in a variable. A
                VariablePointer occurs while a `ref` parameter is bound.

        Returns:
            int/float/str unchanged; a tagged dict for
            bool/ListValue/ResolvedDivertTarget/Void. bool is checked
            before int, Python's bool being an int subclass, and tagged so
            it round-trips as a bool rather than 0/1. Void is tagged too:
            it must not degrade to None, which would rebuild as a
            printable value.
        """
        if isinstance(value, bool):
            return {"$type": "bool", "value": value}
        if isinstance(value, (int, float, str)):
            return value
        if isinstance(value, Void):
            return {"$type": "void"}
        if isinstance(value, ListValue):
            return {
                "$type": "list",
                "entries": [[list(key), val] for key, val in value.entries],
                "origin_names": list(value.origin_names),
            }
        if isinstance(value, VariablePointer):
            return {
                "$type": "variable_pointer",
                "name": value.name,
                "context_index": value.context_index,
            }
        if isinstance(value, ResolvedDivertTarget):
            return {
                "$type": "divert_target",
                "path": _container_path(value.container) if value.container is not None else None,
            }
        # else: an unexpected value type degrades to None rather than
        # raising, so no value can break a save. No known code path
        # produces one.
        return None

    def _deserialize_value(self, data: Any) -> Any:
        """Convert one _serialize_value() result back to a live value.

        Args:
            data: The serialized form.

        Returns:
            The reconstructed value, matching _serialize_value()'s own
            tagging scheme.
        """
        if not isinstance(data, dict) or "$type" not in data:
            return data
        if data["$type"] == "bool":
            return bool(data["value"])
        if data["$type"] == "void":
            return VOID
        if data["$type"] == "list":
            entries = tuple((tuple(key), val) for key, val in data["entries"])
            return ListValue(entries=entries, origin_names=tuple(data["origin_names"]))
        if data["$type"] == "variable_pointer":
            return VariablePointer(name=data["name"], context_index=data["context_index"])
        if data["$type"] == "divert_target":
            return self._deserialize_divert_target(data)
        return None

    def _deserialize_divert_target(self, data: dict[str, Any]) -> ResolvedDivertTarget:
        """Convert a {"$type": "divert_target", "path": ...} dict back to a
        ResolvedDivertTarget.

        Args:
            data: The serialized divert-target dict.

        Returns:
            The reconstructed ResolvedDivertTarget, with container=None if
            the path is missing or no longer resolves against self.root —
            a save taken against a since-edited story degrades rather than
            raising.
        """
        path = data["path"]
        if path is None:
            return ResolvedDivertTarget(container=None)
        target = resolve_path(self.root, Path.parse(str(path)))
        return ResolvedDivertTarget(container=target if isinstance(target, Container) else None)

    def _id_keyed_dict_to_path_keyed(self, id_keyed: dict[int, int], by_id: dict[int, Container]) -> dict[str, int]:
        """Convert an id(Container)-keyed dict (visit_counts/visit_turns'
        own storage shape) to a path-keyed dict, for serialization.

        Args:
            id_keyed: {id(container): int_value}.
            by_id: `self._visited_containers`. Passed in rather than read
                from self, so this stays a pure mapping function.

        Returns:
            {path_string: int_value}, one entry per id_keyed key whose
            container is still reachable from self.root. An id whose
            container no longer exists is dropped silently; this cannot
            happen within one InkRuntimeState's lifetime, containers never
            being removed from the tree after loading.
        """
        result: dict[str, int] = {}
        for container_id, value in id_keyed.items():
            container = by_id.get(container_id)
            if container is not None:
                result[_container_path(container)] = value
        return result

    def _path_keyed_dict_to_id_keyed(self, path_keyed: dict[str, int]) -> dict[int, int]:
        """Convert a path-keyed dict (to_dict()'s serialized form) back to
        the id(Container)-keyed shape visit_counts/visit_turns actually
        use at runtime.

        Args:
            path_keyed: {path_string: int_value}.

        Returns:
            {id(container): int_value}, one entry per path that still
            resolves against self.root. A path removed by a story edit is
            dropped silently; handling that case holistically belongs to a
            save-compatibility path upstream.
        """
        result: dict[int, int] = {}
        for path_str, value in path_keyed.items():
            target = resolve_path(self.root, Path.parse(path_str))
            if isinstance(target, Container):
                result[id(target)] = value
                self._visited_containers[id(target)] = target
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize this state to a plain, JSON-safe dict.

        Every Container/Pointer reference becomes a path string, so the
        result round-trips through `json.dumps`/`json.loads` with no
        custom encoder.

        Transient mid-dispatch flags (_eval_run_depth, _pending_thread,
        _in_tag, _tag_buffer, _string_capture_stack) are included: a
        stopping point can be captured mid-eval-run, and resuming without
        them routes the pending marker down the wrong branch.

        Returns:
            The serialized state.
        """
        by_id = self._visited_containers
        return {
            "pointer": self._serialize_pointer(self.pointer),
            "previous_pointer": self._serialize_pointer(self.previous_pointer),
            "output_tokens": list(self.output.tokens),
            "current_choices": [
                {"text": choice.text, "target_path": _container_path(choice.target), "tags": list(choice.tags)} for choice in self.current_choices
            ],
            "visit_counts": self._id_keyed_dict_to_path_keyed(self.visit_counts, by_id),
            "visit_turns": self._id_keyed_dict_to_path_keyed(self.visit_turns, by_id),
            "current_tags": list(self.current_tags),
            "done": self.done,
            "globals": {name: self._serialize_value(value) for name, value in self.globals.items()},
            "temps": {name: self._serialize_value(value) for name, value in self.temps.items()},
            "eval_stack": [self._serialize_value(value) for value in self.eval_stack],
            "tunnel_stack": [self._serialize_pointer(pointer) for pointer in self.tunnel_stack],
            "call_stack": [
                {
                    "return_pointer": self._serialize_pointer(frame.return_pointer),
                    "temps": {name: self._serialize_value(value) for name, value in frame.temps.items()},
                }
                for frame in self.call_stack
            ],
            "story_seed": self.story_seed,
            "tag_buffer_tokens": list(self._tag_buffer.tokens),
            "string_capture_stack": [list(capture.tokens) for capture in self._string_capture_stack],
            "string_capture_eval_depth": list(self._string_capture_eval_depth),
            **{key: getattr(self, attribute) for key, attribute, _coerce, _default in _SCALAR_STATE_FIELDS},
        }

    @classmethod
    def from_dict(
        cls,
        root: Container,
        data: dict[str, Any],
        list_defs: dict[str, dict[str, int]] | None = None,
        engine_bindings: dict[str, Callable[..., Any]] | None = None,
        *,
        strict_externals: bool = False,
    ) -> InkRuntimeState:
        """Rebuild an InkRuntimeState from a to_dict() result.

        Args:
            root: The story's root Container (from load_story_root()),
                which must be the same compiled story the state was
                serialized against. A path that no longer resolves is
                dropped silently rather than raising.
            data: A to_dict() result.
            list_defs: The story's LIST definitions, as for the
                constructor.
            engine_bindings: As for the constructor. Bindings are not part
                of saved state; the caller re-derives them on every load.
            strict_externals: As for the constructor, and for the same
                reason not part of saved state.

        Returns:
            A new InkRuntimeState with every field from data restored.
        """
        state = cls(root, list_defs, engine_bindings, strict_externals=strict_externals)
        state.pointer = state._deserialize_pointer(data.get("pointer"))
        state.previous_pointer = state._deserialize_pointer(data.get("previous_pointer"))
        state.output = OutputStream.from_tokens(list(data.get("output_tokens", [])))
        state.current_choices = []
        for choice_data in data.get("current_choices", []):
            target = resolve_path(state.root, Path.parse(str(choice_data["target_path"])))
            if isinstance(target, Container):
                # A save written before choices carried tags has no "tags"
                # key; it restores as an untagged choice rather than failing.
                state.current_choices.append(Choice(text=str(choice_data["text"]), target=target, tags=list(choice_data.get("tags", []))))
        state.visit_counts = state._path_keyed_dict_to_id_keyed(data.get("visit_counts", {}))
        state.visit_turns = state._path_keyed_dict_to_id_keyed(data.get("visit_turns", {}))
        state.current_tags = list(data.get("current_tags", []))
        state.done = bool(data.get("done", False))
        state.globals = {name: state._deserialize_value(value) for name, value in data.get("globals", {}).items()}
        state.temps = {name: state._deserialize_value(value) for name, value in data.get("temps", {}).items()}
        state.eval_stack = [state._deserialize_value(value) for value in data.get("eval_stack", [])]
        state.tunnel_stack = [pointer for pointer in (state._deserialize_pointer(p) for p in data.get("tunnel_stack", [])) if pointer is not None]
        state.call_stack = []
        for frame_data in data.get("call_stack", []):
            return_pointer = state._deserialize_pointer(frame_data.get("return_pointer"))
            if return_pointer is None:
                # A call frame with no valid return address is unusable;
                # dropping it degrades to "this call never returns".
                # call_stack is the kind of state a story edit invalidates,
                # and partial repair belongs to a save-compatibility path
                # upstream.
                continue
            frame_temps = {name: state._deserialize_value(value) for name, value in frame_data.get("temps", {}).items()}
            state.call_stack.append(CallFrame(return_pointer=return_pointer, temps=frame_temps))
        for key, attribute, coerce, default in _SCALAR_STATE_FIELDS:
            setattr(state, attribute, coerce(data.get(key, default)))
        # Not in the table: its default is the seed this instance already
        # generated, not a constant.
        state.story_seed = int(data.get("story_seed", state.story_seed))
        state._tag_buffer = OutputStream.from_tokens(list(data.get("tag_buffer_tokens", [])))
        state._string_capture_stack = []
        for tokens in data.get("string_capture_stack", []):
            state._string_capture_stack.append(OutputStream.from_tokens(list(tokens)))
        # Falls back to the restored _eval_run_depth, not 0, for a save
        # blob lacking this field: an all-zero baseline would make every
        # capture believe it started at eval-run depth 0. A save with no
        # active capture has an empty list, so depth 0 is correct there.
        fallback_depths = [state._eval_run_depth] * len(state._string_capture_stack)
        state._string_capture_eval_depth = [int(depth) for depth in data.get("string_capture_eval_depth", fallback_depths)]
        return state
