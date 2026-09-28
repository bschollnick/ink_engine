"""Lay a map out on a compass grid, version 2 of `map_layout.py`.

Every position is computed here, in Python, from the bearings the exits
declare; the page only draws, zooms, drags and opens buildings, and runs
no simulation. The same positions write a static SVG with no browser.

The layout works on a lattice. A place reached by compass exits takes an
even cell, one bearing step being two cells, so the odd cells between
four places are free for buildings. When the map declares entrances, its
buildings are `location_graph.buildings()`: an entrance and the rooms
behind it, a building nested inside another having its entrance drawn
among its parent's rooms. A map with no entrances falls back to grouping
places whose names share a "Building - " prefix. A building's rooms are
packed into a box in the odd cell beside the place its main entrance
opens onto; a nested building's box goes in the free odd cell nearest
its parent's, and a nested building that is only its entrance is framed
around that entrance inside its parent's box. Each lattice column and row is as wide as its widest content,
so a long name or a large building widens only its own column.

A map's bearings need not close geometrically. When two places compute
to the same cell, the later one moves to the nearest free cell and the
move is reported; every exit drawn well off its bearing is reported
too. An author fixes a bad landing with a pins file.

Used through `map_to_mermaid.py --v2html` and `--v2svg`.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field, replace
from html import escape
from typing import Any

try:  # when run as `python tools/map_to_mermaid.py`
    from map_layout import DIRECTION_VECTORS, PAGE_HEAD, PAGE_HEADER_START, group_of
except ModuleNotFoundError:  # when imported as `tools.map_layout_v2`
    from tools.map_layout import (
        DIRECTION_VECTORS,
        PAGE_HEAD,
        PAGE_HEADER_START,
        group_of,
    )

#: One lattice step per bearing, in screen terms (y grows downward).
STEPS: dict[str, tuple[int, int]] = {
    position: (round(math.copysign(1, dx)) if abs(dx) > 0.1 else 0, round(math.copysign(1, dy)) if abs(dy) > 0.1 else 0)
    for position, (dx, dy) in DIRECTION_VECTORS.items()
}

#: An exit drawn more than this many degrees off its bearing is reported.
OFF_BEARING_DEGREES = 22.5

# Spacing, in pixels.
PLACE_PITCH = 110  # the least width and height of a column or row holding a place
GAP_PITCH = 50  # an empty column or row between places
ROOM_PITCH = 44  # the least distance between rooms inside a building
BOX_PADDING = 24  # space around a building's rooms inside its column
LABEL_CHARACTER_WIDTH = 6.2  # an 11px label's average character width
LABEL_PADDING = 16

#: The width-to-height ratio `layout()` aims the whole map at by default.
DEFAULT_ASPECT = 16 / 9
#: Lattice cells between two packed pieces: an odd cell stays free between them for a building.
PIECE_GAP = 4

Cell = tuple[int, int]


@dataclass
class Layout:
    """Where every place goes, and what could not be drawn true.

    Attributes:
        positions: Location id to `[x, y]` pixels, every place shown open.
        buildings: Building key (its entrance id, or its name prefix on a
            map with no entrances) to its display `name`, its main
            `entrance`, all its `entrances` (main first), the `rooms`
            drawn in its box (an outermost building's main entrance
            first; a nested building's main entrance is in its parent's
            box, and a nested building that is only its entrance lists
            that entrance and is framed around it),
            its `parent` key or None, its `size` (every place inside it,
            entrance and nested buildings included) and its reserved
            `box` `[x0, y0, x1, y1]`. Parents come before their children.
        report: One dict per compromise: `kind` ("moved", "off_bearing",
            "no_bearing", "far_from_door" or "no_entrance"), `place`, and
            `detail`.
    """

    positions: dict[str, list[float]]
    buildings: dict[str, dict[str, Any]]
    report: list[dict[str, str]] = field(default_factory=list)


def label_width(text: str) -> float:
    """Return the drawn width of a one-line label, in pixels."""
    return len(text) * LABEL_CHARACTER_WIDTH


def room_label(name: str) -> str:
    """Return a room's own name, without its building's prefix."""
    return name.split(" - ", 1)[1] if " - " in name else name


def _ring(centre: Cell, radius: int) -> list[Cell]:
    """Return the cells at Chebyshev distance `radius`, nearest first."""
    cx, cy = centre
    cells = [(cx + dx, cy + dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1) if max(abs(dx), abs(dy)) == radius]
    return sorted(cells, key=lambda cell: (math.dist(cell, centre), cell[1], cell[0]))


def _nearest_free(want: Cell, taken: dict[Cell, str], parity: int) -> Cell:
    """Return `want`, or the nearest cell with both coordinates of `parity` that nothing holds."""
    for radius in range(0, 200):
        for cell in [want] if radius == 0 else _ring(want, radius):
            if cell[0] % 2 == parity and cell[1] % 2 == parity and cell not in taken:
                return cell
    raise ValueError(f"no free cell near {want}")


@dataclass
class _Placer:
    """The lattice as it fills: which place holds which cell, and what moved."""

    cell: dict[str, Cell] = field(default_factory=dict)
    taken: dict[Cell, str] = field(default_factory=dict)
    report: list[dict[str, str]] = field(default_factory=list)

    def put(self, place: str, want: Cell, reason: str) -> None:
        """Give `place` the even cell `want`, or the nearest free one, reporting a move."""
        cell = _nearest_free(want, self.taken, parity=0)
        if cell != want:
            self.report.append(
                {"kind": "moved", "place": place, "detail": f"wanted cell {want} ({reason}), held by {self.taken[want]}; placed at {cell}"}
            )
        self.cell[place] = cell
        self.taken[cell] = place


@dataclass
class _Shelves:
    """Rows of pieces packed left to right below the main area, each row at most `width` cells wide."""

    left: int
    y: int
    width: int
    x: int = field(init=False)
    row_height: int = 0

    def __post_init__(self) -> None:
        self.x = self.left

    def reserve(self, width: int, height: int) -> Cell:
        """Return the even top-left cell of a free `width` x `height` span, starting a new row when this one is full."""
        if self.x > self.left and self.x + width > self.left + self.width:
            self.x, self.y, self.row_height = self.left, self.y + self.row_height + PIECE_GAP, 0
        origin = (self.x, self.y)
        self.x += width + PIECE_GAP
        self.row_height = max(self.row_height, height)
        return origin


def _even(value: int) -> int:
    """Return `value` rounded up to an even number."""
    return value + value % 2


def _span(cells: list[Cell]) -> tuple[int, int, int, int]:
    """Return the lattice bounding box `(min x, min y, width, height)` of some cells."""
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _place_piece(placer: _Placer, shelves: _Shelves, local: dict[str, Cell]) -> None:
    """Move a piece laid out in its own lattice onto the next free shelf span."""
    x0, y0, width, height = _span(list(local.values()))
    ox, oy = shelves.reserve(_even(width), _even(height))
    for place, (x, y) in local.items():
        placer.put(place, (ox + x - x0, oy + y - y0), "packed below the main area")


def _adjacency(graph: dict[str, Any], in_building: set[str]) -> tuple[dict[str, list[tuple[str, Cell]]], dict[str, list[str]]]:
    """Split the links into compass steps between places, and every other connection."""
    compass: dict[str, list[tuple[str, Cell]]] = {node["id"]: [] for node in graph["nodes"]}
    other: dict[str, list[str]] = {node["id"]: [] for node in graph["nodes"]}
    for link in graph["links"]:
        source, target = link["source"], link["target"]
        step = STEPS.get(link.get("position") or "")
        if step is not None and source not in in_building and target not in in_building:
            compass[source].append((target, step))
            compass[target].append((source, (-step[0], -step[1])))
        else:
            other[source].append(target)
            other[target].append(source)
    return compass, other


def _walk_compass(placer: _Placer, compass: dict[str, list[tuple[str, Cell]]], seed: str) -> None:
    """Place `seed` at the origin and walk its connected run of compass exits outward."""
    placer.put(seed, (0, 0), "start of an area")
    queue = deque([seed])
    while queue:
        here = queue.popleft()
        hx, hy = placer.cell[here]
        for there, (dx, dy) in compass[here]:
            if there not in placer.cell:
                placer.put(there, (hx + 2 * dx, hy + 2 * dy), f"{dx:+d},{dy:+d} from {here}")
                queue.append(there)


def _compass_areas(compass: dict[str, list[tuple[str, Cell]]], order: list[str]) -> list[_Placer]:
    """Lay out each connected run of compass exits in its own lattice, from its busiest place, largest first."""
    spatial = [place for place in order if compass[place]]
    areas: list[_Placer] = []
    placed: set[str] = set()
    while pending := [place for place in spatial if place not in placed]:
        area = _Placer()
        _walk_compass(area, compass, max(pending, key=lambda place: (len(compass[place]), -spatial.index(place))))
        placed.update(area.cell)
        areas.append(area)
    return sorted(areas, key=lambda area: -len(area.cell))


def _report_bearings(placer: _Placer, compass: dict[str, list[tuple[str, Cell]]]) -> None:
    """Report every compass exit drawn more than `OFF_BEARING_DEGREES` off its bearing."""
    seen: set[tuple[str, str]] = set()
    for here, steps in compass.items():
        for there, (dx, dy) in steps:
            if (there, here) in seen:
                continue
            seen.add((here, there))
            (hx, hy), (tx, ty) = placer.cell[here], placer.cell[there]
            drawn = math.degrees(math.atan2(ty - hy, tx - hx) - math.atan2(dy, dx))
            off = abs((drawn + 180) % 360 - 180)
            if off > OFF_BEARING_DEGREES:
                placer.report.append({"kind": "off_bearing", "place": f"{here} -> {there}", "detail": f"drawn {off:.0f} degrees off its bearing"})


def _place_beside_neighbours(placer: _Placer, other: dict[str, list[str]], remaining: list[str]) -> None:
    """Place each of `remaining` that connects to a placed place beside those places, removing it from the list."""
    progressed = True
    while progressed:
        progressed = False
        for place in list(remaining):
            neighbours = [placer.cell[n] for n in other[place] if n in placer.cell]
            if not neighbours:
                continue
            centre = (sum(c[0] for c in neighbours) / len(neighbours), sum(c[1] for c in neighbours) / len(neighbours))
            placer.put(place, (round(centre[0] / 2) * 2, round(centre[1] / 2) * 2), "beside the places it connects to")
            placer.report.append({"kind": "no_bearing", "place": place, "detail": f"no compass exit; placed beside {len(neighbours)} neighbour(s)"})
            remaining.remove(place)
            progressed = True


def _loose_groups(other: dict[str, list[str]], remaining: list[str]) -> list[list[str]]:
    """Split places connected to nothing placed into groups joined by their own exits, each in walking order."""
    left, groups = set(remaining), []
    for start in remaining:
        if start not in left:
            continue
        group, queue = [], deque([start])
        left.discard(start)
        while queue:
            here = queue.popleft()
            group.append(here)
            for there in other[here]:
                if there in left:
                    left.discard(there)
                    queue.append(there)
        groups.append(group)
    return groups


def _place_unbearinged(placer: _Placer, shelves: _Shelves, other: dict[str, list[str]], loose: list[str]) -> None:
    """Place each place no compass exit reaches beside the places it connects to, packing the rest onto shelves."""
    remaining = list(loose)
    _place_beside_neighbours(placer, other, remaining)
    for group in _loose_groups(other, remaining):
        columns = math.ceil(math.sqrt(len(group)))
        _place_piece(placer, shelves, {place: (2 * (index % columns), 2 * (index // columns)) for index, place in enumerate(group)})
        for place in group:
            placer.report.append(
                {"kind": "no_bearing", "place": place, "detail": "no compass exit and connected to nothing placed; packed below the main area"}
            )


_ROOM_PREFERENCE = ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))


def _room_cell(near: Cell, free_cells: list[Cell], taken: set[Cell]) -> Cell:
    """Return the free cell beside `near` in preference order, else the nearest free cell."""
    beside = [(near[0] + dx, near[1] + dy) for dx, dy in _ROOM_PREFERENCE]
    options = [cell for cell in beside if cell in free_cells and cell not in taken]
    if options:
        return options[0]
    return min((cell for cell in free_cells if cell not in taken), key=lambda cell: (math.dist(cell, near), cell[1], cell[0]))


def _pack_rooms(rooms: list[str], other: dict[str, list[str]], mirror: tuple[bool, bool]) -> dict[str, Cell]:
    """Pack a building's rooms into about sqrt(n) columns, the entrance at the corner facing its street."""
    width = math.ceil(math.sqrt(len(rooms)))
    free_cells = [(x, y) for y in range(len(rooms)) for x in range(width)]
    local: dict[str, Cell] = {rooms[0]: (0, 0)}
    queue = deque([rooms[0]])
    while queue:
        here = queue.popleft()
        for there in other[here]:
            if there in rooms and there not in local:
                local[there] = _room_cell(local[here], free_cells, set(local.values()))
                queue.append(there)
    for room in rooms:  # a room no door inside the building reaches
        if room not in local:
            local[room] = _room_cell(local[rooms[0]], free_cells, set(local.values()))
    columns = max(x for x, _ in local.values()) + 1
    rows = max(y for _, y in local.values()) + 1
    return {room: ((columns - 1 - x) if mirror[0] else x, (rows - 1 - y) if mirror[1] else y) for room, (x, y) in local.items()}


