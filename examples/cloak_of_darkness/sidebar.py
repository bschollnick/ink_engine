"""This game's side panel: a compass of the exits from the player's room.

The story records the room in its `current_location` global; the map
answers which exits leave it. An application draws the section and, when
the player picks an exit, passes its `arrival_knot` and `travel_text` to
`ink_engine.travel.take_exit()`.
"""

from __future__ import annotations

from typing import Any

from ink_engine.game_panel import exits_section

from .locations import CLOAK_MAP

#: The story global naming the player's room (`cloak_of_darkness.ink`).
CURRENT_LOCATION_GLOBAL = "current_location"


def panel_context(engine_state: dict[str, Any], globals_: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any] | None:
    """Return the exits panel for the player's room, or None outside the map."""
    del bindings  # Part of the hook signature; this panel asks the story nothing.
    slot = engine_state.get(CLOAK_MAP.state_key)
    location_id = globals_.get(CURRENT_LOCATION_GLOBAL)
    if slot is None or not isinstance(location_id, str):
        return None
    section = exits_section(CLOAK_MAP.exits_from(slot, location_id))
    return {"panel_sections": [section]} if section is not None else None
