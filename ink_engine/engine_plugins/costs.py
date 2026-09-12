"""CostTable: what an action costs, and whether it can be afforded.

A game charges for things -- mana for a spell, time for a turn, money for
a purchase -- and the amount usually depends on circumstance: a first cast
is cheaper than the rest, a skill discounts a whole category, one route
takes longer than another. Without somewhere to put that, those numbers
end up spread across the story's own content as literals, and the same
cost is then written in several places that drift apart.

This module is that somewhere. A story declares its costs as config; this
plugin holds them and answers `cost_of(...)`. It knows nothing about mana,
minutes or money: a cost has a RESOURCE name (a plain string the game
chooses) and an AMOUNT, and what those mean is entirely the game's.

**Lookup, not charging.** This plugin does not debit anything. The
resources a game spends live in whichever plugin owns them -- a clock in
`scheduling`, a currency in the game's own module -- and a `pay()` here
would have to reach into all of them, coupling three systems to save one
call. The caller looks the cost up and spends it through whatever owns
that resource.

**Variants** are how a conditional cost stays data. A cost may declare
named alternatives -- `{"amount": 20, "variants": {"first": 10}}` -- and
the caller names one when the condition holds. The condition itself stays
where it belongs (a character attribute, a skill, a quest stage); this
plugin only holds the number that goes with it. That keeps a cost table
from growing a rules engine, which is the failure mode it exists to
prevent.

**Declared prices are definition; the slot holds only what play changed.**
A game's price list is given to the constructor and read live from the
instance, so a new version of the game reaches every save automatically.
The session slot holds only costs declared or changed during play, which
take precedence. A host may also attach a price list as per-story config;
that is seeded into the slot once, when the session starts, exactly as if
the story had declared those costs itself.
"""

from __future__ import annotations

from typing import Any, TypedDict

from ink_engine.engine_config_schemas import (
    SystemConfigValidationError,
    require_dict,
    require_number,
    require_str,
)
from ink_engine.plugin_base import StatefulPlugin, external, query

# The state slot this plugin owns, named as a module constant so a
# dependent plugin can read it via `engine_state.get(STATE_KEY, {})`
# without a hardcoded string literal.
STATE_KEY = "cost_table"


class CostSlot(TypedDict):
    """A session's own cost table.

    Attributes:
        costs: cost key -> that cost's declaration: `{"resource": str,
            "amount": number, "variants": {name: number}}`. Only what
            play declared or changed; declared prices stay on the plugin.
    """

    costs: dict[str, dict[str, Any]]


def validate_cost_table(config: Any) -> None:
    """Validate a `cost_table` config.

    ```json
    {
        "costs": {
            "spell.transform": {
                "resource": "mana",
                "amount": 20,
                "variants": {"first": 10}
            }
        }
    }
    ```

    A cost names the RESOURCE it is paid in and the AMOUNT. `variants`
    are named alternatives a caller selects when its condition holds -- a
    first cast, a discount a skill grants -- so a conditional price stays
    data instead of becoming a rules engine here. The condition itself is
    never declared: it lives wherever the fact does, and the caller names
    the variant.

    An empty table is valid. A story may declare the system, opt into its
    bindings, and price nothing yet.

    Args:
        config: The already-JSON-decoded config value to validate.

    Raises:
        SystemConfigValidationError: If the shape doesn't match.
    """
    root = require_dict(config, "cost_table config")
    costs = require_dict(root.get("costs", {}), "cost_table.costs")
    for cost_key, cost in costs.items():
        require_str(cost_key, "cost_table.costs key")
        path = f"cost_table.costs.{cost_key}"
        cost_dict = require_dict(cost, path)
        require_str(cost_dict.get("resource"), f"{path}.resource")
        require_number(cost_dict.get("amount"), f"{path}.amount")
        variants = cost_dict.get("variants", {})
        if not isinstance(variants, dict):
            raise SystemConfigValidationError(f"{path}.variants must be a dictionary of name -> amount")
        for variant_name, amount in variants.items():
            require_str(variant_name, f"{path}.variants key")
            require_number(amount, f"{path}.variants.{variant_name}")


