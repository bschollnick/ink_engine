"""This game's map: three rooms, and the exits between them.

Declares the location graph the engine ships, so the game's places,
positions and gates are data rather than knots wired to each other. An
application reads `exits_from()` to offer movement, and the story's own
`movement` knot narrates arriving.

The bar's exit north is always open; the foyer's exit north is the one
the specification refuses, so it is declared `sealed` — it exists, the
player can see it, and it never opens.
"""

from __future__ import annotations

from ink_engine.engine_plugins.location_graph import (
    LocationGraph,
    add_missing_return_exits,
)
from ink_engine.plugin_base import external

LOCATIONS = {
    "locations": {
        "foyer": {
            "known_by_default": True,
            "arrival_knot": "foyer",
            "arrival_text": "You walk back into the foyer.",
            "details": {"name": "Foyer of the Opera House", "terrain": "indoor"},
            "exits": [
                {
                    "to": "bar",
                    "position": "s",
                    "label": "the bar",
                    "arrival_knot": "bar",
                    "travel_text": "You walk south, into the bar.",
                },
                {
                    "to": "cloakroom",
                    "position": "w",
                    "label": "the cloakroom",
                    "arrival_knot": "cloakroom",
                    "travel_text": "You walk west, into the cloakroom.",
                },
                {
                    "to": "street",
                    "position": "n",
                    "label": "the street",
                    "sealed": True,
                    "show_when_blocked": True,
                    "one_way": True,
                },
            ],
        },
        "bar": {
            "known_by_default": True,
            "details": {"name": "Foyer Bar", "terrain": "indoor"},
        },
        "cloakroom": {
            "known_by_default": True,
            "details": {"name": "Cloakroom", "terrain": "indoor"},
        },
        "street": {
            "known_by_default": True,
            "details": {"name": "The Street", "terrain": "city"},
        },
    }
}

#: The return exits — bar to foyer, cloakroom to foyer — are filled in
#: rather than declared, so each corridor is written once. They arrive
#: through the foyer's own `arrival_knot` and `arrival_text`.
MAP = add_missing_return_exits(LOCATIONS)


class CloakMap(LocationGraph):
    """This game's map, with the one binding its story needs."""

    name = "cloak_locations"
    display_name = "Cloak of Darkness map"

    def __init__(self) -> None:
        super().__init__(config=MAP)

    @external
    def location_name_now(self, slot, location_id: str) -> str:
        """EXTERNAL location_name_now(location_id); the place's printed name."""
        return str(self.detail(slot, location_id, "name") or location_id)


CLOAK_MAP = CloakMap()
PLUGIN = CLOAK_MAP.plugin()
