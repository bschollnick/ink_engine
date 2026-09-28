"""`InkRuntimeState.start_interlude()`: running a knot as a tunnel from
outside the story, then returning to the interrupted turn's choices
(interlude.ink)."""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    InkRuntimeState,
    InterludeError,
    load_story_root,
    start_new_story,
)

FIXTURES = FilePath(__file__).parent / "fixtures"
STORY = json.loads((FIXTURES / "interlude.ink.json").read_text(encoding="utf-8"))
ROOT = load_story_root(STORY)
SCENE_CHOICES = ["Ask about the vase", "Leave"]


def _labels(state: InkRuntimeState) -> list[str]:
    return [choice.text for choice in state.current_choices]


def _choose(state: InkRuntimeState, label: str) -> str:
    state.choose(_labels(state).index(label))
    return state.continue_story()


def _round_trip(state: InkRuntimeState) -> InkRuntimeState:
    return InkRuntimeState.from_dict(ROOT, json.loads(json.dumps(state.to_dict())))


class InterludeReturnTests(SimpleTestCase):
    """An interlude that ends with `->->` puts the scene's choices back."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_the_knot_runs_and_the_scene_choices_come_back(self):
        """The knot runs and the scene choices come back."""
        text = self.state.start_interlude("quick_word")
        self.assertEqual(text, 'Sam whispers, "Let me handle this."\n')
        self.assertEqual(_labels(self.state), SCENE_CHOICES)
        self.assertFalse(self.state.done)

    def test_it_is_a_turn(self):
        """It is a turn."""
        before = self.state.turn_count
        self.state.start_interlude("quick_word")
        self.assertEqual(self.state.turn_count, before + 1)
        self.assertEqual(self.state.globals["talked"], 1)

    def test_nothing_is_left_on_the_stacks(self):
        """Nothing is left on the stacks."""
        self.state.start_interlude("quick_word")
        self.assertEqual(self.state.tunnel_stack, [])
        self.assertEqual(self.state.to_dict()["interludes"], [])

    def test_an_interlude_with_its_own_choices_returns_after_them(self):
        """An interlude with its own choices returns after them."""
        self.state.start_interlude("question")
        self.assertEqual(_labels(self.state), ['"Yes"', '"Wander off"', '"Not yet"'])
        self.assertEqual(_choose(self.state, '"Not yet"'), '"Fine."\n')
        self.assertEqual(_labels(self.state), SCENE_CHOICES)

    def test_the_scene_carries_on_afterwards(self):
        """The scene carries on afterwards."""
        self.state.start_interlude("quick_word")
        self.assertEqual(_choose(self.state, "Ask about the vase"), 'She shrugs. "Old."\n')
        self.assertEqual(_labels(self.state), ["Leave"])

    def test_an_interlude_can_start_inside_another(self):
        """An interlude can start inside another."""
        self.state.start_interlude("question")
        self.state.start_interlude("quick_word")
        self.assertEqual(_labels(self.state), ['"Yes"', '"Wander off"', '"Not yet"'])
        _choose(self.state, '"Not yet"')
        self.assertEqual(_labels(self.state), SCENE_CHOICES)
        self.assertEqual(self.state.tunnel_stack, [])


class InterludeSaveTests(SimpleTestCase):
    """The set-aside choices travel with `to_dict()` / `from_dict()`."""

    def test_a_restored_save_still_returns_to_the_scene(self):
        """A restored save still returns to the scene."""
        state = start_new_story(ROOT, {})
        state.start_interlude("question")
        restored = _round_trip(state)
        self.assertEqual(_choose(restored, '"Not yet"'), '"Fine."\n')
        self.assertEqual(_labels(restored), SCENE_CHOICES)
        self.assertEqual(restored.tunnel_stack, [])

    def test_a_save_without_interludes_loads(self):
        """A save without interludes loads."""
        state = start_new_story(ROOT, {})
        saved = state.to_dict()
        del saved["interludes"]
        self.assertEqual(_labels(InkRuntimeState.from_dict(ROOT, saved)), SCENE_CHOICES)


class InterludeLeavesTheSceneTests(SimpleTestCase):
    """An interlude that does not return discards the scene's choices."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})
        self.state.start_interlude("question")

    def test_returning_elsewhere_discards_the_scene(self):
        """Returning elsewhere discards the scene."""
        text = _choose(self.state, '"Yes"')
        self.assertEqual(text, '"Then let\'s go."\nYou are on the street.\nYou run an errand.\nBack on the street.\n')
        self.assertEqual(_labels(self.state), ["Wait"])
        self.assertEqual(self.state.tunnel_stack, [])
        self.assertEqual(self.state.to_dict()["interludes"], [])

    def test_a_later_tunnel_returns_to_its_own_caller(self):
        """A later tunnel returns to its own caller."""
        _choose(self.state, '"Yes"')
        self.assertEqual(_choose(self.state, "Wait"), "You are on the street.\nYou run an errand.\nBack on the street.\n")
        self.assertEqual(_labels(self.state), ["Wait"])

    def test_a_plain_divert_away_keeps_later_tunnels_returning_to_their_callers(self):
        """A plain divert leaves the tunnel open, as in standard Ink."""
        text = _choose(self.state, '"Wander off"')
        self.assertEqual(text, "You wander off.\nYou are on the street.\nYou run an errand.\nBack on the street.\n")
        self.assertEqual(_labels(self.state), ["Wait"])

    def test_ending_the_story_discards_the_scene(self):
        """Ending the story discards the scene."""
        state = start_new_story(ROOT, {})
        state.start_interlude("farewell")
        self.assertTrue(state.done)
        self.assertEqual(state.current_choices, [])
        self.assertEqual(state.tunnel_stack, [])
        self.assertEqual(state.to_dict()["interludes"], [])


class InterludeRefusalTests(SimpleTestCase):
    """What `start_interlude()` refuses, before changing anything."""

    def test_an_unknown_knot_is_refused(self):
        """An unknown knot is refused."""
        state = start_new_story(ROOT, {})
        before = state.to_dict()
        with self.assertRaises(InterludeError):
            state.start_interlude("no_such_knot")
        self.assertEqual(state.to_dict(), before)

    def test_a_finished_story_is_refused(self):
        """A finished story is refused."""
        state = start_new_story(ROOT, {})
        _choose(state, "Leave")
        with self.assertRaises(InterludeError):
            state.start_interlude("quick_word")
