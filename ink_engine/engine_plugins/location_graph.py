"""A plain, occupancy-free map framework.

Knows only about places and the edges between them: no character, no NPC,
no notion of anyone being "at" anywhere. A game wanting just a map -- can
the player reach B from A, is a place known -- must not be forced to adopt
occupancy tracking to use it.

**The dependency runs one way only.** Occupancy depends on the map, since
"who is at which location" presupposes locations; the map depends on
nothing. Placing a character somewhere the map never declared is an
error, and `character_occupancy` raises rather than storing it. So this
module imports nothing from `character_occupancy`, and must not.

Config: `{"locations": {location_id: {"known_by_default": bool,
"details": {...}, "edges": [{"to": location_id, "requires_known": bool}]}}}`,
validated by `validate_location_graph()` below.

**The map's vocabulary is seeded into the slot, deliberately.** The
declared location ids and their details are read by a dependent plugin
from the session state (occupancy checks a write against `declared`), so
they must be where every plugin can see them: in this slot, written once
when the session starts. Edges are read only by this plugin and stay on
the instance.
"""

from __future__ import annotations

from typing import Any, TypedDict

from ink_engine.engine_config_schemas import (
    SystemConfigValidationError,
    require_bool,
    require_dict,
    require_int,
    require_str,
)
from ink_engine.plugin_base import StatefulPlugin, query

#: Where this plugin's state lives in a session's `EngineState`. A
#: dependent plugin reads the declared vocabulary from this slot by this
#: constant.
STATE_KEY = "location_graph"

# What `details` may hold beyond the keys the engine defines. Narrow on
# purpose: this whole module exists so a story's config cannot become an
# injection surface, and a game's own per-location facts are values to
# store and hand back, never anything to interpret.
GameDetailValue = bool | int | float | str

# The terrain types the engine knows, each with the movement cost a story
# may charge for arriving there. Modelled as terrain rather than an
# indoor/outdoor boolean because that is what mature systems converged on
# (ROM's sector types carry exactly this cost), and a two-value game is
# simply one that uses two of these.
TERRAIN_MOVEMENT_COST: dict[str, int] = {
    "indoor": 1,
    "outdoor": 2,
    "city": 2,
    "field": 2,
    "forest": 3,
    "hills": 4,
    "mountain": 6,
    "water": 4,
    "desert": 9,
}


class LocationSlot(TypedDict):
    """A session's map knowledge and per-location facts.

    Attributes:
        known: The location ids this session has discovered, sorted.
            Location ids not flagged `known_by_default` in the story's
            config start absent until `set_known()` adds them.
        declared: Every location id the story's map declares, discovered
            or not -- the map's own vocabulary, carried here so any plugin
            depending on this one can ask what places exist. `known` is
            always a subset of it. Empty for a story that declares no map,
            which readers must treat as "unchecked" rather than "no place
            is valid".
        details: location_id -> that location's declared details, exactly
            as the story's config gave them. Static facts, carried here so
            a dependent plugin reads one place for everything about a
            location.
        visits: location_id -> how many times this session has entered
            it. Absent means zero. A counter rather than a flag because
            "has the player been here" is recoverable from a count while
            a count is not recoverable from a flag.
        place_records: location_id -> `{"attributes": {name: value}}`,
            a location's own story-set facts: whether a door was opened,
            whether a shelf was read. Separate from `details` (what the
            config declared, static) because these change as the story
            runs.
    """

    known: list[str]
    declared: list[str]
    details: dict[str, dict[str, Any]]
    visits: dict[str, int]
    place_records: dict[str, dict[str, dict[str, Any]]]


def _validate_terrain(terrain: Any, path: str) -> None:
    """Validate a location's declared terrain.

    Args:
        terrain: The declared value.
        path: Dotted config path, for the error message.

    Raises:
        SystemConfigValidationError: If it is not one the engine knows.
            A closed set on purpose: terrain fixes the movement cost of
            arriving, so an unrecognised one would silently charge the
            default rather than what the story meant.
    """
    name = require_str(terrain, path)
    if name not in TERRAIN_MOVEMENT_COST:
        raise SystemConfigValidationError(f"{path} '{name}' is not a known terrain (expected one of {', '.join(sorted(TERRAIN_MOVEMENT_COST))})")


def _validate_external_identifier(identifiers: Any, path: str) -> None:
    """Validate a location's identifiers in whatever it was converted from.

    Args:
        identifiers: The declared value.
        path: Dotted config path, for error messages.

    Raises:
        SystemConfigValidationError: If it is not a list of strings or
            integers. `bool` is rejected for the same reason as elsewhere
            here -- it is an int subclass, and a `true` in a list of
            identifiers is a mistake, not an identifier.
    """
    if not isinstance(identifiers, list):
        raise SystemConfigValidationError(f"{path} must be a list")
    for index, identifier in enumerate(identifiers):
        if isinstance(identifier, bool) or not isinstance(identifier, (int, str)):
            raise SystemConfigValidationError(f"{path}[{index}] must be a string or an integer")


