"""Action sections: a side-panel section listing a menu knot's tagged
choices, each run as an interlude (panel_actions.ink)."""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from types import SimpleNamespace
from unittest import TestCase

from ink_engine import game_panel
from ink_engine.engine import InkRuntimeState, load_story_root, start_new_story

FIXTURES = FilePath(__file__).parent / "fixtures"
STORY = json.loads((FIXTURES / "panel_actions.ink.json").read_text(encoding="utf-8"))
ROOT = load_story_root(STORY)


#: Resolves each media request to its own path, prefixed.
ECHO_RESOLVER = SimpleNamespace(resolve=lambda requests: [f"media/{path}" for _kind, path in requests])


def _panel(heading: str = "Companions") -> dict:
    return {"panel_sections": [], "panel_slots": [game_panel.actions_section("companion_actions", heading=heading)]}


def _filled(state: InkRuntimeState) -> dict:
    return game_panel.fill_action_sections(_panel(), state, resolver=ECHO_RESOLVER)


def _groups(state: InkRuntimeState) -> list[dict]:
    return game_panel.action_sections(_filled(state))[0]["groups"]


class ActionsSectionTests(TestCase):
    """`actions_section()` and `fill_action_sections()`: what an action section lists."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_the_declaration_names_the_knot(self):
        """The declaration names the knot."""
        section = game_panel.actions_section("companion_actions", heading="Companions")
        self.assertEqual(section["layout"], game_panel.ACTIONS_LAYOUT)
        self.assertEqual(section["knot"], "companion_actions")

    def test_choices_are_grouped_by_their_group_tag_in_story_order(self):
        """Choices are grouped by their group tag in story order."""
        groups = _groups(self.state)
        self.assertEqual([group["id"] for group in groups], ["sam", ""])
        self.assertEqual([action["label"] for action in groups[0]["actions"]], ["Talk to Sam", "Ask Sam about the shop"])
        self.assertEqual([action["label"] for action in groups[1]["actions"]], ["Check the time"])

    def test_a_group_takes_its_image_from_its_image_tag(self):
        """A group takes its image from its image tag."""
        groups = _groups(self.state)
        self.assertEqual(groups[0]["image_urls"], ["media/sam/Winter/sam-face.jpg"])
        self.assertEqual(groups[1]["image_urls"], [])

    def test_ink_conditions_decide_what_is_listed(self):
        """Ink conditions decide what is listed."""
        self.state.globals["ada_present"] = True
        self.assertIn("ada", [group["id"] for group in _groups(self.state)])

    def test_listing_leaves_the_live_state_unchanged(self):
        """Listing leaves the live state unchanged."""
        before = json.dumps(self.state.to_dict(), sort_keys=True)
        _filled(self.state)
        self.assertEqual(json.dumps(self.state.to_dict(), sort_keys=True), before)

    def test_without_a_resolver_groups_have_no_images(self):
        """Without a resolver groups have no images."""
        filled = game_panel.fill_action_sections(_panel(), self.state)
        self.assertEqual(game_panel.action_sections(filled)[0]["groups"][0]["image_urls"], [])

    def test_an_unknown_knot_lists_nothing(self):
        """An unknown knot lists nothing."""
        panel = {"panel_slots": [game_panel.actions_section("no_such_knot", heading="Companions")]}
        with self.assertLogs("ink_engine.game_panel", level="WARNING"):
            filled = game_panel.fill_action_sections(panel, self.state)
        self.assertEqual(game_panel.action_sections(filled)[0]["groups"], [])

    def test_the_panel_passed_in_is_not_changed(self):
        """The panel passed in is not changed."""
        panel = _panel()
        game_panel.fill_action_sections(panel, self.state)
        self.assertNotIn("groups", panel["panel_slots"][0])

    def test_no_panel_fills_to_none(self):
        """No panel fills to none."""
        self.assertIsNone(game_panel.fill_action_sections(None, self.state))


class FindActionTests(TestCase):
    """`find_action()`, and running what it finds as an interlude."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_an_offered_action_is_found_by_group_and_label(self):
        """An offered action is found by group and label."""
        action = game_panel.find_action(_filled(self.state), "sam", "Talk to Sam")
        self.assertIsNotNone(action)
        self.assertEqual(action["group"], "sam")

    def test_an_action_not_offered_now_is_not_found(self):
        """An action not offered now is not found."""
        self.assertIsNone(game_panel.find_action(_filled(self.state), "ada", "Talk to Ada"))
        self.assertIsNone(game_panel.find_action(_filled(self.state), "", "Talk to Sam"))
        self.assertIsNone(game_panel.find_action(None, "sam", "Talk to Sam"))

    def test_running_an_action_returns_to_the_scene(self):
        """Running an action returns to the scene."""
        action = game_panel.find_action(_filled(self.state), "sam", "Talk to Sam")
        text = self.state.start_interlude(action["target"])
        self.assertEqual(text, "Sam grins.\n")
        self.assertEqual([choice.text for choice in self.state.current_choices], ["Browse", "Leave"])
        self.assertEqual(self.state.globals["chats"], 1)

    def test_a_once_only_action_is_retired_after_it_runs(self):
        """A once only action is retired after it runs."""
        action = game_panel.find_action(_filled(self.state), "sam", "Ask Sam about the shop")
        self.state.start_interlude(action["target"])
        self.assertIsNone(game_panel.find_action(_filled(self.state), "sam", "Ask Sam about the shop"))
        self.assertIsNotNone(game_panel.find_action(_filled(self.state), "sam", "Talk to Sam"))


class PlayReactionTests(TestCase):
    """`play_reaction()`: a panel command's knot played as a story turn."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_the_knot_plays_as_a_turn(self):
        """The reaction's text is the turn's text, and the turn count advances."""
        before = self.state.turn_count
        text = game_panel.play_reaction(self.state, game_panel.CommandResult(knot="check_time"))
        self.assertEqual(text, "It is noon.\n")
        self.assertEqual(self.state.turn_count, before + 1)

    def test_the_reaction_can_show_the_scene_again(self):
        """Diverting back to the scene re-evaluates its choices by showing it."""
        self.state.globals["sam_present"] = False
        text = game_panel.play_reaction(self.state, game_panel.CommandResult(knot="scene"))
        self.assertEqual(text, "The shopkeeper eyes you warily.\n")
        self.assertEqual([choice.text for choice in self.state.current_choices], ["Browse", "Leave"])

    def test_a_message_only_result_plays_nothing(self):
        """No knot: None, and the state is unchanged."""
        before = self.state.to_dict()
        self.assertIsNone(game_panel.play_reaction(self.state, game_panel.CommandResult(message="Too heavy.")))
        self.assertEqual(self.state.to_dict(), before)
