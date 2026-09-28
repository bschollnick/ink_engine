"""The demonstration game in examples/ plays to both of its endings.

An integration test rather than a mechanic test: it drives the compiled
story the way a player does, by choosing from the offered choices, and
asserts the endings and the score. The published walkthrough for this
game is `s / n / w / inventory / hang cloak on hook / e / s / read
message`, which is the winning sequence below.

The disturbance rule under test comes from the game's 1999 original:
moving in the dark costs two, any other action in the dark costs one,
and the message is readable below two. One wrong move therefore loses,
while one non-movement fumble still permits a win.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import InkRuntimeState, load_story_root
from ink_engine.game_panel import find_exit
from ink_engine.travel import take_exit

# The example game is imported from examples/, so these follow the path insertion.
sys.path.insert(0, str(Path(__file__).parent.parent / "examples"))
from cloak_of_darkness.locations import CLOAK_MAP, MAP
from cloak_of_darkness.sidebar import panel_context

GAME = Path(__file__).parent.parent / "examples" / "cloak_of_darkness"
STORY = GAME / "cloak_of_darkness.inkj"

SOUTH = "Go south, to the bar"
NORTH = "Go north, to the foyer"
WEST = "Go west, to the cloakroom"
EAST = "Go east, to the foyer"
HANG = "Hang the cloak on the hook"
DROP = "Drop the cloak on the floor"
READ = "Read the message"
BLUNDER = "Go south, further into the dark"
FUMBLE = "Feel around on the floor"

#: The published walkthrough, as the choices this implementation offers.
WALKTHROUGH = [SOUTH, NORTH, WEST, HANG, EAST, SOUTH, READ]


def _play(labels: list[str]) -> tuple[InkRuntimeState, str]:
    """Play the story, choosing each labelled choice in order.

    Args:
        labels: The choice texts to select, in order.

    Returns:
        The finished state and the whole transcript.

    Raises:
        AssertionError: If a label is not among the offered choices,
            which means the story no longer reaches that point.
    """
    with open(STORY, encoding="utf-8") as story_file:
        state = InkRuntimeState(load_story_root(json.load(story_file)))
    text = state.continue_story()
    for label in labels:
        offered = [index for index, choice in enumerate(state.current_choices) if choice.text == label]
        assert offered, f"no choice {label!r}; offered {[c.text for c in state.current_choices]}"
        state.choose(offered[0])
        text += state.continue_story()
    return state, text


class CloakOfDarknessWalkthroughTests(SimpleTestCase):
    """The demonstration game reaches both endings with the right score."""

    def test_the_published_walkthrough_wins_with_full_score(self):
        state, text = _play(WALKTHROUGH)
        self.assertIn("The message, neatly marked in the sawdust, reads...", text)
        self.assertIn("You have won", text)
        self.assertEqual(state.globals["score"], 2)
        self.assertEqual(state.globals["disturbance"], 0)
        self.assertTrue(state.done)

    def test_the_opening_offers_the_three_doorways_and_an_inventory(self):
        state, text = _play([])
        self.assertIn("bright lights of the Opera House", text)
        # GO is the unguarded movement choice an application takes on the
        # player's behalf; it is never shown to them.
        self.assertEqual(
            [choice.text for choice in state.current_choices],
            [SOUTH, WEST, "Go north, to the street", "Check what you are carrying", "GO"],
        )

    def test_the_street_is_refused_without_leaving_the_foyer(self):
        state, text = _play(["Go north, to the street"])
        self.assertIn("You've only just arrived", text)
        self.assertIn(SOUTH, [choice.text for choice in state.current_choices])

    def test_one_blunder_in_the_dark_loses(self):
        state, text = _play([SOUTH, BLUNDER, NORTH, WEST, HANG, EAST, SOUTH, READ])
        self.assertEqual(state.globals["disturbance"], 2)
        self.assertIn("carelessly trampled", text)
        self.assertIn("You have lost", text)
        self.assertEqual(state.globals["score"], 1)

    def test_one_fumble_in_the_dark_still_wins(self):
        state, text = _play([SOUTH, FUMBLE, NORTH, WEST, HANG, EAST, SOUTH, READ])
        self.assertEqual(state.globals["disturbance"], 1)
        self.assertIn("You have won", text)
        self.assertEqual(state.globals["score"], 2)

    def test_two_fumbles_in_the_dark_lose(self):
        state, text = _play([SOUTH, FUMBLE, FUMBLE, NORTH, WEST, HANG, EAST, SOUTH, READ])
        self.assertEqual(state.globals["disturbance"], 2)
        self.assertIn("You have lost", text)

    def test_dropping_the_cloak_lights_the_bar_but_forfeits_a_point(self):
        state, text = _play([WEST, DROP, EAST, SOUTH, READ])
        self.assertIn("You have won", text)
        self.assertEqual(state.globals["score"], 1)

    def test_the_hook_point_is_awarded_once(self):
        state, _ = _play([WEST, HANG, "Take the cloak from the hook", HANG])
        self.assertEqual(state.globals["score"], 1)

    def test_the_bar_is_dark_while_the_cloak_is_worn(self):
        state, text = _play([SOUTH])
        self.assertIn("pitch dark", text)
        self.assertNotIn(READ, [choice.text for choice in state.current_choices])

    def test_the_hook_description_changes_once_the_cloak_hangs_on_it(self):
        _, before = _play([WEST, "Examine the hook"])
        self.assertIn("screwed to the wall", before)
        _, after = _play([WEST, HANG, "Examine the hook"])
        self.assertIn("with a cloak hanging on it", after)


class CloakMapTests(SimpleTestCase):
    """The game's map drives movement, which is what this game demonstrates."""

    def setUp(self):
        self.slot = CLOAK_MAP.init_state(MAP)

    def test_the_foyer_offers_the_two_doorways_and_the_refused_street(self):
        exits = {exit_["position"]: exit_ for exit_ in CLOAK_MAP.exits_from(self.slot, "foyer")}
        self.assertEqual(sorted(exits), ["n", "s", "w"])
        self.assertTrue(exits["s"]["passable"])
        self.assertTrue(exits["w"]["passable"])
        self.assertFalse(exits["n"]["passable"], "the street is sealed")

    def test_the_return_exits_were_filled_in_rather_than_declared(self):
        for location_id, position in (("bar", "n"), ("cloakroom", "e")):
            with self.subTest(location=location_id):
                exits = CLOAK_MAP.exits_from(self.slot, location_id)
                self.assertEqual([exit_["position"] for exit_ in exits], [position])
                self.assertEqual(exits[0]["to"], "foyer")

    def test_the_sealed_street_gains_no_return(self):
        self.assertEqual(CLOAK_MAP.exits_from(self.slot, "street"), [])

    def test_an_exit_carries_the_knot_and_prose_movement_needs(self):
        south = next(e for e in CLOAK_MAP.exits_from(self.slot, "foyer") if e["position"] == "s")
        self.assertEqual(south["arrival_knot"], "bar")
        self.assertIn("south", south["travel_text"])

    def test_taking_an_exit_by_its_own_data_moves_and_narrates(self):
        state, _ = _play([])
        south = next(e for e in CLOAK_MAP.exits_from(self.slot, "foyer") if e["position"] == "s")
        text = take_exit(state, south["arrival_knot"], south["travel_text"])
        self.assertIn(south["travel_text"], text)
        self.assertIn("pitch dark", text)


