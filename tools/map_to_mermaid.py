"""Draw a game's map as a Mermaid diagram.

    python tools/map_to_mermaid.py <game_dir>
    python tools/map_to_mermaid.py <game_dir> --save <session.json>

Reads a game's location graph and writes a Mermaid `flowchart` to
standard output: one node per location, one labelled arrow per exit, and
a line style per gate so a sealed door reads differently from an open
one.

**Mermaid has no absolute positioning**, so a map cannot be laid out
geographically. What the diagram does instead: a corridor declared from
both ends is drawn as one bidirectional arrow rather than two opposing
ones, and a north-south corridor is always drawn southward. The layout
engine then has one consistent pull per corridor, so on a top-down chart
north generally comes out above south. East and west are left to the
engine; `--direction LR` orients those instead.

With `--save`, the diagram is one session's: places the session has not
discovered are left out, visit counts appear beside the names, and an
exit whose attribute the session has set is drawn as passable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ink_engine.discovery import discover_plugins, mount_game
from ink_engine.engine_plugins.location_graph import (
    STATE_KEY,
    buildings,
    is_entrance,
    without_events,
)

try:  # when run as `python tools/map_to_mermaid.py`
    import map_layout_v2
    from map_layout import (
        PAGE_HEAD,
        PAGE_HEADER_START,
        build_graph,
        build_page,
        pair_key,
    )
except ModuleNotFoundError:  # when imported as `tools.map_to_mermaid`
    from tools import map_layout_v2
    from tools.map_layout import (
        PAGE_HEAD,
        PAGE_HEADER_START,
        build_graph,
        build_page,
        pair_key,
    )

#: Arrowheads say which way a corridor runs; a `linkStyle` line says
#: whether it is currently passable. A blocked corridor keeps its
#: arrowheads and is drawn grey and dashed, which is why the arrow is
#: never the thing that carries the gate: a thin dashed line makes a
#: second arrowhead hard to see, so `BLOCKED_WIDTH` keeps it heavy
#: enough to read.
ONE_WAY = "-->"
BOTH_WAYS = "<-->"

#: Applied to blocked corridors. The width keeps both arrowheads legible
#: on a dashed line.
BLOCKED_STYLE = "stroke:#b0b0b0,stroke-width:3px,stroke-dasharray:6 4"

#: Which position each graph direction runs along, and which of the pair
#: is drawn as the arrow's source. `flowchart TD` flows downward, so an
#: exit going south is drawn in that sense and its north twin is folded
#: into the same arrow -- which is what makes north come out above.
FLOW_DIRECTION = {
    "TD": ("s", "n"),
    "TB": ("s", "n"),
    "BT": ("n", "s"),
    "LR": ("e", "w"),
    "RL": ("w", "e"),
}

#: Characters Mermaid will not accept inside a node identifier.
_UNSAFE_IN_IDENTIFIER = " -./\\:()[]{}#\"'<>|+*&%$!?,;=@~`^"
_IDENTIFIER_SAFE = str.maketrans({character: "_" for character in _UNSAFE_IN_IDENTIFIER})


class MapDiagramError(Exception):
    """A game could not be read, or declares no map."""


def node_identifier(location_id: str, *, distinguish: bool = False) -> str:
    """Return a Mermaid-safe node identifier for a location id.

    Args:
        location_id: The id to convert.
        distinguish: Add a digest of the original id. Needed only when
            another id would translate to the same identifier — `a.b`
            and `a b` both reduce to `a_b` otherwise, and the two
            locations would draw as a single node.

    Returns:
        The identifier, readable in the diagram source.
    """
    safe = "loc_" + location_id.translate(_IDENTIFIER_SAFE)
    if not distinguish:
        return safe
    digest = hashlib.blake2s(location_id.encode("utf-8"), digest_size=3).hexdigest()
    return f"{safe}_{digest}"


def node_identifiers(location_ids: Iterable[str]) -> dict[str, str]:
    """Return one Mermaid-safe identifier per location id, all distinct.

    Ids that would otherwise share an identifier all take a digest
    suffix, so a diagram never draws two locations as one node.
    """
    plain: dict[str, list[str]] = {}
    for location_id in location_ids:
        plain.setdefault(node_identifier(location_id), []).append(location_id)
    return {location_id: node_identifier(location_id, distinguish=len(sharing) > 1) for sharing in plain.values() for location_id in sharing}


def quote(text: str) -> str:
    """Return text safe to sit inside a Mermaid label."""
    return text.replace('"', "&quot;").replace("\n", " ").strip()


def read_map(game_dir: Path) -> dict[str, Any]:
    """Return the location graph config a game declares.

    Mounts the game, so a game whose map lives in its own plugin module
    is read the same way an application reads it.

    Args:
        game_dir: A game folder or bundle.

    Returns:
        The `{"locations": {...}}` config, without its events.

    Raises:
        MapDiagramError: If the game cannot be mounted, or no plugin on
            the location graph's slot declares a map.
    """
    try:
        mounted = mount_game(game_dir)
    except Exception as error:  # Reported, not handled: any failure is the answer.
        raise MapDiagramError(f"could not mount {game_dir}: {error}") from error

    try:
        plugins = discover_plugins([game_dir.name])
    except Exception as error:  # Reported, not handled: any failure is the answer.
        raise MapDiagramError(f"could not read plugins from {game_dir}: {error}") from error
    finally:
        mounted.unmount()

    for plugin in plugins.values():
        if plugin.state_key != STATE_KEY:
            continue
        config = plugin.default_config
        if isinstance(config, dict) and config.get("locations"):
            return without_events(config)
    raise MapDiagramError(f"{game_dir} declares no map")


def read_session(save_path: Path) -> dict[str, Any]:
    """Return the location graph's slot from a saved session.

    Args:
        save_path: A saved session, or a bare engine state.

    Returns:
        The slot.

    Raises:
        MapDiagramError: If the file is not readable JSON, or holds no
            map state.
    """
    try:
        saved = json.loads(save_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MapDiagramError(f"could not read {save_path}: {error}") from error
    if not isinstance(saved, dict):
        raise MapDiagramError(f"{save_path} is not a saved session")
    state = saved.get("engine_state", saved)
    slot = state.get(STATE_KEY)
    if not isinstance(slot, dict):
        raise MapDiagramError(f"{save_path} holds no location state")
    return slot


def exit_is_passable(exit_declaration: dict[str, Any], slot: dict[str, Any] | None) -> bool:
    """Return whether an exit may be taken.

    Without a session this answers what the map alone decides, so an
    exit waiting on an attribute reads as blocked — nothing has set it
    yet.
    """
    if exit_declaration.get("sealed", False):
        return False
    destination = exit_declaration["to"]
    if slot is None:
        return not (exit_declaration.get("requires_known", False) or "unlocked_by" in exit_declaration)
    if exit_declaration.get("requires_known", False) and destination not in slot.get("known", ()):
        return False
    attribute = exit_declaration.get("unlocked_by")
    if attribute is None:
        return True
    attributes = slot.get("place_records", {}).get(destination, {}).get("attributes", {})
    return bool(attributes.get(attribute, False))


def exit_label(exit_declaration: dict[str, Any], locations: dict[str, Any]) -> str:
    """Return an exit's label, falling back the way the map itself does."""
    label = exit_declaration.get("label")
    if label:
        return str(label)
    destination = exit_declaration["to"]
    details = locations.get(destination, {}).get("details", {})
    return str(details.get("name", destination))


