"""Game bundling: the manifest decides what ships."""

from __future__ import annotations

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path
from unittest import TestCase as SimpleTestCase

from ink_engine.bundle_cli import main
from ink_engine.bundler import (
    BundleError,
    build_bundle,
    open_bundle_manifest,
    select_bundle_contents,
    stale_sources,
    verify_plan,
)

STORY_JSON = json.dumps({"inkVersion": 21, "root": [["done", None], "done", None], "listDefs": {}})

DEFAULT_MANIFEST = "MAIN_STORY_FILE: story.inkj\nMEDIA_DIRECTORIES: [Images]\n"


def _make_game(root: Path, *, manifest: str = DEFAULT_MANIFEST, extra: dict[str, str] | None = None) -> Path:
    """Build a minimal game folder; `extra` maps relative path -> content."""
    game = root / "mygame"
    (game / "Images").mkdir(parents=True)
    (game / "manifest.yaml").write_text(manifest, encoding="utf-8")
    # Python's package initialization file: it holds nothing here, but the
    # folder must import so its plugins and sidebar load.
    (game / "__init__.py").write_text("", encoding="utf-8")
    (game / "story.inkj").write_text(STORY_JSON, encoding="utf-8")
    (game / "Images" / "a.jpg").write_bytes(b"\xff\xd8" + b"x" * 200)
    for relative, content in (extra or {}).items():
        target = game / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return game


