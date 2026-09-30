"""The `divert_to_knot` EXTERNAL every `InkRuntimeState` binds itself
(ink_engine.engine.resolve_divert_target, DIVERT_TO_KNOT_EXTERNAL_NAME).

Driven against a real compiled fixture (tests/fixtures/dynamic_divert.ink):
a story that declares the EXTERNAL, an Ink fallback that diverts
somewhere else, and a `go(knot_path)` knot that proves the returned
target is a real divert, not just a value that happens to compare equal.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine.engine import (
    Container,
    InkRuntimeState,
    NotAFunctionError,
    ResolvedDivertTarget,
    UnknownDivertTargetError,
    load_story_root,
    resolve_divert_target,
)

FIXTURES = FilePath(__file__).parent / "fixtures"


def _story() -> InkRuntimeState:
    with open(FIXTURES / "dynamic_divert.ink.json", encoding="utf-8") as fixture_file:
        state = InkRuntimeState(load_story_root(json.load(fixture_file)))
    state.continue_story()
    return state


class ResolveDivertTargetTests(SimpleTestCase):
    """The module-level function, used directly against a story root."""

    def test_a_known_knot_resolves_to_its_container(self):
        state = _story()
        target = resolve_divert_target(state.root, "a_destination")
        self.assertIsInstance(target, ResolvedDivertTarget)
        self.assertIsInstance(target.container, Container)

    def test_a_knot_dot_stitch_path_resolves_to_the_stitch(self):
        state = _story()
        target = resolve_divert_target(state.root, "a_stitched_knot.a_stitch")
        self.assertEqual(target.container.name, "a_stitch")

    def test_an_unknown_path_is_refused(self):
        state = _story()
        with self.assertRaises(UnknownDivertTargetError):
            resolve_divert_target(state.root, "no_such_knot")


class BuiltinBindingTests(SimpleTestCase):
    """Every `InkRuntimeState` binds `divert_to_knot` itself, unasked."""

    def test_the_binding_is_present_with_no_application_bindings(self):
        state = _story()
        self.assertIn("divert_to_knot", state.engine_bindings)

    def test_an_application_binding_dict_does_not_omit_it(self):
        with open(FIXTURES / "dynamic_divert.ink.json", encoding="utf-8") as fixture_file:
            state = InkRuntimeState(load_story_root(json.load(fixture_file)), engine_bindings={})
        self.assertIn("divert_to_knot", state.engine_bindings)

    def test_the_story_can_call_it_and_get_a_real_divert_target(self):
        state = _story()
        result, _ = state.evaluate_function("resolve", "a_destination")
        self.assertIsInstance(result, ResolvedDivertTarget)
        self.assertEqual(result.container.name, "a_destination")

    def test_diverting_to_the_returned_target_actually_moves_the_story(self):
        state = _story()
        state.choose_path("go", "a_destination")
        text = state.continue_story()
        self.assertIn("You arrive at the destination.", text)

    def test_an_unknown_path_raised_through_the_story_names_the_cause(self):
        # evaluate_function() wraps every mid-evaluation error in
        # NotAFunctionError (engine.py's evaluate_function, "raised
        # against a discarded copy"); the underlying UnknownDivertTargetError
        # is preserved in its message and as __cause__.
        state = _story()
        with self.assertRaises(NotAFunctionError) as raised:
            state.evaluate_function("resolve", "no_such_knot")
        self.assertIsInstance(raised.exception.__cause__, UnknownDivertTargetError)
