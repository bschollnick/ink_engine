# Tools

**Date Created:** 2026-09-21  
**Last Updated:** 2026-09-25  
**Last Reviewed:** 2026-09-21

Scripts for looking at a game from outside it. Nothing here is imported
by the engine, and no game depends on it.

## `map_to_mermaid.py`

Answers: **what does this game's map actually look like, and where can a
player get to from where?**

A map is declared as configuration — a location graph of places and the
exits between them — and reading it as configuration does not show the
shape of it. This draws the same data as a
[Mermaid](https://mermaid.js.org) flowchart, which GitHub, many editors
and Mermaid's own live editor render as a picture.

```bash
python tools/map_to_mermaid.py <game_dir>
python tools/map_to_mermaid.py <game_dir> --save <session.json>
python tools/map_to_mermaid.py <game_dir> --fenced >> notes.md
```

One node per location, one labelled arrow per exit, with the exit's
position before its label. An exit a player cannot currently take —
`sealed`, gated on `requires_known`, or waiting on the attribute named
by `unlocked_by` — is drawn as a grey dashed arrow.

**`--save` draws one session instead of the map as declared.** Places
the session has not discovered are left out, visit counts appear beside
the names, and an exit whose attribute the session has set is drawn as
passable. That turns the diagram into a picture of where a player has
been and what they have opened.

**Mermaid has no absolute positioning**, so a map cannot be laid out
geographically. Two things are done instead. A corridor declared from
both ends is drawn as a single bidirectional arrow rather than two
arrows pulling the layout apart, and a north-south corridor is always
drawn southward whichever end declared it. The layout engine then sees
one consistent pull per corridor, so on the default top-down chart north
generally comes out above south.

`--connected-only` leaves out locations that declare no exits, which is
what makes a partly converted map readable: a map that declares many
places but connects only a few otherwise draws every unconnected place
as a loose node around the part worth looking at.

East and west are left to the engine. `--direction LR` orients those
instead, at the cost of north and south; `TD`, `TB`, `BT`, `LR` and `RL`
are all accepted. For a road network, where connections are named routes
rather than compass directions, the labels carry the meaning and the
orientation matters less.

### A map laid out by its compass: `--d3html`

`--d3html PAGE` also writes a self-contained page that lays the map out
by the directions its exits declare, which Mermaid cannot. The page
loads D3 from `cdn.jsdelivr.net`, so opening it needs network access.
The layout code is `map_layout.py`.

A force simulation settles the places:

- An exit with a compass position pulls its destination that way: north
  up, south-east down and to the right. `up`, `down`, `in` and `out`
  pull nothing.
- Places whose names share a prefix before " - " ("Harbour - Warehouse",
  "Harbour - Loft") are one building: they gather together and share a
  colour.
- Places whose terrain is `outdoor`, `city` or `field` form the road
  network. Each building is held at a distance around the road it opens
  onto, and rooms inside it follow.
- A blocked exit is drawn faintly rather than left out, so a place
  reached only through a gate stays attached.

The page has sliders for zoom, compass pull and cluster strength,
switches for all place names and edge labels, and Fit all, Freeze and
Reset buttons. Dragging a place pins it; double-clicking unpins it.

```
$ python tools/map_to_mermaid.py examples/cloak_of_darkness --d3html cloak_map.html > /dev/null
wrote cloak_map.html (4 places, 3 corridors)
```

`--html PAGE` writes the Mermaid diagram itself as a draggable, zoomable
page.

### Version 2: a map laid out on a compass grid: `--v2html` and `--v2svg`

`--v2html PAGE` and `--v2svg FILE` draw the same map from positions
computed in Python by `map_layout_v2.py`, rather than by a force
simulation in the browser. `--d3html` is unchanged and still available.

- Every place reached by compass exits takes a grid cell, one bearing step
  per exit, so a street grid draws as a grid.
- When the bearings cannot all be drawn true (a loop that does not
  close), the later place moves to the nearest free cell. Every move, every
  exit drawn well off its bearing, and every place with no compass exit is
  listed in the page's report and on standard error.
- When the map declares any `entrance`, its buildings are the ones
  `location_graph.buildings()` finds: an entrance and the indoor places
  behind it, with a building whose entrance is inside another nested in
  it. A map with no entrances groups places named "Building - Room"
  instead. A building sits in the gap beside the street its entrance
  opens onto, its rooms packed into a box; a nested building's box sits
  in the nearest free gap beside its parent's, and a nested building that
  is only its entrance is framed around that entrance. A building's
  further entrances are drawn in its box. Its space is kept whether it
  is open or closed, so opening one moves nothing else. Each indoor
  place no entrance leads to is listed in the report.
- Each column and row is as wide as its longest name or largest building.
- Placement follows bearings, whatever the terrain: a forest trail is laid
  out like a street.

The page draws the computed positions with no simulation. A building
shows closed, as its entrance labelled with its name and the number of
places inside it, and opens or closes when its marker or label is
clicked. Open, it shows its rooms and each building nested in it as its
own closed marker. "Open all buildings" opens every one. Dragging a place moves it, and "Copy moved
pins" copies the moved positions as JSON. Saved to a file and passed as
`--pins FILE`, they override the computed positions on every later run.
"Download SVG" saves the current view. Like `--d3html`, the page loads D3
from `cdn.jsdelivr.net`.

`--v2svg FILE` writes the same layout as a static SVG with no browser
involved: buildings closed, or every one open with `--expanded`.

```
$ python tools/map_to_mermaid.py examples/cloak_of_darkness --v2html cloak.html --v2svg cloak.svg > /dev/null
wrote cloak.html (4 places, 0 buildings)
wrote cloak.svg
```

`tests/map_lab.py` builds the 86-place synthetic town the version 2
tests lay out.

### Showing it works

Against the demonstration game:

```
$ python tools/map_to_mermaid.py examples/cloak_of_darkness
flowchart TD
    loc_foyer["Foyer of the Opera House"]
    loc_bar["Foyer Bar"]
    loc_cloakroom["Cloakroom"]
    loc_street["The Street"]
    loc_foyer <-->|s: the bar| loc_bar
    loc_foyer <-->|w: the cloakroom| loc_cloakroom
    loc_foyer -.->|n: the street| loc_street
    linkStyle 2 stroke:#999,stroke-dasharray:4 4
```

The street is the exit that game's specification refuses: declared, and
never passable, so it draws dashed with no way back.

**The control**, which is how to show the script failing rather than
quietly drawing nothing: point it at a game with no location graph.

```
$ python tools/map_to_mermaid.py <a game with no map>
error: <that game> declares no map
```

The script reads a map through the same plugin discovery an application
uses, so a game that declares none says so, and one whose map fails to
load reports why.

A map with one of each gate:

```python
from tools.map_to_mermaid import build_diagram

MAP = {"locations": {
    "hall": {"known_by_default": True, "details": {"name": "Hall"}, "exits": [
        {"to": "yard", "position": "s", "label": "the yard"},
        {"to": "crypt", "position": "down", "label": "the crypt stair",
         "unlocked_by": "crypt_open"},
        {"to": "vault", "position": "e", "label": "the vault", "sealed": True}]},
    "yard": {"known_by_default": True, "details": {"name": "Yard"},
             "exits": [{"to": "hall", "position": "n", "label": "Hall"}]},
    "crypt": {"known_by_default": True, "details": {"name": "Old Crypt"}},
    "vault": {"known_by_default": True, "details": {"name": "Vault"}},
}}

print(build_diagram(MAP))
```

```
flowchart TD
    loc_hall["Hall"]
    loc_yard["Yard"]
    loc_crypt["Old Crypt"]
    loc_vault["Vault"]
    loc_hall <-->|s: the yard| loc_yard
    loc_hall -.->|down: the crypt stair| loc_crypt
    loc_hall -.->|e: the vault| loc_vault
    linkStyle 1,2 stroke:#999,stroke-dasharray:4 4
```

The hall and yard declare the same corridor from both ends, so it is
drawn once, as a bidirectional arrow. The vault and the crypt stair are
one-way as far as the map says, so they keep single arrowheads.

The same map, for a session that has opened the crypt, visited the yard
twice and never found the vault — continuing the same file:

```python
session = {
    "known": ["hall", "yard", "crypt"],
    "visits": {"hall": 1, "yard": 2},
    "place_records": {"crypt": {"attributes": {"crypt_open": True}}},
}

print(build_diagram(MAP, session))
```

```
flowchart TD
    loc_hall["Hall ×1"]
    loc_yard["Yard ×2"]
    loc_crypt["Old Crypt"]
    loc_hall <-->|s: the yard| loc_yard
    loc_hall -->|down: the crypt stair| loc_crypt
```

The vault is gone, the crypt stair is now a solid arrow, and the visit
counts are beside the names.
