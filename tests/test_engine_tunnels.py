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
