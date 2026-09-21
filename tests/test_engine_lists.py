"""LISTs (ink_engine.engine).

InkRuntimeState is driven end-to-end against real compiled JSON
(tests/fixtures/*.ink), with every expected transcript captured
from the local inklecate build's -p play-mode transcript before any
assertion was written (per the plan's standing validate-against-real-data
rule). apply_native_function() is additionally unit-tested directly for
the LIST operator family the fixtures don't each need their own story for.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    InkPathError,
    InkRuntimeState,
    ListValue,
    apply_native_function,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _run(name: str) -> InkRuntimeState:
    data = _load(name)
    state = InkRuntimeState(load_story_root(data), load_list_defs(data))
    return state


class BasicListValueTests(SimpleTestCase):
    """VAR initialized to a single-item LIST value, `+=`/`-=`
    reassignment, and `?` has-item conditional text (basic.ink)."""

    def test_reassignment_and_has_item_conditions_match_transcript(self):
        """A LIST var's display form, `+=` growth, and `?`/else-branch
        conditional text all match the real transcript exactly."""
        state = _run("basic.ink.json")
        text = state.continue_story()
        self.assertEqual(
            text,
            "You have Coins.\nNow you have Coins, Notes.\nYou still have coins.\nCoins are gone.\n",
        )

    def test_item_names_are_pre_registered_as_single_item_globals(self):
        """A bare list item name (e.g. "Coins") is readable as its own
        single-item LIST global before any story content runs."""
        state = _run("basic.ink.json")
        self.assertEqual(state.globals["Coins"], ListValue.single("Wallet", "Coins", 1))


class ListUnaryOperatorTests(SimpleTestCase):
    """LIST_MIN/LIST_MAX/LIST_ALL/LIST_COUNT/LIST_VALUE/
    LIST_INVERT and LIST comparisons (ops.ink)."""

    def test_all_unary_ops_and_one_comparison_match_transcript(self):
        """Every unary LIST_* op and the == comparison match the real
        transcript exactly; the false > comparison produces no text."""
        state = _run("ops.ink.json")
        text = state.continue_story()
        self.assertEqual(
            text,
            "Count: 2\nMin: Coins\nMax: Notes\nAll: Coins, Notes, Cards\n" "Value: 3\nInverted: Cards\nEqual!\n",
        )


class SwitchOnValueTests(SimpleTestCase):
    """`{x: - 1: ... - 4: ... - else: ...}` switch-on-value,
    which depends on the DUPLICATE_TOP ("du") control command
    (switch.ink)."""

    def test_matching_branch_is_selected(self):
        """The branch matching the switch value runs, matching the real
        transcript exactly."""
        state = _run("switch.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "four\n")


class RecursiveBinaryStorageTests(SimpleTestCase):
    """a recursive function combining a switch-on-value block
    with LIST-adjacent bit-flag storage.

    "du" (DUPLICATE_TOP) can be reached at eval-run depth > 0, not just
    depth 0, when the switch container sits inside an outer, still-open
    eval bracket in real compiled output — it must be handled in
    _handle_string_content's main-stream branch, not only there, or the
    duplicate is never pushed and every branch after the first tests
    against nothing. The switch's own trailing bare "pop" is also
    reachable at eval-run depth > 0 and must be handled outside
    _handle_eval_run_command's void-function-call form too, or a stale
    duplicated value is left on eval_stack whenever no switch branch
    matches, corrupting the next eval run to use the stack.
    """

    def test_correct_bits_are_set_across_recursive_calls(self):
        """10 = 8 + 2, so only bit2 and bit8 end up true, matching the
        real transcript exactly."""
        state = _run("binstore.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Bits: false true false true\n")


class BoolDisplayTests(SimpleTestCase):
    """{x} for a bool VAR must display "true"/"false" (matching real
    inklecate), not Python's capitalized str(bool)."""

    def test_bool_displays_lowercase(self):
        """A bool VAR interpolated into text matches real Ink's lowercase
        "true", not Python's "True"."""
        state = _run("bool.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "true\n")


class ListNativeFunctionTests(SimpleTestCase):
    """apply_native_function() LIST operator coverage,
    unit-tested directly (ported from ink-engine-runtime/InkList.cs's
    AddListBinaryOp/AddListUnaryOp call sites)."""

    def setUp(self):
        self.wallet_defs = {"Wallet": {"Coins": 1, "Notes": 2, "Cards": 3}}
        self.coins = ListValue.single("Wallet", "Coins", 1)
        self.notes = ListValue.single("Wallet", "Notes", 2)
        self.coins_notes = ListValue(entries=((("Wallet", "Coins"), 1), (("Wallet", "Notes"), 2)), origin_names=("Wallet",))

    def test_union_add(self):
        """+ merges two LIST values (InkList.Union)."""
        result = apply_native_function("+", [self.coins, self.notes])
        self.assertEqual(result, self.coins_notes)

    def test_without_subtract(self):
        """- removes items present in the second operand (InkList.Without)."""
        result = apply_native_function("-", [self.coins_notes, self.coins])
        self.assertEqual(result, self.notes)

    def test_intersect(self):
        """^ returns only items shared between both operands (InkList.Intersect)."""
        result = apply_native_function("^", [self.coins_notes, self.coins])
        self.assertEqual(result, self.coins)

    def test_has_and_hasnt(self):
        """? and !? test whether the left operand contains every item of the right."""
        self.assertIs(apply_native_function("?", [self.coins_notes, self.coins]), True)
        self.assertIs(apply_native_function("!?", [self.coins_notes, self.coins]), False)
        self.assertIs(apply_native_function("?", [self.coins, self.notes]), False)

    def test_equality(self):
        """== / != compare LIST values by their full item set."""
        self.assertIs(apply_native_function("==", [self.coins, ListValue.single("Wallet", "Coins", 1)]), True)
        self.assertIs(apply_native_function("!=", [self.coins, self.notes]), True)

    def test_magnitude_comparisons(self):
        """>/</>=/<= compare LIST values by min/max item value, per InkList.GreaterThan/LessThan."""
        self.assertIs(apply_native_function(">", [self.notes, self.coins]), True)
        self.assertIs(apply_native_function("<", [self.coins, self.notes]), True)
        self.assertIs(apply_native_function(">=", [self.notes, self.coins]), True)
        self.assertIs(apply_native_function("<=", [self.coins, self.notes]), True)

    def test_empty_operand_comparisons_are_trivially_decided(self):
        """An empty LIST operand short-circuits every comparison by count
        alone, before any item value is examined."""
        empty = ListValue()
        self.assertIs(apply_native_function(">", [self.coins, empty]), True)
        self.assertIs(apply_native_function(">", [empty, self.coins]), False)
        self.assertIs(apply_native_function("<", [empty, self.coins]), True)

    def test_list_min_max_count_value(self):
        """LIST_MIN/LIST_MAX return single-item ListValues; LIST_COUNT/
        LIST_VALUE return plain ints."""
        self.assertEqual(apply_native_function("LIST_MIN", [self.coins_notes]), self.coins)
        self.assertEqual(apply_native_function("LIST_MAX", [self.coins_notes]), self.notes)
        self.assertEqual(apply_native_function("LIST_COUNT", [self.coins_notes]), 2)
        self.assertEqual(apply_native_function("LIST_VALUE", [self.coins]), 1)

    def test_list_all_and_invert(self):
        """LIST_ALL enumerates every item of the value's origin list(s);
        LIST_INVERT enumerates every item the value does NOT hold."""
        all_items = apply_native_function("LIST_ALL", [self.coins], self.wallet_defs)
        self.assertEqual(all_items.as_dict(), {("Wallet", "Coins"): 1, ("Wallet", "Notes"): 2, ("Wallet", "Cards"): 3})
        inverted = apply_native_function("LIST_INVERT", [self.coins], self.wallet_defs)
        self.assertEqual(inverted.as_dict(), {("Wallet", "Notes"): 2, ("Wallet", "Cards"): 3})

    def test_bool_operand_with_list_operand_raises(self):
        """A non-LIST operand paired with a LIST operand has no defined
        operation."""
        with self.assertRaises(InkPathError):
            apply_native_function(">", [self.coins, 5])


class ListRangeAndListFromIntTests(SimpleTestCase):
    """LIST_RANGE(list, min, max) and the LIST(n) int-to-item conversion.

    Both compile to bare ControlCommand markers ("range"/"listInt")
    rather than NativeFunctionCalls. Both were listed as recognized
    markers with no handler, so each silently consumed nothing and left
    its operands on the eval stack for the next pop to mistake for a
    result -- LIST_RANGE(LIST_ALL(Nums), two, four) returned `four`.
    Transcript captured from the local inklecate build's -p output.
    """

    def setUp(self):
        self.text = _run("list_range.json").continue_story()

    def test_integer_bounds_select_the_documented_slice(self):
        """WritingWithInk.md's own example: primes between 10 and 20."""
        self.assertIn("Doc: p11, p13, p17, p19", self.text)

    def test_bounds_outside_the_list_clamp_rather_than_erroring(self):
        self.assertIn("Clamp: one, two, three, four, five", self.text)

    def test_a_range_matching_nothing_yields_an_empty_list(self):
        self.assertIn("Empty:\n", self.text)

    def test_list_item_bounds_work_as_well_as_integers(self):
        """Both bound forms are valid; an item contributes its own value."""
        self.assertIn("MinItem: two, three, four", self.text)

    def test_list_from_int_returns_the_item_holding_that_value(self):
        self.assertIn("FromInt: three", self.text)

    def test_list_from_int_yields_an_empty_list_when_no_item_matches(self):
        self.assertIn("FromIntBad:\n", self.text)

    def test_no_operands_are_left_on_the_eval_stack(self):
        """The defect's signature: operands orphaned by a consumed-but-
        unhandled command are read as the next result."""
        state = _run("list_range.json")
        state.continue_story()
        self.assertEqual(state.eval_stack, [])
