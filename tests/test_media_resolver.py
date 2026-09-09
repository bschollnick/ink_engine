"""The shared media-tag parser and the filesystem-backed resolver.

A host with its own database-indexed resolver (not path-direct) covers
that resolver separately in its own test suite, since it necessarily
imports that host's own framework — nothing here needs a database or
any host framework at all.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest import TestCase

from ink_engine.media_resolver import (
    FilesystemMediaResolver,
    find_cover_image,
    find_prose_styles,
    parse_media_tags,
)


class ParseMediaTagsTests(TestCase):
    """The shared tag parser -- pure text processing, no host knowledge."""

    def test_an_image_tag_is_recognised(self):
        self.assertEqual(parse_media_tags(["image: foo.jpg"]), [("image", "foo.jpg")])

    def test_a_video_tag_is_recognised(self):
        self.assertEqual(parse_media_tags(["video: bar.mp4"]), [("video", "bar.mp4")])

    def test_whitespace_around_the_tag_name_is_stripped(self):
        self.assertEqual(parse_media_tags(["image:   foo.jpg  "]), [("image", "foo.jpg")])

    def test_the_prefix_match_is_case_insensitive(self):
        self.assertEqual(parse_media_tags(["IMAGE: foo.jpg", "Video: bar.mp4"]), [("image", "foo.jpg"), ("video", "bar.mp4")])

    def test_the_tag_names_own_case_is_preserved(self):
        """Only the PREFIX comparison lowercases -- the tag name itself,
        a real relative path a filesystem resolver checks verbatim, is
        returned exactly as written."""
        self.assertEqual(parse_media_tags(["image: FooBar.jpg"]), [("image", "FooBar.jpg")])

    def test_a_non_media_tag_is_ignored(self):
        self.assertEqual(parse_media_tags(["some_other_tag"]), [])

    def test_encounter_order_is_preserved_even_when_interleaved(self):
        self.assertEqual(
            parse_media_tags(["video: b.mp4", "image: a.jpg", "unrelated", "video: c.mp4"]),
            [("video", "b.mp4"), ("image", "a.jpg"), ("video", "c.mp4")],
        )

    def test_an_empty_tag_list_returns_empty(self):
        self.assertEqual(parse_media_tags([]), [])

    def test_a_prefix_with_no_leading_space_still_matches(self):
        self.assertEqual(parse_media_tags(["image:foo.jpg"]), [("image", "foo.jpg")])

    def test_a_tag_with_a_subdirectory_path_is_preserved_verbatim(self):
        """The whole point of the direct-path design: the tag's own
        subdirectory structure -- wherever the game author chose to put
        the file -- is not flattened or reinterpreted here."""
        self.assertEqual(parse_media_tags(["image: church/church_front.jpg"]), [("image", "church/church_front.jpg")])


class FilesystemMediaResolverTests(TestCase):
    """Direct tag-as-relative-path resolution: no lookup table, no
    upfront scan, no filename-stem matching, and NO directory convention
    of the resolver's own imposed on the game (no images/ or video/
    split) -- the tag names a file's own real path relative to the game
    folder's own root, exactly as the game author wrote it, checked for
    existence. See media_resolver.py's own module docstring for why this
    must NOT resemble a database-indexed resolver."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str) -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def test_a_tag_with_its_own_extension_resolves_directly(self):
        path = self._write("foo.jpg")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "foo.jpg")]), [str(path.resolve())])

    def test_a_tag_naming_a_subdirectory_path_resolves_there(self):
        """The real, existing tag shape: `image: church/church_front.jpg`
        must resolve to `<game_dir>/church/church_front.jpg` -- the game's
        own chosen layout, not any convention this resolver invents."""
        path = self._write("church/church_front.jpg")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "church/church_front.jpg")]), [str(path.resolve())])

    def test_the_resolver_imposes_no_directory_convention_of_its_own(self):
        """A game may organize its files however it likes -- an
        images/ subdirectory, a flat layout, or anything else -- as long
        as the tag names the real path. Nothing here requires a specific
        top-level directory name."""
        path = self._write("assets/pictures/whatever/foo.jpg")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "assets/pictures/whatever/foo.jpg")]), [str(path.resolve())])

    def test_video_and_image_tags_share_the_same_addressing_no_kind_based_directory(self):
        """The resolver does not route "video:" tags into a separate
        base directory -- a video tag naming a path under the SAME tree
        an image tag uses resolves exactly as written, same as any
        other tag."""
        path = self._write("scenes/intro.mp4")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("video", "scenes/intro.mp4")]), [str(path.resolve())])

    def test_no_casefold_normalization_happens_in_this_resolver(self):
        """This resolver does no case manipulation of its own anywhere --
        whether `foo.jpg` matches `Foo.jpg` is entirely up to the
        underlying filesystem's own case sensitivity (case-insensitive on
        the usual macOS/Windows setup, case-sensitive on Linux), not
        something this class decides. Proven here by checking the exact
        case DOES resolve -- the one outcome true on every filesystem."""
        path = self._write("Foo.jpg")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "Foo.jpg")]), [str(path.resolve())])

    def test_a_tag_with_no_extension_tries_the_fallback_list(self):
        path = self._write("foo.png")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "foo")]), [str(path.resolve())])

    def test_a_tag_with_the_wrong_extension_does_not_fall_back_to_another(self):
        """The tag already committed to an extension -- .jpg not existing
        must not silently try .png instead, or a tag naming the wrong
        format could resolve to a DIFFERENT real file than intended."""
        self._write("foo.png")
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "foo.jpg")]), [])

    def test_an_unresolvable_tag_is_silently_dropped(self):
        """A work-in-progress story with placeholder tags plays text-only
        rather than erroring."""
        resolver = FilesystemMediaResolver(self.tmp)
        self.assertEqual(resolver.resolve([("image", "nonexistent.jpg")]), [])

    def test_a_missing_game_directory_is_not_an_error(self):
        empty_dir = self.tmp / "no_files_here"
        empty_dir.mkdir()
        resolver = FilesystemMediaResolver(empty_dir)
        self.assertEqual(resolver.resolve([("image", "foo.jpg")]), [])

    def test_results_are_grouped_by_kind_not_request_order(self):
        """All images first, then all videos -- even if the requests list
        interleaves them, matching the DB-indexed resolver's own existing
        (implemented, not just documented) behavior."""
        a = self._write("a.jpg")
        b = self._write("b.mp4")
        c = self._write("c.jpg")
        resolver = FilesystemMediaResolver(self.tmp)
        result = resolver.resolve([("video", "b.mp4"), ("image", "a.jpg"), ("image", "c.jpg")])
        self.assertEqual(result, [str(a.resolve()), str(c.resolve()), str(b.resolve())])


