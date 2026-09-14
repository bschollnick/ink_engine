"""The generic quest plugin (ink_engine.engine_plugins.quests).

SimpleTestCase throughout, and fixture ids only (`quest_a`, `goal_1`,
`subquest_x`): the engine layer must never learn any one story's
vocabulary, so these tests are written so they would read identically for
any game.
"""

from __future__ import annotations

import json
from unittest import TestCase as SimpleTestCase

from ink_engine.engine_plugins.quests import (
    PLUGIN,
    UNSTARTED_STAGE,
    JournalEntry,
    Quests,
    QuestSpec,
    unreachable_goals,
)

# A catalog exercising every structural feature at once: a parent with two
# required children and one optional child, goals on both a parent and a
# child, and a bare stage-only quest with no goals at all.
CATALOG: dict[str, QuestSpec] = {
    "quest_a": QuestSpec(
        quest_id="quest_a",
        goal_ids=("goal_1", "goal_2"),
        requires=("subquest_x", "subquest_y"),
        final_stage=100,
    ),
    "subquest_x": QuestSpec(quest_id="subquest_x", parent_id="quest_a", goal_ids=("goal_3",), final_stage=10),
    "subquest_y": QuestSpec(quest_id="subquest_y", parent_id="quest_a", final_stage=10),
    "subquest_z": QuestSpec(quest_id="subquest_z", parent_id="quest_a", final_stage=10),
    "quest_b": QuestSpec(quest_id="quest_b", final_stage=5),
}

QUESTS = Quests(name="catalogued", catalog=CATALOG)


def _slot():
    return QUESTS.init_state(None)


class QuestStageTests(SimpleTestCase):
    """Stage reads, writes, and the never-regress guard."""

    def test_an_untouched_quest_reports_the_unstarted_stage(self):
        """A story compares stages against thresholds, so the floor must
        be a real number rather than None."""
        self.assertEqual(UNSTARTED_STAGE, QUESTS.quest_stage(_slot(), "quest_a"))
        self.assertFalse(QUESTS.is_quest_started(_slot(), "quest_a"))

    def test_starting_a_quest_records_it(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_a")
        self.assertTrue(QUESTS.is_quest_started(slot, "quest_a"))
        self.assertEqual(1, QUESTS.quest_stage(slot, "quest_a"))

    def test_starting_an_already_started_quest_does_not_reset_progress(self):
        """A re-enterable scene must not knock a quest back to stage 1."""
        slot = _slot()
        QUESTS.start_quest(slot, "quest_a")
        QUESTS.advance_quest(slot, "quest_a", 50)
        QUESTS.start_quest(slot, "quest_a")
        self.assertEqual(50, QUESTS.quest_stage(slot, "quest_a"))

    def test_advance_moves_a_quest_forward(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 20)
        self.assertEqual(20, QUESTS.quest_stage(slot, "quest_a"))

    def test_advance_refuses_to_regress(self):
        """Mirrors source's own `if (getQuestX() < n)` guard, so a scene
        reached out of order cannot undo progress."""
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 50)
        QUESTS.advance_quest(slot, "quest_a", 20)
        self.assertEqual(50, QUESTS.quest_stage(slot, "quest_a"))
        QUESTS.advance_quest(slot, "quest_a", 50)
        self.assertEqual(50, QUESTS.quest_stage(slot, "quest_a"))

    def test_set_stage_still_allows_regression(self):
        """The escape hatch for a failed path being reset for a retry."""
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 900)
        QUESTS.set_quest_stage(slot, "quest_a", 6)
        self.assertEqual(6, QUESTS.quest_stage(slot, "quest_a"))


