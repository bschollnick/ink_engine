"""The plugin contract itself: `Plugin`'s own invariants, discovery of
plugins from real importable sources, and binding resolution.

These three modules (`plugin.py`, `discovery.py`, `binding.py`) are the
library's whole plugin surface, and every host builds on them. Until this
file existed their only coverage lived in the consumers' own suites, so a
contract change could pass here and break both hosts.

Discovery is exercised against real temporary packages on `sys.path`
rather than mocks: the thing worth testing is that ordinary Python import
machinery finds a plugin, which a mocked import would not prove.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import TestCase

from ink_engine.binding import (
    ManifestMismatchError,
    check_required_plugins,
    resolve_bindings,
)
from ink_engine.discovery import (
    ENGINE_PLUGIN_PACKAGE,
    discover_plugins,
    make_game_folder_importable,
)
from ink_engine.engine import load_story_root
from ink_engine.plugin import Plugin


def _story_calling(external_name: str) -> dict[str, Any]:
    """Build a minimal compiled story whose root calls one EXTERNAL.

    Args:
        external_name: The EXTERNAL function the story calls.

    Returns:
        Compiled-story JSON, ready for `load_story_root`.
    """
    return {"inkVersion": 21, "root": [[{"x()": external_name, "exArgs": 0}, "\n", "done"], None], "listDefs": {}}


def _stateless(name: str, **bindings: Any) -> Plugin:
    """Build a stateless plugin exposing exactly `bindings`."""
    return Plugin(name=name, display_name=name.replace("_", " ").title(), bindings=bindings)


class PluginInvariantTests(TestCase):
    """`Plugin.__post_init__`'s all-or-nothing rule for the three
    stateful fields."""

    def test_a_plugin_may_be_purely_stateless(self):
        plugin = _stateless("weather", is_raining_now=lambda: 0)
        self.assertIsNone(plugin.state_key)
        self.assertEqual(sorted(plugin.bindings), ["is_raining_now"])

    def test_a_plugin_may_set_all_three_stateful_fields(self):
        plugin = Plugin(
            name="clock",
            display_name="Clock",
            state_key="clock",
            init_state=lambda config: {"hour": 0},
            bind=lambda own_state, engine_state, list_defs: {},
        )
        self.assertEqual(plugin.state_key, "clock")

    def test_a_half_declared_plugin_raises(self):
        """A plugin that owns state must say both where it lives and how
        to build it; binding without either is handed nothing."""
        for partial in (
            {"state_key": "clock"},
            {"init_state": lambda: {}},
            {"bind": lambda own_state, engine_state, list_defs: {}},
        ):
            with self.subTest(partial=sorted(partial)):
                with self.assertRaises(ValueError) as caught:
                    Plugin(name="clock", display_name="Clock", **partial)
                self.assertIn("clock", str(caught.exception))

    def test_a_plugin_may_own_state_without_binding_anything(self):
        """State a dependent plugin reads is a real shape: requiring a
        no-op `bind` for it only obscured which plugins answer Ink."""
        plugin = Plugin(name="map", display_name="Map", state_key="map", init_state=lambda config: {})
        self.assertEqual(plugin.state_key, "map")
        self.assertIsNone(plugin.bind)

    def test_such_a_plugin_still_gets_its_state_allocated(self):
        plugin = Plugin(name="map", display_name="Map", state_key="map", init_state=lambda config: {"declared": []})
        engine_state: dict[str, Any] = {}
        resolve_bindings({"map": plugin}, ["map"], engine_state)
        self.assertEqual(engine_state, {"map": {"declared": []}})


class DiscoverPluginsTests(TestCase):
    """Discovery against real, importable temporary packages."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        sys.path.insert(0, str(self.tmp))
        self.addCleanup(self._remove_from_sys_path)
        self._imported: list[str] = []
        self.addCleanup(self._evict_imported)

    def _remove_from_sys_path(self) -> None:
        while str(self.tmp) in sys.path:
            sys.path.remove(str(self.tmp))

    def _evict_imported(self) -> None:
        for name in self._imported:
            for loaded in [key for key in sys.modules if key == name or key.startswith(f"{name}.")]:
                del sys.modules[loaded]

    def _write_package(self, package_name: str, modules: dict[str, str]) -> str:
        """Create a real importable package, and return its dotted name.

        Nothing is imported here: `discover_plugins()` imports each
        source itself by ordinary dotted name. The package only has to be
        findable, which the `sys.path` entry in `setUp` arranges.
        """
        package_dir = self.tmp / package_name
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text(modules.get("__init__", ""), encoding="utf-8")
        for module_stem, body in modules.items():
            if module_stem != "__init__":
                (package_dir / f"{module_stem}.py").write_text(body, encoding="utf-8")
        self._imported.append(package_name)
        return package_name

    def test_a_package_source_finds_a_module_declaring_PLUGIN(self):
        package = self._write_package(
            "solo_game",
            {
                "weather": (
                    "from ink_engine.plugin import Plugin\n"
                    "PLUGIN = Plugin(name='weather', display_name='Weather',\n"
                    "                bindings={'is_raining_now': lambda: 1})\n"
                )
            },
        )
        found = discover_plugins([package])
        self.assertEqual(sorted(found), ["weather"])
        self.assertEqual(found["weather"].display_name, "Weather")

    def test_a_module_declaring_PLUGINS_contributes_every_entry(self):
        package = self._write_package(
            "multi_game",
            {
                "pair": (
                    "from ink_engine.plugin import Plugin\n"
                    "PLUGINS = [Plugin(name='first', display_name='First'),\n"
                    "           Plugin(name='second', display_name='Second')]\n"
                )
            },
        )
        self.assertEqual(sorted(discover_plugins([package])), ["first", "second"])

    def test_a_module_with_no_plugin_declaration_is_simply_skipped(self):
        """A plain library module beside real plugins is normal, not an
        error -- inventory.py and containers.py ship exactly that way."""
        package = self._write_package(
            "mixed_game",
            {
                "helpers": "VALUE = 3\n",
                "real": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='real', display_name='Real')\n"),
            },
        )
        self.assertEqual(sorted(discover_plugins([package])), ["real"])

    def test_a_packages_own_init_may_declare_the_plugins(self):
        """How a game folder re-exports its submodules' plugins as one
        list instead of spreading declarations across files."""
        package = self._write_package(
            "reexporting_game",
            {
                "__init__": ("from ink_engine.plugin import Plugin\nPLUGINS = [Plugin(name='from_init', display_name='From init')]\n"),
            },
        )
        self.assertEqual(sorted(discover_plugins([package])), ["from_init"])

    def test_a_reexporting_package_is_not_also_walked(self):
        """A package whose `__init__.py` declares plugins has already
        given its complete answer. Walking its submodules too would find
        each re-exported plugin a second time and read as a duplicate
        name -- which is exactly how a real game folder is laid out."""
        package = self._write_package(
            "reexport_and_submodules",
            {
                "__init__": ("from .part import PLUGIN as _PART\nPLUGINS = [_PART]\n"),
                "part": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='only_once', display_name='Only once')\n"),
            },
        )
        self.assertEqual(sorted(discover_plugins([package])), ["only_once"])

    def test_a_private_module_is_not_scanned(self):
        """A leading underscore marks a module as the package's own
        internals, not a discoverable plugin."""
        package = self._write_package(
            "private_game",
            {
                "_helpers": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='private', display_name='Private')\n"),
                "real": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='public', display_name='Public')\n"),
            },
        )
        self.assertEqual(sorted(discover_plugins([package])), ["public"])

    def test_a_dotted_module_name_source_is_imported_and_scanned(self):
        self._write_package(
            "dotted_game",
            {"plugin_mod": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='dotted', display_name='Dotted')\n")},
        )
        self.assertEqual(sorted(discover_plugins(["dotted_game.plugin_mod"])), ["dotted"])

    def test_a_game_package_resolves_its_own_relative_imports(self):
        """The real payoff of plain import machinery: a multi-file game
        folder works without any synthetic namespace handling."""
        self._write_package(
            "relative_game",
            {
                "base": "SHARED_NAME = 'from_base'\n",
                "__init__": "",
                "entry": (
                    "from ink_engine.plugin import Plugin\n"
                    "from .base import SHARED_NAME\n"
                    "PLUGIN = Plugin(name=SHARED_NAME, display_name='Relative')\n"
                ),
            },
        )
        self.assertEqual(sorted(discover_plugins(["relative_game.entry"])), ["from_base"])

    def test_two_sources_declaring_the_same_plugin_name_raise(self):
        """A silent winner here would mean the host cannot tell which
        implementation a story actually got."""
        first = self._write_package(
            "clash_one",
            {"mod": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='dupe', display_name='One')\n")},
        )
        second = self._write_package(
            "clash_two",
            {"mod": ("from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name='dupe', display_name='Two')\n")},
        )
        with self.assertRaises(ValueError) as caught:
            discover_plugins([first, second])
        self.assertIn("dupe", str(caught.exception))

    def test_no_sources_finds_no_plugins(self):
        self.assertEqual(discover_plugins([]), {})

    def test_an_unimportable_source_raises(self):
        """A source naming something Python cannot import is a host
        misconfiguration, reported loudly rather than silently finding
        nothing."""
        with self.assertRaises(ModuleNotFoundError):
            discover_plugins(["no_such_package_anywhere"])

    def test_the_engines_own_plugin_package_is_discoverable_by_its_constant(self):
        """`ENGINE_PLUGIN_PACKAGE` is what both hosts pass to get the
        shipped generic plugins; it must actually resolve."""
        found = discover_plugins([ENGINE_PLUGIN_PACKAGE])
        self.assertIn("character_occupancy", found)
        self.assertIn("location_graph", found)

    def test_make_game_folder_importable_returns_the_folder_name(self):
        package_dir = self.tmp / "importable_game"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        self.assertEqual(make_game_folder_importable(package_dir), "importable_game")

    def test_make_game_folder_importable_is_idempotent(self):
        """Called once per game, but many games share one parent -- a
        repeat must not grow `sys.path` each time."""
        package_dir = self.tmp / "repeat_game"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        make_game_folder_importable(package_dir)
        before = list(sys.path)
        make_game_folder_importable(package_dir)
        self.assertEqual(sys.path, before)


