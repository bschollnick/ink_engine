"""Where a game's files come from: a directory, or a bundle read in place.

A published game is a `.zip` bundle. A loose directory is a development
convenience — it exists so an author can edit a `.ink` file, recompile,
and re-open without re-zipping — so anything a player depends on must
work from a bundle, and directory-only behaviour is a defect rather than
a supported mode.

Every path handed to a source is **relative to the game's own root**, in
POSIX form (`"images/cover.png"`), whichever implementation is behind it.
Absolute paths and `..` are refused: a manifest is game-supplied content,
and a game may not read outside itself.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any, Protocol, runtime_checkable

import yaml


class GameSourceError(Exception):
    """A game's files cannot be read as asked."""


def normalise(relative: str) -> str:
    """Return a game-relative path in POSIX form, or raise if it escapes.

    Args:
        relative: A path as a manifest or a story tag wrote it.

    Returns:
        The cleaned path, always relative and `/`-separated.

    Raises:
        GameSourceError: The path is absolute, or climbs above the game
            root.
    """
    cleaned = posixpath.normpath(relative.replace("\\", "/"))
    if posixpath.isabs(cleaned) or cleaned == ".." or cleaned.startswith("../"):
        raise GameSourceError(f"path escapes the game: {relative!r}")
    return cleaned


@runtime_checkable
class GameSource(Protocol):
    """Read-only access to one game's files."""

    @property
    def name(self) -> str:
        """The game's own name, for error messages."""

    def exists(self, relative: str) -> bool:
        """Return whether a file exists at `relative`."""

    def read_bytes(self, relative: str) -> bytes:
        """Return one file's bytes.

        Raises:
            GameSourceError: No such file.
        """

    def open_stream(self, relative: str) -> tuple[IO[bytes], int]:
        """Return an open handle on one file, and its total size.

        For serving media an application must not read whole into memory. The
        handle is the caller's to close.

        Raises:
            GameSourceError: No such file, or it cannot be opened.
        """

    def read_text(self, relative: str) -> str:
        """Return one file's decoded text.

        Raises:
            GameSourceError: No such file, or it is not UTF-8.
        """

    def iter_names(self, prefix: str = "", *, recursive: bool = True) -> Iterator[str]:
        """Yield file paths under `prefix`, game-relative.

        Args:
            prefix: Limit to this directory, or "" for the game's root.
            recursive: False to yield only `prefix`'s immediate children.
                A caller wanting the game's own top-level files must pass
                False: a game ships its media inside itself, so walking
                the whole tree to answer a question about the root reads
                every media file's directory entry — 14,000 of them for a
                real game, seconds rather than milliseconds.
        """

    def fingerprint(self, relative: str) -> int:
        """Return a value that changes when `relative` changes.

        The cache key behind `read_manifest()`. A directory answers the
        file's modification time; a bundle answers a constant, since an
        archive cannot change under a session that has it open.

        Returns:
            0 when the file does not exist.
        """

    @property
    def listing_cache(self) -> dict[str, Any]:
        """Scratch space a resolver can index this game's files in.

        A game shipping its own media resolver (`resolve_tag`) typically
        needs its directory listings more than once per turn, and reading
        them is what dominates: measured at 98 ms a tag against 0.1 ms
        cached. Holding that index HERE rather than in the resolver's own
        module gives it the right lifetime -- it belongs to one game, is
        freed with it, and is never shared between games or sessions.

        The engine neither reads nor writes this; its contents are
        entirely the resolver's own. Two games, or two concurrent
        sessions of one game, each get their own.
        """

    def close(self) -> None:
        """Release whatever the source holds open.

        A bundle closes its archive; a directory holds nothing and
        returns. Callers close every source rather than testing which
        kind they were handed.
        """


# The two implementations below satisfy `GameSource`, whose methods carry
# the contract; repeating each docstring here would be duplication rather
# than documentation. Only behaviour specific to one implementation is
# documented on it.
# pylint: disable=missing-function-docstring