@dataclass
class _Building:
    """One building to draw: the places in its box, and where it sits in the tree."""

    key: str
    name: str
    boxed: list[str]
    entrances: list[str]  # the main one first; empty until a name-prefix building's door is found
    parent: str | None
    size: int
    framed: bool = False  # nested with nothing but its entrance: framed where its parent's box draws that entrance

    @property
    def entrance(self) -> str | None:
        """Return the main entrance, or None before a name-prefix building's door is found."""
        return self.entrances[0] if self.entrances else None


def _place_buildings(
    placer: _Placer, shelves: _Shelves, buildings: list[_Building], other: dict[str, list[str]]
) -> tuple[dict[str, Cell], dict[str, dict[str, Cell]], list[_Building]]:
    """Put each outermost building in the odd cell beside the place its entrance opens onto, each nested one beside its parent.

    Returns:
        Each building's cell, its rooms' cells inside the box, and the
        buildings with their entrances resolved and an outermost one's
        entrance first in its box.
    """
    in_building = {place for building in buildings for place in building.boxed}
    block: dict[str, Cell] = {}
    block_taken: dict[Cell, str] = {}
    rooms: dict[str, dict[str, Cell]] = {}
    resolved: list[_Building] = []
    for building in buildings:
        if building.framed:
            resolved.append(building)
            continue
        if building.parent is not None:
            street = block[building.parent]
            cell = _nearest_free(street, block_taken, parity=1)
        else:
            door = next(
                (
                    (m, n)
                    for m in ([building.entrance] if building.entrance else building.boxed)
                    for n in other[m]
                    if n not in in_building and n in placer.cell
                ),
                None,
            )
            cell, street = _building_cell(placer, shelves, block_taken, name=building.key, street=door[1] if door else None)
            entrance = building.entrance or (door[0] if door else building.boxed[0])
            building = replace(building, entrances=building.entrances or [entrance], boxed=[entrance, *(m for m in building.boxed if m != entrance)])
        block[building.key], block_taken[cell] = cell, building.key
        rooms[building.key] = _pack_rooms(building.boxed, other, mirror=(cell[0] < street[0], cell[1] < street[1]))
        resolved.append(building)
    return block, rooms, resolved


