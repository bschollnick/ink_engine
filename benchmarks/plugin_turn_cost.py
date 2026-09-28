"""Per-turn cost of the plugin layer.

Measures the four things a turn pays for: building a session's binding
dictionary, allocating its state slots, reading a hot binding, and
round-tripping the state through JSON.

By default it measures a synthetic town built here with every generic
engine plugin active, its state filled through the plugins' own bindings
to the size of a large game (`--scale` multiplies it). `--game` measures
a real game folder or bundle instead, with the plugins its manifest
declares:

    python -m benchmarks.plugin_turn_cost
    python -m benchmarks.plugin_turn_cost --scale 4
    python -m benchmarks.plugin_turn_cost --game examples/cloak_of_darkness

The figures are absolute, not a comparison against an earlier tree, so
nothing here gates a build.
"""

from __future__ import annotations

import argparse
import json
import statistics
import timeit
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins, mount_game
from ink_engine.engine import load_list_defs
from ink_engine.game_folder import find_main_story_file, read_required_plugins
from ink_engine.game_source import open_game_source
from ink_engine.plugin import Plugin

ENGINE_PLUGINS = "ink_engine.engine_plugins"
REPEATS = 5
CALLS_PER_SAMPLE = 100

#: The synthetic town at `--scale 1`: a street grid, buildings of rooms
#: off it, and the people, belongings, quests, skills and prices a large
#: game carries.
STREET_GRID = 12
BUILDINGS = 60
ROOMS_PER_BUILDING = 6
CHARACTERS = 150
ITEMS = 400
QUESTS = 40
GOALS_PER_QUEST = 4
SKILLS_PER_CHARACTER = 5
PRICED_ACTIONS = 100
ATTRIBUTES_PER_CHARACTER = 8


@dataclass
class Session:
    """What one measured session needs: how to bind it, and what it binds to."""

    label: str
    plugins: dict[str, Plugin]
    active_names: list[str]
    list_defs: dict[str, Any]
    configs: dict[str, Any]

    def bind(self, engine_state: dict[str, Any]) -> dict[str, Callable[..., Any]]:
        """Return this session's bindings over `engine_state`, allocating any missing slot."""
        return resolve_bindings(self.plugins, self.active_names, engine_state, list_defs=self.list_defs, configs=self.configs)


def _town_config(scale: int) -> dict[str, Any]:
    """Return a `location_graph` config: a street grid with buildings of rooms off it."""
    grid = STREET_GRID * scale
    locations: dict[str, Any] = {}

    def place(location_id: str, name: str, terrain: str) -> None:
        locations[location_id] = {"known_by_default": True, "details": {"name": name, "terrain": terrain}, "exits": []}

    def link(origin: str, destination: str, position: str | None = None) -> None:
        exit_: dict[str, Any] = {"to": destination, "label": locations[destination]["details"]["name"]}
        if position:
            exit_["position"] = position
        locations[origin]["exits"].append(exit_)

    for row in range(grid):
        for column in range(grid):
            place(f"street_{row}_{column}", f"Street {row}-{column}", "city")
    for row in range(grid):
        for column in range(grid):
            if column + 1 < grid:
                link(f"street_{row}_{column}", f"street_{row}_{column + 1}", "e")
                link(f"street_{row}_{column + 1}", f"street_{row}_{column}", "w")
            if row + 1 < grid:
                link(f"street_{row}_{column}", f"street_{row + 1}_{column}", "s")
                link(f"street_{row + 1}_{column}", f"street_{row}_{column}", "n")
    for building in range(BUILDINGS * scale):
        # One building per street: a street has one "in" exit.
        street = f"street_{building // grid}_{building % grid}"
        rooms = [f"building_{building}_room_{index}" for index in range(ROOMS_PER_BUILDING)]
        for index, room in enumerate(rooms):
            place(room, f"Building {building} - Room {index}", "indoor")
        link(street, rooms[0], "in")
        link(rooms[0], street, "out")
        for index in range(1, ROOMS_PER_BUILDING):
            link(rooms[index - 1], rooms[index])
            link(rooms[index], rooms[index - 1])
    return {"locations": locations}


def _spread(index: int, size: int, salt: int = 0) -> int:
    """Return a repeatable, well-spread value in `range(size)` for `index`."""
    return (index * 7919 + salt * 104729) % size


