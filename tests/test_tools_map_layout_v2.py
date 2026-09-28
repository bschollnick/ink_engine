"""The version 2 map layout (tools/map_layout_v2.py): positions computed from bearings."""

from __future__ import annotations

import math
import re
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from ink_engine.engine_plugins.location_graph import buildings
from tests.map_lab import BUILDINGS, RING_ROAD, build_block_map, build_map
from tools import map_layout_v2
from tools.map_layout import build_graph
from tools.map_to_mermaid import main

EXAMPLE_GAME = Path(__file__).resolve().parents[1] / "examples" / "cloak_of_darkness"


def _graph(config: dict[str, Any]) -> dict[str, Any]:
    """Build the graph `map_to_mermaid.py` hands the layout, for the map as declared."""

    def exits_for(location_id: str) -> list[dict[str, Any]]:
        return [{**exit_, "passable": not exit_.get("sealed")} for exit_ in config["locations"][location_id].get("exits", [])]

    return build_graph(config, exits_for, None, connected_only=False)


def _compass_agreement(config: dict[str, Any], positions: dict[str, list[float]]) -> float:
    """Return the share of compass exits drawn within 45 degrees of their bearing."""
    agree = total = 0
    for origin, declaration in config["locations"].items():
        for exit_ in declaration.get("exits", []):
            step = map_layout_v2.STEPS.get(exit_.get("position") or "")
            if step is None:
                continue
            total += 1
            (ox, oy), (dx, dy) = positions[origin], positions[exit_["to"]]
            drawn = math.degrees(math.atan2(dy - oy, dx - ox) - math.atan2(step[1], step[0]))
            agree += abs((drawn + 180) % 360 - 180) <= 45
    return agree / total


class LayoutTests(TestCase):
    """The synthetic town laid out once, as declared."""

    @classmethod
    def setUpClass(cls):
        cls.config = build_map()
        cls.result = map_layout_v2.layout(_graph(cls.config))

    def test_every_place_is_placed(self):
        """Every place in the map gets a position."""
        self.assertEqual(set(self.result.positions), set(self.config["locations"]))

    def test_no_two_places_are_closer_than_a_room_pitch(self):
        """No two places are drawn closer than rooms inside a building are."""
        for (a, pa), (b, pb) in combinations(self.result.positions.items(), 2):
            self.assertGreaterEqual(math.dist(pa, pb), map_layout_v2.ROOM_PITCH - 1, f"{a} and {b}")

    def test_bearings_are_kept(self):
        """At least 95% of compass exits are drawn within 45 degrees of their bearing."""
        self.assertGreaterEqual(_compass_agreement(self.config, self.result.positions), 0.95)

    def test_a_forest_trail_is_placed_by_its_bearings_like_any_road(self):
        """Forest terrain is placed by bearing like any road (version 1 counted only outdoor, city and field)."""
        (x0, y0), (x1, y1) = self.result.positions["trail_1"], self.result.positions["trail_2"]
        self.assertAlmostEqual(x0, x1)
        self.assertLess(y1, y0, "trail_2 is declared north of trail_1")

    def test_every_building_is_found_with_its_rooms(self):
        """Every building is found by its name prefix, with all its rooms."""
        self.assertEqual(
            {name: len(b["rooms"]) for name, b in self.result.buildings.items()},
            {name: size for name, _street, size in BUILDINGS},
        )

    def test_each_room_is_inside_its_own_box_and_no_other_place_is(self):
        """A building's box holds exactly its own rooms."""
        for name, building in self.result.buildings.items():
            x0, y0, x1, y1 = building["box"]
            members = set(building["rooms"])
            for place, (x, y) in self.result.positions.items():
                inside = x0 <= x <= x1 and y0 <= y <= y1
                self.assertEqual(inside, place in members, f"{place} and {name}")

    def test_no_two_buildings_overlap(self):
        """No two building boxes overlap."""
        for (a, ba), (b, bb) in combinations(self.result.buildings.items(), 2):
            ax0, ay0, ax1, ay1 = ba["box"]
            bx0, by0, bx1, by1 = bb["box"]
            self.assertFalse(ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1, f"{a} and {b}")

    def test_the_ring_road_that_does_not_close_is_reported(self):
        """The loop whose bearings cannot all be drawn true appears in the report."""
        reported = " ".join(item["place"] for item in self.result.report)
        self.assertTrue(any(road in reported for road in RING_ROAD), self.result.report)

    def test_a_place_with_no_bearing_is_reported(self):
        """The tunnel, reached only by up and down, is reported as placed by its neighbours."""
        self.assertIn({"kind": "no_bearing", "place": "tunnel"}, [{k: item[k] for k in ("kind", "place")} for item in self.result.report])

    def test_the_layout_is_the_same_every_run(self):
        """Two runs give the same positions."""
        self.assertEqual(map_layout_v2.layout(_graph(self.config)).positions, self.result.positions)


