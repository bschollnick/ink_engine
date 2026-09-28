"""A plain, occupancy-free map framework.

Knows only about places and the exits between them: no character, no NPC,
no notion of anyone being "at" anywhere.

**The dependency runs one way only.** Occupancy depends on the map; the
map depends on nothing. **This module imports nothing from
`character_occupancy`, and must not.**

Config: `{"locations": {location_id: {"known_by_default": bool,
"details": {...}, "exits": [...]}}}`, validated by
`validate_location_graph()` below. An exit declares `to` and, optionally,
a `label` to show, a `position` for a widget to place it at, the
`arrival_knot` and `travel_text` an application diverts the story with,
its gates: `requires_known`, `sealed`, `unlocked_by` and
`show_when_blocked`, and `through`, a place the journey passes through.

**The map's vocabulary is seeded into the slot** so a dependent plugin
can read it from session state (occupancy checks writes against
`declared`). Exits are definition, not state: they stay on the instance
and are read from its config.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any, ClassVar, TypedDict

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
# may charge for arriving there.
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


# Where a widget may put an exit. A closed set, because a position is a
# place on screen the application must know how to draw, not a name the
# game chooses -- a lift declares `out` and labels it "EXIT" rather than
# inventing a position.
EXIT_POSITIONS: tuple[str, ...] = (
    "n",
    "ne",
    "e",
    "se",
    "s",
    "sw",
    "w",
    "nw",
    "up",
    "down",
    "in",
    "out",
)

# The position an exit is entered from, for each position it leaves by.
# Used to build the return exit a two-way connection implies.
RETURN_DIRECTION: dict[str, str] = {
    "n": "s",
    "s": "n",
    "e": "w",
    "w": "e",
    "ne": "sw",
    "sw": "ne",
    "nw": "se",
    "se": "nw",
    "up": "down",
    "down": "up",
    "in": "out",
    "out": "in",
}


class LocationSlot(TypedDict):
    """A session's map knowledge and per-location facts.

    Attributes:
        known: The location ids this session has discovered, sorted.
            Location ids not flagged `known_by_default` in the story's
            config start absent until `set_known()` adds them.
        declared: Every location id the story's map declares, discovered
            or not. `known` is always a subset of it. Empty for a story
            that declares no map, which readers must treat as
            "unchecked" rather than "no place is valid".
        details: location_id -> that location's declared details, exactly
            as the story's config gave them. Static.
        visits: location_id -> how many times this session has entered
            it. Absent means zero.
        place_records: location_id -> `{"attributes": {name: value}}`,
            a location's own story-set facts: whether a door was opened,
            whether a shelf was read. Unlike `details`, these change as
            the story runs.
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
            A closed set: terrain fixes the movement cost of arriving.
    """
    name = require_str(terrain, path)
    if name not in TERRAIN_MOVEMENT_COST:
        raise SystemConfigValidationError(f"{path} '{name}' is not a known terrain (expected one of {', '.join(sorted(TERRAIN_MOVEMENT_COST))})")


def _validate_position(position: Any, path: str) -> None:
    """Validate an exit's declared position.

    Args:
        position: The declared value.
        path: Dotted config path, for the error message.

    Raises:
        SystemConfigValidationError: If it is not one the engine knows.
            A closed set: an application lays a position out, so one it
            has never heard of has nowhere to go.
    """
    name = require_str(position, path)
    if name not in EXIT_POSITIONS:
        raise SystemConfigValidationError(f"{path} '{name}' is not a known exit position (expected one of {', '.join(EXIT_POSITIONS)})")


def _validate_external_identifier(identifiers: Any, path: str) -> None:
    """Validate a location's identifiers in whatever it was converted from.

    Args:
        identifiers: The declared value.
        path: Dotted config path, for error messages.

    Raises:
        SystemConfigValidationError: If it is not a list of strings or
            integers. `bool` is rejected, being an int subclass.
    """
    if not isinstance(identifiers, list):
        raise SystemConfigValidationError(f"{path} must be a list")
    for index, identifier in enumerate(identifiers):
        if isinstance(identifier, bool) or not isinstance(identifier, (int, str)):
            raise SystemConfigValidationError(f"{path}[{index}] must be a string or an integer")


_ENGINE_DETAIL_KEYS = frozenset({"name", "description", "external_identifier", "terrain", "region", "lit", "visits", "event", "entrance", "building"})


def _validate_location_details(details: Any, path: str) -> None:
    """Validate one location's `details` dictionary.

    The engine defines the keys below and validates each one's type; any
    other key is the story's own, kept as-is provided its value is a
    plain JSON-safe scalar.

    Engine-defined keys, all optional: `name` (display name), `description`
    (default description), `external_identifier` (a list: the ids this
    location has in whatever the story was converted FROM), `terrain` (one
    of `TERRAIN_MOVEMENT_COST`), `region` (a grouping, not a place), `lit`,
    `visits` (how many times a new game starts having visited it -- a
    COUNTER; `visited` is derived from it and is rejected as a key), and
    `event` (true for a scene that has an id so characters can stand in
    it, but is not a place: `exits_from()`, `reachable_exits()` and
    `without_events()` leave it out), and `entrance` (true for an indoor
    place that is the way into a building, or into a unit inside one, such
    as an apartment off a corridor; `buildings()` groups a map by them),
    and `building` (the location id of a building's main entrance: this
    place is inside that building whatever its terrain or exits, and an entrance
    declaring it is a further entrance of that building).

    Args:
        details: The already-decoded `details` value.
        path: Dotted config path, for error messages.

    Raises:
        SystemConfigValidationError: If a key the engine defines holds
            the wrong type, if `visited` is declared, or if a story's own
            key holds anything but a JSON-safe scalar.
    """
    details_dict = require_dict(details, path)
    for key in ("name", "description", "region", "building"):
        if key in details_dict:
            require_str(details_dict[key], f"{path}.{key}")
    for key in ("lit", "event", "entrance"):
        if key in details_dict:
            require_bool(details_dict[key], f"{path}.{key}")
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


def is_event(config: dict[str, Any], location_id: str) -> bool:
    """Return whether a declared location is an event rather than a place.

    Args:
        config: A location graph config.
        location_id: The location to ask about.

    Returns:
        True if its `details` declare `event: true`.
    """
    return bool(config.get("locations", {}).get(location_id, {}).get("details", {}).get("event", False))


def without_events(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a map with its events, and every exit into one, removed.

    What a map drawing shows: the places, and the corridors between them.

    Args:
        config: A location graph config. Not modified.

    Returns:
        A new config holding only the locations that are not events.
    """
    locations = config.get("locations", {})
    events = {location_id for location_id in locations if is_event(config, location_id)}
    return {
        **config,
        "locations": {
            location_id: {**location, "exits": [exit_ for exit_ in location.get("exits", []) if exit_["to"] not in events]}
            for location_id, location in locations.items()
            if location_id not in events
        },
    }


