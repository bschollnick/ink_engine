"""Building a distributable game bundle: one `.zip` an application plays in place.

**The manifest decides what ships.** A bundle carries `manifest.yaml`
itself, the story it names, the game's Python package, the media
directories it declares, and whatever `EXTRA_FILES` adds -- nothing else. A game
folder also holds uncompiled `.ink` source, superseded build
intermediates, test suites and editor caches, and none of it reaches a
player because none of it is declared.

Declaring rather than excluding matters for the failure it prevents: with
an exclusion list, a file type nobody anticipated ships silently, and the
author finds out from a 4 GB download. Here an undeclared file is simply
absent, and `verify_plan()` catches the case that actually breaks a game
-- something declared but missing.

Bundles are read without extraction, so one more property is structural:
**already-compressed media is stored, not deflated.** Deflate returns
~0.7% on JPEG/MP4 while costing CPU on every read. Text still deflates.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ink_engine.bundle_integrity import (
    BUNDLE_DIRECTORY_SHA256_FIELD,
    STORY_SHA256_FIELD,
    build_archive_comment,
    directory_hash,
    hash_bytes,
)
from ink_engine.bundle_readme import render_readme
from ink_engine.game_folder import (
    COVER_IMAGE_FIELD,
    PLUGIN_DENIED_SCREEN_FIELD,
    PROSE_STYLES_FIELD,
    COMPILED_STORY_SUFFIX,
    EXTRA_FILES_FIELD,
    MANIFEST_FILENAME,
    MEDIA_DIRECTORIES_FIELD,
    GameFolderError,
    read_manifest,
)

#: Filenames never bundled even inside a declared directory: OS droppings
#: that carry no game content and appear at every level of a media tree.
JUNK_FILENAMES: frozenset[str] = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})

#: Directory names never bundled even inside a declared directory —
#: caches that can appear anywhere and are never game content.
JUNK_DIRECTORY_NAMES: frozenset[str] = frozenset({"__pycache__", ".mypy_cache", ".pytest_cache", ".git"})

#: Suffixes stored without compression. Already-compressed formats gain
#: almost nothing from deflate and cost CPU on every read.
STORED_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".zip", ".woff", ".woff2"}
)

#: Suffix of the Python modules forming a game's own package. Every one is
#: bundled: they import each other, and `sidebar.py` is imported lazily by
#: an application rather than at package import, so reachability analysis would
#: wrongly drop it.
PYTHON_SUFFIX = ".py"

#: Uncompiled Ink source. Never bundled -- this engine plays compiled
#: stories only -- but its modification time is what says whether the
#: compiled story beside it is current (see `stale_sources()`).
INK_SOURCE_SUFFIX = ".ink"


class BundleError(Exception):
    """A game folder cannot be bundled as asked."""


@dataclass
class BundlePlan:
    """What `build_bundle()` would write, decided before anything is written.

    Args:
        game_dir: The game folder being bundled.
        package_name: The bundle's top-level package directory, and the
            name an application imports. Defaults to the folder's own name.
        included: Files to write, relative to `game_dir`, each with the
            manifest reason it is present.
        missing: `(declared path, problem)` for every manifest
            declaration that does not resolve to real content.
        main_story_file: The story the manifest names, or None.
    """

    game_dir: Path
    package_name: str
    included: dict[Path, str] = field(default_factory=dict)
    missing: list[tuple[str, str]] = field(default_factory=list)
    main_story_file: str | None = None

    @property
    def total_bytes(self) -> int:
        """Return the uncompressed size of every included file."""
        return sum((self.game_dir / relative).stat().st_size for relative in self.included)

    def counts_by_reason(self) -> dict[str, int]:
        """Return how many files each manifest declaration contributed."""
        counts: dict[str, int] = {}
        for reason in self.included.values():
            counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def counts_by_suffix(self) -> dict[str, int]:
        """Return how many included files carry each suffix, commonest first."""
        counts: dict[str, int] = {}
        for relative in self.included:
            suffix = relative.suffix.lower() or "(none)"
            counts[suffix] = counts.get(suffix, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _is_junk(relative: Path) -> bool:
    """Return whether a path is an OS dropping or a cache directory's content."""
    if relative.name in JUNK_FILENAMES:
        return True
    return any(part in JUNK_DIRECTORY_NAMES for part in relative.parts)


