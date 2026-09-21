"""The session library: save envelope, transcript, turn context.

Each of these was written twice before this library existed, once per
application. The tests that matter most here are the ones that catch the two
sides drifting apart again -- the round-trip and the layering guard.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from if_session import (
    SAVE_FORMAT_VERSION,
    SaveFormatError,
    StoryEngine,
    append_transcript_entry,
    build_saved_state,
    read_saved_state,
    turn_context,
)
from ink_engine.engine import load_story_root, start_new_story

FIXTURES = FilePath(__file__).parent / "fixtures"


class _Resolver:
    """A MediaResolver that reports what it was asked for."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.seen = []

    def resolve(self, requests):
        self.seen.append(requests)
        return [self.answers[name] for _kind, name in requests if name in self.answers]


def _story(name: str = "basic.ink.json"):
    with open(FIXTURES / name, encoding="utf-8") as fixture:
        data = json.load(fixture)
    return start_new_story(load_story_root(data), data.get("listDefs", {}))


class StoryEngineProtocolTests(SimpleTestCase):
    def test_the_ink_runtime_satisfies_it(self):
        """The interface is every member an application actually calls. If Ink
        stopped satisfying it, a second engine's bar would have moved
        without anyone deciding to move it."""
        self.assertIsInstance(_story(), StoryEngine)


class SaveEnvelopeTests(SimpleTestCase):
    def setUp(self):
        self.state = _story()

    def test_it_carries_the_engines_own_fields(self):
        envelope = build_saved_state(self.state, None, [], {})
        for key in self.state.to_dict():
            self.assertIn(key, envelope)

    def test_it_layers_the_host_keys_on_top(self):
        envelope = build_saved_state(self.state, {"prior": True}, [{"text": "a"}], {"slot": 1})
        self.assertEqual(envelope["previous_state"], {"prior": True})
        self.assertEqual(envelope["transcript"], [{"text": "a"}])
        self.assertEqual(envelope["engine_state"], {"slot": 1})

    def test_it_stamps_the_format_version(self):
        self.assertEqual(build_saved_state(self.state, None, [], {})["save_format_version"], SAVE_FORMAT_VERSION)

    def test_the_engine_round_trips_through_the_envelope(self):
        """The defect this guards: `from_dict()` reads every field with a
        default, so a renamed key loads as a default rather than raising.
        Comparing the whole dict makes that loud."""
        data = json.loads((FIXTURES / "basic.ink.json").read_text(encoding="utf-8"))
        envelope = build_saved_state(self.state, None, [], {})
        from ink_engine.engine import InkRuntimeState

        restored = InkRuntimeState.from_dict(load_story_root(data), envelope, data.get("listDefs", {}))
        self.assertEqual(restored.to_dict(), self.state.to_dict())


class SaveVersionTests(SimpleTestCase):
    def test_a_save_of_this_version_reads(self):
        envelope = build_saved_state(_story(), None, [], {})
        self.assertIs(read_saved_state(envelope), envelope)

    def test_a_save_written_before_versioning_reads(self):
        """Those saves are version 1 -- the marker was added without
        changing the shape."""
        self.assertEqual(read_saved_state({"transcript": []}), {"transcript": []})

    def test_a_newer_save_is_refused_with_a_message(self):
        with self.assertRaises(SaveFormatError) as caught:
            read_saved_state({"save_format_version": SAVE_FORMAT_VERSION + 1})
        self.assertIn("newer version", str(caught.exception))


class TranscriptTests(SimpleTestCase):
    def test_it_appends(self):
        self.assertEqual(
            append_transcript_entry([], "opening", None, cap=10),
            [{"text": "opening", "chosen_label": None}],
        )

    def test_it_drops_the_oldest_at_the_cap(self):
        transcript = [{"text": str(n), "chosen_label": None} for n in range(5)]
        kept = append_transcript_entry(transcript, "new", "went north", cap=3)
        self.assertEqual([entry["text"] for entry in kept], ["3", "4", "new"])

    def test_it_does_not_mutate_its_argument(self):
        original = [{"text": "a", "chosen_label": None}]
        append_transcript_entry(original, "b", None, cap=10)
        self.assertEqual(len(original), 1)

    def test_the_cap_is_the_callers(self):
        """Django's own MAX_TRANSCRIPT_TURNS stays a Django concern."""
        self.assertEqual(len(append_transcript_entry([], "x", None, cap=1)), 1)


class TurnContextTests(SimpleTestCase):
    def setUp(self):
        self.state = _story()
        self.resolver = _Resolver()

    def test_it_carries_the_seven_shared_keys(self):
        context = turn_context(self.state, resolver=self.resolver)
        self.assertEqual(
            set(context),
            {"text", "choices", "done", "turn_count", "image_urls", "transcript", "can_undo"},
        )

    def test_a_choice_carries_its_index_and_text(self):
        context = turn_context(self.state, resolver=self.resolver)
        for expected, choice in enumerate(context["choices"]):
            self.assertEqual(choice["index"], expected)
            self.assertIsInstance(choice["text"], str)

    def test_the_resolver_is_asked_for_this_turns_tags(self):
        turn_context(self.state, resolver=self.resolver)
        self.assertTrue(self.resolver.seen)

    def test_transcript_and_undo_come_from_the_caller(self):
        context = turn_context(self.state, resolver=self.resolver, transcript=[{"text": "a"}], can_undo=True)
        self.assertEqual(context["transcript"], [{"text": "a"}])
        self.assertTrue(context["can_undo"])

    def test_no_transcript_is_an_empty_list_not_none(self):
        self.assertEqual(turn_context(self.state, resolver=self.resolver)["transcript"], [])
