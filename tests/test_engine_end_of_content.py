"""A turn that runs out of content without `-> DONE`, `-> END` or a choice (ink_engine.engine).

Each fixture (tests/fixtures/end_of_content_*.ink) was played with the
local inklecate build's `-p`; its output is copied below. inklecate stops
with a RUNTIME ERROR in two wordings, by whether a tunnel is still open,
and plays on where content runs out inside a thread or a function, or at
the end of the story's top-level content.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from typing import ClassVar
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import InkRuntimeState, StoryRuntimeError, load_story_root

FIXTURES = FilePath(__file__).parent / "fixtures"
TUNNEL_OPEN = "unexpectedly reached end of content. Do you need a '->->' to return from a tunnel?"
NO_TUNNEL = "ran out of content. Do you need a '-> DONE' or '-> END'?"


def _state(name: str) -> InkRuntimeState:
    return InkRuntimeState(load_story_root(json.loads((FIXTURES / f"end_of_content_{name}.ink.json").read_text(encoding="utf-8"))))


class RanOutOfContentTests(SimpleTestCase):
    """The turns inklecate stops with a RUNTIME ERROR raise `StoryRuntimeError`, after the text it printed."""

    #: fixture: (text inklecate printed, message it gave, the path the message names here)
    CASES: ClassVar[dict[str, tuple[str, str, str]]] = {
        "tunnel_no_choice": ("Before.\n", TUNNEL_OPEN, "t"),
        "tunnel_falls_off": ("Before.\nIn the tunnel.\n", TUNNEL_OPEN, "t"),
        "no_choice": ("Before.\n", NO_TUNNEL, "room"),
        "knot_falls_off": ("Before.\nIn the room.\n", NO_TUNNEL, "room"),
    }

    def test_the_turn_raises_with_inklecate_s_message(self):
        """The message names where the content ran out, then gives inklecate's wording."""
        for name, (text, message, where) in self.CASES.items():
            with self.subTest(fixture=name):
                state = _state(name)
                with self.assertRaises(StoryRuntimeError) as raised:
                    state.continue_story()
                self.assertEqual(str(raised.exception), f"{where}: {message}")
                self.assertEqual(state.last_turn_text, text)

    def test_a_choice_that_leaves_a_tunnel_open_raises_on_the_next_turn(self):
        """inklecate offers "Pick", then stops after "Picked." with the tunnel still open."""
        state = _state("tunnel_after_choice")
        self.assertEqual(state.continue_story(), "Before.\n")
        self.assertEqual([choice.text for choice in state.current_choices], ["Pick"])
        state.choose(0)
        with self.assertRaisesRegex(StoryRuntimeError, "unexpectedly reached end of content"):
            state.continue_story()
        self.assertEqual(state.last_turn_text, "Picked.\n")


class PlaysOnTests(SimpleTestCase):
    """Where inklecate plays on, the turn stops as it did: no error."""

    #: fixture: (text inklecate printed, the choices it offered)
    CASES: ClassVar[dict[str, tuple[str, list[str]]]] = {
        "top_level": ("Just some text.\n", []),
        "function": ("Before. Inside.\n", []),
        "thread": ("Before.\nThread text.\n", ["Own"]),
        "tunnel_in_thread": ("Before.\nIn the tunnel.\n", ["Own"]),
    }

    def test_the_turn_stops_without_an_error(self):
        """The text and choices inklecate printed."""
        for name, (text, choices) in self.CASES.items():
            with self.subTest(fixture=name):
                state = _state(name)
                self.assertEqual(state.continue_story(), text)
                self.assertEqual([choice.text for choice in state.current_choices], choices)