class Building(TypedDict):
    """One building of a map, as `buildings()` finds it.

    Attributes:
        entrance: Its main entrance's location id, which keys it.
        entrances: Every entrance it has, the main one first.
        rooms: Its other places, in walking order from the entrances. A
            nested building's places are in that building, not here.
        buildings: The buildings whose entrances open off it.
    """

    entrance: str
    entrances: list[str]
    rooms: list[str]
    buildings: list[Building]


class BuildingTree(TypedDict):
    """A map grouped into buildings by its entrances.

    Attributes:
        buildings: The outermost buildings, in declaration order.
        top_level: Every place in no building, in declaration order.
        no_entrance: The indoor places among `top_level`: interiors no
            entrance leads into.
    """

    buildings: list[Building]
    top_level: list[str]
    no_entrance: list[str]


def _detail(config: dict[str, Any], location_id: str, key: str) -> Any:
    """Return one of a location's declared details, or None."""
    return config.get("locations", {}).get(location_id, {}).get("details", {}).get(key)


def is_indoor(config: dict[str, Any], location_id: str) -> bool:
    """Return whether a declared location's terrain is `indoor`; a location with no terrain is not."""
    return _detail(config, location_id, "terrain") == "indoor"


def is_entrance(config: dict[str, Any], location_id: str) -> bool:
    """Return whether a declared location's `details` declare `entrance: true`."""
    return bool(_detail(config, location_id, "entrance"))


