"""A generic quest/goal/journal framework for Ink stories.

**Three separated concepts:**

* A **quest** has a numeric *stage*, a plain int compared against
  thresholds the game defines.
* A **goal** is one discrete objective, met or outstanding. Goals hang
  off a quest and carry no stage of their own.
* The **journal** is assembled here but worded by the game: this module
  produces structure, never a player-facing string.

**Structure is definition; progress is state.** Which quests exist, which
are subquests of which, and what any stage means live in the game's
catalog, a `dict[str, QuestSpec]` handed to the plugin's constructor; the
slot carries only what a session changed.

A story that declares no quests gets empty answers everywhere, never a
raise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, TypedDict

from ink_engine.plugin_base import StatefulPlugin, external, query

#: Where this plugin's state lives in a session's `EngineState`.
STATE_KEY = "quests"

# Stories compare stages against thresholds, so the unstarted value must
# be lower than any stage a game would author; 0 is that floor.
# `is_quest_started` exists so a story never has to encode the convention.
UNSTARTED_STAGE = 0


@dataclass(frozen=True)
class QuestSpec:
    """One quest's immutable structure, owned by the game's catalog.

    Frozen: a catalog is shared by every session.

    Args:
        quest_id: The catalog's opaque id for this quest.
        goal_ids: Every goal belonging to this quest, in the order a
            journal should list them. A quest with no goals is normal --
            plenty of progressions are a bare stage counter.
        requires: Ids of subquests that must complete before this quest
            can. A child NOT listed here still nests in the journal and
            tracks its own stages but does not block its parent, so a
            story can show optional side-work without a second mechanism.
        parent_id: The quest this one nests under in the journal, or None
            for a top-level quest.
        final_stage: The stage at or above which this quest counts as
            complete, or None when completion is decided only by goals
            and required subquests.
    """

    quest_id: str
    goal_ids: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    parent_id: str | None = None
    final_stage: int | None = None


class QuestSlot(TypedDict):
    """A session's quest progress.

    Attributes:
        stages: quest_id -> current stage. A quest absent from this dict
            has never started.
        met_goals: quest_id -> the goal ids met so far. Stored per quest
            rather than as one flat list so two quests may reuse a goal
            id without colliding.
        failed: Quest ids that ended badly. Kept separate from stages so
            the engine can answer "did this fail" without knowing which
            number a given story uses as a failure sentinel.
    """

    stages: dict[str, int]
    met_goals: dict[str, list[str]]
    failed: list[str]


@dataclass(frozen=True)
class JournalEntry:
    """One quest's own line in an assembled journal, plus its children.

    Carries structure and ids only. Every player-facing string is the
    game's to supply, keyed off these ids -- which is what keeps this
    module free of any one story's wording.

    Args:
        quest_id: The quest this entry describes.
        stage: Its current stage.
        complete: Whether it is finished.
        failed: Whether it ended badly.
        met: Goal ids already met, in catalog order.
        outstanding: Goal ids still to do, in catalog order.
        children: Entries for its subquests, one level deep.
    """

    quest_id: str
    stage: int
    complete: bool
    failed: bool
    met: tuple[str, ...]
    outstanding: tuple[str, ...]
    children: tuple[JournalEntry, ...] = ()


def unreachable_goals(catalog: dict[str, QuestSpec], reachable_goal_ids: set[str]) -> list[tuple[str, str]]:
    """Report goals a catalog declares that nothing can ever meet.

    A goal no scene ever meets is a quest that silently never finishes.
    A question about the catalog alone, so it needs no plugin.

    Args:
        catalog: The game's quest catalog.
        reachable_goal_ids: Every goal id some scene actually meets,
            gathered by the caller from the story source.

    Returns:
        (quest_id, goal_id) pairs for declared goals nothing can meet, in
        catalog order. Empty is the healthy answer.
    """
    return [(spec.quest_id, goal_id) for spec in catalog.values() for goal_id in spec.goal_ids if goal_id not in reachable_goal_ids]


class Quests(StatefulPlugin[QuestSlot]):
    """Quest stages, goals and failures over a game's catalog.

    A game instantiates this with its catalog, or subclasses it to add
    its own bindings on top: `Quests(name="my_quests", catalog=CATALOG)`.
    """

    name = "quests"
    display_name = "Quests"
    state_key = STATE_KEY
    slot_type = QuestSlot
    fields: ClassVar[dict[str, Callable[[], Any]]] = {"stages": dict, "met_goals": dict, "failed": list}

    def __init__(
        self,
        *,
        name: str | None = None,
        display_name: str | None = None,
        state_key: str | None = None,
        catalog: dict[str, QuestSpec] | None = None,
    ) -> None:
        """Build a quest plugin over a catalog.

        Args:
            name: Override the plugin name, for a game's copy.
            display_name: Override the display name.
            catalog: The game's quest catalog, or None for a plugin whose
                catalog-free operations (stages, goals, failures) are all
                a story uses.
        """
        super().__init__(name=name, display_name=display_name, state_key=state_key)
        self.catalog: dict[str, QuestSpec] = dict(catalog or {})

    # -- stages ---------------------------------------------------------------

    @query
    @external
    def quest_stage(self, slot: QuestSlot, quest_id: str) -> int:
        """Return a quest's current stage.

        Args:
            slot: This session's slot.
            quest_id: The quest to read.

        Returns:
            The current stage, or `UNSTARTED_STAGE` for a quest never
            started.
        """
        return slot.get("stages", {}).get(quest_id, UNSTARTED_STAGE)

    @query
    @external
    def is_quest_started(self, slot: QuestSlot, quest_id: str) -> bool:
        """Return whether the player has encountered a quest at all.

        Args:
            slot: This session's slot.
            quest_id: The quest to test.

        Returns:
            True once the quest has any stage recorded. A journal uses
            this to decide whether a quest is visible at all.
        """
        return quest_id in slot.get("stages", {})

    @external
    def start_quest(self, slot: QuestSlot, quest_id: str, stage: int = 1) -> None:
        """Begin a quest, if it has not begun already.

        Idempotent: a scene the player can re-enter cannot reset progress
        by starting the quest again.

        Args:
            slot: This session's slot.
            quest_id: The quest to start.
            stage: The stage to start at.
        """
        if not self.is_quest_started(slot, quest_id):
            slot.setdefault("stages", {})[quest_id] = stage

    @external
    def set_quest_stage(self, slot: QuestSlot, quest_id: str, stage: int) -> None:
        """Set a quest's stage unconditionally, including backwards.

        The escape hatch for a story that resets a failed path to an
        earlier stage so it can be retried. Ordinary progress uses
        `advance_quest()`, which cannot regress by accident.

        Args:
            slot: This session's slot.
            quest_id: The quest to move.
            stage: The stage to move it to.
        """
        slot.setdefault("stages", {})[quest_id] = stage

    @external
    def advance_quest(self, slot: QuestSlot, quest_id: str, stage: int) -> None:
        """Move a quest forward, never backward.

        Mirrors the `if (getQuestX() < n) setQuestX(n)` guard stories
        write by hand at each advance site. Advancing to a lower or equal
        stage is a no-op rather than an error, since the guard exists so
        that a re-entered scene is harmless.

        Args:
            slot: This session's slot.
            quest_id: The quest to advance.
            stage: The stage to advance to.
        """
        if stage > self.quest_stage(slot, quest_id):
            slot.setdefault("stages", {})[quest_id] = stage

    # -- goals ----------------------------------------------------------------

    @external
    def meet_goal(self, slot: QuestSlot, quest_id: str, goal_id: str) -> None:
        """Mark one goal met.

        Idempotent: re-entering the scene that completes a goal must not
        count it twice, or any "N of M done" report drifts.

        Args:
            slot: This session's slot.
            quest_id: The quest the goal belongs to.
            goal_id: The goal to mark met.
        """
        met = slot.setdefault("met_goals", {}).setdefault(quest_id, [])
        if goal_id not in met:
            met.append(goal_id)

    @query
    @external
    def is_goal_met(self, slot: QuestSlot, quest_id: str, goal_id: str) -> bool:
        """Return whether one goal has been met.

        Args:
            slot: This session's slot.
            quest_id: The quest the goal belongs to.
            goal_id: The goal to test.

        Returns:
            True once the goal is met.
        """
        return goal_id in slot.get("met_goals", {}).get(quest_id, [])

    def met_goals(self, slot: QuestSlot, quest_id: str) -> list[str]:
        """Return every goal met on a quest, in the order they were met.

        Args:
            slot: This session's slot.
            quest_id: The quest to read.

        Returns:
            A copy of the met-goal list, empty for an untouched quest.
        """
        return list(slot.get("met_goals", {}).get(quest_id, []))

    def outstanding_goals(self, slot: QuestSlot, quest_id: str) -> list[str]:
        """Return a quest's goals that are still unmet, in catalog order.

        Args:
            slot: This session's slot.
            quest_id: The quest to read.

        Returns:
            The unmet goal ids. Empty for a quest with no goals, or one
            the catalog does not declare.
        """
        spec = self.catalog.get(quest_id)
        if spec is None:
            return []
        return [goal_id for goal_id in spec.goal_ids if not self.is_goal_met(slot, quest_id, goal_id)]

    # -- completion -----------------------------------------------------------

    @external
    def finish_quest(self, slot: QuestSlot, quest_id: str) -> bool:
        """Mark a quest finished, whatever its catalog says finishing means.

        Meets every declared goal and moves the stage to `final_stage`, so
        `is_complete()` then answers True without the caller having to know
        either. Idempotent, and safe to call on a quest never started.

        A quest whose catalog entry declares no goals and no `final_stage`
        has no stated ending, so there is nothing to satisfy; it is left
        alone, matching `is_complete()`'s own refusal to call such a quest
        finished. Required subquests are NOT finished recursively -- a
        questline ends when its parts do, so finish those first.

        Args:
            slot: This session's slot.
            quest_id: The quest to finish.

        Returns:
            True if the quest now reports complete, False if its catalog
            gives no way to finish it, or it is unknown.
        """
        spec = self.catalog.get(quest_id)
        if spec is None:
            return False
        for goal_id in spec.goal_ids:
            self.meet_goal(slot, quest_id, goal_id)
        if spec.final_stage is not None:
            self.set_quest_stage(slot, quest_id, spec.final_stage)
        return self.is_complete(slot, quest_id)

    # -- failure --------------------------------------------------------------

    @external
    def fail_quest(self, slot: QuestSlot, quest_id: str) -> None:
        """Mark a quest as ended badly, idempotently.

        Args:
            slot: This session's slot.
            quest_id: The quest that failed.
        """
        failed = slot.setdefault("failed", [])
        if quest_id not in failed:
            failed.append(quest_id)

    @query
    @external
    def is_quest_failed(self, slot: QuestSlot, quest_id: str) -> bool:
        """Return whether a quest ended badly.

        Args:
            slot: This session's slot.
            quest_id: The quest to test.

        Returns:
            True once the quest has been failed.
        """
        return quest_id in slot.get("failed", ())

    # -- completion and the journal, over the catalog --------------------------

    def remaining_requirements(self, slot: QuestSlot, quest_id: str) -> list[str]:
        """Return the required subquests that are not yet complete.

        What lets a journal say "2 of 4 ingredients found" instead of
        printing a bare stage number.

        Args:
            slot: This session's slot.
            quest_id: The parent quest.

        Returns:
            The incomplete required subquest ids, in the order `requires`
            lists them. Empty when every requirement is met, when the
            quest has none, or when the catalog does not declare it.
        """
        spec = self.catalog.get(quest_id)
        if spec is None:
            return []
        return [child_id for child_id in spec.requires if not self.is_complete(slot, child_id)]

    def is_complete(self, slot: QuestSlot, quest_id: str) -> bool:
        """Return whether a quest is finished, honouring its required subquests.

        A quest completes when all three hold: every required subquest is
        complete (checked recursively through each subquest's own
        `requires`), every declared goal is met, and its `final_stage` has
        been reached when it declares one. A quest with no goals, no
        requirements and no `final_stage` never reports complete: calling
        such a quest finished would hide a catalog that forgot to say how
        it ends.

        Args:
            slot: This session's slot.
            quest_id: The quest to test.

        Returns:
            True when the quest is finished.
        """
        spec = self.catalog.get(quest_id)
        if spec is None:
            return False
        if any(not self.is_complete(slot, child_id) for child_id in spec.requires):
            return False
        if self.outstanding_goals(slot, quest_id):
            return False
        if spec.final_stage is None:
            return bool(spec.goal_ids or spec.requires)
        return self.quest_stage(slot, quest_id) >= spec.final_stage

    def _entry_for(self, slot: QuestSlot, quest_id: str, children: tuple[JournalEntry, ...]) -> JournalEntry:
        """Build one JournalEntry for a quest that is known to be started.

        Args:
            slot: This session's slot.
            quest_id: The quest to describe.
            children: Already-assembled entries for this quest's subquests.

        Returns:
            The assembled entry.
        """
        spec = self.catalog[quest_id]
        return JournalEntry(
            quest_id=quest_id,
            stage=self.quest_stage(slot, quest_id),
            complete=self.is_complete(slot, quest_id),
            failed=self.is_quest_failed(slot, quest_id),
            met=tuple(goal_id for goal_id in spec.goal_ids if self.is_goal_met(slot, quest_id, goal_id)),
            outstanding=tuple(self.outstanding_goals(slot, quest_id)),
            children=children,
        )

    def journal_entries(self, slot: QuestSlot) -> list[JournalEntry]:
        """Assemble the player's journal: every started quest, children nested.

        Unstarted quests are omitted entirely, matching the convention
        that a journal shows only what the player has actually
        discovered. A started subquest whose parent has NOT started is
        promoted to the top level rather than dropped -- losing a quest
        the player really began would be the silent-failure mode this
        system exists to prevent.

        Args:
            slot: This session's slot.

        Returns:
            Top-level entries in catalog order, each with its started
            children nested one level deep.
        """
        children_by_parent: dict[str, list[JournalEntry]] = {}
        for quest_id, spec in self.catalog.items():
            if spec.parent_id is None or not self.is_quest_started(slot, quest_id):
                continue
            children_by_parent.setdefault(spec.parent_id, []).append(self._entry_for(slot, quest_id, ()))

        entries: list[JournalEntry] = []
        for quest_id, spec in self.catalog.items():
            if not self.is_quest_started(slot, quest_id):
                continue
            parent = spec.parent_id
            if parent is not None and self.is_quest_started(slot, parent) and parent in self.catalog:
                continue
            entries.append(self._entry_for(slot, quest_id, tuple(children_by_parent.get(quest_id, ()))))
        return entries


QUESTS = Quests()
PLUGIN = QUESTS.plugin()
