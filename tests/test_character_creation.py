"""Tests for `if_session.character_creation`.

One test per documented rule, plus the two that are easy to get wrong and
would be silent if they were: `add_to` ordering, and reading the story's
own declared base rather than assuming 0.
"""

from __future__ import annotations

from typing import Any

import pytest

from if_session.character_creation import answers_to_globals


def text_field(**overrides: Any) -> dict[str, Any]:
    field = {"var": "player_name", "type": "text", "label": "Name?", "default": "Morgan"}
    field.update(overrides)
    return field


def checkbox_field(**overrides: Any) -> dict[str, Any]:
    field = {"var": "hard_mode", "type": "checkbox", "label": "Hard?", "default": False}
    field.update(overrides)
    return field


def radio_field(**overrides: Any) -> dict[str, Any]:
    field = {
        "var": "starting_role",
        "type": "radio_image",
        "label": "Who were you?",
        "default": {"starting_role": "keeper"},
        "options": [
            {"value": {"starting_role": "keeper"}, "label": "The keeper", "image": "a.png"},
            {"value": {"starting_role": "sailor"}, "label": "A sailor", "image": "b.png"},
        ],
    }
    field.update(overrides)
    return field


class TestTextField:
    def test_the_submitted_value_is_used(self) -> None:
        result = answers_to_globals([text_field()], {"player_name": "Alice"}, story_defaults={})
        assert result == {"player_name": "Alice"}

    def test_an_unanswered_field_takes_its_declared_default(self) -> None:
        result = answers_to_globals([text_field()], {}, story_defaults={})
        assert result == {"player_name": "Morgan"}

    def test_a_field_with_no_default_answers_empty(self) -> None:
        field = text_field()
        del field["default"]
        assert answers_to_globals([field], {}, story_defaults={}) == {"player_name": ""}

    def test_an_empty_submission_is_respected_not_replaced(self) -> None:
        """A player clearing the box chose an empty name."""
        assert answers_to_globals([text_field()], {"player_name": ""}, story_defaults={}) == {"player_name": ""}


class TestCheckboxField:
    def test_on_means_true(self) -> None:
        """`"on"` is what an HTML form submits for a ticked box."""
        assert answers_to_globals([checkbox_field()], {"hard_mode": "on"}, story_defaults={}) == {"hard_mode": True}

    def test_an_absent_checkbox_takes_its_declared_default(self) -> None:
        assert answers_to_globals([checkbox_field()], {}, story_defaults={}) == {"hard_mode": False}

    def test_an_absent_checkbox_defaulting_true_resolves_true(self) -> None:
        """A game can declare a box ticked to begin with."""
        field = checkbox_field(default=True)
        assert answers_to_globals([field], {}, story_defaults={}) == {"hard_mode": True}

    def test_a_value_other_than_on_is_false(self) -> None:
        """Present-but-not-"on" is an unticked box, not an unanswered one.

        An application collecting answers itself must send `"on"` or omit
        the key: `"true"` resolves False.
        """
        assert answers_to_globals([checkbox_field(default=True)], {"hard_mode": "true"}, story_defaults={}) == {"hard_mode": False}


class TestLinkedVars:
    def test_a_linked_variable_follows_the_checkbox(self) -> None:
        field = checkbox_field(linked_vars={"rank": {"True": "captain", "False": "deckhand"}})
        result = answers_to_globals([field], {"hard_mode": "on"}, story_defaults={})
        assert result == {"hard_mode": True, "rank": "captain"}

    def test_the_false_branch_is_used_when_unticked(self) -> None:
        field = checkbox_field(linked_vars={"rank": {"True": "captain", "False": "deckhand"}})
        result = answers_to_globals([field], {}, story_defaults={})
        assert result == {"hard_mode": False, "rank": "deckhand"}

    def test_a_malformed_linked_map_raises_rather_than_guessing(self) -> None:
        """The manifest guide warns that unquoted True/False keys become
        YAML booleans. That is an author's mistake, and failing here beats
        leaving the variable silently wrong for a playthrough."""
        field = checkbox_field(linked_vars={"rank": {"True": "captain"}})
        with pytest.raises(KeyError):
            answers_to_globals([field], {}, story_defaults={})


