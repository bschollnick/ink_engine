"""Description-slot lookup for items: one text, chosen from three layers.

A companion to `inventory.py`, sharing no state with it: the inventory
tracks where things are, this module what a thing READS as.

**All text belongs to the caller.** This module holds no strings of its
own: slot names, authored text and default templates are supplied by the
game layer, exactly as item ids are. It performs only the walk from most
specific to least — the item's own authored string for a slot, then the
game's fallback template formatted with the item's display name, then
empty.

Text that varies at runtime is not this module's business: a description
depending on story state is rendered by the story layer.
"""

from __future__ import annotations


def describe(
    slot: str,
    *,
    authored: dict[str, str] | None = None,
    defaults: dict[str, str] | None = None,
    name: str = "",
) -> str:
    """Return the text for one of an item's description slots.

    Args:
        slot: Which description is wanted. Opaque here; the game layer
            decides what slots exist and what they mean.
        authored: This item's own text, per slot, or None when the item
            authored none.
        defaults: The game's fallback templates, per slot. A template may
            contain `{name}`, which is replaced with `name`.
        name: The item's display name, for formatting a default template.

    Returns:
        The authored string when there is one; otherwise the formatted
        default; otherwise an empty string when the game supplied no
        default for this slot either.
    """
    if authored:
        text = authored.get(slot)
        if text:
            return text
    if defaults:
        template = defaults.get(slot)
        if template:
            return template.format(name=name)
    return ""
