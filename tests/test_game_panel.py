"""Calling a game's own side-panel hooks.

Exercised against real modules rather than mocks, since the thing worth
proving is how an ordinary Python function object gets called.
"""

from __future__ import annotations

import logging
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import TestCase

from ink_engine import game_panel


def _module(**members: Any) -> ModuleType:
    """Build a stand-in for a game's own `sidebar` module."""
    return SimpleNamespace(**members)  # type: ignore[return-value]


_QUIET = logging.getLogger("tests.game_panel")
_QUIET.addHandler(logging.NullHandler())
_QUIET.propagate = False


class PanelContextTests(TestCase):
    def test_a_game_with_no_sidebar_module_gets_no_panel(self):
        self.assertIsNone(game_panel.panel_context(None, engine_state={}, globals_={}, bindings={}))

    def test_a_module_without_the_hook_gets_no_panel(self):
        self.assertIsNone(game_panel.panel_context(_module(), engine_state={}, globals_={}, bindings={}))

    def test_the_hooks_own_data_is_returned(self):
        module = _module(panel_context=lambda engine_state, globals_, bindings: {"rows": [1, 2]})
        self.assertEqual(game_panel.panel_context(module, engine_state={}, globals_={}, bindings={}), {"rows": [1, 2]})

    def test_a_hook_answering_the_wrong_type_is_discarded(self):
        """A panel that answers a string where data was expected is as
        unusable as no panel at all."""
        module = _module(panel_context=lambda engine_state, globals_, bindings: "not a mapping")
        self.assertIsNone(game_panel.panel_context(module, engine_state={}, globals_={}, bindings={}))

    def test_a_raising_hook_is_survived(self):
        def _explode(engine_state, globals_, bindings):
            raise RuntimeError("boom")

        self.assertIsNone(game_panel.panel_context(_module(panel_context=_explode), engine_state={}, globals_={}, bindings={}, logger=_QUIET))


class HookArgumentTests(TestCase):
    """Every hook is called by keyword, so its parameter ORDER is its own
    business. This is the property that kept two applications from disagreeing."""

    def test_a_hook_declaring_an_unusual_order_still_receives_the_right_values(self):
        seen: dict[str, Any] = {}

        # Deliberately not the conventional order.
        def _hook(bindings, globals_, engine_state):
            seen.update(engine_state=engine_state, globals_=globals_, bindings=bindings)
            return {}

        engine_state = {"slot": 1}
        globals_ = {"who": "gina"}
        bindings = {"where_is_now": lambda: "market"}
        game_panel.panel_context(_module(panel_context=_hook), engine_state=engine_state, globals_=globals_, bindings=bindings)

        self.assertIs(seen["engine_state"], engine_state)
        self.assertIs(seen["globals_"], globals_)
        self.assertIs(seen["bindings"], bindings)

    def test_a_hook_misspelling_a_parameter_fails_rather_than_receiving_the_wrong_value(self):
        """The failure mode keyword calling buys: a wrong NAME cannot be
        silently satisfied by position."""

        def _typo(engine_state, globals_, binding):  # 'binding', not 'bindings'
            return {}

        # Surfaces as a TypeError the hook caller reports and survives,
        # rather than binding `globals_` into `binding`.
        self.assertIsNone(game_panel.panel_context(_module(panel_context=_typo), engine_state={}, globals_={}, bindings={}, logger=_QUIET))

    def test_engine_state_is_mutated_in_place(self):
        """A command hook writes into the session's own live state."""

        def _hook(engine_state, globals_, bindings, command_id, target_id):
            engine_state["last"] = f"{command_id}:{target_id}"
            return "done"

        engine_state: dict[str, Any] = {}
        result = game_panel.panel_command(
            _module(panel_command=_hook), engine_state=engine_state, globals_={}, bindings={}, command_id="use", target_id="rope"
        )
        self.assertEqual(result, "done")
        self.assertEqual(engine_state["last"], "use:rope")


class PanelActionAndCommandTests(TestCase):
    def test_an_action_answers_its_own_text(self):
        module = _module(panel_action=lambda engine_state, globals_, bindings, action_id, target_id: f"{action_id}:{target_id}")
        self.assertEqual(
            game_panel.panel_action(module, engine_state={}, globals_={}, bindings={}, action_id="examine", target_id="rope"),
            "examine:rope",
        )

    def test_a_missing_action_hook_answers_empty(self):
        self.assertEqual(game_panel.panel_action(_module(), engine_state={}, globals_={}, bindings={}, action_id="x", target_id="y"), "")

    def test_a_raising_command_answers_empty(self):
        def _explode(engine_state, globals_, bindings, command_id, target_id):
            raise ValueError("boom")

        self.assertEqual(
            game_panel.panel_command(
                _module(panel_command=_explode), engine_state={}, globals_={}, bindings={}, command_id="use", target_id="rope", logger=_QUIET
            ),
            "",
        )

    def test_a_command_answering_a_non_string_is_discarded(self):
        module = _module(panel_command=lambda engine_state, globals_, bindings, command_id, target_id: {"unexpected": True})
        self.assertEqual(
            game_panel.panel_command(module, engine_state={}, globals_={}, bindings={}, command_id="use", target_id="rope"),
            "",
        )

    def test_a_hook_may_ask_the_same_questions_the_story_can(self):
        """Hooks receive the session's real bindings, not a reduced set."""
        module = _module(panel_action=lambda engine_state, globals_, bindings, action_id, target_id: bindings["where_is_now"]())
        self.assertEqual(
            game_panel.panel_action(
                module, engine_state={}, globals_={}, bindings={"where_is_now": lambda: "museum"}, action_id="where", target_id="gina"
            ),
            "museum",
        )