class CostTable(StatefulPlugin[CostSlot]):
    """The cost table: declared prices on the instance, play's changes in the slot.

    A game ships its prices by instantiating this class with its config
    under its own name: `CostTable(name="my_game_costs", display_name=...,
    config={"costs": {...}})`.
    """

    name = "cost_table"
    display_name = "Cost table"
    state_key = STATE_KEY
    slot_type = CostSlot
    fields = {"costs": dict}

    def __init__(self, *, name: str | None = None, display_name: str | None = None, config: Any = None) -> None:
        """Build a cost table, optionally with a game's declared prices.

        Args:
            name: Override the plugin name, for a game's configured copy.
            display_name: Override the display name.
            config: The game's price list, in the shape
                `validate_cost_table()` describes, or None.

        Raises:
            SystemConfigValidationError: `config` does not match the shape.
        """
        super().__init__(name=name, display_name=display_name, config=config)
        self._declared: dict[str, dict[str, Any]] = {} if config is None else {cost_key: dict(cost) for cost_key, cost in config.get("costs", {}).items()}

    def validate_config(self, config: Any) -> None:
        """Validate a price list, declared or host-attached.

        Args:
            config: The decoded config.

        Raises:
            SystemConfigValidationError: If the shape doesn't match.
        """
        validate_cost_table(config)

    def seed(self, slot: CostSlot, config: Any) -> None:
        """Declare a host-attached price list into a brand-new slot.

        Args:
            slot: The fresh slot.
            config: The host's config, or None.
        """
        if config:
            for cost_key, cost in config.get("costs", {}).items():
                self.declare(slot, cost_key, resource=cost["resource"], amount=cost["amount"], variants=cost.get("variants"))

    def _entry(self, slot: CostSlot, cost_key: str) -> dict[str, Any] | None:
        """Return one cost's declaration: the slot's if play set it, else the declared one.

        Args:
            slot: This session's slot.
            cost_key: The cost's key.

        Returns:
            The declaration, or None for an unpriced action.
        """
        entry = slot.get("costs", {}).get(cost_key)
        if entry is None:
            return self._declared.get(cost_key)
        return entry

    @query
    @external
    def is_priced(self, slot: CostSlot, cost_key: str) -> bool:
        """Return whether a cost key has a declared price at all.

        A key nobody priced is almost always a typo or an unconverted
        action rather than a deliberate freebie, and `cost_of()` cannot
        tell the two apart -- it answers `default` for both. Ask this when
        the difference matters.

        Args:
            slot: This session's slot.
            cost_key: The cost's key.

        Returns:
            True if the story declared this key, in config or during play.
        """
        return self._entry(slot, cost_key) is not None

    @query
    @external
    def cost_of(self, slot: CostSlot, cost_key: str, variant: str = "", default: float = 0) -> float:
        """Return what an action costs.

        Args:
            slot: This session's slot.
            cost_key: The cost's key, as the story declared it.
            variant: A named alternative to prefer -- the caller names one
                when its condition holds ("first" for a first cast, say).
                Falls back to the base amount when the variant is not
                declared, so a caller may always pass its variant without
                checking whether this particular cost has one.
            default: What to return for a key the story never declared.

        Returns:
            The amount, or `default`.
        """
        entry = self._entry(slot, cost_key)
        if entry is None:
            return default
        if variant:
            amount = entry.get("variants", {}).get(variant)
            if amount is not None:
                return amount
        return entry.get("amount", default)

    @query
    def resource_of(self, slot: CostSlot, cost_key: str, default: str = "") -> str:
        """Return which resource an action is paid in.

        Args:
            slot: This session's slot.
            cost_key: The cost's key.
            default: What to return for an undeclared key.

        Returns:
            The resource name the story declared, or `default`.
        """
        entry = self._entry(slot, cost_key)
        return entry.get("resource", default) if entry else default

    @external
    def can_afford(self, slot: CostSlot, cost_key: str, available: float, variant: str = "") -> bool:
        """Return whether `available` covers this cost.

        The caller supplies what it has, since this plugin holds no
        resource of its own.

        An UNDECLARED key answers False. A priced action is free only when
        the story prices it at 0, which it must do explicitly: answering
        True for a key nobody declared would make every typo
        (`spell.cham` for `spell.charm`) a silently free action, and an
        unconverted action indistinguishable from a deliberate freebie.
        Use `is_priced()` to tell "unpriced" from "costs nothing".

        Args:
            slot: This session's slot.
            cost_key: The cost's key.
            available: How much of the resource the caller currently holds.
            variant: A named alternative to prefer, as `cost_of()`.

        Returns:
            True if `available` is at least the declared cost; False for a
            key the story never declared.
        """
        if not self.is_priced(slot, cost_key):
            return False
        return available >= self.cost_of(slot, cost_key, variant)

    @external
    def set_cost(self, slot: CostSlot, cost_key: str, resource: str, amount: float) -> None:
        """Declare or change one cost's base amount during play.

        Declaring a cost that did not exist is allowed: a story may price
        an action only once it becomes available. Variants already
        declared for this key are kept.

        Args:
            slot: This session's slot.
            cost_key: The cost's key.
            resource: What the cost is paid in.
            amount: The new base amount.
        """
        costs = slot.setdefault("costs", {})
        entry = costs.get(cost_key)
        if entry is None:
            entry = dict(self._declared.get(cost_key, {}))
            costs[cost_key] = entry
        entry["resource"] = resource
        entry["amount"] = amount

    def declare(self, slot: CostSlot, cost_key: str, *, resource: str, amount: float, variants: dict[str, float] | None = None) -> None:
        """Declare one cost outright in the slot, variants included.

        Replaces the whole entry rather than merging: the declaration is
        the complete truth about that cost. `set_cost()` is the narrower
        operation for changing a base amount while keeping variants.

        Args:
            slot: This session's slot.
            cost_key: The cost's key.
            resource: What the cost is paid in.
            amount: The base amount.
            variants: Named alternatives to the base amount, or None.
        """
        entry: dict[str, Any] = {"resource": resource, "amount": amount}
        if variants:
            entry["variants"] = dict(variants)
        slot.setdefault("costs", {})[cost_key] = entry


COST_TABLE = CostTable()
PLUGIN = COST_TABLE.plugin()
