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
from ink_engine.game_panel import GamePanel


def _module(**members: Any) -> ModuleType:
    """Build a stand-in for a game's own `sidebar` module."""
    return SimpleNamespace(**members)  # type: ignore[return-value]


_QUIET = logging.getLogger("tests.game_panel")
_QUIET.addHandler(logging.NullHandler())
_QUIET.propagate = False


def _panel(module: ModuleType | None, **session: Any) -> GamePanel:
    """Build a `GamePanel` over empty session state unless told otherwise."""
    return GamePanel(
        module=module,
        engine_state=session.get("engine_state", {}),
        globals_=session.get("globals_", {}),
        bindings=session.get("bindings", {}),
        logger=_QUIET,
    )


class PanelContextTests(TestCase):
    def test_a_game_with_no_sidebar_module_gets_no_panel(self):
        self.assertIsNone(_panel(None).context())

    def test_a_module_without_the_hook_gets_no_panel(self):
        self.assertIsNone(_panel(_module()).context())

    def test_the_hooks_own_data_is_returned(self):
        module = _module(panel_context=lambda engine_state, globals_, bindings: {"rows": [1, 2]})
        self.assertEqual(_panel(module).context(), {"rows": [1, 2]})

    def test_a_hook_answering_the_wrong_type_is_discarded(self):
        """A panel that answers a string where data was expected is as
        unusable as no panel at all."""
        module = _module(panel_context=lambda engine_state, globals_, bindings: "not a mapping")
        self.assertIsNone(_panel(module).context())

    def test_a_raising_hook_is_survived(self):
        def _explode(engine_state, globals_, bindings):
            raise RuntimeError("boom")

        self.assertIsNone(_panel(_module(panel_context=_explode)).context())


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
        _panel(_module(panel_context=_hook), engine_state=engine_state, globals_=globals_, bindings=bindings).context()

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
        self.assertIsNone(_panel(_module(panel_context=_typo)).context())

    def test_engine_state_is_mutated_in_place(self):
        """A command hook writes into the session's own live state."""

        def _hook(engine_state, globals_, bindings, command_id, target_id):
            engine_state["last"] = f"{command_id}:{target_id}"
            return "done"

        engine_state: dict[str, Any] = {}
        result = _panel(_module(panel_command=_hook), engine_state=engine_state).command("use", "rope")
        self.assertEqual(result, "done")
        self.assertEqual(engine_state["last"], "use:rope")


class PanelActionAndCommandTests(TestCase):
    def test_an_action_answers_its_own_text(self):
        module = _module(panel_action=lambda engine_state, globals_, bindings, action_id, target_id: f"{action_id}:{target_id}")
        self.assertEqual(_panel(module).action("examine", "rope"), "examine:rope")

    def test_a_missing_action_hook_answers_empty(self):
        self.assertEqual(_panel(_module()).action("x", "y"), "")

    def test_a_raising_command_answers_empty(self):
        def _explode(engine_state, globals_, bindings, command_id, target_id):
            raise ValueError("boom")

        self.assertEqual(_panel(_module(panel_command=_explode)).command("use", "rope"), "")

    def test_a_command_answering_a_non_string_is_discarded(self):
        module = _module(panel_command=lambda engine_state, globals_, bindings, command_id, target_id: {"unexpected": True})
        self.assertEqual(_panel(module).command("use", "rope"), "")

    def test_a_hook_may_ask_the_same_questions_the_story_can(self):
        """Hooks receive the session's real bindings, not a reduced set."""
        module = _module(panel_action=lambda engine_state, globals_, bindings, action_id, target_id: bindings["where_is_now"]())
        self.assertEqual(_panel(module, bindings={"where_is_now": lambda: "museum"}).action("where", "gina"), "museum")


def _exit(to: str, position: str | None = None, *, passable: bool = True, knot: str | None = "k") -> dict[str, Any]:
    """Build one exit as `LocationGraph.exits_from()` returns it."""
    return {
        "to": to,
        "label": f"the {to}",
        "position": position,
        "passable": passable,
        "arrival_knot": knot,
        "travel_text": "Off you go." if knot else None,
    }


class ExitsSectionTests(TestCase):
    def test_a_section_is_a_compass_listing_every_exit(self):
        section = game_panel.exits_section([_exit("bar", "s"), _exit("cellar")])
        self.assertEqual(section["layout"], game_panel.COMPASS_LAYOUT)
        self.assertEqual(section["heading"], game_panel.EXITS_HEADING)
        self.assertEqual([exit_["id"] for exit_ in section["exits"]], ["position:s", "to:cellar"])

    def test_exits_with_no_position_and_no_knot_give_no_section(self):
        self.assertIsNone(game_panel.exits_section([_exit("bar", knot=None)]))

    def test_no_exits_give_no_section(self):
        self.assertIsNone(game_panel.exits_section([]))

    def test_a_positioned_exit_with_no_knot_is_drawn_but_not_passable(self):
        section = game_panel.exits_section([_exit("street", "n", knot=None)])
        self.assertFalse(section["exits"][0]["passable"])

    def test_a_blocked_exit_stays_blocked(self):
        section = game_panel.exits_section([_exit("street", "n", passable=False)])
        self.assertFalse(section["exits"][0]["passable"])


