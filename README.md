# ink-engine

A standalone, Django-free Ink interactive-fiction interpreter and plugin engine.

`ink-engine` runs compiled Ink stories (`.ink.json`/`.inkj`) and provides a minimal
plugin contract for host applications (games) to extend the interpreter with their
own stateful mechanics — inventory, scheduling, character occupancy, and so on —
without the engine itself knowing anything about Django, trust/security gating,
or any particular host application's UI conventions.

## Design

- **Zero runtime dependencies.** The interpreter and plugin contract are pure
  Python stdlib.
- **No trust concept.** `ink-engine` scans and loads exactly the sources it is
  given (`discover_plugins(sources)`) — deciding *which* sources are safe to
  load is entirely the host application's responsibility, upstream of ever
  calling into this library.
- **One dataclass, two functions.** `Plugin` describes a discoverable unit of
  Ink `EXTERNAL` bindings, optionally with a private per-session state slice.
  `discover_plugins()` finds them; `resolve_bindings()` builds the real
  bindings dict for one game session.