def _town_with_isolated_places(count: int) -> dict[str, Any]:
    """Return the synthetic town plus `count` places with no exits at all."""
    config = build_map()
    for index in range(count):
        config["locations"][f"lone_{index}"] = {
            "known_by_default": True,
            "details": {"name": f"Lone Place {index}", "terrain": "indoor"},
            "exits": [],
        }
    return config


def _aspect(result: map_layout_v2.Layout) -> float:
    """Return the drawn width-to-height ratio of a layout's places."""
    xs = [x for x, _ in result.positions.values()]
    ys = [y for _, y in result.positions.values()]
    return (max(xs) - min(xs)) / (max(ys) - min(ys))


class AspectTests(TestCase):
    """Pieces connected to nothing are packed toward the requested shape, not strung out in one row."""

    @classmethod
    def setUpClass(cls):
        cls.graph = _graph(_town_with_isolated_places(40))
        cls.standard = map_layout_v2.layout(cls.graph)
        cls.ultrawide = map_layout_v2.layout(cls.graph, aspect=21 / 9)

    def test_the_map_lands_near_the_requested_shape(self):
        """Forty isolated places still leave the map within a third of 16:9."""
        self.assertLess(abs(math.log(_aspect(self.standard) / (16 / 9))), math.log(4 / 3))

    def test_a_wider_target_gives_a_wider_map(self):
        """Asking for 21:9 draws a wider map than 16:9."""
        self.assertGreater(_aspect(self.ultrawide), _aspect(self.standard))

    def test_packed_places_do_not_overlap(self):
        """No two places, packed or not, are closer than a room pitch."""
        for (a, pa), (b, pb) in combinations(self.standard.positions.items(), 2):
            self.assertGreaterEqual(math.dist(pa, pb), map_layout_v2.ROOM_PITCH - 1, f"{a} and {b}")


class PinTests(TestCase):
    """An author's pins file."""

    def test_a_pin_overrides_the_computed_position(self):
        """A place named in the pins lands exactly there; the rest are unchanged."""
        config = build_map()
        free = map_layout_v2.layout(_graph(config))
        pinned = map_layout_v2.layout(_graph(config), {"tunnel": [-500, -500]})
        self.assertEqual(pinned.positions["tunnel"], [-500.0, -500.0])
        self.assertEqual(pinned.positions["st_0_0"], free.positions["st_0_0"])

    def test_a_pin_for_an_unknown_place_is_ignored(self):
        """A pin naming no place in the map changes nothing."""
        config = build_map()
        self.assertEqual(map_layout_v2.layout(_graph(config), {"nowhere": [1, 1]}).positions.keys(), set(config["locations"]))


class SvgTests(TestCase):
    """The static SVG."""

    @classmethod
    def setUpClass(cls):
        config = build_map()
        graph = _graph(config)
        result = map_layout_v2.layout(graph)
        terrains = {k: v["details"].get("terrain") for k, v in config["locations"].items()}
        cls.data = map_layout_v2.page_data(graph, result, terrains)

    def test_closed_buildings_show_only_their_entrance_with_a_room_count(self):
        """Closed, a building is its entrance labelled with its room count."""
        svg = map_layout_v2.build_svg(self.data)
        self.assertIn(">Grand Hotel (12)</text>", svg)
        self.assertNotIn('id="b1_5"', svg)

    def test_open_buildings_show_every_room(self):
        """Open, every place is drawn."""
        svg = map_layout_v2.build_svg(self.data, expanded=True)
        self.assertEqual(len(re.findall(r'<g id="', svg)), len(self.data["nodes"]))

    def test_no_two_labels_intersect(self):
        """Labels sit under their place; no two label boxes may cross, open or closed."""
        for expanded in (False, True):
            svg = map_layout_v2.build_svg(self.data, expanded=expanded)
            boxes = []
            for x, y, text in re.findall(r'<text x="([\d.-]+)" y="([\d.-]+)" text-anchor="middle"[^>]*>([^<]*)</text>', svg):
                half = map_layout_v2.label_width(text) / 2
                boxes.append((float(x) - half, float(y) - 10, float(x) + half, float(y) + 2, text))
            for a, b in combinations(boxes, 2):
                crossing = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                self.assertFalse(crossing, f"{a[4]!r} and {b[4]!r} (expanded={expanded})")