class ManifestDrivenSelectionTests(SimpleTestCase):
    """Only what the manifest declares is bundled."""

    def test_a_minimal_game_bundles_its_package_story_and_declared_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = select_bundle_contents(_make_game(Path(tmp)))
            self.assertEqual(
                sorted(str(p) for p in plan.included),
                ["Images/a.jpg", "__init__.py", "manifest.yaml", "story.inkj"],
            )

    def test_undeclared_media_is_not_bundled(self):
        """A directory nothing declares stays out, however large."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"Unlisted/big.jpg": "x"})
            self.assertNotIn(Path("Unlisted/big.jpg"), select_bundle_contents(game).included)

    def test_uncompiled_source_and_build_intermediates_never_ship(self):
        """Nothing declares them, so no exclusion rule is needed."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(
                Path(tmp),
                extra={
                    "story.ink": "-> DONE",
                    "story.ink.json": STORY_JSON,
                    "chapter_one.inkj": STORY_JSON,
                    "tests/test_game.py": "",
                    "docs/design.md": "",
                },
            )
            included = {str(p) for p in select_bundle_contents(game).included}
            self.assertEqual(
                included & {"story.ink", "story.ink.json", "chapter_one.inkj", "docs/design.md"},
                set(),
            )

    def test_every_sibling_python_module_ships(self):
        """The package's modules import each other, and `sidebar.py` is
        imported lazily by an application -- so reachability would wrongly drop it."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"sidebar.py": "", "skills.py": ""})
            included = {str(p) for p in select_bundle_contents(game).included}
            self.assertLessEqual({"__init__.py", "sidebar.py", "skills.py"}, included)

    def test_a_python_module_under_tests_does_not_ship(self):
        """Only the package's own top-level modules are the game package."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"tests/test_game.py": ""})
            self.assertNotIn(Path("tests/test_game.py"), select_bundle_contents(game).included)

    def test_several_media_directories_are_each_bundled_whole(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(
                Path(tmp),
                manifest="MAIN_STORY_FILE: story.inkj\nMEDIA_DIRECTORIES: [Images, UI]\n",
                extra={"UI/button.png": "x", "UI/nested/icon.png": "x"},
            )
            included = {str(p) for p in select_bundle_contents(game).included}
            self.assertLessEqual({"Images/a.jpg", "UI/button.png", "UI/nested/icon.png"}, included)

    def test_extra_files_are_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(
                Path(tmp),
                manifest="MAIN_STORY_FILE: story.inkj\nEXTRA_FILES: [styles.css]\n",
                extra={"styles.css": "p{}"},
            )
            self.assertIn(Path("styles.css"), select_bundle_contents(game).included)

    def test_junk_inside_a_declared_directory_is_skipped(self):
        """OS droppings and caches appear at every level of a media tree."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"Images/.DS_Store": "", "Images/__pycache__/x.pyc": ""})
            included = {str(p) for p in select_bundle_contents(game).included}
            self.assertEqual(included & {"Images/.DS_Store", "Images/__pycache__/x.pyc"}, set())

    def test_macos_sidecar_files_are_skipped(self):
        """Copying a game to a non-native filesystem leaves an AppleDouble
        sidecar beside every real file, and a `__MACOSX` tree holding
        more. Both carry Finder metadata, never game content."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(
                Path(tmp),
                extra={
                    "Images/._cover.png": "",
                    "Images/cover.png": "",
                    "__MACOSX/Images/._cover.png": "",
                },
            )
            included = {str(p) for p in select_bundle_contents(game).included}

            self.assertIn("Images/cover.png", included)
            self.assertEqual(included & {"Images/._cover.png", "__MACOSX/Images/._cover.png"}, set())

    def test_a_sidecar_beside_a_module_is_not_bundled_as_one(self):
        """`*.py` also matches `._sidebar.py`, which would otherwise ship
        inside the game's own importable package."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"sidebar.py": "", "._sidebar.py": ""})
            included = {str(p) for p in select_bundle_contents(game).included}

            self.assertIn("sidebar.py", included)
            self.assertNotIn("._sidebar.py", included)

    def test_each_included_file_records_the_declaration_that_brought_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = select_bundle_contents(_make_game(Path(tmp)))
            self.assertEqual(plan.included[Path("story.inkj")], "MAIN_STORY_FILE")
            self.assertEqual(plan.included[Path("__init__.py")], "game package")
            self.assertEqual(plan.included[Path("Images/a.jpg")], "MEDIA_DIRECTORIES: Images")

    def test_the_package_name_defaults_to_the_folder_name_and_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            self.assertEqual(select_bundle_contents(game).package_name, "mygame")
            self.assertEqual(select_bundle_contents(game, package_name="other").package_name, "other")

    def test_a_missing_folder_is_a_real_error(self):
        with self.assertRaises(BundleError):
            select_bundle_contents(Path("/nonexistent/game"))


class MissingDeclarationTests(SimpleTestCase):
    """A manifest naming something absent is the failure mode this design
    has, so it must be reported rather than silently dropped."""

    def test_a_declared_media_directory_that_does_not_exist_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="MAIN_STORY_FILE: story.inkj\nMEDIA_DIRECTORIES: [Absent]\n")
            self.assertTrue(any("Absent" in p for p in verify_plan(select_bundle_contents(game))))

    def test_a_declared_extra_file_that_does_not_exist_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="MAIN_STORY_FILE: story.inkj\nEXTRA_FILES: [gone.png]\n")
            self.assertTrue(any("gone.png" in p for p in verify_plan(select_bundle_contents(game))))

    def test_a_manifest_naming_a_missing_story_is_caught(self):
        """This failure would otherwise surface on the player's machine."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="MAIN_STORY_FILE: absent.inkj\n")
            self.assertTrue(any("absent.inkj" in p for p in verify_plan(select_bundle_contents(game))))

    def test_a_declared_path_outside_the_game_folder_is_refused(self):
        """A manifest is game-supplied content, so an escaping path is
        refused rather than followed."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest='MAIN_STORY_FILE: story.inkj\nEXTRA_FILES: ["../../etc/passwd"]\n')
            plan = select_bundle_contents(game)
            self.assertTrue(any("outside the game folder" in reason for _, reason in plan.missing))

    def test_a_complete_manifest_has_no_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(verify_plan(select_bundle_contents(_make_game(Path(tmp)))), [])

    def test_a_game_shipping_python_needs_the_package_marker(self):
        """A game with a module of its own must import, or its plugins and
        sidebar cannot load."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"sidebar.py": "x = 1\n"})
            (game / "__init__.py").unlink()
            problems = verify_plan(select_bundle_contents(game))
            self.assertTrue(any("__init__.py" in p for p in problems), problems)

    def test_a_game_declaring_plugins_needs_the_package_marker(self):
        """REQUIRED_PLUGINS says a module will be imported from the bundle,
        so the marker is needed even before one is written."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest=DEFAULT_MANIFEST + "REQUIRED_PLUGINS: [my_plugin]\n")
            (game / "__init__.py").unlink()
            problems = verify_plan(select_bundle_contents(game))
            self.assertTrue(any("__init__.py" in p for p in problems), problems)

    def test_a_story_only_game_does_not_need_the_package_marker(self):
        """A game that is a story and its media imports nothing, so
        requiring a marker would demand a file it has no use for."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            (game / "__init__.py").unlink()
            self.assertEqual(verify_plan(select_bundle_contents(game)), [])

    def test_a_directory_named_like_the_marker_does_not_satisfy_it(self):
        """`glob` matches a directory too; one cannot be imported."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"sidebar.py": "x = 1\n"})
            (game / "__init__.py").unlink()
            (game / "__init__.py").mkdir()
            problems = verify_plan(select_bundle_contents(game))
            self.assertTrue(any("__init__.py" in p for p in problems), problems)

    def test_a_bundle_with_no_manifest_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            (game / "manifest.yaml").unlink()
            self.assertTrue(any("manifest.yaml" in p for p in verify_plan(select_bundle_contents(game))))

    def test_a_manifest_declaring_no_story_is_caught(self):
        """Nothing is inferred from what the folder happens to contain: a
        game that does not name its story has not said which one plays."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="GAME_TITLE: x\n")
            problems = verify_plan(select_bundle_contents(game))
            self.assertTrue(any("MAIN_STORY_FILE" in problem for problem in problems), problems)


