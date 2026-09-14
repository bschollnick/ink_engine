"""Schedule rules: where a character is, as data evaluated by one function.

A character's schedule is a tuple of `ScheduleRule`s -- "if this condition
holds, they are at this place" -- evaluated in declared order, first match
wins. A rule's condition is a `Condition` tree built from a closed
vocabulary (`ConditionKind`): a story flag, a time-of-day range, a named
story rule or value, a read of another plugin's state, a question another
plugin publishes, and AND/OR/NOT. It is plain data, never a code string.

This module owns the vocabulary and the evaluator. `character_occupancy`
owns the store the resolved answers are written into; it imports this
module, never the other way round, so a story may evaluate schedules with
no occupancy store at all.

Per-session isolation: every function here is pure in its explicit
arguments -- no instance attributes, no module-level state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Named, closed registries a caller supplies to evaluate_condition()/
# resolve_schedule() for STORY_RULE/STORY_VALUE nodes — plain functions of
# the raw clock value (in whatever unit the calling story uses), never an
# arbitrary string the engine evaluates. The registry is the caller's, so
# it is never a fixed set here. Named "story_*" because every name in
# these nodes resolves to whatever the CALLING STORY defines; the engine
# has no opinion about the registry's contents.
StoryRuleRegistry = dict[str, Callable[[int], bool]]
StoryValueRegistry = dict[str, Callable[[int], "int | str"]]

# Which plugins a QUERY condition may ask, and what each can be asked:
# {state_key: {query_name: callable}}. The caller builds this from the
# plugins it activated, so a schedule can only ask a question some active
# plugin actually publishes.
QueryRegistry = dict[str, dict[str, Callable[..., Any]]]

# Ordering operators only make sense for numbers (schedule data never
# needs alphabetical string ordering); equality works for a number or a
# string (e.g. comparing a name-returning function's result against a
# specific name).
_ORDERING_OPERATORS: dict[str, Callable[[int, int], bool]] = {
    ">": lambda actual, target: actual > target,
    ">=": lambda actual, target: actual >= target,
    "<": lambda actual, target: actual < target,
    "<=": lambda actual, target: actual <= target,
}
_EQUALITY_OPERATORS: dict[str, Callable[[int | str, int | str], bool]] = {
    "==": lambda actual, target: actual == target,
    "!=": lambda actual, target: actual != target,
}
# Membership, for reading a plugin's LIST-shaped state. Only meaningful
# for ENGINE_STATE, where the value read may be a collection; STORY_VALUE
# always yields a scalar. A non-collection answers False rather than
# raising, matching this module's "a fact that has not happened answers
# no" contract.
_MEMBERSHIP_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "contains": lambda actual, target: bool(actual) and target in actual,
    "excludes": lambda actual, target: not actual or target not in actual,
}
_COMPARISON_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {**_ORDERING_OPERATORS, **_EQUALITY_OPERATORS, **_MEMBERSHIP_OPERATORS}


class ConditionKind(Enum):
    """The closed vocabulary a ScheduleRule's condition tree is built from
    — plain, JSON-safe data, never a code string. A flag check
    (story-flag-gated presence), a time-of-day range check
    (shop-hours/day-night splits), a named story rule check (a
    story-supplied boolean function of the clock), a named story value
    comparison (a story-supplied int-valued function of the clock), a read
    of another plugin's state (ENGINE_STATE — see
    `Condition.engine_state()`), and AND/OR/NOT combinators for
    multi-condition priority chains."""

    FLAG = "flag"
    MINUTE_IN_RANGE = "minute_in_range"
    STORY_RULE = "story_rule"
    STORY_VALUE = "story_value"
    ENGINE_STATE = "engine_state"
    QUERY = "query"
    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass(frozen=True)
class Condition:
    """One node in a ScheduleRule's condition tree.

    Args:
        kind: Which closed condition kind this node is.
        payload: The kind-specific data, as a plain JSON-safe dict — never
            a code string. Shape depends on `kind`; build via the
            classmethods below rather than constructing `payload`
            directly. One shared dict field keeps this dataclass's shape
            constant however many condition kinds exist, as
            `scheduling.Effect` does.
        clauses: The child Conditions being combined, for AND/OR/NOT
            nodes only (exactly one child for NOT).
    """

    kind: ConditionKind
    payload: dict[str, Any] = field(default_factory=dict)
    clauses: tuple["Condition", ...] = ()

    @classmethod
    def flag_is_set(cls, flag: str) -> "Condition":
        """Build a FLAG condition.

        Args:
            flag: The session-flag name to check.

        Returns:
            A Condition testing whether `flag` is set.
        """
        return cls(kind=ConditionKind.FLAG, payload={"flag": flag})

    @classmethod
    def minute_in_range(cls, minute_low: int, minute_high: int) -> "Condition":
        """Build a MINUTE_IN_RANGE condition.

        Args:
            minute_low: The inclusive lower bound, in minutes-of-day
                (0-1439) — build with `scheduling.py`'s named hour
                constants (e.g. `scheduling.EIGHT_AM`) rather than a bare
                integer.
            minute_high: The exclusive upper bound, in minutes-of-day —
                built the same way (e.g. `scheduling.SIX_PM`).

        Returns:
            A Condition testing whether the current time of day falls in
            `[minute_low, minute_high)`.
        """
        return cls(kind=ConditionKind.MINUTE_IN_RANGE, payload={"minute_low": minute_low, "minute_high": minute_high})

    @classmethod
    def query(cls, state_key: str, query: str, *args: Any, operator: str = "==", value: Any = True, missing: Any = False) -> "Condition":
        """Build a QUERY condition — ask a plugin a question it publishes.

        Preferred over `engine_state()`: naming a question rather than a
        storage path keeps the rule working when the owning plugin
        changes how it stores things. A plugin that has not published the
        question yet should publish it; a raw path is the last resort.

        Args:
            state_key: The plugin to ask, as it publishes its `STATE_KEY`.
            query: The question's name, from that plugin's own `queries`.
            *args: The question's own arguments.
            operator: How to compare the answer, from the same closed set
                the other kinds use.
            value: What to compare against.
            missing: What an answer of None is worth.

        Returns:
            The QUERY Condition.

        Raises:
            ValueError: If `operator` is not a supported comparison.
        """
        if operator not in _COMPARISON_OPERATORS:
            raise ValueError(f"unsupported operator {operator!r}; expected one of {sorted(_COMPARISON_OPERATORS)}")
        return cls(
            kind=ConditionKind.QUERY,
            payload={"state_key": state_key, "query": query, "args": tuple(args), "operator": operator, "value": value, "missing": missing},
        )

    @classmethod
    def story_rule(cls, rule_name: str) -> "Condition":
        """Build a STORY_RULE condition.

        `rule_name` resolves to whatever the CALLING STORY defines; the
        engine has no opinion about the registry's contents.

        Args:
            rule_name: A story-supplied boolean function of the raw
                clock, in the `StoryRuleRegistry` passed to
                `evaluate_condition()`/`resolve_schedule()` (e.g.
                "is_school_open").

        Returns:
            A Condition true exactly when that function returns True for
            the current raw clock value.
        """
        return cls(kind=ConditionKind.STORY_RULE, payload={"rule_name": rule_name})

    @classmethod
    def story_value(cls, value_name: str, operator: str, value: int | str) -> "Condition":
        """Build a STORY_VALUE condition.

        Args:
            value_name: A story-supplied int-or-str-valued function of
                the raw clock, in the `StoryValueRegistry` passed to
                `evaluate_condition()`/`resolve_schedule()` (e.g.
                "hour_of_day").
            operator: One of ">", ">=", "<", "<=" (numbers only) or "==",
                "!=" (numbers or strings).
            value: What to compare against — an int for an ordering
                operator.

        Returns:
            A Condition true exactly when
            `registry[value_name](clock) <operator> value` holds.

        Raises:
            ValueError: If an ordering operator is given a string `value`.
        """
        if isinstance(value, str) and operator in _ORDERING_OPERATORS:
            raise ValueError(f"story_value(): ordering operator {operator!r} is not valid for a string value ({value!r})")
        return cls(kind=ConditionKind.STORY_VALUE, payload={"value_name": value_name, "operator": operator, "value": value})

    @classmethod
    def engine_state(cls, state_key: str, path: tuple[str, ...], operator: str = "==", value: Any = True, missing: Any = False) -> "Condition":
        """Build an ENGINE_STATE condition — a read of another plugin's state.

        Every other kind answers from something the caller hands in; this
        one reads state a different plugin already holds. Naming a slot
        and a path within it keeps the vocabulary generic: no plugin needs
        a kind of its own to become readable.

        Args:
            state_key: The state slot to read, as its owning API declares
                it (e.g. `"characters"`).
            path: The keys to walk within that slot, outermost first —
                e.g. `("records", "npc_id", "attributes",
                "met_the_stranger")`.
            missing: What an unresolved path is worth. A fact that has not
                happened yet is usually indistinguishable from its zero
                value — `charm_level == 0` means "uncharmed", which must
                hold for a character nobody has ever charmed. Defaults to
                False, which compares equal to 0 and unequal to any true
                value, right for both the boolean and the counter case.
                Pass something else where absence genuinely differs from a
                stored value.
            operator: How to compare the value found, from the same
                closed set STORY_VALUE uses. Defaults to `"=="`.
            value: What to compare against. Defaults to True, the common
                case of testing a boolean fact.

        Returns:
            The ENGINE_STATE Condition.

        Raises:
            ValueError: If `operator` is not one of the supported
                comparison operators.
        """
        if operator not in _COMPARISON_OPERATORS:
            raise ValueError(f"unsupported operator {operator!r}; expected one of {sorted(_COMPARISON_OPERATORS)}")
        return cls(
            kind=ConditionKind.ENGINE_STATE,
            payload={"state_key": state_key, "path": tuple(path), "operator": operator, "value": value, "missing": missing},
        )

    @classmethod
    def all_of(cls, *clauses: "Condition") -> "Condition":
        """Build an AND condition.

        Args:
            *clauses: The Conditions that must all be true.

        Returns:
            A Condition true only when every clause is true.
        """
        return cls(kind=ConditionKind.AND, clauses=clauses)

    @classmethod
    def any_of(cls, *clauses: "Condition") -> "Condition":
        """Build an OR condition.

        Args:
            *clauses: The Conditions where at least one must be true.

        Returns:
            A Condition true when any clause is true.
        """
        return cls(kind=ConditionKind.OR, clauses=clauses)

    @classmethod
    def negate(cls, clause: "Condition") -> "Condition":
        """Build a NOT condition.

        Args:
            clause: The Condition to invert.

        Returns:
            A Condition true exactly when `clause` is false.
        """
        return cls(kind=ConditionKind.NOT, clauses=(clause,))


@dataclass(frozen=True)
class EvalContext:
    """The session state a Condition tree is evaluated against — bundled
    so `evaluate_condition()` takes one context argument rather than one
    parameter per kind of state a Condition might need.

    Args:
        flags: The set of currently-set session-flag names.
        minute_of_day: The current minute within a 1440-minute day
            (`(clock % 288) * 5`) — used by MINUTE_IN_RANGE only.
        clock: The raw, un-reduced clock value as passed to
            `resolve_schedule()` — used by STORY_RULE/STORY_VALUE only,
            whose caller-supplied functions expect their own unit, not
            `minute_of_day`. Defaults to 0 for a tree with no such nodes.
        story_rules: The registry of named boolean functions of `clock`
            for STORY_RULE nodes. Defaults to an empty registry.
        story_values: The registry of named int-valued functions of
            `clock` for STORY_VALUE nodes. Defaults to an empty registry.
        engine_state: Other plugins' serialized state, keyed by state
            slot, for ENGINE_STATE nodes. Read-only: a schedule answers
            questions, it never writes. Defaults to empty.
        queries: What each plugin can be asked, for QUERY nodes —
            `{state_key: {query_name: callable}}`, built from the active
            plugins' own `Plugin.queries`. Defaults to empty, which makes
            every QUERY condition a loud misconfiguration rather than a
            silent false.
    """

    flags: frozenset[str]
    minute_of_day: int
    clock: int = 0
    story_rules: StoryRuleRegistry = field(default_factory=dict)
    story_values: StoryValueRegistry = field(default_factory=dict)
    engine_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    queries: QueryRegistry = field(default_factory=dict)


def engine_query_registry() -> QueryRegistry:
    """Return what the engine's own shipped plugins can be asked.

    A `QUERY` condition names a plugin and a question; this is where the
    questions the engine itself publishes are found. A host with extra
    plugins passes its own registry instead, built the same way from each
    active plugin's `Plugin.queries`.

    Built on demand rather than at import so this module keeps importing
    nothing from the plugins that depend on it.

    Returns:
        `{state_key: {query_name: callable}}` for every shipped plugin
        that publishes a query.
    """
    # Deferred to avoid an import cycle: these modules import this one.
    from ink_engine.engine_plugins import (  # pylint: disable=import-outside-toplevel
        character_occupancy,
        characters,
        location_graph,
    )

    return {
        character_occupancy.STATE_KEY: dict(character_occupancy.PLUGIN.queries),
        characters.STATE_KEY: dict(characters.PLUGIN.queries),
        location_graph.STATE_KEY: dict(location_graph.PLUGIN.queries),
    }


def _run_query(context: "EvalContext", state_key: str, query: str, args: tuple[Any, ...]) -> Any:
    """Ask one plugin a question it publishes.

    Raises:
        UnknownQueryError: No active plugin owns that slot, or the plugin
            publishes no such question.
    """
    published = context.queries.get(state_key)
    if published is None:
        raise UnknownQueryError(f"no active plugin owns state slot {state_key!r} (asked for query {query!r})")
    answer = published.get(query)
    if answer is None:
        raise UnknownQueryError(f"plugin {state_key!r} publishes no query {query!r}; it offers {sorted(published)}")
    return answer(context.engine_state.get(state_key, {}), *args)


def _read_engine_state(engine_state: dict[str, dict[str, Any]], state_key: str, path: tuple[str, ...]) -> Any:
    """Walk `path` into one state slot, or return None if it does not resolve.

    A missing key is not an error; a schedule routinely asks about facts
    that have not happened yet.

    Args:
        engine_state: Other plugins' serialized state, keyed by slot.
        state_key: The slot to read.
        path: The keys to walk, outermost first.

    Returns:
        The value found, or None if any step is missing or a non-mapping
        is hit before the path is exhausted.
    """
    current: Any = engine_state.get(state_key)
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _evaluate_combinator(condition: Condition, context: EvalContext) -> bool:
    """Evaluate an AND/OR/NOT combinator node's child clauses.

    Args:
        condition: The AND/OR/NOT condition to evaluate.
        context: The real session state to evaluate its clauses against.

    Returns:
        Whether `condition` holds.
    """
    if condition.kind is ConditionKind.AND:
        return all(_evaluate(clause, context) for clause in condition.clauses)
    if condition.kind is ConditionKind.OR:
        return any(_evaluate(clause, context) for clause in condition.clauses)
    return not _evaluate(condition.clauses[0], context)


def _evaluate(condition: Condition, context: EvalContext) -> bool:
    """Evaluate one Condition node against a bundled evaluation context.

    Args:
        condition: The condition to evaluate.
        context: The real session state to evaluate it against.

    Returns:
        Whether `condition` holds.
    """
    if condition.kind is ConditionKind.FLAG:
        return condition.payload["flag"] in context.flags
    if condition.kind is ConditionKind.MINUTE_IN_RANGE:
        return condition.payload["minute_low"] <= context.minute_of_day < condition.payload["minute_high"]
    if condition.kind is ConditionKind.QUERY:
        actual = _run_query(context, condition.payload["state_key"], condition.payload["query"], condition.payload["args"])
        if actual is None:
            actual = condition.payload.get("missing", False)
        return _COMPARISON_OPERATORS[condition.payload["operator"]](actual, condition.payload["value"])
    if condition.kind is ConditionKind.ENGINE_STATE:
        actual = _read_engine_state(context.engine_state, condition.payload["state_key"], condition.payload["path"])
        if actual is None:
            actual = condition.payload.get("missing", False)
        return _COMPARISON_OPERATORS[condition.payload["operator"]](actual, condition.payload["value"])
    if condition.kind is ConditionKind.STORY_RULE:
        return context.story_rules[condition.payload["rule_name"]](context.clock)
    if condition.kind is ConditionKind.STORY_VALUE:
        value_function = context.story_values[condition.payload["value_name"]]
        return _COMPARISON_OPERATORS[condition.payload["operator"]](value_function(context.clock), condition.payload["value"])
    return _evaluate_combinator(condition, context)


def evaluate_condition(condition: Condition, context: EvalContext) -> bool:
    """Evaluate one Condition node against real session state.

    Args:
        condition: The condition to evaluate.
        context: The session state to evaluate it against — flags, the
            clock (both raw and reduced to minute-of-day), and the
            STORY_RULE/STORY_VALUE registries. Build one directly; its
            registries default to `{}` for a tree with no such nodes.

    Returns:
        Whether `condition` holds.
    """
    return _evaluate(condition, context)


@dataclass(frozen=True)
class ScheduleRule:
    """One branch of a character's schedule — "if this condition holds,
    they're at this place" — evaluated in declared order, first match
    wins, matching a `_place_now()` function's if/elif-chain shape.

    Args:
        condition: The Condition gating this branch. None means "always
            true", for a schedule's trailing fallback branch.
        location_id: The location to report if `condition` holds, or None
            for "not present anywhere" (source's `return 0` convention for
            an absent character).
    """

    condition: Condition | None
    location_id: str | None


def resolve_schedule(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rules: tuple[ScheduleRule, ...],
    flags: frozenset[str],
    clock: int,
    story_rules: StoryRuleRegistry | None = None,
    story_values: StoryValueRegistry | None = None,
    engine_state: dict[str, Any] | None = None,
    queries: QueryRegistry | None = None,
) -> str | None:
    """Resolve a character's current location from their schedule.

    Rules are evaluated top to bottom, first match wins.

    Args:
        rules: The character's schedule, in priority order. The caller
            supplies a trailing unconditional fallback rule
            (`condition=None`) if one is wanted; a schedule with no
            matching rule and no fallback resolves to None, source's
            "not trackable" convention.
        flags: The set of currently-set session-flag names.
        clock: The current absolute tick count, reduced here to
            minute-of-day via `(clock % 288) * 5` for MINUTE_IN_RANGE
            nodes. STORY_RULE/STORY_VALUE registry functions receive the
            raw value unchanged, in the story's own clock unit.
        story_rules: The registry of named boolean functions of `clock`
            for any STORY_RULE node in `rules`. Defaults to empty.
        story_values: The registry of named int-valued functions of
            `clock` for any STORY_VALUE node in `rules`. Defaults to
            empty.
        engine_state: Other plugins' serialized state, keyed by state
            slot, for any ENGINE_STATE node in `rules`. Defaults to empty.
        queries: What each plugin can be asked, for any QUERY node in
            `rules` -- `{state_key: {query_name: callable}}`, as
            `engine_query_registry()` builds. Defaults to empty, which
            makes a QUERY condition raise rather than answer False.

    Returns:
        The resolved location id, or None if the character isn't present
        anywhere right now.
    """
    context = EvalContext(
        flags=flags,
        minute_of_day=(clock % 288) * 5,
        clock=clock,
        story_rules=story_rules or {},
        story_values=story_values or {},
        engine_state=engine_state or {},
        queries=queries if queries is not None else engine_query_registry(),
    )
    for rule in rules:
        if rule.condition is None or _evaluate(rule.condition, context):
            return rule.location_id
    return None


class UnknownQueryError(ValueError):
    """A condition asked a question no active plugin publishes."""
