"""Containers: what makes a holder a container, as the inventory slot holds it.

A companion to `inventory.py`. A container's contents live in the
inventory's own `holder_items` like any other holder's, so a container
record adds only what makes it different from a person: whether it can
be shut, whether it is shut now, and whether you can see in while it is.

A holder must be marked a container explicitly; one is never inferred
from having contents.

This module holds the record's shape and the two questions asked of it;
the operations (declare, open, put in, take from) are `Inventory`'s own
methods. **A holder with no record is always reachable and always shows
its contents.**
"""

from __future__ import annotations

from typing import TypedDict


class ContainerRecord(TypedDict, total=False):
    """One container's either/or properties, as the slot holds them.

    Every key is optional so a save written before a property existed
    still reads with that property's default.

    Attributes:
        openable: Whether the container can be opened and shut at all.
            Defaults False, meaning permanently open (Inform's default),
            so an ordinary always-open container costs nothing to declare.
        is_open: Whether it is open right now. Meaningless unless
            `openable`; a non-openable container is always treated as
            open.
        transparent: Whether its contents can be SEEN while shut. A
            transparent container shows what is inside but still has to be
            opened before anything can be taken out.
        expires_when_empty: Whether the declaration is dropped the moment
            it holds nothing -- a wrapper only ever emptied, never
            refilled (a gift package, a burst pod). It stops being a
            container from then on, as if never declared.
    """

    openable: bool
    is_open: bool
    transparent: bool
    expires_when_empty: bool


def accepts_reach(record: ContainerRecord) -> bool:
    """Return whether anything can be taken out of a container right now.

    Args:
        record: The container's record.

    Returns:
        True when the container is open, or not openable at all.
    """
    return bool(record.get("is_open", True)) or not record.get("openable", False)


def reveals_contents(record: ContainerRecord) -> bool:
    """Return whether a container's contents are visible right now.

    Args:
        record: The container's record.

    Returns:
        True when reachable, or when shut but transparent.
    """
    return accepts_reach(record) or bool(record.get("transparent", False))
