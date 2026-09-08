"""diverts + basic [choice-only] choices (ink_engine.engine).

InkRuntimeState is tested end-to-end against real compiled JSON
(tests/fixtures/choices.ink / gather_loop.ink), driven
turn-by-turn exactly like a player would (continue_story()/choose()), with
every expected transcript captured from a real inklecate build's -p
play-mode transcript before any assertion was written. Both fixtures
deliberately use only the plain "* [choice-only text]" bracket form —
the "text[choice]more" start+choice-only combo compiles to weave/tunnel
machinery ($r variable pointer redirection) that needs the call stack.
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


def _play(state: InkRuntimeState, choices: list[int]) -> str:
    """Drive a full playthrough, choosing each index in order, and return the joined text."""
    text = state.continue_story()
    for index in choices:
        state.choose(index)
        text += state.continue_story()
    return text


class BasicChoiceTests(SimpleTestCase):
    """two once-only bracket choices, no loop (choices.ink)."""

    def test_first_turn_offers_both_choices_with_correct_text(self):
        """Both choices are collected on the opening turn with their bracket text."""
        state = InkRuntimeState(load_story_root(_load("choices.ink.json")))
        state.continue_story()
        self.assertEqual([c.text for c in state.current_choices], ["Go north", "Go south"])

    def test_choosing_north_matches_inklecate_play_transcript(self):
        """Choosing the first choice matches inklecate -p's transcript exactly."""
        state = InkRuntimeState(load_story_root(_load("choices.ink.json")))
        text = _play(state, [0])
        self.assertEqual(text, "Hello, traveler.\nYou went north.\n")
        self.assertTrue(state.done)

    def test_choosing_south_matches_inklecate_play_transcript(self):
        """Choosing the second choice reaches different, further content."""
        state = InkRuntimeState(load_story_root(_load("choices.ink.json")))
        text = _play(state, [1])
        self.assertEqual(text, "Hello, traveler.\nYou went south.\nYou made your choice.\n")
        self.assertTrue(state.done)

    def test_story_ends_with_no_choices_pending_after_either_branch(self):
        """After either branch resolves, no more choices are offered."""
        state = InkRuntimeState(load_story_root(_load("choices.ink.json")))
        _play(state, [1])
        self.assertEqual(state.current_choices, [])


class GatherLoopTests(SimpleTestCase):
    """named knots, a self-loop divert, and once-only pruning
    (gather_loop.ink)."""

    def test_leaving_immediately_matches_inklecate_play_transcript(self):
        """Choosing "Leave" on the first turn diverts straight to the outside knot."""
        state = InkRuntimeState(load_story_root(_load("gather_loop.ink.json")))
        text = _play(state, [1])
        self.assertEqual(text, "You are in a room.\nYou step outside.\n")
        self.assertTrue(state.done)

    def test_looking_around_once_then_leaving_matches_inklecate_play_transcript(self):
        """Looping back into the same knot once, then leaving, matches the real transcript."""
        state = InkRuntimeState(load_story_root(_load("gather_loop.ink.json")))
        text = _play(state, [0, 0])
        self.assertEqual(text, "You are in a room.\nYou are in a room.\nYou step outside.\n")
        self.assertTrue(state.done)

    def test_once_only_choice_is_pruned_after_being_taken(self):
        """ "Look around" (once_only) disappears from current_choices after being chosen."""
        state = InkRuntimeState(load_story_root(_load("gather_loop.ink.json")))
        state.continue_story()
        self.assertEqual([c.text for c in state.current_choices], ["Look around", "Leave"])
        state.choose(0)
        state.continue_story()
        self.assertEqual([c.text for c in state.current_choices], ["Leave"])


