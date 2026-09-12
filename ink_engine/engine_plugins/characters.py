"""Per-character keyed storage, and one vocabulary for asking about a
character.

A game's characters accumulate small private facts -- "has this one been
introduced", numbered switches meaningful to one storyline. This module
gives them a shape: `character_id -> {key: value}`.

It owns **only** that. Where a character is, what they can do, how charmed
they are, what they carry belong to `character_occupancy`, `skills` and an
inventory system. The character API reads through to whichever plugin owns
each fact, so a story asks every question in one vocabulary with no
duplicated state -- `current_location()` holds nothing and answers from
the occupancy slot.

Values must be JSON-safe scalars. A game's per-PLACE keyed state goes in
`location_graph`'s own slot, so a place and a character sharing a name
cannot collide.
"""

from __future__ import annotations

from typing import TypedDict

from ink_engine.engine_plugins.character_occupancy import STATE_KEY as _OCCUPANCY_STATE_KEY
from ink_engine.plugin_base import BindingContext, StatefulPlugin, external, query

#: Where this plugin's state lives in a session's `EngineState`. Published
#: so a dependent plugin or a game names the slot by constant rather than
#: by a copied string literal.
STATE_KEY = "characters"

# What an attribute may hold. Deliberately narrow: these values are
# serialized into a session's own state, so anything that does not survive
# a JSON round-trip cannot go here.
AttributeValue = bool | int | float | str


class CharacterSlot(TypedDict):
    """A session's per-character attributes, and its known-character set.

    Attributes:
        records: character_id -> `{"attributes": {name: value}}`. A
            character with nothing stored yet has no entry; reading an
            unset attribute returns a caller-supplied default rather
            than raising.
        known: The characters the player has met, sorted so the saved
            form is stable. Its own list rather than an attribute, as in
            `location_graph`.
    """

    records: dict[str, dict[str, dict[str, AttributeValue]]]
    known: list[str]


class Characters(StatefulPlugin[CharacterSlot]):
    """Per-character facts and the known-character set."""

    name = "characters"
    display_name = "Characters"
    state_key = STATE_KEY
    slot_type = CharacterSlot
    fields = {"records": dict, "known": list}

    @query
    @external
    def read_attribute(self, slot: CharacterSlot, character_id: str, attribute: str, default: AttributeValue = False) -> AttributeValue:
        """Return one stored attribute.

        Args:
            slot: This session's slot.
            character_id: Whose record to read -- a character, or whatever
                else a story keys this storage by.
            attribute: The attribute name.
            default: What to return when unset. False by default, since
                the commonest use is a story flag whose absence means
                "this has not happened".

        Returns:
            The stored value, or `default`.
        """
        return slot.get("records", {}).get(character_id, {}).get("attributes", {}).get(attribute, default)

    @external
    def set_attribute(self, slot: CharacterSlot, character_id: str, attribute: str, value: AttributeValue) -> None:
        """Store one attribute.

        Args:
            slot: This session's slot.
            character_id: Whose record to write.
            attribute: The attribute name.
            value: The value to store.
        """
        slot.setdefault("records", {}).setdefault(character_id, {}).setdefault("attributes", {})[attribute] = value

    @query
    @external
    def attribute_exists(self, slot: CharacterSlot, character_id: str, attribute: str) -> bool:
        """Return whether an attribute has ever been stored.

        Distinct from reading it: a stored `False` and an unset attribute
        both read as false, and a story sometimes needs to tell them apart.

        Args:
            slot: This session's slot.
            character_id: Whose record to check.
            attribute: The attribute name.

        Returns:
            True if the attribute is present, whatever its value.
        """
        return attribute in slot.get("records", {}).get(character_id, {}).get("attributes", {})

    @external
    def clear_attributes(self, slot: CharacterSlot, character_id: str) -> None:
        """Remove every attribute from one character, keeping their known-state.

        Forgetting the details of someone is not the same as never having
        met them.

        Args:
            slot: This session's slot.
            character_id: The character to clear.
        """
        slot.get("records", {}).pop(character_id, None)

    def attributes(self, slot: CharacterSlot, character_id: str) -> dict[str, AttributeValue]:
        """Return an independent copy of one character's attributes.

        Args:
            slot: This session's slot.
            character_id: Whose record to copy.

        Returns:
            `{attribute name: value}`, empty for a character with nothing
            stored.
        """
        return dict(slot.get("records", {}).get(character_id, {}).get("attributes", {}))

    @query
    @external
    def character_known(self, slot: CharacterSlot, character_id: str) -> bool:
        """Return whether the player has met this character.

        Args:
            slot: This session's slot.
            character_id: The character being asked about.

        Returns:
            True once `set_character_known()` has marked them met.
        """
        return character_id in slot.get("known", ())

    @external
    def set_character_known(self, slot: CharacterSlot, character_id: str, known: bool) -> None:
        """Mark a character met, or not.

        One setter taking a boolean rather than two mark/unmark
        functions, mirroring `location_graph.set_known()`. Marking an
        already-known character, or forgetting one never met, is harmless:
        story content re-runs.

        Args:
            slot: This session's slot.
            character_id: The character to mark.
            known: True to mark them met, False to take the meeting back
                (an erased memory, a mistaken identity).
        """
        met = set(slot.get("known", ()))
        if known:
            met.add(character_id)
        else:
            met.discard(character_id)
        slot["known"] = sorted(met)

    def known_characters(self, slot: CharacterSlot) -> list[str]:
        """Return every character the player has met.

        Args:
            slot: This session's slot.

        Returns:
            The known character ids, sorted for a stable answer.
        """
        return sorted(slot.get("known", ()))

    @external(needs_context=True)
    def current_location(self, context: BindingContext[CharacterSlot], character_id: str) -> str:
        """Return where a character is, read from the occupancy slot.

        This plugin stores no location of its own.

        Args:
            context: This session, for the occupancy slot.
            character_id: The character being asked about.

        Returns:
            The character's location id, or "" when they are nowhere
            (Ink has no None).
        """
        return context.slot_of(_OCCUPANCY_STATE_KEY).get("locations", {}).get(character_id, "")


CHARACTERS = Characters()
PLUGIN = CHARACTERS.plugin()
