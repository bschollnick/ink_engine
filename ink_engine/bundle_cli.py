"""Command-line game bundler: `python -m ink_engine.bundle_cli <game_dir>`.

Three subcommands over `ink_engine.bundler`: `inspect` reports what a
bundle would contain without writing one, `build` writes it, and `verify`
reads a built bundle back the way an application will.

`inspect` exists because a manifest-declared bundle fails quietly in one
direction: a media directory the manifest forgets is simply absent, and
the game plays until it reaches the missing art. Seeing the per-declaration
file counts is how an author confirms the manifest names everything the
game needs before shipping.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from ink_engine.bundle_integrity import verify_bundle
from ink_engine.bundler import (
    BundleError,
    BundlePlan,
    build_bundle,
    open_bundle_manifest,
    select_bundle_contents,
    stale_sources,
    verify_plan,
)
from ink_engine.game_folder import (
    MANIFEST_FILENAME,
    MEDIA_DIRECTORIES_FIELD,
    GameFolderError,
)

#: Suffix rows shown in `inspect`'s file-type breakdown; beyond this the
#: tail is long-tail noise rather than evidence.
MAX_SUFFIX_ROWS = 8

#: Stale sources listed before the rest are summarised as a count.
MAX_STALE_LISTED = 5


def _format_size(byte_count: int) -> str:
    """Return a human-readable size, e.g. `4.4 GB`."""
    size = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _print_plan(plan: BundlePlan) -> None:
    """Report what the manifest put in the bundle, and what it named that
    is missing."""
    print(f"Game folder : {plan.game_dir}")
    print(f"Package name: {plan.package_name}")
    print(f"Main story  : {plan.main_story_file or '(resolved by suffix)'}")
    print()
    print(f"Included: {len(plan.included)} files, {_format_size(plan.total_bytes)}")
    print("\n  by manifest declaration:")
    for reason, count in plan.counts_by_reason().items():
        print(f"    {count:>6}  {reason}")
    print("\n  by file type:")
    for suffix, count in list(plan.counts_by_suffix().items())[:MAX_SUFFIX_ROWS]:
        print(f"    {count:>6}  {suffix}")

    if plan.missing:
        print(f"\nMISSING: {len(plan.missing)} declared but not on disk")
        for declared, reason in plan.missing:
            print(f"    {declared}  ({reason})")


def _report_staleness(plan: BundlePlan) -> bool:
    """Warn if the compiled story predates its `.ink` sources.

    Args:
        plan: The plan whose game folder and story to check.

    Returns:
        True if any source is newer than the compiled story.
    """
    stale = stale_sources(plan.game_dir, plan.main_story_file)
    if not stale:
        return False
    story = plan.main_story_file or "the compiled story"
    print(f"\nWARNING: {len(stale)} .ink source(s) are newer than {story}.")
    print("         The bundle would ship the PREVIOUSLY compiled content.")
    for path in stale[:MAX_STALE_LISTED]:
        print(f"         {path.relative_to(plan.game_dir)}")
    if len(stale) > MAX_STALE_LISTED:
        print(f"         ... and {len(stale) - MAX_STALE_LISTED} more")
    print("         Recompile, or pass --allow-stale to bundle anyway.")
    return True


def _command_inspect(arguments: argparse.Namespace) -> int:
    """Report a plan without writing anything."""
    plan = select_bundle_contents(Path(arguments.game_dir), package_name=arguments.package_name)
    _print_plan(plan)
    stale = _report_staleness(plan)
    problems = verify_plan(plan)
    if problems:
        print("\nWould NOT produce a playable bundle:")
        for problem in problems:
            print(f"    - {problem}")
        return 1
    if not plan.counts_by_reason().get("game package"):
        print("\nBundle would be playable.")
        return 0
    if not any(reason.startswith(MEDIA_DIRECTORIES_FIELD) for reason in plan.counts_by_reason()):
        print(f"\nNote: the manifest declares no {MEDIA_DIRECTORIES_FIELD}, so no media is bundled.")
        print(f"      Add {MEDIA_DIRECTORIES_FIELD} = [...] if this game ships images or video.")
    print("\nBundle would be playable.")
    return 1 if stale else 0


def _command_build(arguments: argparse.Namespace) -> int:
    """Write a bundle."""
    game_dir = Path(arguments.game_dir)
    plan = select_bundle_contents(game_dir, package_name=arguments.package_name)
    output = Path(arguments.output) if arguments.output else game_dir.parent / f"{plan.package_name}.zip"

    if not arguments.quiet:
        _print_plan(plan)

    if _report_staleness(plan) and not arguments.allow_stale:
        print("\nRefusing to build a bundle from a stale story.", file=sys.stderr)
        return 1
    if not arguments.quiet:
        print()

    written = 0

    def report(_relative: Path) -> None:
        nonlocal written
        written += 1
        if not arguments.quiet and written % 500 == 0:
            print(f"    ... {written}/{len(plan.included)} files", flush=True)

    built = build_bundle(plan, output, progress=report)
    size = built.stat().st_size
    print(f"Wrote {built} ({_format_size(size)}, {len(plan.included)} files)")
    if plan.total_bytes:
        print(f"Compression: {100 * size / plan.total_bytes:.1f}% of uncompressed size")
    return 0


def _command_verify(arguments: argparse.Namespace) -> int:
    """Read a built bundle back the way an application will."""
    bundle_path = Path(arguments.bundle)
    if not bundle_path.is_file():
        print(f"No such bundle: {bundle_path}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(bundle_path) as archive:
        entries = archive.namelist()
    manifest = open_bundle_manifest(bundle_path)

    print(f"Bundle  : {bundle_path}")
    print(f"Entries : {len(entries)}")
    print(f"Size    : {_format_size(bundle_path.stat().st_size)}")
    print(f"Title   : {manifest.get('GAME_TITLE', '(untitled)')}")
    print(f"Story   : {manifest.get('MAIN_STORY_FILE', '(resolved by suffix)')}")
    print(f"Layout  : {manifest.get('PLAY_LAYOUT', '(application default)')}")

    required = manifest.get("REQUIRED_PLUGINS")
    if isinstance(required, list):
        print(f"Plugins : {len(required)} declared")
        for name in required:
            print(f"          {name}")

    story = manifest.get("MAIN_STORY_FILE")
    if isinstance(story, str):
        package = next((name.split("/")[0] for name in entries if name.endswith(f"/{MANIFEST_FILENAME}")), "")
        if f"{package}/{story}" not in entries:
            print(f"\nBROKEN: manifest names '{story}' but the bundle does not contain it", file=sys.stderr)
            return 1

    problems = verify_bundle(bundle_path)
    if problems:
        print("\nINTEGRITY CHECK FAILED — this bundle has been modified since it was built:", file=sys.stderr)
        for problem in problems:
            print(f"    - {problem}", file=sys.stderr)
        return 1
    print("\nIntegrity: all recorded hashes match.")

    readme = bundle_path.with_suffix(".md")
    if readme.is_file():
        print(f"Companion readme: {readme.name}")
    else:
        # Not a failure: the readme travels separately by design, so a
        # bundle received on its own legitimately arrives without one.
        print("Companion readme: absent (cannot cross-check hashes out of band)")

    print("\nBundle opens correctly.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this tool."""
    parser = argparse.ArgumentParser(
        prog="ink-bundle",
        description="Build a distributable .zip bundle from an Ink game folder.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, handler, help_text in (
        ("inspect", _command_inspect, "report what a bundle would contain, writing nothing"),
        ("build", _command_build, "write the bundle"),
    ):
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.add_argument("game_dir", help="the game folder to bundle")
        subparser.add_argument("--package-name", default=None, help="top-level package name (default: the folder's name)")
        if name == "build":
            subparser.add_argument("-o", "--output", default=None, help="output path (default: <game_dir>/../<package>.zip)")
            subparser.add_argument("-q", "--quiet", action="store_true", help="print only the final result")
            subparser.add_argument(
                "--allow-stale",
                action="store_true",
                help="build even though .ink sources are newer than the compiled story",
            )
        subparser.set_defaults(handler=handler)

    verify = subparsers.add_parser("verify", help="read a built bundle back and report its manifest")
    verify.add_argument("bundle", help="the .zip bundle to verify")
    verify.set_defaults(handler=_command_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the bundler CLI.

    Args:
        argv: Command-line arguments, or None to read `sys.argv`.

    Returns:
        A process exit status: 0 on success, 1 on a real, reported failure.
    """
    arguments = build_parser().parse_args(argv)
    try:
        exit_status: int = arguments.handler(arguments)
        return exit_status
    except (BundleError, GameFolderError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
