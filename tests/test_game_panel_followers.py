"""Followers sections: a side-panel section listing entries with a head
shot from Ink and actions from a menu knot (panel_followers.ink)."""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from types import SimpleNamespace
from unittest import TestCase

from ink_engine import game_panel
from ink_engine.engine import (
    InkRuntimeState,
    NotAFunctionError,
    load_story_root,
    start_new_story,
)

FIXTURES = FilePath(__file__).parent / "fixtures"
STORY = json.loads((FIXTURES / "panel_followers.ink.json").read_text(encoding="utf-8"))
ROOT = load_story_root(STORY)

#: Resolves each media request to its own path, prefixed.
ECHO_RESOLVER = SimpleNamespace(resolve=lambda requests: [f"media/{path}" for _kind, path in requests])

_ENTRIES = [
    {"id": "sam", "label": "Sam", "head_shot_function": "sam_head_shot"},
    {"id": "ada", "label": "Ada", "head_shot_function": "ada_head_shot"},
]


def _panel(entries: list[dict] | None = None, heading: str = "Followers") -> dict:
    return {
        "panel_sections": [],
        "panel_slots": [game_panel.followers_section(entries if entries is not None else _ENTRIES, heading=heading, knot="companion_actions")],
    }


def _filled(state: InkRuntimeState, entries: list[dict] | None = None) -> dict:
    filled = game_panel.fill_followers_sections(_panel(entries), state, resolver=ECHO_RESOLVER)
    assert filled is not None
    return filled


def _rows(state: InkRuntimeState, entries: list[dict] | None = None) -> list[dict]:
    return game_panel.followers_sections(_filled(state, entries))[0]["rows"]


class FollowersSectionTests(TestCase):
    """`followers_section()` and `fill_followers_sections()`: what a followers section lists."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_the_declaration_names_the_entries_and_knot(self):
        """The declaration names its entries and its knot."""
        section = game_panel.followers_section(_ENTRIES, heading="Followers", knot="companion_actions")
        self.assertEqual(section["layout"], game_panel.FOLLOWERS_LAYOUT)
        self.assertEqual(section["knot"], "companion_actions")
        self.assertEqual(section["entries"], _ENTRIES)

    def test_a_row_per_entry_in_the_order_given(self):
        """A row per entry, in the order given."""
        rows = _rows(self.state)
        self.assertEqual([row["id"] for row in rows], ["sam", "ada"])
        self.assertEqual(rows[0]["label"], "Sam")

    def test_a_row_takes_its_head_shot_from_its_function(self):
        """A row takes its head shot from its own function, not the knot's tags."""
        rows = _rows(self.state)
        self.assertEqual(rows[0]["image_urls"], ["media/sam/Winter/sam-face.jpg"])
        self.assertEqual(rows[1]["image_urls"], ["media/ada/ada-face.jpg"])

    def test_an_entry_with_a_matching_group_gets_its_actions(self):
        """An entry with a matching group in the knot gets its actions."""
        rows = _rows(self.state)
        self.assertEqual([action["label"] for action in rows[0]["actions"]], ["Talk to Sam"])

    def test_an_entry_with_no_matching_group_has_no_actions_but_keeps_its_head_shot(self):
        """An entry with no matching group (Ada is not present) keeps its head shot and has no actions."""
        rows = _rows(self.state)
        self.assertEqual(rows[1]["actions"], [])
        self.assertEqual(rows[1]["image_urls"], ["media/ada/ada-face.jpg"])

    def test_listing_leaves_the_live_state_unchanged(self):
        """Listing leaves the live state unchanged."""
        before = json.dumps(self.state.to_dict(), sort_keys=True)
        _filled(self.state)
        self.assertEqual(json.dumps(self.state.to_dict(), sort_keys=True), before)

    def test_without_a_resolver_rows_have_no_images(self):
        """Without a resolver, rows have no images."""
        filled = game_panel.fill_followers_sections(_panel(), self.state)
        self.assertEqual(game_panel.followers_sections(filled)[0]["rows"][0]["image_urls"], [])

    def test_an_unknown_head_shot_function_lists_no_picture(self):
        """An unknown head-shot function lists no picture, and logs a warning."""
        entries = [{"id": "sam", "label": "Sam", "head_shot_function": "no_such_function"}]
        with self.assertLogs("ink_engine.game_panel", level="WARNING"):
            rows = _rows(self.state, entries)
        self.assertEqual(rows[0]["image_urls"], [])

    def test_a_head_shot_function_naming_a_knot_raises(self):
        """A head-shot function naming a knot, not a function, raises rather than showing nothing."""
        entries = [{"id": "sam", "label": "Sam", "head_shot_function": "scene"}]
        with self.assertRaises(NotAFunctionError):
            _rows(self.state, entries)

    def test_the_panel_passed_in_is_not_changed(self):
        """The panel passed in is not changed."""
        panel = _panel()
        game_panel.fill_followers_sections(panel, self.state)
        self.assertNotIn("rows", panel["panel_slots"][0])

    def test_no_panel_fills_to_none(self):
        """No panel fills to none."""
        self.assertIsNone(game_panel.fill_followers_sections(None, self.state))


class FindActionInFollowersSectionTests(TestCase):
    """`find_action()` also reads a filled followers section's rows."""

    def setUp(self):
        """Start the story at its opening turn."""
        self.state = start_new_story(ROOT, {})

    def test_an_offered_row_action_is_found_by_group_and_label(self):
        """A row's own action is found by group and label."""
        action = game_panel.find_action(_filled(self.state), "sam", "Talk to Sam")
        self.assertIsNotNone(action)
        self.assertEqual(action["group"], "sam")

    def test_a_row_with_no_action_is_not_found(self):
        """Ada's row has no matching group, so no action is found for her."""
        self.assertIsNone(game_panel.find_action(_filled(self.state), "ada", "Talk to Ada"))

    def test_running_a_row_action_returns_to_the_scene(self):
        """Running a row's action returns to the scene, exactly as an action section's does."""
        action = game_panel.find_action(_filled(self.state), "sam", "Talk to Sam")
        text = self.state.start_interlude(action["target"])
        self.assertEqual(text, "Sam grins.\n")
        self.assertEqual([choice.text for choice in self.state.current_choices], ["Leave"])
