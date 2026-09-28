"""`location_graph.buildings()`: a map grouped into buildings by its entrances."""

from __future__ import annotations

import json
from typing import Any
from unittest import TestCase

from ink_engine.engine_config_schemas import SystemConfigValidationError
from ink_engine.engine_plugins.location_graph import (
    add_missing_return_exits,
    buildings,
    validate_location_graph,
)


def _town() -> dict[str, Any]:
    """Return an invented town: a road, an apartment block with two flats, a bakery, and a cellar with no entrance.

    road -> block_lobby (entrance) -> lift -> floor_2 -> flat_201 (entrance) -> flat_201_kitchen, flat_201_bedroom
                                                     -> flat_202 (entrance) -> flat_202_bathroom
    road -> bakery (entrance) -> bakery_kitchen
    road -> cellar (indoor, no entrance) -> cellar_store
    """
    terrain = {"road": "city", "square": "city"}
    entrances = {"block_lobby", "flat_201", "flat_202", "bakery"}
    links = [
        ("road", "square", "n"),
        ("road", "block_lobby", "in"),
        ("block_lobby", "lift", "e"),
        ("lift", "floor_2", "up"),
        ("floor_2", "flat_201", "n"),
        ("floor_2", "flat_202", "s"),
        ("flat_201", "flat_201_kitchen", "e"),
        ("flat_201_kitchen", "flat_201_bedroom", "n"),
        ("flat_202", "flat_202_bathroom", "e"),
        ("square", "bakery", "in"),
        ("bakery", "bakery_kitchen", "n"),
        ("square", "cellar", "down"),
        ("cellar", "cellar_store", "e"),
    ]
    places = dict.fromkeys(place for link in links for place in link[:2])
    locations = {
        place: {
            "known_by_default": True,
            "details": {"terrain": terrain.get(place, "indoor"), **({"entrance": True} if place in entrances else {})},
            "exits": [{"to": destination, "position": position} for origin, destination, position in links if origin == place],
        }
        for place in places
    }
    return add_missing_return_exits({"locations": locations})


class BuildingsTests(TestCase):
    """The invented town's building tree."""

    @classmethod
    def setUpClass(cls):
        cls.config = _town()
        validate_location_graph(cls.config)
        cls.tree = buildings(cls.config)

    def test_the_block_holds_its_lift_and_floor_and_nests_both_flats(self):
        """Road -> lobby -> lift -> floor -> two flats: the flats are buildings inside the block."""
        block = self.tree["buildings"][0]
        self.assertEqual(block["entrance"], "block_lobby")
        self.assertEqual(block["rooms"], ["lift", "floor_2"])
        self.assertEqual(
            block["buildings"],
            [
                {"entrance": "flat_201", "entrances": ["flat_201"], "rooms": ["flat_201_kitchen", "flat_201_bedroom"], "buildings": []},
                {"entrance": "flat_202", "entrances": ["flat_202"], "rooms": ["flat_202_bathroom"], "buildings": []},
            ],
        )

    def test_a_building_with_no_nested_entrance(self):
        """The bakery holds its kitchen and nothing else."""
        self.assertEqual(self.tree["buildings"][1], {"entrance": "bakery", "entrances": ["bakery"], "rooms": ["bakery_kitchen"], "buildings": []})

    def test_only_the_outermost_buildings_are_at_the_top(self):
        """The flats appear only inside the block."""
        self.assertEqual([building["entrance"] for building in self.tree["buildings"]], ["block_lobby", "bakery"])

    def test_an_indoor_place_no_entrance_leads_to_is_reported(self):
        """The cellar and its store stay top-level and are listed as having no entrance."""
        self.assertEqual(self.tree["top_level"], ["road", "square", "cellar", "cellar_store"])
        self.assertEqual(self.tree["no_entrance"], ["cellar", "cellar_store"])

    def test_the_tree_is_json_safe(self):
        """The tree survives a JSON round trip unchanged."""
        self.assertEqual(json.loads(json.dumps(self.tree)), self.tree)

    def test_a_map_with_no_entrance_has_no_buildings(self):
        """Without entrances every place is top-level and every indoor one is reported."""
        config = _town()
        for location in config["locations"].values():
            location["details"].pop("entrance", None)
        tree = buildings(config)
        self.assertEqual(tree["buildings"], [])
        self.assertEqual(len(tree["top_level"]), len(config["locations"]))

    def test_an_entrance_no_road_reaches_is_still_a_building(self):
        """An interior cut off from outside is grouped from its first entrance."""
        config = _town()
        for origin, destination in (("road", "block_lobby"), ("block_lobby", "road")):
            location = config["locations"][origin]
            location["exits"] = [exit_ for exit_ in location["exits"] if exit_["to"] != destination]
        tree = buildings(config)
        self.assertEqual([building["entrance"] for building in tree["buildings"]], ["block_lobby", "bakery"])
        self.assertEqual(len(tree["buildings"][0]["buildings"]), 2)


