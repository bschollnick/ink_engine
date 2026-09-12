"""A generic, roll-under skill-check framework.

A skill is just a name the game layer chooses and a numeric level on
whatever range it declares (1-6, 1-20, 1-100). Every check normalises
internally to a percentile roll, so the game's display range never
touches the roll math.

**Roll-under**: a check succeeds when a 1-100 roll is at or below
(level + bonus). Out-of-range levels and bonuses are clamped at roll
time, never rejected.

**Its own RNG, not Ink's.** The slot carries its own seed, so skill
checks and Ink's `RANDOM()` draw from separate streams and a check is a
pure function of (skill state, RNG state).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TypedDict

from ink_engine.plugin_base import StatefulPlugin, external, query

#: Where this plugin's state lives in a session's `EngineState`.
STATE_KEY = "skills"


class SkillSlot(TypedDict):
    """A session's own skill levels plus this module's own independent RNG state.

    Attributes:
        skill_levels: character_id -> {skill_name: level}. Named for what
            it holds -- skill levels only, not general per-character state
            (which belongs in character attributes instead). The level is
            a NUMBER, not strictly an integer: a game may use a level as a
            multi-stage story counter with sub-stages like 2.1, on
            whatever numeric range the game layer chose for that skill.
        rng_seed: This module's own RNG seed -- fully independent of Ink's
            `story_seed`.
        last_roll: The raw 1-100 roll from the most recent `check()`, 0
            before any has run.
        last_effective_target: The roll-under target that roll was
            compared against, 0 before any check has run.
    """

    skill_levels: dict[str, dict[str, float]]
    rng_seed: int
    last_roll: int
    last_effective_target: int


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one skill check -- the real "get the result of a
    skill test" the game layer queries.

    Args:
        success: Whether the check succeeded (roll <= effective target).
        roll: The raw 1-100 roll made for this check.
        effective_target: The actual roll-under target used, after
            normalizing `level` onto a 1-100 scale and applying `bonus`,
            clamped to [0, 100] -- what `roll` was compared against,
            useful for the game layer to report "you needed X or under,
            you rolled Y."
    """

    success: bool
    roll: int
    effective_target: int


class Skills(StatefulPlugin[SkillSlot]):
    """Skill levels per character, and roll-under checks against them."""

    name = "skills"
    display_name = "Skills"
    state_key = STATE_KEY
    slot_type = SkillSlot
    fields = {"skill_levels": dict, "rng_seed": int, "last_roll": int, "last_effective_target": int}

    @query
    @external
    def skill_level(self, slot: SkillSlot, character_id: str, skill_name: str, default: float = 0) -> float:
        """Return a character's current level in a skill.

        Args:
            slot: This session's slot.
            character_id: The character to look up.
            skill_name: The skill to look up -- any string the game layer
                chose.
            default: The level to return if the character has no recorded
                level for this skill yet.

        Returns:
            The current level, or `default`.
        """
        return slot.get("skill_levels", {}).get(character_id, {}).get(skill_name, default)

    @external
    def set_skill_level(self, slot: SkillSlot, character_id: str, skill_name: str, level: float) -> None:
        """Set a character's level in a skill to an exact value.

        Args:
            slot: This session's slot.
            character_id: The character to update.
            skill_name: The skill to set.
            level: The exact level to set (on whatever range the game
                layer uses for this skill -- not validated or clamped
                here).
        """
        slot.setdefault("skill_levels", {}).setdefault(character_id, {})[skill_name] = level

    @external
    def adjust_skill_level(self, slot: SkillSlot, character_id: str, skill_name: str, delta: float) -> float:
        """Add (or, with a negative delta, subtract) an amount to a level.

        A skill with no prior recorded level is treated as starting at 0
        before applying delta, matching `skill_level()`'s own default.

        Args:
            slot: This session's slot.
            character_id: The character to update.
            skill_name: The skill to adjust.
            delta: The amount to add -- pass a negative value to subtract.

        Returns:
            The new level.
        """
        new_level = self.skill_level(slot, character_id, skill_name) + delta
        self.set_skill_level(slot, character_id, skill_name, new_level)
        return new_level

    def all_levels(self, slot: SkillSlot, character_id: str) -> dict[str, float]:
        """Return every skill level currently recorded for a character.

        The real "get current stats for a player/NPC" query.

        Args:
            slot: This session's slot.
            character_id: The character to look up.

        Returns:
            An independent copy of that character's skill_name -> level
            mapping (empty if the character has no recorded skills).
        """
        return dict(slot.get("skill_levels", {}).get(character_id, {}))

    def check(self, slot: SkillSlot, level: float, max_level: int, bonus: int = 0) -> CheckResult:
        """Perform one roll-under skill check, advancing this plugin's own RNG.

        The level is normalized onto a 0-100 percentile scale via
        `round(level / max_level * 100)` before `bonus` is applied -- the
        game layer's own numeric range (1-6, 1-20, 1-100) is purely
        presentational; this module only ever rolls 1-100 internally.
        `bonus` is added directly to the already-normalized percentile
        target; an effective target outside [0, 100] is clamped rather
        than rejected. The roll and target are recorded in the slot for a
        story that wants to narrate them.

        Args:
            slot: This session's slot, whose RNG state advances.
            level: The character's current level in whatever skill is
                being tested, on a 0-`max_level` scale.
            max_level: The top of that skill's own declared range -- used
                only to normalize `level` onto the internal 0-100 scale.
            bonus: An optional flat percentile bonus (or, negative, a
                penalty) applied after normalization.

        Returns:
            The check's outcome.
        """
        percentile_level = round((level / max_level) * 100) if max_level else 0
        effective_target = max(0, min(100, percentile_level + bonus))
        rng = random.Random(slot.get("rng_seed", 0))
        roll = rng.randint(1, 100)
        slot["rng_seed"] = rng.randint(0, 2**31 - 1)
        slot["last_roll"] = roll
        slot["last_effective_target"] = effective_target
        return CheckResult(success=roll <= effective_target, roll=roll, effective_target=effective_target)

    @external
    def skill_check(self, slot: SkillSlot, level: float, max_level: int, bonus: int = 0) -> bool:
        """EXTERNAL `skill_check(level, max_level, bonus)`: `check()` for Ink.

        Args:
            slot: This session's slot.
            level: The level being tested.
            max_level: The top of that skill's range.
            bonus: A flat percentile bonus or penalty.

        Returns:
            Whether the check succeeded; `last_skill_roll()` and
            `last_skill_target()` report the numbers rolled.
        """
        return self.check(slot, level, max_level, bonus).success

    @external
    def last_skill_roll(self, slot: SkillSlot) -> int:
        """Return the raw 1-100 roll from the most recent check, 0 before any.

        Args:
            slot: This session's slot.

        Returns:
            The roll.
        """
        return slot.get("last_roll", 0)

    @external
    def last_skill_target(self, slot: SkillSlot) -> int:
        """Return the effective roll-under target of the most recent check, 0 before any.

        Args:
            slot: This session's slot.

        Returns:
            The target.
        """
        return slot.get("last_effective_target", 0)


SKILLS = Skills()
PLUGIN = SKILLS.plugin()
