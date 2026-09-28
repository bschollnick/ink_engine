"""Literal text that spells a control marker is text, not the marker.

Compiled JSON writes literal text as "^text" and control markers as bare
strings ("done", "end", "ev", "str", ...). A string value or a line of text
that happens to spell one of those must not run it: `~ temp a = "done"`
once ended the story.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import InkRuntimeState, load_story_root

FIXTURE_JSON = FilePath(__file__).parent / "fixtures" / "text_spelling_a_command.ink.json"


class TextSpellingACommandTests(SimpleTestCase):
    """Strings and text equal to "done", "end", "ev", "str" and "/str"."""

    def setUp(self) -> None:
        self.state = InkRuntimeState(load_story_root(json.loads(FIXTURE_JSON.read_text(encoding="utf-8"))))
        self.text = self.state.continue_story()

    def test_string_values_and_text_are_output(self) -> None:
        """The three temps print as their text, and the story goes on past them."""
        self.assertEqual(self.text, "Before done end ev str /str\nAfter\n")

    def test_the_story_reaches_its_choice_and_tag(self) -> None:
        """Choice text and tags that follow are intact."""
        self.assertEqual([choice.text for choice in self.state.current_choices], ['Pick "done" and pop'])
        self.assertEqual(self.state.current_tags, ["tag"])
