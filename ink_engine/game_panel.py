"""Calling a game's own side-panel hooks.

A game folder may ship a `sidebar.py` exposing `panel_context()`,
`panel_action()` and `panel_command()`; an application renders whatever
data they return beside the story text. `GamePanel` is the shared calling
convention.

A hook supplies data, never markup. This module never imports a game's
code: it calls a module the application already imported, having made its
own trust decision upstream. Every hook is optional, and one that raises
is logged and treated as absent. Hooks are called by keyword, so a wrong
parameter name fails loudly instead of binding the wrong value.

A game's `panel_context()` answers a dict whose `panel_sections` list holds one
dict per section: the active tab's. `panel_sections_by_tab` maps each tab
id to its sections, and `panel_slots` lists sections an application draws
below the active tab's, in the order given, whichever tab is active.
A section with no `layout` is a list: `heading`,
`rows`, `empty_text`. A section with `layout` set to `COMPASS_LAYOUT` is
an exits panel, built by `exits_section()`: `heading` and `exits`, each
exit a dict of `id`, `label`, `position` and `passable`, plus the
`arrival_knot` and `travel_text` an application passes to
`ink_engine.travel.take_exit()` when the player picks it.

A section with `layout` set to `ACTIONS_LAYOUT` names a menu knot, built by
`actions_section()`. The knot's choices are the actions, guarded in Ink and
tagged `# group: <id>` and `# image: <path>`. A game cannot list them
itself, since its hooks do not receive the story state, so an application
calls `fill_action_sections()` on the context, which adds `groups`: one per
group id in story order, each `{id, image_urls, actions}`, each action
`{group, label, target}`. A group's picture is the first `image` tag among
its actions. When the player picks an action, the application looks it up
with `find_action()` in a freshly filled context and passes its `target`
to `InkRuntimeState.start_interlude()`. A menu knot holds only choices:
it is evaluated on a copy of the story state, but with the live bindings.

A section with `layout` set to `FOLLOWERS_LAYOUT` names both a list of
entries and a menu knot, built by `followers_section()`. An entry is
`{id, label, head_shot_function}`: a game builds the list itself (who is
present is its own vocabulary), naming for each one an `== function ==`
that returns the picture to show for it now. The knot supplies actions the
same way an actions section does, matched to an entry by `# group: <id>`;
an entry with no matching group keeps its head shot and no actions. An
application calls `fill_followers_sections()`, which adds `rows`: one per
entry in the order given, each `{id, label, image_urls, actions}`. A row's
actions are found and run exactly as an action section's are, with
`find_action()` and `InkRuntimeState.start_interlude()`.

A game's `panel_command()` answers either a string, a message for the
panel that leaves the story where it is (an Examine, a refusal), or a dict
naming the story turn that is the command's reaction: `knot` (str,
required), the knot or `knot.stitch` to play; `message` (str, optional,
default ""), panel text shown with the turn; and `label` (str, optional,
default `message`), what the transcript records the player as doing.
`GamePanel.command_result()` reads either answer as a `CommandResult`, and
an application plays a knot answer with `play_reaction()`: a jump to the
knot, standard Ink's ChoosePathString, then `continue_story()`, so it
counts as a turn with the same staleness guard and undo snapshot a choice
gets. A reaction that should leave the player where they were ends by
diverting back to the current location's knot, which shows its choices
again. Any other answer is logged and treated as "".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from ink_engine.engine import InkPathError, InkRuntimeState, InterludeError
from ink_engine.media_resolver import MediaResolver, parse_media_tags
from ink_engine.plugin import EngineState
from ink_engine.travel import MOVE_CHOICE_TEXT

#: The names a game's own `sidebar.py` may define. A game defines the ones
#: it wants; every one is optional.
PANEL_CONTEXT_HOOK = "panel_context"
PANEL_ACTION_HOOK = "panel_action"
PANEL_COMMAND_HOOK = "panel_command"

#: The `layout` of a section drawn as a compass rather than a list.
COMPASS_LAYOUT = "compass"


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a panel command answered.

    Attributes:
        message: Text for the panel's detail area; "" for none.
        knot: The knot or `knot.stitch` to play as the command's reaction,
            or None when the command does not advance the story.
        label: What the transcript records the player as doing.
    """

    message: str = ""
    knot: str | None = None
    label: str = ""


#: The heading `exits_section()` gives a section unless told otherwise.
EXITS_HEADING = "Exits"

