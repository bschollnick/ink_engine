"""Tamper evidence for a bundle: three hashes, and how they fit together.

A bundle records what it should be, and every later read checks it still
is. Three values cover what the one before it cannot:

- `STORY_SHA256` — the compiled story alone. Answers "did the story
  change?", which is what decides save compatibility: adding a screenshot
  leaves it untouched.
- `BUNDLE_DIRECTORY_SHA256` — every archive entry's name, size and CRC,
  **excluding the manifest**. Answers "did anything change?".
- `manifest_sha256` — in the **archive comment**, outside the entries.
  Covers the manifest, which the directory hash cannot.

**Why the directory hash excludes the manifest.** The manifest is itself
an entry, so writing the hash into it changes that entry's size and CRC
and invalidates the value just written. Excluding it breaks the cycle,
and the archive comment — which lives in the End of Central Directory
record rather than in an entry — carries the manifest's own hash.

**What this proves, and what it does not.** It detects any modification
after a bundle was built. It does NOT prove a bundle is safe: an attacker
who rewrites an archive recomputes all three and produces something
self-consistent. Trust needs an out-of-band record (a application's trust store,
a published readme) saying which hash was approved.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any

import yaml

from ink_engine.game_folder import MANIFEST_FILENAME
from ink_engine.game_source import GameSourceError

#: Manifest field holding the compiled story's own SHA-256.
STORY_SHA256_FIELD = "STORY_SHA256"

#: Manifest field holding the archive directory's SHA-256.
BUNDLE_DIRECTORY_SHA256_FIELD = "BUNDLE_DIRECTORY_SHA256"

#: Prefixes of the archive-comment lines carrying each SHA-256. A comment
#: is free text, so the prefix is what makes each line parseable.
#:
#: All three are written, which makes a bundle self-describing: what it
#: claims to be is readable from the End of Central Directory record
#: alone, with no YAML parse and no entry reads (`unzip -z` shows it).
#: That is a CONVENIENCE for tooling, not a verification source -- the
#: comment is inside the artifact, so anything that can rewrite the
#: bundle can rewrite the comment in the same pass. `verify_bundle()`
#: reads the manifest, which stays the single authority.
MANIFEST_COMMENT_PREFIX = "manifest_sha256="
STORY_COMMENT_PREFIX = "story_sha256="
DIRECTORY_COMMENT_PREFIX = "directory_sha256="
BUNDLE_VERSION_COMMENT_PREFIX = "bundle_version="

#: The archive layout this bundler writes: how entries are arranged, what
#: the comment carries, and what each hash is computed over. Distinct from
#: `MANIFEST_VERSION` (the manifest's own schema) and `GAME_VERSION` (the
#: game's content release) -- those version the contents, this versions
#: the container.
#:
#: 0.5: all three hashes in the comment, directory hash excluding the
#: manifest entry. Pre-1.0 while the format settles.
BUNDLE_VERSION = "0.5"


class IntegrityError(Exception):
    """A bundle's recorded hashes do not match its contents."""


def hash_bytes(data: bytes) -> str:
    """Return the SHA-256 of `data`, hex-encoded."""
    return hashlib.sha256(data).hexdigest()


def directory_hash(archive: zipfile.ZipFile, *, manifest_name: str) -> str:
    """Hash an archive's own index: every entry's name, size and CRC.

    Reads no file content, so the cost is set by the entry count rather
    than the bundle's size — 24 ms on a 13,000-entry, 4.4 GB bundle,
    against 2.1 s to hash the same file's bytes.

    Entries are taken in sorted order so the result does not depend on
    the order they were written, and timestamps are ignored so rebuilding
    unchanged content reproduces the value.

    Args:
        archive: The open archive.
        manifest_name: The manifest's full entry name, excluded from the
            hash — see this module's docstring.

    Returns:
        The hex-encoded SHA-256.
    """
    digest = hashlib.sha256()
    for info in sorted(archive.infolist(), key=lambda i: i.filename):
        if info.filename == manifest_name:
            continue
        digest.update(info.filename.encode("utf-8"))
        digest.update(str(info.file_size).encode("ascii"))
        digest.update(str(info.CRC).encode("ascii"))
    return digest.hexdigest()


def manifest_entry_name(archive: zipfile.ZipFile) -> str | None:
    """Return the manifest's entry name in a bundle, or None if absent."""
    for name in archive.namelist():
        if name.count("/") == 1 and name.endswith(f"/{MANIFEST_FILENAME}"):
            return name
    return None


def build_archive_comment(*, manifest_sha256: str, story_sha256: str, directory_sha256: str) -> bytes:
    """Return the archive comment: the bundle's version and three hashes.

    Args:
        manifest_sha256: The manifest entry's own hash.
        story_sha256: The compiled story's hash.
        directory_sha256: The central-directory hash.

    Returns:
        The encoded comment, one `name=value` line each.
    """
    return "\n".join(
        (
            f"{BUNDLE_VERSION_COMMENT_PREFIX}{BUNDLE_VERSION}",
            f"{MANIFEST_COMMENT_PREFIX}{manifest_sha256}",
            f"{STORY_COMMENT_PREFIX}{story_sha256}",
            f"{DIRECTORY_COMMENT_PREFIX}{directory_sha256}",
        )
    ).encode("utf-8")