class StaleSourceTests(SimpleTestCase):
    """A story compiled before its most recent source edit ships the OLD
    content, and nothing at play time reveals it."""

    def _age(self, path: Path, *, newer: bool) -> None:
        """Set one file's mtime relative to now."""
        when = time.time() + (60 if newer else -60)
        os.utime(path, (when, when))

    def test_a_source_newer_than_the_story_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"story.ink": "-> DONE"})
            self._age(game / "story.ink", newer=True)
            self.assertEqual([p.name for p in stale_sources(game, "story.inkj")], ["story.ink"])

    def test_a_story_newer_than_every_source_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"story.ink": "-> DONE"})
            self._age(game / "story.ink", newer=False)
            self.assertEqual(stale_sources(game, "story.inkj"), [])

    def test_a_game_with_no_ink_sources_is_never_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(stale_sources(_make_game(Path(tmp)), "story.inkj"), [])

    def test_sources_are_reported_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"old.ink": "", "new.ink": ""})
            self._age(game / "old.ink", newer=True)
            os.utime(game / "new.ink", (time.time() + 120, time.time() + 120))
            self.assertEqual([p.name for p in stale_sources(game, "story.inkj")], ["new.ink", "old.ink"])

    def test_a_missing_story_reports_nothing_rather_than_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(stale_sources(_make_game(Path(tmp)), "absent.inkj"), [])

    def test_build_refuses_a_stale_story_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"story.ink": "-> DONE"})
            self._age(game / "story.ink", newer=True)
            out = Path(tmp) / "out.zip"
            self.assertEqual(main(["build", str(game), "-o", str(out), "--quiet"]), 1)
            self.assertFalse(out.exists())

    def test_allow_stale_builds_anyway(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"story.ink": "-> DONE"})
            self._age(game / "story.ink", newer=True)
            out = Path(tmp) / "out.zip"
            self.assertEqual(main(["build", str(game), "-o", str(out), "--quiet", "--allow-stale"]), 0)
            self.assertTrue(out.exists())

    def test_inspect_reports_a_nonzero_status_for_a_stale_story(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), extra={"story.ink": "-> DONE"})
            self._age(game / "story.ink", newer=True)
            self.assertEqual(main(["inspect", str(game)]), 1)