def _building_cell(placer: _Placer, shelves: _Shelves, block_taken: dict[Cell, str], *, name: str, street: str | None) -> tuple[Cell, Cell]:
    """Return the odd cell for building `name` and the even cell of the street it faces, on a shelf when it has no door."""
    if street is None:
        placer.report.append({"kind": "far_from_door", "place": name, "detail": "opens onto no placed place"})
        origin = shelves.reserve(2, 2)
        cell = _nearest_free((origin[0] + 1, origin[1] + 1), block_taken, parity=1)
        return cell, (cell[0] - 1, cell[1] - 1)
    street_cell = placer.cell[street]
    cell = _nearest_free((street_cell[0] + 1, street_cell[1] + 1), block_taken, parity=1)
    if math.dist(cell, street_cell) > 1.5:
        placer.report.append({"kind": "far_from_door", "place": name, "detail": f"no free block beside {street}"})
    return cell, street_cell


def _buildings_of(names: dict[str, str]) -> list[_Building]:
    """Return every building of two or more places, by the "Building - " prefix of their names."""
    groups: dict[str, list[str]] = {}
    for place, name in names.items():
        groups.setdefault(group_of(name), []).append(place)
    return [
        _Building(key=building, name=building, boxed=members, entrances=[], parent=None, size=len(members))
        for building, members in groups.items()
        if len(members) > 1
    ]


