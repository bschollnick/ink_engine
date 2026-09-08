"""EXTERNAL fallback resolution + full-story validation (ink_engine.engine).

InkRuntimeState is driven end-to-end against real compiled JSON
(tests/fixtures/*.ink), with every expected transcript captured from a
real inklecate build's -p play-mode transcript before any assertion was
written. This module also covers the empty-bracket choice syntax
(`* text[]more`), uncovered by full-story validation against a
real-world story.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    Container,
    FunctionCall,
    InkRuntimeState,
    UnboundExternalError,
    find_unbound_externals,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _run(name: str, with_list_defs: bool = False) -> InkRuntimeState:
    data = _load(name)
    if with_list_defs:
        return InkRuntimeState(load_story_root(data), load_list_defs(data))
    return InkRuntimeState(load_story_root(data))


class ExternalFallbackTests(SimpleTestCase):
    """EXTERNAL declarations resolve to their ink fallback function.

    `EXTERNAL name(...)` leaves no trace at all in compiled JSON; a
    same-named `=== function name(...) ===` immediately after it is
    already an ordinary function. The compiled call site itself,
    however, is not an ordinary `{"f()": ...}` — it's `{"x()": ...,
    "exArgs": n}`, a distinct key that must be built for explicitly:
    without it, every external call silently no-ops instead of
    dispatching. Both fixtures below happened to render identical final
    text either way (uppercase.ink's fallback is an identity passthrough;
    string_to_list.ink's skipped call left the original string on the
    eval stack, which happens to render the same as the
    correctly-resolved single-word LIST item) — a false positive that can
    mask this bug from text-only assertions alone. Those assertions are
    kept here for their real-transcript-fidelity value;
    ExternalCallDispatchTests below adds a side-effect-based assertion a
    no-op dispatch could not satisfy by coincidence."""

    def test_uppercase_fallback_matches_real_transcript(self):
        """UPPERCASE's ink fallback ({txt}) is a stub that doesn't
        actually uppercase — matches the real transcript exactly,
        including that non-transformation, since no real host function is
        bound here (external_uppercase.ink)."""
        state = _run("external_uppercase.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Give me wine!\n")

    def test_string_to_list_fallback_matches_real_transcript(self):
        """STRING_TO_LIST's fallback chain (a sentinel function + a
        recursive string-match search) resolves "Paris" back to the LIST
        item Paris, matching the real transcript exactly
        (external_string_to_list.ink)."""
        state = _run("external_string_to_list.ink.json", with_list_defs=True)
        text = state.continue_story()
        self.assertEqual(text, "Result: Paris\n")


class ExternalCallDispatchTests(SimpleTestCase):
    """A direct, minimal regression for the "x()" no-op bug — isolates
    the dispatch itself (does calling an EXTERNAL with a fallback that
    mutates a global actually run the fallback body) rather than relying
    on final printed text, which the two real-story fixtures above
    showed can coincidentally match even when the call never dispatches
    at all."""

    def test_external_call_runs_its_fallback_body(self):
        """A fallback that sets a global variable must actually run — the
        global's value after the call proves dispatch happened, unlike a
        text-only assertion which the no-op bug could still satisfy by
        accident (external_dispatch_proof.ink)."""
        state = _run("external_dispatch_proof.ink.json")
        state.continue_story()
        self.assertEqual(state.globals.get("ran"), True)


class ExternalArgCountTests(SimpleTestCase):
    """A real "x()" call's "exArgs" key must parse into
    FunctionCall.external_arg_count — previously silently discarded
    (this dispatch path's own Ink-fallback handling never needed arity,
    since it's self-describing via what's already on eval_stack), but
    required by the real Python-callable dispatch branch, which has no
    Ink-side `temp=` header to consume eval_stack on its own."""

    def test_real_exargs_value_round_trips_onto_the_function_call(self):
        """A compiled "x()" call declaring "exArgs": 3 parses with
        external_arg_count == 3, found by walking the compiled tree for the
        one real FunctionCall node (external_expansion_exargs_proof.ink)."""
        root = load_story_root(_load("external_expansion_exargs_proof.ink.json"))
        found = []

        def walk(container: Container) -> None:
            for item in container.content:
                if isinstance(item, FunctionCall):
                    found.append(item)
                elif isinstance(item, Container):
                    walk(item)

        walk(root)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].is_external)
        self.assertEqual(found[0].external_arg_count, 3)

    def test_ordinary_internal_call_has_no_arg_count(self):
        """An ordinary "f()" call (is_external=False) never carries
        "exArgs" in real compiled output — external_arg_count must stay
        None, not default to some other sentinel, so a future dispatch
        branch can tell "not an external call at all" (None) apart from "a
        real external declared with zero arguments" (0, e.g.
        external_dispatch_proof.ink.json's MARK_RAN() call)
        (recursive_function.ink, a real internal self-recursive
        function call, is_external=False)."""
        root = load_story_root(_load("recursive_function.ink.json"))
        found = []

        def walk(container: Container) -> None:
            for item in container.content:
                if isinstance(item, FunctionCall):
                    found.append(item)
                elif isinstance(item, Container):
                    walk(item)

        walk(root)
        self.assertEqual(len(found), 1)
        self.assertFalse(found[0].is_external)
        self.assertIsNone(found[0].external_arg_count)


class UnboundExternalTests(SimpleTestCase):
    """find_unbound_externals() walks the tree for every "x()" call
    site and checks its target name resolves to a real Container — the
    only viable detection strategy given that EXTERNAL leaves zero
    trace of its own declaration in compiled JSON."""

    def test_bound_externals_report_nothing(self):
        """A story whose every EXTERNAL has a same-named ink fallback
        reports no unbound names, across both real bundled EXTERNAL
        fixtures."""
        for name in ("external_uppercase.ink.json", "external_string_to_list.ink.json"):
            root = load_story_root(_load(name))
            self.assertEqual(find_unbound_externals(root), [])

    def test_missing_fallback_is_reported_by_name(self):
        """Removing UPPERCASE's own fallback function from the compiled
        tree (simulating a story whose EXTERNAL was never given one) is
        reported by name, not silently accepted."""
        data = _load("external_uppercase.ink.json")
        del data["root"][2]["UPPERCASE"]
        root = load_story_root(data)
        self.assertEqual(find_unbound_externals(root), ["UPPERCASE"])


class UnboundExternalDispatchTests(SimpleTestCase):
    """An EXTERNAL call with neither a bound Python callable nor a
    resolvable Ink fallback raises UnboundExternalError instead of
    silently pushing 0 — matches real inklecate, which compiles such a
    story successfully but raises "Missing function binding for
    external... and no fallback ink function found" the moment the call
    is actually reached (confirmed directly against inklecate v1.2.1,
    inkVersion 21)."""

    def test_no_binding_no_fallback_raises(self):
        """Removing UPPERCASE's own fallback function from the compiled
        tree, then actually running the story with no engine_bindings,
        must raise rather than silently render "0" for the call
        expression."""
        data = _load("external_uppercase.ink.json")
        del data["root"][2]["UPPERCASE"]
        state = InkRuntimeState(load_story_root(data))
        with self.assertRaises(UnboundExternalError):
            state.continue_story()


class VoidReturnTests(SimpleTestCase):
    """A function that falls off the end of its body without an
    explicit "~ret" implicitly returns Void (real Ink: functions may
    evaluate to Void), which must render as no output at all -- a print
    expression calling such a function (e.g. `{UPPERCASE(...)}` where the
    fallback body has no `~ret`) must not print the literal text "0".
    Covered indirectly by ExternalFallbackTests' uppercase.ink case above
    (its fallback has no `~ret`); this class adds a minimal, deliberately
    EXTERNAL-free fixture isolating just the void-return-printed-as-
    expression behavior."""

    def test_void_returning_function_prints_nothing(self):
        """A function with no `~ret` called as a print expression
        contributes no visible text for its own return value — only
        whatever it explicitly printed via its own inline `{...}` runs
        inside the function body (void_return.ink)."""
        state = _run("void_return.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Give me wine!\n")


class EmptyBracketChoiceTests(SimpleTestCase):
    """`* text[]more` (Ink's empty-bracket choice syntax) —
    found genuinely unimplemented during full-story validation against a
    real-world story, previously deferred as "weave/tunnel machinery"
    without being tracked by name. Regression coverage for three real
    bugs found together:
    (1) ChoicePoint.has_start_content was treated as an unconditional
    bail rather than a second text-pop (Story.ProcessChoice pops
    choice-only text, then start text, concatenating them);
    (2) Divert.is_variable_target (`{"->": "varName", "var": true}`) was
    entirely unimplemented — the choice text is built via a divert into
    the choice's own display-text container, then a variable-pointer
    divert back to a saved return address;
    (3) _step()'s out-of-range-index check unconditionally ended the
    whole story instead of walking up to the parent container, which
    broke landing on the empty anonymous return-address container this
    construct's variable-target divert lands on
    (bracket_choice.ink)."""

    def test_choice_text_and_followed_content_match_real_transcript(self):
        """The choice text ("Hut 14", built from start text alone — no
        choice-only text in this fixture) and the content reached after
        choosing it both match the real transcript exactly."""
        state = _run("bracket_choice.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "They are keeping me waiting.\n")
        self.assertEqual([c.text for c in state.current_choices], ["Hut 14"])
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "Hut 14. The door was locked after I sat down.\nI don't even have a pen to do any work.\n")


class ThreadedFunctionConditionalChoiceTests(SimpleTestCase):
    """a `<- funcName(-> returnPoint)` thread (a function called as a
    thread, not a bare knot) whose own choice is conditional. A case that
    additionally depends on the still-out-of-scope `ref` parameter
    feature is a documented known exception rather than fixed here
    (thread_func_condition.ink)."""

    def test_false_condition_hides_the_threaded_choice(self):
        """A thread that's a function call, with an internally false
        choice condition, correctly shows no thread-generated choice —
        matching the real transcript's plain ["A", "B"] exactly, with no
        spurious blank-text choice."""
        state = _run("thread_func_condition.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "")
        self.assertEqual([c.text for c in state.current_choices], ["A", "B"])