class ResolveBindingsTests(TestCase):
    """Binding resolution, state allocation, and the merge order."""

    def test_a_stateless_plugins_bindings_are_merged(self):
        plugins = {"weather": _stateless("weather", is_raining_now=lambda: 1)}
        resolved = resolve_bindings(plugins, ["weather"], {})
        self.assertEqual(sorted(resolved), ["is_raining_now"])
        self.assertEqual(resolved["is_raining_now"](), 1)

    def test_an_inactive_plugin_contributes_nothing(self):
        plugins = {
            "weather": _stateless("weather", is_raining_now=lambda: 1),
            "unused": _stateless("unused", never_called_now=lambda: 1),
        }
        self.assertEqual(sorted(resolve_bindings(plugins, ["weather"], {})), ["is_raining_now"])

    def test_a_stateful_plugin_gets_its_slot_allocated_on_first_use(self):
        plugin = Plugin(
            name="clock",
            display_name="Clock",
            state_key="clock",
            init_state=lambda config: {"hour": 7},
            bind=lambda own_state, engine_state, list_defs: {"hour_now": lambda: own_state["hour"]},
        )
        engine_state: dict[str, Any] = {}
        resolved = resolve_bindings({"clock": plugin}, ["clock"], engine_state)
        self.assertEqual(engine_state, {"clock": {"hour": 7}})
        self.assertEqual(resolved["hour_now"](), 7)

    def test_existing_state_is_reused_rather_than_reinitialised(self):
        """Resuming a save must not reset a plugin's own slot."""
        plugin = Plugin(
            name="clock",
            display_name="Clock",
            state_key="clock",
            init_state=lambda config: {"hour": 7},
            bind=lambda own_state, engine_state, list_defs: {"hour_now": lambda: own_state["hour"]},
        )
        engine_state: dict[str, Any] = {"clock": {"hour": 19}}
        resolved = resolve_bindings({"clock": plugin}, ["clock"], engine_state)
        self.assertEqual(resolved["hour_now"](), 19)

    def test_a_plugin_may_read_another_plugins_slot(self):
        """The documented cross-plugin pattern: read the other plugin's
        state by its known key, with no dependency declaration."""
        owner = Plugin(
            name="location_graph",
            display_name="Location graph",
            state_key="location_graph",
            init_state=lambda config: {"declared": ["market"]},
            bind=lambda own_state, engine_state, list_defs: {},
        )

        def _reader_bind(own_state: dict[str, Any], engine_state: dict[str, Any], list_defs: dict[str, Any]) -> dict[str, Any]:
            known = engine_state.get("location_graph", {}).get("declared", [])
            return {"first_location_now": lambda: known[0] if known else ""}

        reader = Plugin(
            name="occupancy",
            display_name="Occupancy",
            state_key="occupancy",
            init_state=lambda config: {},
            bind=_reader_bind,
        )
        resolved = resolve_bindings({"location_graph": owner, "occupancy": reader}, ["location_graph", "occupancy"], {})
        self.assertEqual(resolved["first_location_now"](), "market")

    def test_a_later_plugin_wins_a_binding_name_collision(self):
        """How a game overrides a generic plugin's binding: activate it
        after the generic one."""
        plugins = {
            "generic": _stateless("generic", where_is_now=lambda: "generic"),
            "game": _stateless("game", where_is_now=lambda: "game"),
        }
        resolved = resolve_bindings(plugins, ["generic", "game"], {})
        self.assertEqual(resolved["where_is_now"](), "game")

    def test_an_undiscovered_active_name_raises(self):
        """A host promising a plugin that discovery never found is a
        real misconfiguration, reported loudly rather than skipped."""
        with self.assertRaises(KeyError):
            resolve_bindings({}, ["never_discovered"], {})


