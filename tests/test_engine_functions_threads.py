"""functions + threads (ink_engine.engine).

InkRuntimeState is driven end-to-end against real compiled JSON
(tests/fixtures/*.ink), with every expected transcript captured
from the local inklecate build's -p play-mode transcript before any
assertion was written (per the plan's standing validate-against-real-data
rule).
"""

from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import InkRuntimeState, load_list_defs, load_story_root

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


class FunctionEmittedTextTests(SimpleTestCase):
    """A function that prints, called from inside a line's `{...}`.

    The body's text is output, not an operand, even though it arrives at
    eval-run depth like one — the open call frame is what separates them.
    Its trailing newline is dropped as the frame pops (C#'s
    functionTrimIndex) so the caller's line survives the call, while a
    newline *inside* the body is kept. Both halves were wrong: the text
    was dropped entirely, printing "Before after.". Transcript captured
    from the local inklecate build's -p output.
    """

    def setUp(self):
        state = InkRuntimeState(load_story_root(_load("function_emits_text.json")))
        self.text = state.continue_story()

    def test_the_body_text_reaches_the_output(self):
        self.assertIn("MIDDLE", self.text)

    def test_the_call_does_not_break_the_caller_s_line(self):
        self.assertIn("Before MIDDLE after.", self.text)

    def test_a_newline_inside_the_body_is_kept(self):
        """Only the trailing one is trimmed."""
        self.assertIn("Line two A\nB end.", self.text)

    def test_the_whole_transcript_matches(self):
        self.assertEqual(self.text, "Before MIDDLE after.\nLine two A\nB end.\n")


def _play(name: str) -> InkRuntimeState:
    """Load a fixture with its LIST definitions and run its first turn."""
    data = _load(name)
    state = InkRuntimeState(load_story_root(data), load_list_defs(data))
    state.continue_story()
    return state


#: fixture: (choice labels, text printed after choosing each label, in order)
THREAD_TRANSCRIPTS: dict[str, tuple[list[str], list[str]]] = {
    # A thread that recursively threads itself, one temp per level.
    "thread_temps.ink.json": (
        [
            "Pick zeta",
            "Pick epsilon",
            "Pick delta",
            "Pick gamma",
            "Pick beta",
            "Pick alpha",
            "Leave",
        ],
        [
            "You pick zeta.",
            "You pick epsilon.",
            "You pick delta.",
            "You pick gamma.",
            "You pick beta.",
            "You pick alpha.",
            "",
        ],
    ),
    # Threads inside threads, every level declaring the same temp name.
    "thread_nested_temps.ink.json": (
        [
            "Inner A1 inner-A1",
            "Inner A2 inner-A2",
            "Outer A outer-A",
            "Inner B1 inner-B1",
            "Inner B2 inner-B2",
            "Outer B outer-B",
            "Main main",
        ],
        [
            "Inner chose A1, x is inner-A1.",
            "Inner chose A2, x is inner-A2.",
            "Outer chose A, x is outer-A.",
            "Inner chose B1, x is inner-B1.",
            "Inner chose B2, x is inner-B2.",
            "Outer chose B, x is outer-B.",
            "Main chose, x is main.",
        ],
    ),
    # A choice that diverts to a knot, passing the thread's argument
    # (directly, and through a divert-target parameter).
    "thread_divert_argument.ink.json": (
        ["Go left", "Go right", "Walk north", "Walk south"],
        ["You went left.", "You went right.", "You walked north.", "You walked south."],
    ),
    # A choice generated inside a tunnel inside a thread: `->->` must
    # return into that thread, with its own argument.
    "thread_tunnel.ink.json": (
        ["Chat with Ann", "Chat with Bo", "Stay"],
        ["You chat with Ann.\nAfter chatting with Ann.", "You chat with Bo.\nAfter chatting with Bo.", "You stay."],
    ),
}


class ThreadChoiceKeepsItsOwnThreadTests(SimpleTestCase):
    """Each choice generated in a thread keeps that thread's temps,
    arguments and tunnel returns, as `choice.threadAtGeneration` does in
    inkle's runtime. Transcripts copied from the local inklecate build's
    `-p` output, one run per choice.
    """

    def test_each_choice_label_uses_its_own_thread(self):
        """A choice's label reads the temps of the thread that generated it."""
        for name, (labels, _outcomes) in THREAD_TRANSCRIPTS.items():
            with self.subTest(fixture=name):
                self.assertEqual([choice.text for choice in _play(name).current_choices], labels)

    def test_each_choice_continues_in_its_own_thread(self):
        """Choosing a choice resumes with its generating thread's temps, arguments and tunnel returns."""
        for name, (_labels, outcomes) in THREAD_TRANSCRIPTS.items():
            for index, expected in enumerate(outcomes):
                with self.subTest(fixture=name, choice=index + 1):
                    state = _play(name)
                    state.choose(index)
                    self.assertEqual(state.continue_story().rstrip("\n"), expected)

    def test_a_thread_does_not_change_the_flow_that_started_it(self):
        """The thread's temps and its open tunnel are its own: the main
        flow's `x` is unchanged and no tunnel return leaks into it."""
        state = _play("thread_nested_temps.ink.json")
        self.assertEqual(state.temps, {"x": "main"})
        state = _play("thread_tunnel.ink.json")
        self.assertEqual(state.tunnel_stack, [])