def _buildings_from_tree(names: dict[str, str], tree: dict[str, Any]) -> list[_Building]:
    """Flatten `location_graph.buildings()`'s tree, parents first, keeping only places the graph draws.

    A nested building whose only place on the drawn map is its entrance
    is framed around that entrance, in its parent's box.
    """
    flat: list[_Building] = []

    def size(node: dict[str, Any]) -> int:
        own = [place for place in (*node.get("entrances", [node["entrance"]]), *node["rooms"]) if place in names]
        return len(own) + sum(size(child) for child in node["buildings"] if child["entrance"] in names)

    def visit(node: dict[str, Any], parent: str | None) -> None:
        entrance = node["entrance"]
        if entrance not in names:
            return
        entrances = [entrance, *(other for other in node.get("entrances", [entrance])[1:] if other in names)]
        rooms = [room for room in node["rooms"] if room in names]
        children = [child for child in node["buildings"] if child["entrance"] in names]
        boxed = [*([entrance] if parent is None else []), *entrances[1:], *rooms, *(child["entrance"] for child in children)]
        name = group_of(names[entrance]) if parent is None else room_label(names[entrance])
        flat.append(
            _Building(
                key=entrance,
                name=name,
                boxed=boxed or [entrance],
                entrances=entrances,
                parent=parent,
                size=size(node),
                framed=not boxed,
            )
        )
        for child in children:
            visit(child, entrance)

    for node in tree["buildings"]:
        visit(node, None)
    return flat


def layout(
    graph: dict[str, Any], pins: dict[str, list[float]] | None = None, *, aspect: float = DEFAULT_ASPECT, tree: dict[str, Any] | None = None
) -> Layout:
    """Compute every place's position from its exits' bearings.

    The largest area of compass exits is laid out first. Every other
    piece -- another compass area, places connected to nothing placed, a
    building with no door -- is packed in rows below it, the row width
    chosen so the whole map comes nearest `aspect`.

    Args:
        graph: `map_layout.build_graph()`'s answer: nodes with `id` and
            `name`, links with `source`, `target` and `position`.
        pins: Location id to `[x, y]` pixels, applied last, overriding the
            computed position of each place named.
        aspect: The width-to-height ratio to aim the whole map at.
        tree: `location_graph.buildings()` for the map, to group it by
            its entrances; None groups it by name prefix. Each of its
            `no_entrance` places the graph draws is reported.

    Returns:
        The positions with every building open, the buildings, and the
        report.
    """
    names = {node["id"]: node["name"] for node in graph["nodes"]}
    buildings = _buildings_from_tree(names, tree) if tree is not None else _buildings_of(names)
    in_building = {place for building in buildings for place in building.boxed}
    compass, other = _adjacency(graph, in_building)
    parts = _MapParts(names, buildings, compass, other, _compass_areas(compass, list(names)))
    main_width = _span(list(parts.areas[0].cell.values()))[2] if parts.areas else 0
    widths = range(max(main_width, 8), max(main_width, 2 * len(names)) + 8, 8)
    best = min((_layout_with_width(parts, width) for width in widths), key=lambda result: abs(math.log(_aspect_of(result) / aspect)))
    best.positions.update({place: [float(x), float(y)] for place, (x, y) in (pins or {}).items() if place in best.positions})
    best.report.extend(
        {"kind": "no_entrance", "place": place, "detail": "indoor, but no entrance leads to it"}
        for place in (tree or {}).get("no_entrance", [])
        if place in names
    )
    return best


@dataclass
class _MapParts:
    """What every trial layout of one map starts from."""

    names: dict[str, str]
    buildings: list[_Building]
    compass: dict[str, list[tuple[str, Cell]]]
    other: dict[str, list[str]]
    areas: list[_Placer]


