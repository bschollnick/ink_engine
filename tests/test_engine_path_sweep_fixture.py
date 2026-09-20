"""Every container in a large story resolves to itself.

The targeted tests in `test_engine_paths.py` prove the path MECHANISM
works. They cannot show it holds across a whole story: a change that
perturbs path strings in one rarely-taken branch passes them all.

So this sweeps every container in `structural_sweep.ink` -- a generated
story carrying the constructs that decide how containers nest (knots,
stitches, weave with nested gathers, tunnels, threads, sequences,
conditionals, once-only and guarded choices) at a scale no hand-written
fixture reaches. It is the committed counterpart to a local sweep over a
real multi-thousand-knot game, which only runs where that game exists.

The invariant is the one saves depend on: `visit_counts` is stored by
path and restored by resolution, so a path that resolves elsewhere is a
visit count silently attached to the wrong container.
"""

from __future__ import annotations

import json
from pathlib import Path as FilePath
from unittest import TestCase

from ink_engine.engine import (
    Container,
    Path,
    _container_path,
    load_story_root,
    resolve_path,
)

FIXTURES = FilePath(__file__).parent / "fixtures"

#: Below this, the fixture has stopped being a scale test and the
#: assertions here would pass vacuously.
MINIMUM_CONTAINERS = 4000


def _load() -> dict:
    with open(FIXTURES / "structural_sweep.json", encoding="utf-8") as story_file:
        return json.load(story_file)


def _every_container(root: Container) -> list[Container]:
    """Return every container reachable from `root`, root included."""
    found: list[Container] = []
    seen: set[int] = set()

    def walk(container: Container) -> None:
        if id(container) in seen:
            return
        seen.add(id(container))
        found.append(container)
        for item in container.content:
            if isinstance(item, Container):
                walk(item)
        for item in container.named_content.values():
            if isinstance(item, Container):
                walk(item)

    walk(root)
    return found


class FixturePathSweepTests(TestCase):
    """The whole tree, not a sample."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = load_story_root(_load())
        cls.containers = _every_container(cls.root)

    def test_the_tree_is_the_size_it_was(self):
        """A collapse in the container count would make every other
        assertion here vacuous without failing anything."""
        self.assertGreater(len(self.containers), MINIMUM_CONTAINERS)

    def test_every_container_resolves_to_itself(self):
        """`_container_path()` writes it, `resolve_path()` reads it back,
        within one tree."""
        wrong: list[str] = []
        for container in self.containers:
            if container is self.root:
                continue  # the root's own path is empty by construction
            path_string = _container_path(container)
            if resolve_path(self.root, Path.parse(path_string)) is not container:
                wrong.append(path_string)
        self.assertEqual(wrong, [], f"{len(wrong)} container(s) do not round-trip, e.g. {wrong[:5]}")

    def test_paths_address_the_same_content_in_a_SEPARATELY_built_tree(self):
        """The assertion that actually guards saves.

        A save stores path strings written against one tree and resolves
        them against another, built later from the same JSON. Checking a
        single tree against itself cannot detect drift -- both sides move
        together, so a tree whose indices have shifted still passes.
        """
        other_root = load_story_root(_load())

        wrong: list[str] = []
        for container in self.containers:
            if container is self.root:
                continue
            path_string = _container_path(container)
            elsewhere = resolve_path(other_root, Path.parse(path_string))
            if not isinstance(elsewhere, Container):
                wrong.append(f"{path_string} (unresolvable)")
            elif _container_path(elsewhere) != path_string:
                wrong.append(f"{path_string} -> {_container_path(elsewhere)}")
        self.assertEqual(wrong, [], f"{len(wrong)} path(s) address different content across builds, e.g. {wrong[:5]}")

    def test_every_path_string_is_unique(self):
        """Two containers sharing a path string would collide in
        `visit_counts` serialization, one silently overwriting the
        other."""
        by_path: dict[str, int] = {}
        for container in self.containers:
            if container is self.root:
                continue
            path_string = _container_path(container)
            by_path[path_string] = by_path.get(path_string, 0) + 1
        collisions = {path: count for path, count in by_path.items() if count > 1}
        self.assertEqual(collisions, {}, f"path strings shared by more than one container: {list(collisions)[:5]}")


class FixtureLazyTreeEquivalenceTests(TestCase):
    """A lazily-built tree must be indistinguishable from a full one.

    Laziness defers a story's knots, which are named-only children of the
    root -- absent from `content`, so deferring them cannot disturb the
    positional indices `_container_path()` addresses by. That is the
    argument; these are the assertions that hold it to account.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = _load()

    def test_a_lazy_root_defers_its_knots(self):
        """Otherwise the rest of this class proves nothing."""
        lazy = load_story_root(self.source, full_build=False)
        self.assertTrue(lazy.has_deferred_content)
        self.assertEqual(len(lazy.named_content), 0)

    def test_materializing_yields_the_same_containers(self):
        full = load_story_root(self.source)
        lazy = load_story_root(self.source, full_build=False)
        lazy.materialize_all()
        self.assertEqual(len(_every_container(lazy)), len(_every_container(full)))

    def test_every_path_addresses_the_same_content_in_both(self):
        """A path string written against a full tree is resolved against
        whatever tree the next request builds, which may be lazy."""
        full = load_story_root(self.source)
        lazy = load_story_root(self.source, full_build=False)

        wrong: list[str] = []
        for container in _every_container(full)[1:]:
            path_string = _container_path(container)
            resolved = resolve_path(lazy, Path.parse(path_string))
            if not isinstance(resolved, Container):
                wrong.append(f"{path_string} (unresolvable)")
            elif _container_path(resolved) != path_string:
                wrong.append(f"{path_string} -> {_container_path(resolved)}")
        self.assertEqual(wrong, [], f"{len(wrong)} path(s) differ against a lazy tree, e.g. {wrong[:5]}")
