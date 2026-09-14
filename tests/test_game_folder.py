"""Resolving a game folder's own compiled story file, and reading its
`manifest.yaml`.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

import yaml

from ink_engine.game_folder import (
    GameFolderError,
    check_manifest_supported,
    find_main_story_file,
    read_cover_image,
    read_engine_format,
    read_extra_files,
    read_game_description,
    read_game_version,
    read_manifest_version,
    read_media_directories,
    read_module_literals,
    read_play_layout,
    read_prose_styles,
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

    def test_the_manifest_names_the_story(self):
        self._write("story.inkj", "{}")
        self._write("manifest.yaml", "MAIN_STORY_FILE: story.inkj\n")
        self.assertEqual(find_main_story_file(self.tmp), "story.inkj")

    def test_a_lone_inkj_is_not_guessed_at(self):
        """Nothing is inferred from what happens to be in the folder: a
        game with one story and no declaration is a game that has not
        said which story plays."""
        self._write("story.inkj", "{}")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_resolving_the_story_never_reads_the_media_tree(self):
        """It is a manifest lookup, so a game's media is irrelevant to it
        however much of it there is."""
        self._write("story.inkj", "{}")
        self._write("manifest.yaml", "MAIN_STORY_FILE: story.inkj\n")
        media = self.tmp / "images" / "rooms"
        media.mkdir(parents=True)
        (media / "decoy.inkj").write_text("{}", encoding="utf-8")
        self.assertEqual(find_main_story_file(self.tmp), "story.inkj")

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

    def test_several_inkj_files_with_no_declaration_is_an_error(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_multiple_inkj_files_resolved_by_main_story_file_manifest_field(self):
        self._write("story_a.inkj", "{}")
        real_story = self._write("story_b.inkj", "{}")
        self._write("manifest.yaml", "MAIN_STORY_FILE: story_b.inkj\n")
        self.assertEqual(find_main_story_file(self.tmp), "story_b.inkj")

    def test_main_story_file_naming_a_missing_file_is_an_error(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        self._write("manifest.yaml", "MAIN_STORY_FILE: story_c.inkj\n")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_a_malformed_init_py_with_multiple_inkj_files_is_an_error_not_a_crash(self):
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        self._write("manifest.yaml", "key: [unclosed\n  bad: : :")
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)

    def test_the_manifest_is_read_as_data_never_imported(self):
        """A manifest is data, with no execution path at all.

        The manifest was once `__init__.py`, and its safety rested on a
        promise never to import it. As YAML there is nothing to promise:
        Python source in the manifest is just a string that fails to
        describe any field, and a game folder's `__init__.py` is an empty
        package marker carrying no data."""
        self._write("story_a.inkj", "{}")
        self._write("story_b.inkj", "{}")
        self._write("manifest.yaml", 'import os\nos.environ["SHOULD_NEVER_RUN"] = "1"\n')
        with self.assertRaises(GameFolderError):
            find_main_story_file(self.tmp)
        import os

        self.assertNotIn("SHOULD_NEVER_RUN", os.environ)


class ReadPlayLayoutTests(TestCase):
    """A single-field manifest read, sharing the same helper
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
        self._write("manifest.yaml", "PLAY_LAYOUT: three_column\n")
        self.assertEqual(read_play_layout(self.tmp), "three_column")

    def test_no_manifest_at_all_returns_none(self):
        """Falling back to a default layout name is the CALLER's decision
        -- this function has no opinion on what layouts exist."""
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_manifest_with_no_play_layout_field_returns_none(self):
        self._write("manifest.yaml", "MAIN_STORY_FILE: story.inkj\n")
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_non_string_play_layout_returns_none(self):
        self._write("manifest.yaml", "PLAY_LAYOUT: 42\n")
        self.assertIsNone(read_play_layout(self.tmp))

    def test_a_malformed_init_py_returns_none_not_a_crash(self):
        self._write("manifest.yaml", "key: [unclosed\n  bad: : :")
        self.assertIsNone(read_play_layout(self.tmp))

    def test_the_manifest_is_read_as_data_never_imported(self):
        self._write("manifest.yaml", 'import os\nos.environ["SHOULD_NEVER_RUN_LAYOUT"] = "1"\n')
        # Python source is not a YAML mapping, so it declares no fields
        # at all -- and running it was never a possibility.
        self.assertIsNone(read_play_layout(self.tmp))
        import os

        self.assertNotIn("SHOULD_NEVER_RUN_LAYOUT", os.environ)

    def test_reading_play_layout_and_main_story_file_from_the_same_manifest_both_work(self):
        """The shared helper correctly reads either field independently,
        proving genericity rather than an accidental MAIN_STORY_FILE-only
        implementation."""
        story = self._write("story.inkj", "{}")
        self._write("manifest.yaml", "MAIN_STORY_FILE: story.inkj\nPLAY_LAYOUT: three_column\n")
        self.assertEqual(find_main_story_file(self.tmp), "story.inkj")
        self.assertEqual(read_play_layout(self.tmp), "three_column")


