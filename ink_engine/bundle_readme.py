"""The companion readme written beside a bundle.

A bundle's own hashes prove "this is the same bundle I saw before" but
not "this bundle is safe" — an attacker who rewrites an archive
recomputes them all. Publishing the hashes in a file that travels
*separately* gives a verifier something the bundle's author did not
supply inside the bundle.

It is also, plainly, what a human wants: what this game is, who made it,
what it needs, without opening a ZIP.

Every value is derived from the manifest, the plan, or the hashes just
computed — nothing is hand-written, so the readme cannot drift from the
bundle it describes. It is regenerated on every build.

Written **beside** the bundle, never inside it: an entry would be one
more thing to hash, and would defeat the point of an out-of-band copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Fields quoted verbatim into the requirements table, in display order,
#: each with the label it is shown under.
_REQUIREMENT_LABELS: tuple[tuple[str, str], ...] = (
    ("ENGINE_FORMAT", "Story format"),
    ("ENGINE_VERSION", "Minimum engine"),
    ("PLAY_LAYOUT", "Layout"),
)


def _format_size(byte_count: int) -> str:
    """Return a human-readable size, e.g. `4.4 GB`."""
    size = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def render_readme(
    manifest: dict[str, Any],
    *,
    bundle_name: str,
    bundle_bytes: int,
    file_count: int,
    story_sha256: str,
    directory_sha256: str,
    manifest_sha256: str,
) -> str:
    """Render the companion readme for one built bundle.

    Args:
        manifest: The game's manifest, as read from the game folder.
        bundle_name: The bundle file's own name.
        bundle_bytes: The bundle's size on disk.
        file_count: How many files it contains.
        story_sha256: The compiled story's hash.
        directory_sha256: The archive directory's hash.
        manifest_sha256: The manifest's hash, as recorded in the archive
            comment.

    Returns:
        The readme's full Markdown text.
    """
    title = str(manifest.get("GAME_TITLE") or Path(bundle_name).stem)
    lines = [f"# {title}", ""]

    facts = [f"**Bundle:** `{bundle_name}` ({_format_size(bundle_bytes)}, {file_count:,} files)"]
    if manifest.get("GAME_AUTHOR"):
        facts.append(f"**Author:** {manifest['GAME_AUTHOR']}")
    if manifest.get("GAME_VERSION"):
        facts.append(f"**Version:** {manifest['GAME_VERSION']}")
    if manifest.get("SOURCE_GAME_VERSION"):
        facts.append(f"**Converted from:** {manifest['SOURCE_GAME_VERSION']}")
    lines.extend(["  \n".join(facts), ""])

    description = str(manifest.get("GAME_DESCRIPTION") or "").strip()
    if description:
        lines.extend([description, ""])

    lines.extend(
        [
            "## Verification",
            "",
            "These hashes are published here so they can be checked against a",
            "copy of the bundle that did not travel with them.",
            "",
            "| Value | SHA-256 |",
            "|---|---|",
        ]
    )
    story_file = manifest.get("MAIN_STORY_FILE")
    if story_sha256 and isinstance(story_file, str):
        lines.append(f"| Story (`{story_file}`) | `{story_sha256}` |")
    lines.append(f"| Bundle directory | `{directory_sha256}` |")
    lines.append(f"| Manifest | `{manifest_sha256}` |")
    lines.extend(["", f"Verify with: `ink-bundle verify {bundle_name}`", ""])

    requirements = [(label, manifest[field]) for field, label in _REQUIREMENT_LABELS if manifest.get(field)]
    plugins = manifest.get("REQUIRED_PLUGINS")
    questions = manifest.get("NEW_GAME_FIELDS")
    if requirements or plugins or questions:
        lines.extend(["## Requirements", ""])
        for label, value in requirements:
            lines.append(f"**{label}:** {value}  ")
        if isinstance(plugins, list) and plugins:
            lines.append(f"**Plugins ({len(plugins)}):** {', '.join(str(name) for name in plugins)}  ")
        if isinstance(questions, list) and questions:
            lines.append(f"**Character creation:** {len(questions)} question(s) before play begins  ")
        lines.append("")

    return "\n".join(lines)
