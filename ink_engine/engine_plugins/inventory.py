"""InventorySystem: a generic item-placement and holder-inventory framework.

A reusable engine service a story's own item system builds on. This module
has zero knowledge of what any item IS: an item is a plain string id the
game layer chooses, and only its whereabouts are tracked here. Item names,
display text, prices, currency and per-item behaviour all belong in the
game's own bridge module.

**Two things are tracked, mutually exclusive per item:** `item_locations`
maps an item to the location it lies in, and `holder_items` maps a holder
to the items it carries and how many of each. An item held by someone has
no `item_locations` entry at all.

A "holder" is any opaque id string -- the player, an NPC, a chest, a body
being possessed. This module never distinguishes between them, which is
what makes give-to-a-person, take-from-a-person and put-in-a-container the
same operation.

The store is `{item_id: count}`; the boolean case is a count of 1. A
holder may declare a maximum number of DISTINCT items (adding more of
something already held never trips it), and exceeding it raises
`InventoryFullError`.

**A library, not a discoverable plugin.** `Inventory` publishes no Ink
binding of its own: a game subclasses it, names the bindings its story
uses, and activates its own plugin. Every check happens before anything
is written, so a refused operation leaves the slot exactly as it was.
"""

from __future__ import annotations

from typing import Any, TypedDict

from ink_engine.engine_plugins.containers import ContainerRecord, accepts_reach, reveals_contents
from ink_engine.plugin_base import StatefulPlugin

# --------------------------------------------------------------------------
# Tunable limits
#
# Every bound this module enforces is a constant here, so changing one is
# a single edit rather than a hunt through call sites.
# --------------------------------------------------------------------------

#: A limit value meaning "no limit at all". Used for both stack size and
#: slot count, so a caller never has to remember which sentinel goes where.
UNLIMITED = 0

#: How many units of ONE item a holder may keep in its slot, when the game
#: layer sets nothing. Configurable per holder via `set_stack_limit()`.
DEFAULT_STACK_LIMIT = 25

#: The hardest ceiling this API accepts for a stack. More than this is
#: rejected rather than clamped, so a typo like 2000 surfaces as an error
#: instead of silently becoming something else.
MAX_STACK_LIMIT = 100

#: How many DISTINCT items a holder may carry when the game layer sets
#: nothing: uncapped until a game says otherwise.
DEFAULT_SLOT_LIMIT = UNLIMITED

#: How many items one WORN slot holds when the game layer declares no
#: capacity for it. One is the ordinary case (a neck holds one necklace);
#: a game wanting two rings on one hand declares `{"finger": 2}` rather
#: than inventing a second slot name.
DEFAULT_WORN_SLOT_CAPACITY = 1

#: The hardest ceiling this API accepts for a worn slot's capacity, same
#: guard shape as MAX_STACK_LIMIT: rejected, never clamped.
MAX_WORN_SLOT_CAPACITY = 100


class InventoryError(Exception):
    """Base class for this module's closed set of failure modes."""


class InventoryFullError(InventoryError):
    """A holder already carries its maximum number of distinct items."""


class StackFullError(InventoryError):
    """One item's slot is already at its stack limit.

    Distinct from `InventoryFullError`: a holder can hit this with slots
    still free.
    """


class InvalidLimitError(InventoryError):
    """A caller asked for a limit this API will not accept.

    Out-of-range limits raise; they are never clamped.
    """


class ItemNotHeldError(InventoryError):
    """A holder was asked to give up an item it does not have enough of.

    Covers both "does not hold it at all" and "holds fewer than the count
    asked for".
    """


class SlotOccupiedError(InventoryError):
    """A worn slot is already full.

    Distinct from `InventoryFullError`, which is about carrying capacity.
    """


class ContainerClosedError(InventoryError):
    """A container was reached into while shut.

    Raised whether or not the container is transparent: seeing in does
    not permit taking out.
    """


