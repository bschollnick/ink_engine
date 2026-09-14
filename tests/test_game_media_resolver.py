"""A game answering for its own media tags.

A tag is a path for a game authored against this engine. A game converted
from elsewhere may have tags that are not paths at all — a character key
mapping to a folder through a table only that game knows — so it answers
for its own. The engine learns none of those rules.
"""

from __future__ import annotations

import shutil
import tempfile
import types
import zipfile
from pathlib import Path
from unittest import TestCase

from ink_engine.game_source import DirectoryGameSource, ZipGameSource
from ink_engine.media_resolver import FilesystemMediaResolver

FILES = {
    "Images/door.jpg": b"\xff\xd8" + b"d" * 40,
    "Images/People/Catherine/x.jpg": b"\xff\xd8" + b"c" * 40,
}


def _resolver_module(*, raises: bool = False, returns: object = "") -> types.ModuleType:
    """Build a stand-in for a game's own `image_resolver.py`."""
    module = types.ModuleType("image_resolver")
    mapping = {"catherineross": "Catherine"}

    def resolve_tag(*, kind, tag, source, reference):
        if raises:
            raise RuntimeError("boom")
        if returns != "":
            return returns
        prefix, _separator, rest = tag.partition("/")
        if not rest:
            return None
        if prefix == "shared":
            candidate = f"Images/{rest}"
        elif prefix in mapping:
            candidate = f"Images/People/{mapping[prefix]}/{rest}"
        else:
            return None
        return reference(candidate) if source.exists(candidate) else None

    module.resolve_tag = resolve_tag
    return module


class GameResolverTestCase(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        game = self.tmp / "game"
        for relative, payload in FILES.items():
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        self.directory = DirectoryGameSource(game)

        bundle = self.tmp / "game.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            for relative, payload in FILES.items():
                archive.writestr(f"game/{relative}", payload)
        self.bundle = ZipGameSource(bundle)
        self.addCleanup(self.bundle.close)

    def _resolve(self, source, tag, module=None):
        return FilesystemMediaResolver(source, resolver_module=module).resolve([("image", tag)])


class WithoutAGameResolverTests(GameResolverTestCase):
    """Every game that needs nothing must behave exactly as before."""

    def test_a_path_tag_still_resolves(self):
        self.assertEqual(len(self._resolve(self.directory, "Images/door.jpg")), 1)

    def test_an_extensionless_path_tag_still_resolves(self):
        self.assertEqual(len(self._resolve(self.directory, "Images/door")), 1)

    def test_a_non_path_tag_resolves_to_nothing(self):
        self.assertEqual(self._resolve(self.directory, "catherineross/x.jpg"), [])


class WithAGameResolverTests(GameResolverTestCase):
    def test_a_character_key_resolves_through_the_games_own_table(self):
        resolved = self._resolve(self.directory, "catherineross/x.jpg", _resolver_module())
        self.assertEqual(len(resolved), 1)
        self.assertTrue(resolved[0].endswith("Catherine/x.jpg"))

    def test_a_games_synthetic_namespace_resolves(self):
        resolved = self._resolve(self.directory, "shared/door.jpg", _resolver_module())
        self.assertEqual(len(resolved), 1)

    def test_the_same_tag_resolves_from_a_bundle_as_a_data_uri(self):
        """The game resolver is handed the source, so it works from
        either without knowing which it has."""
        resolved = self._resolve(self.bundle, "catherineross/x.jpg", _resolver_module())
        self.assertEqual(len(resolved), 1)
        self.assertTrue(resolved[0].startswith("data:image/jpeg;base64,"))

    def test_a_tag_the_game_declines_falls_back_to_the_path_lookup(self):
        """Declining is not failing: a game may resolve its own scheme and
        leave ordinary paths to the engine."""
        resolved = self._resolve(self.directory, "Images/door.jpg", _resolver_module())
        self.assertEqual(len(resolved), 1)

    def test_a_tag_nothing_can_resolve_yields_nothing(self):
        self.assertEqual(self._resolve(self.directory, "unknown/x.jpg", _resolver_module()), [])


class BrokenGameResolverTests(GameResolverTestCase):
    """A game's resolver must not be able to take a turn down."""

    def test_a_raising_resolver_falls_back_rather_than_propagating(self):
        resolved = self._resolve(self.directory, "Images/door.jpg", _resolver_module(raises=True))
        self.assertEqual(len(resolved), 1)

    def test_a_resolver_returning_a_non_string_is_ignored(self):
        self.assertEqual(len(self._resolve(self.directory, "Images/door.jpg", _resolver_module(returns=42))), 1)

    def test_a_resolver_returning_an_empty_string_is_ignored(self):
        """An empty reference would render as a broken image; treat it as
        no answer and let the path lookup try."""
        self.assertEqual(len(self._resolve(self.directory, "Images/door.jpg", _resolver_module(returns=""))), 1)

    def test_a_module_without_the_hook_is_ignored(self):
        self.assertEqual(len(self._resolve(self.directory, "Images/door.jpg", types.ModuleType("empty"))), 1)
