"""Taking an exit from outside the story's choice list (ink_engine.travel).

Driven against a real compiled fixture (tests/fixtures/travel_movement.ink),
three locations each offering `+ [GO] -> movement`.

Two behaviours matter and both have been wrong in practice. A
destination built as a `DivertTargetValue` rather than a
`ResolvedDivertTarget` fails silently, so the negative case is asserted
here rather than assumed. And consecutive moves must each narrate and
each advance the turn: an earlier design guarded the movement choice
behind a flag and refreshed to reveal it, which moved the player once
and then relocated them in silence.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    DivertTargetValue,
    InkRuntimeState,
    Path,
    load_story_root,
)
from ink_engine.travel import TravelError, build_divert_target, take_exit

FIXTURES = FilePath(__file__).parent / "fixtures"


def _story() -> InkRuntimeState:
    """Return a started session on the travel fixture, in the foyer."""
    with open(FIXTURES / "travel_movement.ink.json", encoding="utf-8") as fixture_file:
        state = InkRuntimeState(load_story_root(json.load(fixture_file)))
    state.continue_story()
    return state


class TakeExitTests(SimpleTestCase):
    """take_exit() narrates the move and advances the turn."""

    def test_a_move_narrates_the_travel_text_then_the_arrival(self):
        state = _story()
        text = take_exit(state, "bar", "You walk south into the bar.")
        self.assertIn("You walk south into the bar.", text)
        self.assertIn("The bar is empty.", text)

    def test_a_move_advances_the_turn(self):
        state = _story()
        before = state.turn_count
        take_exit(state, "bar", "South.")
        self.assertEqual(state.turn_count, before + 1)

    def test_the_arrival_offers_the_destination_choices(self):
        state = _story()
        take_exit(state, "bar", "South.")
        self.assertIn("Read the message", [choice.text for choice in state.current_choices])

    def test_four_consecutive_moves_each_narrate_and_advance(self):
        state = _story()
        journey = [
            ("bar", "You walk south into the bar."),
            ("cloakroom", "You walk west to the cloakroom."),
            ("bar", "You return to the bar."),
            ("foyer", "You walk back to the foyer."),
        ]
        for index, (knot, travel_text) in enumerate(journey):
            text = take_exit(state, knot, travel_text)
            self.assertIn(travel_text, text, f"move {index} printed no travel text")
            self.assertEqual(state.turn_count, index, f"move {index} did not advance the turn")

    def test_an_unknown_knot_is_refused_rather_than_diverting_nowhere(self):
        state = _story()
        with self.assertRaises(TravelError):
            take_exit(state, "no_such_knot", "You walk nowhere.")

    def test_a_turn_with_no_movement_choice_is_refused(self):
        state = _story()
        take_exit(state, "bar", "South.")
        state.choose(next(index for index, choice in enumerate(state.current_choices) if choice.text == "Read the message"))
        state.continue_story()
        with self.assertRaises(TravelError):
            take_exit(state, "foyer", "You walk back.")

    def test_a_refused_move_leaves_the_movement_globals_untouched(self):
        state = _story()
        take_exit(state, "bar", "South.")
        state.choose(next(index for index, choice in enumerate(state.current_choices) if choice.text == "Read the message"))
        state.continue_story()
        before = (state.globals["destination"], state.globals["travel_text"])
        with self.assertRaises(TravelError):
            take_exit(state, "foyer", "You walk back.")
        self.assertEqual((state.globals["destination"], state.globals["travel_text"]), before)


class DivertTargetTests(SimpleTestCase):
    """Only a ResolvedDivertTarget moves the story."""

    def test_build_divert_target_returns_a_target_the_story_follows(self):
        state = _story()
        state.globals["destination"] = build_divert_target(state, "bar")
        state.globals["travel_text"] = "South."
        state.choose(next(index for index, choice in enumerate(state.current_choices) if choice.text == "GO"))
        self.assertIn("The bar is empty.", state.continue_story())

    def test_a_divert_target_value_does_not_move_the_story(self):
        """The silent failure this module exists to prevent, asserted as silent."""
        state = _story()
        state.globals["destination"] = DivertTargetValue(target_path=Path.parse("bar"))
        state.globals["travel_text"] = "South."
        state.choose(next(index for index, choice in enumerate(state.current_choices) if choice.text == "GO"))
        text = state.continue_story()
        self.assertIn("South.", text)
        self.assertNotIn("The bar is empty.", text)

    def test_build_divert_target_refuses_a_name_the_story_does_not_have(self):
        state = _story()
        with self.assertRaises(TravelError):
            build_divert_target(state, "no_such_knot")