class InventorySlot(TypedDict):
    """A session's item placements and per-holder inventories.

    Attributes:
        item_locations: item_id -> location_id, for items lying in the
            world. An item held by someone has NO entry here: held and
            on-the-ground are mutually exclusive.
        holder_items: holder_id -> {item_id: count}. Counts are always
            >= 1; an item reaching 0 is removed rather than left as a
            zero entry.
        capacities: holder_id -> maximum number of DISTINCT items, or None
            for unlimited. A holder with no entry is unlimited.
        stack_limits: holder_id -> how many units of ONE item fit in its
            slot, defaulting to DEFAULT_STACK_LIMIT. A property of the
            SLOT, not the item.
        containers: holder_id -> its container record, for holders that
            are containers. A holder with no entry is an ordinary holder.
        worn: holder_id -> slot_name -> [item_id, ...]. Slot names are
            chosen by the game layer and opaque here, like item ids. A
            worn item stays in `holder_items` too: wearing requires
            holding.
        worn_slot_capacities: slot_name -> how many items that slot holds,
            defaulting to DEFAULT_WORN_SLOT_CAPACITY. Global, not
            per-holder: a slot's capacity is a fact about the game's
            anatomy.
    """

    item_locations: dict[str, str]
    holder_items: dict[str, dict[str, int]]
    capacities: dict[str, int | None]
    stack_limits: dict[str, int]
    containers: dict[str, ContainerRecord]
    worn: dict[str, dict[str, list[str]]]
    worn_slot_capacities: dict[str, int]


