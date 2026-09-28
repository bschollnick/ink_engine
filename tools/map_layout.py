"""Lay a map out by its own compass directions, as a draggable page.

A flowchart tool decides where nodes go by its own rules and throws the
compass away, so a place declared north of another lands wherever the
layout engine likes. This builds the graph as data and lets the browser
settle it with a force simulation that pulls each exit toward the
direction it declares: a north exit pulls its destination upward, a
south-east exit down and to the right.

Only an exit with a compass position pulls anything. A map that gives
bearings to its outdoor routes and none to the doors between rooms
leaves indoor places with no pull of their own; they settle beside
whatever they connect to, which is what a reader expects of a room
inside a building.

Used through `map_to_mermaid.py --d3html`.
"""

from __future__ import annotations

import json
from typing import Any

#: Unit vectors for each exit position, in screen terms: x grows right,
#: y grows downward, so north is negative y.
DIRECTION_VECTORS: dict[str, tuple[float, float]] = {
    "n": (0.0, -1.0),
    "ne": (0.7071, -0.7071),
    "e": (1.0, 0.0),
    "se": (0.7071, 0.7071),
    "s": (0.0, 1.0),
    "sw": (-0.7071, 0.7071),
    "w": (-1.0, 0.0),
    "nw": (-0.7071, -0.7071),
}

#: `up`, `down`, `in` and `out` describe movement rather than a bearing,
#: so they pull nothing and their exits are drawn without a direction.
NON_SPATIAL_POSITIONS = ("up", "down", "in", "out")

#: The opening and the header of both tools' pages, around each page's own
#: stylesheet. `str.format` fills `{title}`.
PAGE_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
"""
PAGE_HEADER_START = """</style>
</head>
<body>
<header>
  <h1>{title}</h1>