class DirectoryGameSource:
    """A game read from a directory on disk — the development path."""

    def __init__(self, game_dir: Path) -> None:
        """
        Args:
            game_dir: The game folder.
        """
        self._root = game_dir
        self._listing_cache: dict[str, Any] = {}

    @property
    def listing_cache(self) -> dict[str, Any]:
        return self._listing_cache

    @property
    def root(self) -> Path:
        """The game folder, for a caller that genuinely needs a real path.

        Reaching for this is a sign the caller does something a bundle
        cannot do; prefer the protocol's own methods.
        """
        return self._root

    @property
    def name(self) -> str:
        return self._root.name

    def _resolve(self, relative: str) -> Path:
        return self._root / normalise(relative)

    def exists(self, relative: str) -> bool:
        try:
            return self._resolve(relative).is_file()
        except GameSourceError:
            return False

    def read_bytes(self, relative: str) -> bytes:
        try:
            return self._resolve(relative).read_bytes()
        except OSError as error:
            raise GameSourceError(f"cannot read '{relative}' from '{self.name}': {error}") from error

    def open_stream(self, relative: str) -> tuple[IO[bytes], int]:
        try:
            path = self._resolve(relative)
            return path.open("rb"), path.stat().st_size
        except OSError as error:
            raise GameSourceError(f"cannot read '{relative}' from '{self.name}': {error}") from error

    def read_text(self, relative: str) -> str:
        try:
            return self._resolve(relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise GameSourceError(f"cannot read '{relative}' from '{self.name}': {error}") from error

    def iter_names(self, prefix: str = "", *, recursive: bool = True) -> Iterator[str]:
        base = self._root / normalise(prefix) if prefix else self._root
        if not base.is_dir():
            return
        for path in sorted(base.rglob("*") if recursive else base.glob("*")):
            if path.is_file() and not path.is_symlink():
                yield path.relative_to(self._root).as_posix()

    def fingerprint(self, relative: str) -> int:
        try:
            return self._resolve(relative).stat().st_mtime_ns
        except (OSError, GameSourceError):
            return 0

    def close(self) -> None:
        # A directory holds nothing open; the method exists so a caller
        # need not ask which kind of source it has.
        return


class ZipGameSource:
    """A game read from a `.zip` bundle, in place and never extracted.

    Entries inside a bundle live under one package directory, so the
    package name is stripped on the way in and out: a caller asks for
    `"images/cover.png"` exactly as it would of a directory.

    A table of contents is built once at construction. Without it every
    existence check re-parses the archive's central directory — measured
    at 2.4 ms against 0.00002 ms for a set lookup on a 13,000-entry
    bundle, and one extensionless media tag costs up to nine such checks.
    """

    def __init__(self, bundle_path: Path) -> None:
        """
        Args:
            bundle_path: The `.zip` bundle.

        Raises:
            GameSourceError: The file is not a readable archive, or holds
                no package directory.
        """
        self._path = bundle_path
        self._listing_cache: dict[str, Any] = {}
        try:
            # Held open for the session, not scoped to a block: every
            # later read goes through it. `close()` releases it.
            self._archive = zipfile.ZipFile(bundle_path)  # pylint: disable=consider-using-with
        except (OSError, zipfile.BadZipFile) as error:
            raise GameSourceError(f"cannot open bundle '{bundle_path.name}': {error}") from error

        entries = self._archive.namelist()
        roots = {entry.split("/", 1)[0] for entry in entries if "/" in entry}
        if len(roots) != 1:
            raise GameSourceError(f"bundle '{bundle_path.name}' must hold exactly one package directory, found {len(roots)}")
        self._package = roots.pop()
        prefix = f"{self._package}/"
        self._contents = frozenset(entry[len(prefix) :] for entry in entries if entry.startswith(prefix) and not entry.endswith("/"))

    @property
    def package(self) -> str:
        """The bundle's own package directory name."""
        return self._package

    @property
    def name(self) -> str:
        return self._path.name

    @property
    def listing_cache(self) -> dict[str, Any]:
        return self._listing_cache

    def close(self) -> None:
        """Release the archive. The source is unusable afterwards."""
        self._archive.close()

    def exists(self, relative: str) -> bool:
        try:
            return normalise(relative) in self._contents
        except GameSourceError:
            return False

    def read_bytes(self, relative: str) -> bytes:
        cleaned = normalise(relative)
        if cleaned not in self._contents:
            raise GameSourceError(f"'{cleaned}' is not in bundle '{self.name}'")
        return self._archive.read(f"{self._package}/{cleaned}")

    def open_stream(self, relative: str) -> tuple[IO[bytes], int]:
        """Media is STORED rather than deflated, so the returned handle
        seeks cheaply and a Range request costs no decompression."""
        cleaned = normalise(relative)
        if cleaned not in self._contents:
            raise GameSourceError(f"'{cleaned}' is not in bundle '{self.name}'")
        entry = f"{self._package}/{cleaned}"
        try:
            return self._archive.open(entry), self._archive.getinfo(entry).file_size
        except (KeyError, OSError, zipfile.BadZipFile) as error:
            raise GameSourceError(f"cannot read '{relative}' from '{self.name}': {error}") from error

    def read_text(self, relative: str) -> str:
        try:
            return self.read_bytes(relative).decode("utf-8")
        except UnicodeDecodeError as error:
            raise GameSourceError(f"'{relative}' in '{self.name}' is not UTF-8") from error

    def iter_names(self, prefix: str = "", *, recursive: bool = True) -> Iterator[str]:
        cleaned = f"{normalise(prefix)}/" if prefix else ""
        names = (name for name in self._contents if name.startswith(cleaned))
        if not recursive:
            names = (name for name in names if "/" not in name[len(cleaned) :])
        yield from sorted(names)

    def fingerprint(self, relative: str) -> int:
        # Constant for the life of the archive: a bundle open in a session
        # cannot change, so any present file's answer need only differ
        # from an absent file's.
        return 1 if self.exists(relative) else 0


def as_source(game: GameSource | Path) -> GameSource:
    """Return a `GameSource` for `game`, wrapping a `Path` if needed.

    Every reader in the engine takes either, so a caller holding a plain
    directory path -- the development case, and what every existing call
    site passes -- need not construct a source itself.

    A `.zip` path is opened as a bundle, not treated as a directory:
    wrapping one as a `DirectoryGameSource` silently gives it directory
    semantics, so every read misses and the game appears empty.

    Args:
        game: A source, a game directory, or a bundle.

    Returns:
        The source.
    """
    if not isinstance(game, Path):
        return game
    if game.suffix.lower() == ".zip":
        return ZipGameSource(game)
    return DirectoryGameSource(game)


#: Length of the identity digest a game is keyed by. Sixteen hex
#: characters is 64 bits — collision-free in practice for a library of
#: games, and short enough to read in a directory listing.
IDENTITY_LENGTH = 16


def _declared_title(source: GameSource) -> str:
    """Return a bundle's own GAME_TITLE, or "" when it declares none.

    Parses the manifest here rather than calling `game_folder`, which
    imports this module -- the dependency runs one way only.
    """
    if not source.exists("manifest.yaml"):
        return ""
    try:
        manifest = yaml.safe_load(source.read_text("manifest.yaml"))
    except yaml.YAMLError:
        return ""
    if not isinstance(manifest, dict):
        return ""
    return str(manifest.get("GAME_TITLE", "") or "")


def game_identity(game: GameSource | Path) -> str:
    """Return a stable id for one game, unchanged by rebuilding it.

    A filename is not an identity: it is chosen by whoever downloaded the
    game, so two unrelated games both saved as `game.zip` would share
    save files and shadow each other's modules. This keys on what the
    game IS instead.

    A bundle answers a slug of its declared title plus a short hash of
    that title, so a renamed, moved OR REBUILT bundle keeps its saves. A
    directory answers its own name, for the same reason.

    Rebuilding a game changes its story but not its identity. Use
    `game_build()` to tell one build from another -- an application that
    cares shows a caution, rather than a player losing every save to a
    corrected typo.

    Args:
        game: A source, or a game directory.

    Returns:
        A readable, filesystem-safe id.
    """
    source = as_source(game)
    if isinstance(source, DirectoryGameSource):
        return source.root.resolve().name

    title = _declared_title(source)
    if not title:
        # No declared title: fall back to content, which at least keys on
        # something real. Such a game's saves do not survive a rebuild.
        digest = hashlib.sha256()
        for relative in sorted(n for n in source.iter_names(recursive=False) if n.endswith(".inkj")):
            digest.update(source.read_bytes(relative))
        return digest.hexdigest()[:IDENTITY_LENGTH]

    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-.").lower() or "game"
    # The suffix separates two games whose titles slug the same way, and
    # keeps a title with no ASCII at all from collapsing to nothing.
    suffix = hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:40]}-{suffix}"