class BuildBundleTests(SimpleTestCase):
    def test_every_entry_lives_under_the_package_directory(self):
        """An application puts the bundle on sys.path and imports the package, so
        a flat archive would not be importable."""
        with tempfile.TemporaryDirectory() as tmp:
            plan = select_bundle_contents(_make_game(Path(tmp)))
            out = build_bundle(plan, Path(tmp) / "out" / "mygame.zip")
            with zipfile.ZipFile(out) as archive:
                names = archive.namelist()
            self.assertTrue(all(name.startswith("mygame/") for name in names), names)

    def test_media_is_stored_and_text_is_deflated(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = select_bundle_contents(_make_game(Path(tmp)))
            out = build_bundle(plan, Path(tmp) / "out.zip")
            with zipfile.ZipFile(out) as archive:
                self.assertEqual(archive.getinfo("mygame/Images/a.jpg").compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.getinfo("mygame/story.inkj").compress_type, zipfile.ZIP_DEFLATED)

    def test_an_unplayable_plan_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="MAIN_STORY_FILE: absent.inkj\n")
            out = Path(tmp) / "out.zip"
            with self.assertRaises(BundleError):
                build_bundle(select_bundle_contents(game), out)
            self.assertFalse(out.exists())

    def test_writing_into_the_game_folder_is_refused(self):
        """Writing into the folder being walked would race the walk and,
        on a rebuild, try to bundle the previous bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            with self.assertRaises(BundleError):
                build_bundle(select_bundle_contents(game), game / "self.zip")

    def test_progress_is_reported_once_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = select_bundle_contents(_make_game(Path(tmp)))
            seen: list[Path] = []
            build_bundle(plan, Path(tmp) / "out.zip", progress=seen.append)
            self.assertEqual(sorted(seen), sorted(plan.included))


class ReadBackTests(SimpleTestCase):
    """A built bundle must be readable the way an application reads it."""

    def _build(self, tmp: str) -> Path:
        manifest = "MAIN_STORY_FILE: story.inkj\nGAME_TITLE: Demo\nREQUIRED_PLUGINS: [a, b]\nMEDIA_DIRECTORIES: [Images]\n"
        plan = select_bundle_contents(_make_game(Path(tmp), manifest=manifest))
        return build_bundle(plan, Path(tmp) / "out.zip")

    def test_the_manifest_reads_back_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = open_bundle_manifest(self._build(tmp))
            self.assertEqual(manifest["GAME_TITLE"], "Demo")
            self.assertEqual(manifest["REQUIRED_PLUGINS"], ["a", "b"])
            self.assertEqual(manifest["MEDIA_DIRECTORIES"], ["Images"])

    def test_the_story_reads_back_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(self._build(tmp)) as archive:
                story = json.loads(archive.read("mygame/story.inkj"))
            self.assertEqual(story["inkVersion"], 21)


class CommandLineTests(SimpleTestCase):
    def test_inspect_reports_success_for_a_good_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["inspect", str(_make_game(Path(tmp)))]), 0)

    def test_inspect_reports_failure_for_a_broken_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp), manifest="MAIN_STORY_FILE: absent.inkj\n")
            self.assertEqual(main(["inspect", str(game)]), 1)

    def test_build_then_verify_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            out = Path(tmp) / "built.zip"
            self.assertEqual(main(["build", str(game), "-o", str(out), "--quiet"]), 0)
            self.assertEqual(main(["verify", str(out)]), 0)

    def test_verify_reports_a_missing_bundle(self):
        self.assertEqual(main(["verify", "/nonexistent/bundle.zip"]), 1)

    def test_a_bundle_error_is_reported_not_raised(self):
        self.assertEqual(main(["inspect", "/nonexistent/game"]), 1)


class PackageMarkerOfferTests(SimpleTestCase):
    """`build` offers to create the `__init__.py` a game needs."""

    def _game_shipping_python(self, root: Path) -> Path:
        game = _make_game(root, extra={"sidebar.py": "x = 1\n"})
        (game / "__init__.py").unlink()
        return game

    def test_the_flag_creates_the_marker_and_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = self._game_shipping_python(Path(tmp))
            out = Path(tmp) / "built.zip"
            status = main(["build", str(game), "-o", str(out), "-q", "--create-package-marker"])
            self.assertEqual(status, 0)
            self.assertTrue((game / "__init__.py").is_file())
            self.assertEqual((game / "__init__.py").read_text(encoding="utf-8"), "")

    def test_the_created_marker_is_in_the_bundle(self):
        """The plan is rebuilt after creating it, or the file exists on
        disk but never reaches the bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            game = self._game_shipping_python(Path(tmp))
            out = Path(tmp) / "built.zip"
            main(["build", str(game), "-o", str(out), "-q", "--create-package-marker"])
            with zipfile.ZipFile(out) as archive:
                self.assertIn(f"{game.name}/__init__.py", archive.namelist())

    def test_a_story_only_game_is_never_offered_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = _make_game(Path(tmp))
            (game / "__init__.py").unlink()
            out = Path(tmp) / "built.zip"
            self.assertEqual(main(["build", str(game), "-o", str(out), "-q"]), 0)
            self.assertFalse((game / "__init__.py").exists())

    def test_a_directory_in_the_way_is_refused_rather_than_written_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            game = self._game_shipping_python(Path(tmp))
            (game / "__init__.py").mkdir()
            out = Path(tmp) / "built.zip"
            status = main(["build", str(game), "-o", str(out), "-q", "--create-package-marker"])
            self.assertEqual(status, 1)
            self.assertTrue((game / "__init__.py").is_dir())
            self.assertFalse(out.exists())