#: The `layout` of a section listing a menu knot's choices as actions.
ACTIONS_LAYOUT = "actions"

#: The choice tag naming the group an action belongs to.
GROUP_TAG = "group"

#: The `layout` of a section listing entries with a picture from Ink and
#: actions from a menu knot, some entries having none.
FOLLOWERS_LAYOUT = "followers"


@dataclass(frozen=True, slots=True)
class GamePanel:
    """One session's view of a game's own side-panel hooks.

    Built per call from what the application already holds; every hook
    receives the same `engine_state`, `globals_` and `bindings`.

    Attributes:
        module: The game's already-imported `sidebar` module, or None.
        engine_state: The session's live plugin-state dict. A hook may
            mutate it; `panel_command` is expected to.
        globals_: The runtime's Ink globals, likewise mutable.
        bindings: The session's real EXTERNAL bindings, so a hook can ask
            what the story can.
        logger: Where to report a raising hook.
    """

    module: ModuleType | None
    engine_state: EngineState
    globals_: dict[str, Any]
    bindings: dict[str, Any]
    logger: logging.Logger | None = None

    def context(self) -> dict[str, Any] | None:
        """Ask the game for the data its side panel should render.

        Read-only by contract: nothing returned here is persisted.

        Returns:
            The panel's data, or None when this game supplies no panel.
        """
        return self._run(PANEL_CONTEXT_HOOK, default=None)

    def action(self, action_id: str, target_id: str) -> str:
        """Run one of the panel's read-only row actions (e.g. "examine").

        Args:
            action_id: Which action the row offered.
            target_id: What it was invoked on.

        Returns:
            The text to show, or "" when unrecognised or unavailable.
        """
        return self._run(PANEL_ACTION_HOOK, default="", action_id=action_id, target_id=target_id)

    def command(self, command_id: str, target_id: str) -> str:
        """Run one of the panel's state-changing commands and answer its message.

        Args:
            command_id: Which command the row offered.
            target_id: What it was invoked on.

        Returns:
            `command_result(command_id, target_id).message`.
        """
        return self.command_result(command_id, target_id).message

    def command_result(self, command_id: str, target_id: str) -> CommandResult:
        """Run one of the panel's state-changing commands (e.g. "use", "cast").

        Expected to mutate `engine_state`, and may mutate `globals_`; an
        application persists both as it would after a mid-turn binding
        call. The command itself does not advance the story; a result
        naming a knot asks the application to play one turn with
        `play_reaction()`.

        Args:
            command_id: Which command the row offered.
            target_id: What it was invoked on.

        Returns:
            The answer, read as the module docstring describes. An
            unrecognised, unavailable or malformed answer is an empty
            result. A raising command answers an empty result and may
            leave state partly mutated, as a raising EXTERNAL binding
            mid-turn would.
        """
        answer = self._run(PANEL_COMMAND_HOOK, default="", expected_types=(str, dict), command_id=command_id, target_id=target_id)
        if isinstance(answer, str):
            return CommandResult(message=answer)
        knot, message = answer.get("knot"), answer.get("message", "")
        label = answer.get("label", message)
        if not (isinstance(knot, str) and isinstance(message, str) and isinstance(label, str)):
            (self.logger or logging.getLogger(__name__)).warning("ink_engine.game_panel: %s answered a malformed result; ignored", PANEL_COMMAND_HOOK)
            return CommandResult()
        return CommandResult(message=message, knot=knot, label=label)

    def _run(self, hook_name: str, *, default: Any, expected_types: tuple[type, ...] | None = None, **extra_args: str) -> Any:
        """Call one hook by keyword, or answer `default`.

        The hook's answer must be an instance of `expected_types`, or,
        when that is None, of `type(default)`, with a None default meaning
        any dict. An absent hook, a raising one, or a wrong-typed answer
        all answer `default`.
        """
        hook = getattr(self.module, hook_name, None) if self.module is not None else None
        if not callable(hook):
            return default

        try:
            result = hook(engine_state=self.engine_state, globals_=self.globals_, bindings=self.bindings, **extra_args)
        except Exception:  # pylint: disable=broad-except
            (self.logger or logging.getLogger(__name__)).exception("ink_engine.game_panel: %s failed; treating the panel as absent", hook_name)
            return default

        if expected_types is None:
            expected_types = (dict,) if default is None else (type(default),)
        return result if isinstance(result, expected_types) else default