class QuestGoalTests(SimpleTestCase):
    """Goals: idempotent, per-quest scoped, and countable."""

    def test_meeting_a_goal_records_it(self):
        slot = _slot()
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        self.assertTrue(QUESTS.is_goal_met(slot, "quest_a", "goal_1"))

    def test_meeting_a_goal_twice_records_it_once(self):
        """A re-entered scene must not make an "N of M" count drift."""
        slot = _slot()
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        self.assertEqual(["goal_1"], QUESTS.met_goals(slot, "quest_a"))

    def test_goal_ids_are_scoped_per_quest(self):
        slot = _slot()
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        self.assertFalse(QUESTS.is_goal_met(slot, "quest_b", "goal_1"))

    def test_outstanding_goals_follows_catalog_order(self):
        """The journal renders in this order, so it must be the catalog's
        rather than the order the player happened to meet them."""
        slot = _slot()
        self.assertEqual(["goal_1", "goal_2"], QUESTS.outstanding_goals(slot, "quest_a"))
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        self.assertEqual(["goal_2"], QUESTS.outstanding_goals(slot, "quest_a"))

    def test_outstanding_goals_is_empty_for_an_undeclared_quest(self):
        self.assertEqual([], QUESTS.outstanding_goals(_slot(), "quest_missing"))