def game_build(game: GameSource | Path) -> str:
    """Return which build of a game this is.

    Changes whenever the story or manifest changes, where
    `game_identity()` does not. An application compares the build
    recorded in a save against the game in front of it, and cautions the
    player when they differ.

    Args:
        game: A source, or a game directory.

    Returns:
        A short hex digest, or "" for a directory, which changes too
        often for the comparison to mean anything.
    """
    source = as_source(game)
    if isinstance(source, DirectoryGameSource):
        return ""
    digest = hashlib.sha256()
    for relative in ("manifest.yaml", *sorted(n for n in source.iter_names(recursive=False) if n.endswith(".inkj"))):
        if source.exists(relative):
            digest.update(relative.encode("utf-8"))
            digest.update(source.read_bytes(relative))
    return digest.hexdigest()[:IDENTITY_LENGTH]


def open_game_source(game: Path) -> GameSource:
    """Return a source for a game folder or a `.zip` bundle.

    The one place an application decides which kind of game it was handed.

    Args:
        game: A game folder, or a bundle.

    Returns:
        The matching source.

    Raises:
        GameSourceError: `game` is neither, or does not exist.
    """
    if game.is_dir():
        return DirectoryGameSource(game)
    if game.suffix.lower() == ".zip":
        return ZipGameSource(game)
    raise GameSourceError(f"not a game folder or bundle: {game}")