class TestRadioImageField:
    def test_the_chosen_option_supplies_its_value(self) -> None:
        result = answers_to_globals([radio_field()], {"starting_role": "1"}, story_defaults={})
        assert result == {"starting_role": "sailor"}

    def test_one_option_can_set_several_variables(self) -> None:
        field = radio_field(options=[{"value": {"role": "keeper", "home": "lighthouse"}, "label": "Keeper", "image": "a.png"}])
        assert answers_to_globals([field], {"starting_role": "0"}, story_defaults={}) == {
            "role": "keeper",
            "home": "lighthouse",
        }

    def test_no_answer_falls_back_to_the_option_matching_default(self) -> None:
        assert answers_to_globals([radio_field()], {}, story_defaults={}) == {"starting_role": "keeper"}

    @pytest.mark.parametrize("submitted", ["9", "-1", "notanumber", ""], ids=["too-big", "negative", "text", "empty"])
    def test_an_unusable_answer_falls_back_rather_than_raising(self, submitted: str) -> None:
        result = answers_to_globals([radio_field()], {"starting_role": submitted}, story_defaults={})
        assert result == {"starting_role": "keeper"}

    def test_an_unmatched_default_falls_back_to_the_first_option(self) -> None:
        field = radio_field(default={"starting_role": "nobody"})
        assert answers_to_globals([field], {}, story_defaults={}) == {"starting_role": "keeper"}

    def test_a_field_declaring_no_options_contributes_nothing(self) -> None:
        assert answers_to_globals([radio_field(options=[])], {}, story_defaults={}) == {}


class TestAddTo:
    """The rule a second implementation would get wrong."""

    def test_a_ticked_additive_field_adds_to_the_story_default(self) -> None:
        field = checkbox_field(var="lottery", add_to={"money": 500})
        result = answers_to_globals([field], {"lottery": "on"}, story_defaults={"money": 20})
        assert result == {"money": 520}

    def test_an_unticked_additive_field_adds_nothing(self) -> None:
        field = checkbox_field(var="lottery", add_to={"money": 500})
        assert answers_to_globals([field], {}, story_defaults={"money": 20}) == {}

    def test_the_additive_variable_itself_is_not_set(self) -> None:
        """`add_to` names what it adds to; the checkbox's own var is not
        a story variable."""
        field = checkbox_field(var="lottery", add_to={"money": 500})
        result = answers_to_globals([field], {"lottery": "on"}, story_defaults={"money": 0})
        assert "lottery" not in result

    def test_an_unknown_target_starts_from_zero(self) -> None:
        field = checkbox_field(var="lottery", add_to={"money": 500})
        assert answers_to_globals([field], {"lottery": "on"}, story_defaults={}) == {"money": 500}

    def test_two_additive_fields_both_apply(self) -> None:
        fields = [
            checkbox_field(var="lottery", add_to={"money": 500}),
            checkbox_field(var="inheritance", add_to={"money": 50}),
        ]
        result = answers_to_globals(fields, {"lottery": "on", "inheritance": "on"}, story_defaults={"money": 20})
        assert result == {"money": 570}

    def test_it_adds_to_a_value_an_earlier_field_set(self) -> None:
        """The ordering rule. `add_to` runs after every other field, so a
        radio choice that sets the same variable is added to -- not
        overwritten by, and not ignored in favour of, the story default.
        """
        fields = [
            checkbox_field(var="lottery", add_to={"money": 500}),
            radio_field(
                var="wealth",
                options=[{"value": {"money": 1000}, "label": "Rich", "image": "a.png"}],
                default={"money": 1000},
            ),
        ]
        result = answers_to_globals(fields, {"lottery": "on", "wealth": "0"}, story_defaults={"money": 20})

        # 1000 from the radio choice, then +500 -- not 520, and not 500.
        assert result == {"money": 1500}


class TestWholeForm:
    def test_a_realistic_form_resolves_every_field(self) -> None:
        fields = [
            text_field(),
            radio_field(),
            checkbox_field(linked_vars={"rank": {"True": "captain", "False": "deckhand"}}),
            checkbox_field(var="lottery", add_to={"money": 500}),
        ]
        answers = {"player_name": "Alice", "starting_role": "1", "hard_mode": "on", "lottery": "on"}

        result = answers_to_globals(fields, answers, story_defaults={"money": 20})

        assert result == {
            "player_name": "Alice",
            "starting_role": "sailor",
            "hard_mode": True,
            "rank": "captain",
            "money": 520,
        }

    def test_no_fields_means_no_globals(self) -> None:
        assert answers_to_globals([], {"anything": "x"}, story_defaults={"money": 20}) == {}

    def test_an_unanswered_form_still_produces_every_default(self) -> None:
        """Opening a game without asking behaves as though every default
        was chosen."""
        fields = [text_field(), radio_field(), checkbox_field()]
        assert answers_to_globals(fields, {}, story_defaults={}) == {
            "player_name": "Morgan",
            "starting_role": "keeper",
            "hard_mode": False,
        }

    def test_an_unknown_field_type_is_skipped(self) -> None:
        """A manifest from a newer engine must not break this one."""
        fields = [text_field(), {"var": "x", "type": "colour_picker", "default": "red"}]
        assert answers_to_globals(fields, {}, story_defaults={}) == {"player_name": "Morgan"}

    def test_a_field_missing_its_var_raises(self) -> None:
        with pytest.raises(KeyError):
            answers_to_globals([{"type": "text"}], {}, story_defaults={})