class EntranceTests(TestCase):
    """A map that declares entrances is grouped by `location_graph.buildings()`, buildings nested."""

    @classmethod
    def setUpClass(cls):
        config = build_block_map()
        graph = _graph(config)
        cls.result = map_layout_v2.layout(graph, tree=buildings(config))
        terrains = {k: v["details"].get("terrain") for k, v in config["locations"].items()}
        cls.data = map_layout_v2.page_data(graph, cls.result, terrains)

    def test_buildings_come_from_entrances_with_the_flats_nested_in_the_block(self):
        """Each entrance is a building; the flats' parent is the block."""
        self.assertEqual(
            {key: building["parent"] for key, building in self.result.buildings.items()},
            {"lobby": None, "flat_201": "lobby", "flat_202": "lobby", "flat_301": "lobby", "shop": None},
        )

    def test_the_block_box_holds_its_rooms_and_the_flat_entrances(self):
        """The block draws its lift, floors and flat doors; each flat draws only its own rooms."""
        self.assertEqual(self.result.buildings["lobby"]["rooms"], ["lobby", "lift", "floor_2", "floor_3", "flat_201", "flat_202", "flat_301"])
        self.assertEqual(self.result.buildings["flat_201"]["rooms"], ["flat_201_kitchen", "flat_201_bedroom"])

    def test_sizes_count_every_place_inside(self):
        """The block counts itself, its three rooms and three flats of three places each."""
        self.assertEqual(
            {key: b["size"] for key, b in self.result.buildings.items()}, {"lobby": 13, "flat_201": 3, "flat_202": 3, "flat_301": 3, "shop": 3}
        )

    def test_each_place_is_inside_only_its_own_box(self):
        """A box holds exactly the places it draws."""
        for key, building in self.result.buildings.items():
            x0, y0, x1, y1 = building["box"]
            for place, (x, y) in self.result.positions.items():
                self.assertEqual(x0 <= x <= x1 and y0 <= y <= y1, place in building["rooms"], f"{place} and {key}")

    def test_no_two_boxes_overlap(self):
        """No two building boxes overlap, nested ones included."""
        for (a, ba), (b, bb) in combinations(self.result.buildings.items(), 2):
            ax0, ay0, ax1, ay1 = ba["box"]
            bx0, by0, bx1, by1 = bb["box"]
            self.assertFalse(ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1, f"{a} and {b}")

    def test_an_indoor_place_with_no_entrance_is_reported_and_not_grouped(self):
        """The basement stays a loose place and is reported."""
        reported = {item["place"] for item in self.result.report if item["kind"] == "no_entrance"}
        self.assertEqual(reported, {"basement", "basement_boiler"})
        self.assertFalse(any("basement" in building["rooms"] for building in self.result.buildings.values()))

    def test_a_flat_entrance_is_drawn_within_the_block(self):
        """Page data: a flat's door sits in the block's box and opens the flat."""
        node = next(node for node in self.data["nodes"] if node["id"] == "flat_201")
        self.assertEqual((node["kind"], node["building"], node["within"]), ("entrance", "flat_201", "lobby"))

    def test_closed_the_block_is_one_labelled_marker(self):
        """Closed, the block shows as its entrance with its name and size, and no flat shows."""
        svg = map_layout_v2.build_svg(self.data)
        self.assertIn(">Apartment Block (13)</text>", svg)
        self.assertNotIn('id="flat_201"', svg)
        self.assertNotIn('id="lift"', svg)

    def test_opening_the_block_shows_each_flat_closed(self):
        """Open, the block shows its rooms and each flat as a closed marker."""
        svg = map_layout_v2.build_svg(self.data, open_buildings={"lobby"})
        self.assertIn('id="lift"', svg)
        self.assertIn(">Flat 201 (3)</text>", svg)
        self.assertNotIn('id="flat_201_kitchen"', svg)

    def test_a_flat_opens_only_inside_an_open_block(self):
        """A flat's rooms show when the flat and the block are both open."""
        self.assertNotIn('id="flat_201_kitchen"', map_layout_v2.build_svg(self.data, open_buildings={"flat_201"}))
        self.assertIn('id="flat_201_kitchen"', map_layout_v2.build_svg(self.data, open_buildings={"lobby", "flat_201"}))

    def test_the_page_carries_the_tree(self):
        """The page embeds each building's parent and each place's box."""
        page = map_layout_v2.build_page("block", self.data)
        self.assertIn('"parent": "lobby"', page)
        self.assertIn('"within": "lobby"', page)