def _place_compass_areas(parts: _MapParts, width: int) -> tuple[_Placer, _Shelves]:
    """Place the main compass area, open shelves below it `width` cells wide, and pack the other areas onto them."""
    placer = _Placer()
    for place, cell in (parts.areas[0].cell if parts.areas else {}).items():
        placer.put(place, cell, "main area")
    placer.report.extend(item for area in parts.areas for item in area.report)
    x0, y0, _, height = _span(list(placer.cell.values())) if placer.cell else (0, 0, 0, 0)
    shelves = _Shelves(left=x0, y=y0 + height + PIECE_GAP, width=width)
    for area in parts.areas[1:]:
        _place_piece(placer, shelves, area.cell)
    return placer, shelves


def _layout_with_width(parts: _MapParts, width: int) -> Layout:
    """Lay the map out with its packed pieces in rows at most `width` lattice cells wide."""
    placer, shelves = _place_compass_areas(parts, width)
    _report_bearings(placer, parts.compass)
    in_building = {place for building in parts.buildings for place in building.boxed}
    loose = [place for place in parts.names if place not in placer.cell and place not in in_building]
    _place_unbearinged(placer, shelves, parts.other, loose)
    block, rooms, resolved = _place_buildings(placer, shelves, parts.buildings, parts.other)
    positions, boxes = _to_pixels(parts.names, placer.cell, block, rooms)
    for building in resolved:
        if building.framed:
            (x, y), half = positions[building.entrances[0]], max(ROOM_PITCH, label_width(building.name) + LABEL_PADDING) / 2
            boxes[building.key] = [x - half, y - ROOM_PITCH / 2, x + half, y + ROOM_PITCH / 2]
    return Layout(
        positions=positions,
        buildings={
            b.key: {
                "name": b.name,
                "entrance": b.entrance,
                "entrances": b.entrances,
                "rooms": b.boxed,
                "parent": b.parent,
                "size": b.size,
                "box": boxes[b.key],
            }
            for b in resolved
        },
        report=list(placer.report),
    )


def _aspect_of(result: Layout) -> float:
    """Return the width-to-height ratio of everything a layout draws, building boxes included."""
    boxes = [building["box"] for building in result.buildings.values()]
    xs = [x for x, _ in result.positions.values()] + [edge for box in boxes for edge in (box[0], box[2])]
    ys = [y for _, y in result.positions.values()] + [edge for box in boxes for edge in (box[1], box[3])]
    return max(max(xs) - min(xs), 1.0) / max(max(ys) - min(ys), 1.0)


def _offsets(extent: dict[int, float]) -> dict[int, float]:
    """Return each lattice column's (or row's) centre, laying spans end to end; an empty one is `GAP_PITCH`."""
    centres, edge = {}, 0.0
    for index in range(min(extent), max(extent) + 1):
        span = extent.get(index, GAP_PITCH)
        centres[index] = edge + span / 2
        edge += span
    return centres


def _building_sizes(names: dict[str, str], rooms: dict[str, dict[str, Cell]]) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    """Return each building's room pitch (its widest room label) and its box size."""
    pitch: dict[str, float] = {}
    size: dict[str, tuple[float, float]] = {}
    for name, local in rooms.items():
        pitch[name] = max(ROOM_PITCH, *(label_width(room_label(names[room])) + LABEL_PADDING for room in local))
        columns = max(x for x, _ in local.values()) + 1
        rows = max(y for _, y in local.values()) + 1
        size[name] = (columns * pitch[name], rows * ROOM_PITCH)
    return pitch, size


def _column_and_row_centres(
    names: dict[str, str], cell: dict[str, Cell], block: dict[str, Cell], size: dict[str, tuple[float, float]]
) -> tuple[dict[int, float], dict[int, float]]:
    """Size each lattice column and row to its widest content, and return their centres."""
    widths: dict[int, float] = {}
    heights: dict[int, float] = {}
    for place, (x, y) in cell.items():
        widths[x] = max(widths.get(x, 0.0), PLACE_PITCH, label_width(names[place]) + LABEL_PADDING)
        heights[y] = max(heights.get(y, 0.0), PLACE_PITCH)
    for name, (x, y) in block.items():
        widths[x] = max(widths.get(x, 0.0), size[name][0] + BOX_PADDING)
        heights[y] = max(heights.get(y, 0.0), size[name][1] + BOX_PADDING)
    return _offsets(widths), _offsets(heights)


