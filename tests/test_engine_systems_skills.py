"""`engine_plugins.skills`: levels per character, and roll-under checks.

No host framework needed. SimpleTestCase throughout.
"""

from __future__ import annotations

import json
from unittest import TestCase as SimpleTestCase

from ink_engine.engine_plugins.skills import PLUGIN, SKILLS, CheckResult


def _slot(rng_seed: int = 0):
    slot = SKILLS.init_state(None)
    slot["rng_seed"] = rng_seed
    return slot


class GetSetAdjustLevelTests(SimpleTestCase):
    """Levels can be named anything (per the explicit "skills should be
    able to be called anything" requirement)."""

    def test_unset_skill_returns_the_given_default(self):
        """A skill never set for a character returns whatever default the
        caller supplies, not a fixed value."""
        slot = _slot()
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Wisdom", default=0), 0)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Wisdom", default=10), 10)

    def test_set_level_is_readable_back(self):
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Strength", 15)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 15)

    def test_adjust_level_adds_to_an_existing_level(self):
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Charisma", 10)
        self.assertEqual(SKILLS.adjust_skill_level(slot, "hero", "Charisma", 3), 13)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Charisma"), 13)

    def test_adjust_level_subtracts_with_a_negative_delta(self):
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Charisma", 10)
        SKILLS.adjust_skill_level(slot, "hero", "Charisma", -4)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Charisma"), 6)

    def test_adjust_level_on_an_unset_skill_starts_from_zero(self):
        slot = _slot()
        SKILLS.adjust_skill_level(slot, "hero", "Muscles", 5)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Muscles"), 5)

    def test_arbitrary_skill_names_are_supported(self):
        """The framework has no fixed skill list at all."""
        slot = _slot()
        names = ("Strength", "Muscles", "Wisdom", "Charisma", "some totally custom name")
        for name in names:
            SKILLS.set_skill_level(slot, "hero", name, 7)
        self.assertEqual(SKILLS.all_levels(slot, "hero"), {name: 7 for name in names})

    def test_different_characters_have_independent_levels(self):
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Strength", 15)
        SKILLS.set_skill_level(slot, "villain", "Strength", 20)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 15)
        self.assertEqual(SKILLS.skill_level(slot, "villain", "Strength"), 20)


class AllLevelsTests(SimpleTestCase):
    """all_levels() is the real "get current stats" query."""

    def test_returns_every_recorded_skill_for_a_character(self):
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Strength", 15)
        SKILLS.set_skill_level(slot, "hero", "Wisdom", 12)
        self.assertEqual(SKILLS.all_levels(slot, "hero"), {"Strength": 15, "Wisdom": 12})

    def test_character_with_no_skills_returns_an_empty_dict(self):
        self.assertEqual(SKILLS.all_levels(_slot(), "nobody"), {})

    def test_returned_dict_is_an_independent_copy(self):
        """Mutating the returned dict must never affect the slot."""
        slot = _slot()
        SKILLS.set_skill_level(slot, "hero", "Strength", 15)
        levels = SKILLS.all_levels(slot, "hero")
        levels["Strength"] = 999
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 15)


class CheckTests(SimpleTestCase):
    """check() is a real roll-under mechanic: success when roll <=
    (normalized level + bonus)."""

    def test_level_zero_always_fails(self):
        """A 0-level skill normalizes to a 0 percentile target -- a 1-100
        roll can never be <= 0."""
        slot = _slot(42)
        for _ in range(50):
            self.assertFalse(SKILLS.check(slot, level=0, max_level=20).success)

    def test_max_level_with_no_bonus_always_succeeds(self):
        slot = _slot(1)
        for _ in range(50):
            self.assertTrue(SKILLS.check(slot, level=20, max_level=20).success)

    def test_success_exactly_matches_roll_vs_effective_target(self):
        """A direct, non-statistical proof: success is exactly (roll <=
        effective_target), not some other comparison."""
        result = SKILLS.check(_slot(7), level=10, max_level=20, bonus=5)
        self.assertEqual(result.effective_target, 55)  # 10/20*100=50, +5 bonus
        self.assertEqual(result.success, result.roll <= 55)

    def test_effective_target_normalizes_across_different_max_levels(self):
        """A level of 3 on a 1-6 scale and a level of 10 on a 1-20 scale
        both normalize to the same 50 percentile target."""
        self.assertEqual(SKILLS.check(_slot(99), level=3, max_level=6).effective_target, 50)
        self.assertEqual(SKILLS.check(_slot(99), level=10, max_level=20).effective_target, 50)

    def test_bonus_can_be_negative_a_penalty(self):
        self.assertEqual(SKILLS.check(_slot(3), level=10, max_level=20, bonus=-5).effective_target, 45)

    def test_effective_target_is_clamped_to_0_and_100(self):
        self.assertEqual(SKILLS.check(_slot(0), level=20, max_level=20, bonus=50).effective_target, 100)
        self.assertEqual(SKILLS.check(_slot(0), level=0, max_level=20, bonus=-50).effective_target, 0)

    def test_check_advances_the_rng_state_deterministically(self):
        """Two runs from the SAME seed produce the SAME sequence of
        results -- real determinism, not just "it runs"."""
        slot_a, slot_b = _slot(555), _slot(555)
        results_a = [(result.roll, result.success) for result in (SKILLS.check(slot_a, level=10, max_level=20) for _ in range(5))]
        results_b = [(result.roll, result.success) for result in (SKILLS.check(slot_b, level=10, max_level=20) for _ in range(5))]
        self.assertEqual(results_a, results_b)

    def test_a_check_records_what_it_rolled(self):
        slot = _slot(1)
        result = SKILLS.check(slot, level=50, max_level=100)
        self.assertEqual(slot["last_roll"], result.roll)
        self.assertEqual(slot["last_effective_target"], result.effective_target)

    def test_repeated_checks_produce_a_real_distribution(self):
        """A statistical sanity check against a badly broken RNG or
        comparison, not a strict statistical test."""
        slot = _slot(2024)
        trials = 500
        successes = sum(1 for _ in range(trials) if SKILLS.check(slot, level=10, max_level=20).success)
        self.assertGreater(successes, trials * 0.35)
        self.assertLess(successes, trials * 0.65)