def _block_with_studio_and_back_door() -> dict[str, Any]:
    """Return the block map plus a one-room studio flat off the third floor and a back door into the shop."""
    config = build_block_map()
    locations = config["locations"]
    locations["studio"] = {
        "known_by_default": True,
        "details": {"name": "Apartment Block - Studio", "terrain": "indoor", "entrance": True},
        "exits": [],
    }
    locations["shop_back"] = {
        "known_by_default": True,
        "details": {"name": "Corner Shop - Back Door", "terrain": "indoor", "entrance": True, "building": "shop"},
        "exits": [],
    }
    for origin, destination in (("floor_3", "studio"), ("street_1", "shop_back"), ("shop_back", "shop_store")):
        locations[origin]["exits"].append({"to": destination})
        locations[destination]["exits"].append({"to": origin})
    return config


class SingleRoomAndSecondEntranceTests(TestCase):
    """A building that is only its entrance, and a building with two entrances."""

    @classmethod
    def setUpClass(cls):
        config = _block_with_studio_and_back_door()
        graph = _graph(config)
        cls.result = map_layout_v2.layout(graph, tree=buildings(config))
        terrains = {k: v["details"].get("terrain") for k, v in config["locations"].items()}
        cls.data = map_layout_v2.page_data(graph, cls.result, terrains)

    def test_a_one_room_flat_is_a_building_framed_around_its_entrance(self):
        """The studio is a building of one place whose box surrounds its entrance inside the block's box."""
        studio, block = self.result.buildings["studio"], self.result.buildings["lobby"]
        self.assertEqual((studio["parent"], studio["size"], studio["rooms"]), ("lobby", 1, ["studio"]))
        x, y = self.result.positions["studio"]
        self.assertTrue(studio["box"][0] < x < studio["box"][2] and studio["box"][1] < y < studio["box"][3])
        self.assertIn("studio", block["rooms"])

    def test_the_one_room_flat_is_a_clickable_marker_that_opens_to_itself(self):
        """Inside the open block the studio shows closed with its size; opened, it shows its own name."""
        closed = map_layout_v2.build_svg(self.data, open_buildings={"lobby"})
        self.assertIn(">Studio (1)</text>", closed)
        opened = map_layout_v2.build_svg(self.data, open_buildings={"lobby", "studio"})
        self.assertIn('fill="#7a6ea8">Studio</text>', opened, "the studio's frame and title")
        self.assertIn('text-anchor="middle" fill="#1b1b1f">Studio</text>', opened, "the studio itself")

    def test_both_shop_doors_belong_to_one_building(self):
        """The back door is a second entrance of the shop, drawn in its box and opening it."""
        shop = self.result.buildings["shop"]
        self.assertEqual(shop["entrances"], ["shop", "shop_back"])
        self.assertIn("shop_back", shop["rooms"])
        node = next(node for node in self.data["nodes"] if node["id"] == "shop_back")
        self.assertEqual((node["kind"], node["building"], node["within"]), ("entrance", "shop", "shop"))
        self.assertEqual(shop["size"], 4)

    def test_a_closed_shop_draws_its_back_door_links_at_its_main_entrance(self):
        """Closed, the shop is one marker; the back door is hidden."""
        svg = map_layout_v2.build_svg(self.data)
        self.assertIn(">Corner Shop (4)</text>", svg)
        self.assertNotIn('id="shop_back"', svg)


class CommandLineTests(TestCase):
    """The --v2html and --v2svg flags."""

    def test_the_page_and_svg_are_written(self):
        """The command line writes the page and the SVG for the example game."""
        with TemporaryDirectory() as folder:
            page, svg = Path(folder) / "map.html", Path(folder) / "map.svg"
            self.assertEqual(main([str(EXAMPLE_GAME), "--v2html", str(page), "--v2svg", str(svg)]), 0)
            self.assertIn("Foyer of the Opera House", page.read_text(encoding="utf-8"))
            self.assertTrue(svg.read_text(encoding="utf-8").startswith("<svg"))