def _neighbours(config: dict[str, Any]) -> dict[str, list[str]]:
    """Return each place's neighbours by an exit either way, an exit's `through` standing for its destination; events left out."""
    locations = config.get("locations", {})
    neighbours: dict[str, list[str]] = {location_id: [] for location_id in locations if not is_event(config, location_id)}
    for origin in neighbours:
        for exit_declaration in locations[origin].get("exits", []):
            destination = exit_declaration.get("through", exit_declaration["to"])
            if destination in neighbours and destination != origin:
                if destination not in neighbours[origin]:
                    neighbours[origin].append(destination)
                if origin not in neighbours[destination]:
                    neighbours[destination].append(origin)
    return neighbours


class _BuildingClaim:
    """The outside-in claim `buildings()` makes: which building owns each place."""

    def __init__(self, config: dict[str, Any], neighbours: dict[str, list[str]]) -> None:
        self.config, self.neighbours = config, neighbours
        declared = list(neighbours)
        found: dict[str, list[str]] = {}
        for place in declared:
            if is_entrance(config, place):
                found.setdefault(_detail(config, place, "building") or place, []).append(place)
        #: Main entrance -> every entrance of that building, the main one first.
        self.groups = {key: [*(e for e in found[key] if e == key), *(e for e in found[key] if e != key)] for key in sorted(found, key=declared.index)}
        self.group_of = {entrance: key for key, members in self.groups.items() for entrance in members}
        self.owner: dict[str, str] = {}
        #: Main entrance -> its `rooms` (those declaring it first) and its nested `buildings`' main entrances.
        self.contents: dict[str, dict[str, list[str]]] = {key: {"rooms": [], "buildings": []} for key in self.groups}
        for place in declared:
            key = _detail(config, place, "building")
            if key in self.contents and place not in self.group_of:
                self.contents[key]["rooms"].append(place)
        self.outermost = [key for key, members in self.groups.items() if any(self.outside(n, key) for e in members for n in neighbours[e])]

    def outside(self, place: str, key: str) -> bool:
        """Return whether a place is outside building `key`: not indoor, and not declaring that building."""
        return not is_indoor(self.config, place) and _detail(self.config, place, "building") != key

    def run(self) -> None:
        """Claim every building's places, layer by layer from the outermost."""
        placed = set(self.outermost)
        layer = list(self.outermost)
        while layer or len(placed) < len(self.groups):
            if not layer:
                layer = [next(key for key in self.groups if key not in placed)]
                placed.add(layer[0])
                self.outermost.append(layer[0])
            starts = [place for key in layer for place in (*self.groups[key], *self.contents[key]["rooms"])]
            self.owner.update((place, key) for key in layer for place in (*self.groups[key], *self.contents[key]["rooms"]))
            layer = self._flood(starts, placed)

    def _flood(self, starts: list[str], placed: set[str]) -> list[str]:
        """Claim the places the entrances in `starts` reach, and return the buildings found inside them."""
        queue, found = deque(starts), []
        while queue:
            here = queue.popleft()
            building = self.owner[here]
            for there in self.neighbours[here]:
                if there in self.owner or self.outside(there, building):
                    continue
                if there not in self.group_of:
                    self.owner[there] = building
                    self.contents[building]["rooms"].append(there)
                    queue.append(there)
                elif self.group_of[there] not in placed:
                    placed.add(self.group_of[there])
                    self.contents[building]["buildings"].append(self.group_of[there])
                    found.append(self.group_of[there])
        return found


def buildings(config: dict[str, Any]) -> BuildingTree:
    """Group a map's places into buildings by the entrances it declares.

    A building is its entrances, every place whose `details.building`
    names it (reachable or not), and every place reachable from those
    without passing another building's entrance or a place outside it. A
    place is inside if it is indoor (`terrain: "indoor"`) or declares this
    building. Exits count both ways, an exit's `through` stands for its
    destination, and events are left out.

    Buildings are claimed outside in, starting from those with an entrance
    beside a place outside them. A building whose entrance is reached from
    inside another is nested in it and claims only what its parent has
    not. The nearer building claims a contested place, ties going to the
    one declared first; a building nothing outside reaches is outermost.

    Args:
        config: A validated location graph config. Not modified.

    Returns:
        The building tree, JSON-safe.
    """
    neighbours = _neighbours(config)
    claim = _BuildingClaim(config, neighbours)
    claim.run()

    def tree(key: str) -> Building:
        inside = claim.contents[key]
        return {
            "entrance": key,
            "entrances": claim.groups[key],
            "rooms": inside["rooms"],
            "buildings": [tree(child) for child in inside["buildings"]],
        }

    top_level = [place for place in neighbours if place not in claim.owner]
    return {
        "buildings": [tree(key) for key in sorted(claim.outermost, key=list(neighbours).index)],
        "top_level": top_level,
        "no_entrance": [place for place in top_level if is_indoor(config, place)],
    }