_ENGINE_DETAIL_KEYS = frozenset({"name", "description", "external_identifier", "terrain", "region", "lit", "visits"})


def _validate_location_details(details: Any, path: str) -> None:
    """Validate one location's `details` dictionary.

    The engine defines the keys below and validates each one's type; any
    other key is the story's own, and is kept as-is provided its value is
    a plain JSON-safe scalar. That split is the point of the field: a game
    stores its source place numbers and per-location scene data here
    rather than in a parallel structure of its own.

    Engine-defined keys, all optional: `name` (display name), `description`
    (default description), `external_identifier` (a list: the ids this
    location has in whatever the story was converted FROM), `terrain` (one
    of `TERRAIN_MOVEMENT_COST`), `region` (a grouping, not a place), `lit`,
    and `visits` (how many times a new game starts having visited it -- a
    COUNTER; `visited` is derived from it and is rejected as a key).

    Args:
        details: The already-decoded `details` value.
        path: Dotted config path, for error messages.

    Raises:
        SystemConfigValidationError: If a key the engine defines holds
            the wrong type, if `visited` is declared, or if a story's own
            key holds anything but a JSON-safe scalar.
    """
    details_dict = require_dict(details, path)
    if "name" in details_dict:
        require_str(details_dict["name"], f"{path}.name")
    if "description" in details_dict:
        require_str(details_dict["description"], f"{path}.description")
    if "region" in details_dict:
        require_str(details_dict["region"], f"{path}.region")
    if "lit" in details_dict:
        require_bool(details_dict["lit"], f"{path}.lit")
    if "visits" in details_dict and require_int(details_dict["visits"], f"{path}.visits") < 0:
        raise SystemConfigValidationError(f"{path}.visits cannot be negative")
    if "visited" in details_dict:
        raise SystemConfigValidationError(f"{path}.visited is derived from {path}.visits and cannot be declared; set visits instead")
    if "terrain" in details_dict:
        _validate_terrain(details_dict["terrain"], f"{path}.terrain")
    if "external_identifier" in details_dict:
        _validate_external_identifier(details_dict["external_identifier"], f"{path}.external_identifier")
    for key, value in details_dict.items():
        if key in _ENGINE_DETAIL_KEYS:
            continue
        require_str(key, f"{path} key")
        if not isinstance(value, (bool, int, float, str)):
            raise SystemConfigValidationError(f"{path}.{key} must be a string, number, or boolean")


def validate_location_graph(config: Any) -> None:
    """Validate a `location_graph` config.

    ```json
    {
        "locations": {
            "<location_id>": {
                "known_by_default": false,
                "details": {"name": "Police Station - Jail Cell", "terrain": "indoor", "external_identifier": [260, 261]},
                "edges": [{"to": "<other_location_id>", "requires_known": true}]
            }
        }
    }
    ```

    `edges[].requires_known` defaults to `false` when omitted -- most
    ordinary walkable edges don't require the destination to already be
    known, since walking there is often how it becomes known; `true` is
    for a destination that must be discovered some other way first.

    Args:
        config: The already-JSON-decoded config value to validate.

    Raises:
        SystemConfigValidationError: If the shape doesn't match, including
            an edge referencing a location_id not itself declared (a real,
            closed graph -- no dangling edges).
    """
    root = require_dict(config, "location_graph config")
    locations = require_dict(root.get("locations", {}), "location_graph.locations")
    if not locations:
        raise SystemConfigValidationError("location_graph.locations must declare at least one location")

    for location_id, location in locations.items():
        require_str(location_id, "location_graph.locations key")
        location_path = f"location_graph.locations.{location_id}"
        location_dict = require_dict(location, location_path)
        require_bool(location_dict.get("known_by_default", False), f"{location_path}.known_by_default")
        if "details" in location_dict:
            _validate_location_details(location_dict["details"], f"{location_path}.details")
        edges = location_dict.get("edges", [])
        if not isinstance(edges, list):
            raise SystemConfigValidationError(f"{location_path}.edges must be a list")
        for index, edge in enumerate(edges):
            edge_path = f"{location_path}.edges[{index}]"
            edge_dict = require_dict(edge, edge_path)
            destination = require_str(edge_dict.get("to"), f"{edge_path}.to")
            if destination not in locations:
                raise SystemConfigValidationError(f"{edge_path}.to references unknown location '{destination}'")
            if "requires_known" in edge_dict:
                require_bool(edge_dict["requires_known"], f"{edge_path}.requires_known")


