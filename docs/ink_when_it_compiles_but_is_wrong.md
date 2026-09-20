# Ink: when it compiles but is wrong

**Date Created:** 2026-09-15  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-20

This document lists the issues that can arise when authoring Ink code.
They were found while porting a game to Ink from another interactive
fiction engine, so some may be edge cases. Most of what follows compiles
cleanly and then misbehaves at play time — which is why it is collected
here rather than left to the compiler to catch. Each entry describes the
issue, includes sample Ink code when the behaviour is subtle, and gives
the compiler or runtime error verbatim. The last part shows how to verify
that a story behaves the way you meant.

**Every behavioural claim here was verified by running real `inklecate`**,
not inferred from documentation, and the sample code is what proved it --
so any of it can be re-run.

inkle's own reference (third-party, not ours) is vendored in this repo at
[`inkles-ink-standard/`](inkles-ink-standard/) — read that for what
Ink *does*; read this for what it does when you get it subtly wrong. Where
inkle's reference already covers something, the entry says so and cites it;
what is left is the behaviour it does not describe. The headline case below,
Section 1.1, is the sharpest of those: inkle documents the construct and
recommends it, and never mentions what it does inside a loop.

```bash
inklecate -o out.json story.ink            # compile
inklecate -p story.ink                     # compile and play in the terminal
printf '1\n2\n' | inklecate -p story.ink   # feed choices; 1-INDEXED
```

---

## Part 1 — The language

### 1.1 Never write a choice inside a conditional block

Inkle states that you can put options inside conditional blocks
(WritingWithInk.md, "Conditional blocks"), and gives a worked example. Their
only caveat is that gather points are not allowed inside them. This guide
disagrees with that advice deliberately. Their example is a one-shot branch
the story never re-enters, so it never reaches the failure described below.

Inkle also states that "conditionals don't override the once-only behaviour
of options". That is true, and it is about a *guard* on a choice
(`* {cond} [Label]`). It does not extend to a choice *wrapped* in a
conditional block.

**A choice must never be written inside a conditional block.**

```ink
{ COND: + [Label] -> scene }      // WRONG - inner choice list
+ { COND } [Label] -> scene       // RIGHT - guarded outer choice
```

The two read identically to a human and compile differently. The wrapped form
becomes a *nested* choice list, and its once-only/consumed tracking does not
survive re-entering the knot.

Combined with the standard hub idiom — a gather that re-enters its own knot,
plus a scene that diverts back — the story takes the same choice again and
again **inside a single turn**, printing the scene's prose each lap and never
stopping to ask the player anything. The turn never ends. The game hangs.

Proof, in eight lines, against real `inklecate`:

```ink
VAR ok = true
-> main
=== main ===
Hub.
{ ok: * [Wrapped once-only] -> back }
* { ok } [Guarded once-only] -> back
+ [Leave] -> END
=== back ===
(chose)
-> main
```

`inklecate -p` never offers the wrapped choice to the player at all. It
auto-takes it forever:

```
Hub.
* [Wrapped once-only] (chose)
Hub.
* [Wrapped once-only] (chose)
...
```

The guarded choice sitting on the very next line behaves correctly.

Note it is `*` — a **once-only** choice — that loops. Marking a choice `*`
gives no protection here; see Section 1.2.

Ban the wrapped form outright rather than policing it case by case: the
guarded form is equivalent everywhere, so there is never a reason to write
the wrapped one. A static check over the story text catches it in one pass.

> **Symptom to recognise:** the game stops responding at one specific
> location, CPU pinned, no error, no output. Look for a wrapped choice in the
> hub you were standing in.

### 1.2 Once-only (`*`) vs sticky (`+`)

A `*` choice **does** stay consumed across re-entry, including a round trip
through another knot:

```ink
-> main
=== main ===
Choose.
* [Once-only A] -> back
+ [Sticky B] -> back
+ [Leave] -> END
=== back ===
(chose)
-> main
```

After taking A once it is gone; B stays forever. This is why Section 1.1 is
surprising: the wrapped form defeats tracking that otherwise works fine.

**`*` strands players.** A knot whose only exits are once-only leaves a
returning player with nothing to click. This happens two ways:

- **A gated `+` is not an unconditional exit.** If the `+` guard is false, the
  spent `*`s are all that remain and the knot has *no exit at all*:

  ```ink
  === main ===
  The room.
  * [Look around] -> main
  + { can_leave } [Leave] -> END
  ```

  Take "Look around" with `can_leave` false and Ink stops with
  `RUNTIME ERROR: ran out of content. Do you need a '-> DONE' or '-> END'?`
  A check that only flags knots whose exits are *all* once-only will not
  catch this — the `+` makes it look safe.

- **Reset paths replay spent choices.** Anything that reopens a chain from
  the top finds every `*` in it already consumed.

If you are porting a game whose engine redraws its menu each turn, its
choices are sticky by nature — `+` is the faithful default, and `*` is the
deliberate exception.

### 1.3 `not` binds tighter than comparison

`not X == "y"` parses as `(not X) == "y"`.

With a **string**, this is a hard runtime error, and it fires only when that
line is actually reached — so it compiles, ships, and waits:

```ink
{ not where_is() == "kitchen": ... }
// RUNTIME ERROR: Cannot perform operation '!' on String
```

With a **number**, `not f() > 0` and `not (f() > 0)` both fire — the two agree
at every reachable value, so numeric sites are safe and rewriting them is
churn. Check the actual value range before "fixing" one.

**Always parenthesise:** `not (expr == value)`.

Both failure modes are silent at compile time, so a static check over guard
expressions earns its place.

### 1.4 Structural rules (all compile-time, with exact messages)

| Rule | Error if broken |
|---|---|
| A stitch may not share a name with a VAR | `Stitch 'shop': name has already been used for a var on line 1` |
| A function may not contain a divert | `Functions may not contain diverts, but saw '-> main'` |
| Diverting into a stitch **from outside its knot** needs the full path | silently a loose end / unresolved |

Within a knot, a sibling stitch is reachable by bare name (`-> second`). From
anywhere else it must be `-> knot.stitch`.

**So anything diverted to from another file must be a top-level knot.** Ink
silently binds `= name` as a stitch of whichever knot precedes it — no error
at the declaration. The failure appears far away as `divert target not found`,
or, if the stitch trails the file's last knot, as content that is simply
unreachable with **no error at all**:

```ink
=== shop_floor ===    // globally divertable
= shop_floor          // becomes back_office.shop_floor — not what you meant
```

**Ink has no bitwise operators.** The arithmetic set is
`+ - * / % mod` plus `POW(x, y)`. If the game you are converting packs flags into integer
bitfields, do not hand-roll bit arithmetic to preserve a memory-packing
trick that has no meaning in Ink — port one flat named boolean per flag. The
general principle: **port the content, not the storage mechanics.**