class ListDefsArgumentTests(TestCase):
    """The story's LIST tables reach `bind()` as a real argument.

    Passing them directly rather than through `engine_state` is what makes
    the whole class of lifetime bugs unwritable: `list_defs` is a local,
    so it cannot outlive the call, cannot be read late from a closure, and
    cannot reach a host's persisted save data.
    """

    def _capturing_plugin(self, seen: dict[str, Any]) -> Plugin:
        def _bind(own_state: dict[str, Any], engine_state: dict[str, Any], list_defs: dict[str, Any]) -> dict[str, Any]:
            seen["list_defs"] = list_defs
            return {}

        return Plugin(name="reader", display_name="Reader", state_key="reader", init_state=lambda config: {}, bind=_bind)

    def test_bind_receives_the_tables(self):
        seen: dict[str, Any] = {}
        list_defs = {"AllCharacters": {"gina": 1, "lola": 2}}

        resolve_bindings({"reader": self._capturing_plugin(seen)}, ["reader"], {}, list_defs=list_defs)

        self.assertEqual(seen["list_defs"], list_defs)

    def test_omitting_list_defs_hands_bind_an_empty_mapping(self):
        """Never `None`: a plugin can index the argument unconditionally."""
        seen: dict[str, Any] = {}

        resolve_bindings({"reader": self._capturing_plugin(seen)}, ["reader"], {})

        self.assertEqual(seen["list_defs"], {})

    def test_the_tables_never_enter_engine_state(self):
        """The property that makes cross-session contamination and save
        pollution impossible: nothing is ever written into the session's
        own dict, so there is nothing to leak or to clean up."""
        engine_state: dict[str, Any] = {}

        resolve_bindings({"reader": self._capturing_plugin({})}, ["reader"], engine_state, list_defs={"AllCharacters": {"gina": 1}})

        self.assertEqual(sorted(engine_state), ["reader"])  # the plugin's own slot, nothing else

    def test_two_sessions_of_different_stories_receive_their_own_tables(self):
        """Each call's tables are its own argument, so concurrent
        sessions of different stories cannot observe each other."""
        seen_first: dict[str, Any] = {}
        seen_second: dict[str, Any] = {}
        first_lists = {"AllCharacters": {"gina": 1}}
        second_lists = {"AllCharacters": {"zali": 1, "nina": 2}}

        resolve_bindings({"reader": self._capturing_plugin(seen_first)}, ["reader"], {}, list_defs=first_lists)
        resolve_bindings({"reader": self._capturing_plugin(seen_second)}, ["reader"], {}, list_defs=second_lists)

        self.assertEqual(seen_first["list_defs"], first_lists)
        self.assertEqual(seen_second["list_defs"], second_lists)

    def test_a_bind_with_the_old_two_argument_shape_fails_loudly(self):
        """The reason the third parameter is mandatory rather than
        inspected-for. An un-migrated plugin raises at bind time instead
        of silently never receiving the tables."""

        def _old_shape_bind(own_state: dict[str, Any], engine_state: dict[str, Any]) -> dict[str, Any]:
            return {}

        plugin = Plugin(name="old", display_name="Old", state_key="old", init_state=lambda config: {}, bind=_old_shape_bind)

        with self.assertRaises(TypeError):
            resolve_bindings({"old": plugin}, ["old"], {}, list_defs={})


