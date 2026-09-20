"""start_new_story() -- the shared new-game entry point (ink_engine.engine).

Both applications build a fresh game through this one helper, so the
initial-globals seam is verified here once rather than in each consumer.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import load_list_defs, load_story_root, start_new_story

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class StartNewStoryTests(SimpleTestCase):
    """variables.ink declares `VAR score = 0`, then adds 5 and branches on
    the result -- so a seeded value shows up in both the interpolated text
    and the conditional."""

    def _root_and_lists(self):
        story_json = _load("variables.ink.json")
        return load_story_root(story_json), load_list_defs(story_json)

    def test_the_opening_turn_has_already_run(self):
        root, list_defs = self._root_and_lists()
        state = start_new_story(root, list_defs)
        self.assertIn("You have 5 points.", state.last_turn_text)

    def test_declared_var_defaults_apply_when_nothing_is_seeded(self):
        root, list_defs = self._root_and_lists()
        state = start_new_story(root, list_defs)
        self.assertEqual(state.globals["score"], 5)

    def test_initial_globals_are_applied_before_the_opening_turn(self):
        """Seeding 10 must reach the story's own arithmetic, not be
        overwritten by the VAR declaration -- 10 + 5, interpolated."""
        root, list_defs = self._root_and_lists()
        state = start_new_story(root, list_defs, initial_globals={"score": 10})
        self.assertEqual(state.globals["score"], 15)
        self.assertIn("You have 15 points.", state.last_turn_text)

    def test_a_seeded_value_drives_the_storys_own_branch(self):
        """The negative branch is only reachable through seeding: the
        story's own default always lands above the threshold."""
        root, list_defs = self._root_and_lists()
        state = start_new_story(root, list_defs, initial_globals={"score": -10})
        self.assertIn("Keep trying.", state.last_turn_text)

    def test_an_empty_initial_globals_leaves_defaults_untouched(self):
        root, list_defs = self._root_and_lists()
        state = start_new_story(root, list_defs, initial_globals={})
        self.assertEqual(state.globals["score"], 5)