**`not` also binds tighter than `?`, but this one is not silent.**
`not present ? alice` is a compile-time error — inklecate names the exact
fix: `Using 'not' or '!' here negates 'present' rather than the result of
the '?' or 'has' operator. You need to add parentheses around the (A ? B)
expression.` Unlike the string-comparison case in Section 1.3 above (which
compiles fine and only fails at runtime, if it's ever reached), this one
is caught immediately. Parenthesise: `not (present ? alice)`.

**Stitches must stay contiguous with their parent knot.** Never insert a new
`=== knot ===` between an existing knot's choices and its own `=` stitches —
it silently reparents them. Recompile after any insertion into a stitched
knot.

**A prose line starting with a keyword becomes code.** A narrative line
beginning `VAR ...` is parsed as a declaration:

```
ERROR: Expected variable name but saw '-in-interpolation and shuffles.'
```

**A `=== function ===` swallows everything until the next `===`.** Dropping
one into the middle of a file therefore captures whatever followed it —
including the file's own `-> start` divert, which then reports
`Functions may not contain diverts`. Put functions after the divert that
starts the story, or at the end of the file. (This bit while writing *this
guide's own* test cases.)

### 1.5 Functions

- A function **cannot contain stitches, use diverts, or offer choices**
  (inkle lists these limitations together), but it **may mutate a global**
  — that is the escape hatch for side effects.
- `~ temp x = ...` is scoped to the function/knot; globals are `VAR`.
- **You do not need to capture a return value.** `~ do_thing()` is a valid
  statement even when `do_thing` returns something, and this holds for
  `EXTERNAL` bindings too.
- **A function that falls off its end returns Void, not `0`.** Interpolating
  it yields nothing: `[{nothing()}]` renders `[]`. An engine that substitutes
  `0` for Void will print a literal `"0"` into the prose.
- **A misspelled function name can interpolate `0` instead of failing.** Real
  Ink treats an unresolvable function call as a story error; this engine
  degrades to `0` rather than crashing (`engine.py`, `_call_function`). So
  `{caclulate_total()}` renders `0`, with no error — and `0` is a value a
  working function could legitimately return.
  If a `0` appears that you cannot account for, check the spelling of the
  function names near it before debugging the arithmetic.

### 1.6 A story may not begin with a named knot

Inkle covers this under "a knottier 'hello world'" — content outside knots
runs automatically, knots do not, so a file using knots must divert into one.
The symptom: if the literal first line is `== knot ==`, the
compiler is happy and the story produces **zero playable output**, because the
entry point is the top-level flow and a leading named knot is never entered.
**If a story compiles but prints nothing at all, check line 1 first.**
Start the file with
`-> start` (or with prose).

If a story compiles but prints nothing at all, check line 1 first.

### 1.7 `-> END` and `-> DONE` on a choice end the GAME

Both look like "this branch is finished," which is exactly what makes this
easy to write by accident:

- `-> END` ends the **story**, not the scene.
- `-> DONE` ends the **thread**; with nothing else running the runtime has
  zero choices, which a player sees as "The story has ended."

Inkle states this distinction directly — "Using `-> END` in this case will
not end the thread, but the whole story flow. (And this is the real reason for
having two different ways to end flow.)" What follows is the authoring
consequence, which it does not cover.

Verified: a hub offering `+ [Leave via END] -> END` and
`+ [Leave via DONE] -> DONE` produces no further output from either.

An exit choice must divert to a real destination. The faithful target is
usually "the place that applications this scene" — but **it is per-scene, so a
blanket substitution is wrong**: sending every scene back to a single shared
hub can turn an "Exit" choice into a loop back into the very place it was
meant to leave.

When auditing for this, **survey by what the choice does, not by its
label**: exit-type choices are not all called "Leave" or "Exit" — they are
also "Say goodbye to…", "Head home", "Step out", "Slip away".

`-> END` used as a *placeholder* is the same bug in another form: an
unfinished branch ending `-> END` makes that outcome an unconditional game
over, with whatever should follow it unreachable.

Legitimate uses: a real, named ending the story actually intends.

**An unlabelled choice is not a broken choice — it is a fallback.**
`* -> somewhere` is Ink's documented *fallback choice* (WritingWithInk.md,
"Fallback choices"): deliberately never shown to the player, and taken
automatically when no other option is available. There is also a "choice then
arrow" form (`* ->` with content beneath it).

The mistake is writing one when you meant a visible choice: it renders as a blank
entry, or under `inklecate -p` as no entry at all, so a choice you expected to
offer simply is not there. Do not "fix" unlabelled choices by adding labels —
that breaks every intentional fallback in the corpus. Check whether each one
was meant to be visible.

A fallback is also the standard cure for the stranding in Section 1.2: it
gives an exhausted knot somewhere to go instead of running out of content.

### 1.8 Tunnels lose content silently

```ink
-> sub ->        // call
...
=== sub ===
->->             // return
```

Inkle warns about this in one sentence — "tunnel knots aren't declared as
such, so the compiler won't check that tunnels really do end in `->->`
statements, except at run-time. So you will need to write carefully to ensure
that all the flows into a tunnel really do come out again." (It also sanctions
finishing a tunnel on a normal divert where that is what you meant.)

What the warning does not give you is the symptom. If the target ends in
`-> END` (or a plain divert) instead of `->->`, **everything after the call
site is dropped with nothing to announce it** — the loss is invisible rather
than reported:

```
Tunnel that forgets to return.
In sub, diverting instead of returning.
[the line after `-> sub ->` never prints]
```

**A tunnel-return choice needs somewhere to return to.** A choice written
`-> scene ->` at the end of a knot that has no gather produces
`Apparent loose end exists where the flow runs out`. Give it a landing stitch:

```ink
= scene_from_hub
-> scene ->
-> hub
```

### 1.9 Alternatives

Verified across repeated visits:

| Syntax | Behaviour | Sequence over 4 visits |
|---|---|---|
| `{a\|b\|c}` | sequence, **sticks on last** | a, b, c, c |
| `{&a\|b\|c}` | cycle, wraps | a, b, c, a |
| `{!a\|b}` | once-only, then **empty** | a, b, ∅, ∅ |
| `{~a\|b\|c}` | shuffle | random without replacement |

Shuffle seeds from the container's path via a simple character-sum hash plus
the story seed — so it is reproducible only if you pin the seed. A runtime
that seeds from the wall clock (as real Ink's C# runtime does) gives different
results for the same save.

**Shuffle *order* may not match `inklecate` for the same seed.** This engine
reproduces Ink's documented shuffle/shuffle-once/shuffle-stopping semantics,
but its path hash has never been diffed against the C# source
(`engine.py`, `_shuffle_index`). It matches at least one captured real
transcript (`tests/test_engine_rng.py`); treat anything beyond that as
unverified. Do not use a shuffle to derive a value that must agree with a
run under a different runtime.

### 1.10 Conditionals, truthiness, LIST

- `0` is falsy; a non-empty LIST is truthy.
- **`""` is falsy and any non-empty string is truthy**, so
  `{ where_is("x"): ... }` reads directly as "is x somewhere".
- `{cond: A|B}` is if/else inside text; `- else:` is the block form.
- LIST: `?` tests membership, `LIST_COUNT()` sizes, `+=`/`-=` add and remove.
- Interpolation **does** work inside a function call's arguments:
  `{echo("{flag:X|Y}")}` renders `X`, the same as writing `{flag:X|Y}`
  directly. (Verified against `inklecate` and this engine; an earlier
  revision of this guide claimed the opposite.)

**Numbers and strings compare equal across types.** `"5" == 5` is **true**,
in both orders. So a function that returns `"0"` where the story expects `0`
compares equal and the type error never surfaces. Do not rely on a comparison
to catch a wrong return type.

**Floats and integers compare equal too:** `6.0 == 6` is true. That is
usually what you want — an application binding returning a float still
satisfies an
integer gate — but it means a comparison will not tell you which type you
actually got.

**Spaces inside `{cond:a|b}` become output.** Ink treats them as literal text,
not syntax whitespace:

```ink
A:{flag:Sarah|Angela}.        // renders "A:Sarah."
B:{ flag: Sarah | Angela }.   // renders "B: Sarah ."  <- note the spaces
```

Both compile. Only the spaced one is wrong, and only visibly so in the prose.

**There is no chained multi-branch inline conditional.** Ink has no `?:` and
no `elif` inside `{...}`:

```ink
{n==1:x|n==2:y|z}     // ERROR: Expected one or two alternatives
                      // separated by '|' in inline conditional
{n==1:x|{n==2:y|z}}   // valid - must nest
```

**Nesting then has a hard ceiling.** The compiler dies at **depth 23** — of
*inline conditionals* specifically. Weave nesting is a separate mechanism and
inkle states it has no depth limit.

```
Unhandled exception. System.Exception: Stack overflow in parser state
```

Measured by compiling generated stories at increasing depth — depths 1-22
compile clean. Past a handful of levels a flat block is easier to read than a
nest anyway:

```ink
{ n == 0: L0 }
{ n == 1: L1 }
{ n == 2: L2 }
```

### 1.11 Visit counts

`{knot_name}` is the visit count and increments normally across knots. If a
count looks stuck, suspect a consumed choice rather than a counting quirk.

Because `0` is falsy, a bare knot name in a conditional reads as
"have I been here":

```ink
{ room: You have been to the room. | You have never been to the room. }
```

### 1.12 Only the FIRST top-level divert runs

The story follows the first unconditional top-level divert and never returns
to the others. In a multi-file corpus this silently kills per-file entry
points: if the master file has `-> game_introduction` before its `INCLUDE`s,
then every included file's own `-> <character>_start` divert is **dead**.

Note the precise rule: a divert is only dead if it sits **before its file's
first knot**. A column-0 divert further down is ordinary flow — a detector
that ignores that distinction over-reports badly.

### 1.13 `INCLUDE` has no scoping — everything is one namespace

`INCLUDE` merges every file into one namespace. That surprises people in
three different ways:

- **VARs are corpus-wide.** There is no per-file scope. A scene that hardcodes
  a value believing another file's variable is "not cross-referenceable" is
  wrong — it was always readable.
- **A duplicate `VAR` is a hard error, not a silent merge.** Including two
  files that both declare it fails the build.
- **Tags flatten too.** Two files' same-named `# image: pool.jpg` tags
  silently collide. Give every tag a path prefix that is unique per file.

**The dangerous middle case is a local VAR shadowing a global of the same
meaning with a different default.** One file writes its own copy while every
other file reads the shared one, so the change is invisible everywhere except
where it was made. Neither version compiles wrong.

The rule that prevents it: **any VAR read or written by more than one file
belongs in a single shared globals file**, never in one of the participating
files. Then a second file cannot silently declare its own copy — the name is
already taken, and a typo becomes `Unresolved variable` instead of a
permanently-false boolean.

### 1.14 Randomness

- `{a|b|c}` and `{&a|b|c}` involve **no randomness at all** — they are
  `MIN(visit_count, N-1)` and `visit_count % N`. Only `{~a|b|c}` and
  `LIST_RANDOM` use the RNG.
- **`RANDOM()` re-rolls on every knot visit.** For a stable value, hold it in
  a VAR; when an image tag and its prose must agree, hold the roll in a
  `~ temp` so the two cannot disagree.
- **`RANDOM()` is wall-clock seeded**, matching real Ink's C# runtime — so
  two runs of the same test differ, and `inklecate -p` on an unseeded fixture
  differs run to run. Pin a seed or harness numbers are meaningless.
- **A story has no fixed seed unless something pins one.** Three things do:
  `SEED_RANDOM(n)` from the story itself; the application passing its own
  `random_engine` when constructing the runtime; and **resuming a save** —
  `story_seed` and `previous_random` are both serialized, so a restored save
  continues the same sequence rather than re-rolling. (The C# caveat above is
  about real Ink's runtime, not this one.)
- **A wall-clock-seeded run here will not match a wall-clock-seeded
  `inklecate` run**, even at the same instant: this engine reproduces only the
  *nondeterminism* of C#'s clock seed, not its exact formula (`rng.py`,
  `time_seed`). Pin the seed on both sides before comparing transcripts.

### 1.15 LIST gotchas

```ink
LIST AllCharacters = alice, bob, carol   // the universe of possible members
VAR here = ()                            // the subset currently true
```

One global set re-valued as things move — never one list per location.

**`?` against a group means "contains ALL of them", not "any".** Inkle
documents this — it is the subset operator, and `^` is the one for
"any" (WritingWithInk.md, "Intersecting lists"). It is listed here only
because it bites hard when mechanically replacing `a_here or b_here`:

```ink
~ here = (alice, bob)
{ here ? (alice, bob, carol): ... }   // NO  - asks whether ALL three are here
{ here ^ (alice, carol): ... }        // YES - intersection: any of them
{ (here ? alice) or (here ? carol): ... }   // also correct, more verbose
```

Use `^`. The `or` chain is worth knowing as the mechanical conversion of
an existing `a_here or b_here`, and is what you need when the members
being tested are not a fixed group — but reach for `^` first.
Parenthesise each `(here ? x)` if you do write the chain: it is being
dropped into a larger boolean expression.

**A duplicate LIST member under two spellings compiles silently.** Unlike a
duplicate function (a hard error), declaring both `guard_captain` and
`guardcaptain` means one is silently checked and the other silently ignored.
Pick a spelling convention and machine-check it.

**Machine-check member count against write count, in both directions.** A
member never added is permanently absent; an add with no member is a compile
error.

### 1.16 `~` needs its own line

```ink
{ flag: ~ here += a }   // ERROR
```
```
You shouldn't use a '~' here - tildas are for logic that's on its own line.
To do inline logic, use { curly braces } instead
```

Use the block form:

```ink
{ flag:
    ~ here += a
}
```

It is easy to write this in bulk — a whole function's worth of conditional
additions at once — and the whole function then fails to compile.

### 1.17 LISTs have no `for` loop — traverse them by recursion

There is no `for` loop, but a list **can** be traversed — by recursion.
Inkle's own `reach()` function does exactly this: `pop()` a member, act on
it, then call itself with what is left (WritingWithInk.md, in the extended
LIST example).

```ink
=== function reach(statesToSet)
   ~ temp x = pop(statesToSet)
   { - not x: ~ return false
     ...
     ~ reach(statesToSet)     // recurse over the remainder
   }
```

So "every member of this list does X" is a recursive function, not one block
per member. Writing it out by hand is only necessary where each member needs
*different* content — a per-member choice with its own text.

Relatedly, **a plain divert cannot return to its caller** — that is what
tunnels are for (Section 1.8). Where a scene must resume one of two different
callers, either use a tunnel or carry an explicit "where to go back to" VAR.

### 1.18 Threads inject choices ahead of the application's own

`<- other_knot` pulls another knot's choices into this one. The threaded
choices are listed **first**:

```ink
=== main ===
Main choices.
<- extra_choices
+ [Own choice] -> END
```

```
1: Threaded choice
2: Own choice
```

Inkle documents the ordering, with a numbered worked example: the first
fork considered runs the threaded content and collects its options, then the
other fork runs.

Recorded here only because it bites anything that selects choices by index — a
test, a walkthrough, a piped `inklecate -p` script.

---

## Part 2 — Verifying a story

### 2.1 Randomized playthrough is the highest-value test

Drive the compiled story with random choices — say 40 runs of up to 600
steps, fixed seeds — and report steps taken, dead ends and errors. It finds
what unit tests do not: unreachable content, crashes deep in a branch, and
the Section 1.1 hang. **Pin the story seed** (the runtime seeds from the wall clock
by default) or failures are unreproducible.

A **dead end** — no choices offered while text is still pending — is a real
defect, distinct from a proper ending.

### 2.2 Debugging a hang

1. `faulthandler.dump_traceback_later(25, exit=True)` gives the stack.
2. Watch the output-token count from a thread. Steady growth with the step
   index frozen = one turn is emitting unboundedly.
3. Print the accumulated text — the repeating passage names the knot.
4. **Reduce to a minimal `.ink` and run it through real `inklecate`.** This is
   the step that decides whether it is an engine bug or a story bug — if
   `inklecate` itself loops identically, the interpreter is faithful and the
   fix belongs in the story.

### 2.3 Recompile after every edit

Not at the end of a batch — an edit that looks correct in the diff (a
duplicated `~ return`, a severed stitch chain) can still be structurally
broken, and only a real recompile catches it.

Compare against a **known error baseline**, not against zero, and check the
remaining error *set*, not just the count: counts can fall while a new
regression hides among the fixes. A recorded baseline goes stale — re-verify
it rather than trusting a stated number from an earlier pass.

---

## Appendix — Checklists

**Before writing a choice**
- [ ] Guard is `+ { cond } [Label]`, never `{ cond: + [Label] }`
- [ ] `not (a == b)` and `not (list ? x)`, parenthesised
- [ ] It has a label — `+ -> target` is unusable
- [ ] It does not divert to `-> END` or `-> DONE` unless it really is an ending
- [ ] Divert into another knot's stitch uses `knot.stitch`
- [ ] A `-> scene ->` tunnel choice has a landing stitch
- [ ] Tunnel targets end in `->->`
- [ ] `*` is deliberate — is there still an exit once it is spent?

**Before adding a VAR**
- [ ] Something actually writes it
- [ ] The name matches every read exactly, and nothing already tracks the same
      fact under another spelling
- [ ] It doesn't collide with a stitch name or an `EXTERNAL` parameter name
- [ ] If two files touch it, it lives in the shared globals file
- [ ] Its sentinel (`0`, `""`, `-1`) cannot collide with a real value
- [ ] It is stored, not derivable from something already tracked

**Before calling it done**
- [ ] Compiles with zero errors *and* zero warnings
- [ ] Randomized playthrough: 0 dead ends, 0 errors
- [ ] Any new static check has been mutation-tested — reintroduce the bug,
      confirm red, restore