def location_label(location_id: str, declaration: dict[str, Any], slot: dict[str, Any] | None) -> str:
    """Return a location's node text, with its visit count when known."""
    name = str(declaration.get("details", {}).get("name", location_id))
    if slot is None:
        return name
    visits = slot.get("visits", {}).get(location_id, 0)
    return f"{name} \u00d7{visits}" if visits else name


def _fold_reciprocal_exits(
    locations: dict[str, Any],
    shown: Any,
    flow: tuple[str, str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return one entry per corridor, folding a there-and-back pair into one.

    Two exits describing the same corridor pull the layout in opposite
    directions if both are drawn. Folding them into a single
    bidirectional arrow leaves one pull per corridor, and drawing it in
    the sense the graph direction flows is what lets the layout engine
    put north above south.

    Args:
        locations: Every declared location.
        shown: Predicate deciding whether a location is drawn.
        flow: The position the graph direction flows along, and its
            return, e.g. `("s", "n")` for a top-down chart.

    Returns:
        corridor key -> the exit to draw, its origin and destination,
        and whether it runs both ways.
    """
    downstream, upstream = flow
    corridors: dict[tuple[str, str], dict[str, Any]] = {}
    for origin, declaration in locations.items():
        if not shown(origin):
            continue
        for exit_declaration in declaration.get("exits", []):
            destination = exit_declaration.get("to")
            if destination not in locations or not shown(destination):
                continue
            key = pair_key(origin, destination)
            position = exit_declaration.get("position")
            existing = corridors.get(key)
            if existing is None:
                corridors[key] = {
                    "exit": exit_declaration,
                    "origin": origin,
                    "destination": destination,
                    "both_ways": False,
                }
                continue
            existing["both_ways"] = True
            # Prefer to draw the half running with the flow, so the
            # layout engine sees every vertical corridor the same way up.
            if position == downstream and existing["exit"].get("position") == upstream:
                existing.update({"exit": exit_declaration, "origin": origin, "destination": destination})
    return corridors


def _exit_lines(
    locations: dict[str, Any],
    identifiers: dict[str, str],
    slot: dict[str, Any] | None,
    shown: Any,
    flow: tuple[str, str],
) -> tuple[list[str], list[int]]:
    """Return one arrow per corridor, and which of them are blocked.

    Mermaid numbers links from zero in the order they are declared, so
    the blocked list holds link numbers rather than line numbers.
    """
    lines: list[str] = []
    blocked: list[int] = []
    for corridor in _fold_reciprocal_exits(locations, shown, flow).values():
        exit_declaration = corridor["exit"]
        passable = exit_is_passable(exit_declaration, slot)
        arrow = BOTH_WAYS if corridor["both_ways"] else ONE_WAY
        label = quote(exit_label(exit_declaration, locations))
        position = exit_declaration.get("position")
        if position:
            label = f"{position}: {label}"
        lines.append(f"    {identifiers[corridor['origin']]} {arrow}|{label}| {identifiers[corridor['destination']]}")
        if not passable:
            blocked.append(len(lines) - 1)
    return lines, blocked


def _node_lines(
    locations: dict[str, Any],
    identifiers: dict[str, str],
    slot: dict[str, Any] | None,
    shown: Any,
) -> list[str]:
    """Return one node declaration per drawn location."""
    return [
        f'    {identifiers[location_id]}["{quote(location_label(location_id, declaration, slot))}"]'
        for location_id, declaration in locations.items()
        if shown(location_id)
    ]


#: A self-contained page that renders the diagram and lets the reader
#: drag and zoom it. Mermaid draws a static picture wherever Markdown is
#: rendered, which is unusable for a map of any size.
HTML_TEMPLATE = (
    PAGE_HEAD
    + """  :root {{ --ink: #1b1b1f; --paper: #fdfdfb; --edge: #d8d8d2; }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{ --ink: #e9e9ec; --paper: #16161a; --edge: #33333a; }}
  }}
  html, body {{ margin: 0; height: 100%; }}
  body {{ background: var(--paper); color: var(--ink);
         font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
         display: flex; flex-direction: column; }}
  header {{ padding: 10px 16px; border-bottom: 1px solid var(--edge);
            display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }}
  h1 {{ font-size: 15px; font-weight: 600; margin: 0; }}
  .hint {{ opacity: .65; }}
  button {{ font: inherit; color: inherit; background: transparent;
            border: 1px solid var(--edge); border-radius: 6px;
            padding: 3px 10px; cursor: pointer; }}
  button:hover {{ border-color: currentColor; }}
  #frame {{ flex: 1; overflow: hidden; touch-action: none; cursor: grab; }}
  #frame.dragging {{ cursor: grabbing; }}
  #frame svg {{ max-width: none !important; height: auto; }}
"""
    + PAGE_HEADER_START
    + """  <span class="hint">drag to pan &middot; scroll to zoom</span>
  <button id="reset" type="button">Reset view</button>
  <span class="hint" id="scale"></span>
</header>
<div id="frame"><pre class="mermaid">{diagram}</pre></div>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
const dark = matchMedia("(prefers-color-scheme: dark)").matches;
mermaid.initialize({{ startOnLoad: false, theme: dark ? "dark" : "default", maxTextSize: 500000 }});
await mermaid.run();

const frame = document.getElementById("frame");
const svg = frame.querySelector("svg");
const readout = document.getElementById("scale");
let scale = 1, x = 0, y = 0;

function apply() {{
  svg.style.transformOrigin = "0 0";
  svg.style.transform = `translate(${{x}}px, ${{y}}px) scale(${{scale}})`;
  readout.textContent = Math.round(scale * 100) + "%";
}}
function reset() {{ scale = 1; x = 0; y = 0; apply(); }}
document.getElementById("reset").addEventListener("click", reset);

frame.addEventListener("wheel", (event) => {{
  event.preventDefault();
  const box = frame.getBoundingClientRect();
  const px = event.clientX - box.left, py = event.clientY - box.top;
  const factor = Math.exp(-event.deltaY * 0.0015);
  const next = Math.min(8, Math.max(0.05, scale * factor));
  x = px - (px - x) * (next / scale);
  y = py - (py - y) * (next / scale);
  scale = next;
  apply();
}}, {{ passive: false }});

let dragging = false, lastX = 0, lastY = 0;
frame.addEventListener("pointerdown", (event) => {{
  dragging = true; lastX = event.clientX; lastY = event.clientY;
  frame.classList.add("dragging"); frame.setPointerCapture(event.pointerId);
}});
frame.addEventListener("pointermove", (event) => {{
  if (!dragging) return;
  x += event.clientX - lastX; y += event.clientY - lastY;
  lastX = event.clientX; lastY = event.clientY;
  apply();
}});
for (const end of ["pointerup", "pointercancel"]) {{
  frame.addEventListener(end, () => {{ dragging = false; frame.classList.remove("dragging"); }});
}}
reset();
</script>
</body>
</html>
"""
)


def _connected_locations(locations: dict[str, Any]) -> set[str]:
    """Return the locations that declare an exit or are named by one."""
    connected: set[str] = set()
    for location_id, declaration in locations.items():
        exits = declaration.get("exits", [])
        if not exits:
            continue
        connected.add(location_id)
        connected.update(exit_["to"] for exit_ in exits)
    return connected


def build_diagram(
    config: dict[str, Any],
    slot: dict[str, Any] | None = None,
    *,
    direction: str = "TD",
    connected_only: bool = False,
) -> str:
    """Return a Mermaid flowchart for a map.

    Args:
        config: The location graph config.
        slot: One session's slot, or None for the map as declared. With
            a session, undiscovered places are left out.
        direction: The Mermaid graph direction. `TD` flows downward, so
            a corridor running north-south is drawn with north above.
        connected_only: Leave out locations with no exits at all. A map
            partway through being given exits is otherwise mostly
            unconnected nodes.

    Returns:
        Mermaid source.
    """
    locations: dict[str, Any] = config.get("locations", {})
    known = set(slot.get("known", ())) if slot is not None else None
    connected = _connected_locations(locations) if connected_only else None

    def shown(location_id: str) -> bool:
        if connected is not None and location_id not in connected:
            return False
        return known is None or location_id in known

    identifiers = node_identifiers(locations)
    lines = [f"flowchart {direction}"]
    lines.extend(_node_lines(locations, identifiers, slot, shown))

    flow = FLOW_DIRECTION.get(direction, FLOW_DIRECTION["TD"])
    exit_lines, blocked = _exit_lines(locations, identifiers, slot, shown, flow)
    lines.extend(exit_lines)

    # A blocked exit is dashed and grey, so it reads as a way the player
    # cannot go without having to compare arrowheads.
    if blocked:
        indices = ",".join(str(index) for index in blocked)
        lines.append(f"    linkStyle {indices} {BLOCKED_STYLE}")
    return "\n".join(lines)


def aspect_ratio(text: str) -> float:
    """Parse `W:H` (or a plain number) as a width-to-height ratio for `--aspect`."""
    try:
        width, _, height = text.partition(":")
        ratio = float(width) / float(height or 1)
    except (ValueError, ZeroDivisionError) as error:
        raise argparse.ArgumentTypeError(f"expected W:H, such as 21:9, not {text!r}") from error
    if ratio <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive ratio, not {text!r}")
    return ratio


def write_version_2(arguments: argparse.Namespace, config: dict[str, Any], graph: dict[str, Any], pins: dict[str, list[float]] | None) -> None:
    """Write the version 2 page and SVG the arguments ask for, and print the layout's report."""
    tree = buildings(config) if any(is_entrance(config, location_id) for location_id in config["locations"]) else None
    result = map_layout_v2.layout(graph, pins, aspect=arguments.aspect, tree=tree)
    terrains = {location_id: declaration.get("details", {}).get("terrain") for location_id, declaration in config["locations"].items()}
    data = map_layout_v2.page_data(graph, result, terrains)
    if arguments.v2html:
        arguments.v2html.write_text(map_layout_v2.build_page(f"{arguments.game_dir.name} map", data), encoding="utf-8")
        print(f"wrote {arguments.v2html} ({len(data['nodes'])} places, {len(data['buildings'])} buildings)", file=sys.stderr)
    if arguments.v2svg:
        arguments.v2svg.write_text(map_layout_v2.build_svg(data, expanded=arguments.expanded), encoding="utf-8")
        print(f"wrote {arguments.v2svg}", file=sys.stderr)
    for item in result.report:
        print(f"  {item['kind']}: {item['place']}: {item['detail']}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Write a Mermaid diagram of a game's map to standard output."""
    parser = argparse.ArgumentParser(description="Draw a game's map as a Mermaid flowchart.")
    parser.add_argument("game_dir", type=Path, help="the game folder or bundle to read")
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        metavar="SESSION",
        help="a saved session: draws only discovered places, with visit counts",
    )
    parser.add_argument(
        "--direction",
        choices=sorted(FLOW_DIRECTION),
        default="TD",
        help="Mermaid graph direction; TD (the default) puts north above south",
    )
    parser.add_argument(
        "--connected-only",
        action="store_true",
        help="leave out locations that declare no exits and are named by none",
    )
    parser.add_argument(
        "--d3html",
        type=Path,
        default=None,
        metavar="PAGE",
        help="also write a page that lays the map out by its own compass directions",
    )
    parser.add_argument(
        "--v2html",
        type=Path,
        default=None,
        metavar="PAGE",
        help="also write the version 2 page: laid out on a compass grid, buildings opening on click",
    )
    parser.add_argument(
        "--v2svg",
        type=Path,
        default=None,
        metavar="FILE",
        help="also write the version 2 layout as a static SVG",
    )
    parser.add_argument(
        "--expanded",
        action="store_true",
        help="with --v2svg, draw every building open",
    )
    parser.add_argument(
        "--pins",
        type=Path,
        default=None,
        metavar="FILE",
        help="JSON of {location id: [x, y]} overriding version 2 positions (the page's 'Copy moved pins')",
    )
    parser.add_argument(
        "--aspect",
        type=aspect_ratio,
        default=map_layout_v2.DEFAULT_ASPECT,
        metavar="W:H",
        help="the width-to-height ratio to aim the version 2 map at, such as 21:9 for an ultrawide screen (default 16:9)",
    )
    parser.add_argument(
        "--fenced",
        action="store_true",
        help="wrap the diagram in a Markdown mermaid fence",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        metavar="PAGE",
        help="also write a page that renders the diagram, draggable and zoomable",
    )
    arguments = parser.parse_args(argv)

    try:
        config = read_map(arguments.game_dir)
        slot = read_session(arguments.save) if arguments.save else None
    except MapDiagramError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    diagram = build_diagram(config, slot, direction=arguments.direction, connected_only=arguments.connected_only)

    def exits_for(location_id: str) -> list[dict[str, Any]]:
        """Return one location's exits, each marked passable or not.

        Unlike the flowchart, a laid-out map keeps a blocked exit and
        draws it faintly: leaving it out would detach places that are
        only reached through a gate, and a map with holes in it is harder
        to read than one showing a shut door.
        """
        declaration = config["locations"][location_id]
        return [{**exit_declaration, "passable": exit_is_passable(exit_declaration, slot)} for exit_declaration in declaration.get("exits", [])]

    if arguments.d3html:
        graph = build_graph(config, exits_for, slot, connected_only=arguments.connected_only)
        arguments.d3html.write_text(build_page(f"{arguments.game_dir.name} map", graph), encoding="utf-8")
        print(
            f"wrote {arguments.d3html} " f"({len(graph['nodes'])} places, {len(graph['links'])} corridors)",
            file=sys.stderr,
        )

    if arguments.v2html or arguments.v2svg:
        try:
            pins = json.loads(arguments.pins.read_text(encoding="utf-8")) if arguments.pins else None
        except (OSError, ValueError) as error:
            print(f"error: could not read pins {arguments.pins}: {error}", file=sys.stderr)
            return 1
        write_version_2(arguments, config, build_graph(config, exits_for, slot, connected_only=arguments.connected_only), pins)

    if arguments.html:
        title = f"{arguments.game_dir.name} map"
        arguments.html.write_text(HTML_TEMPLATE.format(title=title, diagram=diagram), encoding="utf-8")
        print(f"wrote {arguments.html}", file=sys.stderr)

    print(f"```mermaid\n{diagram}\n```" if arguments.fenced else diagram)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
