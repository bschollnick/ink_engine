# Ink Engine — Miscellaneous Notes

**Date Created:** 2026-09-19  
**Last Updated:** 2026-09-19  
**Last Reviewed:** 2026-09-19

Runtime facts about `engine.py` for someone working on the interpreter.
Nothing here is needed to write a game. Each entry stands alone.

An entry marked **[Ink]** is the Ink language's own behaviour, which this
engine reproduces. The rest are this engine's own implementation.

---

- **The output buffer is truncated per turn**, not accumulated forever.
  `continue_story()` records `len(self.output.tokens)` at its own start and
  slices only the new tokens for `last_turn_text` — serializing the whole
  history instead would grow saved state without bound.
- **Glue lookups are cached, not a rescan.** `_latest_glue_index()`
  (`OutputStream`) only rescans the suffix appended since the last call,
  not the whole turn's buffer.
- **Every transient mid-dispatch flag is part of serialized state**
  (`_eval_run_depth`, `_pending_thread`, `_in_tag`, `_tag_buffer`,
  `_string_capture_stack`, and the rest of `to_dict()`'s own field list) —
  omitting any of them from a save/resume path can leave a resumed session
  in a state the live interpreter would never actually produce on its own
  (e.g. a function-call return marker routed through the wrong branch).
- **[Ink] Tags are cleared per turn.** `current_tags` is reset at the start
  of every `continue_story()` call, matching inkle's own documented
  `currentTags` contract (`RunningYourInk.md`: scoped to "every time you
  get content with `Continue()`") — an interpreter or application that skips this
  leaves every tag ever seen "active" for the rest of the story.
- **Shuffle seeding is a character-sum hash of the container's own path,
  combined with the story's seed** — reproducing Ink's documented
  shuffle/`shuffle once`/`shuffle stopping` behavior
  (`WritingWithInk.md`), and reproducible only if the story seed itself is
  pinned (real Ink seeds from the wall clock by default). `_shuffle_index`
  notes in its own docstring which part of the port is unverified.
- **[Ink] String operators are only `+`/`==`/`!=`**; `?`/`!?` are LIST-only.
  Confirmed directly: `not` applied to a raw string (`not s`, not a
  comparison result) raises `RUNTIME ERROR: ... Cannot perform operation
  '!' on String`; `not` applied to the *result* of a string comparison
  (`not (s == "world")`) works fine, since `==` already produces a boolean
  (see [section 1.3 of "Ink: when it compiles but is wrong"](ink_when_it_compiles_but_is_wrong.md#13-not-binds-tighter-than-comparison)).
