"""One `InkRuntimeState` per playthrough (ink_engine.engine).

`InkRuntimeState` holds a whole playthrough -- position, call stack,
variables -- and mutates it in place with no internal locking. Two
threads driving one instance corrupt it; a compiled story root is
read-only and may be shared by any number of states.

Overlapping turns on one state raise `ConcurrentPlaythroughError`
instead of corrupting it. Handing a state between threads sequentially
is allowed: the guard detects an overlapping turn, not an owning thread,
because thread ids are recycled and a worker pool is a legitimate caller.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    ConcurrentPlaythroughError,
    InkRuntimeState,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"

#: The story's own CONST TOTAL -- a finished playthrough ends here.
EXPECTED_TURNS = 400

#: Threads per trial, and trials for the contention test. Four threads
#: on a 400-turn story overlapped on every trial in development.
THREAD_COUNT = 4
CONTENTION_TRIALS = 5


def _story() -> tuple[object, dict]:
    """Return the compiled counter story's root and LIST tables."""
    compiled = json.loads((FIXTURES / "counter_loop.ink.json").read_text())
    return load_story_root(compiled), load_list_defs(compiled)


def _play_to_end(state: InkRuntimeState) -> None:
    """Run one state until the story stops."""
    while state.continue_story():
        pass


class SessionIsolation(SimpleTestCase):
    """A state per thread is safe; the story root is safe to share."""

    def test_one_state_per_thread_is_unaffected_by_the_others(self) -> None:
        """Four concurrent playthroughs each finish with a correct count."""
        root, list_defs = _story()
        counts: list[int] = []
        failures: list[str] = []

        def play() -> None:
            try:
                state = InkRuntimeState(root, list_defs)
                _play_to_end(state)
                counts.append(state.globals["turns"])
            except Exception as error:  # pylint: disable=broad-exception-caught
                failures.append(f"{type(error).__name__}: {error}")

        threads = [threading.Thread(target=play) for _ in range(THREAD_COUNT)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [])
        self.assertEqual(counts, [EXPECTED_TURNS] * THREAD_COUNT)

    def test_one_story_root_serves_many_states(self) -> None:
        """Sharing the read-only root does not couple two playthroughs.

        The counter story offers no choices, so one `continue_story()`
        runs it to `-> END`; the second state must still start at zero.
        """
        root, list_defs = _story()
        first, second = InkRuntimeState(root, list_defs), InkRuntimeState(root, list_defs)

        _play_to_end(first)
        self.assertEqual(first.globals["turns"], EXPECTED_TURNS)
        self.assertEqual(second.globals["turns"], 0, "a second state saw the first's progress")

        _play_to_end(second)
        self.assertEqual(second.globals["turns"], EXPECTED_TURNS)
        self.assertEqual(first.globals["turns"], EXPECTED_TURNS, "one state's globals reached another")


class TurnGuardRelease(SimpleTestCase):
    """The guard releases the state however a turn ends."""

    def test_a_failed_turn_leaves_the_state_usable(self) -> None:
        """An exception mid-turn releases the guard rather than wedging it."""
        root, list_defs = _story()
        state = InkRuntimeState(root, list_defs)

        with self.assertRaises(IndexError):
            state.choose(99)

        self.assertIsNone(state._running_thread)  # pylint: disable=protected-access
        self.assertEqual(state._turn_depth, 0)  # pylint: disable=protected-access

        _play_to_end(state)
        self.assertEqual(state.globals["turns"], EXPECTED_TURNS)

    def test_a_state_may_be_handed_between_threads_in_turn(self) -> None:
        """Sequential use from different threads is allowed, not refused."""
        root, list_defs = _story()
        state = InkRuntimeState(root, list_defs)
        first_done = threading.Event()
        failures: list[str] = []

        def claim_first() -> None:
            state.continue_story()
            first_done.set()

        def follow_after() -> None:
            first_done.wait(timeout=5)
            try:
                state.continue_story()
            except Exception as error:  # pylint: disable=broad-exception-caught
                failures.append(f"{type(error).__name__}: {error}")

        # Both threads stay alive together, so their ids cannot be recycled
        # into each other -- the case an owner-based check gets wrong.
        threads = [threading.Thread(target=claim_first), threading.Thread(target=follow_after)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [], "a sequential handoff was refused as if it were concurrent")


class ConcurrentUseIsRefused(SimpleTestCase):
    """Overlapping turns raise rather than corrupting the playthrough."""

    def test_a_second_thread_is_refused_and_the_first_finishes(self) -> None:
        """Intruders raise; the thread that got there first is unharmed.

        Without the guard this same loop corrupted the state: in
        development it raised `IndexError: pop from empty list` from the
        call stack on two trials in five, and on the others silently left
        the counter at 0 or 1 instead of its full count.
        """
        root, list_defs = _story()
        original_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        refusals = 0
        try:
            for _ in range(CONTENTION_TRIALS):
                state = InkRuntimeState(root, list_defs)
                raised: list[str] = []

                def drive(shared: InkRuntimeState = state, errors: list[str] = raised) -> None:
                    try:
                        _play_to_end(shared)
                    except ConcurrentPlaythroughError:
                        errors.append("refused")
                    except Exception as error:  # pylint: disable=broad-exception-caught
                        errors.append(f"{type(error).__name__}: {error}")  # noqa: B023  (`error` is the except binding, not the loop variable)

                threads = [threading.Thread(target=drive) for _ in range(THREAD_COUNT)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(
                    [error for error in raised if error != "refused"],
                    [],
                    "a shared state raised something other than ConcurrentPlaythroughError",
                )
                self.assertEqual(
                    state.globals["turns"],
                    EXPECTED_TURNS,
                    "the thread holding the state did not finish its playthrough intact",
                )
                refusals += len(raised)
        finally:
            sys.setswitchinterval(original_interval)

        if not refusals:
            self.skipTest(f"no thread overlapped in {CONTENTION_TRIALS} trials; the guard was never reached")
