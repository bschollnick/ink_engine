"""call stack + tunnels (ink_engine.engine).

InkRuntimeState is driven end-to-end against real compiled JSON
(tests/fixtures/*.ink), with every expected transcript captured
from the local inklecate build's -p play-mode transcript before any
assertion was written (per the plan's standing validate-against-real-data
rule).
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import InkRuntimeState, load_story_root

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class SingleTunnelTests(SimpleTestCase):
    """a single `-> knot ->` / `->->` tunnel (tunnel.ink)."""

    def test_tunnel_return_resumes_right_after_the_divert(self):
        """Content after the tunnel-push divert plays, matching the real transcript."""
        state = InkRuntimeState(load_story_root(_load("tunnel.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "You approach the door.\nIt's dark in here.\nYou go inside.\n")
        self.assertTrue(state.done)

    def test_tunnel_stack_is_empty_after_a_clean_return(self):
        """tunnel_stack is pushed to and popped back to empty across the tunnel."""
        state = InkRuntimeState(load_story_root(_load("tunnel.ink.json")))
        state.continue_story()
        self.assertEqual(state.tunnel_stack, [])


class NestedTunnelTests(SimpleTestCase):
    """a tunnel that itself tunnels into another knot before
    returning (nested_tunnel.ink)."""

    def test_nested_tunnel_returns_match_inklecate_transcript(self):
        """Both ->-> returns resolve to their correct, distinct addresses."""
        state = InkRuntimeState(load_story_root(_load("nested_tunnel.ink.json")))
        text = state.continue_story()
        self.assertEqual(
            text,
            "You start the journey.\n"
            "Entering the outer tunnel.\n"
            "Entering the inner tunnel.\n"
            "Leaving the outer tunnel.\n"
            "You finish the journey.\n",
        )
        self.assertTrue(state.done)


class TunnelWithChoiceTests(SimpleTestCase):
    """a tunnel containing choices gathered to a single ->->
    (tunnel_choice.ink)."""

    def test_choosing_inside_a_tunnel_then_returns_to_caller(self):
        """A choice made inside the tunnel is followed, then ->-> returns correctly."""
        state = InkRuntimeState(load_story_root(_load("tunnel_choice.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "You approach a fork.\nWhich way?\n")
        self.assertEqual([c.text for c in state.current_choices], ["Left", "Right"])
        state.choose(0)
        text2 = state.continue_story()
        self.assertEqual(text2, "You go left.\nYou continue on your way.\n")
        self.assertTrue(state.done)


class StarvedOperatorTests(SimpleTestCase):
    """a native-function operator applied with too few eval_stack
    operands must degrade gracefully, not crash.

    A bare "MIN" operator can run with its LIST-typed operand never
    pushed: the compiled form pairs LIST_MIN with a "visit"
    ControlCommand that this engine recognizes but doesn't implement, so
    nothing is on the stack when "MIN" runs, and a naive pop() would
    raise IndexError. starved_operator.json is hand-constructed
    (isolating just the starved-operator shape, not the full LIST/
    visit-index machinery around it) since no compiled .ink source
    directly authors a bare unpaired operator token.
    """

    def test_operator_with_no_operands_does_not_crash(self):
        """A starved operator is silently skipped; content after it still plays."""
        state = InkRuntimeState(load_story_root(_load("starved_operator.json")))
        text = state.continue_story()
        self.assertEqual(text, "Survived.\n")


class TunnelReturnOverrideTests(SimpleTestCase):
    """`->-> elsewhere` — a tunnel returning somewhere other than its caller.

    Documented in WritingWithInk.md, "Advanced: Tunnels can return
    elsewhere". The compiler emits the divert target where a plain `->->`
    emits a void; the engine discarded it, so the story silently returned
    to the caller instead — inkle's own `hurt(x)` example printed "You're
    still alive!" where the reference prints "You lost, buddy.".
    Transcripts captured from the local inklecate build's -p output.
    """

    def test_the_override_target_is_taken_instead_of_the_return_address(self):
        state = InkRuntimeState(load_story_root(_load("tunnel_return_override.json")))
        self.assertEqual(state.continue_story(), "You slip.\nOuch.\nYou lost, buddy.\n")

    def test_the_override_consumes_its_tunnel_frame(self):
        """The outer tunnel's own content is skipped: the inner override
        ate outer's return address, so `elsewhere`'s `->->` goes back to
        main, one level further out."""
        state = InkRuntimeState(load_story_root(_load("tunnel_return_override_nested.json")))
        text = state.continue_story()
        self.assertEqual(text, "Outer start.\nInner start.\nElsewhere reached.\nBack in main.\n")
        self.assertNotIn("Outer after inner.", text)

    def test_the_stacks_unwind_cleanly(self):
        """An override that leaked a frame or an operand would strand the
        next return."""
        state = InkRuntimeState(load_story_root(_load("tunnel_return_override_nested.json")))
        state.continue_story()
        self.assertEqual(state.tunnel_stack, [])
        self.assertEqual(state.eval_stack, [])


class VariableTunnelTests(SimpleTestCase):
    """`-> where ->` — a tunnel whose target is a divert-target variable or
    parameter (variable_tunnel.ink). Transcript captured from the local
    inklecate build's -p output."""

    def test_the_tunnel_runs_its_target_and_returns(self):
        """The tunnel runs its target and returns."""
        state = InkRuntimeState(load_story_root(_load("variable_tunnel.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Before.\nInside.\nMiddle.\nInside.\nAfter.\n")
        self.assertTrue(state.done)

    def test_the_tunnel_stack_is_empty_afterwards(self):
        """The tunnel stack is empty afterwards."""
        state = InkRuntimeState(load_story_root(_load("variable_tunnel.ink.json")))
        state.continue_story()
        self.assertEqual(state.tunnel_stack, [])


class TunnelTempScopeTests(SimpleTestCase):
    """A tunnel has its own temp scope (tunnel_temp_scope.ink,
    tunnel_choice_scope.ink). Transcripts copied from the local inklecate
    build's -p output."""

    def test_a_tunnel_parameter_does_not_overwrite_the_caller_s_temp(self):
        """Covers a parameter, a nested tunnel declaring the same name, and a
        `ref` argument to a temp declared inside the tunnel."""
        state = InkRuntimeState(load_story_root(_load("tunnel_temp_scope.ink.json")))
        self.assertEqual(
            state.continue_story(),
            "Inside t: x is tunnel, y is 2.\n"
            "After t: x is caller.\n"
            "Inside t: x is nested, y is 2.\n"
            "Back in outer: x is outer.\n"
            "After outer: x is caller.\n",
        )

    def test_a_choice_inside_a_tunnel_returns_to_the_caller_s_scope(self):
        """Choosing a choice offered inside the tunnel, then `->->`, reads the caller's own temp."""
        state = InkRuntimeState(load_story_root(_load("tunnel_choice_scope.ink.json")))
        state.continue_story()
        self.assertEqual([choice.text for choice in state.current_choices], ["Answer asked"])
        state.choose(0)
        self.assertEqual(state.continue_story(), "You answer asked.\nAfter ask: x is caller.\n")


class TunnelReturnWithoutTunnelInThreadTests(SimpleTestCase):
    """A thread reaching `->->` with no tunnel to return to
    (thread_tunnel_return_without_tunnel.ink). inklecate stops with a
    runtime error after "Start."; this engine ends the story there, as it
    does for the same statement outside a thread."""

    def test_the_story_ends_instead_of_looping(self):
        """The thread stops; the main flow's own choice is never reached."""
        state = InkRuntimeState(load_story_root(_load("thread_tunnel_return_without_tunnel.ink.json")))
        self.assertEqual(state.continue_story(), "Start.\n")
        self.assertEqual(state.current_choices, [])
        self.assertTrue(state.done)
