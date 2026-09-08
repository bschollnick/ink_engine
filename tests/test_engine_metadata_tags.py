"""remaining eval-stack ops + tags (ink_engine.engine).

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


def _run(name: str) -> InkRuntimeState:
    return InkRuntimeState(load_story_root(_load(name)))


class TurnsTests(SimpleTestCase):
    """TURNS() (turns.ink)."""

    def test_turns_is_zero_before_any_choice_and_increments_after(self):
        """TURNS() reads 0 on the opening turn and 1 after one choice,
        matching the real transcript exactly — turn_count starts at -1
        internally (ports currentTurnIndex's own -1 initial value) so
        TURNS() (turn_count+1) reads 0 before any choice is made."""
        state = _run("turns.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Turn is 0.\n")
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "Turn is 1.\n")


class TurnsSinceTests(SimpleTestCase):
    """TURNS_SINCE(-> knot) (turns_since.ink) —
    regression coverage for the count_flags/enteringAtStart gating this
    section added to _record_visit()/_visit_changed_containers_due_to_divert()."""

    def test_turns_since_tracks_the_gather_across_a_loop_back_divert(self):
        """A gather labeled `- (start)` re-entered via its own loop-back
        divert (`-> start` from inside a descendant container) still
        records a fresh at-start visit, matching the real transcript's
        0, 0, 1 sequence exactly — the initial (incorrect) version of this
        gating stopped the ancestor walk at the first already-open
        ancestor unconditionally, which silently prevented `start` from
        ever getting a fresh turn-index visit recorded on re-entry."""
        state = _run("turns_since.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "You are here. Since: 0.\n")
        state.choose(0)  # Wait -> loops back to start
        text = state.continue_story()
        self.assertEqual(text, "You are here. Since: 0.\n")
        state.choose(0)  # Leave
        text = state.continue_story()
        self.assertEqual(text, "Leaving. Since: 1.\n")

    def test_never_visited_target_returns_negative_one(self):
        """A DivertTargetValue that fails to resolve to a real Container
        degrades to -1 (the real engine's own "never visited" sentinel),
        not a crash — unit-tested directly since no real compiled story
        produces an unresolvable TURNS_SINCE target."""
        state = _run("turns_since.ink.json")
        state.eval_stack.append(None)
        state._push_turns_since()  # pylint: disable=protected-access
        self.assertEqual(state.eval_stack[-1], -1)


class ReadCountTests(SimpleTestCase):
    """bare `{knot_name}` display syntax (readcount.ink)
    and the explicit `READ_COUNT(-> knot)` function form
    (readcount_func.ink) — two different compiled shapes for the
    same underlying visit count."""

    def test_bare_display_syntax_matches_real_transcript(self):
        """`{knot_name}` (compiles to a bare {"CNT?": path} literal,
        resolved directly to its visit count at push time) matches the
        real transcript exactly across two visits."""
        state = _run("readcount.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Visited 1 times.\n")
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "Visited 2 times.\n")

    def test_explicit_function_syntax_matches_real_transcript(self):
        """`READ_COUNT(-> knot_name)` (compiles to a DivertTargetValue
        literal followed by a bare "readc" marker) matches the real
        transcript exactly across two visits."""
        state = _run("readcount_func.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Count is 1.\n")
        state.choose(0)
        text = state.continue_story()
        self.assertEqual(text, "Count is 2.\n")


class ChoiceCountTests(SimpleTestCase):
    """CHOICE_COUNT() (choicecount.ink)."""

    def test_choice_count_reflects_choices_generated_so_far_this_turn(self):
        """CHOICE_COUNT() read before any ChoicePoint runs this turn is 0,
        matching the real transcript exactly — it is not a running total
        across turns, and not a forward-looking count of choices about to
        be generated later in the same turn."""
        state = _run("choicecount.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "Choices available: 0\n")


class TagTests(SimpleTestCase):
    """`# tag text` tag collection (tags.ink)."""

    def test_tag_text_is_excluded_from_visible_output_and_collected_separately(self):
        """Two tagged lines produce visible text with the tag content
        entirely excluded, matching the real transcript exactly, with
        both tags collected into current_tags in encounter order."""
        state = _run("tags.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "You step into a clearing.\nSunlight filters through the leaves.\n")
        self.assertEqual(state.current_tags, ["image: cover.jpg", "mood: calm"])

    def test_conditional_tag_content_does_not_leak_a_nop_marker(self):
        """A tag whose text is itself an inline conditional
        (`# image: {cond:a|b}`) must not leak a bare "nop" marker onto the
        end of the resolved tag string.

        Unlike a conditional inside choice-only text (wrapped in ev/../ev,
        see test_engine_choices.py's ControlCommandMarkerTests), the
        compiler does not wrap a conditional inside a tag in ev/../ev at
        all — it runs at main-stream depth while self._in_tag is still
        True, so _handle_tag_command's capture branch must treat the
        branch's trailing "nop" as consumed, not literal tag text
        (otherwise it would produce "image: alt.jpgnop" instead of
        "image: alt.jpg"), the same way _handle_string_capture_command
        does for choice text.
        """
        state = _run("tag_conditional.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "You step into a clearing.\n")
        self.assertEqual(state.current_tags, ["image: alt.jpg"])

    def test_current_tags_is_scoped_to_the_current_turn_not_cumulative(self):
        """current_tags must not accumulate every tag seen since the start
        of the playthrough — only the tags encountered on the turn just
        produced by the most recent continue_story() call.

        continue_story() must reset current_tags at its start the same
        way it resets current_choices -- otherwise any caller that
        iterates state.current_tags each turn, expecting only the
        current turn's tags, would see every image ever tagged stacked
        up by the end of a playthrough. inklecate's own -p transcript
        confirms a second tagged turn's "# tags:" line shows only that
        turn's tag, not both.
        """
        state = _run("tag_per_turn.ink.json")
        state.continue_story()
        self.assertEqual(state.current_tags, ["image: a.jpg"])
        state.choose(0)
        state.continue_story()
        self.assertEqual(state.current_tags, ["image: b.jpg"])

    def test_plain_variable_interpolation_inside_a_tag_does_not_leak_into_output(self):
        """A tag whose text interpolates a plain VAR (`# image: {model}/x.jpg`,
        no conditional) must resolve entirely inside the tag, not leak the
        interpolated value onto the front of the next visible line.

        Unlike the conditional-tag-content case above
        (test_conditional_tag_content_does_not_leak_a_nop_marker), this
        construct DOES run inside an "ev"/"/ev" eval run (a bare `{var}`
        interpolation always does), so it reaches
        _handle_eval_run_command's own EVAL_OUTPUT ("out") branch, which
        must route the popped value into self._tag_buffer when
        self._in_tag is set rather than unconditionally writing it to
        self.output like every other tag-content token already does.
        """
        state = _run("tag_variable_interpolation.ink.json")
        text = state.continue_story()
        self.assertEqual(text, "You step into a clearing.\n")
        self.assertEqual(state.current_tags, ["image: Anna/gypsy0.jpg"])