class Inventory(StatefulPlugin[InventorySlot]):
    """Item placements, holder inventories, capacity, worn slots and containers.

    A game subclasses this, keeps the methods as its Python API, and adds
    the Ink bindings its story calls under its own plugin name.
    """

    name = "inventory"
    display_name = "Inventory"
    state_key = "inventory"
    slot_type = InventorySlot
    fields = {
        "item_locations": dict,
        "holder_items": dict,
        "capacities": dict,
        "stack_limits": dict,
        "containers": dict,
        "worn": dict,
        "worn_slot_capacities": dict,
    }

    # -- world placement ----------------------------------------------------------

    def place_item(self, slot: InventorySlot, item_id: str, location_id: str) -> None:
        """Put an item down at a location, taking it from whoever held it.

        Args:
            slot: This session's slot.
            item_id: The item to place.
            location_id: Where it now lies.
        """
        for holder_id, items in slot.setdefault("holder_items", {}).items():
            if items.pop(item_id, None) is not None:
                self._stop_wearing(slot, holder_id, item_id)
        slot.setdefault("item_locations", {})[item_id] = location_id

    def remove_from_world(self, slot: InventorySlot, item_id: str) -> None:
        """Remove an item from play entirely -- no location, no holder.

        Removing an item that is already nowhere is not an error, so a
        story can call this unconditionally.

        Args:
            slot: This session's slot.
            item_id: The item to remove.
        """
        slot.get("item_locations", {}).pop(item_id, None)
        for holder_id, items in slot.get("holder_items", {}).items():
            if items.pop(item_id, None) is not None:
                self._stop_wearing(slot, holder_id, item_id)

    def item_location(self, slot: InventorySlot, item_id: str) -> str | None:
        """Return the location an item is lying in, if any.

        Args:
            slot: This session's slot.
            item_id: The item to look up.

        Returns:
            The location id, or None when the item is held by someone or
            is not in play at all. Use `item_holder()` to tell those two
            apart.
        """
        return slot.get("item_locations", {}).get(item_id)

    def items_at_location(self, slot: InventorySlot, location_id: str) -> frozenset[str]:
        """Return every item lying at a location.

        Args:
            slot: This session's slot.
            location_id: The location to inspect.

        Returns:
            The item ids lying there -- held items are never included.
        """
        return frozenset(item_id for item_id, where in slot.get("item_locations", {}).items() if where == location_id)

    # -- holders (characters and containers alike) ---------------------------------

    def set_capacity(self, slot: InventorySlot, holder_id: str, limit: int | None) -> None:
        """Set how many DISTINCT items a holder may carry.

        Args:
            slot: This session's slot.
            holder_id: The holder to limit.
            limit: The maximum number of distinct items, or None for
                unlimited. Setting a limit below what the holder already
                carries is allowed and drops nothing -- no NEW distinct
                item can be added until something goes.
        """
        slot.setdefault("capacities", {})[holder_id] = limit

    def capacity(self, slot: InventorySlot, holder_id: str) -> int | None:
        """Return a holder's distinct-item limit.

        Args:
            slot: This session's slot.
            holder_id: The holder to inspect.

        Returns:
            The limit, or None when the holder is unlimited.
        """
        return slot.get("capacities", {}).get(holder_id)

    def set_stack_limit(self, slot: InventorySlot, holder_id: str, limit: int) -> None:
        """Set how many units of ONE item fit in this holder's slot.

        The limit belongs to the slot, not the item: one value applies to
        everything the holder carries. Lowering a limit below what is
        already stacked drops nothing.

        Args:
            slot: This session's slot.
            holder_id: The holder to limit.
            limit: Units per slot. `UNLIMITED` (0) for no limit, 1 to
                allow only a single unit, up to `MAX_STACK_LIMIT`.

        Raises:
            InvalidLimitError: `limit` is negative, or above
                MAX_STACK_LIMIT. Rejected rather than clamped so a typo
                surfaces as an error.
        """
        if limit < 0:
            raise InvalidLimitError(f"stack limit must be >= 0 ({UNLIMITED} means unlimited), got {limit}")
        if limit > MAX_STACK_LIMIT:
            raise InvalidLimitError(f"stack limit {limit} exceeds MAX_STACK_LIMIT ({MAX_STACK_LIMIT})")
        slot.setdefault("stack_limits", {})[holder_id] = limit

    def stack_limit(self, slot: InventorySlot, holder_id: str) -> int:
        """Return how many units of one item this holder may stack.

        Args:
            slot: This session's slot.
            holder_id: The holder to inspect.

        Returns:
            The limit, or `DEFAULT_STACK_LIMIT` when the holder has none
            set. `UNLIMITED` (0) means no limit.
        """
        return slot.get("stack_limits", {}).get(holder_id, DEFAULT_STACK_LIMIT)

    def _check_stack_room(self, slot: InventorySlot, holder_id: str, item_id: str, count: int) -> None:
        """Raise if adding `count` would overflow this holder's slot.

        Args:
            slot: This session's slot.
            holder_id: The receiving holder.
            item_id: The item being added.
            count: How many units are being added.

        Raises:
            StackFullError: The resulting stack would exceed the limit.
                The slot is NOT topped up to the limit -- the whole
                addition is refused, so the caller can leave the surplus
                where it was.
        """
        limit = self.stack_limit(slot, holder_id)
        if limit == UNLIMITED:
            return
        held = self.item_count(slot, holder_id, item_id)
        if held + count > limit:
            raise StackFullError(f"holder '{holder_id}' cannot stack {count} more '{item_id}' (has {held}, limit {limit})")

    def _capacity_load(self, slot: InventorySlot, holder_id: str) -> int:
        """Return how many distinct items count against a holder's capacity.

        Worn items do not count.
        """
        held = slot.get("holder_items", {}).get(holder_id, {})
        if not held:
            return 0
        worn = self.worn_items(slot, holder_id)
        return sum(1 for item_id in held if item_id not in worn)

    def _check_room_for(self, slot: InventorySlot, holder_id: str, item_id: str, count: int) -> None:
        """Raise if a holder cannot receive `count` of an item.

        Args:
            slot: This session's slot.
            holder_id: The receiving holder.
            item_id: The item being added.
            count: How many.

        Raises:
            InventoryFullError: The holder is at its distinct-item
                capacity and this item would be a NEW distinct entry.
            StackFullError: The holder already has this item at its
                stack limit.
        """
        held = slot.get("holder_items", {}).get(holder_id, {})
        limit = self.capacity(slot, holder_id)
        if limit is not None and item_id not in held and self._capacity_load(slot, holder_id) >= limit:
            raise InventoryFullError(f"holder '{holder_id}' already carries {self._capacity_load(slot, holder_id)} distinct item(s), its limit")
        self._check_stack_room(slot, holder_id, item_id, count)

    def give_item(self, slot: InventorySlot, holder_id: str, item_id: str, count: int = 1) -> None:
        """Give a holder an item, taking it out of the world.

        Args:
            slot: This session's slot.
            holder_id: Who receives it.
            item_id: What they receive.
            count: How many. Must be >= 1.

        Raises:
            ValueError: `count` is less than 1.
            InventoryFullError: The holder is at its distinct-item
                capacity and this item would be a NEW distinct entry.
                Adding more of something already held never raises this.
            StackFullError: The holder already has this item at its stack
                limit. This can happen with slots still free.
        """
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")
        self._check_room_for(slot, holder_id, item_id, count)
        slot.get("item_locations", {}).pop(item_id, None)
        held = slot.setdefault("holder_items", {}).setdefault(holder_id, {})
        held[item_id] = held.get(item_id, 0) + count

    def take_item(self, slot: InventorySlot, holder_id: str, item_id: str, count: int = 1) -> None:
        """Take an item away from a holder, removing it from play.

        To move an item from one holder to another, use `transfer_item()`;
        to put it on the ground, use `place_item()`.

        Args:
            slot: This session's slot.
            holder_id: Who loses it.
            item_id: What they lose.
            count: How many. Must be >= 1.

        Raises:
            ValueError: `count` is less than 1.
            ItemNotHeldError: The holder does not hold at least `count`
                of it.
        """
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")
        if self.item_count(slot, holder_id, item_id) < count:
            raise ItemNotHeldError(f"holder '{holder_id}' does not hold {count} of '{item_id}'")
        held = slot["holder_items"][holder_id]
        remaining = held[item_id] - count
        if remaining > 0:
            held[item_id] = remaining
        else:
            del held[item_id]
            self._stop_wearing(slot, holder_id, item_id)

    def has_item(self, slot: InventorySlot, holder_id: str, item_id: str) -> bool:
        """Return whether a holder has at least one of an item.

        Args:
            slot: This session's slot.
            holder_id: The holder to check.
            item_id: The item to look for.

        Returns:
            True when the holder carries one or more.
        """
        return self.item_count(slot, holder_id, item_id) > 0

    def item_count(self, slot: InventorySlot, holder_id: str, item_id: str) -> int:
        """Return how many of an item a holder carries.

        Args:
            slot: This session's slot.
            holder_id: The holder to check.
            item_id: The item to count.

        Returns:
            The count, or 0 when the holder has none.
        """
        return slot.get("holder_items", {}).get(holder_id, {}).get(item_id, 0)

    def held_items(self, slot: InventorySlot, holder_id: str) -> dict[str, int]:
        """Return everything a holder carries.

        Args:
            slot: This session's slot.
            holder_id: The holder to inspect.

        Returns:
            An independent copy of {item_id: count}.
        """
        return dict(slot.get("holder_items", {}).get(holder_id, {}))

    def item_holder(self, slot: InventorySlot, item_id: str) -> str | None:
        """Return which holder currently carries an item.

        Args:
            slot: This session's slot.
            item_id: The item to trace.

        Returns:
            The holder id, or None when the item is on the ground or out
            of play.
        """
        for holder_id, items in slot.get("holder_items", {}).items():
            if items.get(item_id, 0) > 0:
                return holder_id
        return None

    def transfer_item(self, slot: InventorySlot, from_holder: str, to_holder: str, item_id: str, count: int = 1) -> None:
        """Move an item from one holder to another.

        Args:
            slot: This session's slot.
            from_holder: Who gives it up.
            to_holder: Who receives it.
            item_id: What moves.
            count: How many. Must be >= 1.

        Raises:
            ValueError: `count` is less than 1.
            ItemNotHeldError: `from_holder` does not hold enough of it.
            InventoryFullError: `to_holder` is at its distinct-item
                capacity.
            StackFullError: `to_holder` already has this item at its
                stack limit.
        """
        if count < 1:
            raise ValueError(f"count must be >= 1, got {count}")
        if self.item_count(slot, from_holder, item_id) < count:
            raise ItemNotHeldError(f"holder '{from_holder}' does not hold {count} of '{item_id}'")
        self._check_room_for(slot, to_holder, item_id, count)
        self.take_item(slot, from_holder, item_id, count)
        held = slot["holder_items"].setdefault(to_holder, {})
        held[item_id] = held.get(item_id, 0) + count

    # -- worn slots -----------------------------------------------------------------
    #
    # An OPTIONAL capability: slot names are chosen by the game layer and
    # are opaque here, like item ids. A game that declares no slots never
    # wears anything, and every method below is inert for it.

    def set_worn_slot_capacity(self, slot: InventorySlot, worn_slot: str, slot_capacity: int) -> None:
        """Declare how many items one worn slot holds.

        Args:
            slot: This session's slot.
            worn_slot: The game's slot name.
            slot_capacity: How many items fit. Must be >= 1 and no greater
                than MAX_WORN_SLOT_CAPACITY. Zero is rejected too: a slot
                holding everything is not a constraint.

        Raises:
            InvalidLimitError: `slot_capacity` is out of range.
        """
        if slot_capacity < 1 or slot_capacity > MAX_WORN_SLOT_CAPACITY:
            raise InvalidLimitError(f"worn slot capacity must be 1..{MAX_WORN_SLOT_CAPACITY}, got {slot_capacity}")
        slot.setdefault("worn_slot_capacities", {})[worn_slot] = slot_capacity

    def worn_slot_capacity(self, slot: InventorySlot, worn_slot: str) -> int:
        """Return how many items a worn slot holds.

        Args:
            slot: This session's slot.
            worn_slot: The slot name to look up.

        Returns:
            The declared capacity, or DEFAULT_WORN_SLOT_CAPACITY.
        """
        return slot.get("worn_slot_capacities", {}).get(worn_slot, DEFAULT_WORN_SLOT_CAPACITY)

    def wear_item(self, slot: InventorySlot, holder_id: str, item_id: str, worn_slot: str) -> None:
        """Put a held item on, into one of the game's worn slots.

        Wearing requires holding: the item stays in `holder_items` and is
        additionally recorded as worn. Wearing something already worn in
        that slot is idempotent rather than an error.

        Args:
            slot: This session's slot.
            holder_id: Who is putting it on.
            item_id: What they are putting on.
            worn_slot: Which of the game's slots it occupies.

        Raises:
            ItemNotHeldError: The holder does not have the item.
            SlotOccupiedError: The slot is already at its capacity.
                Nothing is displaced to make room, since which item to
                remove is the story's decision.
        """
        if not self.has_item(slot, holder_id, item_id):
            raise ItemNotHeldError(f"holder '{holder_id}' does not hold '{item_id}'")
        occupants = slot.get("worn", {}).get(holder_id, {}).get(worn_slot, [])
        if item_id in occupants:
            return
        if len(occupants) >= self.worn_slot_capacity(slot, worn_slot):
            raise SlotOccupiedError(f"slot '{worn_slot}' on holder '{holder_id}' already holds {len(occupants)} item(s), its capacity")
        slot.setdefault("worn", {}).setdefault(holder_id, {}).setdefault(worn_slot, []).append(item_id)

    def _stop_wearing(self, slot: InventorySlot, holder_id: str, item_id: str) -> None:
        """Drop one item from a holder's worn index.

        `worn` is an index over `holder_items`, so call this wherever an
        item stops being held.
        """
        worn = slot.get("worn", {})
        slots = worn.get(holder_id)
        if not slots:
            return
        for worn_slot, occupants in list(slots.items()):
            if item_id not in occupants:
                continue
            remaining = [worn_id for worn_id in occupants if worn_id != item_id]
            if remaining:
                slots[worn_slot] = remaining
            else:
                del slots[worn_slot]
        if not slots:
            del worn[holder_id]

    def remove_worn_item(self, slot: InventorySlot, holder_id: str, item_id: str) -> None:
        """Take a worn item off, leaving it held.

        Taking off something that was not worn is not an error -- the end
        state the caller asked for is already true.

        Args:
            slot: This session's slot.
            holder_id: Who is taking it off.
            item_id: What they are taking off.
        """
        self._stop_wearing(slot, holder_id, item_id)

    def is_worn(self, slot: InventorySlot, holder_id: str, item_id: str) -> bool:
        """Return whether a holder is currently wearing an item.

        Args:
            slot: This session's slot.
            holder_id: Whose worn items to check.
            item_id: The item in question.

        Returns:
            True when the item occupies any of that holder's slots.
        """
        return item_id in self.worn_items(slot, holder_id)

    def worn_items(self, slot: InventorySlot, holder_id: str) -> frozenset[str]:
        """Return everything a holder is wearing, across all slots.

        Args:
            slot: This session's slot.
            holder_id: Whose worn items to list.

        Returns:
            Every worn item id. Empty for a holder wearing nothing.
        """
        slots = slot.get("worn", {}).get(holder_id)
        if not slots:
            return frozenset()
        return frozenset(item_id for occupants in slots.values() for item_id in occupants)

    def worn_in_slot(self, slot: InventorySlot, holder_id: str, worn_slot: str) -> tuple[str, ...]:
        """Return what occupies one of a holder's worn slots.

        Args:
            slot: This session's slot.
            holder_id: Whose slot to inspect.
            worn_slot: Which slot.

        Returns:
            The occupying item ids in the order they were put on. Empty
            when the slot is free.
        """
        return tuple(slot.get("worn", {}).get(holder_id, {}).get(worn_slot, ()))

    # -- containers -------------------------------------------------------------------

    def declare_container(  # pylint: disable=too-many-arguments
        self,
        slot: InventorySlot,
        holder_id: str,
        *,
        openable: bool = False,
        is_open: bool = True,
        transparent: bool = False,
        expires_when_empty: bool = False,
    ) -> None:
        """Mark a holder as a container.

        Args:
            slot: This session's slot.
            holder_id: The holder to mark.
            openable: Whether it can be opened and shut at all. Defaults
                False, meaning permanently open.
            is_open: Whether it starts open. Ignored unless `openable`.
            transparent: Whether contents are visible while shut.
            expires_when_empty: Whether the declaration itself is dropped
                the moment the container is emptied -- see
                `ContainerRecord`. A story that declares one this way
                should also give it its starting contents before anything
                can observe it empty, or it expires on the very next
                `take_from_container` call.
        """
        record: ContainerRecord = {"openable": openable, "is_open": is_open, "transparent": transparent, "expires_when_empty": expires_when_empty}
        slot.setdefault("containers", {})[holder_id] = record

    def is_container(self, slot: InventorySlot, holder_id: str) -> bool:
        """Return whether a holder has been declared a container.

        Args:
            slot: This session's slot.
            holder_id: The holder to test.

        Returns:
            True when the holder was declared via `declare_container()`.
        """
        return holder_id in slot.get("containers", {})

    def set_container_open(self, slot: InventorySlot, holder_id: str, is_open: bool) -> None:
        """Open or shut a container.

        A holder that is not a container, or one that is not openable, is
        left unchanged rather than raising -- a story asking to open
        something permanently open has already got what it wanted.

        Args:
            slot: This session's slot.
            holder_id: The container to operate.
            is_open: True to open, False to shut.
        """
        record = slot.get("containers", {}).get(holder_id)
        if record is None or not record.get("openable", False):
            return
        record["is_open"] = is_open

    def is_container_open(self, slot: InventorySlot, holder_id: str) -> bool:
        """Return whether a container can currently be reached into.

        Args:
            slot: This session's slot.
            holder_id: The container to test.

        Returns:
            True when it is open or not openable. A holder that is not a
            container is always reachable.
        """
        record = slot.get("containers", {}).get(holder_id)
        return True if record is None else accepts_reach(record)

    def visible_contents(self, slot: InventorySlot, holder_id: str) -> dict[str, int]:
        """Return what can be SEEN inside a holder right now.

        Args:
            slot: This session's slot.
            holder_id: The holder to look into.

        Returns:
            {item_id: count} when the contents are visible -- always, for
            an ordinary holder or an open container, and also for a shut
            TRANSPARENT one. Empty for a shut opaque container.
        """
        record = slot.get("containers", {}).get(holder_id)
        if record is not None and not reveals_contents(record):
            return {}
        return self.held_items(slot, holder_id)

    def take_from_container(self, slot: InventorySlot, holder_id: str, to_holder: str, item_id: str, count: int = 1) -> None:
        """Take an item out of a container.

        If the container declares `expires_when_empty` and this take
        leaves it holding nothing, the declaration itself is dropped: it
        stops being a container, as if never declared. The holder
        underneath is untouched.

        Args:
            slot: This session's slot.
            holder_id: The container to take from.
            to_holder: Who receives it.
            item_id: What to take.
            count: How many.

        Raises:
            ContainerClosedError: The container is shut. Being transparent
                does not help -- seeing inside is not reaching inside.
            ItemNotHeldError: The container does not hold enough of it.
            InventoryFullError: The receiver is at its distinct-item
                capacity.
            StackFullError: The receiver is at its stack limit for this
                item.
        """
        if not self.is_container_open(slot, holder_id):
            raise ContainerClosedError(f"container '{holder_id}' is shut")
        self.transfer_item(slot, holder_id, to_holder, item_id, count)
        record = slot.get("containers", {}).get(holder_id)
        if record is not None and record.get("expires_when_empty", False) and not self.held_items(slot, holder_id):
            del slot["containers"][holder_id]

    def put_in_container(self, slot: InventorySlot, from_holder: str, holder_id: str, item_id: str, count: int = 1) -> None:
        """Put an item into a container.

        Args:
            slot: This session's slot.
            from_holder: Who is putting it in.
            holder_id: The container to put it in.
            item_id: What to put in.
            count: How many.

        Raises:
            ContainerClosedError: The container is shut.
            ItemNotHeldError: The giver does not hold enough of it.
            InventoryFullError: The container is at its distinct-item
                capacity.
            StackFullError: The container is at its stack limit for this
                item.
        """
        if not self.is_container_open(slot, holder_id):
            raise ContainerClosedError(f"container '{holder_id}' is shut")
        self.transfer_item(slot, from_holder, holder_id, item_id, count)


INVENTORY = Inventory()