class LocationGraph(StatefulPlugin[LocationSlot]):
    """The map: what places exist, which are known, and facts about each.

    A game ships its map by instantiating this class with its config under
    its own name: `LocationGraph(name="my_map", config={"locations":
    {...}})`. The config is seeded into the slot when a session starts,
    so the declared vocabulary is visible to every plugin; a resumed save
    keeps the map it was saved with.

    This plugin answers no Ink call of its own; a game's plugin binds the
    names its story uses over these methods.
    """

    name = "location_graph"
    display_name = "Location graph"
    state_key = STATE_KEY
    slot_type = LocationSlot
    fields = {"known": list, "declared": list, "details": dict, "visits": dict, "place_records": dict}

    def __init__(self, *, name: str | None = None, display_name: str | None = None, config: Any = None) -> None:
        """Build a map plugin, optionally over a game's declared map.

        Args:
            name: Override the plugin name, for a game's configured copy.
            display_name: Override the display name.
            config: The game's map, in the shape `validate_location_graph()`
                describes, or None.

        Raises:
            SystemConfigValidationError: `config` does not match the shape.
        """
        super().__init__(name=name, display_name=display_name, config=config)
        # Seeded at allocation: a dependent plugin reads `declared` from
        # the session, not from this instance.
        self.default_config = config

    def validate_config(self, config: Any) -> None:
        """Validate a map, declared or host-attached.

        An empty config means "none attached" -- a host's opt-in row with
        nothing in it -- and is always valid; the session then seeds from
        the map this instance was built with.

        Args:
            config: The decoded config.

        Raises:
            SystemConfigValidationError: If the shape doesn't match.
        """
        if config in (None, {}):
            return
        validate_location_graph(config)

    def seed(self, slot: LocationSlot, config: Any) -> None:
        """Write a map into a brand-new slot: vocabulary, details, defaults.

        Args:
            slot: The fresh slot.
            config: The map config, or None for a story with no map.
        """
        if not config:
            return
        locations = config.get("locations", {})
        slot["declared"] = sorted(locations)
        slot["known"] = sorted(location_id for location_id, location in locations.items() if location.get("known_by_default", False))
        slot["details"] = {location_id: dict(location.get("details", {})) for location_id, location in locations.items()}
        slot["visits"] = {location_id: detail["visits"] for location_id, detail in slot["details"].items() if detail.get("visits")}

    # -- the vocabulary ---------------------------------------------------------

    def declares(self, slot: LocationSlot, location_id: str) -> bool:
        """Return whether the map declares `location_id` at all.

        Distinct from `is_known()`, which asks whether the PLAYER has
        found the place: an undiscovered location is still a real place,
        while an undeclared one does not exist in this story.

        Args:
            slot: This session's slot.
            location_id: The location to check.

        Returns:
            True if the map declares it. False for every id when the
            story declares no map at all -- callers must check `declared`
            itself before treating a False as an error.
        """
        return location_id in slot.get("declared", ())

    def detail(self, slot: LocationSlot, location_id: str, key: str, default: Any = None) -> Any:
        """Return one declared fact about a location.

        Args:
            slot: This session's slot.
            location_id: The location to ask about.
            key: The detail key -- one the engine defines (`name`,
                `terrain`, `region`, `lit`, `description`,
                `external_identifier`) or one the story declared itself.
            default: What to return when the location or the key is absent.

        Returns:
            The declared value, or `default`.
        """
        return slot.get("details", {}).get(location_id, {}).get(key, default)

    def movement_cost(self, slot: LocationSlot, location_id: str, default: int = 1) -> int:
        """Return what arriving at a location costs, from its terrain.

        Args:
            slot: This session's slot.
            location_id: The location being entered.
            default: The cost for a location declaring no terrain.

        Returns:
            That terrain's cost, or `default`.
        """
        terrain = self.detail(slot, location_id, "terrain")
        return TERRAIN_MOVEMENT_COST.get(terrain, default) if isinstance(terrain, str) else default

    def reachable_edges(self, slot: LocationSlot, location_id: str) -> list[str]:
        """Return the outgoing edges from `location_id` reachable right now.

        An edge with `requires_known: true` is only included once its
        destination is already known some other way; an edge with
        `requires_known: false`, or the key omitted, is always included.
        Edges come from this instance's config, since only this plugin
        reads them.

        Args:
            slot: This session's slot.
            location_id: The location to list real outgoing edges from.

        Returns:
            The destination location ids reachable from `location_id`
            right now, in declared order. Empty if `location_id` is not
            declared, or this instance was built with no map.
        """
        location = (self.config or {}).get("locations", {}).get(location_id)
        if location is None:
            return []
        destinations = []
        for edge in location.get("edges", []):
            destination = edge["to"]
            if edge.get("requires_known", False) and not self.is_known(slot, destination):
                continue
            destinations.append(destination)
        return destinations

    # -- discovery --------------------------------------------------------------

    @query
    def is_known(self, slot: LocationSlot, location_id: str) -> bool:
        """Return whether a location has been discovered this session.

        Args:
            slot: This session's slot.
            location_id: The location to check.

        Returns:
            True once discovered.
        """
        return location_id in slot.get("known", ())

    def set_known(self, slot: LocationSlot, location_id: str, known: bool = True) -> None:
        """Mark a location discovered, or forget it.

        Real stories do revoke a discovery (a place is destroyed, sealed,
        or the memory of it taken), so forgetting is a first-class
        operation rather than something a story has to reach around the
        API to do. Forgetting an unknown location is a no-op.

        Args:
            slot: This session's slot.
            location_id: The location to update.
            known: True to discover it, False to forget it.
        """
        discovered = set(slot.get("known", ()))
        if known:
            discovered.add(location_id)
        else:
            discovered.discard(location_id)
        slot["known"] = sorted(discovered)

    def set_all_known(self, slot: LocationSlot, known: bool) -> None:
        """Mark EVERY declared location known, or none of them.

        One step for the whole map. The two real uses are a debug/cheat
        "reveal the whole map" toggle and a test fixture that needs every
        destination reachable without replaying each discovery scene.

        Note the asymmetry, which is deliberate: `known=False` clears the
        map completely, including locations the story's config marks
        `known_by_default`. It is "forget everything," not "reset to a
        new game".

        Args:
            slot: This session's slot.
            known: True to mark every declared location known; False to
                mark every location unknown.
        """
        slot["known"] = list(slot.get("declared", ())) if known else []

    # -- visits -----------------------------------------------------------------

    def visit_count(self, slot: LocationSlot, location_id: str) -> int:
        """Return how many times this session has entered a location.

        Args:
            slot: This session's slot.
            location_id: The location to ask about.

        Returns:
            The count, 0 if never entered.
        """
        return slot.get("visits", {}).get(location_id, 0)

    def has_visited(self, slot: LocationSlot, location_id: str) -> bool:
        """Return whether a location has ever been entered.

        Derived from `visit_count()` rather than stored: one fact, one
        place, so the flag and the count can never disagree.

        Args:
            slot: This session's slot.
            location_id: The location to ask about.

        Returns:
            True if it has been entered at least once.
        """
        return self.visit_count(slot, location_id) > 0

    def record_visit(self, slot: LocationSlot, location_id: str) -> int:
        """Count one more entry into a location.

        Args:
            slot: This session's slot.
            location_id: The location just entered.

        Returns:
            The new visit count.
        """
        visits = slot.setdefault("visits", {})
        visits[location_id] = visits.get(location_id, 0) + 1
        return visits[location_id]

    # -- a place's own story-set facts -------------------------------------------

    @query
    def read_attribute(self, slot: LocationSlot, location_id: str, attribute: str, default: Any = False) -> Any:
        """Return one story-set fact about a location.

        The per-location counterpart to a character attribute: whether a
        door was opened, whether a shelf was read. Distinct from
        `detail()`, which answers what the config declared.

        Args:
            slot: This session's slot.
            location_id: The location to ask about.
            attribute: The attribute name.
            default: What to return when never set.

        Returns:
            The stored value, or `default`.
        """
        return slot.get("place_records", {}).get(location_id, {}).get("attributes", {}).get(attribute, default)

    def set_attribute(self, slot: LocationSlot, location_id: str, attribute: str, value: Any) -> None:
        """Store one story-set fact about a location.

        Args:
            slot: This session's slot.
            location_id: The location to update.
            attribute: The attribute name.
            value: The value to store.
        """
        slot.setdefault("place_records", {}).setdefault(location_id, {}).setdefault("attributes", {})[attribute] = value

    def attribute_exists(self, slot: LocationSlot, location_id: str, attribute: str) -> bool:
        """Return whether a fact was ever stored, whatever its value.

        A stored `False` and a never-set attribute both read as false; a
        story sometimes needs to tell them apart.

        Args:
            slot: This session's slot.
            location_id: The location to check.
            attribute: The attribute name.

        Returns:
            True when present.
        """
        return attribute in slot.get("place_records", {}).get(location_id, {}).get("attributes", {})


LOCATION_GRAPH = LocationGraph()
PLUGIN = LOCATION_GRAPH.plugin()