class QuestCompletionTests(SimpleTestCase):
    """Completion, including required vs. optional subquests."""

    def _parent_at_final_stage_with_goals(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 100)
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        QUESTS.meet_goal(slot, "quest_a", "goal_2")
        return slot

    def test_a_stage_only_quest_completes_at_its_final_stage(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_b", 4)
        self.assertFalse(QUESTS.is_complete(slot, "quest_b"))
        QUESTS.advance_quest(slot, "quest_b", 5)
        self.assertTrue(QUESTS.is_complete(slot, "quest_b"))

    def test_a_parent_is_incomplete_while_a_required_subquest_is(self):
        """The motivating property: without it, every site that cares has
        to hand-check the children, which is how a stage gets missed."""
        self.assertFalse(QUESTS.is_complete(self._parent_at_final_stage_with_goals(), "quest_a"))

    def test_a_parent_completes_once_every_requirement_is_met(self):
        slot = self._parent_at_final_stage_with_goals()
        QUESTS.meet_goal(slot, "subquest_x", "goal_3")
        QUESTS.advance_quest(slot, "subquest_x", 10)
        QUESTS.advance_quest(slot, "subquest_y", 10)
        self.assertTrue(QUESTS.is_complete(slot, "quest_a"))

    def test_an_optional_subquest_does_not_block_its_parent(self):
        """subquest_z nests in the journal but is absent from `requires`."""
        slot = self._parent_at_final_stage_with_goals()
        QUESTS.meet_goal(slot, "subquest_x", "goal_3")
        QUESTS.advance_quest(slot, "subquest_x", 10)
        QUESTS.advance_quest(slot, "subquest_y", 10)
        QUESTS.start_quest(slot, "subquest_z")
        self.assertFalse(QUESTS.is_complete(slot, "subquest_z"))
        self.assertTrue(QUESTS.is_complete(slot, "quest_a"))

    def test_an_unmet_goal_blocks_completion_even_at_the_final_stage(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "subquest_x", 10)
        self.assertFalse(QUESTS.is_complete(slot, "subquest_x"))
        QUESTS.meet_goal(slot, "subquest_x", "goal_3")
        self.assertTrue(QUESTS.is_complete(slot, "subquest_x"))

    def test_remaining_requirements_reports_which_children_are_outstanding(self):
        slot = _slot()
        QUESTS.meet_goal(slot, "subquest_x", "goal_3")
        QUESTS.advance_quest(slot, "subquest_x", 10)
        self.assertEqual(["subquest_y"], QUESTS.remaining_requirements(slot, "quest_a"))

    def test_a_quest_declaring_no_ending_never_reports_complete(self):
        """Silently calling such a quest finished would hide a catalog
        that forgot to say how it ends."""
        endless = Quests(name="endless", catalog={"quest_c": QuestSpec(quest_id="quest_c")})
        slot = endless.init_state(None)
        endless.advance_quest(slot, "quest_c", 9999)
        self.assertFalse(endless.is_complete(slot, "quest_c"))

    def test_an_undeclared_quest_is_never_complete(self):
        self.assertFalse(QUESTS.is_complete(_slot(), "quest_missing"))


class QuestFailureTests(SimpleTestCase):
    """Failure is tracked apart from stages."""

    def test_a_quest_starts_unfailed(self):
        self.assertFalse(QUESTS.is_quest_failed(_slot(), "quest_a"))

    def test_failing_a_quest_records_it(self):
        slot = _slot()
        QUESTS.fail_quest(slot, "quest_a")
        self.assertTrue(QUESTS.is_quest_failed(slot, "quest_a"))

    def test_failing_twice_records_once(self):
        slot = _slot()
        QUESTS.fail_quest(slot, "quest_a")
        QUESTS.fail_quest(slot, "quest_a")
        self.assertEqual(["quest_a"], slot["failed"])

    def test_failing_does_not_disturb_stage_or_goals(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 40)
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        QUESTS.fail_quest(slot, "quest_a")
        self.assertEqual(40, QUESTS.quest_stage(slot, "quest_a"))
        self.assertTrue(QUESTS.is_goal_met(slot, "quest_a", "goal_1"))


class QuestJournalTests(SimpleTestCase):
    """Journal assembly: structure only, never player-facing wording."""

    def test_an_untouched_journal_is_empty(self):
        self.assertEqual([], QUESTS.journal_entries(_slot()))

    def test_only_started_quests_appear(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_b")
        self.assertEqual(["quest_b"], [entry.quest_id for entry in QUESTS.journal_entries(slot)])

    def test_started_children_nest_under_their_parent(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_a")
        QUESTS.start_quest(slot, "subquest_x")
        entries = QUESTS.journal_entries(slot)
        self.assertEqual(["quest_a"], [entry.quest_id for entry in entries])
        self.assertEqual(["subquest_x"], [child.quest_id for child in entries[0].children])

    def test_a_started_child_of_an_unstarted_parent_is_promoted(self):
        """Dropping it would silently lose a quest the player really began."""
        slot = _slot()
        QUESTS.start_quest(slot, "subquest_x")
        self.assertEqual(["subquest_x"], [entry.quest_id for entry in QUESTS.journal_entries(slot)])

    def test_an_entry_carries_stage_goals_and_flags(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_a")
        QUESTS.advance_quest(slot, "quest_a", 40)
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        entry = QUESTS.journal_entries(slot)[0]
        self.assertEqual(40, entry.stage)
        self.assertEqual(("goal_1",), entry.met)
        self.assertEqual(("goal_2",), entry.outstanding)
        self.assertFalse(entry.complete)
        self.assertFalse(entry.failed)

    def test_an_entry_reports_failure(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_b")
        QUESTS.fail_quest(slot, "quest_b")
        self.assertTrue(QUESTS.journal_entries(slot)[0].failed)

    def test_entries_carry_no_player_facing_text(self):
        slot = _slot()
        QUESTS.start_quest(slot, "quest_a")
        entry = QUESTS.journal_entries(slot)[0]
        self.assertEqual({"quest_id", "stage", "complete", "failed", "met", "outstanding", "children"}, set(vars(entry)))
        self.assertIsInstance(entry, JournalEntry)


class QuestSerializationTests(SimpleTestCase):
    """State must survive the session round-trip."""

    def test_a_populated_slot_round_trips_through_json(self):
        slot = _slot()
        QUESTS.advance_quest(slot, "quest_a", 40)
        QUESTS.meet_goal(slot, "quest_a", "goal_1")
        QUESTS.fail_quest(slot, "quest_b")
        restored = json.loads(json.dumps(slot))
        self.assertEqual(40, QUESTS.quest_stage(restored, "quest_a"))
        self.assertTrue(QUESTS.is_goal_met(restored, "quest_a", "goal_1"))
        self.assertTrue(QUESTS.is_quest_failed(restored, "quest_b"))

    def test_a_save_missing_keys_is_repaired_on_bind(self):
        """A session saved before this plugin existed must still load."""
        old_save: dict = {}
        PLUGIN.bind(old_save, {}, {})
        self.assertEqual(UNSTARTED_STAGE, QUESTS.quest_stage(old_save, "quest_a"))
        self.assertEqual([], old_save["failed"])


class QuestInertWhenUnusedTests(SimpleTestCase):
    """A story declaring no quests pays nothing and crashes nowhere."""

    def test_every_query_answers_empty_against_an_empty_catalog(self):
        empty = Quests(name="empty")
        slot = empty.init_state(None)
        self.assertEqual([], empty.journal_entries(slot))
        self.assertEqual([], empty.outstanding_goals(slot, "anything"))
        self.assertEqual([], empty.remaining_requirements(slot, "anything"))
        self.assertFalse(empty.is_complete(slot, "anything"))
        self.assertFalse(empty.is_quest_started(slot, "anything"))
        self.assertEqual(UNSTARTED_STAGE, empty.quest_stage(slot, "anything"))

    def test_an_unused_slot_is_empty_containers(self):
        self.assertEqual({"stages": {}, "met_goals": {}, "failed": []}, PLUGIN.init_state(None))


class QuestUnreachableGoalAuditTests(SimpleTestCase):
    """The audit the surveyed prior art lacks."""

    def test_a_goal_no_scene_can_meet_is_reported(self):
        self.assertEqual([("quest_a", "goal_2"), ("subquest_x", "goal_3")], unreachable_goals(CATALOG, {"goal_1"}))

    def test_a_fully_reachable_catalog_reports_nothing(self):
        self.assertEqual([], unreachable_goals(CATALOG, {"goal_1", "goal_2", "goal_3"}))


class BindingTests(SimpleTestCase):
    """The EXTERNAL surface a story actually calls -- the catalog-free
    half. A host that holds the catalog calls `is_complete()` and
    `journal_entries()` directly in Python; Ink passes scalars, never a
    catalog."""

    def setUp(self):
        self.slot = PLUGIN.init_state(None)
        self.bindings = PLUGIN.bind(self.slot, {}, {})

    def test_the_bindings_are_published_under_the_method_names(self):
        self.assertEqual(
            sorted(self.bindings),
            [
                "advance_quest",
                "fail_quest",
                "is_goal_met",
                "is_quest_failed",
                "is_quest_started",
                "meet_goal",
                "quest_stage",
                "set_quest_stage",
                "start_quest",
            ],
        )

    def test_writes_persist_into_the_session_slot(self):
        self.bindings["start_quest"]("quest_a", 1)
        self.assertEqual(self.slot["stages"]["quest_a"], 1)

    def test_stage_start_advance_round_trip_through_the_bindings(self):
        self.assertEqual(self.bindings["quest_stage"]("quest_a"), UNSTARTED_STAGE)
        self.assertFalse(self.bindings["is_quest_started"]("quest_a"))
        self.bindings["start_quest"]("quest_a", 1)
        self.assertTrue(self.bindings["is_quest_started"]("quest_a"))
        self.bindings["advance_quest"]("quest_a", 3)
        self.assertEqual(self.bindings["quest_stage"]("quest_a"), 3)
        self.bindings["advance_quest"]("quest_a", 1)  # regression is a no-op
        self.assertEqual(self.bindings["quest_stage"]("quest_a"), 3)

    def test_set_quest_stage_allows_regression(self):
        self.bindings["start_quest"]("quest_a", 5)
        self.bindings["set_quest_stage"]("quest_a", 1)
        self.assertEqual(self.bindings["quest_stage"]("quest_a"), 1)

    def test_goal_met_round_trips_through_the_bindings(self):
        self.assertFalse(self.bindings["is_goal_met"]("quest_a", "goal_1"))
        self.bindings["meet_goal"]("quest_a", "goal_1")
        self.assertTrue(self.bindings["is_goal_met"]("quest_a", "goal_1"))

    def test_fail_quest_round_trips_through_the_bindings(self):
        self.assertFalse(self.bindings["is_quest_failed"]("quest_a"))
        self.bindings["fail_quest"]("quest_a")
        self.assertTrue(self.bindings["is_quest_failed"]("quest_a"))

    def test_the_plugin_declares_its_own_state_slot(self):
        self.assertEqual(PLUGIN.state_key, "quests")