"""

PAGE = (
    PAGE_HEAD
    + """  /* Dark by default: a dense graph of thin lines is read on a dark
     ground, and leaving it to the browser's colour preference means the
     same map arrives white on one machine and dark on the next. */
  :root {{ --ink:#e9e9ec; --paper:#15151a; --edge:#32323a; --line:#6f6f7a;
           --road:#7aa6e8; --gated:#4a4a55; --indoor:#b6a7e8; --outdoor:#7fc39a; }}
  :root[data-theme="light"] {{ --ink:#1b1b1f; --paper:#fdfdfb; --edge:#d9d9d3;
    --line:#8a8a94; --road:#3f6fb5; --gated:#b8b8c0; --indoor:#7a6ea8; --outdoor:#2f6f4f; }}
  html,body {{ margin:0; height:100%; }}
  body {{ background:var(--paper); color:var(--ink); display:flex; flex-direction:column;
          font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
  header {{ padding:9px 14px; border-bottom:1px solid var(--edge);
            display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
  h1 {{ font-size:14px; font-weight:600; margin:0; }}
  label {{ display:flex; gap:6px; align-items:center; opacity:.85; }}
  input[type=range] {{ width:120px; }}
  button {{ font:inherit; color:inherit; background:transparent; border:1px solid var(--edge);
            border-radius:6px; padding:3px 9px; cursor:pointer; }}
  button:hover {{ border-color:currentColor; }}
  .hint {{ opacity:.6; }}
  #canvas {{ flex:1; cursor:grab; touch-action:none; }}
  #canvas.dragging {{ cursor:grabbing; }}
  .node-label {{ font-size:11px; paint-order:stroke; stroke:var(--paper);
                 stroke-width:3px; stroke-linejoin:round; pointer-events:none; }}
  .edge-label {{ font-size:9px; fill:var(--line); paint-order:stroke;
                 stroke:var(--paper); stroke-width:2.5px; pointer-events:none; }}
"""
    + PAGE_HEADER_START
    + """  <label>zoom <input id="zoom" type="range" min="8" max="600" value="75">
    <span id="zoomout" class="hint">75%</span></label>
  <label>compass pull <input id="pull" type="range" min="0" max="100" value="55"></label>
  <label>cluster <input id="cluster" type="range" min="0" max="100" value="70"></label>
  <label><input id="allnames" type="checkbox"> all place names</label>
  <label><input id="labels" type="checkbox"> edge labels</label>
  <button id="fit" type="button">Fit all</button>
  <button id="freeze" type="button">Freeze</button>
  <button id="reset" type="button">Reset</button>
  <span class="hint">drag a place to pin it &middot; scroll to zoom &middot; double-click to unpin</span>
</header>
<svg id="canvas"></svg>
<script type="module">
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";

const graph = {graph};
const nodes = graph.nodes.map(d => Object.assign({{}}, d));
const links = graph.links.map(d => Object.assign({{}}, d));

const svg = d3.select("#canvas");
const root = svg.append("g");
const linkLayer = root.append("g");
const labelLayer = root.append("g");
const nodeLayer = root.append("g");

const markers = [
  {{id: "head-open",  fill: "var(--line)",  back: false}},
  {{id: "head-gated", fill: "var(--gated)", back: false}},
  {{id: "tail-open",  fill: "var(--line)",  back: true}},
  {{id: "tail-gated", fill: "var(--gated)", back: true}},
];
svg.append("defs").selectAll("marker").data(markers).join("marker")
    .attr("id", d => d.id)
    .attr("viewBox", "0 -5 10 10").attr("refX", 0).attr("refY", 0)
    .attr("markerWidth", 6).attr("markerHeight", 6)
    .attr("orient", d => d.back ? "auto-start-reverse" : "auto")
  .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", d => d.fill);

const link = linkLayer.selectAll("line").data(links).join("line")
  .attr("stroke", d => d.gated ? "var(--gated)" : "var(--line)")
  .attr("stroke-width", d => d.gated ? 1.4 : 1.8)
  .attr("stroke-dasharray", d => d.gated ? "5 4" : null)
  .attr("marker-end", d => "url(#head-" + (d.gated ? "gated" : "open") + ")")
  .attr("marker-start", d => d.both ? "url(#tail-" + (d.gated ? "gated" : "open") + ")" : null);

const edgeText = labelLayer.selectAll("text").data(links).join("text")
  .attr("class", "edge-label").attr("text-anchor", "middle")
  .attr("display", "none")
  .text(d => d.position ? d.position + ": " + d.label : d.label);

// A press becomes a drag only once the pointer has actually moved far
// enough to mean it. Pinning the place and reheating the simulation on
// mousedown alone means a plain click reflows the whole map.
const DRAG_SLOP = 3;
//: Set by the Freeze button, read while dragging so a place still
//: follows the pointer when no tick is running.
let frozen = false;
const node = nodeLayer.selectAll("g").data(nodes).join("g").call(
  d3.drag()
    // The pan behaviour on the canvas ignores presses that land on a
    // place, so the two never compete for one gesture.
    .on("start", (event, d) => {{ d.__pressX = event.x; d.__pressY = event.y;
                                  d.__moved = false; }})
    .on("drag", (event, d) => {{
      if (!d.__moved) {{
        if (Math.hypot(event.x - d.__pressX, event.y - d.__pressY) < DRAG_SLOP) return;
        d.__moved = true;
        // A settled simulation runs no ticks, so a pinned place would
        // keep its old drawn position however far it is dragged. Raise
        // the temperature as well as the target to start it moving.
        if (!event.active) sim.alphaTarget(0.25).alpha(0.3).restart();
      }}
      d.fx = event.x; d.fy = event.y;
      // Draw the place under the pointer directly rather than waiting
      // for a tick. A settled or frozen simulation runs none, so the
      // place would otherwise stay where it was however far it is
      // dragged.
      d.x = event.x; d.y = event.y;
      tick();
    }})
    // A press that never moved is a click. The drag behaviour suppresses
    // the element's own click event, so the selection is made here.
    .on("end", (event, d) => {{
      if (d.__moved) {{ if (!event.active) sim.alphaTarget(0); return; }}
      picked = picked === d.id ? null : d.id;
      applyPick();
    }})
);
node.on("dblclick", (event, d) => {{
  event.stopPropagation();
  d.fx = null; d.fy = null; sim.alpha(0.4).restart();
}});

// Clicking a place picks it out: the place and what it connects to stay
// lit while the rest of the map dims, which is the only way to follow
// one place's exits through a drawing this dense. Clicking it again, or
// clicking the background, puts everything back.
//
// Three steps out are shown, fading with distance, so a road reads as
// its own frontage first and the district around it second.
const neighbourIds = new Map();
for (const item of nodes) neighbourIds.set(item.id, []);
for (const edge of links) {{
  const a = edge.source.id || edge.source;
  const b = edge.target.id || edge.target;
  neighbourIds.get(a).push(b);
  neighbourIds.get(b).push(a);
}}

//: How far each step out is faded. Index 0 is the picked place itself.
const PICK_OPACITY = [1, 1, 0.5, 0.25];
const PICK_REACH = PICK_OPACITY.length - 1;

//: Everything further than `PICK_REACH`. Faint enough to read as ground
//: the selection sits on rather than as part of it.
const PICK_BACKGROUND = 0.03;

function stepsFrom(start) {{
  // Breadth-first, so a place reached two ways takes its shortest
  // distance rather than whichever was walked first.
  const depth = new Map([[start, 0]]);
  let frontier = [start];
  for (let step = 1; step <= PICK_REACH; step += 1) {{
    const next = [];
    for (const here of frontier) {{
      for (const other of neighbourIds.get(here) || []) {{
        if (depth.has(other)) continue;
        depth.set(other, step);
        next.push(other);
      }}
    }}
    frontier = next;
  }}
  return depth;
}}

let picked = null;
let pickDepth = null;
function fadeOf(id) {{
  if (!pickDepth) return 1;
  const step = pickDepth.get(id);
  return step === undefined ? PICK_BACKGROUND : PICK_OPACITY[step];
}}

function applyPick() {{
  pickDepth = picked ? stepsFrom(picked) : null;
  node.style("opacity", d => fadeOf(d.id));
  node.select("text.node-label").attr("display", d =>
    pickDepth
      // Name what the reader is looking at, out to the second step;
      // the third is context and would only crowd it.
      ? ((pickDepth.get(d.id) ?? 99) <= 2 ? null : "none")
      : (showAllLabels || (d.degree || 0) >= labelFloor ? null : "none"));
  // An exit is as visible as the dimmer of the two places it joins, so
  // a line never outshines what it connects.
  link.style("opacity", d =>
    Math.min(fadeOf(d.source.id || d.source), fadeOf(d.target.id || d.target)));
  edgeText.style("opacity", d =>
    Math.min(fadeOf(d.source.id || d.source), fadeOf(d.target.id || d.target)));
}}

// Clicking the background clears the selection.
svg.on("click", (event) => {{
  if (picked && event.target === svg.node()) {{ picked = null; applyPick(); }}
}});

// Rooms of one building pull toward each other's centre, so a building's
// rooms settle together rather than scattering across the map.
// Groups come from the names themselves -- everything before the first
// " - " -- so nothing has to be listed by hand.
const groups = new Map();
for (const item of nodes) {{
  if (!groups.has(item.group)) groups.set(item.group, []);
  groups.get(item.group).push(item);
}}
let cluster = 0.7;
function clusterForce(alpha) {{
  const strength = cluster * alpha;
  if (!strength) return;
  for (const members of groups.values()) {{
    if (members.length < 2) continue;
    let cx = 0, cy = 0;
    for (const item of members) {{ cx += item.x; cy += item.y; }}
    cx /= members.length; cy /= members.length;
    for (const item of members) {{
      item.vx += (cx - item.x) * strength;
      item.vy += (cy - item.y) * strength;
    }}
  }}
}}

// A colour per building, so a clump reads as one place at a glance.
// Groups of one keep the plain indoor/outdoor colours rather than
// spending a hue on a place that has no siblings.
const bigGroups = [...groups.entries()].filter(([, m]) => m.length > 1).map(([name]) => name);
const hue = d3.scaleOrdinal(bigGroups, bigGroups.map((_, i) => `hsl(${{(i * 360 / bigGroups.length + 25) % 360}} 55% 55%)`));

node.append("circle")
  .attr("r", d => (d.outdoor ? 7 : 5) + Math.min(6, (d.degree || 0) * 0.35))
  .attr("fill", d => (groups.get(d.group) || []).length > 1
    ? hue(d.group)
    : (d.outdoor ? "var(--outdoor)" : "var(--indoor)"))
  .attr("stroke", "var(--paper)").attr("stroke-width", 1.5);
// A name is written one line per part, breaking at each " - " --
// "Harbour - Warehouse - Loft" becomes three stacked lines. A 50-character name drawn on one line reaches
// across a quarter of the map and crosses everything in the way.
const LABEL_LINE_HEIGHT = 11;
const labelLines = d => d.name.split(" - ");

node.append("text").attr("class", "node-label")
  .attr("x", 11).attr("fill", "var(--ink)")
  .each(function (d) {{
    const lines = labelLines(d);
    // Centre the stack on the place rather than hanging it below.
    const top = 4 - (lines.length - 1) * LABEL_LINE_HEIGHT / 2;
    d3.select(this).selectAll("tspan").data(lines).join("tspan")
      .attr("x", 11)
      .attr("y", (line, index) => top + index * LABEL_LINE_HEIGHT)
      .text(line => line);
  }});
node.append("title").text(d => d.id);

// Each positioned exit pulls its two places toward the declared bearing.
// Unpositioned exits pull nothing, so an interior settles beside what it
// connects to rather than being flung along an invented axis.
let pull = 0.55;
function compassForce(alpha) {{
  const strength = pull * alpha;
  if (!strength) return;
  for (const edge of links) {{
    if (!edge.vector) continue;
    const [ux, uy] = edge.vector;
    const dx = edge.target.x - edge.source.x;
    const dy = edge.target.y - edge.source.y;
    const distance = Math.hypot(dx, dy) || 1;
    // Where the target should sit if it honoured its direction exactly.
    const wantX = edge.source.x + ux * distance;
    const wantY = edge.source.y + uy * distance;
    // Most declared exits run north-south, so an equal pull on both axes
    // grows the map into a tall column that wastes the width of any
    // screen. The vertical half is eased hard to even it out; the
    // bearing still reads, because what matters is that north is above
    // south rather than how far above.
    const shiftX = (wantX - edge.target.x) * strength;
    const shiftY = (wantY - edge.target.y) * strength * 0.22;
    edge.target.vx += shiftX; edge.target.vy += shiftY;
    edge.source.vx -= shiftX; edge.source.vy -= shiftY;
  }}
}}

// A place with twenty ways out needs far more room than one with two,
// and a 50-character name needs more than its 7px circle suggests. Both
// are measured rather than assumed: a flat repulsion leaves hubs in a
// knot and long labels stacked on top of each other.
const byId = new Map(nodes.map(n => [n.id, n]));
for (const item of nodes) item.degree = 0;
for (const edge of links) {{
  const from = byId.get(edge.source.id || edge.source);
  const to = byId.get(edge.target.id || edge.target);
  if (from) from.degree += 1;
  if (to) to.degree += 1;
}}
// The widest line of a name, since a name is drawn stacked. ~5.4px per
// character at 11px.
const labelWidth = d =>
  7 + Math.max(...d.name.split(" - ").map(line => line.length)) * 5.4;

// Keeping buildings apart is a separate job from gathering each one:
// charge acts per node, so a building of twenty rooms pushes no harder as
// a group than one of four, and two buildings end up overlapping.
function separateForce(alpha) {{
  const centres = [];
  for (const [name, members] of groups) {{
    if (members.length < 2) continue;
    let cx = 0, cy = 0;
    for (const item of members) {{ cx += item.x; cy += item.y; }}
    centres.push({{name, x: cx / members.length, y: cy / members.length,
                  radius: 64 + Math.sqrt(members.length) * 34, members}});
  }}
  const push = alpha * 0.7;
  for (let i = 0; i < centres.length; i += 1) {{
    for (let j = i + 1; j < centres.length; j += 1) {{
      const a = centres[i], b = centres[j];
      const dx = b.x - a.x, dy = b.y - a.y;
      const distance = Math.hypot(dx, dy) || 1;
      const wanted = a.radius + b.radius;
      if (distance >= wanted) continue;
      const shift = (wanted - distance) / distance * push;
      // Widen the horizontal half, damp the vertical: two buildings end
      // up beside each other instead of one being flung up or down.
      const mx = dx * shift * 1.5, my = dy * shift * 0.35;
      for (const item of a.members) {{ item.vx -= mx; item.vy -= my; }}
      for (const item of b.members) {{ item.vx += mx; item.vy += my; }}
    }}
  }}
}}

const outsideLinks = new Map();
for (const edge of links) {{
  const a = byId.get(edge.source.id || edge.source);
  const b = byId.get(edge.target.id || edge.target);
  if (!a || !b || a.group === b.group) continue;
  outsideLinks.set(a.group, (outsideLinks.get(a.group) || 0) + 1);
  outsideLinks.set(b.group, (outsideLinks.get(b.group) || 0) + 1);
}}

function tetherForce(alpha) {{
  let cx = 0, cy = 0;
  for (const item of nodes) {{ cx += item.x; cy += item.y; }}
  cx /= nodes.length; cy /= nodes.length;
  for (const [name, members] of groups) {{
    const ties = outsideLinks.get(name) || 0;
    if (ties > 3) continue;
    // One link out is a thread; three is an anchor. Pull hardest on the
    // thread.
    const strength = alpha * 0.05 * (4 - ties);
    for (const item of members) {{
      item.vx += (cx - item.x) * strength;
      item.vy += (cy - item.y) * strength;
    }}
  }}
}}

// Each building is held at a set distance from the road it opens onto,
// and pushed around the circle away from its neighbours -- so a road's
// frontage spreads into a star rather than a pile on one side.
// Which road each place belongs to. A building opening onto a road
// belongs to it directly; a room inside that building belongs to the
// same road, and so on inward. Without walking the chain, a room that
// does not open straight onto a road answers to no road at all and is
// placed by nothing but the generic charge, so it scatters.
const neighbours = new Map();
for (const edge of links) {{
  const a = edge.source.id || edge.source;
  const b = edge.target.id || edge.target;
  if (!neighbours.has(a)) neighbours.set(a, []);
  if (!neighbours.has(b)) neighbours.set(b, []);
  neighbours.get(a).push(b);
  neighbours.get(b).push(a);
}}

// Breadth-first from every road at once, recording the road each place
// answers to. A building opening onto a road answers to it; a room
// inside that building answers to the same road, and so on inward.
const roadOf = new Map();
const queue = [];
for (const item of nodes) {{
  if (item.road) {{ roadOf.set(item.id, item.id); queue.push(item.id); }}
}}
for (let head = 0; head < queue.length; head += 1) {{
  const here = queue[head];
  for (const next of neighbours.get(here) || []) {{
    if (roadOf.has(next)) continue;
    roadOf.set(next, roadOf.get(here));
    queue.push(next);
  }}
}}

// A road's frontage is its groups, not its individual rooms. Placing
// each room on the door it is reached through turns a building with
// several doors onto the road into one ring per door. Instead the whole
// group takes one position on the road, and the rooms arrange
// themselves inside it.
// How many places stand on each road, counting rooms reached through
// them. A road with none needs no room cleared around it.
const frontageCount = new Map();
for (const item of nodes) {{
  const road = roadOf.get(item.id);
  if (road && road !== item.id) {{
    frontageCount.set(road, (frontageCount.get(road) || 0) + 1);
  }}
}}

const frontage = new Map();
const groupRoad = new Map();
for (const [name, members] of groups) {{
  // A group of roads -- a park's paths, a wilderness trail -- is held
  // together by the cluster force instead: it has no frontage position
  // to take, because it is itself part of the road network.
  if (members.every(item => item.road)) continue;
  // The road most of the group answers to, so one oddly-connected room
  // cannot drag the building to the wrong street.
  const tally = new Map();
  for (const item of members) {{
    const road = roadOf.get(item.id);
    if (road) tally.set(road, (tally.get(road) || 0) + 1);
  }}
  if (tally.size === 0) continue;
  const [best] = [...tally.entries()].sort((a, b) => b[1] - a[1]);
  groupRoad.set(name, best[0]);
  if (!frontage.has(best[0])) frontage.set(best[0], []);
  frontage.get(best[0]).push(name);
}}

function frontageForce(alpha) {{
  for (const [roadId, names] of frontage) {{
    const road = byId.get(roadId);
    if (!road) continue;
    names.forEach((name, index) => {{
      const members = groups.get(name) || [];
      if (members.length === 0) return;
      // Wide enough that a big building clears its neighbours on the
      // ring, measured from how much room the building itself needs.
      const ring = 120 + names.length * 21 + Math.sqrt(members.length) * 24;
      const angle = (index / names.length) * Math.PI * 2;
      const wantX = road.x + Math.cos(angle) * ring;
      const wantY = road.y + Math.sin(angle) * ring;
      // A large building holds its own position: twenty rooms linked to
      // each other have enough link force to stay put. A house with one
      // link has none, and the road's own charge drives it away -- which
      // is what strands a single house in the middle of somewhere else.
      // The fewer members, the harder it is held here.
      const hold = alpha * (members.length > 3 ? 0.5 : 1.1);
      // Cancel the road's repulsion on what belongs to it. forceManyBody
      // pushes every pair alike and cannot be told to skip one, so the
      // push a road gives its own frontage is undone here; without this
      // a degree-1 house is simply thrown off its street.
      let cx = 0, cy = 0;
      for (const item of members) {{ cx += item.x; cy += item.y; }}
      cx /= members.length; cy /= members.length;
      const awayX = cx - road.x, awayY = cy - road.y;
      const span = Math.hypot(awayX, awayY) || 1;
      if (span < 1100) {{
        const standing = frontageCount.get(roadId) || 0;
        const undo = Math.min(1400, 900 + road.degree * 60 + standing * 40)
          * alpha / (span * span);
        for (const item of members) {{
          item.vx -= awayX / span * undo;
          item.vy -= awayY / span * undo;
        }}
      }}
      const shiftX = (wantX - cx) * hold;
      const shiftY = (wantY - cy) * hold;
      for (const item of members) {{ item.vx += shiftX; item.vy += shiftY; }}
    }});
  }}
}}

// Declared before the simulation, which fires its first tick as it is
// built: a `const` read from `tick()` before this point is in the
// temporal dead zone, and the ReferenceError leaves every node without
// a position while the page shows no error.
const nodeRadius = d => (d.outdoor ? 7 : 5);
const withArrow = d => nodeRadius(d) + 7;

const sim = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(links).id(d => d.id)
    .distance(d => {{
      // A door between two rooms of one building is short; a road
      // between two parts of town is long. Without the distinction a
      // building's rooms spread as wide as the streets around it.
      if (d.source.group === d.target.group) return 95;
      const busiest = Math.max(d.source.degree || 1, d.target.degree || 1);
      // Two roads are a street apart, with room for the buildings that
      // stand on each of them between the two centres. The collision
      // radius below sets the real minimum; this only has to not fight
      // it.
      if (d.source.road && d.target.road) return 240 + busiest * 5;
      return (d.vector ? 95 : 60) + busiest * 4;
    }})
    .strength(d => d.source.group === d.target.group ? 0.55 : 0.35))
  // Roads push hard on each other to spread the town out; a building
  // barely pushes at all, so it can sit close to the road it stands on
  // instead of being driven off it.
  //
  // A road pushes in proportion to what stands on it. An outdoor place
  // with nothing reached through it -- a park path, a lakeside -- needs
  // no room cleared around it, and pushing as hard as a high street
  // drives the chain of them apart across the whole map.
  .force("charge", d3.forceManyBody()
    .strength(d => {{
      if (!d.road) return -90;
      const standing = frontageCount.get(d.id) || 0;
      if (standing === 0) return -240;
      // A road clears room for itself and for everything standing on
      // it, so a street with a dozen buildings pushes further than one
      // with two. Capped: an uncapped total drives the road network
      // apart faster than the links can pull it back, and the map flies
      // off the screen instead of settling.
      return -Math.min(1400, 900 + d.degree * 60 + standing * 40);
    }})
    .distanceMax(1100))
  // A road keeps a clear circle around itself wide enough for its own
  // frontage, so two streets cannot sit on top of each other however
  // hard the links between them pull. Collision is a hard limit where
  // charge is only a push, and a push loses to a link at short range.
  .force("collide", d3.forceCollide(d => d.road
      ? 95 + Math.min(85, Math.sqrt(frontageCount.get(d.id) || 0) * 26)
      : 40 + Math.min(34, (d.degree || 0) * 2.2)).strength(0.9))
  .force("compass", compassForce)
  .force("cluster", clusterForce)
  .force("separate", separateForce)
  .force("frontage", frontageForce)
  .force("tether", tetherForce)
  .on("tick", tick);

function tick() {{
  // Ending the line at the node's edge is what keeps an arrowhead
  // attached to something: a fixed `refX` cannot know a node's radius,
  // so it leaves one floating whenever the two ends differ in size.
  link.each(function (d) {{
    const dx = d.target.x - d.source.x, dy = d.target.y - d.source.y;
    const distance = Math.hypot(dx, dy) || 1;
    const ux = dx / distance, uy = dy / distance;
    // Only an end that carries an arrowhead needs room for one.
    const from = d.both ? withArrow(d.source) : nodeRadius(d.source);
    const to = withArrow(d.target);
    d3.select(this)
      .attr("x1", d.source.x + ux * from).attr("y1", d.source.y + uy * from)
      .attr("x2", d.target.x - ux * to)
      .attr("y2", d.target.y - uy * to);
  }});
  edgeText.attr("x", d => (d.source.x + d.target.x) / 2)
          .attr("y", d => (d.source.y + d.target.y) / 2 - 3);
  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}}

// At a distance only the busiest places are named; the rest appear as
// the reader zooms in. Drawing all 270 names at once is what makes the
// whole map unreadable rather than merely crowded.
let showAllLabels = false;
//: The busyness a place must reach to be named at the current scale.
//: Shared with the pick highlight, which restores these names when the
//: selection is cleared.
let labelFloor = 7;
function labelVisibility(scale) {{
  // Names come in as the reader zooms, busiest first. The thresholds are
  // low because a name that only appears at high zoom is a name nobody
  // reads: by then the place is already the only thing on screen.
  labelFloor = scale > 1.1 ? 0 : scale > 0.85 ? 2 : scale > 0.6 ? 4 : 7;
  // A picked place owns which names are shown; a zoom must not undo it.
  if (picked) return;
  node.select("text.node-label").attr("display", d =>
    showAllLabels || (d.degree || 0) >= labelFloor ? null : "none");
}}

const zoomSlider = document.getElementById("zoom");
const zoomReadout = document.getElementById("zoomout");

const zoom = d3.zoom().scaleExtent([0.08, 6])
  // A press that begins on a place belongs to that place, not to the
  // canvas: without this the pan behaviour claims the gesture and the
  // whole map slides while the place stays where it was. A wheel is
  // always a zoom, wherever the pointer happens to sit.
  .filter(event => event.type === "wheel"
    || !(event.target instanceof SVGCircleElement || event.target instanceof SVGTextElement))
  .on("zoom", (event) => {{
  root.attr("transform", event.transform);
  labelVisibility(event.transform.k);
  // Scrolling and the slider drive the same transform, so the slider
  // follows the wheel rather than fighting it.
  zoomSlider.value = Math.round(event.transform.k * 100);
  zoomReadout.textContent = Math.round(event.transform.k * 100) + "%";
}});
svg.call(zoom);
labelVisibility(0.75);

function zoomTo(scale, animate) {{
  // Keep whatever sits at the middle of the view in the middle of the
  // view. Working from the graph coordinate under that point, rather
  // than from the previous transform, is what stops a slider drag
  // compounding its own output and sending the view off the map.
  const box = svg.node().getBoundingClientRect();
  const current = d3.zoomTransform(svg.node());
  const cx = box.width / 2, cy = box.height / 2;
  const [gx, gy] = current.invert([cx, cy]);
  const next = d3.zoomIdentity.translate(cx - gx * scale, cy - gy * scale).scale(scale);
  (animate ? svg.transition().duration(300) : svg).call(zoom.transform, next);
}}

function centreAt(scale) {{
  // Put the middle of the laid-out graph in the middle of the window at
  // the given scale. 100% is the default because a map this size is read
  // by zooming around it, not by shrinking it until it fits.
  const box = svg.node().getBoundingClientRect();
  const xs = nodes.map(n => n.x).filter(Number.isFinite);
  const ys = nodes.map(n => n.y).filter(Number.isFinite);
  if (!xs.length) return;
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  svg.transition().duration(350).call(zoom.transform,
    d3.zoomIdentity.translate(box.width / 2 - scale * cx, box.height / 2 - scale * cy).scale(scale));
}}

function fit() {{
  // Measure what was actually laid out. A fixed scale leaves most of a
  // large map off-screen, which is indistinguishable from it being broken.
  const box = svg.node().getBoundingClientRect();
  const xs = nodes.map(n => n.x).filter(Number.isFinite).sort((a, b) => a - b);
  const ys = nodes.map(n => n.y).filter(Number.isFinite).sort((a, b) => a - b);
  if (!xs.length) return;
  // Fit the bulk, not the outliers. A handful of places hanging off the
  // edge otherwise set the scale for everything, and "fit all" shrinks
  // the map to the point where none of it can be read.
  const edge = at => {{
    const i = Math.floor(at * (xs.length - 1));
    return i;
  }};
  const lo = edge(0.02), hi = edge(0.98);
  const minX = xs[lo], maxX = xs[hi];
  const minY = ys[lo], maxY = ys[hi];
  const width = Math.max(1, maxX - minX), height = Math.max(1, maxY - minY);
  const scale = Math.max(0.3, Math.min(1.4,
    0.92 * Math.min(box.width / width, box.height / height)));
  const x = box.width / 2 - scale * (minX + maxX) / 2;
  const y = box.height / 2 - scale * (minY + maxY) / 2;
  svg.transition().duration(400).call(zoom.transform,
    d3.zoomIdentity.translate(x, y).scale(scale));
}}
setTimeout(() => centreAt(1), 1200);

zoomSlider.addEventListener("input", (event) => zoomTo(event.target.value / 100, false));

document.getElementById("cluster").addEventListener("input", (event) => {{
  cluster = event.target.value / 100;
  sim.alpha(0.5).restart();
}});
document.getElementById("pull").addEventListener("input", (event) => {{
  pull = event.target.value / 100;
  sim.alpha(0.5).restart();
}});
document.getElementById("allnames").addEventListener("change", (event) => {{
  showAllLabels = event.target.checked;
  labelVisibility(d3.zoomTransform(svg.node()).k);
}});
document.getElementById("labels").addEventListener("change", (event) => {{
  edgeText.attr("display", event.target.checked ? null : "none");
}});
document.getElementById("fit").addEventListener("click", fit);
// Freeze holds the layout still; pressing it again releases it. A
// one-way freeze leaves the map permanently inert, with dragging a
// place appearing to do nothing.
const freezeButton = document.getElementById("freeze");
freezeButton.addEventListener("click", () => {{
  frozen = !frozen;
  freezeButton.textContent = frozen ? "Unfreeze" : "Freeze";
  if (frozen) sim.stop(); else sim.alpha(0.3).restart();
}});
document.getElementById("reset").addEventListener("click", () => {{
  for (const item of nodes) {{ item.fx = null; item.fy = null; }}
  sim.alpha(1).restart();
  centreAt(1);
}});
</script>
</body>
</html>
"""
)


def group_of(name: str) -> str:
    """Return the building or area a place belongs to.

    Taken from the name itself: everything before the first " - ", for
    names written as "Building - Room" ("Harbour - Warehouse"). A place
    with no " - " is its own group.
    """
    return name.split(" - ")[0].strip()


def pair_key(origin: str, destination: str) -> tuple[str, str]:
    """Return a key naming the corridor between two locations, either way round."""
    return (origin, destination) if origin <= destination else (destination, origin)


def _corridors(locations: dict[str, Any], exits_for: Any, shown: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """Merge every shown exit into one corridor per pair of places."""
    corridors: dict[tuple[str, str], dict[str, Any]] = {}
    for origin in locations:
        if not shown(origin):
            continue
        for exit_declaration in exits_for(origin):
            destination = exit_declaration["to"]
            if destination not in locations or not shown(destination):
                continue
            position = exit_declaration.get("position")
            existing = corridors.get(pair_key(origin, destination))
            if existing is None:
                corridors[pair_key(origin, destination)] = {
                    "source": origin,
                    "target": destination,
                    "label": exit_declaration.get("label") or destination,
                    "position": position if position in DIRECTION_VECTORS else None,
                    "gated": not exit_declaration.get("passable", True),
                    "both": False,
                }
                continue
            existing["both"] = True
            # A corridor a player cannot walk in one direction is not
            # freely open: whichever half is blocked decides, or a door
            # locked from one side would draw as an ordinary door.
            existing["gated"] = existing["gated"] or not exit_declaration.get("passable", True)
            # Prefer the half that declares a bearing, so the corridor
            # has something to pull it.
            if existing["position"] is None and position in DIRECTION_VECTORS:
                existing.update(
                    {
                        "source": origin,
                        "target": destination,
                        "position": position,
                        "label": exit_declaration.get("label") or destination,
                    }
                )
    return corridors


def build_graph(
    config: dict[str, Any],
    exits_for: Any,
    slot: dict[str, Any] | None = None,
    *,
    connected_only: bool = True,
) -> dict[str, Any]:
    """Return the nodes and links the page lays out.

    A corridor declared from both ends becomes one link carrying two
    arrowheads, drawn in whichever half declares a direction.

    Args:
        config: The location graph config.
        exits_for: Callable taking a location id and returning the exits
            to draw for it, already filtered for the session.
        slot: One session's slot, or None for the map as declared.
        connected_only: Leave out places with no exits either way.

    Returns:
        `{"nodes": [...], "links": [...]}`, ready to serialize.
    """
    locations: dict[str, Any] = config.get("locations", {})
    known = set(slot.get("known", ())) if slot is not None else None

    def shown(location_id: str) -> bool:
        return known is None or location_id in known

    corridors = _corridors(locations, exits_for, shown)

    touched = {end for corridor in corridors.values() for end in (corridor["source"], corridor["target"])}
    nodes = [
        {
            "id": location_id,
            "name": declaration.get("details", {}).get("name", location_id),
            "group": group_of(declaration.get("details", {}).get("name", location_id)),
            "outdoor": declaration.get("details", {}).get("terrain") in ("outdoor", "city", "field"),
        }
        for location_id, declaration in locations.items()
        if shown(location_id) and (location_id in touched or not connected_only)
    ]
    links = [{**corridor, "vector": DIRECTION_VECTORS.get(corridor["position"] or "")} for corridor in corridors.values()]
    # An outdoor place is part of the road network; everything else is a
    # building or a room reached from one. The two are laid out
    # differently, so the page is told which is which.
    #
    # Read from the terrain the location declares rather than from
    # whether an exit happens to carry a bearing. A road whose exits
    # declare no direction is still a road; classifying by bearing would
    # lay out one end of such a street as a road and the other as a
    # building.
    for node in nodes:
        node["road"] = node["outdoor"]
    return {"nodes": nodes, "links": links}


def build_page(title: str, graph: dict[str, Any]) -> str:
    """Return a self-contained page laying the graph out by compass."""
    return PAGE.format(title=title, graph=json.dumps(graph, indent=None))
