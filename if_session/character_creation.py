"""One definition of how a player's answers become Ink globals.

A game can declare questions to ask before its first turn --
`manifest.yaml`'s `NEW_GAME_FIELDS` -- each naming a variable to set and
how to ask for it. Turning what the player submitted into the variables
the story reads is the same work whichever application asks, and two of
its rules are easy to get wrong:

- `add_to` is applied LAST, so an additive field adds to a value another
  field may just have set rather than to a static default.
- The base value comes from the compiled story's own declared defaults,
  not from an assumed 0.

This module owns that translation. It does not build a form: how the
question is put to the player -- a web page, a desktop screen -- stays
with the application, which passes the answers here.

Nothing here touches a story engine. The story's declared defaults arrive
as a plain mapping the application read for itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: What an HTML checkbox submits when ticked. A form sends nothing at all
#: when it is clear, so absence means "unticked", not "unanswered".
CHECKBOX_ON = "on"


def answers_to_globals(
    fields: list[dict[str, Any]],
    answers: Mapping[str, str],
    *,
    story_defaults: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the Ink globals to set before a new game's first turn.

    Args:
        fields: The manifest's own `NEW_GAME_FIELDS`, verbatim.
        answers: What the player submitted, keyed by each field's `var`.
            A plain dict satisfies this, as does a web framework's own
            request-parameter mapping. Only `.get()` is used: a
            multi-value mapping widens the value type of `items()` and
            `__getitem__`, so reading it any other way would make this
            signature a lie.
        story_defaults: The compiled story's own declared variable values,
            read by the application. An `add_to` field adds to the real
            base rather than a guess.

    Returns:
        Every global to set, including the linked and additive variables
        a field declares. A field the player did not answer takes its own
        declared `default`, never an error.

    Raises:
        KeyError: A field is missing `var` or `type`, or a `linked_vars`
            map lacks the `"True"`/`"False"` key it needs. A malformed
            manifest is the author's mistake, and failing at the point of
            the mistake beats leaving a variable silently wrong for a
            whole playthrough.
    """
    result: dict[str, Any] = {}
    additive: list[tuple[bool, dict[str, Any]]] = []

    for field in fields:
        var_name = field["var"]
        field_type = field["type"]
        if field_type == "text":
            result[var_name] = answers.get(var_name, field.get("default", ""))
        elif field_type == "radio_image":
            result.update(_chosen_option_value(field, answers))
        elif field_type == "checkbox":
            submitted = answers.get(var_name)
            checked = submitted == CHECKBOX_ON if submitted is not None else bool(field.get("default", False))
            if "add_to" in field:
                additive.append((checked, field["add_to"]))
                continue
            result[var_name] = checked
            for linked_var, value_map in field.get("linked_vars", {}).items():
                result[linked_var] = value_map[str(checked)]

    # Applied last, so an additive field adds to whatever the fields above
    # settled on -- not to the manifest's own static default.
    for checked, targets in additive:
        if not checked:
            continue
        for target_var, amount in targets.items():
            result[target_var] = result.get(target_var, story_defaults.get(target_var, 0)) + amount
    return result


def _chosen_option_value(field: dict[str, Any], answers: Mapping[str, str]) -> dict[str, Any]:
    """Return the `value` dict of the option a `radio_image` field chose.

    An option's `value` is itself a mapping, so one question can set
    several variables at once.

    Args:
        field: The field's own manifest entry (`options`, `default`).
        answers: The submitted answers, keyed by the field's `var`.

    Returns:
        The chosen option's `value`. An answer that is missing, not a
        number, or out of range falls back to the option matching
        `default`, then to the first option, then to nothing.
    """
    options = field.get("options", [])
    submitted_index = answers.get(field["var"])
    if submitted_index is not None and submitted_index.isdigit() and int(submitted_index) < len(options):
        return dict(options[int(submitted_index)]["value"])
    default_option = next(
        (option for option in options if option["value"] == field.get("default")),
        options[0] if options else None,
    )
    return dict(default_option["value"]) if default_option is not None else {}