def exit_id(exit_: dict[str, Any]) -> str:
    """Return the identifier an exits section gives one exit.

    Positions are unique within one location, so a positioned exit is
    named by its position and any other by its destination.

    Args:
        exit_: One exit, as `LocationGraph.exits_from()` returns it.

    Returns:
        `"position:<position>"`, or `"to:<destination>"` for an exit
        with no position.
    """
    if exit_.get("position"):
        return f"position:{exit_['position']}"
    return f"to:{exit_['to']}"


def exits_section(exits: list[dict[str, Any]], *, heading: str = EXITS_HEADING) -> dict[str, Any] | None:
    """Build a compass section from one location's exits.

    An exit with neither a `position` nor an `arrival_knot` is left out:
    it has nowhere to be drawn on the compass and nothing to do when
    picked. An exit is `passable` only when the location graph says it is
    and it has an `arrival_knot` to travel to.

    Args:
        exits: The location's exits, as `LocationGraph.exits_from()`
            returns them.
        heading: The section's heading.

    Returns:
        The section, or None when no exit is left to show, so a game
        whose exits carry no positions or arrival knots shows no exits
        panel at all.
    """
    shown = [
        {
            "id": exit_id(exit_),
            "label": exit_["label"],
            "position": exit_.get("position"),
            "passable": bool(exit_.get("passable")) and exit_.get("arrival_knot") is not None,
            "arrival_knot": exit_.get("arrival_knot"),
            "travel_text": exit_.get("travel_text") or "",
        }
        for exit_ in exits
        if exit_.get("position") or exit_.get("arrival_knot")
    ]
    if not shown:
        return None
    return {"heading": heading, "layout": COMPASS_LAYOUT, "exits": shown}


