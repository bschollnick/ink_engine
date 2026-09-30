"""evaluate_function() (ink_engine.engine).

InkRuntimeState is driven end-to-end against real compiled JSON
(tests/fixtures/evaluate_function.ink), with every expected return
value and text output captured from a direct run against inkle's own
`Ink.Runtime.dll` before any assertion was written, per the plan's
standing validate-against-real-data rule.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    InkPathError,
    InkRuntimeState,
    NotAFunctionError,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _state(**kwargs) -> InkRuntimeState:
    data = _load("evaluate_function.ink.json")
    return InkRuntimeState(load_story_root(data), load_list_defs(data), **kwargs)


class ReturnValueAndArgumentsTests(SimpleTestCase):
    """Arguments in, the `~ return` value out, matching inkle's own `EvaluateFunction`."""

    def test_two_int_arguments_return_their_sum(self):
        """Two int arguments are passed positionally and summed."""
        state = _state()
        result, text_output = state.evaluate_function("add", 2, 3)
        self.assertEqual(result, 5)
        self.assertEqual(text_output, "")

    def test_string_argument_and_concatenation(self):
        """A str argument feeds a `+` string concatenation in the function body."""
        state = _state()
        result, _ = state.evaluate_function("greet", "World")
        self.assertEqual(result, "Hello, World!")


class ComparisonAndStringJoinTests(SimpleTestCase):
    """A function with comparisons and string joins (describe_score),
    matching a real EvaluateFunction run exactly for three inputs."""

    def test_low_branch(self):
        """Below both thresholds takes the `else` branch."""
        state = _state()
        result, _ = state.evaluate_function("describe_score", 3)
        self.assertEqual(result, "score is low (3)")

    def test_medium_branch(self):
        """Between the two thresholds takes the nested `>= 5` branch."""
        state = _state()
        result, _ = state.evaluate_function("describe_score", 7)
        self.assertEqual(result, "score is medium (7)")

    def test_high_branch(self):
        """At or above the outer threshold takes the `>= 10` branch."""
        state = _state()
        result, _ = state.evaluate_function("describe_score", 12)
        self.assertEqual(result, "score is high (12)")


class TextOutputTests(SimpleTestCase):
    """A function's printed text is returned separately, and never joins `output`."""

    def test_printed_text_is_returned_and_not_appended_to_output(self):
        """The function's printed line comes back as text_output, and `output` is untouched."""
        state = _state()
        before_output = state.output.get_text()
        result, text_output = state.evaluate_function("noisy", 5)
        self.assertEqual(result, 10)
        self.assertEqual(text_output, "This function prints text.\n")
        self.assertEqual(state.output.get_text(), before_output)


class ExternalCallTests(SimpleTestCase):
    """An EXTERNAL binding fires during evaluation, and its result feeds the return value."""

    def test_external_binding_is_called_and_its_result_returned(self):
        """A bound Python callable dispatches during evaluation and feeds the return value."""
        state = _state(engine_bindings={"double_it": lambda x: x * 2})
        result, _ = state.evaluate_function("callsExternal", 4)
        self.assertEqual(result, 8)


class LiveStateUnchangedTests(SimpleTestCase):
    """The live state is unchanged afterward: globals, visit counts, turn
    count, output, choices, and the call/tunnel stacks.

    Real inkle mutates the live story's globals permanently for the same
    call (confirmed by running `Ink.Runtime.dll` directly: a
    `~ score = score + 1` function leaves `score` incremented after
    `EvaluateFunction` returns). This engine's `evaluate_function()`
    deliberately does not.
    """

    def test_globals_visit_counts_and_position_are_unaffected(self):
        """Globals, choices, turn count, output and both call/tunnel stacks survive a call unchanged."""
        state = _state()
        state.continue_story()  # stops at "intro"'s choice, having run its `~ visits += 1`
        before_globals = dict(state.globals)
        before_choices = [choice.text for choice in state.current_choices]
        before_turn_count = state.turn_count
        before_output = state.output.get_text()
        before_call_stack = list(state.call_stack)
        before_tunnel_stack = list(state.tunnel_stack)

        result, _ = state.evaluate_function("add", 10, 10)

        self.assertEqual(result, 20)
        self.assertEqual(state.globals, before_globals)
        self.assertEqual([choice.text for choice in state.current_choices], before_choices)
        self.assertEqual(state.turn_count, before_turn_count)
        self.assertEqual(state.output.get_text(), before_output)
        self.assertEqual(state.call_stack, before_call_stack)
        self.assertEqual(state.tunnel_stack, before_tunnel_stack)

    def test_story_still_playable_normally_after_evaluation(self):
        """A successful call does not disturb the story's own ability to continue."""
        state = _state()
        state.continue_story()
        state.evaluate_function("add", 1, 1)
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "This is chapter two.\n")


class RejectionTests(SimpleTestCase):
    """An unknown name and a knot name are both rejected, clearly and
    without disturbing the live state -- unlike inkle's own runtime,
    which corrupts the live story for the knot case (confirmed by
    running `Ink.Runtime.dll` directly: calling `EvaluateFunction` on a
    non-function knot leaves `currentChoices` empty and the story
    unplayable)."""

    def test_unknown_function_name_raises(self):
        """A name resolving to no container raises InkPathError."""
        state = _state()
        with self.assertRaises(InkPathError):
            state.evaluate_function("does_not_exist")

    def test_knot_name_raises_not_a_function(self):
        """A knot ending in `-> END` raises NotAFunctionError, not a generic StoryRuntimeError."""
        state = _state()
        with self.assertRaises(NotAFunctionError):
            state.evaluate_function("chapter_two")

    def test_knot_offering_a_choice_also_raises_not_a_function(self):
        """A knot that offers a choice instead of returning also raises NotAFunctionError."""
        state = _state()
        with self.assertRaises(NotAFunctionError):
            state.evaluate_function("intro")

    def test_story_still_playable_after_a_rejected_knot_name(self):
        """A rejected call leaves the live story exactly as playable as before it."""
        state = _state()
        state.continue_story()
        with self.assertRaises(NotAFunctionError):
            state.evaluate_function("chapter_two")
        self.assertEqual([choice.text for choice in state.current_choices], ["Continue"])
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "This is chapter two.\n")

    def test_argument_of_the_wrong_type_raises_type_error(self):
        """An argument outside choose_path()'s accepted types raises TypeError."""
        state = _state()
        with self.assertRaises(TypeError):
            state.evaluate_function("add", {"not": "scalar"}, 1)