def _fill_state(bindings: dict[str, Callable[..., Any]], places: list[str], scale: int) -> None:
    """Fill every plugin's state through its own bindings, as a long play-through would."""
    characters = [f"character_{index}" for index in range(CHARACTERS * scale)]
    for number, character in enumerate(characters):
        bindings["set_location"](character, places[_spread(number, len(places))])
        bindings["set_character_known"](character, True)
        for attribute in range(ATTRIBUTES_PER_CHARACTER):
            bindings["set_attribute"](character, f"attribute_{attribute}", _spread(number, 101, attribute))
        for skill in range(SKILLS_PER_CHARACTER):
            bindings["set_skill_level"](character, f"skill_{skill}", 1 + _spread(number, 5, skill))
    holders = ["player", *characters]
    for index in range(ITEMS * scale):
        if index % 2:
            bindings["give_item_to"](holders[_spread(index, len(holders))], f"item_{index}", 1)
        else:
            bindings["drop_item_at"](f"item_{index}", places[_spread(index, len(places))])
    for quest in range(QUESTS * scale):
        bindings["start_quest"](f"quest_{quest}", 1)
        bindings["set_quest_stage"](f"quest_{quest}", 1 + _spread(quest, 50))
        for goal in range(_spread(quest, GOALS_PER_QUEST + 1)):
            bindings["meet_goal"](f"quest_{quest}", f"goal_{goal}")
    for action in range(PRICED_ACTIONS * scale):
        bindings["set_cost"](f"action_{action}", "money", 1 + _spread(action, 500))
    bindings["advance_clock"](60 * 24 * 3)


def synthetic_session(scale: int) -> tuple[Session, dict[str, Any]]:
    """Return a session over every generic engine plugin, and its filled state.

    Args:
        scale: Multiplies every count above.

    Returns:
        The session, and the engine state after filling it the way a long
        play-through would.
    """
    plugins = discover_plugins([ENGINE_PLUGINS])
    town = _town_config(scale)
    session = Session(
        label=f"synthetic town, scale {scale}",
        plugins=plugins,
        active_names=list(plugins),
        list_defs={},
        configs={"location_graph": town},
    )
    engine_state: dict[str, Any] = {}
    _fill_state(session.bind(engine_state), list(town["locations"]), scale)
    return session, engine_state


def game_session(game: Path) -> tuple[Session, dict[str, Any]]:
    """Return a session over a real game's declared plugins, and its fresh state.

    Args:
        game: A game folder or bundle.

    Returns:
        The session, and the engine state its first binding allocated.
    """
    source = open_game_source(game)
    try:
        compiled = json.loads(source.read_text(find_main_story_file(source)))
        required = read_required_plugins(source)
    finally:
        source.close()
    # The mount stays in place: the game's plugin modules stay imported for the run.
    package = mount_game(game).package
    session = Session(
        label=f"game {game.name}",
        plugins=discover_plugins([ENGINE_PLUGINS, package]),
        active_names=required,
        list_defs=load_list_defs(compiled),
        configs={},
    )
    engine_state: dict[str, Any] = {}
    session.bind(engine_state)
    return session, engine_state


def _best_microseconds(statement: Callable[[], Any], *, calls: int = CALLS_PER_SAMPLE) -> float:
    """Return the best per-call time in microseconds, best of REPEATS; the fastest sample is the least disturbed."""
    samples = timeit.repeat(statement, repeat=REPEATS, number=calls)
    return min(samples) / calls * 1_000_000


def report(session: Session, engine_state: dict[str, Any]) -> None:
    """Measure one session and print the results.

    Args:
        session: What to bind.
        engine_state: The state to bind onto and serialize.
    """
    bindings = session.bind(engine_state)
    print(f"{session.label}   bindings: {len(bindings)}   state slots: {len(engine_state)}")
    print(f"best of {REPEATS}, {CALLS_PER_SAMPLE} calls per sample\n")

    print(f"{'bind a fresh session (allocate + bind)':<44}{_best_microseconds(lambda: session.bind({})):>9.1f} us")
    # The path every turn after the first runs.
    print(f"{'bind onto existing state (per turn)':<44}{_best_microseconds(lambda: session.bind(engine_state)):>9.1f} us")

    hot = bindings.get("clock")
    if hot is not None:
        # Nanoseconds: a slot read is far below microsecond resolution.
        print(f"{'hot read: clock()':<44}{_best_microseconds(hot, calls=100_000) * 1000:>9.0f} ns")
    else:
        print(f"{'hot read':<44}{'skipped (no clock binding)':>9}")

    encoded = json.dumps(engine_state)
    print(f"{'state -> JSON':<44}{_best_microseconds(lambda: json.dumps(engine_state)):>9.1f} us")
    print(f"{'JSON -> state':<44}{_best_microseconds(lambda: json.loads(encoded)):>9.1f} us")
    print(f"{'serialized state size':<44}{len(encoded):>9,} bytes")

    per_turn = statistics.mean(timeit.repeat(lambda: session.bind(engine_state), repeat=REPEATS, number=CALLS_PER_SAMPLE)) / CALLS_PER_SAMPLE
    print(f"\nplugin layer per turn: {per_turn * 1000:.3f} ms (mean)")


def main(argv: list[str] | None = None) -> None:
    """Parse the command line, build the session and report on it.

    Args:
        argv: The arguments, or None for `sys.argv`.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scale", type=int, default=1, help="multiply the synthetic town's size (default 1)")
    group.add_argument("--game", type=Path, help="measure this game folder or bundle instead")
    arguments = parser.parse_args(argv)
    report(*(game_session(arguments.game) if arguments.game else synthetic_session(arguments.scale)))


if __name__ == "__main__":
    main()
