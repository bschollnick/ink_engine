"""`ref` parameters and the list traversal built on them (ink_engine.engine).

Every expected transcript here was captured from the local inklecate
build's -p play-mode output before any assertion was written.

The story in `list_recursion_and_intersection.ink` is the `pop()`/
`reach()` pair from inkle's own LIST documentation. It exercises four
behaviours that each failed silently -- wrong output or a non-terminating
loop, never an error -- until they were implemented together:

- a `ref` parameter writing back to the caller's variable
- the intersection operator, which the compiler emits as "L^"
- `not` applied to a LIST, the guard that ends the recursion
- a whole-valued float printing without its ".0"
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    InkRuntimeState,
    ListValue,
    apply_native_function,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"

#: Enough to finish either fixture; both end without offering a choice.
MAXIMUM_STEPS = 500


def _run(name: str) -> str:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)
    state = InkRuntimeState(load_story_root(data), load_list_defs(data))
    text = []
    for _ in range(MAXIMUM_STEPS):
        step = state.continue_story()
        if step:
            text.append(step)
        if state.done or state.current_choices:
            break
    else:
        raise AssertionError(f"{name} did not finish within {MAXIMUM_STEPS} steps")
    return "".join(text)


class ReferenceParameterTests(SimpleTestCase):
    """A `ref` parameter writes to the caller's variable (ref_parameters.ink)."""

    def test_mutations_reach_the_caller_and_match_transcript(self):
        """Both an int and a LIST mutate in the caller's scope: without
        that, `bump` leaves score at 10 and `pop` returns 0."""
        self.assertEqual(
            _run("ref_parameters.ink.json"),
            "Before: 10\nAfter: 15\nPopped: apple\nSack now: pear\n",
        )


class OutermostTempReferenceTests(SimpleTestCase):
    """A `ref` to a temp that no call frame owns (ref_outermost_temp.ink).

    The pointed-to variable lives in the outermost temp scope rather than
    in a frame's, which is a different lookup from the one a function
    calling another function exercises: resolving it as a global instead
    reads 0, and the filtered-out members come back.
    """

    def test_a_filter_function_prunes_the_callers_list(self):
        self.assertEqual(
            _run("ref_outermost_temp.ink.json"),
            "Remaining: v2, v4\nCount: 2\n",
        )


class ListRecursionTests(SimpleTestCase):
    """Upstream's own pop()/reach() traversal (list_recursion_and_intersection.ink)."""

    def test_recursive_traversal_and_operators_match_transcript(self):
        """The whole documented example, including the intersection
        operator and the POW value printing as "9" rather than "9.0"."""
        self.assertEqual(
            _run("list_recursion_and_intersection.ink.json"),
            "Overlap: self_belief\n"
            "SubsetAll: true\n"
            "SubsetPartial: false\n"
            "NotEmpty: 1\n"
            "NotFull: 0\n"
            "POW: 9\n"
            "Reached: a1, a2, a3, b1, b2\n",
        )


class ListNotOperatorTests(SimpleTestCase):
    """`not` on a LIST operand, which the recursion's exit test depends on."""

    def test_not_reports_emptiness_as_an_int(self):
        """Real Ink prints 1 for an empty list and 0 for a non-empty one."""
        empty = ListValue(entries=(), origin_names=("Chain",))
        full = ListValue(entries=((("Chain", "a1"), 1),), origin_names=("Chain",))
        self.assertEqual(apply_native_function("!", [empty]), 1)
        self.assertEqual(apply_native_function("!", [full]), 0)


class IntersectionOperatorTests(SimpleTestCase):
    """The compiler emits intersection as "L^"; a bare "^" marks literal text."""

    def test_both_spellings_intersect(self):
        """Either name reaches the same set-intersection operation."""
        first = ListValue(entries=((("V", "a"), 1), (("V", "b"), 2)), origin_names=("V",))
        second = ListValue(entries=((("V", "b"), 2), (("V", "c"), 3)), origin_names=("V",))
        expected = ListValue(entries=((("V", "b"), 2),), origin_names=("V",))
        self.assertEqual(apply_native_function("L^", [first, second]), expected)
        self.assertEqual(apply_native_function("^", [first, second]), expected)
