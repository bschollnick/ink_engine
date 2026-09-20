"""Has inkle's documentation moved since the pinned snapshot? (network)

`docs/inkles-ink-standard/retrieved-<date>/` holds verbatim copies of
inkle's own Ink documentation, pinned to the text this engine was written
against. Nothing tells us when inkle edits it, so this check asks.

Opt-in, because it reaches the network: run it with

    INK_ENGINE_CHECK_UPSTREAM=1 python -m pytest tests/test_vendored_standard_is_current.py

It is skipped in an ordinary run, and skipped rather than failed when the
network is unreachable -- "GitHub was down" is not a documentation change.

A difference is not a defect. It means inkle has revised the standard and
someone should read the diff, decide whether it affects this engine, and
-- if it is worth pinning -- add a new `retrieved-<date>/` directory
beside the old one. Never edit a pinned snapshot in place.

**Compare text, not bytes.** Upstream serves CRLF line endings and the
vendored copies are LF, so a byte comparison reports every line of the
largest file as changed on every run. That false alarm is the reason this
check normalizes line endings before comparing.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path as FilePath
from unittest import TestCase, skipUnless

#: Set to 1 to run this check; it is skipped otherwise.
CHECK_UPSTREAM = os.environ.get("INK_ENGINE_CHECK_UPSTREAM") == "1"

#: The pinned snapshot this engine was written against.
VENDORED = FilePath(__file__).parent.parent / "docs" / "inkles-ink-standard" / "retrieved-2026-09-02"

#: Where each vendored file came from, as the vendoring README records.
DOCUMENTATION_URL = "https://raw.githubusercontent.com/inkle/ink/master/Documentation/{name}"
LICENCE_URL = "https://raw.githubusercontent.com/inkle/ink/master/LICENSE.txt"

FETCH_TIMEOUT_SECONDS = 30


def _upstream_url(name: str) -> str:
    """Return the raw URL a vendored file was taken from."""
    return LICENCE_URL if name == "LICENSE.txt" else DOCUMENTATION_URL.format(name=name)


def _normalized(text: str) -> str:
    """Return `text` with line endings and trailing blank lines levelled."""
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")


@skipUnless(CHECK_UPSTREAM, "set INK_ENGINE_CHECK_UPSTREAM=1 to check inkle's documentation")
class VendoredStandardIsCurrent(TestCase):
    """Each pinned file still matches what inkle publishes today."""

    def test_every_vendored_file_matches_upstream(self) -> None:
        """Report every pinned file inkle has since revised."""
        revised: list[str] = []
        for local in sorted(VENDORED.iterdir()):
            if not local.is_file():
                continue
            url = _upstream_url(local.name)
            try:
                with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:
                    upstream = response.read().decode("utf-8")
            except (urllib.error.URLError, TimeoutError) as error:
                self.skipTest(f"cannot reach {url}: {error}")
            if _normalized(upstream) != _normalized(local.read_text(encoding="utf-8")):
                revised.append(local.name)

        self.assertEqual(
            revised,
            [],
            "inkle has revised these documents since the pinned snapshot: "
            f"{', '.join(revised)}. Read the upstream diff, decide whether it "
            "affects this engine, and pin a new retrieved-<date>/ directory "
            "beside the existing one rather than editing it.",
        )
