"""The map diagram tool (tools/map_to_mermaid.py).

Covers the two things a reader of a diagram relies on: that a gate
decides the arrow style, and that a session's diagram shows only what
that session has found.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from tempfile import TemporaryDirectory
from typing import Any, ClassVar
from unittest import TestCase as SimpleTestCase

from tools.map_to_mermaid import (
    MapDiagramError,
    build_diagram,
    node_identifier,
    node_identifiers,
    read_session,
)

GATED_MAP = {
    "locations": {
        "hall": {
            "known_by_default": True,
            "details": {"name": "Hall"},
            "exits": [
                {"to": "yard", "position": "s", "label": "the yard"},
                {"to": "crypt", "position": "down", "label": "the crypt stair", "unlocked_by": "crypt_open"},
                {"to": "vault", "position": "e", "label": "the vault", "sealed": True},
            ],
        },
        "yard": {"known_by_default": True, "details": {"name": "Yard"}, "exits": [{"to": "hall", "position": "n", "label": "Hall"}]},
        "crypt": {"known_by_default": True, "details": {"name": "Old Crypt"}},
        "vault": {"known_by_default": True, "details": {"name": "Vault"}},
    }
}


class DiagramTests(SimpleTestCase):
    """The map as declared, with no session."""

    def test_every_location_becomes_a_node(self):
        diagram = build_diagram(GATED_MAP)
        for location_id in GATED_MAP["locations"]:
            self.assertIn(f'{node_identifier(location_id)}["', diagram)

    def test_an_open_exit_is_a_solid_arrow_carrying_position_and_label(self):
        # The yard declares the way back, so the corridor folds into one
        # bidirectional arrow drawn in the direction the chart flows.
        self.assertIn("loc_hall <-->|s: the yard| loc_yard", build_diagram(GATED_MAP))

    def test_a_one_way_exit_stays_a_single_arrow(self):
        self.assertIn("loc_hall -->|e: the vault| loc_vault", build_diagram(GATED_MAP))

    def test_a_reciprocal_pair_is_drawn_once(self):
        diagram = build_diagram(GATED_MAP)
        self.assertEqual(diagram.count("loc_yard"), 2, "one node plus one arrow")

    def test_a_north_south_corridor_is_drawn_southward_so_north_lies_above(self):
        north_first = {
            "locations": {
                "cellar": {
                    "known_by_default": True,
                    "details": {"name": "Cellar"},
                    "exits": [{"to": "hall", "position": "n", "label": "up to the hall"}],
                },
                "hall": {
                    "known_by_default": True,
                    "details": {"name": "Hall"},
                    "exits": [{"to": "cellar", "position": "s", "label": "down to the cellar"}],
                },
            }
        }
        # Declared cellar-first, but drawn hall -> cellar, because the
        # chart flows downward and the hall is to the north.
        self.assertIn("loc_hall <-->|s: down to the cellar| loc_cellar", build_diagram(north_first))

    def test_the_graph_direction_is_declared(self):
        self.assertTrue(build_diagram(GATED_MAP).startswith("flowchart TD"))

    def test_a_sealed_exit_is_greyed_rather_than_given_its_own_arrow(self):
        """A gate is a line style, so arrowheads keep saying which way it runs."""
        diagram = build_diagram(GATED_MAP)
        self.assertIn("loc_hall -->|e: the vault| loc_vault", diagram)
        self.assertIn("linkStyle 1,2 ", diagram)

    def test_an_unopened_gate_is_greyed(self):
        diagram = build_diagram(GATED_MAP)
        self.assertIn("loc_hall -->|down: the crypt stair| loc_crypt", diagram)
        self.assertIn("linkStyle 1,2 ", diagram)

    def test_a_blocked_two_way_corridor_keeps_both_arrowheads(self):
        """A gate is a line style, so it never costs the corridor an arrowhead."""
        blocked_both_ways = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "b", "position": "s", "label": "down", "unlocked_by": "shut"}]},
                "b": {"known_by_default": True, "exits": [{"to": "a", "position": "n", "label": "up", "unlocked_by": "shut"}]},
            }
        }
        diagram = build_diagram(blocked_both_ways)
        self.assertIn("<-->", diagram)
        self.assertIn("linkStyle 0 ", diagram)

    def test_blocked_links_are_styled_by_their_link_number(self):
        # Mermaid numbers links from zero in declaration order: the crypt
        # stair is link 1 and the vault link 2.
        self.assertIn("linkStyle 1,2 ", build_diagram(GATED_MAP))

    def test_a_map_with_no_blocked_exits_declares_no_link_style(self):
        open_map = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "b", "position": "n"}]},
                "b": {"known_by_default": True},
            }
        }
        self.assertNotIn("linkStyle", build_diagram(open_map))


class SessionDiagramTests(SimpleTestCase):
    """The map as one session has found it."""

    SESSION: ClassVar[dict[str, Any]] = {
        "known": ["hall", "yard", "crypt"],
        "visits": {"hall": 1, "yard": 2},
        "place_records": {"crypt": {"attributes": {"crypt_open": True}}},
    }

    def test_an_undiscovered_location_is_left_out(self):
        diagram = build_diagram(GATED_MAP, self.SESSION)
        self.assertNotIn("loc_vault", diagram)

    def test_an_exit_to_an_undiscovered_location_is_left_out(self):
        self.assertNotIn("the vault", build_diagram(GATED_MAP, self.SESSION))

    def test_an_opened_gate_becomes_a_solid_arrow(self):
        self.assertIn("loc_hall -->|down: the crypt stair| loc_crypt", build_diagram(GATED_MAP, self.SESSION))

    def test_visit_counts_appear_beside_the_names(self):
        diagram = build_diagram(GATED_MAP, self.SESSION)
        self.assertIn('loc_yard["Yard \N{MULTIPLICATION SIGN}2"]', diagram)

    def test_a_discovered_but_unvisited_location_carries_no_count(self):
        self.assertIn('loc_crypt["Old Crypt"]', build_diagram(GATED_MAP, self.SESSION))


class LabelTests(SimpleTestCase):
    """Labels and identifiers survive whatever a game declares."""

    def test_a_missing_label_falls_back_to_the_destination_name(self):
        config = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "b"}]},
                "b": {"known_by_default": True, "details": {"name": "The Inn"}},
            }
        }
        self.assertIn("|The Inn|", build_diagram(config))

    def test_punctuation_in_a_location_id_cannot_collapse_two_nodes(self):
        mapping = node_identifiers(["a.b", "a b"])
        self.assertNotEqual(mapping["a.b"], mapping["a b"])

    def test_an_unambiguous_id_keeps_its_readable_identifier(self):
        self.assertEqual(node_identifiers(["hall"])["hall"], "loc_hall")

    def test_a_quote_in_a_label_is_escaped(self):
        config = {
            "locations": {
                "a": {"known_by_default": True, "exits": [{"to": "b", "label": 'the "back" door'}]},
                "b": {"known_by_default": True},
            }
        }
        self.assertIn("&quot;back&quot;", build_diagram(config))


class ReadSessionTests(SimpleTestCase):
    """A saved session is read from either wrapping."""

    def _written(self, payload: dict) -> FilePath:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = FilePath(directory.name) / "session.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_a_slot_inside_engine_state_is_found(self):
        path = self._written({"engine_state": {"location_graph": {"known": ["a"]}}})
        self.assertEqual(read_session(path), {"known": ["a"]})

    def test_a_bare_engine_state_is_found(self):
        path = self._written({"location_graph": {"known": ["a"]}})
        self.assertEqual(read_session(path), {"known": ["a"]})

    def test_a_file_with_no_location_state_is_refused(self):
        path = self._written({"engine_state": {"inventory": {}}})
        with self.assertRaises(MapDiagramError):
            read_session(path)