def _to_pixels(
    names: dict[str, str], cell: dict[str, Cell], block: dict[str, Cell], rooms: dict[str, dict[str, Cell]]
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Turn lattice cells into pixels, each column and row sized to its contents."""
    pitch, size = _building_sizes(names, rooms)
    column_x, row_y = _column_and_row_centres(names, cell, block, size)
    boxes = {
        name: [
            column_x[block[name][0]] - size[name][0] / 2,
            row_y[block[name][1]] - size[name][1] / 2,
            column_x[block[name][0]] + size[name][0] / 2,
            row_y[block[name][1]] + size[name][1] / 2,
        ]
        for name in rooms
    }
    positions = {place: [column_x[x], row_y[y]] for place, (x, y) in cell.items()}
    positions.update(
        {
            room: [boxes[name][0] + (x + 0.5) * pitch[name], boxes[name][1] + (y + 0.5) * ROOM_PITCH]
            for name, local in rooms.items()
            for room, (x, y) in local.items()
        }
    )
    return positions, boxes


def _is_outdoor(terrain: str | None) -> bool:
    """Return whether a terrain is outdoors: every terrain the engine knows but `indoor`."""
    return terrain is not None and terrain != "indoor"


def page_data(graph: dict[str, Any], result: Layout, terrains: dict[str, str | None]) -> dict[str, Any]:
    """Return what the page and the SVG writer draw: places, corridors, buildings and the report.

    Each node's `building` is the building it is a room of, or the one it
    opens for any of that building's entrances; `within` is the building whose box draws it,
    None for a place always shown.
    """
    kind: dict[str, str] = {}
    building_of: dict[str, str] = {}
    within: dict[str, str] = {}
    for key, building in result.buildings.items():  # parents first, so a nested entrance keeps its parent's box
        for room in building["rooms"]:
            if room != building["entrance"] or building["parent"] is None:
                kind[room], building_of[room], within[room] = "room", key, key
        for entrance in building["entrances"]:
            kind[entrance], building_of[entrance] = "entrance", key
        if building["parent"] is None:
            within.pop(building["entrance"], None)
    nodes = [
        {
            "id": node["id"],
            "name": node["name"],
            "label": room_label(node["name"]) if node["id"] in building_of else node["name"],
            "kind": kind.get(node["id"], "place"),
            "building": building_of.get(node["id"]),
            "within": within.get(node["id"]),
            "outdoor": _is_outdoor(terrains.get(node["id"])),
            "x": round(result.positions[node["id"]][0], 1),
            "y": round(result.positions[node["id"]][1], 1),
        }
        for node in graph["nodes"]
    ]
    links = [{key: link[key] for key in ("source", "target", "label", "position", "gated", "both")} for link in graph["links"]]
    buildings = {
        key: {
            "name": b["name"],
            "entrance": b["entrance"],
            "entrances": b["entrances"],
            "parent": b["parent"],
            "size": b["size"],
            "box": [round(v, 1) for v in b["box"]],
        }
        for key, b in result.buildings.items()
    }
    return {"nodes": nodes, "links": links, "buildings": buildings, "report": result.report}


class _Visibility:
    """Which places and boxes show with a given set of buildings open, and where a hidden place is drawn."""

    def __init__(self, data: dict[str, Any], opened: set[str]) -> None:
        self.nodes = {node["id"]: node for node in data["nodes"]}
        self.buildings = data["buildings"]
        self.opened = opened

    def box_shown(self, key: str) -> bool:
        """Return whether a building's box shows: it is open and its entrance shows."""
        return key in self.opened and not self.hidden(self.nodes[self.buildings[key]["entrance"]])

    def hidden(self, node: dict[str, Any]) -> bool:
        """Return whether a place is inside a box that does not show."""
        return node["within"] is not None and not self.box_shown(node["within"])

    def at(self, node: dict[str, Any]) -> tuple[float, float]:
        """Return where a place is drawn: its own position, or the nearest shown entrance of a building holding it."""
        while self.hidden(node):
            node = self.nodes[self.buildings[node["within"]]["entrance"]]
        return node["x"], node["y"]


def _svg_boxes(data: dict[str, Any], seen: _Visibility) -> list[str]:
    """Return the box and name of every building whose box shows."""
    out = []
    for key, building in data["buildings"].items():
        if not seen.box_shown(key):
            continue
        x0, y0, x1, y1 = building["box"]
        out.append(
            f'<rect x="{x0}" y="{y0}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" rx="6" fill="#efeaf8" stroke="#b6a7e8"/>'
            f'<text x="{x0 + 4}" y="{y0 - 5}" fill="#7a6ea8">{escape(building["name"])}</text>'
        )
    return out


def _svg_lines(data: dict[str, Any], end: dict[str, tuple[float, float]]) -> list[str]:
    """Return one line per corridor between two drawn ends, dashed when gated or between levels."""
    out = []
    drawn: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for link in data["links"]:
        a, b = end[link["source"]], end[link["target"]]
        if a == b or (a, b) in drawn:
            continue
        drawn.add((a, b))
        dashed = ' stroke-dasharray="5 4"' if link["gated"] or link["position"] in ("up", "down") else ""
        out.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="#8a8a94"{dashed}/>')
    return out


def _svg_place(data: dict[str, Any], node: dict[str, Any], opened: set[str]) -> str:
    """Return one place's dot and label; a closed building's entrance is labelled with its name and size."""
    colour = "#7a6ea8" if node["building"] else "#3f6fb5" if node["outdoor"] else "#8a6f3f"
    text = node["label"]
    if node["kind"] == "entrance" and node["building"] not in opened:
        building = data["buildings"][node["building"]]
        text = f'{building["name"]} ({building["size"]})'
    return (
        f'<g id="{escape(node["id"], quote=True)}"><circle cx="{node["x"]}" cy="{node["y"]}" r="6" fill="{colour}"/>'
        f'<text x="{node["x"]}" y="{node["y"] + 17}" text-anchor="middle" fill="#1b1b1f">{escape(text)}</text></g>'
    )


def build_svg(data: dict[str, Any], *, expanded: bool = False, open_buildings: set[str] | None = None) -> str:
    """Return a static SVG of the map.

    Args:
        data: `page_data()`'s answer.
        expanded: Draw every building open.
        open_buildings: Building keys to draw open when not `expanded`;
            a nested building shows only when its parent is open too.

    Returns:
        The SVG document. A closed building's rooms are drawn at its
        entrance, so its outside doors still show.
    """
    opened = set(data["buildings"]) if expanded else set(open_buildings or ())
    seen = _Visibility(data, opened)
    shown = [node for node in seen.nodes.values() if not seen.hidden(node)]
    end = {place: seen.at(node) for place, node in seen.nodes.items()}
    x0, y0 = min(n["x"] for n in shown) - 90, min(n["y"] for n in shown) - 50
    x1, y1 = max(n["x"] for n in shown) + 90, max(n["y"] for n in shown) + 50
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {x1 - x0:.0f} {y1 - y0:.0f}" '
            'font-family="system-ui,sans-serif" font-size="11">',
            f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{x1 - x0:.0f}" height="{y1 - y0:.0f}" fill="#fdfdfb"/>',
            *_svg_boxes(data, seen),
            *_svg_lines(data, end),
            *(_svg_place(data, node, opened) for node in shown),
            "</svg>",
        ]
    )