def _abbey() -> dict[str, Any]:
    """Return an invented abbey, and an inn whose room has a shortcut to the lane.

    lane -> nave (entrance) -> cloister (outdoor, inside the abbey) -> cell_1, cell_2
    lane -> gatehouse (a second entrance of the abbey) -> cloister
    lane -> inn (entrance) -> inn_hall -> inn_room (entrance) -> lane, through inn_hall
    """

    def place(terrain: str, **details: Any) -> dict[str, Any]:
        return {"known_by_default": True, "details": {"terrain": terrain, **details}, "exits": []}

    locations = {
        "lane": place("city"),
        "nave": place("indoor", entrance=True),
        "cloister": place("outdoor", building="nave"),
        "cell_1": place("indoor"),
        "cell_2": place("indoor"),
        "gatehouse": place("indoor", entrance=True, building="nave"),
        "inn": place("indoor", entrance=True),
        "inn_hall": place("indoor"),
        "inn_room": place("indoor", entrance=True),
    }
    for origin, destination in (
        ("lane", "nave"),
        ("nave", "cloister"),
        ("cloister", "cell_1"),
        ("cloister", "cell_2"),
        ("lane", "gatehouse"),
        ("gatehouse", "cloister"),
        ("lane", "inn"),
        ("inn", "inn_hall"),
        ("inn_hall", "inn_room"),
    ):
        locations[origin]["exits"].append({"to": destination})
        locations[destination]["exits"].append({"to": origin})
    locations["inn_room"]["exits"].append({"to": "lane", "through": "inn_hall"})
    return {"locations": locations}


class MultipleEntranceTests(TestCase):
    """A building with two entrances and a courtyard inside its walls, and a shortcut exit through a building."""

    @classmethod
    def setUpClass(cls):
        cls.config = _abbey()
        validate_location_graph(cls.config)
        cls.tree = buildings(cls.config)

    def test_both_entrances_open_one_building(self):
        """The gatehouse declares the nave as its building: the abbey has two entrances, the main one first."""
        abbey = self.tree["buildings"][0]
        self.assertEqual((abbey["entrance"], abbey["entrances"]), ("nave", ["nave", "gatehouse"]))

    def test_an_outdoor_place_declaring_the_building_is_inside_it(self):
        """The cloister is outdoor but declares the abbey, so it and the cells off it are the abbey's."""
        self.assertEqual(self.tree["buildings"][0]["rooms"], ["cloister", "cell_1", "cell_2"])
        self.assertEqual(self.tree["no_entrance"], [])

    def test_a_place_declaring_the_building_belongs_to_it_even_when_no_entrance_reaches_it(self):
        """A store reached only from the lane is the abbey's because it declares the abbey."""
        config = _abbey()
        config["locations"]["store"] = {"known_by_default": True, "details": {"terrain": "indoor", "building": "nave"}, "exits": [{"to": "lane"}]}
        config["locations"]["lane"]["exits"].append({"to": "store"})
        tree = buildings(config)
        self.assertIn("store", tree["buildings"][0]["rooms"])
        self.assertNotIn("store", tree["top_level"])

    def test_an_exit_through_a_building_does_not_make_a_room_outermost(self):
        """The inn room's shortcut to the lane passes through the hall, so the room is nested in the inn."""
        inn = self.tree["buildings"][1]
        self.assertEqual((inn["entrance"], [child["entrance"] for child in inn["buildings"]]), ("inn", ["inn_room"]))

    def test_without_through_the_shortcut_makes_the_room_outermost(self):
        """Control: the same exit without `through` puts the inn room beside the lane."""
        config = _abbey()
        del config["locations"]["inn_room"]["exits"][-1]["through"]
        self.assertIn("inn_room", [building["entrance"] for building in buildings(config)["buildings"]])

    def test_building_must_name_a_main_entrance(self):
        """`building` must name a declared entrance that is not itself another building's entrance."""
        for location_id, value in (("cloister", "nowhere"), ("cloister", "cell_1"), ("cell_1", "gatehouse")):
            config = _abbey()
            config["locations"][location_id]["details"]["building"] = value
            with self.subTest(value=value), self.assertRaises(SystemConfigValidationError):
                validate_location_graph(config)

    def test_through_must_name_a_declared_location(self):
        """An exit's `through` is checked like its `to`."""
        config = _abbey()
        config["locations"]["inn_room"]["exits"][-1]["through"] = "nowhere"
        with self.assertRaises(SystemConfigValidationError):
            validate_location_graph(config)