class SlotMethodTests(TestCase):
    """Each stateful plugin reaches its own stored data through its own
    methods, so the storage layout never crosses the boundary.

    The point is that a consumer names the PLUGIN and the OPERATION, not
    the key a plugin happens to save under. The encapsulation probe in the
    plan checks it by renaming a field and confirming nothing outside the
    owning module breaks.
    """

    def test_a_write_lands_in_the_live_session_state(self):
        """The method works on the slot handed to it, so a write is
        already persisted when the turn ends -- no write-back step."""
        from ink_engine.engine_plugins.skills import SKILLS

        slot = SKILLS.init_state(None)
        SKILLS.set_skill_level(slot, "hero", "Strength", 3)
        self.assertEqual(slot["skill_levels"]["hero"]["Strength"], 3)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 3)

    def test_an_unset_value_answers_the_default(self):
        from ink_engine.engine_plugins.skills import SKILLS

        self.assertEqual(SKILLS.skill_level(SKILLS.init_state(None), "nobody", "Strength", default=-1), -1)

    def test_all_levels_returns_an_independent_copy(self):
        """Mutating what a reader hands back must not corrupt session
        state."""
        from ink_engine.engine_plugins.skills import SKILLS

        slot = SKILLS.init_state(None)
        SKILLS.set_skill_level(slot, "hero", "Strength", 5)
        snapshot = SKILLS.all_levels(slot, "hero")
        snapshot["Strength"] = 999
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 5)

    def test_no_whole_slot_rewrite_can_orphan_a_reader(self):
        """The hazard the old accessor pattern documented -- an accessor
        held across a `clear()`/`update()` writing into orphaned inner
        dicts -- cannot occur: every method takes the slot itself and
        nothing rewrites the whole slot."""
        from ink_engine.engine_plugins.skills import SKILLS

        slot = SKILLS.init_state(None)
        SKILLS.set_skill_level(slot, "hero", "Strength", 1)
        slot.clear()
        slot.update(SKILLS.init_state(None))
        SKILLS.set_skill_level(slot, "hero", "Strength", 99)
        self.assertEqual(SKILLS.skill_level(slot, "hero", "Strength"), 99)