def read_bundle_version(archive: zipfile.ZipFile) -> str | None:
    """Return the archive layout version the bundle declares, or None.

    None means a bundle built before the version was recorded. A consumer
    treats that, and any version it does not recognise, as a reason to
    **warn** rather than refuse: the layout is backward-compatible so far,
    and refusing to open a game over an unfamiliar container version would
    be a worse answer than reading it and saying so.

    Args:
        archive: The open archive.

    Returns:
        The declared version, or None when the comment carries none.
    """
    return _read_comment_field(archive, BUNDLE_VERSION_COMMENT_PREFIX)


def _read_comment_field(archive: zipfile.ZipFile, prefix: str) -> str | None:
    """Return one `prefix=value` line's value from the archive comment."""
    try:
        comment = archive.comment.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for line in comment.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def read_comment_hash(archive: zipfile.ZipFile) -> str | None:
    """Return the manifest hash recorded in the archive comment, or None.

    Args:
        archive: The open archive.

    Returns:
        The hex digest, or None when the comment is absent, undecodable,
        or does not carry one.
    """
    return _read_comment_field(archive, MANIFEST_COMMENT_PREFIX)


def recorded_hashes(bundle_path: Path) -> dict[str, str]:
    """Return the three integrity hashes a bundle records about itself.

    These are what the bundle claims, not what it is: `verify_bundle()`
    answers whether the claims hold. An application stores them to detect a
    bundle changing underneath it later.

    Args:
        bundle_path: The `.zip` bundle.

    Returns:
        `{"manifest", "directory", "story"}`, each a hex digest or an
        empty string where the bundle records none.

    Raises:
        GameSourceError: The file is not a readable archive.
    """
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            manifest_name = manifest_entry_name(archive)
            manifest: dict[str, Any] = {}
            if manifest_name is not None:
                loaded = yaml.safe_load(archive.read(manifest_name).decode("utf-8"))
                manifest = loaded if isinstance(loaded, dict) else {}
            return {
                "manifest": read_comment_hash(archive) or "",
                "directory": str(manifest.get(BUNDLE_DIRECTORY_SHA256_FIELD) or ""),
                "story": str(manifest.get(STORY_SHA256_FIELD) or ""),
            }
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, yaml.YAMLError) as error:
        raise GameSourceError(f"cannot read bundle '{bundle_path.name}': {error}") from error


def unrecognized_bundle_version(bundle_path: Path) -> str | None:
    """Return the bundle's layout version when this reader does not know it.

    For a consumer to warn on. A bundle declaring a version this reader
    has never heard of still opens -- the layout has stayed
    backward-compatible -- but the consumer should say so, because
    anything it cannot see is by definition unaccounted for.

    Args:
        bundle_path: The `.zip` bundle.

    Returns:
        The unrecognised version string, or None when the bundle declares
        the version this reader writes (or declares none at all, which is
        a bundle built before versioning).
    """
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            declared = read_bundle_version(archive)
    except (OSError, zipfile.BadZipFile):
        return None
    if declared is None or declared == BUNDLE_VERSION:
        return None
    return declared


def verify_bundle(bundle_path: Path) -> list[str]:
    """Check a built bundle against the hashes it records.

    Args:
        bundle_path: The `.zip` bundle.

    Returns:
        One problem per failed check, most fundamental first. Empty means
        every recorded hash matches. A bundle recording no hashes at all
        reports that as its single problem rather than passing silently.
    """
    problems: list[str] = []
    with zipfile.ZipFile(bundle_path) as archive:
        manifest_name = manifest_entry_name(archive)
        if manifest_name is None:
            return [f"bundle has no {MANIFEST_FILENAME}"]

        manifest_bytes = archive.read(manifest_name)
        loaded = yaml.safe_load(manifest_bytes.decode("utf-8"))
        manifest = loaded if isinstance(loaded, dict) else {}

        recorded_manifest = read_comment_hash(archive)
        if recorded_manifest is None:
            problems.append("archive comment records no manifest hash")
        elif recorded_manifest != hash_bytes(manifest_bytes):
            problems.append("manifest does not match the hash in the archive comment")

        recorded_directory = manifest.get(BUNDLE_DIRECTORY_SHA256_FIELD)
        if not recorded_directory:
            problems.append(f"manifest records no {BUNDLE_DIRECTORY_SHA256_FIELD}")
        elif recorded_directory != directory_hash(archive, manifest_name=manifest_name):
            problems.append(f"{BUNDLE_DIRECTORY_SHA256_FIELD} does not match the bundle's contents")

        recorded_story = manifest.get(STORY_SHA256_FIELD)
        story_file = manifest.get("MAIN_STORY_FILE")
        if not recorded_story:
            problems.append(f"manifest records no {STORY_SHA256_FIELD}")
        elif isinstance(story_file, str):
            package = manifest_name.split("/")[0]
            try:
                story_bytes = archive.read(f"{package}/{story_file}")
            except KeyError:
                problems.append(f"manifest names '{story_file}' but the bundle does not contain it")
            else:
                if recorded_story != hash_bytes(story_bytes):
                    problems.append(f"{STORY_SHA256_FIELD} does not match '{story_file}'")
    return problems
