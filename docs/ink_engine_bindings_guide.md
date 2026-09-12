# ink_engine: EXTERNAL Bindings and Host Integration

How a story reaches Python in this engine, and the failure modes that are
silent if you don't know to check for them. Companion to
[`ink_pitfalls_and_debugging.md`](ink_pitfalls_and_debugging.md) (the language's own gotchas) — this
document is specific to `ink_engine`'s own runtime and plugin machinery.

**Verification, and how to read the labels below.** `ink_engine` 0.1.0,
`inklecate` v1.2.1 (compiled format `inkVersion` 21 — the binary itself has
no `--version` flag; see [`inkles-ink-standard`](inkles-ink-standard/)).
Every claim about `ink_engine`'s own Python API (the `StatefulPlugin`/
`Plugin`/`discover_plugins()`/`resolve_bindings()` machinery, §3-4, and the
dispatch mechanism's own internals, §1) was verified directly against
`ink_engine/plugin_base.py`, `ink_engine/engine.py`, `ink_engine/binding.py`,
and `ink_engine/discovery.py` as they exist today — inklecate has no concept of Python bindings, so there
is nothing to cross-check those claims against. Every claim about real Ink
language/runtime behavior — anywhere `ink_engine` deliberately reproduces
what Ink itself does, including where that behavior is a genuine gotcha —
is labeled **[Ink]** and was independently compiled and run through the real
`inklecate` binary, not just read out of `engine.py`'s own source or
comments. A label of **[Ink]** means "this is
upstream Ink behavior that `ink_engine` matches on purpose" — never read it
as `ink_engine` diverging from or failing to match the real compiler.

---

## 1. The dispatch mechanism

`EXTERNAL name(...)` in Ink source compiles to an ordinary function-call
token with an `is_external` flag — nothing else distinguishes it at runtime.
When `InkRuntimeState` reaches one, it checks
`self.engine_bindings.get(target_name)`:

- **A real Python callable is registered** → it is called directly with the
  popped argument values (positional, in original order), and its return
  value is pushed onto the eval stack. The callable receives *only* those
  arguments — never `self`, never any implicit shared state.
- **No callable is registered for that name** → the call falls through to
  the story's own in-Ink fallback function (`=== function name(...) ===`),
  exactly like an ordinary Ink function call.
- **No callable is registered, and no fallback exists either** → raises
  `UnboundExternalError` (see §2), matching real Ink's own runtime error
  for this exact case rather than silently degrading.

`engine_bindings` is a plain `dict[str, Callable]` passed to
`InkRuntimeState(root, list_defs, engine_bindings=...)` (or `from_dict(...,
engine_bindings=...)`). **This engine has no concept of trust, enable/
disable, or per-story configuration of its own** — deciding which bindings
a given session should receive at all, and building that dict, is entirely
the host application's job, via `discover_plugins()`/`resolve_bindings()`
(§3) or by hand. An untrusted/unconfigured session simply gets an empty (or
partial) `engine_bindings` dict, and every EXTERNAL call for a name not in
it falls through to the Ink fallback — there is no other gate inside the
engine itself.

## 2. Failure modes that are silent

**[Ink] An `EXTERNAL` with no same-named Ink fallback compiles fine — it
fails at runtime, not compile time.** Confirmed directly: `inklecate`
compiles a story declaring `EXTERNAL greet(name)` with zero Ink-side
fallback with exit code 0. Playing that story (`inklecate -p`) is what
fails, with `ERROR: Missing function binding for external: 'greet' , and no
fallback ink function found.` `ink_engine` matches this exactly —
`_call_function` raises `UnboundExternalError` (not a silent `0`) the
moment such a call is reached with no bound Python callable and no
resolvable fallback, regardless of `strict_externals` (see the TBD plan in
`claude_docs/plans/feature_enhancements.md`, which covers a *different*
case — see below).

**The real silent hazard is the other case: a binding *declared* in Ink,
with a working fallback, that is simply never wired into `engine_bindings`
at runtime.** The fallback runs instead — typically returning
`""`/`false`/`0` depending on how the story author wrote it — and
**nothing raises**. Presence checks then read as "no" across the board, and
the affected content simply never appears. A binding that is declared, has
a working stub, and is never wired looks identical to a binding that works
and legitimately answers no. This case has no inklecate equivalent to test
against — inklecate has no concept of a host-side Python binding at all;
it's purely a fact about `ink_engine`'s own host-integration contract.

Use `find_unbound_externals(root)` (in `ink_engine.engine`) to catch the
first paragraph's failure mode at validation time, ahead of ever running the
story — it walks the compiled tree and reports every `EXTERNAL` call site
with no resolvable Ink fallback at all. It cannot detect the second
paragraph's case — "declared, has a fallback, but never wired to a real
binding" — since that is a fact about the *host's own* configuration, not
about the story. Test for that by giving the fallback an impossible
sentinel value (see §4).

**`resolve_bindings()` raises `KeyError` on a genuinely missing plugin
name**, rather than silently producing an incomplete bindings dict — if
`active_names` names a plugin that `discover_plugins()` never actually
found, that is a real host-side misconfiguration and it is reported loudly.
This is distinct from the paragraph above: an EXTERNAL name simply absent
from *any* discovered plugin's `bindings` still falls through to the Ink
stub silently, since that is ordinary, expected behavior (an opt-in
capability the story doesn't use), not an error — only a name explicitly
listed in `active_names` but missing from `plugins` is a misconfiguration.

**An EXTERNAL cannot hold state across calls on its own** — a bound
callable is a stateless function of its arguments (see §1). A plugin that
needs to remember something between calls does so via the `Plugin.bind`/
`state_key`/`init_state` mechanism (§3), which gives it a private slice of
the session's own `engine_state` dict to close over — not via a module-level
Python variable, which would leak between sessions.

**[Ink] An EXTERNAL parameter may not share a name with a global `VAR`** —
confirmed directly: `inklecate` rejects this with the exact error `argument
'x': name has already been used for a var on line N of <file>`. Grep for
`^VAR <name>` across every `.ink` file being compiled together before
renaming a binding's own parameter; a single-file compile will not surface
a collision that only exists once files are combined via `INCLUDE`.

**An EXTERNAL cannot supply a non-zero/non-empty initial value the way `VAR
x = "default"` can** — its Ink-side fallback always starts from whatever the
fallback function itself returns on a cold call, and the real binding (once
wired) starts from whatever the host's own `init_state()` produces. If a
story needs a non-default starting value, set it explicitly at the actual
point where it first matters, not by assuming the binding's own "zero
value" happens to be right.

**[Ink] A function that falls off its end returns Void, not `0`.** Confirmed
directly: comparing such a return value (`falls_off() == 0`) raises
`RUNTIME ERROR: ... Attempting to perform == on a void value. Did you
forget to 'return' a value from a function you called here?` — real Ink
does not coerce Void to a comparable zero. This applies to a story's own
Ink functions and matters for a binding's return value too: a host binding
should return a real value on every path, never rely on "falling through"
the way an Ink function's own fallback can.

## 3. Writing a plugin

A plugin is a unit of EXTERNAL bindings, optionally owning one named slice
of the running session's state. Most are written by subclassing
`StatefulPlugin`; the flat `Plugin` dataclass underneath it is still the
contract everything is resolved through, and is described in §3.4 for the
stateless case and for anyone reading the machinery itself.

### 3.1 `StatefulPlugin`: the instance is the definition, the slot is the state

```python
from ink_engine.plugin_base import StatefulPlugin, external, query


class CostSlot(TypedDict):
    costs: dict[str, dict[str, Any]]


class CostTable(StatefulPlugin[CostSlot]):
    name = "cost_table"
    display_name = "Cost table"
    state_key = "cost_table"
    slot_type = CostSlot
    fields = {"costs": dict}

    @query
    @external
    def cost_of(self, slot: CostSlot, cost_key: str, default: float = 0) -> float:
        """Return what an action costs."""
        entry = slot.get("costs", {}).get(cost_key) or self._declared.get(cost_key)
        return entry.get("amount", default) if entry else default

    @external
    def set_cost(self, slot: CostSlot, cost_key: str, resource: str, amount: float) -> None:
        """Declare or change one cost during play."""
        slot.setdefault("costs", {})[cost_key] = {"resource": resource, "amount": amount}


COST_TABLE = CostTable()
PLUGIN = COST_TABLE.plugin()
```

That is the whole shape. Four things about it are load-bearing:

**The instance is a module-level definition, not per-session data.** One
`CostTable()` object serves every concurrent session in the process. The
per-session data is the slot, which is a plain JSON-safe dict living in
`engine_state`, and **every method takes it as its first argument after
`self`**. A plugin that stores session data on `self` is broken in a way
tests with one session will not catch.

**`@external` publishes a method as an Ink binding under its own name.**
The method name *is* the Ink name; there is no second naming layer to keep
in sync. A return annotation is mandatory, and `-> None` is meaningful:
it makes the binding return `VOID`, because Ink has no void EXTERNAL and a
writer that returned Python's `None` would otherwise surface as an Ink
runtime error at the call site. Omitting the annotation entirely is a
`TypeError` at class definition time rather than a silent wrong answer.

**`@query` publishes a method to the host's own read API** (the panel/
sidebar surface), independently of whether it is also an `@external`.
Stacking both, as `cost_of` does, means Ink and the host call one
implementation.

**`fields` declares the slot's shape** as name → zero-argument factory, and
`slot_type` is the `TypedDict` that shape must match. The two are checked
against each other when the instance is constructed, so a field added to
one and not the other fails at import, not in a save six months later.
`init_state()` additionally round-trips the fresh slot through
`json.dumps()`, which is what stops a definition object (a dataclass, an
Enum, a compiled table) from leaking into state that has to serialize.

### 3.2 Reading another plugin's state, and `needs_context`

A method that needs more than its own slot takes the binding context
instead:

```python
    @external(needs_context=True)
    def place(self, context: BindingContext[OccupancySlot], character: str, place_id: str) -> None:
        declared = context.slot_of("location_graph").get("declared", {})
        ...
```

`BindingContext` carries `slot`, `engine_state` and `list_defs`, and
`slot_of(state_key)` reads another plugin's slot with a `{}` default. **Use
the default rather than indexing.** A cross-plugin read can legitimately
find nothing: the other plugin may not be active in this session, or the
save may predate it. Readers throughout the shipped plugins use
`.get(..., default)` for exactly this reason, and a new plugin that indexes
directly will KeyError on an old save.

`list_defs` is the story's own compiled LIST tables, for a plugin that must
answer in terms of real LIST members. It is passed as an argument rather
than parked in `engine_state` so it cannot outlive the bind, be read late
from a closure, or reach a host's persisted save.

### 3.3 Definition vs. state, and extending a shipped plugin

**Config is definition; the slot holds only what play changed.** A price
list, a map's edges, a quest catalog — these belong on the instance and are
read live. Only what a session actually changed goes in the slot. This is
not a style preference: it is what lets a new version of a game reach an
existing save. Re-price a spell or add a map edge, and every save in
flight sees it, because the save never contained a copy.

**A game extends an engine plugin by instantiating it with config, or by
subclassing it — and then activates the result, not both.**

```python
ASFA_COSTS = CostTable(name="set_asfa_costs", config=COST_TABLE_CONFIG)

class AsfaSkills(Skills):           # adds fields and methods of its own
    name = "asfa_skills"
    slot_type = AsfaSkillSlot
```

A subclass republishes inherited bindings under the engine's names and adds
its own under whatever convention the game uses. That is how ASFA keeps its
`*_now` names on its own bindings while the engine publishes unsuffixed
ones: a game's vocabulary is the game's to set, and the engine's naming
standard binds only what the engine itself publishes.

Activating both the base plugin and a subclass of it is the one real
hazard, because they share a `state_key`. §3.5 describes what happens.

### 3.4 The flat `Plugin` contract, and stateless plugins

`StatefulPlugin.plugin()` produces the frozen dataclass everything
downstream actually resolves:

```python
@dataclass(frozen=True)
class Plugin:
    name: str
    display_name: str
    bindings: dict[str, Callable[..., Any]] = field(default_factory=dict)
    validate_config: Callable[[Any], None] | None = None
    state_key: str | None = None
    init_state: Callable[[Any], dict[str, Any]] | None = None
    default_config: Any = None
    bind: Callable[[dict, EngineState, ListDefs], dict[str, Callable]] | None = None
```

A plugin with only `bindings` set is a **stateless** plugin: pure functions,
no per-session data, no slot. Declare one directly as a `Plugin`, or hang
one off a stateful plugin's `stateless_bindings` when the functions belong
to the same subject (scheduling's day-phase helpers are stateless while its
clock is not). `state_key is not None` is the real test for "does this
plugin own state" — not the presence of `bind`, which every plugin has.

`ink_engine.discovery.discover_plugins(sources)` scans a host-supplied list
of sources (a `Path` to a directory of independent `.py` files, or a `str`
naming an importable dotted module) and merges every `PLUGIN` /
`PLUGINS` it finds into one dict keyed by name. **This function has no
trust concept whatsoever** — every source given is scanned and imported
unconditionally. Deciding which sources are even safe to pass is entirely
the host's job, upstream of this call.

### 3.5 Two-phase resolution: allocate, then bind

`resolve_bindings(plugins, active_names, engine_state, configs=None)` runs
in two passes, and the split is what makes activation order stop mattering.

**Pass 1, `allocate_state()`** creates every missing slot before anything
binds — so a plugin whose `bind()` reads a neighbour's slot finds it there
regardless of which was activated first. Of the active plugins sharing one
slot, those carrying a config (a host entry, else `default_config`) are its
**seeders**:

- exactly one seeder — it builds the slot: `validate_config(config)`, then
  `init_state(config)`;
- no seeder — the first tenant builds it from `init_state(None)`;
- two seeders — `AmbiguousSlotConfigError`, because whichever won would be
  an accident of ordering. This is the loud failure you get from activating
  both a base plugin and its configured subclass; activate one.

**A slot already present is left alone** — no validation, no re-seeding.
That is the resumed-save path, and it is why config must never be the place
a running session's data lives.

**Pass 2** binds each active plugin and merges the results into the
`dict[str, Callable]` that goes to `InkRuntimeState(engine_bindings=...)`.

## 4. Testing that a binding is really wired

A declared-but-unwired `EXTERNAL` falls through to its Ink fallback and
answers whatever that fallback returns, forever — so "the tests pass" on
its own proves very little. Two checks that do prove something:

- **Assert each plugin's exact binding-name set.** Compare
  `plugin.bindings.keys()` (or the keys returned by `plugin.bind(...)`)
  against an explicit expected list in a test, so an accidental
  addition/removal fails loudly rather than silently changing the surface
  a story can call.
- **Give the Ink fallback an impossible sentinel.** Have the story's own
  fallback function return a value the real binding can never produce
  (e.g. `-1` for a function that only ever returns a real count), then
  assert the observed value during a real play-through is not that
  sentinel. That distinguishes "the binding ran" from "the fallback ran" —
  no ordinary assertion on the returned value alone can tell those apart
  when the fallback's own default happens to overlap with a legitimate
  real answer.
- **Assert the slot stays JSON-safe and encapsulated.** `json.dumps()` the
  slot after exercising the plugin's writers. A slot that will not
  serialize is a save that will not persist, and the usual cause is a
  definition object (a dataclass, an Enum) reaching state that should hold
  only plain data. `init_state()` checks this for a *fresh* slot; only a
  test covers what the writers put there later.

## 5. Runtime notes — for anyone working on `engine.py` itself

- **The output buffer is truncated per turn**, not accumulated forever.
  `continue_story()` records `len(self.output.tokens)` at its own start and
  slices only the new tokens for `last_turn_text` — serializing the whole
  history instead would grow saved state without bound.
- **Glue lookups are cached, not a rescan.** `_latest_glue_index()`
  (`OutputStream`) only rescans the newly appended suffix since the last
  call, not the whole turn's buffer — a stale claim that this was O(n)
  per lookup was corrected in this pass; confirmed by reading the current
  incremental-cache implementation directly.
- **Every transient mid-dispatch flag is part of serialized state**
  (`_eval_run_depth`, `_pending_thread`, `_in_tag`, `_tag_buffer`,
  `_string_capture_stack`, and the rest of `to_dict()`'s own field list) —
  omitting any of them from a save/resume path can leave a resumed session
  in a state the live interpreter would never actually produce on its own
  (e.g. a function-call return marker routed through the wrong branch).
- **[Ink] Tags are cleared per turn.** `current_tags` is reset at the start
  of every `continue_story()` call, matching inkle's own documented
  `currentTags` contract (`RunningYourInk.md`: scoped to "every time you
  get content with `Continue()`") — an interpreter/host that skips this
  leaves every tag ever seen "active" for the rest of the story.
- **Shuffle seeding is a simple character-sum hash of the container's own
  path, combined with the story's seed** — designed to reproduce Ink's
  documented shuffle semantics (`WritingWithInk.md`'s shuffle/`shuffle
  once`/`shuffle stopping` behavior), and reproducible only if the story
  seed itself is pinned (real Ink's own runtime seeds from the wall clock
  by default). `engine.py`'s own docstring for `_shuffle_index` additionally
  claims this "ports `Story.NextSequenceShuffleIndex`... matching the C#
  source exactly" — that specific claim describes matching a named method
  in `ink-engine-runtime`'s actual C# source, which has not been directly
  read and compared in this pass; treat it as unverified until someone
  does that comparison.
- **[Ink] String operators are only `+`/`==`/`!=`**; `?`/`!?` are LIST-only.
  Confirmed directly: `not` applied to a raw string (`not s`, not a
  comparison result) raises `RUNTIME ERROR: ... Cannot perform operation
  '!' on String`; `not` applied to the *result* of a string comparison
  (`not (s == "world")`) works fine, since `==` already produces a boolean
  (see the pitfalls guide's own §1.3).

## 6. Known interpreter gaps

See the main [README](../README.md#limitations) for the maintained,
verified list of what this interpreter does not implement (choice-point
forms, function-call-frame whitespace trimming, and so on) — kept in one
place rather than duplicated here.
