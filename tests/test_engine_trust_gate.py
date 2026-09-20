"""The trust-gate contract and `_call_function`'s real EXTERNAL dispatch
branch.

This module locks in the single most important behavior an application
application relies on: an EXTERNAL call from an untrusted story must
always run its Ink-side fallback, never a real Python callable,
regardless of whether a binding happens to be registered somewhere. It
also proves the trusted half actually works (a real Python callable is
reached, its return value flows back into the story), and that two
concurrent InkRuntimeState sessions calling the exact same registered
Python callable never leak state into each other.

`ink_engine` itself has NO trust concept at all — deciding which
stories/sessions get real bindings is entirely an application's own
adapter concern. What belongs here, and is genuinely portable, is the
ENGINE's own half of the contract: `InkRuntimeState`'s dispatch is a
pure function of whatever `engine_bindings` dict it is constructed
with — a name present in that dict reaches Python, a name absent from it
always falls through to the story's own Ink stub. `_bindings_for()`
below is a trivial local stand-in for the trust decision an application
application's own adapter would make — this file needs no database and
no application framework at all to prove the engine's own real, load-bearing
behavior.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase

from ink_engine.engine import InkRuntimeState, load_story_root

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _mark_ran_binding() -> bool:
    """A trivial, genuinely stateless Python binding for MARK_RAN() —
    returns a fixed value with no side effect on any shared/module-level
    state, matching the per-session isolation requirement (a real binding
    would instead take explicit arguments/return a value derived only from
    them, never read or write anything outside the call)."""
    return True


def _bindings_for(is_engine_trusted: bool) -> dict[str, object]:
    """A trivial stand-in for the trust decision a real application's
    own adapter owns — only ever returns real bindings when explicitly
    told the caller is trusted, mirroring where that decision really
    lives (an application's own view/session layer, never the interpreter
    itself)."""
    return {"MARK_RAN": _mark_ran_binding} if is_engine_trusted else {}


class UntrustedExternalCallAlwaysUsesFallbackTests(TestCase):
    """An EXTERNAL call with no binding for that name always runs its
    Ink fallback, never a registered Python callable — even when a real
    binding for that exact function name exists and would be reachable had
    the caller passed it in."""

    def test_marking_a_story_untrusted_still_runs_the_ink_fallback(self):
        """external_dispatch_proof.ink's MARK_RAN() fallback sets
        a real global (True) — proving the call actually dispatched into
        Ink content, not the Python binding above, which would also set
        the eval stack's return value to True but never touch this
        InkRuntimeState's own `globals` dict at all, so the two paths are
        genuinely distinguishable by more than just the resulting value."""
        compiled_json = _load("external_dispatch_proof.ink.json")
        state = InkRuntimeState(load_story_root(compiled_json), engine_bindings=_bindings_for(is_engine_trusted=False))
        self.assertEqual(state.engine_bindings, {})
        state.continue_story()
        self.assertEqual(state.globals.get("ran"), True)


class TrustedExternalCallReachesThePythonBindingTests(TestCase):
    """A caller that supplies a real binding for a name reaches the
    registered Python callable instead of its Ink fallback."""

    def test_trusted_story_dispatches_to_the_real_python_callable(self):
        """With a real binding registered, MARK_RAN()'s Ink fallback
        (which flips the already-initialized globals["ran"] from False to
        True) must NOT run — proving the Python callable was reached
        instead of the fallback, not just that some code path happened to
        also produce a truthy value."""
        compiled_json = _load("external_dispatch_proof.ink.json")
        state = InkRuntimeState(load_story_root(compiled_json), engine_bindings=_bindings_for(is_engine_trusted=True))
        self.assertIn("MARK_RAN", state.engine_bindings)
        state.continue_story()
        self.assertEqual(state.globals.get("ran"), False)

    def test_trusted_story_binding_return_value_flows_back_into_the_story(self):
        """external_expansion_exargs_proof.ink's SUM3(1,2,3) computes 6 via
        its Ink fallback normally; bound to a real Python callable that
        returns a fixed 42 instead, the printed result must reflect the
        Python return value, proving the value genuinely flows back onto
        eval_stack and into the story's own print expression, not just
        that dispatch was reached."""
        compiled_json = _load("external_expansion_sum3_print.ink.json")
        state = InkRuntimeState(
            load_story_root(compiled_json),
            engine_bindings={"SUM3": lambda a, b, c: 42},
        )
        text = state.continue_story()
        self.assertEqual(text, "Result: 42\n")


class PerSessionIsolationTests(TestCase):
    """The explicit per-session isolation requirement in
    external_expansion_IF_engine.md: multiple users can run multiple Ink
    games concurrently, and nothing about one session may leak into
    another. This test runs two independent InkRuntimeState sessions
    through the exact same registered Python callable object (matching how
    a real per-story binding dict would be shared/reused across every
    request for that story, since it holds no per-game data itself) and
    confirms their resulting game states are fully independent."""

    def test_two_concurrent_sessions_through_the_same_binding_stay_independent(self):
        """Two InkRuntimeState instances, built from the SAME story and
        the SAME bindings dict/callable object, must each hold their own
        independent output/eval_stack/globals — a stateful (and therefore
        non-compliant) binding that stashed something on itself between
        calls would make the second session's result depend on the first
        having already run; this test would only pass by coincidence if
        that were happening, since both sessions call the identical
        SUM3(1,2,3) expression and must both see 6, in either call order."""
        calls: list[int] = []

        def counting_sum3(a: int, b: int, c: int) -> int:
            # Deliberately mutates a variable OUTSIDE this function's own
            # arguments/return value, the exact failure mode the isolation
            # requirement warns about -- proves the *session* state (each
            # InkRuntimeState's own globals/eval_stack) stays independent
            # even though this one shared, stateful callable object is
            # reused across both sessions on purpose.
            calls.append(1)
            return a + b + c

        bindings = {"SUM3": counting_sum3}
        root = load_story_root(_load("external_expansion_sum3_print.ink.json"))

        session_a = InkRuntimeState(root, engine_bindings=bindings)
        session_b = InkRuntimeState(root, engine_bindings=bindings)

        text_a = session_a.continue_story()
        text_b = session_b.continue_story()

        self.assertEqual(text_a, "Result: 6\n")
        self.assertEqual(text_b, "Result: 6\n")
        # The shared callable really was invoked twice, independently --
        # confirms this test isn't vacuously passing because dispatch
        # never happened at all.
        self.assertEqual(len(calls), 2)
        # Each session's OWN state (eval_stack/output/globals) never
        # touched the other's, regardless of the shared callable above.
        self.assertIsNot(session_a.eval_stack, session_b.eval_stack)
        self.assertIsNot(session_a.output, session_b.output)
        self.assertIsNot(session_a.globals, session_b.globals)
