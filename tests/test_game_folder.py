"""claude_docs/plans/standalone_if_player.md Step 2: resolving a game
folder's own compiled story file. Step 4: reading its own PLAY_LAYOUT
manifest field.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

from ink_engine.game_folder import (
    GameFolderError,
    find_main_story_file,
    read_play_layout,
    read_required_plugins,
)


class FindMainStoryFileTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str = "") -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_a_single_inkj_file_is_used_with_no_manifest_read(self):
        """The common case: exactly one .inkj file, no __init__.py needed
        at all to resolve it."""
        story = self._write("story.inkj", "{}")
        self.assertEqual(find_main_story_file(self.tmp), story)

    def test_a_single_inkj_file_is_used_even_with_a_stray_ink_source_file(self):
        """An .ink source file alongside its own compiled counterpart is
        not ambiguity -- there is still exactly one .inkj."""
        story = self._write("story.inkj", "{}")
        self._write("story.ink", "== knot ==\n")
        self.assertEqual(find_main_story_file(self.tmp), story)

    def test_zero_inkj_files_with_only_ink_source_is_a_real_error(self):
        """The exact case this validation exists for: a .ink file with no
        compiled counterpart is not a playable story, regardless of how
        it got there -- see this project's own permanent "no compiler
        dependency" decision."""
        self._write("story.ink", "== knot ==\n")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_zero_inkj_files_and_no_manifest_at_all_is_a_real_error(self):
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_multiple_inkj_files_with_no_manifest_to_disambiguate_is_an_error(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_multiple_inkj_files_resolved_by_main_story_file_manifest_field(self):
        self._write("story_a.inkj", "{}")
        real_story = self._write("story_b.inkj", "{}")
        self._write("__init__.py", 'MAIN_STORY_FILE = "story_b.inkj"\n')
        self.assertEqual(find_main_story_file(self.tmp), real_story)

    def test_main_story_file_naming_a_missing_file_is_an_error(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        self._write("__init__.py", 'MAIN_STORY_FILE = "story_c.inkj"\n')
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_a_malformed_init_py_with_multiple_inkj_files_is_an_error_not_a_crash(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        self._write("__init__.py", "this is not valid python (((")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_the_manifest_is_read_as_data_never_imported(self):
        """A game folder is untrusted content -- __init__.py containing
        real, executable side effects must never run just to resolve the
        story file."""
        self._write("story_a.inkj", "{}")
        real_story = self._write("story_b.inkj", "{}")
        self._write("__init__.py", 'import os\nos.environ["SHOULD_NEVER_RUN"] = "1"\nMAIN_STORY_FILE = "story_b.inkj"\n')
        self.assertEqual(find_main_story_file(self.tmp), real_story)
        import os

        self.assertNotIn("SHOULD_NEVER_RUN", os.environ)


class ReadPlayLayoutTests(TestCase):
    """Step 4's own single-field manifest read, sharing the same helper
    find_main_story_file() uses for MAIN_STORY_FILE."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str = "") -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_a_declared_layout_is_read(self):
        self._write("__init__.py", 'PLAY_LAYOUT = "three_column"\n')
        self.assertEqual(read_play_layout(self.tmp), "three_column")

    def test_no_manifest_at_all_returns_none(self):
        """Falling back to a default layout name is the CALLER's decision
        -- this function has no opinion on what layouts exist."""
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_manifest_with_no_play_layout_field_returns_none(self):
        self._write("__init__.py", 'MAIN_STORY_FILE = "story.inkj"\n')
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_non_string_play_layout_returns_none(self):
        self._write("__init__.py", "PLAY_LAYOUT = 42\n")
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_malformed_init_py_returns_none_not_a_crash(self):
        self._write("__init__.py", "this is not valid python (((")
        self.assertIsNone(read_play_layout(self.tmp))

    def test_the_manifest_is_read_as_data_never_imported(self):
        self._write("__init__.py", 'import os\nos.environ["SHOULD_NEVER_RUN_LAYOUT"] = "1"\nPLAY_LAYOUT = "three_column"\n')
        self.assertEqual(read_play_layout(self.tmp), "three_column")
        import os

        self.assertNotIn("SHOULD_NEVER_RUN_LAYOUT", os.environ)

    def test_reading_play_layout_and_main_story_file_from_the_same_manifest_both_work(self):
        """The shared helper correctly reads either field independently,
        proving genericity rather than an accidental MAIN_STORY_FILE-only
        implementation."""
        story = self._write("story.inkj", "{}")
        self._write("__init__.py", 'MAIN_STORY_FILE = "story.inkj"\nPLAY_LAYOUT = "three_column"\n')
        self.assertEqual(find_main_story_file(self.tmp), story)
        self.assertEqual(read_play_layout(self.tmp), "three_column")


class ReadRequiredPluginsTests(TestCase):
    """Step 4's own list-field manifest read -- REQUIRED_PLUGINS, the
    same field name QuickBBS's own ingestion.py already populates
    Story.game_required_plugins from."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str = "") -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_declared_plugins_are_read(self):
        self._write("__init__.py", 'REQUIRED_PLUGINS = ["scheduling", "occupancy"]\n')
        self.assertEqual(read_required_plugins(self.tmp), ["scheduling", "occupancy"])

    def test_no_manifest_at_all_returns_empty_list(self):
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_manifest_with_no_required_plugins_field_returns_empty_list(self):
        self._write("__init__.py", 'MAIN_STORY_FILE = "story.inkj"\n')
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_non_list_value_returns_empty_list(self):
        self._write("__init__.py", 'REQUIRED_PLUGINS = "scheduling"\n')
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_list_with_non_string_items_returns_empty_list(self):
        self._write("__init__.py", "REQUIRED_PLUGINS = [1, 2]\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_an_empty_list_is_a_real_value_not_absence(self):
        self._write("__init__.py", "REQUIRED_PLUGINS = []\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_malformed_init_py_returns_empty_list_not_a_crash(self):
        self._write("__init__.py", "this is not valid python (((")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_the_manifest_is_read_as_data_never_imported(self):
        self._write("__init__.py", 'import os\nos.environ["SHOULD_NEVER_RUN_PLUGINS"] = "1"\nREQUIRED_PLUGINS = ["scheduling"]\n')
        self.assertEqual(read_required_plugins(self.tmp), ["scheduling"])
        import os

        self.assertNotIn("SHOULD_NEVER_RUN_PLUGINS", os.environ)
