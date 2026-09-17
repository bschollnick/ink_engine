"""Media-tag resolution: turning a turn's `# image: <tag>`/`# video: <tag>`
Ink tags into displayable URLs or paths.

What a tag resolves TO is application-specific: `parse_media_tags` splits a
turn's raw tags into `(kind, tag_name)` pairs, and `MediaResolver` is the
seam each application implements.

The `image:`/`video:` prefixes are this project's convention, not Ink's:
Ink tags are untyped metadata handed to the game verbatim, with no notion
of media kind or directory layout.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Protocol

from ink_engine.game_folder import read_cover_image, read_prose_styles
from ink_engine.game_source import DirectoryGameSource, GameSource, as_source

#: Ink tag prefix -> the media kind it names. Order matters: `resolve()`'s
#: own grouped-output contract (all images, then all videos) follows this
#: dict's own iteration order, matching the prefix-scan behavior every real
#: application already implements today.
MEDIA_TAG_PREFIXES: dict[str, str] = {"image:": "image", "video:": "video"}

#: Extensions `FilesystemMediaResolver` tries, in order, for a tag that
#: names no extension of its own. A tag that already ends in one of these
#: (the normal case — every real converted tag carries its own extension,
#: e.g. `image: church/church_front.jpg`) is checked as given first, and
#: this list is never consulted at all.
EXTENSION_FALLBACKS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".mov")

#: Extensions `find_cover_image()` tries, in order. Image formats only — a
#: cover is always a still image, never video.
COVER_EXTENSION_FALLBACKS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".gif")

#: Where `find_cover_image()` looks for `cover.<ext>`, in order — the game
#: folder's own root first, then a conventional `images/` subdirectory some
#: games may still choose to use even though nothing requires it.
COVER_SEARCH_DIRS: tuple[str, ...] = (".", "images")


def find_cover_image(game_dir: GameSource | Path) -> str | None:
    """Return a game folder's own cover image.

    A manifest that declares `COVER_IMAGE` names the file outright — one
    lookup, and any filename the game likes. Otherwise this falls back to
    the old convention: `cover.<ext>` (any of `COVER_EXTENSION_FALLBACKS`)
    directly under `game_dir`, then under `game_dir/images/`, which costs
    up to ten filesystem probes to find one file.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The resolved absolute path, or None if the game declares no cover
        and none is found by convention. A declared file that does not
        exist yields None rather than raising — a missing cover is a
        cosmetic gap, not a reason a game cannot be played.
    """
    source = as_source(game_dir)
    resolver = FilesystemMediaResolver(source)

    declared = read_cover_image(source)
    if declared:
        return resolver.reference(declared) if source.exists(declared) else None

    for search_dir in COVER_SEARCH_DIRS:
        for extension in COVER_EXTENSION_FALLBACKS:
            candidate = f"cover{extension}" if search_dir == "." else f"{search_dir}/cover{extension}"
            if source.exists(candidate):
                return resolver.reference(candidate)
    return None


#: Filename `find_prose_styles()` looks for, directly under `game_dir` —
#: fixed convention, same as `find_cover_image()`.
PROSE_STYLES_FILENAME = "styles.css"

#: The function a game's own resolver module exposes, if it ships one.
#: Same shape as a panel hook: absent, raising, or answering the wrong
#: type all mean "this game has nothing to say", never an error.
RESOLVE_TAG_HOOK = "resolve_tag"


def find_prose_styles(game_dir: GameSource | Path) -> str | None:
    """Return a game folder's own prose-styling CSS, if it supplies one.

    Looks for `styles.css` directly under `game_dir` — a fixed filename
    convention, no manifest field. A story tags a span of prose with an
    inline `<style=name>...</style>` marker (this project's own inline-tag
    convention, not part of the Ink language); this file is where a game
    defines what each `name` actually renders as (font, size, colour).
    Entirely optional — an application applies its own baseline style names first,
    and this file's rules load after, so a game can override any baseline
    name or add its own without the application knowing about it in advance.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The file's raw text content, or None if the game folder supplies
        no such file. Reading and injecting that CSS into a page is the
        application's own concern — `ink_engine` has no opinion on application UI.
    """
    source = as_source(game_dir)
    candidate = read_prose_styles(source) or PROSE_STYLES_FILENAME
    return source.read_text(candidate) if source.exists(candidate) else None


def parse_media_tags(current_tags: list[str]) -> list[tuple[str, str]]:
    """Return `(kind, tag_name)` pairs for every media tag in `current_tags`.

    Args:
        current_tags: A turn's raw Ink tags (`InkRuntimeState.current_tags`),
            exactly as the engine produced them — unstripped, original case.

    Returns:
        `(kind, tag_name)` pairs, `kind` one of `MEDIA_TAG_PREFIXES`'s own
        values ("image"/"video"), `tag_name` stripped, in encounter order.
        A tag that does not start with a recognised prefix (after
        stripping and lowercasing for the comparison only — the returned
        `tag_name` keeps its original case) is silently ignored, exactly
        like every other non-media Ink tag a story might carry.
    """
    pairs: list[tuple[str, str]] = []
    for tag in current_tags:
        stripped = tag.strip()
        lowered = stripped.lower()
        for prefix, kind in MEDIA_TAG_PREFIXES.items():
            if lowered.startswith(prefix):
                pairs.append((kind, stripped[len(prefix) :].strip()))
                break
    return pairs


class MediaResolver(Protocol):  # pylint: disable=too-few-public-methods
    """Maps `parse_media_tags()` output to displayable URL/path strings.

    Implementations MUST batch: `resolve()` is called once per turn with
    every media tag that turn carries, not once per tag, so a
    database-backed implementation can answer with one query regardless of
    how many tags a turn names.
    """

    def resolve(self, requests: list[tuple[str, str]]) -> list[str]:
        """Resolve a turn's media requests to displayable strings.

        Args:
            requests: `parse_media_tags()`'s own output for this turn.

        Returns:
            One URL/path per request that could be resolved. A request
            naming a tag with no resolvable target is silently dropped —
            not an error, not a placeholder entry — matching the existing
            tolerance a work-in-progress story with placeholder tags
            relies on: it plays text-only rather than erroring. Output is
            GROUPED by kind in `MEDIA_TAG_PREFIXES`'s own order (every
            resolved image, then every resolved video), each group in its
            own tag-encounter order — not interleaved in the order
            `requests` names them.
        """
        ...  # pylint: disable=unnecessary-ellipsis


def _group_by_kind(requests: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Split `requests` into `{kind: [tag_name, ...]}`, preserving order.

    Args:
        requests: `parse_media_tags()`'s own output.

    Returns:
        One list per `MEDIA_TAG_PREFIXES` value, in encounter order within
        each group — the grouping `MediaResolver.resolve()`'s own grouped-
        output contract is built from.
    """
    grouped: dict[str, list[str]] = {kind: [] for kind in MEDIA_TAG_PREFIXES.values()}
    for kind, tag_name in requests:
        grouped.setdefault(kind, []).append(tag_name)
    return grouped


