"""functions + threads (ink_engine.engine).

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


class FunctionCallTests(SimpleTestCase):
    """`{func(x)}` inline function calls with return values
    (function.ink)."""

    def test_two_function_calls_match_inklecate_transcript(self):
        """Two independent {func(...)} calls, each returning a value used
        in interpolated text, match the real transcript exactly."""
        state = InkRuntimeState(load_story_root(_load("function.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "You have 7 points now.\nThe double of 5 is 10.\n")

    def test_function_side_effect_updates_globals(self):
        """A function's own `~ score = ...` reassignment is visible in
        globals after the call, matching real Ink's shared VariablesState."""
        state = InkRuntimeState(load_story_root(_load("function.ink.json")))
        state.continue_story()
        self.assertEqual(state.globals["score"], 7)

    def test_call_stack_is_empty_after_both_calls_return(self):
        """call_stack is pushed to and popped back to empty across each call."""
        state = InkRuntimeState(load_story_root(_load("function.ink.json")))
        state.continue_story()
        self.assertEqual(state.call_stack, [])


class VoidFunctionCallTests(SimpleTestCase):
    """`~ func()` void-context call with no `~ return`
    (void_func.ink)."""

    def test_void_call_runs_its_side_effect_and_matches_transcript(self):
        """A void function with no explicit return still runs to
        completion and its side effect (score += 1) is visible afterward."""
        state = InkRuntimeState(load_story_root(_load("void_func.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Score is 1.\n")

    def test_void_return_value_is_consumed_not_leaked_onto_eval_stack(self):
        """The compiler's bare "pop" after a void call must leave
        eval_stack clean, not leaking a stray implicit-Void placeholder."""
        state = InkRuntimeState(load_story_root(_load("void_func.ink.json")))
        state.continue_story()
        self.assertEqual(state.eval_stack, [])


class NestedFunctionCallTests(SimpleTestCase):
    """a function calling another function, each with its own
    `temp=` parameter scope (nested_func.ink)."""

    def test_nested_call_result_matches_inklecate_transcript(self):
        """outer(10) calls inner(10), and the combined result (10*2+1=21)
        matches the real transcript exactly."""
        state = InkRuntimeState(load_story_root(_load("nested_func.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "21\n")


class RecursiveFunctionCallTests(SimpleTestCase):
    """a function calling itself compiles its `{"f()": path}` target
    as a *relative* path (e.g. ".^.^.^" for direct recursion), not
    always the absolute top-level name a naive `_call_function` might
    assume — `_call_function` must resolve target paths via
    `_resolve_target`, the same way Divert/ChoicePoint targets already
    are (recursive_function.ink)."""

    def test_recursive_self_call_reaches_the_expected_depth(self):
        """Three levels of self-recursion each increment count, matching
        the real transcript exactly (no LIST/listDefs involved)."""
        state = InkRuntimeState(load_story_root(_load("recursive_function.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Count is 3.\n")


class SingleTopLevelThreadTests(SimpleTestCase):
    """a `<- knot` thread with no choices, weaving text inline
    before the main flow continues (thread.ink)."""

    def test_thread_text_is_woven_in_before_main_flow_continues(self):
        """The threaded knot's text appears between the main flow's own
        lines, matching the real transcript exactly."""
        state = InkRuntimeState(load_story_root(_load("thread.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "You are at a crossroads.\nA distant bell tolls.\n")
        self.assertTrue(state.done)


class ThreadedChoiceTests(SimpleTestCase):
    """a thread that itself offers a choice, woven into the
    main flow's own choice list (thread_choice.ink)."""

    def test_threaded_choice_appears_before_main_flow_choices(self):
        """Real Ink runs a thread immediately when reached, so its
        choices are collected before the main flow's own."""
        state = InkRuntimeState(load_story_root(_load("thread_choice.ink.json")))
        state.continue_story()
        self.assertEqual([c.text for c in state.current_choices], ["Ring the bell", "Go left", "Go right"])

    def test_choosing_the_threaded_choice_resumes_only_within_the_thread(self):
        """Picking the thread's own choice abandons the main flow entirely,
        matching real Ink's per-thread resumption."""
        state = InkRuntimeState(load_story_root(_load("thread_choice.ink.json")))
        state.continue_story()
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "A distant bell tolls.\n")

    def test_choosing_a_main_flow_choice_still_works_normally(self):
        """A non-threaded choice in the same turn is unaffected by the
        thread that ran alongside it."""
        state = InkRuntimeState(load_story_root(_load("thread_choice.ink.json")))
        state.continue_story()
        state.choose(1)
        text = state.continue_story()
        self.assertEqual(text, "You went left.\n")


class MultipleThreadsTests(SimpleTestCase):
    """two threads started in a row before the main flow's own
    choice (thread_multi.ink)."""

    def test_choice_order_matches_thread_start_order_then_main_flow(self):
        """Choices appear in the order their threads were started
        (east before west), with the main flow's own choice last —
        matching the real transcript's numbered choice order exactly."""
        state = InkRuntimeState(load_story_root(_load("thread_multi.ink.json")))
        state.continue_story()
        self.assertEqual([c.text for c in state.current_choices], ["Go east", "Go west", "Wait here"])

    def test_choosing_the_second_thread_matches_transcript(self):
        """Picking the second-started thread's choice resumes correctly,
        independent of the first thread ever having run."""
        state = InkRuntimeState(load_story_root(_load("thread_multi.ink.json")))
        state.continue_story()
        state.choose(1)
        text = state.continue_story()
        self.assertEqual(text, "Sunset awaits.\n")
