# inkle's Ink Standard

**This is not our documentation.** It's a verbatim, unmodified copy of
inkle's own Ink language/runtime docs (© inkle Ltd, MIT licensed — see
`retrieved-2026-09-02/LICENSE.txt`), kept here so the standard is right in
front of anyone working on `ink_engine` — the exact text this
implementation was written against, pinned rather than left to drift
upstream. Anything this project has written *about* Ink — our own
gotchas, conventions, engine-specific binding notes — lives alongside this
folder in [`docs/`](../) instead; that's the place to look for
project-authored material.

**These files are third-party and read-only. Do not edit them.** Editing a
vendored file would silently fork it from upstream and make the next
refresh a merge conflict — see *Related reading* below for where
corrections and project conventions actually belong.

## Contents

The actual documents live in [`retrieved-2026-09-02/`](retrieved-2026-09-02/),
named for when this copy was pulled — each future refresh gets its own
dated subfolder rather than overwriting the last one in place, so it's
always clear which version of the standard a given claim in this project's
own docs was checked against.

| File | What it covers |
|---|---|
| `WritingWithInk.md` | The language reference — knots, stitches, weave, diverts, choices, variables, LIST, functions, tunnels, threads. The one to reach for when writing a story. |
| `RunningYourInk.md` | Embedding a compiled story: the runtime API, `EXTERNAL` binding, tags, save/load. |
| `ArchitectureAndDevOverview.md` | How the compiler and runtime fit together, for people working on Ink itself. |
| `ink_JSON_runtime_format.md` | The compiled `.json` container format — the spec `engine.py` implements. |
| `LICENSE.txt` | inkle's MIT licence, which is what permits this copy. |

## Provenance

- **Source:** <https://github.com/inkle/ink> — `Documentation/`, `master` branch
- **Retrieved:** 2026-09-02, via `raw.githubusercontent.com`
- **Upstream state at retrieval:** last `Documentation/` commit `ead3cab938fb`
  (2025-04-20); latest tagged release `v1.2.1` (2026-05-05)
- **Licence:** MIT, © inkle Ltd. See `retrieved-2026-09-02/LICENSE.txt`.

SHA-256 of the copies as retrieved, so a later refresh can tell whether
anything actually changed:

```
0555b6ac648055967fd2c1b636d32e47180d6c4e69f2cb09144ecf5278fb5ecb  WritingWithInk.md
94031c0de03ffa6f9109728f4fe11e05ddc3fdd7e9f05dd52251ee93c9f859ba  RunningYourInk.md
d6f28dfd202ea471cc07255e95b247cf06b36a30ebb8d16ddf27b8ec0f8a3287  ArchitectureAndDevOverview.md
399f423e6c78364ff82bb8beca7e119d9f638b912ee201f38a9a76e593cb6d89  ink_JSON_runtime_format.md
```

### Refreshing

Pull a new dated copy alongside the existing one — never overwrite a
retrieved snapshot in place:

```bash
cd interactive_fiction/inkles-ink-standard
mkdir "retrieved-$(date +%Y-%m-%d)" && cd "retrieved-$(date +%Y-%m-%d)"
for f in WritingWithInk RunningYourInk ArchitectureAndDevOverview ink_JSON_runtime_format; do
    curl -sLO "https://raw.githubusercontent.com/inkle/ink/master/Documentation/$f.md"
done
curl -sLO "https://raw.githubusercontent.com/inkle/ink/master/LICENSE.txt"
shasum -a 256 *.md          # compare against the block above
```

Then re-check anything in the project's own guides that cites upstream
behaviour, update this README's own "Contents" link and hashes to point at
the new dated folder, and decide whether to keep or remove the old one.

## Which version this matches

This documents what version of Ink `ink_engine` was reverse-engineered
against: `inklecate` emitting `"inkVersion": 21`, the runtime format
`retrieved-2026-09-02/ink_JSON_runtime_format.md` describes.

Our `ink_engine` doesn't enforce any particular version of compiled ink
output, but if inkle updates the standard, there could be unexpected
behavior from our ink engine. The intent is to keep the ink engine
up-to-date with inkle's standard reference.

## Related reading — this project's own documents

- **[`ink_pitfalls_and_debugging.md`](../ink_pitfalls_and_debugging.md)**
  — standard Ink as actually encountered while building and testing this
  engine: the gotchas, exact compiler error messages, and behaviours
  verified by running `inklecate` rather than inferred. Complements the
  upstream reference; it is deliberately about the sharp edges, not full
  coverage.

  The two do not overlap as much as you would expect. `WritingWithInk.md`
  documents the *correct* way to write a conditional choice
  (`* { cond } [Label]`, §7 "Conditional Choices") but never mentions that the
  wrapped form `{ cond: * [Label] }` also compiles — and then silently
  auto-takes itself forever inside a hub. Read the upstream docs for what Ink
  *does*; read ours for what it does when you get it subtly wrong.
- **[`ink_engine_bindings_guide.md`](../ink_engine_bindings_guide.md)**
  — how a story reaches Python from this engine's own perspective:
  `EXTERNAL` binding wiring and its silent failure modes, the `Plugin`
  contract, and runtime notes for anyone working on `engine.py`.