class FindExitTests(TestCase):
    def setUp(self):
        section = game_panel.exits_section([_exit("bar", "s"), _exit("street", "n", passable=False)])
        self.panel = {"panel_sections": [{"heading": "Pack", "rows": []}, section]}

    def test_a_passable_exit_is_found_by_id(self):
        self.assertEqual(game_panel.find_exit(self.panel, "position:s")["label"], "the bar")

    def test_a_blocked_exit_is_not_found(self):
        self.assertIsNone(game_panel.find_exit(self.panel, "position:n"))

    def test_an_unknown_id_or_no_panel_finds_nothing(self):
        self.assertIsNone(game_panel.find_exit(self.panel, "position:e"))
        self.assertIsNone(game_panel.find_exit(None, "position:s"))

    def test_a_compass_on_another_tab_is_found(self):
        panel = {"panel_sections": [], "panel_sections_by_tab": {"map": self.panel["panel_sections"]}}
        self.assertEqual(len(game_panel.compass_sections(panel)), 1)
        self.assertEqual(game_panel.find_exit(panel, "position:s")["label"], "the bar")


class ChoicesBesidePanelTests(TestCase):
    def setUp(self):
        self.choices = [{"index": 0, "text": "GO"}, {"index": 1, "text": "Look around"}]

    def test_a_compass_hides_the_movement_choice(self):
        panel = {"panel_sections": [game_panel.exits_section([_exit("bar", "s")])]}
        self.assertEqual(game_panel.choices_beside_panel(self.choices, panel), [{"index": 1, "text": "Look around"}])

    def test_without_a_compass_every_choice_stays(self):
        panel = {"panel_sections": [{"heading": "Pack", "rows": []}]}
        self.assertEqual(game_panel.choices_beside_panel(self.choices, panel), self.choices)
        self.assertEqual(game_panel.choices_beside_panel(self.choices, None), self.choices)


class PanelSlotTests(TestCase):
    """Sections a game places in `panel_slots`, below the active tab."""

    def test_a_compass_in_a_slot_is_found(self):
        """A compass in a slot is found."""
        panel = {"panel_sections": [{"heading": "Pack", "rows": []}], "panel_slots": [game_panel.exits_section([_exit("bar", "s")])]}
        self.assertEqual(len(game_panel.compass_sections(panel)), 1)
        self.assertEqual(game_panel.find_exit(panel, "position:s")["label"], "the bar")

    def test_a_compass_in_a_slot_hides_the_movement_choice(self):
        """A compass in a slot hides the movement choice."""
        panel = {"panel_slots": [game_panel.exits_section([_exit("bar", "s")])]}
        choices = [{"index": 0, "text": "GO"}, {"index": 1, "text": "Look around"}]
        self.assertEqual(game_panel.choices_beside_panel(choices, panel), [{"index": 1, "text": "Look around"}])


def _answering(answer: Any) -> ModuleType:
    """Build a sidebar whose `panel_command` answers `answer`."""
    return _module(panel_command=lambda engine_state, globals_, bindings, command_id, target_id: answer)


class CommandResultTests(TestCase):
    """`GamePanel.command_result()`: a message, or a knot to play as the reaction."""

    def test_a_string_is_a_message_only(self):
        """A plain answer is a message; no knot, so the story does not advance."""
        self.assertEqual(_panel(_answering("Too heavy.")).command_result("use", "rope"), game_panel.CommandResult(message="Too heavy."))

    def test_a_knot_answer_names_the_reaction(self):
        """`knot` alone: no message, no label."""
        self.assertEqual(_panel(_answering({"knot": "rope_used"})).command_result("use", "rope"), game_panel.CommandResult(knot="rope_used"))

    def test_message_and_label_come_with_the_knot(self):
        """All three fields, as the game gave them."""
        answer = {"knot": "rope_used", "message": "You uncoil the rope.", "label": "Use the rope"}
        expected = game_panel.CommandResult(message="You uncoil the rope.", knot="rope_used", label="Use the rope")
        self.assertEqual(_panel(_answering(answer)).command_result("use", "rope"), expected)

    def test_the_label_defaults_to_the_message(self):
        """A knot answer with a message and no label records the message."""
        result = _panel(_answering({"knot": "rope_used", "message": "You uncoil the rope."})).command_result("use", "rope")
        self.assertEqual(result.label, "You uncoil the rope.")

    def test_a_malformed_answer_is_discarded(self):
        """No string `knot`, or a non-string field: treated as no answer."""
        for answer in ({"knot": 5}, {"message": "no knot"}, {"knot": "rope_used", "label": 3}, 42):
            with self.subTest(answer=answer):
                self.assertEqual(_panel(_answering(answer)).command_result("use", "rope"), game_panel.CommandResult())

    def test_command_still_answers_the_message(self):
        """`command()` is the message part of `command_result()`."""
        self.assertEqual(_panel(_answering({"knot": "rope_used", "message": "Done."})).command("use", "rope"), "Done.")