def _walk_directory(game_dir: Path, declared: str) -> Iterator[Path]:
    """Yield every real file under one declared directory, relative and sorted.

    Symlinks are skipped: a bundle must be self-contained, and following
    one would either embed something from outside the game folder or write
    a dangling entry.

    Args:
        game_dir: The game folder.
        declared: A directory path relative to `game_dir`.

    Yields:
        Paths relative to `game_dir`, sorted, junk omitted.
    """
    for path in sorted((game_dir / declared).rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(game_dir)
        if not _is_junk(relative):
            yield relative


def _resolve_declared(game_dir: Path, declared: str) -> Path | None:
    """Return a declared path that stays inside the game folder, else None.

    A manifest is game-supplied content, so a path escaping the game folder
    (`../../etc/passwd`, or an absolute path) is refused rather than
    followed.

    Args:
        game_dir: The game folder.
        declared: The manifest's path, relative to `game_dir`.

    Returns:
        The resolved absolute path, or None if it escapes `game_dir`.
    """
    candidate = (game_dir / declared).resolve()
    if candidate == game_dir.resolve() or candidate.is_relative_to(game_dir.resolve()):
        return candidate
    return None


def select_bundle_contents(game_dir: Path, *, package_name: str | None = None) -> BundlePlan:
    """Decide what a bundle of `game_dir` would contain, from its manifest.

    Collects, in order: `manifest.yaml` itself, every top-level `.py`
    (the game's own package, including the `__init__.py` that makes it
    importable), the story named by `MAIN_STORY_FILE`, every directory in
    `MEDIA_DIRECTORIES`, and every path in `EXTRA_FILES`. Nothing else is
    considered.

    Never writes anything -- `build_bundle()` does that, so an author can
    inspect the plan first.

    Args:
        game_dir: The game folder to bundle.
        package_name: The bundle's top-level package name. Defaults to
            `game_dir`'s own name.

    Returns:
        The `BundlePlan`, with `missing` naming anything declared but
        absent.

    Raises:
        BundleError: `game_dir` is not a directory.
    """
    if not game_dir.is_dir():
        raise BundleError(f"Not a directory: {game_dir}")

    manifest = read_manifest(game_dir)
    main_story_file = manifest.get("MAIN_STORY_FILE")
    if not isinstance(main_story_file, str):
        main_story_file = None

    plan = BundlePlan(game_dir=game_dir, package_name=package_name or game_dir.name, main_story_file=main_story_file)

    if (game_dir / MANIFEST_FILENAME).is_file():
        plan.included[Path(MANIFEST_FILENAME)] = "manifest"

    for module_path in sorted(game_dir.glob(f"*{PYTHON_SUFFIX}")):
        plan.included[module_path.relative_to(game_dir)] = "game package"

    if main_story_file:
        story = game_dir / main_story_file
        if story.is_file():
            plan.included[Path(main_story_file)] = "MAIN_STORY_FILE"
        else:
            plan.missing.append((main_story_file, "MAIN_STORY_FILE names a story that does not exist"))

    _collect_declared(plan, manifest, MEDIA_DIRECTORIES_FIELD, wants_directory=True)
    _collect_declared(plan, manifest, EXTRA_FILES_FIELD, wants_directory=False)
    # Fields naming ONE file rather than a list. Without these a game that
    # declares a cover, a stylesheet or a plugin-denied screen builds a
    # bundle that does not contain it, and the feature silently does
    # nothing once bundled.
    for field_name in (COVER_IMAGE_FIELD, PROSE_STYLES_FIELD, PLUGIN_DENIED_SCREEN_FIELD):
        _collect_single_file(plan, manifest, field_name)
    return plan


def _collect_single_file(plan: BundlePlan, manifest: dict[str, Any], field_name: str) -> None:
    """Add one manifest field's single declared file to `plan`.

    Args:
        plan: The plan to add to, mutated in place.
        manifest: The game's manifest.
        field_name: The field naming one path, relative to the game folder.
    """
    declared = manifest.get(field_name)
    if not isinstance(declared, str) or not declared:
        return
    resolved = _resolve_declared(plan.game_dir, declared)
    if resolved is None:
        plan.missing.append((declared, f"{field_name} names a path outside the game folder"))
    elif resolved.is_file():
        plan.included[Path(declared)] = field_name
    else:
        plan.missing.append((declared, f"{field_name} names a file that does not exist"))


def _collect_declared(plan: BundlePlan, manifest: dict[str, Any], field_name: str, *, wants_directory: bool) -> None:
    """Add one manifest field's declared paths to `plan`, or record why not.

    Args:
        plan: The plan to add to, mutated in place.
        manifest: The game's manifest.
        field_name: The field naming the paths.
        wants_directory: True to bundle each path's whole tree, False to
            bundle each path as a single file.
    """
    kind = "directory" if wants_directory else "file"
    for declared in _string_list(manifest, field_name):
        resolved = _resolve_declared(plan.game_dir, declared)
        if resolved is None:
            plan.missing.append((declared, f"{field_name} names a path outside the game folder"))
        elif wants_directory and resolved.is_dir():
            for relative in _walk_directory(plan.game_dir, declared):
                plan.included[relative] = f"{field_name}: {declared}"
        elif not wants_directory and resolved.is_file():
            plan.included[Path(declared)] = field_name
        else:
            plan.missing.append((declared, f"{field_name} names a {kind} that does not exist"))


def _string_list(manifest: dict[str, object], field_name: str) -> list[str]:
    """Return a manifest field's list-of-strings value, or `[]`."""
    value = manifest.get(field_name)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return []


def stale_sources(game_dir: Path, main_story_file: str | None) -> list[Path]:
    """Return `.ink` sources modified after the compiled story was built.

    A compiled story is what ships; its `.ink` sources are not bundled and
    are not read at play time. So a story compiled before its most recent
    source edit produces a bundle that plays the OLD content, with nothing
    at play time to reveal it -- the player simply gets a game the author
    no longer wrote. Modification times are the only evidence available
    here: this engine has no Ink compiler and cannot re-derive the story
    to compare.

    Args:
        game_dir: The game folder.
        main_story_file: The manifest's `MAIN_STORY_FILE`, or None to
            resolve a lone compiled story by suffix.

    Returns:
        Source paths newer than the compiled story, newest first. Empty
        when the story is current, when the manifest declares no story,
        or when the game ships no `.ink` sources at all.
    """
    if not main_story_file:
        return []
    story = game_dir / main_story_file
    if not story.is_file():
        return []

    built_at = story.stat().st_mtime
    newer = [path for path in game_dir.rglob(f"*{INK_SOURCE_SUFFIX}") if path.is_file() and path.stat().st_mtime > built_at]
    return sorted(newer, key=lambda path: -path.stat().st_mtime)


def verify_plan(plan: BundlePlan) -> list[str]:
    """Return every reason `plan` would produce an unplayable bundle.

    Checked here rather than after writing, so a bundle that cannot open is
    never handed to a player.

    Args:
        plan: The plan to check.

    Returns:
        Problems, most fundamental first. Empty means the bundle opens.
    """
    problems: list[str] = []

    if Path(MANIFEST_FILENAME) not in plan.included:
        problems.append(f"no {MANIFEST_FILENAME}: a bundle without a manifest cannot declare its story or plugins")
    if Path("__init__.py") not in plan.included:
        problems.append("no __init__.py: the game folder would not be an importable package, so its plugins and sidebar could not load")

    for declared, reason in plan.missing:
        problems.append(f"{reason}: '{declared}'")

    if not plan.main_story_file:
        problems.append(f"the manifest declares no MAIN_STORY_FILE, so nothing says which {COMPILED_STORY_SUFFIX} file plays")
    return problems


def _compression_for(relative: Path) -> int:
    """Return the zipfile compression constant for one file."""
    if relative.suffix.lower() in STORED_SUFFIXES:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def build_bundle(plan: BundlePlan, output_path: Path, *, progress: Callable[[Path], None] | None = None) -> Path:
    """Write `plan` to a `.zip` bundle.

    Every file is written under the plan's `package_name` directory, so the
    archive is importable: an application puts the bundle on `sys.path` and imports
    that package.

    Args:
        plan: What to write (see `select_bundle_contents()`).
        output_path: Where to write the bundle.
        progress: Called with each file's relative path as it is written,
            for a caller reporting progress.

    Also writes two things a reader depends on: the manifest gains its
    `STORY_SHA256`/`BUNDLE_DIRECTORY_SHA256`, the archive comment gains
    the manifest's own hash, and a companion `<name>.md` readme is written
    **beside** the bundle publishing all three out of band.

    Returns:
        The resolved `output_path`. The readme sits next to it, same stem
        with a `.md` suffix.

    Raises:
        BundleError: The plan would produce an unplayable bundle (see
            `verify_plan()`), or `output_path` is inside the game folder.
    """
    problems = verify_plan(plan)
    if problems:
        raise BundleError("; ".join(problems))

    resolved_output = output_path.resolve()
    if resolved_output.is_relative_to(plan.game_dir.resolve()):
        # Writing into the folder being walked would race the walk and, on
        # a rebuild, try to bundle the previous bundle.
        raise BundleError(f"Output must be outside the game folder: {output_path}")

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    digests = _write_archive(plan, resolved_output, progress)

    resolved_output.with_suffix(".md").write_text(
        render_readme(
            read_manifest(plan.game_dir),
            bundle_name=resolved_output.name,
            bundle_bytes=resolved_output.stat().st_size,
            file_count=len(plan.included),
            **digests,
        ),
        encoding="utf-8",
    )
    return resolved_output


def _write_archive(plan: BundlePlan, output_path: Path, progress: Callable[[Path], None] | None) -> dict[str, str]:
    """Write the archive, and return the three hashes it records.

    The manifest carries hashes of the bundle it lives in, so ordering is
    load-bearing: every other entry is written first, the directory hash
    is taken over those, and only then does the manifest go in — followed
    by the archive comment carrying the manifest's own hash, which is the
    one thing the directory hash cannot cover.

    Args:
        plan: What to write.
        output_path: The resolved bundle path.
        progress: Called with each file's relative path as it is written.

    Returns:
        `story_sha256`, `directory_sha256` and `manifest_sha256`, ready to
        pass to `render_readme()`.
    """
    manifest_relative = Path(MANIFEST_FILENAME)
    manifest_arcname = str(Path(plan.package_name) / manifest_relative)
    story_relative = Path(plan.main_story_file) if plan.main_story_file else None
    story_digest = ""

    with zipfile.ZipFile(output_path, "w") as archive:
        for relative in plan.included:
            if relative == manifest_relative:
                continue
            source = plan.game_dir / relative
            archive.write(source, arcname=str(Path(plan.package_name) / relative), compress_type=_compression_for(relative))
            if relative == story_relative:
                story_digest = hash_bytes(source.read_bytes())
            if progress is not None:
                progress(relative)

        directory_digest = directory_hash(archive, manifest_name=manifest_arcname)
        manifest_text = _manifest_with_hashes(
            (plan.game_dir / manifest_relative).read_text(encoding="utf-8"),
            story_sha256=story_digest,
            directory_sha256=directory_digest,
        )
        archive.writestr(manifest_arcname, manifest_text)
        manifest_digest = hash_bytes(manifest_text.encode("utf-8"))
        archive.comment = build_archive_comment(
            manifest_sha256=manifest_digest, story_sha256=story_digest, directory_sha256=directory_digest
        )
        if progress is not None:
            progress(manifest_relative)

    return {"story_sha256": story_digest, "directory_sha256": directory_digest, "manifest_sha256": manifest_digest}


def _manifest_with_hashes(source: str, *, story_sha256: str, directory_sha256: str) -> str:
    """Return the manifest text with its two integrity hashes appended.

    Appended as plain lines rather than re-serialised through YAML: a
    round-trip would discard every comment in the file, and a game
    manifest's comments are often the only record of why a value is what
    it is.

    Args:
        source: The manifest's own text, as authored.
        story_sha256: The compiled story's hash, or "" if the game
            declares no story file.
        directory_sha256: The archive directory's hash.

    Returns:
        The text to write into the bundle.
    """
    lines = [source.rstrip("\n"), "", "# Added at build time; editing either value fails verification."]
    if story_sha256:
        lines.append(f"{STORY_SHA256_FIELD}: {story_sha256}")
    lines.append(f"{BUNDLE_DIRECTORY_SHA256_FIELD}: {directory_sha256}")
    return "\n".join(lines) + "\n"


def open_bundle_manifest(bundle_path: Path) -> dict[str, object]:
    """Read a built bundle's manifest without extracting it.

    Confirms a bundle is well-formed by reading it back the way an application
    will.

    Args:
        bundle_path: The `.zip` bundle.

    Returns:
        Every top-level key the manifest declares.

    Raises:
        GameFolderError: The bundle has no package directory containing a
            manifest.
    """
    with zipfile.ZipFile(bundle_path) as archive:
        manifests = [name for name in archive.namelist() if name.count("/") == 1 and name.endswith(f"/{MANIFEST_FILENAME}")]
        if not manifests:
            raise GameFolderError(f"Bundle '{bundle_path.name}' has no package directory containing {MANIFEST_FILENAME}")
        source = archive.read(manifests[0]).decode("utf-8")
    try:
        loaded = yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise GameFolderError(f"Bundle '{bundle_path.name}': {MANIFEST_FILENAME} is not valid YAML ({error})") from error
    return loaded if isinstance(loaded, dict) else {}