class ManifestCheckTests(TestCase):
    """The manifest is a check and balance: a plugin in use but not
    declared is an error, not a convenience.

    Without this, the two can drift silently -- one host binds from a
    database row, another from the manifest, and the game plays
    differently on each with nothing raising.
    """

    def _plugins(self) -> dict[str, Plugin]:
        return {
            "declared": _stateless("declared", declared_now=lambda: 1),
            "undeclared": _stateless("undeclared", only_here_now=lambda: 1),
        }

    def test_a_consistent_manifest_raises_nothing(self):
        check_required_plugins(self._plugins(), ["declared"], ["declared"])

    def test_activating_an_undeclared_plugin_raises(self):
        with self.assertRaises(ManifestMismatchError) as caught:
            check_required_plugins(self._plugins(), ["declared"], ["declared", "undeclared"])
        self.assertIn("undeclared", str(caught.exception))

    def test_exporting_an_undeclared_plugin_raises(self):
        """A game's package exporting a plugin its manifest omits is the
        same drift, found before anything is activated."""
        with self.assertRaises(ManifestMismatchError) as caught:
            check_required_plugins(self._plugins(), ["declared"], ["declared"], game_plugin_names=["declared", "undeclared"])
        self.assertIn("undeclared", str(caught.exception))

    def test_the_error_names_every_offender_at_once(self):
        plugins = self._plugins()
        plugins["third"] = _stateless("third")
        with self.assertRaises(ManifestMismatchError) as caught:
            check_required_plugins(plugins, ["declared"], ["declared", "undeclared", "third"])
        self.assertIn("undeclared", str(caught.exception))
        self.assertIn("third", str(caught.exception))

    def test_a_plugin_a_declared_one_already_covers_is_not_flagged(self):
        """A game shipping its own plugin for an Ink function a generic
        one could also answer is overriding the engine, not leaving a
        gap -- flagging it would make the check unusable."""
        plugins = {
            "generic": _stateless("generic", where_is_now=lambda: "generic"),
            "game": _stateless("game", where_is_now=lambda: "game"),
        }
        root = load_story_root(_story_calling("where_is_now"))
        check_required_plugins(plugins, ["game"], ["game"], root=root)

    def test_the_only_provider_of_a_called_external_must_be_declared(self):
        plugins = {"generic": _stateless("generic", where_is_now=lambda: "generic")}
        root = load_story_root(_story_calling("where_is_now"))
        with self.assertRaises(ManifestMismatchError) as caught:
            check_required_plugins(plugins, [], [], root=root)
        self.assertIn("where_is_now", str(caught.exception))
