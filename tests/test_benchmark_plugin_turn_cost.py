"""The plugin-layer benchmark (benchmarks/plugin_turn_cost.py) still builds and runs."""

from __future__ import annotations

import ast
import contextlib
import io
import sys
from pathlib import Path
from unittest import TestCase

from benchmarks import plugin_turn_cost

EXAMPLE_GAME = Path(__file__).resolve().parents[1] / "examples" / "cloak_of_darkness"


class SyntheticTownTests(TestCase):
    """The synthetic town is filled to the size the constants declare."""

    @classmethod
    def setUpClass(cls):
        cls.session, cls.state = plugin_turn_cost.synthetic_session(1)

    def test_every_generic_plugin_is_active(self):
        """Every generic engine plugin contributes a state slot."""
        self.assertEqual(set(self.state), set(self.session.active_names))

    def test_the_state_is_filled_to_scale(self):
        """Each plugin holds the counts the benchmark promises."""
        self.assertEqual(len(self.state["character_occupancy"]["locations"]), plugin_turn_cost.CHARACTERS)
        self.assertEqual(len(self.state["quests"]["stages"]), plugin_turn_cost.QUESTS)
        self.assertEqual(len(self.state["cost_table"]["costs"]), plugin_turn_cost.PRICED_ACTIONS)
        places = plugin_turn_cost.STREET_GRID**2 + plugin_turn_cost.BUILDINGS * plugin_turn_cost.ROOMS_PER_BUILDING
        self.assertEqual(len(self.state["location_graph"]["declared"]), places)


class CommandLineTests(TestCase):
    """The command line runs without any application installed."""

    def test_a_game_folder_is_measured(self):
        """`--game` reports on the example game."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            plugin_turn_cost.main(["--game", str(EXAMPLE_GAME)])
        self.assertIn("game cloak_of_darkness", output.getvalue())
        self.assertIn("plugin layer per turn", output.getvalue())

    def test_only_the_engine_and_the_standard_library_are_imported(self):
        """The benchmark imports nothing but `ink_engine` and the standard library."""
        tree = ast.parse(Path(plugin_turn_cost.__file__).read_text(encoding="utf-8"))
        roots = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        roots |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertEqual(sorted(roots - sys.stdlib_module_names - {"ink_engine"}), [])
