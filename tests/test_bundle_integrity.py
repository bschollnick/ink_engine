"""Bundle tamper evidence: the three hashes and the companion readme."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase

import yaml

from ink_engine.bundle_integrity import (
    BUNDLE_DIRECTORY_SHA256_FIELD,
    BUNDLE_VERSION,
    STORY_SHA256_FIELD,
    directory_hash,
    hash_bytes,
    read_comment_hash,
    read_bundle_version,
    recorded_hashes,
    unrecognized_bundle_version,
    verify_bundle,
)
from ink_engine.bundle_readme import render_readme
from ink_engine.game_source import GameSourceError
from ink_engine.bundler import build_bundle, select_bundle_contents

MANIFEST = "MAIN_STORY_FILE: story.inkj\nGAME_TITLE: Demo\nMEDIA_DIRECTORIES: [Images]\n# an author's comment\n"


class BundleIntegrityTestCase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        game = self.tmp / "mygame"
        (game / "Images").mkdir(parents=True)
        (game / "manifest.yaml").write_text(MANIFEST, encoding="utf-8")
        (game / "__init__.py").write_text("", encoding="utf-8")
        (game / "story.inkj").write_text('{"inkVersion": 21}', encoding="utf-8")
        (game / "plugins.py").write_text("SAFE = True\n", encoding="utf-8")
        (game / "Images" / "a.jpg").write_bytes(b"\xff\xd8" + b"x" * 200)
        self.game = game
        self.bundle = build_bundle(select_bundle_contents(game), self.tmp / "out.zip")

    def _rebuild_with(self, entry: str, data: bytes) -> Path:
        """Copy the bundle, replacing one entry — an attacker who edits in
        place but cannot recompute the comment."""
        target = self.tmp / "tampered.zip"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(target, "w") as copy:
            copy.comment = source.comment
            for info in source.infolist():
                copy.writestr(info.filename, data if info.filename == entry else source.read(info.filename))
        return target


class RecordedHashTests(BundleIntegrityTestCase):
    def test_a_freshly_built_bundle_verifies(self):
        self.assertEqual(verify_bundle(self.bundle), [])

    def test_the_manifest_gains_both_hash_fields(self):
        with zipfile.ZipFile(self.bundle) as archive:
            manifest = yaml.safe_load(archive.read("mygame/manifest.yaml"))
        self.assertEqual(len(manifest[STORY_SHA256_FIELD]), 64)
        self.assertEqual(len(manifest[BUNDLE_DIRECTORY_SHA256_FIELD]), 64)

    def test_the_archive_comment_carries_the_manifest_hash(self):
        with zipfile.ZipFile(self.bundle) as archive:
            recorded = read_comment_hash(archive)
            self.assertEqual(recorded, hash_bytes(archive.read("mygame/manifest.yaml")))

    def test_the_authors_own_comments_survive(self):
        """The hashes are appended as text, never round-tripped through a
        YAML dump — a dump would discard every comment in the file."""
        with zipfile.ZipFile(self.bundle) as archive:
            manifest = archive.read("mygame/manifest.yaml").decode("utf-8")
        self.assertIn("# an author's comment", manifest)

    def test_the_story_hash_is_the_story_files_own(self):
        with zipfile.ZipFile(self.bundle) as archive:
            manifest = yaml.safe_load(archive.read("mygame/manifest.yaml"))
            self.assertEqual(manifest[STORY_SHA256_FIELD], hash_bytes(archive.read("mygame/story.inkj")))


class RecordedHashReaderTests(BundleIntegrityTestCase):
    """`recorded_hashes()` reports what a bundle claims about itself, for
    an application to store and compare against later."""

    def test_it_returns_all_three_digests(self):
        hashes = recorded_hashes(self.bundle)
        self.assertEqual(set(hashes), {"manifest", "directory", "story"})
        for value in hashes.values():
            self.assertEqual(len(value), 64)

    def test_they_are_the_hashes_the_bundle_actually_records(self):
        hashes = recorded_hashes(self.bundle)
        with zipfile.ZipFile(self.bundle) as archive:
            manifest_bytes = archive.read("mygame/manifest.yaml")
            manifest = yaml.safe_load(manifest_bytes)
            self.assertEqual(hashes["manifest"], hash_bytes(manifest_bytes))
            self.assertEqual(hashes["story"], manifest[STORY_SHA256_FIELD])
            self.assertEqual(hashes["directory"], manifest[BUNDLE_DIRECTORY_SHA256_FIELD])

    def test_it_reports_what_a_tampered_bundle_claims_not_what_it_is(self):
        """The reader is not a verifier: an edited bundle still reports
        its own stale claims, which is how an application detects the change."""
        tampered = self._rebuild_with("mygame/story.inkj", b'{"inkVersion": 99}')
        self.assertEqual(recorded_hashes(tampered)["story"], recorded_hashes(self.bundle)["story"])
        self.assertNotEqual(verify_bundle(tampered), [])

    def test_an_unreadable_file_raises(self):
        not_a_bundle = self.tmp / "broken.zip"
        not_a_bundle.write_bytes(b"not a zip at all")
        with self.assertRaises(GameSourceError):
            recorded_hashes(not_a_bundle)


class TamperDetectionTests(BundleIntegrityTestCase):
    """Each case the three hashes exist to catch."""

    def test_an_altered_plugin_is_detected(self):
        target = self._rebuild_with("mygame/plugins.py", b"EVIL = True\n")
        self.assertTrue(any(BUNDLE_DIRECTORY_SHA256_FIELD in p for p in verify_bundle(target)))

    def test_an_altered_story_is_detected(self):
        target = self._rebuild_with("mygame/story.inkj", b'{"inkVersion": 99}')
        self.assertTrue(verify_bundle(target))

    def test_an_altered_manifest_is_detected(self):
        """The one case the directory hash cannot catch, since it must
        exclude the manifest to avoid hashing itself."""
        target = self._rebuild_with("mygame/manifest.yaml", MANIFEST.encode("utf-8") + b"EXTRA: yes\n")
        self.assertTrue(any("archive comment" in p for p in verify_bundle(target)))

    def test_a_bundle_recording_no_hashes_does_not_pass_silently(self):
        target = self.tmp / "unsigned.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("mygame/manifest.yaml", MANIFEST)
            archive.writestr("mygame/story.inkj", "{}")
        self.assertTrue(verify_bundle(target))


class DirectoryHashTests(BundleIntegrityTestCase):
    def test_the_manifest_is_excluded_from_its_own_hash(self):
        """Including it would be self-referential: writing the hash into
        the manifest changes the entry the hash covers."""
        with zipfile.ZipFile(self.bundle) as archive:
            excluded = directory_hash(archive, manifest_name="mygame/manifest.yaml")
            included = directory_hash(archive, manifest_name="")
            manifest = yaml.safe_load(archive.read("mygame/manifest.yaml"))
        self.assertEqual(manifest[BUNDLE_DIRECTORY_SHA256_FIELD], excluded)
        self.assertNotEqual(excluded, included)

    def test_entry_order_does_not_change_the_hash(self):
        with zipfile.ZipFile(self.bundle) as source:
            names = source.namelist()
            reordered = self.tmp / "reordered.zip"
            with zipfile.ZipFile(reordered, "w") as copy:
                for name in reversed(names):
                    copy.writestr(name, source.read(name))
            original = directory_hash(source, manifest_name="mygame/manifest.yaml")
        with zipfile.ZipFile(reordered) as archive:
            self.assertEqual(directory_hash(archive, manifest_name="mygame/manifest.yaml"), original)


class CompanionReadmeTests(BundleIntegrityTestCase):
    def test_a_readme_is_written_beside_the_bundle(self):
        readme = self.bundle.with_suffix(".md")
        self.assertTrue(readme.is_file())

    def test_the_readme_is_not_inside_the_bundle(self):
        """It travels separately by design — an entry would be one more
        thing to hash, defeating the point of an out-of-band copy."""
        with zipfile.ZipFile(self.bundle) as archive:
            self.assertEqual([n for n in archive.namelist() if n.endswith(".md")], [])

    def test_the_readme_publishes_all_three_hashes(self):
        text = self.bundle.with_suffix(".md").read_text(encoding="utf-8")
        with zipfile.ZipFile(self.bundle) as archive:
            manifest_bytes = archive.read("mygame/manifest.yaml")
            manifest = yaml.safe_load(manifest_bytes)
        self.assertIn(manifest[STORY_SHA256_FIELD], text)
        self.assertIn(manifest[BUNDLE_DIRECTORY_SHA256_FIELD], text)
        self.assertIn(hash_bytes(manifest_bytes), text)

    def test_the_readme_names_the_game_and_its_bundle(self):
        text = self.bundle.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("# Demo", text)
        self.assertIn("out.zip", text)

    def test_rendering_is_pure_and_repeatable(self):
        """Nothing is hand-written and nothing varies per run, so the same
        inputs must produce byte-identical output — otherwise a rebuild of
        unchanged content would show a spurious diff."""
        arguments = {
            "bundle_name": "g.zip",
            "bundle_bytes": 1024,
            "file_count": 3,
            "story_sha256": "a" * 64,
            "directory_sha256": "b" * 64,
            "manifest_sha256": "c" * 64,
        }
        manifest = {"GAME_TITLE": "T", "MAIN_STORY_FILE": "s.inkj"}
        self.assertEqual(render_readme(manifest, **arguments), render_readme(manifest, **arguments))

    def test_a_minimal_manifest_still_renders(self):
        """Every descriptive field is optional; a game declaring none must
        not produce a broken readme."""
        text = render_readme(
            {},
            bundle_name="g.zip",
            bundle_bytes=10,
            file_count=1,
            story_sha256="",
            directory_sha256="d" * 64,
            manifest_sha256="e" * 64,
        )
        self.assertIn("# g", text)
        self.assertIn("d" * 64, text)


class ArchiveCommentTests(BundleIntegrityTestCase):
    """The comment carries the bundle's version and all three hashes.

    It makes a bundle self-describing: what it claims to be is readable
    from the End of Central Directory record alone, with no YAML parse
    and no entry reads. That is a CONVENIENCE -- the comment is inside
    the artifact, so anything that can rewrite the bundle can rewrite the
    comment in the same pass. `verify_bundle()` reads the manifest, which
    stays the authority.
    """

    def _comment_lines(self) -> dict[str, str]:
        with zipfile.ZipFile(self.bundle) as archive:
            return dict(line.split("=", 1) for line in archive.comment.decode().splitlines())

    def test_it_carries_all_three_hashes_and_the_version(self):
        fields = self._comment_lines()
        self.assertEqual(set(fields), {"bundle_version", "manifest_sha256", "story_sha256", "directory_sha256"})

    def test_the_hashes_match_the_ones_the_bundle_records(self):
        fields = self._comment_lines()
        recorded = recorded_hashes(self.bundle)
        self.assertEqual(fields["manifest_sha256"], recorded["manifest"])
        self.assertEqual(fields["story_sha256"], recorded["story"])
        self.assertEqual(fields["directory_sha256"], recorded["directory"])

    def test_the_declared_version_is_the_one_this_bundler_writes(self):
        with zipfile.ZipFile(self.bundle) as archive:
            self.assertEqual(read_bundle_version(archive), BUNDLE_VERSION)

    def test_a_bundle_of_this_version_raises_no_warning(self):
        self.assertIsNone(unrecognized_bundle_version(self.bundle))

    def test_an_unknown_version_is_reported_for_a_consumer_to_warn_on(self):
        """Warn, never refuse: the layout has stayed backward-compatible,
        and refusing a game over an unfamiliar container version would be
        a worse answer than opening it and saying so."""
        future = self.tmp / "future.zip"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(future, "w") as copy:
            copy.comment = source.comment.replace(f"bundle_version={BUNDLE_VERSION}".encode(), b"bundle_version=9.9")
            for info in source.infolist():
                copy.writestr(info.filename, source.read(info.filename))
        self.assertEqual(unrecognized_bundle_version(future), "9.9")

    def test_a_bundle_predating_versioning_raises_no_warning(self):
        """None means "built before the version existed", not "wrong"."""
        legacy = self.tmp / "legacy.zip"
        with zipfile.ZipFile(self.bundle) as source, zipfile.ZipFile(legacy, "w") as copy:
            copy.comment = b"manifest_sha256=" + recorded_hashes(self.bundle)["manifest"].encode()
            for info in source.infolist():
                copy.writestr(info.filename, source.read(info.filename))
        self.assertIsNone(unrecognized_bundle_version(legacy))
