"""`InkRuntimeState.choose_path()`: standard Ink's ChoosePathString, a jump
to a knot by name that does not return (choose_path.ink).

Expected text captured from the local inklecate build's -p transcript of
choose_path_reference.ink, which reaches the same targets by ordinary
diverts.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    InkPathError,
    InkRuntimeState,
    load_story_root,
    start_new_story,
)

FIXTURES = FilePath(__file__).parent / "fixtures"
STORY = json.loads((FIXTURES / "choose_path.ink.json").read_text(encoding="utf-8"))
ROOT = load_story_root(STORY)


def _labels(state: InkRuntimeState) -> list[str]:
    return [choice.text for choice in state.current_choices]


class ChoosePathTests(SimpleTestCase):
    """Jumping to a knot, a stitch, or a knot with parameters."""

    def setUp(self):
        """Start the story; it stops inside a tunnel, with a temporary variable set."""
        self.state = start_new_story(ROOT, {})

    def test_the_story_starts_inside_a_tunnel(self):
        """The fixture's own starting point, which the jump must leave behind."""
        self.assertEqual(_labels(self.state), ["Wait"])
        self.assertEqual(len(self.state.tunnel_stack), 1)

    def test_a_knot_plays_from_its_start(self):
        """The text and choices inklecate shows after `-> kitchen`."""
        self.state.choose_path("kitchen")
        self.assertEqual(self.state.continue_story(), "The kitchen.\n")
        self.assertEqual(_labels(self.state), ["Leave"])
        self.assertEqual(self.state.globals["visits"], 1)

    def test_a_stitch_is_addressed_with_a_dot(self):
        """`knot.stitch`, as inklecate shows after `-> kitchen.pantry`."""
        self.state.choose_path("kitchen.pantry")
        self.assertEqual(self.state.continue_story(), "The pantry.\n")

    def test_arguments_reach_a_knot_with_parameters(self):
        """As inklecate shows after `-> greet("Sam")`."""
        self.state.choose_path("greet", "Sam")
        self.assertEqual(self.state.continue_story(), "Hello, Sam.\n")

    def test_it_is_a_turn(self):
        """The turn index advances, as a choice does."""
        before = self.state.turn_count
        self.state.choose_path("kitchen")
        self.assertEqual(self.state.turn_count, before + 1)

    def test_the_call_stack_is_reset(self):
        """No tunnel is left to return to, and the old temporaries are gone."""
        self.state.choose_path("kitchen")
        self.state.continue_story()
        self.assertEqual(self.state.tunnel_stack, [])
        self.assertEqual(self.state.call_stack, [])
        self.assertNotIn("mood", self.state.temps)

    def test_the_current_choices_are_cleared(self):
        """Until the story continues, nothing is offered."""
        self.state.choose_path("kitchen")
        self.assertEqual(self.state.current_choices, [])

    def test_a_pending_interlude_is_discarded(self):
        """A jump leaves the interrupted scene for good."""
        self.state.start_interlude("kitchen.pantry")
        self.state.choose_path("kitchen")
        self.state.continue_story()
        self.assertEqual(self.state.to_dict()["interludes"], [])
        self.assertEqual(_labels(self.state), ["Leave"])

    def test_an_unknown_path_is_refused_before_anything_changes(self):
        """InkPathError, with the state as it was."""
        before = self.state.to_dict()
        with self.assertRaises(InkPathError):
            self.state.choose_path("no_such_knot")
        self.assertEqual(self.state.to_dict(), before)

    def test_arrival_counts_as_a_visit(self):
        """A `{knot}` read count straight after the jump, as inklecate shows after `-> counted`."""
        self.state.choose_path("counted")
        self.assertEqual(self.state.continue_story(), "Counted 1 times.\n")

    def test_the_previous_pointer_is_cleared(self):
        """`ForceEnd()` nulls the previous pointer before the jump."""
        self.state.choose_path("kitchen")
        self.assertIsNone(self.state.previous_pointer)

    def test_an_argument_of_another_type_is_refused_before_anything_changes(self):
        """Only int, float, string, bool and LIST values can be passed, as inkle's runtime accepts."""
        before = self.state.to_dict()
        for argument in (None, ["Sam"], {"name": "Sam"}, object()):
            with self.subTest(argument=argument), self.assertRaises(TypeError):
                self.state.choose_path("greet", argument)
        self.assertEqual(self.state.to_dict(), before)

    def test_every_accepted_type_reaches_the_knot(self):
        """int, float, bool and string print as Ink prints them."""
        for argument, printed in ((3, "3"), (1.5, "1.5"), (True, "true"), ("Sam", "Sam")):
            with self.subTest(argument=argument):
                state = start_new_story(ROOT, {})
                state.choose_path("greet", argument)
                self.assertEqual(state.continue_story(), f"Hello, {printed}.\n")
