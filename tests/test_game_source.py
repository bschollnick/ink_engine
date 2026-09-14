"""GameSource: a directory and a bundle answering identically."""

from __future__ import annotations

import base64
import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

from ink_engine.game_folder import find_main_story_file, read_manifest
from ink_engine.game_source import (
    DirectoryGameSource,
    GameSource,
    GameSourceError,
    ZipGameSource,
    normalise,
)
from ink_engine.media_resolver import FilesystemMediaResolver

FILES = {
    "manifest.yaml": b"MAIN_STORY_FILE: story.inkj\n",
    "__init__.py": b"",
    "story.inkj": b'{"inkVersion": 21}',
    "images/cover.png": b"\x89PNG" + b"x" * 40,
    "images/rooms/hall.jpg": b"\xff\xd8" + b"y" * 40,
}


class GameSourceTestCase(TestCase):
    """Builds the same game as a directory and as a bundle."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        game = self.tmp / "mygame"
        for relative, content in FILES.items():
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.directory = DirectoryGameSource(game)

        bundle = self.tmp / "mygame.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            for relative, content in FILES.items():
                archive.writestr(f"mygame/{relative}", content)
        self.bundle = ZipGameSource(bundle)
        self.addCleanup(self.bundle.close)

    @property
    def both(self):
        return (("directory", self.directory), ("bundle", self.bundle))


class ProtocolTests(GameSourceTestCase):
    def test_both_satisfy_the_protocol(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertIsInstance(source, GameSource)


class ParityTests(GameSourceTestCase):
    """The point of the protocol: the same question, the same answer."""

    def test_exists_agrees(self):
        for probe in ("manifest.yaml", "images/cover.png", "images/rooms/hall.jpg", "absent.txt"):
            with self.subTest(probe):
                self.assertEqual(self.directory.exists(probe), self.bundle.exists(probe))

    def test_read_bytes_agrees(self):
        for relative in FILES:
            with self.subTest(relative):
                self.assertEqual(self.directory.read_bytes(relative), self.bundle.read_bytes(relative))

    def test_read_text_agrees(self):
        self.assertEqual(self.directory.read_text("manifest.yaml"), self.bundle.read_text("manifest.yaml"))

    def test_iter_names_agrees(self):
        self.assertEqual(sorted(self.directory.iter_names()), sorted(self.bundle.iter_names()))

    def test_iter_names_under_a_prefix_agrees(self):
        self.assertEqual(sorted(self.directory.iter_names("images")), sorted(self.bundle.iter_names("images")))

    def test_a_missing_file_raises_in_both(self):
        for label, source in self.both:
            with self.subTest(label), self.assertRaises(GameSourceError):
                source.read_bytes("absent.txt")


class PathSafetyTests(GameSourceTestCase):
    """A manifest is game-supplied content, so a path may not escape."""

    def test_an_escaping_path_is_refused_by_both(self):
        for probe in ("../secrets.txt", "../../etc/passwd", "/etc/passwd"):
            for label, source in self.both:
                with self.subTest(f"{label}:{probe}"), self.assertRaises(GameSourceError):
                    source.read_text(probe)

    def test_an_escaping_path_does_not_exist_rather_than_raising(self):
        """`exists()` answers a question; it should not blow up on a bad
        path, only report that nothing is there."""
        for label, source in self.both:
            with self.subTest(label):
                self.assertFalse(source.exists("../secrets.txt"))

    def test_a_path_may_traverse_within_the_game(self):
        """`images/../story.inkj` stays inside, so it resolves."""
        for label, source in self.both:
            with self.subTest(label):
                self.assertTrue(source.exists("images/../story.inkj"))

    def test_normalise_accepts_windows_separators(self):
        self.assertEqual(normalise("images\\cover.png"), "images/cover.png")


class FingerprintTests(GameSourceTestCase):
    def test_an_absent_file_fingerprints_zero(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertEqual(source.fingerprint("absent.txt"), 0)

    def test_a_present_file_fingerprints_non_zero(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertNotEqual(source.fingerprint("manifest.yaml"), 0)

    def test_a_directory_fingerprint_changes_when_the_file_changes(self):
        """This is what keeps an edited manifest visible mid-session."""
        before = self.directory.fingerprint("manifest.yaml")
        (self.directory.root / "manifest.yaml").write_text("GAME_TITLE: New\n", encoding="utf-8")
        self.assertNotEqual(self.directory.fingerprint("manifest.yaml"), before)


class ZipSpecificTests(GameSourceTestCase):
    def test_the_package_directory_is_stripped(self):
        """A caller asks for game-relative paths, never the package name."""
        self.assertEqual(self.bundle.package, "mygame")
        self.assertTrue(self.bundle.exists("story.inkj"))
        self.assertFalse(self.bundle.exists("mygame/story.inkj"))

    def test_a_bundle_with_several_package_directories_is_refused(self):
        target = self.tmp / "two.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("one/manifest.yaml", "")
            archive.writestr("two/manifest.yaml", "")
        with self.assertRaises(GameSourceError):
            ZipGameSource(target)

    def test_a_file_that_is_not_an_archive_is_refused(self):
        target = self.tmp / "not.zip"
        target.write_bytes(b"this is not a zip")
        with self.assertRaises(GameSourceError):
            ZipGameSource(target)


class TopLevelScanTests(GameSourceTestCase):
    """Resolving the story must not walk the game's media.

    A game ships its media inside itself, so answering a question about
    the game's root by recursing reads every media file's directory
    entry — measured at 8.2 seconds against 6 ms on a real 14,000-file
    game.
    """

    def setUp(self):
        super().setUp()
        deep = self.directory.root / "images" / "rooms" / "deep"
        deep.mkdir(parents=True, exist_ok=True)
        (deep / "buried.inkj").write_bytes(b"{}")

    def test_a_nested_inkj_is_not_mistaken_for_the_story(self):
        """Only top-level files are candidates; the buried one must not
        make the game look ambiguous."""
        self.assertEqual(find_main_story_file(self.directory), "story.inkj")

    def test_iter_names_non_recursive_stays_at_one_level(self):
        for label, source in self.both:
            with self.subTest(label):
                names = list(source.iter_names(recursive=False))
                self.assertIn("story.inkj", names)
                self.assertNotIn("images/cover.png", names)

    def test_iter_names_recursive_still_reaches_everything(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertIn("images/cover.png", list(source.iter_names()))

    def test_resolving_the_story_does_not_read_the_media_tree(self):
        """The regression guard: count what the walk touches."""
        walked: list[str] = []
        original = DirectoryGameSource.iter_names

        def counting(self, prefix="", *, recursive=True):
            for name in original(self, prefix, recursive=recursive):
                walked.append(name)
                yield name

        DirectoryGameSource.iter_names = counting
        try:
            find_main_story_file(self.directory)
        finally:
            DirectoryGameSource.iter_names = original
        self.assertNotIn("images/cover.png", walked)


class ReaderParityTests(GameSourceTestCase):
    """The engine's own readers, driven from either source."""

    def test_find_main_story_file_agrees(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertEqual(find_main_story_file(source), "story.inkj")

    def test_read_manifest_agrees(self):
        self.assertEqual(read_manifest(self.directory), read_manifest(self.bundle))

    def test_a_path_is_still_accepted(self):
        """Every existing caller passes a directory path; that must keep
        working without being wrapped by hand."""
        self.assertEqual(read_manifest(self.directory.root), read_manifest(self.directory))


class MediaReferenceTests(GameSourceTestCase):
    """What a resolver returns differs by source, because it must: a
    bundle has no filesystem path to hand out."""

    def _resolve(self, source, tag="images/cover.png"):
        return FilesystemMediaResolver(source).resolve([("image", tag)])

    def test_a_directory_yields_an_absolute_path(self):
        resolved = self._resolve(self.directory)
        self.assertEqual(len(resolved), 1)
        self.assertTrue(Path(resolved[0]).is_absolute())

    def test_a_bundle_yields_a_data_uri_a_browser_can_load(self):
        resolved = self._resolve(self.bundle)
        self.assertEqual(len(resolved), 1)
        self.assertTrue(resolved[0].startswith("data:image/png;base64,"))

    def test_the_data_uri_carries_the_real_bytes(self):
        payload = self._resolve(self.bundle)[0].split(",", 1)[1]
        self.assertEqual(base64.b64decode(payload), FILES["images/cover.png"])

    def test_both_agree_on_whether_a_tag_resolves_at_all(self):
        for tag, expected in (("images/cover.png", 1), ("images/absent.png", 0)):
            with self.subTest(tag):
                self.assertEqual(len(self._resolve(self.directory, tag)), expected)
                self.assertEqual(len(self._resolve(self.bundle, tag)), expected)

    def test_an_extensionless_tag_resolves_through_the_fallbacks_from_both(self):
        """`images/cover` must find `cover.png` either way."""
        for label, source in self.both:
            with self.subTest(label):
                self.assertEqual(len(self._resolve(source, "images/cover")), 1)


class ListingCacheTests(GameSourceTestCase):
    """Scratch space a game's own media resolver indexes its files in.

    Held here rather than in the resolver's module so its lifetime is the
    game's: a module-level dict keyed by `id(source)` reads a freed game's
    listings back for whichever game next reuses that id.
    """

    def test_both_offer_one(self):
        for label, source in self.both:
            with self.subTest(label):
                self.assertEqual(source.listing_cache, {})

    def test_it_is_writable(self):
        for label, source in self.both:
            with self.subTest(label):
                source.listing_cache["x"] = {"a": 1}
                self.assertEqual(source.listing_cache["x"], {"a": 1})

    def test_two_sources_never_share_one(self):
        """The defect this replaces: two games, one cache."""
        self.directory.listing_cache["files"] = {"only": "in the first"}
        second = DirectoryGameSource(self.tmp / "game")
        self.assertEqual(second.listing_cache, {})
