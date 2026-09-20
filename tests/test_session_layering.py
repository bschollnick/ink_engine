"""The session library is a tenant of this repo, not part of the engine.

It ships here because `ink_engine` is the one package both applications already
depend on. When a second IF engine appears it moves out, and that move
must be a package relocation rather than an untangling -- which holds only
while the dependency runs one way.
"""

from __future__ import annotations

import ast
from pathlib import Path as FilePath
from unittest import TestCase as SimpleTestCase

ENGINE = FilePath(__file__).parent.parent / "ink_engine"
SESSION = FilePath(__file__).parent.parent / "if_session"


def _imported_modules(source: FilePath) -> set[str]:
    """Return every top-level package `source` imports."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


class OneWayDependencyTests(SimpleTestCase):
    """A cycle here is what turns a future relocation into a rewrite."""

    def test_the_engine_never_imports_the_session_library(self):
        offenders = [
            module.relative_to(ENGINE.parent)
            for module in sorted(ENGINE.rglob("*.py"))
            if "if_session" in _imported_modules(module)
        ]
        self.assertEqual(offenders, [], f"the interpreter must not depend on its tenant: {offenders}")

    def test_the_session_library_reaches_the_engine_narrowly(self):
        """Every engine module it names is a line to rewrite when a second
        engine arrives, so the list is asserted rather than merely kept
        small by intent."""
        reached = set()
        for module in sorted(SESSION.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("ink_engine"):
                    reached.add(node.module)
        self.assertEqual(reached, {"ink_engine.media_resolver"})