class ControlCommandMarkerTests(SimpleTestCase):
    """bare ControlCommand markers must never leak as visible text.

    A bare "nop"/"thread" marker in real compiled output (e.g. a thread
    weave's own `<- knot` divert) must never fall through to push_text()
    and appear in visible output as literal text -- only
    EVAL_START/EVAL_END/STRING_START/STRING_END/DONE_COMMANDS are
    recognized as control-command markers by default, so anything else
    must be explicitly handled.

    control_command_leak.json is hand-constructed, not compiled
    by inklecate — "nop" is an internal compiler artifact (a structural
    placeholder), not something directly authorable in .ink source, so
    there's no real .ink file to compile it from. Every other fixture in
    this file is compiled from real .ink source and playtested against a
    real inklecate transcript; this one instead pins down the exact
    documented JSON encoding for ControlCommand markers.
    """

    def test_nop_marker_does_not_appear_in_output_text(self):
        """A bare "nop" marker between two text tokens contributes no text of its own."""
        state = InkRuntimeState(load_story_root(_load("control_command_leak.json")))
        text = state.continue_story()
        self.assertEqual(text, "Before.\nAfter.\n")

    def test_nop_marker_inside_choice_text_string_capture_does_not_leak(self):
        """A bare "nop" marker inside an active str/../str capture (not just
        the main output stream) must not leak into a choice's text either.

        Regression coverage for a second, distinct instance of the same bug
        class: an inline conditional inside choice-only bracket text
        (`* [Follow {use_alt:Sarah|Angela}]`) compiles to two branch
        containers that both divert to a shared join point, followed by
        a bare "nop" *inside* the choice text's own str/../str
        string-capture run (choice_text_conditional.ink, real
        inklecate-compiled output, not hand-constructed). This is a
        different code path than the main-stream leak above:
        _handle_string_capture_command was unconditionally capturing every
        token as literal text once a capture was active, without first
        checking CONTROL_COMMAND_MARKERS the way the main-stream branch in
        _handle_string_content already did — producing "Follow Angelanop"
        instead of "Follow Angela".
        """
        state = InkRuntimeState(load_story_root(_load("choice_text_conditional.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Test.\n")
        self.assertEqual([c.text for c in state.current_choices], ["Follow Angela"])
        state.choose(0)
        text += state.continue_story()
        self.assertEqual(text, "Test.\nDone.\n")
        self.assertTrue(state.done)

    def test_operator_inside_choice_text_string_capture_does_not_leak(self):
        """A native-function operator token (e.g. "==") inside an active
        str/../str capture must be evaluated, not captured as literal text.

        A choice-text inline conditional whose CONDITION is a comparison,
        not a bare bool var, compiles to a NESTED "ev"/"/ev" pair *inside*
        the outer choice-text "str"/"/str" capture — the inner eval run's
        own operator token ("==") is eval-stack machinery belonging to the
        condition check, not text content, so
        _handle_string_capture_command's `if self._string_capture_stack:`
        branch must not unconditionally capture every non-marker token as
        literal text once a capture is active. The same applies to
        NATIVE_FUNCTION_ARITY/CHOICE_COUNT/TURNS/TURNS_SINCE/READ_COUNT/
        VISIT_INDEX/rnd/srnd/seq/lrnd tokens, which must route to
        _apply_operator_defensively/_handle_story_metadata_command/
        _handle_rng_command exactly like at eval-run depth 0, not fall
        through to the text-capture branch.
        """
        state = InkRuntimeState(load_story_root(_load("operator_in_choice_text_string_capture.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Test.\n")
        self.assertEqual([c.text for c in state.current_choices], ['"Fuck"'])
        state.choose(0)
        text += state.continue_story()
        self.assertEqual(text, "Test.\nDone.\n")
        self.assertTrue(state.done)

    def test_var_interpolation_inside_choice_text_string_capture_does_not_truncate(self):
        """A plain `{var}` interpolation inside an active str/../str
        choice-text capture must be evaluated AND leave the literal text
        that follows it (in the same capture) intact.

        `* [Obey the {officer_title}?]` compiles the choice text's
        str/../str capture as `"str", "^Obey the ", "ev",
        {"VAR?": "officer_title"}, "out", "/ev", "^?", "/str"` — a NESTED
        "ev"/"/ev" pair around the VariableReference, same shape as the
        operator case above, but for a bare variable read rather than a
        comparison. Two things must both hold:

        (1) `_handle_string_capture_command`'s CONTROL_COMMAND_MARKERS
        fast path must not swallow "out" (EVAL_OUTPUT is a member of that
        frozenset) before `_handle_eval_run_command`'s real EVAL_OUTPUT
        handling runs, or the interpolated value is discarded entirely.

        (2) The literal `?` immediately following the nested ev/../ev
        block sits back at the capture's own base eval-run depth (already
        > 0, since the whole capture sits inside the choice's own
        surrounding "ev"), and collides with LIST_NATIVE_FUNCTION_ARITY's
        "?" (the LIST "contains" operator, merged into
        NATIVE_FUNCTION_ARITY at module scope) if the operator/
        native-function check is gated on a bare `self._eval_run_depth >
        0`. Each string capture must instead record its own baseline
        `_eval_run_depth` in a parallel `_string_capture_eval_depth`
        stack when it opens, and compare against THAT baseline (not a
        bare 0) to distinguish "genuinely inside the nested eval run
        this capture opened" from "back at this capture's own text
        level" — both EVAL_OUTPUT's CONTROL_COMMAND_MARKERS exclusion
        and the operator/native-function check use this baseline
        comparison.
        """
        state = InkRuntimeState(load_story_root(_load("var_interpolation_in_choice_text_string_capture.ink.json")))
        text = state.continue_story()
        self.assertEqual(text, "Hub.\n")
        self.assertEqual([c.text for c in state.current_choices], ["Obey the Officer?"])
        state.choose(0)
        text += state.continue_story()
        self.assertEqual(text, "Hub.\nDone.\n")
        self.assertTrue(state.done)