PAGE = (
    PAGE_HEAD
    + """  :root {{ --ink:#e9e9ec; --paper:#15151a; --edge:#32323a; --line:#6f6f7a;
           --place:#7aa6e8; --indoor:#c9a46a; --room:#b6a7e8; --box:rgba(182,167,232,.10); }}
  :root[data-theme="light"] {{ --ink:#1b1b1f; --paper:#fdfdfb; --edge:#d9d9d3; --line:#8a8a94;
    --place:#3f6fb5; --indoor:#8a6f3f; --room:#7a6ea8; --box:#efeaf8; }}
  html,body {{ margin:0; height:100%; }}
  body {{ background:var(--paper); color:var(--ink); display:flex; flex-direction:column;
          font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  header {{ padding:9px 14px; border-bottom:1px solid var(--edge);
            display:flex; gap:12px; align-items:center; flex-wrap:wrap; }}
  h1 {{ font-size:14px; font-weight:600; margin:0; }}
  button {{ font:inherit; color:inherit; background:transparent; border:1px solid var(--edge);
            border-radius:6px; padding:3px 9px; cursor:pointer; }}
  button:hover {{ border-color:currentColor; }}
  .hint {{ opacity:.6; }}
  details {{ max-width:100%; }}
  #canvas {{ flex:1; cursor:grab; touch-action:none; }}
  text {{ font-size:11px; paint-order:stroke; stroke:var(--paper); stroke-width:3px;
          stroke-linejoin:round; fill:var(--ink); pointer-events:none; }}
  .entrance text, .box-title {{ font-weight:600; }}
  .box-frame, .box-title-hit {{ cursor:pointer; }}
  .glyph {{ font-size:13px; font-weight:700; stroke:none; fill:var(--paper); }}
"""
    + PAGE_HEADER_START
    + """  <button id="all" type="button">Open all buildings</button>
  <button id="fit" type="button">Fit</button>
  <button id="pins" type="button">Copy moved pins</button>
  <button id="svgout" type="button">Download SVG</button>
  <button id="theme" type="button">Light / dark</button>
  <span class="hint">click a building's square or name to open it, its box or title to close it; a building inside another opens the same way &middot; drag a place to move it &middot; scroll to zoom</span>
  <details id="report"><summary></summary><ul id="report-list"></ul></details>
</header>
<svg id="canvas"></svg>
<script type="module">
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";
const DATA = {data};
const byId = new Map(DATA.nodes.map(n => [n.id, n]));
const open = new Set();
const moved = {{}};

const report = DATA.report;
document.querySelector("#report summary").textContent =
  report.length ? `Layout report: ${{report.length}} item(s) not drawn true to the map` : "Every place drawn true to its bearings";
const list = document.getElementById("report-list");
for (const item of report) {{
  const li = document.createElement("li");
  li.textContent = `${{item.place}}: ${{item.detail}}`;
  list.appendChild(li);
}}

const svg = d3.select("#canvas");
const root = svg.append("g");
const boxLayer = root.append("g"), lineLayer = root.append("g"), nodeLayer = root.append("g");
const B = DATA.buildings;
// A box shows when its building is open and its entrance shows; a nested entrance shows only inside its open parent.
const boxShown = key => open.has(key) && !hidden(byId.get(B[key].entrance));
const hidden = n => n.within !== null && !boxShown(n.within);
// A hidden place is drawn at the nearest shown entrance holding it, so its outside doors still draw.
const at = n => hidden(n) ? at(byId.get(B[n.within].entrance)) : n;
const closedLabel = n => `${{B[n.building].name}} (${{B[n.building].size}})`;
const labelOf = n => n.kind === "entrance" && !open.has(n.building) ? closedLabel(n) : n.label;

const boxes = boxLayer.selectAll("g").data(Object.entries(B)).join("g");
boxes.append("rect").attr("class", "box-frame").attr("rx", 6).attr("fill", "var(--box)").attr("stroke", "var(--room)")
  .attr("x", d => d[1].box[0]).attr("y", d => d[1].box[1])
  .attr("width", d => d[1].box[2] - d[1].box[0]).attr("height", d => d[1].box[3] - d[1].box[1]);
boxes.append("rect").attr("class", "box-title-hit").attr("fill", "transparent")
  .attr("x", d => d[1].box[0] - 6).attr("y", d => d[1].box[1] - 26)
  .attr("width", d => Math.max(80, 7 * d[1].name.length + 30)).attr("height", 28);
boxes.append("text").attr("class", "box-title").attr("x", d => d[1].box[0] + 4).attr("y", d => d[1].box[1] - 7)
  .text(d => `${{d[1].name}} −`);
boxes.append("title").text(d => `${{d[1].name}}: click to close`);
boxes.on("click", (event, d) => {{ open.delete(d[0]); draw(); }});

const lines = lineLayer.selectAll("line").data(DATA.links).join("line").attr("stroke", "var(--line)")
  .attr("stroke-dasharray", d => d.gated || d.position === "up" || d.position === "down" ? "5 4" : null);
const places = nodeLayer.selectAll("g").data(DATA.nodes).join("g").style("cursor", "pointer")
  .attr("class", d => d.kind === "entrance" ? "entrance" : null);
// The marker keeps a readable size on screen however far out the map is zoomed; see scaleMarkers().
const markers = places.append("g");
// Each place's hit area covers its marker and its longest label, so a click on either lands.
const hitWidth = d => Math.max(56, 6.6 * Math.max(d.label.length, d.kind === "entrance" ? closedLabel(d).length : 0) + 24);
markers.append("rect").attr("class", "hit").attr("fill", "transparent").attr("rx", 8)
  .attr("x", d => -hitWidth(d) / 2).attr("y", -20).attr("width", hitWidth).attr("height", 50);
markers.filter(d => d.kind !== "entrance").append("circle").attr("r", 7)
  .attr("fill", d => d.building ? "var(--room)" : d.outdoor ? "var(--place)" : "var(--indoor)");
const doors = markers.filter(d => d.kind === "entrance");
doors.append("rect").attr("x", -11).attr("y", -11).attr("width", 22).attr("height", 22).attr("rx", 4)
  .attr("fill", "var(--room)").attr("stroke", "var(--ink)");
const glyphs = doors.append("text").attr("class", "glyph").attr("text-anchor", "middle").attr("y", 5);
const labels = places.append("text").attr("text-anchor", "middle").attr("y", 24);
places.append("title").text(d => d.kind === "entrance" ? `${{B[d.building].name}}: click to open or close` : d.name);
function scaleMarkers(k) {{ markers.attr("transform", `scale(${{Math.max(1, 1 / k)}})`); }}

function draw() {{
  boxes.style("display", d => boxShown(d[0]) ? null : "none");
  places.style("display", d => hidden(d) ? "none" : null)
    .attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  labels.text(labelOf);
  glyphs.text(d => open.has(d.building) ? "−" : "+");
  lines.attr("x1", d => at(byId.get(d.source)).x).attr("y1", d => at(byId.get(d.source)).y)
    .attr("x2", d => at(byId.get(d.target)).x).attr("y2", d => at(byId.get(d.target)).y)
    .style("display", d => at(byId.get(d.source)) === at(byId.get(d.target)) ? "none" : null);
}}

places.on("click", (event, d) => {{
  if (event.defaultPrevented || d.kind !== "entrance") return;
  open.has(d.building) ? open.delete(d.building) : open.add(d.building);
  draw();
}});
places.call(d3.drag().on("drag", (event, d) => {{
  d.x = event.x; d.y = event.y;
  moved[d.id] = [Math.round(event.x), Math.round(event.y)];
  draw();
}}));

const zoom = d3.zoom().scaleExtent([0.08, 6]).on("zoom", event => {{
  root.attr("transform", event.transform);
  scaleMarkers(event.transform.k);
}});
svg.call(zoom).on("dblclick.zoom", null);
function fit() {{
  const box = root.node().getBBox(), width = svg.node().clientWidth, height = svg.node().clientHeight;
  const scale = Math.min(2, 0.92 * Math.min(width / box.width, height / box.height));
  svg.call(zoom.transform, d3.zoomIdentity
    .translate(width / 2 - scale * (box.x + box.width / 2), height / 2 - scale * (box.y + box.height / 2)).scale(scale));
}}
document.getElementById("fit").onclick = fit;
document.getElementById("all").onclick = () => {{
  const openAll = open.size < Object.keys(DATA.buildings).length;
  for (const name of Object.keys(DATA.buildings)) openAll ? open.add(name) : open.delete(name);
  document.getElementById("all").textContent = openAll ? "Close all buildings" : "Open all buildings";
  draw();
}};
document.getElementById("pins").onclick = () => navigator.clipboard.writeText(JSON.stringify(moved, null, 1));
document.getElementById("svgout").onclick = () => {{
  const clone = svg.node().cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const link = document.createElement("a");
  link.download = "map.svg";
  link.href = URL.createObjectURL(new Blob([clone.outerHTML], {{type: "image/svg+xml"}}));
  link.click();
}};
document.getElementById("theme").onclick = () => {{
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === "light" ? "dark" : "light";
}};
draw();
fit();
</script>
</body>
</html>
"""
)


def build_page(title: str, data: dict[str, Any]) -> str:
    """Return a self-contained page drawing the laid-out map."""
    return PAGE.format(title=escape(title), data=json.dumps(data, indent=None))
