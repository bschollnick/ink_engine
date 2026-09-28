"""A synthetic town map for testing map layouts. Not a test module itself.

86 places: a 5x4 street grid, a ring road whose bearings do not close, a
park and forest trail reached diagonally, a tunnel joined by up/down,
eight buildings of 3-12 rooms named "Building - Room" (one with floors),
and a sealed gate. Every choice is fixed, so the map is the same on
every run.
"""

from __future__ import annotations

from typing import Any

from ink_engine.engine_plugins.location_graph import add_missing_return_exits

#: The ring road's loop east of the grid, which cannot be drawn with every
#: bearing true: its last leg returns to a street two columns west of it.
RING_ROAD = ("rd_1", "rd_2", "rd_3")

#: Building name, the street its entrance opens onto, and its room count.
BUILDINGS = (
    ("Harbour Warehouse", "st_3_2", 6),
    ("Grand Hotel", "st_1_1", 12),
    ("Museum", "st_0_2", 9),
    ("Bakery", "st_2_3", 3),
    ("Town Hall", "st_1_3", 7),
    ("Library", "st_2_0", 5),
    ("Clinic", "st_0_3", 4),
    ("Station", "st_3_1", 8),
)

_PARK_BEARINGS = ("s", "sw", "w")


def _place(locations: dict[str, Any], location_id: str, name: str, terrain: str) -> None:
    """Declare one place with no exits yet."""
    locations[location_id] = {"known_by_default": True, "details": {"name": name, "terrain": terrain}, "exits": []}


def _link(locations: dict[str, Any], origin: str, destination: str, position: str | None = None, **extra: Any) -> None:
    """Declare one exit, labelled with its destination's name."""
    exit_: dict[str, Any] = {"to": destination, "label": locations[destination]["details"]["name"]}
    if position:
        exit_["position"] = position
    locations[origin]["exits"].append({**exit_, **extra})


def _add_streets(locations: dict[str, Any]) -> None:
    """Add the street grid and the ring road east of it."""
    for row in range(4):
        for column in range(5):
            _place(locations, f"st_{row}_{column}", f"Street {chr(65 + row)}{column + 1}", "city")
    for row in range(4):
        for column in range(5):
            if column < 4:
                _link(locations, f"st_{row}_{column}", f"st_{row}_{column + 1}", "e")
            if row < 3:
                _link(locations, f"st_{row}_{column}", f"st_{row + 1}_{column}", "s")
    for location_id, name in zip(RING_ROAD, ("Ring Road East", "Ring Road Bend", "Ring Road North"), strict=True):
        _place(locations, location_id, name, "outdoor")
    _link(locations, "st_1_4", "rd_1", "e")
    _link(locations, "rd_1", "rd_2", "e")
    _link(locations, "rd_2", "rd_3", "n")
    _link(locations, "rd_3", "st_0_4", "w")


def _add_outskirts(locations: dict[str, Any]) -> None:
    """Add the park, the forest trail, the tunnel under the town and the locked yard."""
    for index in range(4):
        _place(locations, f"park_{index}", f"Park Path {index + 1}", "outdoor")
    _link(locations, "st_3_0", "park_0", "sw")
    for index, bearing in enumerate(_PARK_BEARINGS):
        _link(locations, f"park_{index}", f"park_{index + 1}", bearing)
    for index in range(3):
        _place(locations, f"trail_{index}", f"Forest Trail {index + 1}", "forest")
    _link(locations, "park_3", "trail_0", "w")
    _link(locations, "trail_0", "trail_1", "nw")
    _link(locations, "trail_1", "trail_2", "n")

    _place(locations, "tunnel", "Old Tunnel", "indoor")
    _link(locations, "st_0_0", "tunnel", "down")
    _link(locations, "tunnel", "st_3_4", "up", one_way=True)
    _link(locations, "st_3_4", "tunnel", "down")

    _place(locations, "gate_yard", "Locked Yard", "outdoor")
    _link(locations, "st_2_4", "gate_yard", "e", sealed=True, show_when_blocked=True, one_way=True)


def _add_buildings(locations: dict[str, Any]) -> None:
    """Add each building: an entrance off its street, rooms behind it with no positions."""
    for number, (building, street, size) in enumerate(BUILDINGS):
        rooms = [f"b{number}_{index}" for index in range(size)]
        for index, room_id in enumerate(rooms):
            _place(locations, room_id, f"{building} - {'Entrance' if index == 0 else f'Room {index}'}", "indoor")
        _link(locations, street, rooms[0], "in")
        _link(locations, rooms[0], street, "out")
        for index in range(1, size):
            # Each room opens off an earlier one, so every building is one connected block.
            _link(locations, rooms[(index - 1) // 2], rooms[index])
        if building == "Grand Hotel":
            _link(locations, rooms[0], rooms[4], "up")
            _link(locations, rooms[4], rooms[8], "up")


def build_map() -> dict[str, Any]:
    """Return the town as a location graph config, with return exits filled in."""
    locations: dict[str, Any] = {}
    _add_streets(locations)
    _add_outskirts(locations)
    _add_buildings(locations)
    return add_missing_return_exits({"locations": locations})


def build_block_map() -> dict[str, Any]:
    """Return a street with an apartment block, a shop and a basement, grouped by entrances.

    The block's lobby is an entrance; a lift joins its two floors; flats 201
    and 202 open off the second floor and flat 301 off the third, each an
    entrance with two rooms. The shop is an entrance with two rooms and no
    nested building. The basement is indoor with no entrance.
    """
    locations: dict[str, Any] = {}
    for index in range(3):
        _place(locations, f"street_{index}", f"High Street {index + 1}", "city")
        if index:
            _link(locations, f"street_{index - 1}", f"street_{index}", "e")
    for location_id, name in (
        ("lobby", "Apartment Block - Lobby"),
        ("lift", "Apartment Block - Lift"),
        ("floor_2", "Apartment Block - Second Floor"),
        ("floor_3", "Apartment Block - Third Floor"),
        ("shop", "Corner Shop - Counter"),
        ("shop_store", "Corner Shop - Storeroom"),
        ("shop_office", "Corner Shop - Office"),
        ("basement", "Basement"),
        ("basement_boiler", "Basement Boiler Room"),
    ):
        _place(locations, location_id, name, "indoor")
    _link(locations, "street_0", "lobby", "in")
    _link(locations, "lobby", "lift", "e")
    _link(locations, "lift", "floor_2", "up")
    _link(locations, "floor_2", "floor_3", "up")
    for flat, floor in (("201", "floor_2"), ("202", "floor_2"), ("301", "floor_3")):
        _place(locations, f"flat_{flat}", f"Apartment Block - Flat {flat}", "indoor")
        _place(locations, f"flat_{flat}_kitchen", f"Flat {flat} - Kitchen", "indoor")
        _place(locations, f"flat_{flat}_bedroom", f"Flat {flat} - Bedroom", "indoor")
        _link(locations, floor, f"flat_{flat}")
        _link(locations, f"flat_{flat}", f"flat_{flat}_kitchen", "e")
        _link(locations, f"flat_{flat}_kitchen", f"flat_{flat}_bedroom", "n")
    _link(locations, "street_2", "shop", "in")
    _link(locations, "shop", "shop_store", "n")
    _link(locations, "shop", "shop_office", "e")
    _link(locations, "street_1", "basement", "down")
    _link(locations, "basement", "basement_boiler", "e")
    for entrance in ("lobby", "flat_201", "flat_202", "flat_301", "shop"):
        locations[entrance]["details"]["entrance"] = True
    return add_missing_return_exits({"locations": locations})