class CheckResultTests(SimpleTestCase):
    def test_check_result_fields_are_directly_readable(self):
        result = CheckResult(success=True, roll=42, effective_target=60)
        self.assertTrue(result.success)
        self.assertEqual(result.roll, 42)
        self.assertEqual(result.effective_target, 60)


class SerializationTests(SimpleTestCase):
    """The slot round-trips through plain JSON, RNG state included."""

    def test_round_trips_through_real_json(self):
        slot = _slot(123)
        SKILLS.set_skill_level(slot, "hero", "Strength", 15)
        SKILLS.set_skill_level(slot, "villain", "Wisdom", 8)
        restored = json.loads(json.dumps(slot))
        self.assertEqual(SKILLS.skill_level(restored, "hero", "Strength"), 15)
        self.assertEqual(SKILLS.skill_level(restored, "villain", "Wisdom"), 8)
        self.assertEqual(restored["rng_seed"], 123)

    def test_restored_state_continues_the_same_rng_sequence(self):
        """Serialization preserves determinism across a save/load boundary."""
        slot = _slot(77)
        result_before = SKILLS.check(slot, level=10, max_level=20)
        restored = json.loads(json.dumps(slot))
        result_after = SKILLS.check(restored, level=10, max_level=20)
        expected = SKILLS.check(slot, level=10, max_level=20)
        self.assertEqual(result_after.roll, expected.roll)
        self.assertNotEqual(result_before.roll, result_after.roll)

    def test_an_older_save_missing_the_last_roll_is_repaired_on_bind(self):
        """The most recent roll was once a loose key beside the state, so a
        save from then lacks it; binding repairs the shape."""
        old_save = {"skill_levels": {}, "rng_seed": 5}
        PLUGIN.bind(old_save, {}, {})
        self.assertEqual((old_save["last_roll"], old_save["last_effective_target"]), (0, 0))


class BindingTests(SimpleTestCase):
    """The EXTERNAL surface a story actually calls."""

    def setUp(self):
        self.slot = PLUGIN.init_state(None)
        self.bindings = PLUGIN.bind(self.slot, {}, {})

    def test_the_bindings_are_published_under_the_method_names(self):
        self.assertEqual(
            sorted(self.bindings), ["adjust_skill_level", "last_skill_roll", "last_skill_target", "set_skill_level", "skill_check", "skill_level"]
        )

    def test_writes_persist_into_the_session_slot(self):
        self.bindings["set_skill_level"]("hero", "Strength", 15)
        self.assertEqual(self.slot["skill_levels"]["hero"]["Strength"], 15)

    def test_get_set_round_trips_through_the_bindings(self):
        self.assertEqual(self.bindings["skill_level"]("hero", "Strength"), 0)
        self.bindings["set_skill_level"]("hero", "Strength", 15)
        self.assertEqual(self.bindings["skill_level"]("hero", "Strength"), 15)

    def test_adjust_returns_and_persists_the_new_level(self):
        self.bindings["set_skill_level"]("hero", "Strength", 10)
        self.assertEqual(self.bindings["adjust_skill_level"]("hero", "Strength", 5), 15)
        self.assertEqual(self.bindings["skill_level"]("hero", "Strength"), 15)

    def test_check_advances_state_and_records_the_roll_and_target(self):
        success = self.bindings["skill_check"](10, 20, 0)
        self.assertIsInstance(success, bool)
        roll = self.bindings["last_skill_roll"]()
        target = self.bindings["last_skill_target"]()
        self.assertTrue(1 <= roll <= 100)
        self.assertEqual(target, 50)
        self.assertEqual(success, roll <= target)

    def test_last_roll_and_target_are_zero_before_any_check(self):
        self.assertEqual(self.bindings["last_skill_roll"](), 0)
        self.assertEqual(self.bindings["last_skill_target"](), 0)

    def test_repeated_checks_advance_the_rng_each_time(self):
        self.bindings["skill_check"](50, 100, 0)
        first_roll = self.bindings["last_skill_roll"]()
        rolls_differ = any(
            self.bindings["skill_check"](50, 100, 0) is not None and self.bindings["last_skill_roll"]() != first_roll for _ in range(10)
        )
        self.assertTrue(rolls_differ, "10 consecutive checks all rolled the same value -- RNG is not advancing")

    def test_the_plugin_declares_its_own_state_slot(self):
        self.assertEqual(PLUGIN.state_key, "skills")