def _all_sections(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every section in a panel context: its tabs' and its slots', each once."""
    panel = panel or {}
    candidates = list(panel.get("panel_sections") or [])
    for tab_sections in (panel.get("panel_sections_by_tab") or {}).values():
        candidates.extend(tab_sections)
    candidates.extend(panel.get("panel_slots") or [])
    seen: set[int] = set()
    sections = []
    for section in candidates:
        if isinstance(section, dict) and id(section) not in seen:
            seen.add(id(section))
            sections.append(section)
    return sections


def compass_sections(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every compass section in a panel context, across its tabs and slots.

    Args:
        panel: A `GamePanel.context()` answer, or None.

    Returns:
        The sections whose `layout` is `COMPASS_LAYOUT`, possibly empty.
    """
    return [section for section in _all_sections(panel) if section.get("layout") == COMPASS_LAYOUT]


def find_exit(panel: dict[str, Any] | None, wanted_id: str) -> dict[str, Any] | None:
    """Return the passable exit named `wanted_id` from a panel's compass sections.

    An application calls this on a panel context it has just asked the
    game for, so the exit taken is one the game offers now rather than
    whatever the player's screen last showed.

    Args:
        panel: A `GamePanel.context()` answer, or None.
        wanted_id: The exit's `id`.

    Returns:
        The exit, or None when no compass section offers a passable exit
        by that id.
    """
    for section in compass_sections(panel):
        for exit_ in section.get("exits", []):
            if exit_.get("id") == wanted_id and exit_.get("passable"):
                return exit_
    return None


def choices_beside_panel(choices: list[dict[str, Any]], panel: dict[str, Any] | None, *, move_choice: str = MOVE_CHOICE_TEXT) -> list[dict[str, Any]]:
    """Return a turn's choices minus the story's movement choice while the panel draws a compass.

    The compass takes an exit through that choice (`ink_engine.travel.take_exit()`),
    so listing it among the choices as well offers the same move twice.

    Args:
        choices: The turn's choices, each a dict with at least a `text` key.
        panel: The `GamePanel.context()` answer shown beside them, or None.
        move_choice: The movement choice's text.

    Returns:
        `choices` unchanged when the panel has no compass section; otherwise
        a new list without the movement choice. The rest keep their own keys.
    """
    if not compass_sections(panel):
        return choices
    return [choice for choice in choices if choice.get("text") != move_choice]


def actions_section(knot: str, *, heading: str, empty_text: str = "") -> dict[str, Any]:
    """Declare a section listing a menu knot's choices, for a game's `panel_context()`.

    Args:
        knot: The menu knot, by path.
        heading: The section's heading.
        empty_text: What to show when the knot offers no choices.

    Returns:
        The section, to be filled by `fill_action_sections()`.
    """
    return {"heading": heading, "layout": ACTIONS_LAYOUT, "knot": knot, "empty_text": empty_text}


def action_sections(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every action section in a panel context, across its tabs and slots.

    Args:
        panel: A `GamePanel.context()` answer, or None.

    Returns:
        The sections whose `layout` is `ACTIONS_LAYOUT`, possibly empty.
    """
    return [section for section in _all_sections(panel) if section.get("layout") == ACTIONS_LAYOUT]


def _tag_value(tags: list[str], name: str) -> str | None:
    """Return the value of the first `name: value` tag, or None."""
    for tag in tags:
        key, separator, value = tag.partition(":")
        if separator and key.strip() == name:
            return value.strip()
    return None


def _action_groups(state: InkRuntimeState, knot: str, resolver: MediaResolver | None) -> list[dict[str, Any]]:
    """List a menu knot's choices as groups of actions; an unknown knot lists none."""
    try:
        choices = state.knot_choices(knot)
    except InterludeError:
        logging.getLogger(__name__).warning("ink_engine.game_panel: action section names no knot %r", knot)
        return []
    groups: dict[str, dict[str, Any]] = {}
    for choice in choices:
        group_id = _tag_value(choice.tags, GROUP_TAG) or ""
        group = groups.setdefault(group_id, {"id": group_id, "image_urls": [], "actions": []})
        group["actions"].append({"group": group_id, "label": choice.text, "target": choice.target_path})
        images = [request for request in parse_media_tags(choice.tags) if request[0] == "image"][:1]
        if images and not group["image_urls"] and resolver is not None:
            group["image_urls"] = resolver.resolve(images)
    return list(groups.values())


def fill_action_sections(panel: dict[str, Any] | None, state: InkRuntimeState, *, resolver: MediaResolver | None = None) -> dict[str, Any] | None:
    """Return a copy of a panel context with every action section's `groups` listed.

    Each menu knot is evaluated with `InkRuntimeState.knot_choices()`, so
    the live state is unchanged. A section naming no knot of the story
    lists no groups, and a warning is logged.

    Args:
        panel: A `GamePanel.context()` answer, or None.
        state: The session's story state, at the turn being shown.
        resolver: Turns each group's `image` tag into displayable
            references; without one, groups have no images.

    Returns:
        The filled context, or None when `panel` is None. `panel` itself
        is not changed.
    """
    if panel is None:
        return None
    filled: dict[int, dict[str, Any]] = {
        id(section): {**section, "groups": _action_groups(state, str(section.get("knot", "")), resolver)} for section in action_sections(panel)
    }
    if not filled:
        return panel

    def fill(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [filled.get(id(section), section) for section in sections]

    result = dict(panel)
    for key in ("panel_sections", "panel_slots"):
        if panel.get(key):
            result[key] = fill(panel[key])
    if panel.get("panel_sections_by_tab"):
        result["panel_sections_by_tab"] = {tab: fill(sections) for tab, sections in panel["panel_sections_by_tab"].items()}
    return result


def find_action(panel: dict[str, Any] | None, group: str, label: str) -> dict[str, Any] | None:
    """Return the action `label` in group `group` from a panel's filled action or followers sections.

    An application calls this on a context it has just asked the game for
    and filled (with `fill_action_sections()`, `fill_followers_sections()`,
    or both), so the action run is one the story offers now rather than
    whatever the player's screen last showed.

    Args:
        panel: A filled panel context, or None.
        group: The action's group id; "" for an ungrouped action.
        label: The action's label.

    Returns:
        The action, whose `target` goes to `InkRuntimeState.start_interlude()`,
        or None when no action or followers section offers it now.
    """
    for section in action_sections(panel):
        for listed_group in section.get("groups", []):
            for action in listed_group.get("actions", []):
                if action.get("group") == group and action.get("label") == label:
                    return action
    for section in followers_sections(panel):
        for row in section.get("rows", []):
            for action in row.get("actions", []):
                if action.get("group") == group and action.get("label") == label:
                    return action
    return None


def followers_section(entries: list[dict[str, Any]], *, heading: str, knot: str, empty_text: str = "") -> dict[str, Any]:
    """Declare a section listing entries with a head shot from Ink and actions from a menu knot.

    Args:
        entries: One dict per entry, in the order to show them: `id`,
            `label`, and `head_shot_function`, an `== function ==` of the
            story that `fill_followers_sections()` evaluates for the
            picture to show now.
        heading: The section's heading.
        knot: The menu knot whose choices are matched to entries by
            `# group: <id>` (see `actions_section()`); an entry with no
            matching group shows only its head shot.
        empty_text: What to show when `entries` is empty.

    Returns:
        The section, to be filled by `fill_followers_sections()`.
    """
    return {"heading": heading, "layout": FOLLOWERS_LAYOUT, "entries": entries, "knot": knot, "empty_text": empty_text}


def followers_sections(panel: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return every followers section in a panel context, across its tabs and slots.

    Args:
        panel: A `GamePanel.context()` answer, or None.

    Returns:
        The sections whose `layout` is `FOLLOWERS_LAYOUT`, possibly empty.
    """
    return [section for section in _all_sections(panel) if section.get("layout") == FOLLOWERS_LAYOUT]


def _entry_head_shot(state: InkRuntimeState, function_name: str, resolver: MediaResolver | None) -> list[str]:
    """Return the image URLs for one entry's head shot, or none.

    A missing function name is a game authoring mistake, not a player-
    facing failure, so it is logged and treated as no picture rather than
    raised.
    """
    if not function_name or resolver is None:
        return []
    try:
        image_path, _ = state.evaluate_function(function_name)
    except InkPathError:
        logging.getLogger(__name__).warning("ink_engine.game_panel: followers section names no head-shot function %r", function_name)
        return []
    if not isinstance(image_path, str) or not image_path:
        return []
    return resolver.resolve([("image", image_path)])


def _followers_rows(state: InkRuntimeState, section: dict[str, Any], resolver: MediaResolver | None) -> list[dict[str, Any]]:
    """List one followers section's entries with their pictures and actions."""
    groups = {group["id"]: group for group in _action_groups(state, str(section.get("knot", "")), resolver)}
    rows = []
    for entry in section.get("entries", []):
        entry_id = str(entry.get("id", ""))
        group = groups.get(entry_id)
        rows.append(
            {
                "id": entry_id,
                "label": entry.get("label", ""),
                "image_urls": _entry_head_shot(state, str(entry.get("head_shot_function", "")), resolver),
                "actions": group["actions"] if group else [],
            }
        )
    return rows


def fill_followers_sections(panel: dict[str, Any] | None, state: InkRuntimeState, *, resolver: MediaResolver | None = None) -> dict[str, Any] | None:
    """Return a copy of a panel context with every followers section's `rows` listed.

    Each entry's head shot is read with `InkRuntimeState.evaluate_function()`
    and its actions from the section's menu knot with `InkRuntimeState.knot_choices()`,
    so the live state is unchanged either way.

    Args:
        panel: A `GamePanel.context()` answer, or None.
        state: The session's story state, at the turn being shown.
        resolver: Turns each entry's head-shot path into displayable
            references; without one, entries have no images.

    Returns:
        The filled context, or None when `panel` is None. `panel` itself
        is not changed.

    Raises:
        NotAFunctionError: An entry's `head_shot_function` names a knot or
            stitch of the story, not a function -- a game authoring
            mistake worth raising rather than silently showing no picture.
        UnboundExternalError: As for `InkRuntimeState.continue_story()`.
    """
    if panel is None:
        return None
    filled: dict[int, dict[str, Any]] = {
        id(section): {**section, "rows": _followers_rows(state, section, resolver)} for section in followers_sections(panel)
    }
    if not filled:
        return panel

    def fill(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [filled.get(id(section), section) for section in sections]

    result = dict(panel)
    for key in ("panel_sections", "panel_slots"):
        if panel.get(key):
            result[key] = fill(panel[key])
    if panel.get("panel_sections_by_tab"):
        result["panel_sections_by_tab"] = {tab: fill(sections) for tab, sections in panel["panel_sections_by_tab"].items()}
    return result


def play_reaction(state: InkRuntimeState, result: CommandResult) -> str | None:
    """Play a panel command's reaction as a story turn.

    Jumps to `result.knot` with `InkRuntimeState.choose_path()`, which
    advances the turn count and discards the current choices and call
    stack, then continues the story.

    Args:
        state: The session's story state.
        result: A `GamePanel.command_result()` answer.

    Returns:
        The turn's text, or None when `result` names no knot; nothing is
        changed then.

    Raises:
        InkPathError: `result.knot` names no knot of the story. Raised
            before the story is changed.
    """
    if result.knot is None:
        return None
    state.choose_path(result.knot)
    return state.continue_story()