class ReadRequiredPluginsTests(TestCase):
    """The list-field manifest read for REQUIRED_PLUGINS."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str = "") -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_declared_plugins_are_read(self):
        self._write("manifest.yaml", "REQUIRED_PLUGINS: [scheduling, occupancy]\n")
        self.assertEqual(read_required_plugins(self.tmp), ["scheduling", "occupancy"])

    def test_no_manifest_at_all_returns_empty_list(self):
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_manifest_with_no_required_plugins_field_returns_empty_list(self):
        self._write("manifest.yaml", "MAIN_STORY_FILE: story.inkj\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_non_list_value_returns_empty_list(self):
        self._write("manifest.yaml", "REQUIRED_PLUGINS: scheduling\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_list_with_non_string_items_returns_empty_list(self):
        self._write("manifest.yaml", "REQUIRED_PLUGINS: [1, 2]\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_an_empty_list_is_a_real_value_not_absence(self):
        self._write("manifest.yaml", "REQUIRED_PLUGINS: []\n")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_a_malformed_init_py_returns_empty_list_not_a_crash(self):
        self._write("manifest.yaml", "key: [unclosed\n  bad: : :")
        self.assertEqual(read_required_plugins(self.tmp), [])

    def test_the_manifest_is_read_as_data_never_imported(self):
        self._write("manifest.yaml", 'import os\nos.environ["SHOULD_NEVER_RUN_PLUGINS"] = "1"\n')
        self.assertEqual(read_required_plugins(self.tmp), [])
        import os

        self.assertNotIn("SHOULD_NEVER_RUN_PLUGINS", os.environ)


class ReadModuleLiteralsTests(TestCase):
    """The general primitive every single-field/whole-file reader in this
    module (and each host application's own manifest/mapping reader)
    builds on."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str, content: str = "") -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_every_top_level_literal_assignment_is_read(self):
        path = self._write("data.py", 'A = 1\nB = "two"\nC = [3, 4]\n')
        result = read_module_literals(path)
        self.assertEqual(result.literals, {"A": 1, "B": "two", "C": [3, 4]})
        self.assertEqual(result.skipped, frozenset())

    def test_annotated_assignment_is_read_like_plain_assignment(self):
        """A declaration written as `NAME: Type = ...` is the same data as
        `NAME = ...` -- silently missing it would make a real mapping look
        like an empty one."""
        path = self._write("data.py", 'MAPPING: dict[str, str] = {"a": "b"}\n')
        self.assertEqual(read_module_literals(path).literals, {"MAPPING": {"a": "b"}})

    def test_a_bare_annotation_with_no_value_contributes_nothing_and_is_not_skipped(self):
        """A bare `NAME: Type` declares a type but gives no value -- there
        is nothing to evaluate, and nothing a game author was trying to
        assign, so it must not show up in `.skipped` either."""
        path = self._write("data.py", "MAPPING: dict\n")
        result = read_module_literals(path)
        self.assertEqual(result.literals, {})
        self.assertEqual(result.skipped, frozenset())

    def test_a_non_literal_assignment_is_skipped_not_raised(self):
        path = self._write("data.py", "A = 1\nB = some_function_call()\nC = 2\n")
        result = read_module_literals(path)
        self.assertEqual(result.literals, {"A": 1, "C": 2})
        self.assertEqual(result.skipped, frozenset({"B"}))

    def test_a_missing_file_returns_empty_result(self):
        result = read_module_literals(self.tmp / "nope.py")
        self.assertEqual(result.literals, {})
        self.assertEqual(result.skipped, frozenset())

    def test_a_malformed_file_returns_empty_result_not_a_crash(self):
        path = self._write("data.py", "this is not valid python (((")
        result = read_module_literals(path)
        self.assertEqual(result.literals, {})
        self.assertEqual(result.skipped, frozenset())

    def test_the_file_is_read_as_data_never_imported(self):
        path = self._write("data.py", 'import os\nos.environ["SHOULD_NEVER_RUN_LITERALS"] = "1"\nA = 1\n')
        self.assertEqual(read_module_literals(path).literals, {"A": 1})
        import os

        self.assertNotIn("SHOULD_NEVER_RUN_LITERALS", os.environ)


class ManifestCacheTests(TestCase):
    """`read_manifest()` parses once per file, not once per field.

    Each typed reader wants one field, so an uncached implementation
    re-parses for every one — measured at 5 parses for 5 fields, at
    ~2.7 ms a parse on a real game's manifest.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "manifest.yaml").write_text(
            "MAIN_STORY_FILE: story.inkj\nPLAY_LAYOUT: three_column\n" "REQUIRED_PLUGINS: [a, b]\nMEDIA_DIRECTORIES: [Images]\n",
            encoding="utf-8",
        )
        (self.tmp / "story.inkj").write_text("{}", encoding="utf-8")

    def _count_parses(self, work):
        calls = []
        original = yaml.safe_load

        def counting(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        yaml.safe_load = counting
        try:
            work()
        finally:
            yaml.safe_load = original
        return len(calls)

    def test_four_field_reads_cost_one_parse(self):
        def read_four():
            read_play_layout(self.tmp)
            read_required_plugins(self.tmp)
            read_media_directories(self.tmp)
            read_extra_files(self.tmp)

        self.assertEqual(self._count_parses(read_four), 1)

    def test_an_edited_manifest_is_picked_up_without_a_restart(self):
        """The cache keys on mtime, so editing a manifest mid-session is
        seen -- a game author should not have to restart to see a change."""
        self.assertEqual(read_play_layout(self.tmp), "three_column")
        os.utime(self.tmp / "manifest.yaml", (0, 0))
        (self.tmp / "manifest.yaml").write_text("PLAY_LAYOUT: classic\n", encoding="utf-8")
        self.assertEqual(read_play_layout(self.tmp), "classic")


class NewManifestFieldTests(TestCase):
    """The fields added with the YAML migration."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, body):
        (self.tmp / "manifest.yaml").write_text(body, encoding="utf-8")

    def test_every_new_field_reads_back(self):
        self._write(
            "MANIFEST_VERSION: 1\nENGINE_FORMAT: ink\nGAME_VERSION: '2.1'\n"
            "GAME_DESCRIPTION: A short game.\nCOVER_IMAGE: art/cover.png\n"
            "PROSE_STYLES: theme.css\n"
        )
        self.assertEqual(read_manifest_version(self.tmp), 1)
        self.assertEqual(read_engine_format(self.tmp), "ink")
        self.assertEqual(read_game_version(self.tmp), "2.1")
        self.assertEqual(read_game_description(self.tmp), "A short game.")
        self.assertEqual(read_cover_image(self.tmp), "art/cover.png")
        self.assertEqual(read_prose_styles(self.tmp), "theme.css")

    def test_every_new_field_is_optional(self):
        self._write("MAIN_STORY_FILE: story.inkj\n")
        self.assertIsNone(read_manifest_version(self.tmp))
        self.assertIsNone(read_engine_format(self.tmp))
        self.assertIsNone(read_game_version(self.tmp))
        self.assertIsNone(read_cover_image(self.tmp))

    def test_a_numeric_game_version_reads_as_a_string(self):
        """YAML types `1.0` as a float; a version is always a string, so
        `1.0` and `'1.0'` must not behave differently."""
        self._write("GAME_VERSION: 1.0\n")
        self.assertEqual(read_game_version(self.tmp), "1.0")

    def test_a_boolean_is_not_mistaken_for_a_manifest_version(self):
        """`True` is an int in Python; a version of True is nonsense."""
        self._write("MANIFEST_VERSION: true\n")
        self.assertIsNone(read_manifest_version(self.tmp))


class ManifestSupportTests(TestCase):
    """Two fields exist to be checked; unchecked they are worthless.

    A manifest written to a future schema would otherwise be read as this
    one and silently misinterpreted, and a game in another story format
    would be loaded as Ink and fail somewhere further in.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, body):
        (self.tmp / "manifest.yaml").write_text(body, encoding="utf-8")

    def test_the_supported_version_and_format_pass(self):
        self._write("MANIFEST_VERSION: 1\nENGINE_FORMAT: ink\n")
        check_manifest_supported(self.tmp)

    def test_a_future_manifest_version_is_refused(self):
        self._write("MANIFEST_VERSION: 99\n")
        with self.assertRaises(GameFolderError) as caught:
            check_manifest_supported(self.tmp)
        self.assertIn("newer player", str(caught.exception))

    def test_an_older_manifest_version_is_accepted(self):
        """Only a version from the future is unreadable; an older one is
        a shape this engine already knows."""
        self._write("MANIFEST_VERSION: 0\n")
        check_manifest_supported(self.tmp)

    def test_another_story_format_is_refused_by_name(self):
        self._write("ENGINE_FORMAT: twine\n")
        with self.assertRaises(GameFolderError) as caught:
            check_manifest_supported(self.tmp)
        self.assertIn("twine", str(caught.exception))

    def test_omitting_both_fields_is_accepted(self):
        """Games predate both fields; absence claims nothing."""
        self._write("GAME_TITLE: Old Game\n")
        check_manifest_supported(self.tmp)

    def test_a_game_with_no_manifest_at_all_is_accepted_here(self):
        """This check has one job. A missing story is
        `find_main_story_file()`'s error to raise, not this one's."""
        check_manifest_supported(self.tmp)
