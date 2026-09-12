"""Media-tag resolution: turning a turn's `# image: <tag>`/`# video: <tag>`
Ink tags into displayable URLs or paths.

What a tag resolves TO is host-specific; splitting a turn's raw tag list
into `(kind, tag_name)` pairs is not, so `parse_media_tags` lives here
once and `MediaResolver` is the seam each host implements. A host picks
its implementation by ordinary import — no registry, since a story is
played by exactly one host at a time.

The `image:`/`video:` prefixes are this project's convention, not Ink's:
Ink tags are untyped metadata handed to the game verbatim, with no notion
of media kind or directory layout. Nothing here invents one either — a
tag's string is a path the game author chose, used as written.

`FilesystemMediaResolver` therefore does a plain per-tag existence check
under the game's own directory: no catch-all media folder, per-kind
subdirectory, stem matching, or upfront scan. A host whose media library
maintains its own indirection has a real reason for a tag not to be a
path, but that is a separate implementation of the same seam, and neither
one's behaviour belongs in the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

#: Ink tag prefix -> the media kind it names. Order matters: `resolve()`'s
#: own grouped-output contract (all images, then all videos) follows this
#: dict's own iteration order, matching the prefix-scan behavior every real
#: host already implements today.
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


def find_cover_image(game_dir: Path) -> str | None:
    """Return a game folder's own cover image, by a fixed filename
    convention — no manifest field, no Ink tag.

    Looks for `cover.<ext>` (any of `COVER_EXTENSION_FALLBACKS`) directly
    under `game_dir`, then under `game_dir/images/` — the same
    does-it-exist philosophy `FilesystemMediaResolver` uses, structural
    rather than story-driven, since a cover is a fact about the game
    folder itself, not something an Ink tag ever names.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The resolved absolute path to `cover.<ext>`, or None if no such
        file exists in either location — deciding what to show instead
        (a generic placeholder icon) is the caller's own concern, not
        this function's; `ink_engine` has no opinion on host UI.
    """
    for search_dir in COVER_SEARCH_DIRS:
        for extension in COVER_EXTENSION_FALLBACKS:
            candidate = game_dir / search_dir / f"cover{extension}"
            if candidate.is_file():
                return str(candidate.resolve())
    return None


#: Filename `find_prose_styles()` looks for, directly under `game_dir` —
#: fixed convention, same as `find_cover_image()`.
PROSE_STYLES_FILENAME = "styles.css"


def find_prose_styles(game_dir: Path) -> str | None:
    """Return a game folder's own prose-styling CSS, if it supplies one.

    Looks for `styles.css` directly under `game_dir` — a fixed filename
    convention, no manifest field. A story tags a span of prose with an
    inline `<style=name>...</style>` marker (this project's own inline-tag
    convention, not part of the Ink language); this file is where a game
    defines what each `name` actually renders as (font, size, colour).
    Entirely optional — a host applies its own baseline style names first,
    and this file's rules load after, so a game can override any baseline
    name or add its own without the host knowing about it in advance.

    Args:
        game_dir: The game folder's real filesystem path.

    Returns:
        The file's raw text content, or None if the game folder supplies
        no such file. Reading and injecting that CSS into a page is the
        host's own concern — `ink_engine` has no opinion on host UI.
    """
    candidate = game_dir / PROSE_STYLES_FILENAME
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return None


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
    """Resolves media tags directly against a real game folder's own files
    — the standalone player's implementation, needing no database, no
    upfront directory scan, and no lookup table of any kind.

    A tag names a file's own path relative to the game folder's own root,
    exactly as the game author wrote it: `image: church/church_front.jpg`
    resolves to `<game_dir>/church/church_front.jpg`, checked for real
    existence on disk, nothing more. Where a game organizes its own files
    is entirely the game's own choice, expressed by what path it writes
    into its own tags — this resolver imposes NO directory convention of
    its own (no `images/`/`video/` split, no other fixed subdirectory) and
    does not care which media kind a tag was (`image:` vs `video:`) beyond
    using it to group the output. A tag with no extension of its own tries
    each of `EXTENSION_FALLBACKS` in order until one exists.

    No filename-stem matching, no casefold scan, no override dictionary —
    the tag already names its own file's exact real path. This is
    deliberate: see this module's own docstring for why a standalone game
    folder needs none of the indirection a database-indexed resolver
    exists for.
    """

    def __init__(self, game_dir: Path) -> None:
        """
        Args:
            game_dir: The game folder's real filesystem path (the
                directory holding `__init__.py`/`story.inkj`, and every
                media file a tag might name, wherever the game itself
                chose to put them).
        """
        self._game_dir = game_dir

    def resolve(self, requests: list[tuple[str, str]]) -> list[str]:
        """Resolve a turn's media requests directly against the game
        folder's own files.

        Args:
            requests: `parse_media_tags()`'s own output for this turn.

        Returns:
            One path per request whose file genuinely exists on disk,
            grouped by kind (see `MediaResolver.resolve()`'s own
            contract) — an absolute filesystem path string; turning that
            into a `file://` URI or a served-loopback path is a host
            application's own concern, not this resolver's.
        """
        grouped = _group_by_kind(requests)
        resolved: list[str] = []
        for kind in MEDIA_TAG_PREFIXES.values():
            for tag_name in grouped.get(kind, []):
                target = self._resolve_one(tag_name)
                if target is not None:
                    resolved.append(target)
        return resolved

    def _resolve_one(self, tag_name: str) -> str | None:
        """Resolve one tag directly to a real file under the game folder.

        Args:
            tag_name: The tag's own name, as `parse_media_tags()` returned
                it — a path relative to the game folder's own root, with
                or without an extension, exactly as the game author wrote
                it.

        Returns:
            The resolved absolute path, if a real file exists there —
            checked as given first, then with each of
            `EXTENSION_FALLBACKS` appended in turn. None if no such file
            exists under any tried extension.
        """
        candidate = self._game_dir / tag_name
        if candidate.is_file():
            return str(candidate.resolve())
        if candidate.suffix:
            # The tag already names an extension that didn't exist above
            # -- trying a different one on top of it would silently
            # invent a second, unintended candidate path.
            return None
        for extension in EXTENSION_FALLBACKS:
            with_extension = self._game_dir / f"{tag_name}{extension}"
            if with_extension.is_file():
                return str(with_extension.resolve())
        return None