class CloakPanelTests(SimpleTestCase):
    """The game's sidebar draws the player's room's exits, and they can be taken."""

    def _panel(self, state: InkRuntimeState) -> dict:
        engine_state = {CLOAK_MAP.state_key: CLOAK_MAP.init_state(MAP)}
        return panel_context(engine_state=engine_state, globals_=state.globals, bindings={})

    def _go(self, state: InkRuntimeState, exit_id: str) -> str:
        exit_ = find_exit(self._panel(state), exit_id)
        self.assertIsNotNone(exit_, f"no passable exit {exit_id!r} from {state.globals['current_location']!r}")
        return take_exit(state, exit_["arrival_knot"], exit_["travel_text"])

    def test_the_foyer_panel_shows_the_sealed_street(self):
        state, _ = _play([])
        exits = {exit_["id"]: exit_ for exit_ in self._panel(state)["panel_sections"][0]["exits"]}
        self.assertEqual(sorted(exits), ["position:n", "position:s", "position:w"])
        self.assertFalse(exits["position:n"]["passable"])

    def test_every_room_can_be_left_by_the_compass(self):
        """The returns to the foyer are synthesized, so this covers them too."""
        for there, back in (("position:s", "position:n"), ("position:w", "position:e")):
            with self.subTest(exit=there):
                state, _ = _play([])
                self._go(state, there)
                text = self._go(state, back)
                self.assertIn("You walk back into the foyer.", text)
                self.assertEqual(state.globals["current_location"], "foyer")

    def test_the_walkthrough_wins_moving_only_by_the_compass(self):
        state, _ = _play([])
        for step in ("position:s", "position:n", "position:w"):
            self._go(state, step)
        state.choose(next(i for i, c in enumerate(state.current_choices) if c.text == HANG))
        state.continue_story()
        self._go(state, "position:e")
        self._go(state, "position:s")
        state.choose(next(i for i, c in enumerate(state.current_choices) if c.text == READ))
        text = state.continue_story()
        self.assertIn("You have won", text)
        self.assertEqual(state.globals["score"], 2)