class FilesystemMediaResolver:  # pylint: disable=too-few-public-methods
    """Resolves media tags against a game's own files, from either source.

    A tag names a file's path relative to the game's root, exactly as the
    author wrote it: `image: church/church_front.jpg` resolves to
    `church/church_front.jpg` within the game, checked for real
    existence. This resolver imposes NO directory convention of its own,
    and does no stem matching or casefold scanning. A tag with no
    extension tries each of `EXTENSION_FALLBACKS` in order until one
    exists.

    **What `resolve()` returns depends on the source**, because the two
    cannot answer the same way: a directory yields an absolute filesystem
    path an application can turn into a `file://` URI, while a bundle has no such
    path and yields a `data:` URI carrying the bytes. Both are strings a
    browser loads directly from an `<img>`/`<video>` `src`, which is what
    every application does with them, so the difference does not reach the application's
    own code.
    """

    def __init__(self, source: GameSource | Path, resolver_module: ModuleType | None = None, logger: logging.Logger | None = None) -> None:
        """
        Args:
            source: The game's files. A `Path` is accepted and wrapped as
                a `DirectoryGameSource`, since a directory is the
                development path and every existing caller passes one.
            resolver_module: The game's own resolver module, if it ships
                one. A game converted from elsewhere may have tags that
                are not paths at all -- a character key, say, that maps
                to a folder through a table only that game knows. Such a
                game answers for its own tags here; every other game
                needs nothing and passes None.
            logger: Where to report a raising game resolver.
        """
        self._source: GameSource = DirectoryGameSource(source) if isinstance(source, Path) else source
        self._resolver_module = resolver_module
        self._logger = logger or logging.getLogger(__name__)

    def resolve(self, requests: list[tuple[str, str]]) -> list[str]:
        """Resolve a turn's media requests against the game's own files.

        Args:
            requests: `parse_media_tags()`'s own output for this turn.

        Returns:
            One string per request whose file genuinely exists, grouped by
            kind (see `MediaResolver.resolve()`'s own contract). An
            absolute filesystem path from a directory, a `data:` URI from
            a bundle — see this class's own docstring.
        """
        grouped = _group_by_kind(requests)
        resolved: list[str] = []
        for kind in MEDIA_TAG_PREFIXES.values():
            for tag_name in grouped.get(kind, []):
                target = self._resolve_one(tag_name, kind)
                if target is not None:
                    resolved.append(target)
        return resolved

    def _resolve_one(self, tag_name: str, kind: str = "image") -> str | None:
        """Resolve one tag to a real file within the game.

        A game shipping its own resolver is asked first; the path-based
        lookup below is the answer for every game that does not, and the
        fallback when a game's resolver declines a tag.

        Args:
            tag_name: The tag's own name, as `parse_media_tags()` returned
                it — a path relative to the game's root, with or without
                an extension, exactly as the game author wrote it.
            kind: The media kind this tag named ("image"/"video"), passed
                to a game resolver so it can treat the two differently.

        Returns:
            The resolved reference, checked as given first, then with each
            of `EXTENSION_FALLBACKS` appended in turn. None if no such
            file exists under any tried extension.
        """
        from_game = self._ask_game(kind, tag_name)
        if from_game is not None:
            return from_game

        if self._source.exists(tag_name):
            return self.reference(tag_name)
        if PurePosixPath(tag_name).suffix:
            # The tag already names an extension that didn't exist above
            # -- trying a different one on top of it would silently
            # invent a second, unintended candidate path.
            return None
        for extension in EXTENSION_FALLBACKS:
            candidate = f"{tag_name}{extension}"
            if self._source.exists(candidate):
                return self.reference(candidate)
        return None

    def _ask_game(self, kind: str, tag_name: str) -> str | None:
        """Ask a game's own resolver what one of its tags means.

        Modelled on `game_panel.run_panel_hook()`: called by keyword, and
        absent, raising, or answering a non-string all mean "no answer"
        rather than an error. A broken resolver must not take a turn
        down; the tag simply goes unresolved, exactly as an unresolvable
        path-based tag already does.

        Args:
            kind: The media kind ("image"/"video").
            tag_name: The tag as the game author wrote it.

        Returns:
            A displayable reference, or None to fall through to the
            path-based lookup.
        """
        hook = getattr(self._resolver_module, RESOLVE_TAG_HOOK, None) if self._resolver_module is not None else None
        if not callable(hook):
            return None
        try:
            result = hook(kind=kind, tag=tag_name, source=self._source, reference=self.reference)
        except Exception:  # pylint: disable=broad-except
            self._logger.exception("ink_engine.media_resolver: %s failed for %r; falling back", RESOLVE_TAG_HOOK, tag_name)
            return None
        return result if isinstance(result, str) and result else None

    def reference(self, relative: str) -> str:
        """Return the string an application can display for one resolved file."""
        if isinstance(self._source, DirectoryGameSource):
            return str((self._source.root / relative).resolve())
        return _data_uri(relative, self._source.read_bytes(relative))


def _data_uri(relative: str, payload: bytes) -> str:
    """Return a `data:` URI for one file's bytes.

    A bundle's files have no filesystem path, so the bytes travel inline.
    The media type is taken from the extension: a browser will not render
    an image served as `application/octet-stream`.

    Args:
        relative: The file's game-relative path, for its extension.
        payload: The file's bytes.

    Returns:
        A `data:<type>;base64,...` URI.
    """
    media_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    return f"data:{media_type};base64,{base64.b64encode(payload).decode('ascii')}"