class FindCoverImageTests(TestCase):
    """A game folder's own cover image -- fixed filename convention, no
    manifest field, no Ink tag."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write(self, relative_path: str) -> Path:
        path = self.tmp / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path

    def test_a_cover_at_the_game_root_is_found(self):
        path = self._write("cover.jpg")
        self.assertEqual(find_cover_image(self.tmp), str(path.resolve()))

    def test_a_cover_under_images_is_found_when_the_root_has_none(self):
        path = self._write("images/cover.png")
        self.assertEqual(find_cover_image(self.tmp), str(path.resolve()))

    def test_the_game_root_takes_priority_over_images(self):
        root_cover = self._write("cover.jpg")
        self._write("images/cover.png")
        self.assertEqual(find_cover_image(self.tmp), str(root_cover.resolve()))

    def test_no_cover_anywhere_returns_none(self):
        self.assertIsNone(find_cover_image(self.tmp))

    def test_a_missing_images_directory_is_not_an_error(self):
        self.assertIsNone(find_cover_image(self.tmp))

    def test_video_extensions_are_never_tried_for_a_cover(self):
        """A cover is always a still image -- a stray cover.mp4 must not
        be picked up as if it were a valid cover."""
        self._write("cover.mp4")
        self.assertIsNone(find_cover_image(self.tmp))


class FindProseStylesTests(TestCase):
    """A game folder's own optional prose-styling CSS -- fixed filename
    convention, no manifest field, no Ink tag."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_styles_css_at_the_game_root_is_returned_verbatim(self):
        content = ".style-computer { font-family: monospace; }"
        (self.tmp / "styles.css").write_text(content, encoding="utf-8")
        self.assertEqual(find_prose_styles(self.tmp), content)

    def test_no_styles_css_returns_none(self):
        self.assertIsNone(find_prose_styles(self.tmp))
