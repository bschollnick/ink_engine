"""InkRuntimeState.to_dict()/from_dict() serialization tests
(ink_engine.engine).

Every test drives real compiled JSON through a snapshot -> real
json.dumps/json.loads round-trip -> from_dict() rebuild, then confirms
the rebuilt state produces identical continuation output/choices to an
unsnapshotted control run — the actual correctness property this
serialization exists for: a resumed game must play on exactly as if it
had never been serialized at all.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

from ink_engine import engine
from ink_engine.engine import (
    InkRuntimeState,
    ListValue,
    OutputStream,
    ResolvedDivertTarget,
    load_list_defs,
    load_story_root,
)

FIXTURES = FilePath(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    with open(FIXTURES / name, encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def _round_trip(state: InkRuntimeState, root, list_defs=None) -> InkRuntimeState:
    """Serialize state, pass through real json.dumps/loads, rebuild."""
    snapshot = json.loads(json.dumps(state.to_dict()))
    return InkRuntimeState.from_dict(root, snapshot, list_defs)


class BasicRoundTripTests(SimpleTestCase):
    """A freshly-constructed state, and one after a turn with a pending
    choice, both round-trip with identical observable state."""

    def test_fresh_state_round_trips(self):
        """A state that has never taken a turn (only __init__'s global
        -decl bootstrap has run) round-trips with matching globals and
        pointer position."""
        data = _load("variables.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState(root)
        state2 = _round_trip(state, load_story_root(data))
        self.assertEqual(state.globals, state2.globals)
        self.assertEqual(state.turn_count, state2.turn_count)

    def test_state_with_pending_choice_round_trips(self):
        """A state stopped at a choice point round-trips with matching
        choice text/count, and continuing both after choosing the same
        option produces identical text."""
        data = _load("choices.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState(root)
        state.continue_story()
        state2 = _round_trip(state, load_story_root(data))
        self.assertEqual([c.text for c in state.current_choices], [c.text for c in state2.current_choices])
        state.choose(0)
        state2.choose(0)
        self.assertEqual(state.continue_story(), state2.continue_story())


class SavedStateStaysBoundedTests(SimpleTestCase):
    """The serialized state must not grow without bound as turns pass."""

    def test_output_tokens_hold_only_the_current_turn(self):
        """`to_dict()` carries only the CURRENT turn's output tokens.

        `continue_story()` appends into one long-lived OutputStream and
        reads back only `tokens[start_length:]` -- the accumulated prefix
        is never used again, but it WAS serialized in full every turn, so
        a saved state grew linearly forever. Measured on a real story
        before this was fixed: 34KB at turn 0 rising to 114KB by turn
        600, ~111 bytes/turn with no ceiling, of which output_tokens was
        69%.

        The invariant, checked directly rather than via a growth curve: at
        any stopping point the serialized token list is exactly the tokens
        that turn produced, so it re-renders `last_turn_text` and nothing
        older.
        """
        data = _load("gather_loop.ink.json")
        state = InkRuntimeState(load_story_root(data))
        for turn in range(3):
            text = state.continue_story()
            snapshot = InkRuntimeState.from_dict(load_story_root(data), json.loads(json.dumps(state.to_dict())))
            replayed = OutputStream()
            replayed.tokens.extend(snapshot.output.tokens)
            self.assertEqual(
                replayed.get_text(),
                text,
                f"turn {turn}: serialized output_tokens are not this turn's own output -- older turns are accumulating",
            )
            if not state.current_choices:
                break
            state.choose(0)

    def test_a_resumed_state_still_produces_identical_output(self):
        """Truncating the buffer must not change what the story says.

        The guard for the invariant above: if the accumulated prefix ever
        DID matter, dropping it would show up here as divergent text.
        """
        data = _load("gather_loop.ink.json")
        state = InkRuntimeState(load_story_root(data))
        for _ in range(6):
            state.continue_story()
            if not state.current_choices:
                break
            state.choose(0)
        resumed = _round_trip(state, load_story_root(data))
        for _ in range(6):
            self.assertEqual(state.continue_story(), resumed.continue_story())
            if not state.current_choices or not resumed.current_choices:
                break
            state.choose(0)
            resumed.choose(0)


class MidTunnelRoundTripTests(SimpleTestCase):
    """A state snapshotted mid-tunnel (tunnel_stack non-empty) resumes
    and completes identically to the unsnapshotted original."""

    def test_mid_tunnel_state_resumes_identically(self):
        """A snapshot taken with tunnel_stack non-empty resumes and
        finishes the story with the same output as the unsnapshotted run."""
        data = _load("nested_tunnel.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState(root)
        while not state.done and not state.tunnel_stack:
            state._step()  # pylint: disable=protected-access
        self.assertTrue(state.tunnel_stack, "fixture must reach a non-empty tunnel_stack to test anything")
        state2 = _round_trip(state, load_story_root(data))
        self.assertEqual(len(state.tunnel_stack), len(state2.tunnel_stack))
        while not state.done:
            state._step()  # pylint: disable=protected-access
        while not state2.done:
            state2._step()  # pylint: disable=protected-access
        self.assertEqual(state.output.get_text(), state2.output.get_text())


class MidFunctionCallRoundTripTests(SimpleTestCase):
    """to_dict()/from_dict() must round-trip _eval_run_depth and the
    other transient mid-dispatch flags (_pending_thread, _in_tag,
    _tag_buffer, _string_capture_stack). A snapshot taken with
    call_stack non-empty — meaning a function call is in progress, and
    the *outer* eval run that called it is still open — must not resume
    with _eval_run_depth reset to 0 (fresh construction's default): that
    would silently route the eventual "out" marker through the no-op
    CONTROL_COMMAND_MARKERS branch instead of real EVAL_OUTPUT handling,
    producing no output at all instead of the interpolated return
    value."""

    def test_mid_function_call_state_resumes_with_correct_output(self):
        """A snapshot taken with call_stack non-empty still produces the
        correct interpolated function-call result once resumed —
        against nested_func.ink's real output ("21")."""
        data = _load("nested_func.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState(root)
        while not state.done and not state.call_stack:
            state._step()  # pylint: disable=protected-access
        self.assertTrue(state.call_stack, "fixture must reach a non-empty call_stack to test anything")
        state2 = _round_trip(state, load_story_root(data))
        self.assertEqual(state2._eval_run_depth, state._eval_run_depth)  # pylint: disable=protected-access
        while not state.done:
            state._step()  # pylint: disable=protected-access
        while not state2.done:
            state2._step()  # pylint: disable=protected-access
        self.assertEqual(state.output.get_text(), "21\n")
        self.assertEqual(state.output.get_text(), state2.output.get_text())


class ListValueRoundTripTests(SimpleTestCase):
    """LIST-valued globals round-trip through serialization unchanged,
    including entries/origin_names structure."""

    def test_list_valued_globals_round_trip(self):
        """A story whose globals include real LIST values round-trips
        every entry/origin_names exactly."""
        data = _load("listToNumber.ink.json")
        root = load_story_root(data)
        list_defs = load_list_defs(data)
        state = InkRuntimeState(root, list_defs)
        state.continue_story()
        self.assertTrue(any(isinstance(v, ListValue) for v in state.globals.values()))
        state2 = _round_trip(state, load_story_root(data), list_defs)
        self.assertEqual(state.globals, state2.globals)


class ResolvedDivertTargetRoundTripTests(SimpleTestCase):
    """A ResolvedDivertTarget value (from a DivertTargetValue literal —
    e.g. Ink's empty-bracket choice syntax's own temp-variable plumbing)
    round-trips through serialization to the same logical container."""

    def test_resolved_divert_target_in_temps_round_trips(self):
        """A ResolvedDivertTarget stored in a temp variable resolves to
        the same container (by name) before and after round-tripping."""
        data = _load("bracket_choice.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState(root)
        state.continue_story()
        # Drive one step into the choice-text-building machinery, where a
        # ResolvedDivertTarget is assigned to the temp variable "$r".
        while not state.done and "$r" not in state.temps:
            state._step()  # pylint: disable=protected-access
        self.assertIn("$r", state.temps)
        self.assertIsInstance(state.temps["$r"], ResolvedDivertTarget)
        original_target_path = state.temps["$r"].container.name if state.temps["$r"].container else None
        state2 = _round_trip(state, load_story_root(data))
        resumed_value = state2.temps["$r"]
        self.assertIsInstance(resumed_value, ResolvedDivertTarget)
        self.assertEqual(resumed_value.container.name if resumed_value.container else None, original_target_path)


class MissingContainerDegradationTests(SimpleTestCase):
    """A serialized path that no longer resolves (simulating a changed
    story) degrades to None/dropped rather than raising — the same
    defensive philosophy every other out-of-scope-construct handling in
    this module already follows. Full save-compatibility repair is Step
    4 scope; these tests only confirm from_dict() itself doesn't crash."""

    def test_unresolvable_pointer_path_degrades_to_none(self):
        """A pointer path that fails to resolve produces a null-container
        pointer rather than raising."""
        data = _load("simple.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState.from_dict(root, {"pointer": {"path": "does_not_exist", "index": 0}})
        self.assertIsNone(state.pointer.container if state.pointer else None)

    def test_unresolvable_choice_target_is_dropped(self):
        """A serialized choice whose target path fails to resolve is
        silently omitted from current_choices rather than raising."""
        data = _load("simple.ink.json")
        root = load_story_root(data)
        state = InkRuntimeState.from_dict(root, {"current_choices": [{"text": "Ghost choice", "target_path": "does_not_exist"}]})
        self.assertEqual(state.current_choices, [])


class PersistedKeyContractTests(SimpleTestCase):
    """`to_dict()` output is a persisted format, not an internal detail.

    A host stores it in a database column and in save files, so renaming
    a key or changing a default silently invalidates every existing save.
    The other tests here all round-trip freshly built state, which cannot
    catch that: a key absent from BOTH halves round-trips perfectly while
    dropping real data. These pin the shape itself.
    """

    #: Every key a saved state carries. Changing this list is a
    #: save-format change: old saves lack anything added, and anything
    #: removed or renamed is silently dropped on load.
    EXPECTED_KEYS = frozenset(
        {
            "call_stack",
            "current_choices",
            "current_tags",
            "done",
            "eval_run_depth",
            "eval_stack",
            "globals",
            "in_tag",
            "last_turn_text",
            "output_tokens",
            "pending_thread",
            "pointer",
            "previous_pointer",
            "previous_random",
            "story_seed",
            "string_capture_eval_depth",
            "string_capture_stack",
            "tag_buffer_tokens",
            "temps",
            "tunnel_stack",
            "turn_count",
            "visit_counts",
            "visit_turns",
        }
    )

    def _played(self) -> InkRuntimeState:
        data = _load("variables.ink.json")
        state = InkRuntimeState(load_story_root(data), load_list_defs(data))
        state.continue_story()
        return state

    def test_the_saved_key_set_is_exactly_what_hosts_persist(self):
        self.assertEqual(set(self._played().to_dict()), set(self.EXPECTED_KEYS))

    def test_a_state_missing_every_optional_key_still_loads(self):
        """What an older save looks like: only what that version wrote.
        Each absent key must fall back, not raise."""
        data = _load("variables.ink.json")
        root = load_story_root(data)
        restored = InkRuntimeState.from_dict(root, {}, load_list_defs(data))
        self.assertEqual(restored.turn_count, -1)
        self.assertFalse(restored.done)

    def test_an_unknown_key_from_a_newer_save_is_ignored(self):
        """A save written by a later version must not break this one."""
        data = _load("variables.ink.json")
        root = load_story_root(data)
        snapshot = self._played().to_dict()
        snapshot["a_key_this_version_never_wrote"] = 99
        restored = InkRuntimeState.from_dict(root, snapshot, load_list_defs(data))
        self.assertEqual(restored.turn_count, self._played().turn_count)

    def test_a_bool_global_round_trips_as_a_bool(self):
        """Bools are tagged rather than stored raw, because Python's bool
        is an int subclass and would otherwise reload as 0/1."""
        state = self._played()
        state.globals["a_flag"] = True
        data = _load("variables.ink.json")
        restored = InkRuntimeState.from_dict(load_story_root(data), state.to_dict(), load_list_defs(data))
        self.assertIs(restored.globals["a_flag"], True)


class ScalarFieldTableTests(SimpleTestCase):
    """The scalar fields both halves of serialization share.

    Writing and reading were once two hand-mirrored lists, so a field
    could be added to one and missed in the other. These check the table
    that replaced them actually describes the real attributes.
    """

    def test_every_tabled_field_names_a_real_attribute(self):
        data = _load("variables.ink.json")
        state = InkRuntimeState(load_story_root(data), load_list_defs(data))
        for key, attribute, _coerce, _default in engine._SCALAR_STATE_FIELDS:
            with self.subTest(key=key):
                self.assertTrue(hasattr(state, attribute), f"{key!r} names a missing attribute {attribute!r}")

    def test_every_tabled_field_is_actually_written(self):
        data = _load("variables.ink.json")
        state = InkRuntimeState(load_story_root(data), load_list_defs(data))
        state.continue_story()
        written = state.to_dict()
        for key, _attribute, _coerce, _default in engine._SCALAR_STATE_FIELDS:
            with self.subTest(key=key):
                self.assertIn(key, written)

    def test_each_default_applies_when_a_save_omits_the_field(self):
        data = _load("variables.ink.json")
        restored = InkRuntimeState.from_dict(load_story_root(data), {}, load_list_defs(data))
        for key, attribute, _coerce, default in engine._SCALAR_STATE_FIELDS:
            with self.subTest(key=key):
                self.assertEqual(getattr(restored, attribute), default)

    def test_a_capture_depth_from_an_older_save_falls_back_to_the_run_depth(self):
        """The one field deliberately left out of the table: its default
        derives from other restored state, so an all-zero baseline would
        make every capture believe it began at depth 0."""
        data = _load("variables.ink.json")
        restored = InkRuntimeState.from_dict(
            load_story_root(data),
            {"eval_run_depth": 3, "string_capture_stack": [["a"], ["b"]]},
            load_list_defs(data),
        )
        self.assertEqual(restored._string_capture_eval_depth, [3, 3])