def add_missing_return_exits(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a map with the return journey of every two-way exit.

    A corridor is declared once, from either end. This fills in the exit
    coming back: same pair of locations, the returning position, and the
    destination's own name as the label. When the location being returned
    to declares an `arrival_knot`, the return exit carries it, with that
    location's `arrival_text` (or "") as its `travel_text`, so an
    application can take it; otherwise the return exit has no arrival
    knot and cannot be taken.

    An exit is left alone when it declares `one_way`, when the
    destination already declares an exit back to this location, or when
    it has no position (nothing says which way the return would lie).
    A return whose position is already taken at the destination is still
    added, without one.

    Args:
        config: A validated location graph config. Not modified.

    Returns:
        A new config. Game configs are built once at import and shared,
        so the original is never written to.
    """
    locations = config.get("locations", {})
    filled = {location_id: {**location, "exits": list(location.get("exits", []))} for location_id, location in locations.items()}

    for origin, location in locations.items():
        for exit_declaration in location.get("exits", []):
            destination = exit_declaration["to"]
            position = exit_declaration.get("position")
            if exit_declaration.get("one_way") or position is None:
                continue
            if destination not in filled:
                continue
            if any(back["to"] == origin for back in filled[destination]["exits"]):
                continue
            details = location.get("details", {})
            returning = RETURN_DIRECTION[position]
            # A map may already send another exit that way, which the
            # original of a converted game is free to do. The return is
            # still offered; it just carries no position.
            taken = {back.get("position") for back in filled[destination]["exits"]}
            synthesized: dict[str, Any] = {"to": origin, "label": details.get("name", origin)}
            if "arrival_knot" in location:
                synthesized["arrival_knot"] = location["arrival_knot"]
                synthesized["travel_text"] = location.get("arrival_text", "")
            if returning not in taken:
                synthesized["position"] = returning
            filled[destination]["exits"].append(synthesized)

    return {**config, "locations": filled}


def _validate_exit(
    exit_declaration: Any,
    path: str,
    locations: dict[str, Any],
    seen_positions: dict[str, int],
) -> None:
    """Validate one exit, and record the position it occupies.

    Args:
        exit_declaration: The declared exit.
        path: Dotted config path, for the error message.
        locations: Every declared location, so `to` can be closed.
        seen_positions: position -> the index that already claimed it,
            for this origin. Updated in place.

    Raises:
        SystemConfigValidationError: If a field has the wrong type, `to`
            or `through` names an undeclared location, the position is not one the
            engine knows or is already taken from this origin, or
            `arrival_knot` and `travel_text` are not declared together.
    """
    exit_dict = require_dict(exit_declaration, path)
    destination = require_str(exit_dict.get("to"), f"{path}.to")
    if destination not in locations:
        raise SystemConfigValidationError(f"{path}.to references unknown location '{destination}'")

    if "label" in exit_dict:
        require_str(exit_dict["label"], f"{path}.label")
    if "requires_known" in exit_dict:
        require_bool(exit_dict["requires_known"], f"{path}.requires_known")
    if "one_way" in exit_dict:
        require_bool(exit_dict["one_way"], f"{path}.one_way")
    if "sealed" in exit_dict:
        require_bool(exit_dict["sealed"], f"{path}.sealed")
    if "show_when_blocked" in exit_dict:
        require_bool(exit_dict["show_when_blocked"], f"{path}.show_when_blocked")
    if "unlocked_by" in exit_dict:
        require_str(exit_dict["unlocked_by"], f"{path}.unlocked_by")
    if "through" in exit_dict and require_str(exit_dict["through"], f"{path}.through") not in locations:
        raise SystemConfigValidationError(f"{path}.through references unknown location '{exit_dict['through']}'")

    # An arrival knot with no travel text narrates nothing, and travel
    # text with nowhere to arrive is never printed.
    has_knot = "arrival_knot" in exit_dict
    has_text = "travel_text" in exit_dict
    if has_knot != has_text:
        missing = "travel_text" if has_knot else "arrival_knot"
        raise SystemConfigValidationError(f"{path} declares one of arrival_knot/travel_text without the other; {missing} is missing")
    if has_knot:
        require_str(exit_dict["arrival_knot"], f"{path}.arrival_knot")
        require_str(exit_dict["travel_text"], f"{path}.travel_text")

    if "position" in exit_dict:
        _validate_position(exit_dict["position"], f"{path}.position")
        position = exit_dict["position"]
        if position in seen_positions:
            taken_by = seen_positions[position]
            raise SystemConfigValidationError(f"{path}.position '{position}' is already taken by exits[{taken_by}]")
        seen_positions[position] = int(path.rsplit("[", 1)[1].rstrip("]"))


def validate_location_graph(config: Any) -> None:
    """Validate a `location_graph` config.

    ```json
    {
        "locations": {
            "<location_id>": {
                "known_by_default": false,
                "details": {"name": "Police Station - Jail Cell", "terrain": "indoor", "external_identifier": [260, 261]},
                "exits": [{"to": "<other_location_id>", "label": "the hospital",
                           "position": "n", "requires_known": true,
                           "arrival_knot": "<knot_name>", "travel_text": "You walk north."}]
            }
        }
    }
    ```

    Every field but `to` is optional, so `{"to": "<location_id>"}` is a
    complete exit and a game adopts only as much as it needs.

    `requires_known` defaults to `false` -- most ordinary walkable exits
    don't require the destination to already be known, since walking
    there is often how it becomes known; `true` is for a destination
    that must be discovered some other way first. `sealed` is never
    passable. `unlocked_by` names an attribute on the destination, set
    through `set_attribute()`, which opens the exit for the rest of the
    game because it is saved with the session. A blocked exit is left
    out of `exits_from()` unless it declares `show_when_blocked`.

    `through` names a declared location the journey passes through, such
    as a hotel's lobby on a shortcut from a room to the street;
    `buildings()` treats the exit as leading there. `position` must be
    one of `EXIT_POSITIONS`, and two exits from one location may not
    share it. `arrival_knot` and `travel_text` are
    declared together or not at all.

    A location may declare `arrival_knot` and `arrival_text`: the knot and
    prose for arriving there, which `add_missing_return_exits()` gives to
    every return exit it builds into that location. `arrival_text`
    requires `arrival_knot`.

    Args:
        config: The already-JSON-decoded config value to validate.

    Raises:
        SystemConfigValidationError: If the shape doesn't match, including
            an exit referencing a location_id not itself declared (a real,
            closed graph -- no dangling exits), or a `details.building`
            that does not name a main entrance.
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
        if "arrival_knot" in location_dict:
            require_str(location_dict["arrival_knot"], f"{location_path}.arrival_knot")
        if "arrival_text" in location_dict:
            if "arrival_knot" not in location_dict:
                raise SystemConfigValidationError(f"{location_path} declares arrival_text without arrival_knot")
            require_str(location_dict["arrival_text"], f"{location_path}.arrival_text")
        exits = location_dict.get("exits", [])
        if not isinstance(exits, list):
            raise SystemConfigValidationError(f"{location_path}.exits must be a list")
        seen_positions: dict[str, int] = {}
        for index, exit_declaration in enumerate(exits):
            exit_path = f"{location_path}.exits[{index}]"
            _validate_exit(exit_declaration, exit_path, locations, seen_positions)
    _validate_building_references(locations)


def _validate_building_references(locations: dict[str, Any]) -> None:
    """Raise `SystemConfigValidationError` unless every `details.building` names a declared main entrance."""
    for location_id, location in locations.items():
        main = location.get("details", {}).get("building")
        if main is None:
            continue
        path = f"location_graph.locations.{location_id}.details.building"
        if main not in locations:
            raise SystemConfigValidationError(f"{path} references unknown location '{main}'")
        main_details = locations[main].get("details", {})
        if not main_details.get("entrance"):
            raise SystemConfigValidationError(f"{path} '{main}' is not an entrance")
        if main_details.get("building", main) != main:
            raise SystemConfigValidationError(f"{path} '{main}' is itself an entrance of '{main_details['building']}'")


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
    fields: ClassVar[dict[str, Callable[[], Any]]] = {"known": list, "declared": list, "details": dict, "visits": dict, "place_records": dict}

    def __init__(self, *, name: str | None = None, display_name: str | None = None, state_key: str | None = None, config: Any = None) -> None:
        """Build a map plugin, optionally over a game's declared map.

        Args:
            name: Override the plugin name, for a game's configured copy.
            display_name: Override the display name.
            config: The game's map, in the shape `validate_location_graph()`
                describes, or None.

        Raises:
            SystemConfigValidationError: `config` does not match the shape.
        """
        super().__init__(name=name, display_name=display_name, state_key=state_key, config=config)
        # Seeded at allocation: a dependent plugin reads `declared` from
        # the session, not from this instance.
        self.default_config = config

    def validate_config(self, config: Any) -> None:
        """Validate a map, declared or application-attached.

        An empty config means "none attached" -- an application's opt-in row with
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
                `description`, `external_identifier`, `terrain`,
                `region`, `lit`, `visits`, `event`, `entrance`) or one
                the story declared itself.
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

    def reachable_exits(self, slot: LocationSlot, location_id: str) -> list[str]:
        """Return the outgoing exits from `location_id` reachable right now.

        An exit with `requires_known: true` is only included once its
        destination is already known some other way; an exit with
        `requires_known: false`, or the key omitted, is always included.
        An exit into an event is never included: the scene that starts
        the event offers it as a story choice.
        Edges come from this instance's config, since only this plugin
        reads them.

        Args:
            slot: This session's slot.
            location_id: The location to list real outgoing exits from.

        Returns:
            The destination location ids reachable from `location_id`
            right now, in declared order. Empty if `location_id` is not
            declared, or this instance was built with no map.
        """
        location = (self.config or {}).get("locations", {}).get(location_id)
        if location is None:
            return []
        destinations = []
        for exit_declaration in location.get("exits", []):
            destination = exit_declaration["to"]
            if is_event(self.config or {}, destination):
                continue
            if exit_declaration.get("requires_known", False) and not self.is_known(slot, destination):
                continue
            destinations.append(destination)
        return destinations

    # -- discovery --------------------------------------------------------------

    def exits_from(self, slot: LocationSlot, location_id: str) -> list[dict[str, Any]]:
        """Return the outgoing exits from `location_id`, ready to render.

        Every exit an application would show, each as a dict carrying
        `to`, `label`, `position`, `travel_text`, `arrival_knot` and
        `passable`. `label` falls back to the destination's declared
        name, and then to its id.

        A blocked exit is left out unless it declares
        `show_when_blocked`, in which case it comes back with
        `passable` false so the application can draw it unavailable.
        An exit is blocked when it is `sealed`, when `requires_known`
        and the destination is not known, or when `unlocked_by` names an
        attribute that is not yet set on the destination. An exit into an
        event is never returned.

        Args:
            slot: This session's slot.
            location_id: The location to list exits from.

        Returns:
            The exits, in declared order. Empty if `location_id` is not
            declared, or this instance was built with no map.
        """
        locations = (self.config or {}).get("locations", {})
        location = locations.get(location_id)
        if location is None:
            return []

        rendered: list[dict[str, Any]] = []
        for exit_declaration in location.get("exits", []):
            destination = exit_declaration["to"]
            if is_event(self.config or {}, destination):
                continue
            passable = self._exit_is_passable(slot, exit_declaration)
            if not passable and not exit_declaration.get("show_when_blocked", False):
                continue
            details = locations.get(destination, {}).get("details", {})
            rendered.append(
                {
                    "to": destination,
                    "label": exit_declaration.get("label") or details.get("name", destination),
                    "position": exit_declaration.get("position"),
                    "travel_text": exit_declaration.get("travel_text"),
                    "arrival_knot": exit_declaration.get("arrival_knot"),
                    "passable": passable,
                }
            )
        return rendered

    def _exit_is_passable(self, slot: LocationSlot, exit_declaration: dict[str, Any]) -> bool:
        """Return whether this session may take one exit right now."""
        if exit_declaration.get("sealed", False):
            return False
        destination = exit_declaration["to"]
        if exit_declaration.get("requires_known", False) and not self.is_known(slot, destination):
            return False
        attribute = exit_declaration.get("unlocked_by")
        return attribute is None or bool(self.read_attribute(slot, destination, attribute))

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

        Asymmetric: `known=False` clears the map completely, including
        locations config marks `known_by_default`.

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