#: fixture: the text inklecate prints before the story ends
END_CASES: dict[str, str] = {
    # A thread ends after an earlier thread offered a choice.
    "end_in_thread.ink.json": "Start.\nEnder text.\n",
    # The same, inside a tunnel.
    "end_in_thread_in_tunnel.ink.json": "Start.\nIn tunnel.\nEnder text.\n",
    # A thread nested in a thread ends.
    "end_in_nested_thread.ink.json": "Start.\nEnder text.\n",
    # The main flow ends after a thread offered a choice.
    "end_after_thread_choices.ink.json": "Start.\nMain text.\n",
}


class EndInsideAThreadTests(SimpleTestCase):
    """`-> END` ends the whole story, with no choices, wherever it is reached.

    Source: inkle's vendored runtime format (ink_JSON_runtime_format.md,
    "end": ends the story flow, closes all threads, unwinds the call stack
    and removes the choices already created). There is no C# in the
    snapshot, so the expected text is inklecate's `-p` output for each
    fixture, copied here: every case prints the text below and then offers
    no choices.
    """

    def test_the_story_ends_with_no_choices(self):
        """Nothing after END runs, and the choices already offered are removed."""
        for name, text in END_CASES.items():
            with self.subTest(fixture=name):
                state = InkRuntimeState(load_story_root(_load(name)))
                self.assertEqual(state.continue_story(), text)
                self.assertEqual(state.current_choices, [])
                self.assertTrue(state.done)

    def test_the_tunnel_is_unwound(self):
        """No tunnel frame is left to return to after END inside a tunnel's thread."""
        state = InkRuntimeState(load_story_root(_load("end_in_thread_in_tunnel.ink.json")))
        state.continue_story()
        self.assertEqual((state.tunnel_stack, state.call_stack), ([], []))


def _timed_turn(fixture: str, knot: str, results: multiprocessing.Queue) -> None:
    """Run one turn of `fixture` (from `knot`, if given) and report its seconds and choice labels."""
    data = _load(fixture)
    state = InkRuntimeState(load_story_root(data), load_list_defs(data))
    if knot:
        state.choose_path(knot)
    start = time.perf_counter()
    state.continue_story()
    results.put((time.perf_counter() - start, [choice.text for choice in state.current_choices]))


class RecursiveThreadReturningFromATunnelTests(SimpleTestCase):
    """A thread that recurses over a LIST and ends with `->->`
    (thread_recursive_tunnel_return.ink), the pattern a game uses to offer
    one choice per person present. Entered without a tunnel, the `->->` has
    nothing to return to, and a thread that reached it used to loop forever.
    Choice labels copied from the local inklecate build's `-p` output."""

    #: Seconds. A turn of this story takes about a millisecond.
    BOUND = 10.0

    def _run(self, knot: str) -> tuple[float, list[str]]:
        """Run the turn in a child process, so a turn that never returns fails instead of hanging the suite."""
        results: multiprocessing.Queue = multiprocessing.Queue()
        child = multiprocessing.Process(target=_timed_turn, args=("thread_recursive_tunnel_return.ink.json", knot, results))
        child.start()
        child.join(timeout=self.BOUND * 3)
        if child.is_alive():
            child.terminate()
            child.join()
            self.fail(f"the turn did not return within {self.BOUND * 3} seconds")
        return results.get(timeout=self.BOUND)

    def test_entered_as_a_tunnel_it_matches_inklecate_quickly(self):
        """Tunnelled into from the story's start, as inklecate plays it."""
        elapsed, choices = self._run("")
        self.assertLess(elapsed, self.BOUND)
        self.assertEqual(choices, ["Leave", "Pick epsilon", "Pick delta", "Pick gamma", "Pick beta", "Pick alpha"])

    def test_entered_without_a_tunnel_it_returns(self):
        """`choose_path()` straight into the recursion: inklecate reports a
        runtime error at the `->->`; this engine ends the story there."""
        elapsed, _choices = self._run("offers")
        self.assertLess(elapsed, self.BOUND)
