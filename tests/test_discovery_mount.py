"""Mounting a game for import, and releasing it again.

Removing a `sys.path` entry does not unload anything: an imported module
is cached by name, so without purging `sys.modules` a second game whose
package shares the first's name silently gets the first's code.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

from ink_engine.discovery import discover_plugins, mount_game

PLUGIN_SOURCE = "from ink_engine.plugin import Plugin\nPLUGIN = Plugin(name={name!r}, display_name='x')\n"


class MountTestCase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._restore_import_state, list(sys.path), set(sys.modules))

    def _restore_import_state(self, path_before, modules_before):
        sys.path[:] = path_before
        for name in [n for n in sys.modules if n not in modules_before and n.startswith("mygame")]:
            del sys.modules[name]

    def _folder(self, tag: str) -> Path:
        game = self.tmp / tag / "mygame"
        game.mkdir(parents=True)
        (game / "__init__.py").write_text("", encoding="utf-8")
        (game / "plugins.py").write_text(PLUGIN_SOURCE.format(name=f"p_{tag}"), encoding="utf-8")
        return game

    def _bundle(self, tag: str) -> Path:
        target = self.tmp / f"{tag}.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("mygame/__init__.py", "")
            archive.writestr("mygame/plugins.py", PLUGIN_SOURCE.format(name=f"p_{tag}"))
        return target


class CollisionTests(MountTestCase):
    """The bug this exists to fix."""

    def test_a_second_game_gets_its_own_modules(self):
        with mount_game(self._folder("A")):
            self.assertIn("p_A", discover_plugins(["mygame"]))
        with mount_game(self._folder("B")):
            self.assertIn("p_B", discover_plugins(["mygame"]))

    def test_a_bundle_does_not_inherit_a_folders_modules(self):
        with mount_game(self._folder("A")):
            importlib.import_module("mygame.plugins")
        with mount_game(self._bundle("Z")):
            self.assertIn("p_Z", discover_plugins(["mygame"]))

    def test_mounting_twice_does_not_accumulate_path_entries(self):
        folder = self._folder("A")
        before = len(sys.path)
        with mount_game(folder):
            during = len(sys.path)
        self.assertEqual(during, before + 1)
        self.assertEqual(len(sys.path), before)


class ReleaseTests(MountTestCase):
    def test_unmount_clears_both_the_path_and_the_modules(self):
        mounted = mount_game(self._folder("A"))
        importlib.import_module("mygame.plugins")
        mounted.unmount()
        self.assertNotIn(mounted.path_entry, sys.path)
        self.assertNotIn("mygame.plugins", sys.modules)

    def test_unmount_is_idempotent(self):
        mounted = mount_game(self._folder("A"))
        mounted.unmount()
        mounted.unmount()

    def test_the_context_manager_releases_on_the_way_out(self):
        with mount_game(self._folder("A")) as mounted:
            entry = mounted.path_entry
        self.assertNotIn(entry, sys.path)

    def test_an_exception_still_releases(self):
        with self.assertRaises(RuntimeError):
            with mount_game(self._folder("A")) as mounted:
                entry = mounted.path_entry
                raise RuntimeError("boom")
        self.assertNotIn(entry, sys.path)


class BundleMountTests(MountTestCase):
    def test_a_bundle_mounts_by_its_own_package_name(self):
        with mount_game(self._bundle("Z")) as mounted:
            self.assertEqual(mounted.package, "mygame")
            self.assertIn("p_Z", discover_plugins([mounted.package]))

    def test_a_bundle_with_several_package_directories_is_refused(self):
        target = self.tmp / "two.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("one/__init__.py", "")
            archive.writestr("two/__init__.py", "")
        with self.assertRaises(ValueError):
            mount_game(target)

    def test_something_that_is_neither_is_refused(self):
        stray = self.tmp / "notes.txt"
        stray.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            mount_game(stray)
