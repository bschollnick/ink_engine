# ink_engine: plugins and `EXTERNAL` bindings

How an Ink story reaches Python in this engine: the plugins that ship with
it, how to use them from your `.ink`, and how to write your own.

- **[section 1](#1-plugins-and-the-two-ways-to-use-them)** — what the plugins are for, and the two ways to reach them
- **[section 2](#2-using-the-plugins-that-ship-with-the-engine)** — the eight plugins that ship, and how to extend one
- **[section 3](#3-creating-a-plugin)** — writing a plugin of your own
- **[Section 4](#4-testing-that-a-binding-is-really-wired) and [section 5](#5-runtime-notes-for-anyone-working-on-enginepy-itself)** — checking your wiring, and notes for anyone working on the
  engine itself
- **[section 6](#6-saving-a-game)** — saving and loading a game: save slots, labels, quicksave, and export files
- **[section 7](#7-when-something-does-not-work)** — what to look at when something does not work

Companion to [`ink_pitfalls_and_debugging.md`](ink_pitfalls_and_debugging.md),
which covers the Ink language's own sharp edges; this document is about
this engine's plugin machinery.

**About the examples.** Every Python example here runs as printed, and
every output shown was copied from running it. Claims about Ink's own
behaviour are labelled **[Ink]** and were checked against the real
`inklecate` binary (v1.2.1, compiled format `inkVersion` 21) rather than
inferred — that label means "this is upstream Ink behaviour that
`ink_engine` matches on purpose", never a divergence from it.

---

## 1. Plugins, and the two ways to use them

### 1.1 Why the engine ships plugins at all

No two games are exactly the same, but often games have common elements —
somebody is carrying something, somewhere has been visited, a quest is
half done, time has moved on, a character is better at picking locks than
talking. Not every game wants all of that, and some want none of it.
Enough games need that common functionality that writing it from scratch
each time is wasted effort.

That is what the shipped plugins are for: the recurring parts, already
built, so your development work goes into the story instead.

Ink can do a surprising amount of this on its own, with `VAR`s and LISTs,
and for a small game that is often the right answer. It gets harder as the
game grows. Tracking which of two hundred items is in which of forty
rooms — and which are held, and which are inside a chest — is a lot of
`VAR`s to keep consistent by hand, and Ink gives you no way to ask "what
is in this room?" without checking every item in turn.

Moving that into a plugin also buys three things you would otherwise
build yourself:

- **It saves and restores correctly.** Whatever a plugin remembers is
  written into the save along with the story's own progress, and comes
  back intact. Save slots, labels and export files come with the engine
  too -- see [section 6](#6-saving-a-game).
- **Your program can read it.** A sidebar, a character sheet, a map
  screen — all need to see the same state the story sees, without
  interrogating the story to get it.
- **Plugins can see each other.** Character locations are validated
  against the map's own list of places, so a typo is caught rather than
  silently stored.

### 1.2 Two ways in, one set of data

Every plugin can be reached from two directions:

- **From your story**, as an `EXTERNAL` function your `.ink` calls.
- **From your application**, as an ordinary Python method.

They are not two systems. Both read and write the same data for the same
playthrough, so a place your application marks as discovered is
immediately a place the story sees as known.

The two are not equal in size. Ink can reach **58** of the shipped
functions; Python can reach **116** — everything Ink can, and as much
again. The reason is mechanical rather than a matter of taste: Ink
handles numbers, true/false and text, so a function returning *the set of
items in a room* or *the whole quest journal* has nothing to hand back to
a story. Those exist, and they are Python-only.

One plugin is Python-only entirely. `LocationGraph` (the map) publishes no
`EXTERNAL`s at all — a story reaches a place by diverting to its knot, so
it never needs to ask.

**A rule of thumb: the story asks and decides; the application displays
and observes.** A scene asking "does the player have the key?" is Ink.
A sidebar drawing everything in the player's pack is Python. It is a
default, not a law — there are good reasons to cross it in both
directions.

### 1.3 Calling a plugin from your story

Write `EXTERNAL where_is(character)` at the top of your `.ink`, and from
then on your story can call `where_is("blacksmith")` like any other
function.

Three things can happen when the story makes that call:

- **A plugin provides it.** The function runs, and its answer goes back
  into your story — as the value of `{where_is("blacksmith")}`, or as the
  condition on a choice.
- **No plugin provides it, but your story does.** Ink lets you write an
  ordinary `=== function where_is(character) ===` alongside the
  `EXTERNAL` declaration. That version is used instead. This is worth
  doing deliberately: it lets a story stay playable on an application that
  offers none of these plugins, falling back to a simple answer of your
  own.
- **Neither provides it.** The story stops with an error naming the
  function, exactly as `inklecate` does in the same situation.

The second case is the useful one to remember. A story is not tied to the
plugins — it declares what it wants, and takes the best answer available.

### 1.4 Calling a plugin from your application

`ink_engine` is a library, not a program — it interprets a story but has
no window, no save button and no way to show a picture. The
**application** is the Python program you write around it that does those
things: the standalone player and this project's own web gallery are two,
and yours would be a third.

Every plugin hands your application the same functions the story gets,
plus the ones Ink cannot take. Calling them is ordinary Python — there is
no bridge to cross and no story to interrupt, which is why it is often
the easier of the two routes:

- **A whole answer in one call.** `held_items("player")` returns
  everything the player carries, as `{item: count}`. In Ink you would ask
  about each item by name.
- **Reading without disturbing the story.** A sidebar redraws whenever it
  likes. The story is not consulted and does not advance.
- **Writing what the application noticed.** The player clicked a map, so
  the application marks a place discovered — no scene needs to announce
  it.

Which plugins your application switches on is its own decision
([section 2.0](#20-turning-them-on)); anything left off simply falls back
to your Ink version. There is no permission system inside the engine
itself, and a game handed nothing at all still runs on its own fallbacks.

[Section 2](#2-using-the-plugins-that-ship-with-the-engine) introduces each
plugin in turn, with runnable examples of both routes.

## 2. Using the plugins that ship with the engine

Eight plugins ship with `ink_engine`, plus a ready-made answer for saving
and loading. Most games never write one: you activate the ones you need,
call their bindings from `.ink`, and give them your world's data as
config. This section is that path. [section 4](#4-testing-that-a-binding-is-really-wired) is for when you
need something nobody has written yet.

| Plugin | For | Callable from `.ink` |
|---|---|---|
| [**Cost table**](#21-costtable-what-things-cost) | what an action costs, and whether it can be afforded | `cost_of` `can_afford` `is_priced` `set_cost` |
| [**Inventory**](#22-inventorysystem-where-things-are) | where items are, and who holds them | `has_item` `item_count` `give_item_to` `take_item_from` `move_item` `drop_item_at` `destroy_item` `location_of_item` `holder_of_item` `held_item_count` `holds_nothing` `item_is_at` |
| [**Character occupancy**](#24-characteroccupancy-who-is-where) | who is at which place right now | `set_location` `where_is` `is_at` `is_with` `is_anywhere` `who_is_at` |
| [**Characters**](#25-characters-anything-you-want-to-remember-about-someone) | any fact about a character — statistics, feelings, biography, flags | `read_attribute` `set_attribute` `attribute_exists` `clear_attributes` `character_known` `set_character_known` `current_location` |
| [**Quests**](#26-quests-progress-that-outlives-a-scene) | quest stages, goals, completion and failure | `start_quest` `quest_stage` `set_quest_stage` `advance_quest` `meet_goal` `is_goal_met` `is_quest_started` `finish_quest` `fail_quest` `is_quest_failed` |
| [**Skills**](#27-skills-what-a-character-is-capable-of) | what a character can do and how well — known/unknown, a degree, or something to roll against | `skill_level` `set_skill_level` `adjust_skill_level` `knows_skill` `add_skill` `skill_check` `last_skill_roll` `last_skill_target` |
| [**Scheduling**](#28-scheduling-time-passing) | a clock, and effects timed against it | `clock` `advance_clock` `set_clock` |
| [**Location graph**](#23-locationgraph-the-places-in-your-world) | places, routes, which are known, per-place attributes | *(none — see below)* |
| [**Game saves**](#29-game-saves-save-slots-and-quicksave) | save slots, labels, quicksave, and export files | *(none — your program calls it)* |

Activate a plugin by name and those bindings arrive in your story.

**The `.ink` column is not the whole plugin.** Every one of these also has
a Python side your application calls directly. That is how a sidebar or character
sheet reads what the plugin knows, and how the application records things it
notices rather than the story announcing them — marking a place discovered
because the player walked there, say.

`LocationGraph` is the clearest case: it publishes *nothing* to Ink, and is
driven entirely from application code. Others are mostly symmetrical, with an
occasional application-only extra such as `characters_at` or `resource_of`.

Each plugin is introduced in turn below. Later, [section 3](#3-creating-a-plugin) uses three of them —
`Quests`, `Skills` and `CharacterOccupancy` — to demonstrate how to
develop a plugin from scratch.

### 2.0 Turning them on

Everything in this section starts here. Discover the shipped plugins, pick
the ones your game uses, and you get back the functions your `.ink` can
call:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins

plugins = discover_plugins(["ink_engine.engine_plugins"])

game_state = {}                       # this session's saved state
story_functions = resolve_bindings(   # what the story may call
    plugins,
    ["cost_table", "inventory", "location_graph", "character_occupancy",
     "characters", "quests", "skills", "scheduling"],
    game_state,
)

InkRuntimeState(root, list_defs, engine_bindings=story_functions)
```

Those two calls do different jobs, and the arguments are worth naming.

#### Finding plugins

**`discover_plugins(sources)`** takes a list of importable module or
package names and returns **every plugin it finds there**, as a dict keyed
by plugin name. Discovery is only *finding* — nothing is switched on yet.

The eight shipped plugins live in one package:

```python
plugins = discover_plugins(["ink_engine.engine_plugins"])

sorted(plugins)   # ['character_occupancy', 'characters', 'cost_table',
                  #  'inventory', 'location_graph', 'quests',
                  #  'scheduling', 'skills']
```

Your own plugins are found the same way — add the module or package that
holds them. A source is anything importable, so a game folder that is on
the path works exactly like the engine's own package:

```python
plugins = discover_plugins(["ink_engine.engine_plugins", "mygame.plugins"])

sorted(plugins)   # the same eight, plus 'weather'
```

A source is any importable dotted name, at whatever depth your game is
laid out — `"mygame"` if the plugin modules sit at its root,
`"mygame.plugins"` for a subpackage holding several, or
`"mygame.plugins.weather"` to name one module exactly.

Each module is scanned for a `PLUGIN` it exposes (or a `PLUGINS` list), so
a `mygame/plugins/weather.py` ending in `PLUGIN = Weather().plugin()` is
picked up with no registration step.

**Two plugins may not share a name.** A second one claiming `quests`
raises `ValueError: Duplicate plugin name 'quests'` naming the source it
came from, rather than one silently shadowing the other. To replace a
shipped plugin rather than sit beside it, give yours its own name and
activate that one instead ([section 2.9](#210-extending-a-plugin-for-your-own-game)).

#### Switching them on

**`resolve_bindings(plugins, active_names, game_state)`** is what switches
them on, and takes three things:

- **`plugins`** — what to choose from. The dict `discover_plugins`
  returned, or one you assemble by hand ([section 2.3](#23-locationgraph-the-places-in-your-world) passes
  `{"town": TOWN.plugin()}` to use its own configured map).
- **`active_names`** — **which of them this game actually uses**, by name.
  This is the opt-in list: name three of the eight and you get three
  plugins' bindings and three keys in `game_state`. A name that is not in
  `plugins` raises `KeyError` rather than being skipped, so a typo here is
  loud.
- **`game_state`** — the dict it fills in, described below.

It returns the bindings dict — the `story_functions` above.

One keyword argument is worth knowing now: **`configs=`** hands a plugin
your world's data by name, so
`resolve_bindings(..., configs={"cost_table": PRICES})` activates the
shipped cost table already holding your prices. It is not universal: a
plugin that reads its data from the instance rather than from session
state — `LocationGraph` and its edges, as [section 2.3](#23-locationgraph-the-places-in-your-world) shows — needs its own
configured instance instead.

#### Where your saved state lives

**`game_state` is yours — you create it.** It is an ordinary dict you make
and hand in; `resolve_bindings` fills it, giving each active plugin one key
of its own. After the call above:

```python
sorted(game_state)   # ['character_occupancy', 'characters', 'cost_table',
                     #  'inventory', 'location_graph', 'quests',
                     #  'scheduling', 'skills']
```

That dict is this session's entire plugin state — the thing you persist
when the player saves, and the thing you pass back in when they resume.
Every example below reads from it as `game_state["quests"]`,
`game_state["inventory"]`, and so on.

**`story_functions` is what the story may call** — a plain
`dict[str, Callable]`. Hand it to `InkRuntimeState` as `engine_bindings`
and your `.ink` can call those names as `EXTERNAL`s. Calling one from
Python, as the examples below do, is calling exactly what the story
calls.

### 2.1 `CostTable` — what things cost

**What.** A price list your story can ask about: `cost_of("lantern")`,
`can_afford("lantern", purse)`.

**Why.** To keep track of the prices or costs of things — in whatever
currency your world uses: gold pieces, mana, energy, favours, US dollars,
grotniks. One place holds what everything costs, so the shop shelf, the
haggling scene and the "you cannot afford that" line all quote the same
number.

**When.** Shop inventories, bribes, bargaining scenes, travel fares, spell
costs. Anywhere the answer to "what does this cost?" is data rather than
prose. Its **variants** feature covers the conditional case — the same item
cheaper the second time you ask, or for a charmed shopkeeper — without
that condition leaking into the price list.

**How.** Prices go in config, not in the slot, so re-pricing an item
reaches every save already in flight. It is deliberately **lookup, not
charging**: it tells you the price and whether the player can meet it, and
something else debits the purse. That split is what lets one price list
serve a shop, a dialogue check and a travel menu without any of them
knowing about the others.

**In practice.** Your price list is fixed data, shared by every session.
Only a price the story actually changes mid-game is recorded per session:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.engine_plugins.costs import CostTable

PRICES = {
    "costs": {
        "lantern":  {"resource": "coins",  "amount": 20},
        "rope":     {"resource": "coins",  "amount": 8},
        "blessing": {"resource": "favour", "amount": 1,
                     "variants": {"devout": 0}},
    }
}

SHOP = CostTable(name="shop", config=PRICES)

game_state = {}
story_functions = resolve_bindings({"shop": SHOP.plugin()}, ["shop"], game_state)

print("1", story_functions["cost_of"]("lantern"))        # coins
print("2", story_functions["is_priced"]("lantern"), story_functions["is_priced"]("moon"))
print("3", story_functions["can_afford"]("lantern", 25))  # 25 coins in hand
print("4", story_functions["can_afford"]("lantern", 5))   # only 5 coins

print("5", story_functions["cost_of"]("blessing"), story_functions["cost_of"]("blessing", "devout"))

story_functions["set_cost"]("rope", "coins", 12)
print("6", story_functions["cost_of"]("rope"))
print("7", game_state["cost_table"])
```

```
1 20
2 True False
3 True
4 False
5 1 0
6 12
7 {'costs': {'rope': {'resource': 'coins', 'amount': 12}}}
```

`can_afford` compares a price against a number you supply (3, 4) — it
never touches the player's purse, because the resource belongs to
whatever plugin owns it. **Variants** are the conditional case: the
blessing costs a favour, or nothing for the devout (5).

Look at what `game_state` holds afterwards (7): **only `rope`**, the one
price this session changed. The lantern and the blessing are not there,
because they are still exactly what `PRICES` says. That is worth knowing
before you ship an update — re-price the lantern in a new release and
every save already out there sees the new price, since no save ever
contained a copy of the old one.

From a story:

```ink
The lantern is {cost_of("lantern")} coins.
+ { can_afford("lantern", purse) } [Buy it] -> bought
+ [Leave] -> street
```

### 2.2 `InventorySystem` — where things are

**What.** Item placement and holder inventories: `has_item`,
`give_item_to`, `move_item`, `drop_item_at`, `location_of_item`, and eight
more.

**Why.** To keep track of every object in your world and where it
currently is — carried by someone, lying in a room, or gone. The player
picks things up, hands them over, drops them and loses them, and this is
what remembers the result.

**When.** Any story with objects the player picks up, gives away, loses or
finds. Also the NPC side of that: a guard *holding* a key is the same
mechanism as the player holding one.

**How.** It has **zero knowledge of what an item IS** — an item is a plain
string id you choose, and only its whereabouts are tracked. Names, prices,
descriptions and behaviour stay in your own game layer. A "holder" is any
opaque id, so the player, an NPC and a chest are the same kind of thing to
it. Pair it with `CostTable` and you have a shop.

**In practice.** 
```python
from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins

plugins = discover_plugins(["ink_engine.engine_plugins"])
game_state = {}
story_functions = resolve_bindings(plugins, ["inventory"], game_state)

story_functions["give_item_to"]("player", "brass_key")
story_functions["give_item_to"]("player", "coin", 5)      # 5 of them
story_functions["drop_item_at"]("lantern", "crypt")

print("1", story_functions["has_item"]("player", "brass_key"))
print("2", story_functions["item_count"]("player", "coin"))
print("3", story_functions["holder_of_item"]("brass_key"))
print("4", story_functions["location_of_item"]("lantern"))
print("5", story_functions["item_is_at"]("lantern", "crypt"))

story_functions["move_item"]("player", "guard", "brass_key")
print("6", story_functions["has_item"]("player", "brass_key"))
print("7", story_functions["has_item"]("guard", "brass_key"))
print("8", story_functions["holds_nothing"]("guard"))

story_functions["destroy_item"]("lantern")
print("9", story_functions["location_of_item"]("lantern"))
print("10", game_state["inventory"])
```

```
1 True
2 5
3 player
4 crypt
5 True
6 False
7 True
8 False
9 
10 {'item_locations': {}, 'holder_items': {'player': {'coin': 5}, 'guard': {'brass_key': 1}}, ...}
```

An item is either held or lying somewhere, never both: the key moves
from the player to the guard in one call (6, 7), and a destroyed item
has no location at all (9). Counts are per holder, so five coins are
one entry (2).

From a story:

```ink
{ has_item("player", "lantern"): The lantern throws a long shadow. }
+ [Hand the key to the guard] -> give
= give
~ move_item("player", "guard", "brass_key")
The guard pockets it.
```

### 2.3 `LocationGraph` — the places in your world

**What.** Places, the routes between them, which the player has
discovered, and per-place attributes.

**Why.** To keep track of the places in your world, how they connect, and
which ones the player has found. It answers "where can I go from here?"
— the list a travel menu is built from.

**When.** Town maps, dungeons, travel menus. Works equally for a static
map, where every place is known from the start, and a growing one, where
places are revealed as the player hears about them.

#### From a drawn map to a config

Say your world is a 5×4 grid, and eight of its cells are places:

```
        0        1        2        3        4
    +--------+--------+--------+--------+--------+
  0 |  INN -----SQUARE----MARKET|        |        |
    |        |    |   |     |   |        |        |
  1 |        |  WELL  |   ROAD -----FARM |        |
    |        |        |     |   |        |        |
  2 |        |        |  CRYPT  |        |        |
    |        |        |     |   |        |        |
  3 |        |        |  TOMB   |        |        |
    +--------+--------+--------+--------+--------+
```

Reading the lines: the **inn**, **square** and **market** sit in a row,
each joined to its neighbour. The **well** hangs below the square. The
**road** runs south from the market to the **farm** in the east and the
**crypt** in the south, and the **tomb** lies below the crypt.

So from the road you can reach the market, the farm and the crypt — but
not the square or the well, which are only reachable back through the
market. That is the point of an explicit graph: adjacency on the page is
not connection.

The crypt is on the map but the player does not know it is there until
someone tells them, and the tomb is deeper still.

**The grid itself never reaches the plugin.** Coordinates are a drawing
aid; what matters is which places connect to which. That becomes:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.engine_plugins.location_graph import LocationGraph

TOWN_MAP = {
    "locations": {
        "inn":    {"known_by_default": True,  "details": {"name": "The Inn"},
                   "edges": [{"to": "square"}]},
        "square": {"known_by_default": True,  "details": {"name": "Town Square"},
                   "edges": [{"to": "inn"}, {"to": "market"}, {"to": "well"}]},
        "well":   {"known_by_default": True,  "details": {"name": "The Well"},
                   "edges": [{"to": "square"}]},
        "market": {"known_by_default": True,  "details": {"name": "Market"},
                   "edges": [{"to": "square"}, {"to": "road"}]},
        "road":   {"known_by_default": True,  "details": {"name": "South Road"},
                   "edges": [{"to": "market"}, {"to": "farm"},
                             {"to": "crypt", "requires_known": True}]},
        "farm":   {"known_by_default": True,  "details": {"name": "Hillside Farm"},
                   "edges": [{"to": "road"}]},
        "crypt":  {"known_by_default": False, "details": {"name": "Old Crypt"},
                   "edges": [{"to": "road"},
                             {"to": "tomb", "requires_known": True}]},
        "tomb":   {"known_by_default": False, "details": {"name": "Sealed Tomb"},
                   "edges": [{"to": "crypt"}]},
    }
}

TOWN = LocationGraph(name="town", config=TOWN_MAP)

game_state = {}
story_functions = resolve_bindings({"town": TOWN.plugin()}, ["town"], game_state)
```

**A map belongs to its own instance.** Edges are read from the instance's
config, not from session state, so a game builds its own `LocationGraph`
with its map rather than using the shipped one — which, having no map,
would report every place as having nowhere to go.

Note what is *absent*: `road` lists no edge to `square` or `well`. Nothing
infers a route from two places being near each other on the page — if you
do not write the edge, it does not exist.

Four things that config decides:

- **Edges are one-way as written.** `square` lists `inn`, and `inn` lists
  `square` back — that pair is what makes it walkable both ways. Omit one
  side and you have a drop, deliberate or otherwise.
- **`known_by_default`** puts a place on the player's map at the start.
  The crypt's `False` is why it is absent until something reveals it.
- **`requires_known`** gates the *edge*, not the place: standing on the
  road, the crypt turning is only offered once the crypt is known.
  Ordinary edges omit it, because walking somewhere is usually how it
  becomes known.
- **`details`** is free-form per place — a display name here, but equally
  terrain, an icon, or an id from whatever the map was drawn in.

#### What it looks like at runtime

`game_state["location_graph"]` is this session's own map state — the part
that changes as one player explores, kept apart from `TOWN_MAP` above,
which every session shares. Continuing the same file:

```python
the_map = game_state["location_graph"]

print("1", sorted(the_map["declared"]))
print("2", sorted(the_map["known"]))

print("3", TOWN.reachable_edges(the_map, "square"))
print("4", TOWN.reachable_edges(the_map, "road"))

TOWN.set_known(the_map, "crypt", True)
print("5", TOWN.reachable_edges(the_map, "road"))
print("6", TOWN.detail(the_map, "crypt", "name"))
```

```
1 ['crypt', 'farm', 'inn', 'market', 'road', 'square', 'tomb', 'well']
2 ['farm', 'inn', 'market', 'road', 'square', 'well']
3 ['inn', 'market', 'well']
4 ['market', 'farm']
5 ['market', 'farm', 'crypt']
6 Old Crypt
```

The crypt is declared from the start but not known, so the road offers no
turning toward it until `set_known` is called.

`reachable_edges` is the travel menu: hand it where the player is standing
and it returns where they may go, with the gated turning appearing only
after discovery.

**Who is standing where is not this plugin's job.** The map knows places
and routes; it never knows that the blacksmith is at the inn.
`CharacterOccupancy` ([section 2.4](#24-characteroccupancy-who-is-where)) tracks that, and it builds directly on this
data — every character's location is one of the place ids declared here,
and placing someone anywhere else is refused. Draw the map first; [section 2.4](#24-characteroccupancy-who-is-where) has
the examples.

**How it fits with everything else.** It is deliberately
**occupancy-free** — it knows places and edges, never who is standing
where, so `CharacterOccupancy` ([section 2.4](#24-characteroccupancy-who-is-where)) layers on top without the map
knowing characters exist.

**Discovery is written, just not from Ink.** `set_known`, `set_all_known`,
`record_visit` and `set_attribute` all change the slot; this plugin is not
read-only. What it publishes to *Ink* is nothing. A story reaches a place
by diverting to its knot, and your application marks it known — which is why this
plugin needs no `EXTERNAL` surface at all.

### 2.4 `CharacterOccupancy` — who is where

**What.** The current place of every character: `set_location`,
`where_is`, `is_at`, `is_with`, `is_anywhere`, `who_is_at`.

**Why.** To keep track of people and where they are in the world — the
player included. It answers "who is here?" and "where is she?", so a scene
can turn on who happens to be in the room.

**When.** Any story where NPCs are somewhere in particular — a blacksmith
who is at the forge in the morning and the tavern at night, a rival who
follows you, a guard you need to get past.

**How.** It **depends on `LocationGraph`, and enforces it**: placing
someone at a place the map never declared raises `UnknownLocationError`
rather than storing a typo that quietly never matches again. The
dependency runs one way only — the map knows nothing about characters.
`is_with("guard", "captain")` answers "are these two in the same place"
without either of them naming it.

**In practice.** Occupancy needs a map to validate against, so both
plugins are activated together:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.engine_plugins.character_occupancy import (
    CHARACTER_OCCUPANCY, CharacterOccupancy)
from ink_engine.engine_plugins.location_graph import LocationGraph

TOWN_MAP = {"locations": {
    "inn":    {"known_by_default": True, "edges": [{"to": "square"}]},
    "square": {"known_by_default": True, "edges": [{"to": "inn"}, {"to": "market"}]},
    "market": {"known_by_default": True, "edges": [{"to": "square"}]},
    "farm":   {"known_by_default": True, "edges": []},
}}

TOWN = LocationGraph(name="town", config=TOWN_MAP)

game_state = {}
story_functions = resolve_bindings(
    {"town": TOWN.plugin(), "character_occupancy": CharacterOccupancy().plugin()},
    ["town", "character_occupancy"],
    game_state,
)

print("1", game_state["character_occupancy"]["locations"])

story_functions["set_location"]("player", "square")
story_functions["set_location"]("blacksmith", "inn")
story_functions["set_location"]("farmer", "farm")
print("2", game_state["character_occupancy"]["locations"])

print("3", story_functions["where_is"]("player"))
print("4", story_functions["is_at"]("blacksmith", "inn"))
print("5", story_functions["is_with"]("player", "blacksmith"))
print("6", story_functions["who_is_at"]("inn"))

story_functions["set_location"]("player", "inn")          # the player walks
print("7", story_functions["is_with"]("player", "blacksmith"))
print("8", story_functions["who_is_at"]("inn"))
print("9", repr(story_functions["who_is_at"]("square")))

print("10", repr(story_functions["where_is"]("ghost")))
print("11", CHARACTER_OCCUPANCY.characters_at(game_state["character_occupancy"], "inn"))
```

```
1 {}
2 {'player': 'square', 'blacksmith': 'inn', 'farmer': 'farm'}
3 square
4 True
5 False
6 blacksmith
7 True
8 player,blacksmith
9 ''
10 ''
11 ['player', 'blacksmith']
```

A character is any id string you choose — the plugin never needs to be
told they exist first (2). One write moves someone, and every answer
follows from it: after the player walks to the inn, `is_with` flips to
True (7) and the inn holds two people (8) while the square empties (9).

In a story that reads as:

```ink
{ is_at("player", "market"): Stalls crowd the square's edge. }
{ where_is("blacksmith") == "inn": He is drinking again. }
+ { is_with("player", "blacksmith") } [Ask about the crypt] -> ask
```

Three behaviours worth knowing before you hit them:

- **`where_is` answers `""`** for a character never placed (10) — asking
  about someone unknown is not an error, so a scene can ask before the
  story has placed them.
- **`who_is_at` returns one comma-joined string**, because Ink has no
  list type. Application code wanting a real list calls
  `CHARACTER_OCCUPANCY.characters_at(...)` instead (11).
- **A place the map never declared raises.**
  `story_functions["set_location"]("player", "merket")` fails with
  `UnknownLocationError` rather than stranding the player somewhere no
  check will ever match. This is the `LocationGraph` dependency doing its
  job: the map is the vocabulary, and occupancy is held to it.

### 2.5 `Characters` — anything you want to remember about someone

**What.** An **attribute** is one named fact about one character. The
plugin does not care what it means, so it can be:

- a **statistic** — `strength` 14, `charisma` 9, `hit_points` 22
- a **state of mind** — `suspicion` 3, `loves` `"marguerite"`,
  `angry_at_player` `true`
- a **fact of biography** — `lives_at` `"the mill"`, `surname`
  `"Tanner"`, `is_a_widow` `true`
- a **story flag** — `has_seen_the_letter` `true`, `owes_player` 40,
  `goal` `"reach the coast"`

A value is a number, a true/false, or a string, so "how much" and "which
one" and "has this happened" are all storable. Read one with
`read_attribute`, write it with `set_attribute`, ask whether it was ever
set with `attribute_exists`, and wipe a character's record with
`clear_attributes`. `character_known` / `set_character_known` sit
alongside for whether the player has met them at all.

**Attributes are the general case; skills ([section 2.7](#27-skills-what-a-character-is-capable-of)) are a specialised one.**
A skill is an attribute that happens to be a number on a declared range,
with known/unknown and rolling built on top. If all you need is to
remember that the blacksmith's `temper` is 7, this is the plugin — reach
for `Skills` when you want a numeric value on a declared range, or for
that value to be rolled against as a test.

**Why.** To keep track of attributes, statistics and any other information
about your characters — the player included. Anything the story wants to
remember about a person and read back later.

**When.** Whenever a fact about someone outlives the scene that
established it: a debt incurred in chapter one and called in at the end, a
temper that rises across three conversations, a character sheet the player
can open.

**How.** The plugin has no opinion about what an attribute *means* — only
that it is a named value belonging to someone. An undeclared attribute
answers with the default rather than raising, so a story can ask before
anything has set it. `character_known` is separate because "have we met?"
would otherwise be everyone's first attribute, asked constantly.

Attributes are a *pattern*, not this plugin's private trick:
`LocationGraph` publishes its own `read_attribute` for the per-place
equivalent — whether a door was opened, whether a shelf was read.

**In practice.** 
```python
from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins

plugins = discover_plugins(["ink_engine.engine_plugins"])
game_state = {}
story_functions = resolve_bindings(plugins, ["characters"], game_state)

print("1", story_functions["character_known"]("smith"))
story_functions["set_character_known"]("smith", True)
print("2", story_functions["character_known"]("smith"))

story_functions["set_attribute"]("smith", "trust", 3)
print("3", story_functions["read_attribute"]("smith", "trust", 0))
print("4", story_functions["read_attribute"]("smith", "debt", 0))
print("5", story_functions["attribute_exists"]("smith", "debt"))
print("6", game_state["characters"])
```

```
1 False
2 True
3 3
4 0
5 False
6 {'records': {'smith': {'attributes': {'trust': 3}}}, 'known': ['smith']}
```

Note `read_attribute` takes the default as its last argument (4), which
is why asking about something never set is safe. In a story:

```ink
{ character_known("smith"): The blacksmith nods at you. }
{ read_attribute("smith", "trust", 0) >= 3: He lowers his voice. }
+ { not character_known("smith") } [Introduce yourself] -> meet_smith
```

### 2.6 `Quests` — progress that outlives a scene

**What.** Quest *stages* (`quest_stage`, `set_quest_stage`,
`advance_quest`), discrete *goals* hanging off them (`meet_goal`,
`is_goal_met`), and failure (`fail_quest`, `is_quest_failed`).

**Why.** To keep track of quests, tasks, or anything that is ongoing or
done. A scene written weeks after the one that started it can ask how far
along the player is, what they have finished, and what they have failed.

**When.** Any thread that spans scenes — a rescue, an investigation, a
favour someone asked for two chapters ago.

**How.** A stage is an int compared against thresholds your game defines,
so `{ quest_stage("rescue") >= 3 }` gates content without the plugin
knowing what 3 means. Whole numbers are the intent — leave room between
them (10, 20, 30) if you expect to add steps later, rather than reaching
for 2.5. Goals are the checklist case: several
objectives under one quest, each met or outstanding, none carrying a stage
of its own. The quest *catalog* is config; only progress lives in the
slot.

**In practice.** A quest's *catalog* — which quests exist and what
finishing each one means — is data you hand the plugin. Progress is what
the session records:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.engine_plugins.quests import QuestSpec, Quests

CATALOG = {
    # Finished once the player reaches stage 30 AND meets both goals.
    "rescue": QuestSpec(
        quest_id="rescue",
        final_stage=30,
        goal_ids=("found_key", "opened_cell"),
    ),
}

QUESTS = Quests(catalog=CATALOG)

game_state = {}
story_functions = resolve_bindings({"quests": QUESTS.plugin()}, ["quests"], game_state)

print("1", story_functions["quest_stage"]("rescue"))       # 0 = never started
story_functions["start_quest"]("rescue")
print("2", story_functions["is_quest_started"]("rescue"))
print("3", story_functions["quest_stage"]("rescue"))

story_functions["meet_goal"]("rescue", "found_key")
print("4", story_functions["is_goal_met"]("rescue", "found_key"))
print("5", story_functions["is_goal_met"]("rescue", "opened_cell"))

story_functions["advance_quest"]("rescue", 30)             # its final stage
print("6", QUESTS.is_complete(game_state["quests"], "rescue"))   # a goal outstanding

print("7", story_functions["finish_quest"]("rescue"))     # meets what remains
print("8", QUESTS.is_complete(game_state["quests"], "rescue"))

story_functions["fail_quest"]("bandits")
print("9", story_functions["is_quest_failed"]("bandits"))
print("10", game_state["quests"])
```

```
1 0
2 True
3 1
4 True
5 False
6 False
7 True
8 True
9 True
10 {'stages': {'rescue': 30}, 'met_goals': {'rescue': ['found_key', 'opened_cell']}, 'failed': ['bandits']}
```

**Don't hand-roll "finished".** Look at (6): the quest has reached its
`final_stage` of 30 and is still **not** complete, because `opened_cell`
is outstanding. Getting that right by hand means every scene knowing both
the magic number and the full goal list.

`finish_quest` (7) does it from the catalog instead — meeting every
declared goal and setting the stage to `final_stage`, whatever they are —
and returns whether the quest now reports complete. A quest declaring
`requires` is checked recursively, so a questline completes only once its
subquests have; finish those first, and the parent follows.

Define what "finished" means once, in the catalog. Then one call ends a
quest and one question asks whether it ended, with no scene re-deciding
which number counts.

**`is_complete` is application-side only** — it is not published to Ink, because
answering it needs the catalog rather than session state. A story asks
the parts it can see: `quest_stage`, `is_goal_met`, `is_quest_failed`. A
game that wants a single "is it done" test in `.ink` publishes one from a
subclass ([section 2.9](#210-extending-a-plugin-for-your-own-game)).

In a story:

```ink
{ quest_stage("rescue") >= 30: The cell door is already open. }
+ { is_goal_met("rescue", "found_key") } [Unlock it] -> unlock
+ { not is_quest_started("rescue") } [Ask about the prisoner] -> begin
```

### 2.7 `Skills` — what a character is capable of

**What.** A number per character per skill — read it, set it, move it
(`skill_level`, `set_skill_level`, `adjust_skill_level`); ask whether they
have the skill at all (`knows_skill`, `add_skill`); or roll against it
(`skill_check`, `last_skill_roll`, `last_skill_target`).

**Why.** To keep track of what your characters can do and how well —
whether a skill is known at all, and how good they are at it. The same
number gates a choice, fills in a character sheet, and goes up when they
learn or train.

**When.** Lockpicking, persuasion, spell-casting — and equally, a spell
the player has simply learned or not.

**How.** One number per character per skill, on whatever range your game
declares (1-6, 1-20, 1-100). What it *means* is your choice, and the
plugin supports three readings of the same stored value:

- **Known or not.** `knows_skill` is any level above zero, and
  `add_skill` grants one — returning `False` and **leaving an existing
  level alone**, so a re-entered scene cannot reset hard-won progress. No
  roll involved.
- **A degree of capability.** Read `skill_level` and compare it yourself:
  gate a choice at 40, give the expert a different description at 80, let
  training move the number with `adjust_skill_level`.
- **Something to roll against.** `skill_check` succeeds when a 1-100 roll
  lands at or below the level plus any bonus; checks normalise internally
  to a percentile, so your display range never touches the roll maths.
  Afterwards `last_skill_roll` / `last_skill_target` let the story narrate
  the near-miss rather than just reporting failure.

**In practice.** Levels first, then the two things built on them:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins

plugins = discover_plugins(["ink_engine.engine_plugins"])
game_state = {}
story_functions = resolve_bindings(plugins, ["skills"], game_state)
game_state["skills"]["rng_seed"] = 7          # pin the rolls for this example

print("1", story_functions["skill_level"]("player", "lockpicking", 0))
story_functions["set_skill_level"]("player", "lockpicking", 40)   # on a 0-100 range
print("2", story_functions["adjust_skill_level"]("player", "lockpicking", 15))

print("3", story_functions["knows_skill"]("player", "firestarting"))
print("4", story_functions["add_skill"]("player", "firestarting", 1))
print("5", story_functions["knows_skill"]("player", "firestarting"))
print("6", story_functions["add_skill"]("player", "firestarting", 1))

print("7", story_functions["skill_check"](55, 100, 0))    # level 55, max 100, no bonus
print("8", story_functions["last_skill_roll"]())
print("9", story_functions["last_skill_target"]())
```

```
1 0
2 55
3 False
4 True
5 True
6 False
7 True
8 42
9 55
```

`add_skill` returns False for a skill already known (6) and leaves the
existing level alone, so a re-entered scene cannot reset progress.

`skill_check` takes the level itself, not a character and skill name, so
the caller decides where the number came from — a skill, a skill plus a
situational bonus, or a flat difficulty. In a story:

```ink
{ knows_skill("player", "firestarting"): You could light this. }
+ { skill_check(skill_level("player", "lockpicking", 0), 100, 0) } [Pick the lock] -> opened
- The lock holds. You were {last_skill_roll()} against {last_skill_target()}.
```

### 2.8 `Scheduling` — time passing

**What.** A clock, the calendar questions you ask about it, and effects
queued against it.

- **The clock** — `clock` reads it, `advance_clock` moves it forward,
  `set_clock` jumps to a given time.
- **Time of day** — `hour_of_day`, and the phase tests `is_morning`,
  `is_afternoon`, `is_evening`, `is_night`, `is_day`.
- **The calendar** — `day_of_week` (0 = Monday), `is_weekday`.

**Why.** To keep track of the time in your world, and what should happen
when it reaches a certain point. Shops shut, ships sail, people go home —
so what the player chooses to do first starts to matter.

**When.** Shops closing, night falling, someone leaving before you get
back, a deadline the player can miss. Also the quieter uses: a greeting
that changes with the hour, a market that only runs on weekdays.

**How.** **The unit is minutes**, not an arbitrary tick — the clock counts
minutes since the story began, so `1440` is one day and `8 * 60` is 08:00
on day zero. The phase tests are pure functions of a clock value, which is
why you pass them one rather than them reading it themselves.

Day phases divide the 24 hours between them, with no gaps:

| Phase | From | Until |
|---|---|---|
| `is_morning` | 06:00 | 12:00 |
| `is_afternoon` | 12:00 | 17:00 |
| `is_evening` | 17:00 | 21:00 |
| `is_night` | 21:00 | 06:00 |

`is_day` is true for morning, afternoon and evening together — the
daylight hours as one test.

**In practice.** 
```python
from ink_engine.binding import resolve_bindings
from ink_engine.discovery import discover_plugins

plugins = discover_plugins(["ink_engine.engine_plugins"])
game_state = {}
story_functions = resolve_bindings(plugins, ["scheduling"], game_state)

print("1", story_functions["clock"]())                  # minutes since the story began
print("2", story_functions["advance_clock"](30))        # 30 minutes later
print("3", story_functions["set_clock"](8 * 60))        # jump to 08:00 on day 0

print("4", story_functions["hour_of_day"](story_functions["clock"]()))
print("5", story_functions["is_morning"](story_functions["clock"]()))
print("6", story_functions["is_day"](story_functions["clock"]()))

story_functions["set_clock"](21 * 60)                   # 21:00
print("7", story_functions["is_evening"](story_functions["clock"]()))
print("8", story_functions["is_night"](story_functions["clock"]()))

story_functions["set_clock"](3 * 1440 + 10 * 60)        # day 3, 10:00
print("9", story_functions["day_of_week"](story_functions["clock"]()))
print("10", story_functions["is_weekday"](story_functions["clock"]()))
```

```
1 0
2 30
3 480
4 8
5 True
6 True
7 False
8 True
9 3
10 True
```

Note 21:00 is already night rather than evening (7, 8) — the phases are
contiguous, so a boundary hour belongs to exactly one of them. Day 3 of a
story starting on a Monday is a Thursday (9), still a weekday (10).

In a story:

```ink
{ is_night(clock()): The market is shuttered for the night. }
{ is_morning(clock()): Stallholders are still setting out their trays. }
+ { is_weekday(clock()) } [Visit the courthouse] -> courthouse
+ [Wait an hour] -> waited
= waited
~ advance_clock(60)
An hour passes.
```

### 2.9 Game saves — save slots and quicksave

Batteries included: save slots, labels, quicksave and export files come
with the engine, ready to use and replaceable where you need something
different. It is not a plugin in the sense the rest of this section uses
— nothing to discover, nothing to pass to `resolve_bindings()` — so it
is listed here to make sure you find it.
[Section 6](#6-saving-a-game) has the full set — a save menu, exporting
and importing, quicksave — and how to customize it.

Saving is done by your program, so your story never calls this one. Give
it a folder to write to:

```python
from pathlib import Path
from if_session import GameSavesDirectory, save_game, load_game_save

game_saves_directory = GameSavesDirectory(Path("saves"))
save_game("thehauntedhouse", 0, state, "Before the bridge",
          saves_in=game_saves_directory, maximum_gamesave_slots=5, saved_at=when)
```

The save covers the whole game world and everything in it: the story's
own progress, and every plugin's state along with it.

### 2.10 Extending a plugin for your own game

#### Config versus session state

**Your world's data belongs to the plugin; only what a session changed
belongs to that session.** A price list, a map's edges, a quest catalog —
these are the world as you authored it, held on the plugin and read live.
What one playthrough did to that world — a price it altered, a place it
discovered — is what `game_state` records, as [section 2.1](#21-costtable-what-things-cost) showed.

That split is what lets a new version of a game reach an existing save.
Re-price a spell or add a map edge, and every save in flight sees the
change, because no save ever contained a copy of the old value.

**A game extends a shipped plugin by instantiating it with config, or by
subclassing it — and then activates the result, not both.**

The simple case is config: the same plugin, holding your data.

```python
GAME_COSTS = CostTable(name="game_costs", config=MY_PRICES)
```

#### Bounty hunting: extending Quests with money

Subclassing is for when you want the plugin to do something it does not
already do. Say quests should pay a bounty — the engine has no notion of
payment, but everything else about quests is already right. Add a field
for what each job pays, and three bindings that use it:

```python
from ink_engine.binding import resolve_bindings
from ink_engine.engine_plugins.quests import QuestSpec, Quests, QuestSlot
from ink_engine.plugin_base import external, query


class BountySlot(QuestSlot):
    """The engine's quest state, plus what this game pays for a job."""
    rewards: dict[str, int]


class BountyQuests(Quests):
    name = "bounty_quests"
    display_name = "Quests with bounties"
    slot_type = BountySlot
    fields = {**Quests.fields, "rewards": dict}

    @external
    def offer_bounty(self, slot: BountySlot, quest_id: str, coins: int) -> None:
        """Promise a payment for finishing this quest."""
        slot.setdefault("rewards", {})[quest_id] = coins

    @query
    @external
    def bounty_for(self, slot: BountySlot, quest_id: str) -> int:
        """Return what finishing this quest pays, 0 if nothing was offered."""
        return slot.get("rewards", {}).get(quest_id, 0)

    @query
    @external
    def bounty_owed(self, slot: BountySlot) -> int:
        """Return the total promised for quests the player has finished."""
        return sum(
            coins
            for quest_id, coins in slot.get("rewards", {}).items()
            if self.is_complete(slot, quest_id)
        )


CATALOG = {
    "rescue":  QuestSpec(quest_id="rescue", final_stage=30),
    "bandits": QuestSpec(quest_id="bandits", final_stage=10),
}

BOUNTY_QUESTS = BountyQuests(name="bounty_quests", catalog=CATALOG)

game_state = {}
story_functions = resolve_bindings(
    {"bounty_quests": BOUNTY_QUESTS.plugin()}, ["bounty_quests"], game_state
)

print("1", sorted(story_functions))

story_functions["offer_bounty"]("rescue", 50)
story_functions["offer_bounty"]("bandits", 20)
print("2", story_functions["bounty_for"]("rescue"))
print("3", story_functions["bounty_for"]("errand"))

story_functions["start_quest"]("rescue")
print("4", story_functions["bounty_owed"]())      # started, not finished

story_functions["finish_quest"]("rescue")
print("5", story_functions["bounty_owed"]())
print("6", sorted(game_state))
print("7", game_state["quests"])
```

```
1 ['advance_quest', 'bounty_for', 'bounty_owed', 'fail_quest', 'finish_quest', 'is_goal_met', 'is_quest_failed', 'is_quest_started', 'meet_goal', 'offer_bounty', 'quest_stage', 'set_quest_stage', 'start_quest']
2 50
3 0
4 0
5 50
6 ['quests']
7 {'stages': {'rescue': 30}, 'met_goals': {}, 'failed': [], 'rewards': {'rescue': 50, 'bandits': 20}}
```

**Four things that example shows:**

- **You get everything the base plugin published, plus your own** (1) —
  ten inherited quest bindings alongside `offer_bounty`, `bounty_for`
  and `bounty_owed`. Your story calls them all the same way.
- **`fields` extends rather than replaces.** `{**Quests.fields,
  "rewards": dict}` keeps the engine's three and adds one, so a single
  slot holds both (7). Writing `{"rewards": dict}` alone would drop the
  quest state the base class needs, and `slot_type` must gain the field
  too — the two are checked against each other at construction.
- **Your methods may call the ones you inherited.** `bounty_owed` asks
  `self.is_complete(...)` which bounties are payable (4, 5) rather than
  comparing stage numbers itself — so "finished" keeps meaning whatever
  the quest's own `final_stage`, goals and subquests say it means.
- **`state_key` is inherited, not renamed.** Despite `name =
  "bounty_quests"`, the state lands under `quests` (6) — which is the
  point: a save written before the bounty feature existed still loads,
  and simply has no `rewards` yet.

That last point is also the one real hazard. A subclass shares its parent's
`state_key`, so **activating both the base plugin and a subclass of it is
a conflict** — two plugins claiming one slot. Activate one. [section 3.6](#36-two-phase-resolution-allocate-then-bind) describes
what the resolver does when you get it wrong.

A subclass republishes inherited bindings under the engine's names and
adds its own under whatever convention the game uses. So a game whose own
bindings carry a suffix keeps that suffix on them while the engine
publishes unsuffixed ones: a game's vocabulary is the game's to set, and
the engine's naming standard binds only what the engine itself publishes.

## 3. Creating a plugin

A plugin gives your story a set of functions, and usually somewhere of its
own to remember things between calls.

**This section builds three of the shipped plugins from scratch —
`Quests`, `Skills` and `CharacterOccupancy` — to demonstrate how to write
one.** Each covers ground the others do not:

- **[section 3.1](#31-a-first-plugin-line-by-line-quests) `Quests`** — a whole plugin, line by line, and what every part of
  it is for.
- **[section 3.2](#32-keeping-state-a-binding-needs-skills) `Skills`** — what a plugin should keep in its own store, and how
  that survives a save.
- **[section 3.3](#33-depending-on-another-plugin-characteroccupancy) `CharacterOccupancy`** — building on another plugin without
  tying the two together.

Sections [3.4](#34-reading-another-plugins-state-and-needs_context), [3.5](#35-the-flat-plugin-contract-and-stateless-plugins) and [3.6](#36-two-phase-resolution-allocate-then-bind) cover the machinery underneath: reading another plugin's data,
plugins that need no storage at all, and how the engine switches
everything on.

### 3.1 A first plugin, line by line: `Quests`

Start here: everything later builds on this.

#### The Quests plugin in full

```python
class QuestSlot(TypedDict):
    stages: dict[str, int]
    met_goals: dict[str, list[str]]
    failed: list[str]


class Quests(StatefulPlugin[QuestSlot]):
    name = "quests"
    display_name = "Quests"
    state_key = "quests"
    slot_type = QuestSlot
    fields = {"stages": dict, "met_goals": dict, "failed": list}

    @external
    def start_quest(self, slot: QuestSlot, quest_id: str, stage: int = 1) -> None:
        """Begin a quest, or reset it to a starting stage."""
        slot.setdefault("stages", {})[quest_id] = stage

    @query
    @external
    def quest_stage(self, slot: QuestSlot, quest_id: str) -> int:
        """Return the quest's current stage, 0 if never started."""
        return slot.get("stages", {}).get(quest_id, 0)


QUESTS = Quests()
PLUGIN = QUESTS.plugin()
```

Those last two lines are what makes the plugin findable: `discover_plugins`
([section 2.0](#20-turning-them-on)) scans a module for a `PLUGIN` and picks up whatever it finds. The
rest of this section works through the parts above them.

#### Why a *stateful* plugin

A plugin gives your story functions it can call — the ones you declare at
the top of your `.ink` with `EXTERNAL start_quest(quest_id)`. Ink hands
over the arguments, gets an answer back, and that is the whole
conversation.

Which is fine for a function that only needs its arguments: "what is 3 +
4". It is not enough for quests. `quest_stage("rescue")` has to know what
happened in a scene the player read an hour ago, and `start_quest` has to
leave something behind for it to find.

So the plugin needs somewhere to **remember**, and that somewhere has to
belong to *one playthrough*. Two people playing your game at once must not
share a quest log, and a player who saves and returns tomorrow must find
theirs as they left it.

`StatefulPlugin` is what provides that. It hands every method a **slot** —
one dict, private to this plugin, belonging to this playthrough, saved and
restored along with the story. Subclass it when your plugin must remember
something; use the flat `Plugin` ([section 3.5](#35-the-flat-plugin-contract-and-stateless-plugins)) when it need not.

#### What `QuestSlot` is, and why it appears twice

`QuestSlot` is the list of things this plugin remembers, written down:
quest stages, met goals, failed quests. Nothing else. It is a `TypedDict`,
which is an ordinary Python dict that also names the keys it is allowed to
have — so it behaves exactly like `{"stages": {...}}` while letting your
editor and the engine both know what belongs in it.

It appears in two places, doing two jobs:

- **`StatefulPlugin[QuestSlot]`** — the square brackets tell your editor
  what the `slot` argument holds, so it can autocomplete `slot["stages"]`
  and flag a typo before you ever run the game.
- **`slot_type = QuestSlot`** — the same claim, made to the engine, which
  checks it against `fields` and refuses to build the plugin if the two
  disagree.

Saying it twice is the point: your editor and the engine are then working
from the same description, and neither can quietly fall out of step with
the other.

#### The five class attributes

| Attribute | What it is |
|---|---|
| `name` | The plugin's unique name — what an application puts in `active_names` to switch it on. Two plugins may not share one. |
| `display_name` | A human label, for a application's own settings UI or error messages. Never seen by a story, but not optional — omitting it fails when the plugin is built. |
| `state_key` | Which key of `game_state` this plugin's slot lives under. Usually the same as `name`, but not always — a subclass keeps its parent's, which is how a save survives being renamed ([section 2.9](#210-extending-a-plugin-for-your-own-game)). |
| `slot_type` | The `TypedDict` above. |
| `fields` | `{field_name: empty_value_factory}` for every key of `slot_type` — `dict` and `list` here, the *callables*, not `{}` and `[]`. |

`fields` earns a closer look, because it does more than it appears to.
`init_state()` builds a fresh slot from it, and `bind()` **re-applies it
with `setdefault` on every load**. That second part is what lets you add a
field later: a save written before `failed` existed still loads, and
simply gains an empty `failed` list. Had the factories been shared
instances (`{}` rather than `dict`), every session would mutate the same
object.

#### `@external` and `@query`

Neither decorator changes what the method does. Each answers a different
question about who is allowed to call it.

**`@external` is the Python side of Ink's `EXTERNAL`.** It makes the
method callable from your story. Declare `EXTERNAL start_quest(quest_id)`
at the top of your `.ink`, mark the Python method `@external`, and the two
are joined — the method name *is* the Ink name, so there is no second
place to keep in sync.

Two rules it enforces, because Ink is stricter than Python about return
values:

- **You must say what the method returns.** Leaving the `-> bool` or
  `-> None` off raises an error the moment the plugin is built, rather
  than when a story eventually calls it.
- **`-> None` is a real answer, not the absence of one.** Ink has no
  concept of a function that returns nothing, so a method declared
  `-> None` is published as returning a placeholder value instead. That is
  what lets `~ start_quest("rescue")` work as a statement in a story.

**`@query` has nothing to do with Ink.** It publishes the method to the
*application* — the program running your game — so a sidebar, character sheet or
debug panel can ask the same questions your story asks. `quest_stage`
carries both decorators, so the story and the sidebar share one
implementation rather than two that can disagree.

Queries are for reading only. Every one the shipped plugins publish
answers a question; none of them changes anything. `finish_quest` is
`@external` but deliberately not `@query`, because a sidebar has no
business completing a quest behind the story's back.

A method with neither decorator is internal — your other methods can call
it, and neither the story nor the application can see it.

#### Why every method takes `slot` first

At the bottom of the file sits a single line — `QUESTS = Quests()`. That
runs **once**, when your game starts up, and every playthrough from then on
uses that same one object. Not one per player: one, ever. If two people are
playing your game at the same time, both are calling methods on it.

That works because the object holds nothing personal. It holds the quest
catalog, the settings, the code — none of which differs between players.
The part that *is* personal is the slot, and it arrives as an argument:

```python
def quest_stage(self, slot, quest_id): ...
```

`self` is the shared object. `slot` is this player's quest log. The method
never needs to know who it is serving, because whoever called it already
handed over the right one.

This is the trap worth knowing about. Writing `self.current_quest =
quest_id` puts one player's progress onto the object everyone shares.
Nothing complains, and it works perfectly while you are the only person
playing — then two players see each other's quests. **Everything a
playthrough changes goes in the slot.**

### 3.2 Keeping state a binding needs: `Skills`

Skills track a number per character per skill, and what that number means
is yours to decide. Read it as a yes/no — they know the spell or they do
not. Read it as a degree — a locksmith at 80 picks faster, or gets
description the novice does not. Or roll against it, TTRPG-style, on
whatever range your game declares: 1-6, 1-20, 1-100.

All three are the same stored number, read differently. Skills is here to
show what a plugin that carries real data can do — from a simple yes/no,
through how good someone is at something, to a roll that decides whether
the player succeeds. It also demonstrates the construction that keeps a
plugin's data safe across saves and shared cleanly between playthroughs.

#### The Skills plugin in full

```python
class SkillSlot(TypedDict):
    skill_levels: dict[str, float]
    rng_seed: int
    last_roll: int
    last_effective_target: int


class Skills(StatefulPlugin[SkillSlot]):
    name = "skills"
    display_name = "Skills"
    state_key = "skills"
    slot_type = SkillSlot
    fields = {"skill_levels": dict, "rng_seed": int,
              "last_roll": int, "last_effective_target": int}

    @external
    def skill_check(self, slot: SkillSlot, level: float, max_level: int, bonus: int = 0) -> bool:
        """Roll against a skill; True on success."""
        ...


SKILLS = Skills()
PLUGIN = SKILLS.plugin()
```

#### Randomness belongs in the slot

The obvious way to roll a die is Python's `random`. It is also wrong here,
for a reason that only shows up later: **a save must reproduce.** Reload a
game and the player should not be able to re-roll a check they already
failed by saving beforehand, nor should a restored session diverge from the
one that was saved.

So the generator's seed lives in the slot as `rng_seed`, is advanced by
each check, and is written into the save with everything else. Restoring a
save restores the position in the random sequence too.

The rule generalises: **anything a binding must remember between calls
goes in the slot** — never anywhere else in your Python, because
everywhere else is shared by every playthrough at once.

#### What happens if you get it wrong

Less than you might fear, and the engine catches most of it for you.

Nothing is corrupted. A save holds the slot and only the slot, so a value
you kept somewhere else is simply **not saved** — the story reloads with
that value back at its starting point. Annoying, findable, not
destructive. Saves cannot be damaged by putting state in the wrong place,
because the engine never writes anything it was not handed.

Two mistakes are caught outright:

- **A value the engine could not save.** `fields` declaring something that
  is not JSON-safe fails the moment the plugin is built, with a message
  naming the plugin and the offending value: *"init_state() is not
  JSON-safe; a definition object is leaking into state"*. You find out at
  startup, not when a player tries to save.
- **`fields` and `slot_type` disagreeing.** Adding a field to one and
  forgetting the other is refused at the same moment, with both key lists
  in the message.

The one that is not caught is storing per-player data on `self` instead of
in the slot. It works while you are the only person playing, then two
players see each other's data. The habit that avoids it entirely: **if a
method changes something, it changes `slot`.** Nothing else in a plugin
should ever be assigned to.

#### Store what the story will want to say

`last_roll` and `last_effective_target` are not needed to decide the check
— `skill_check` already returns a bool. They are there because after a
failure, a story usually wants to *narrate* it: "you needed 55 and rolled
62." A binding that returned only True/False would force the story to roll
again to find out how close it came, which would change the answer.

Keep what the caller will ask about next, not just what the current call
must return.

#### Why skill levels are floats

`skill_levels` holds floats, not ints. Levels sit on whatever range a game
declares (1-6, 1-20, 1-100) and checks normalise internally to a
percentile, so a game is free to award half a point. Declaring the field
`float` when a game might only ever use whole numbers costs nothing.
Declaring it whole-numbers-only and later wanting halves means changing
the field after players already have saves written the old way — much more
work than allowing for it now.

### 3.3 Depending on another plugin: `CharacterOccupancy`

Who is at which location right now. The lesson is **how one plugin builds
on another without tying the two together permanently.**

#### The CharacterOccupancy plugin in full

```python
class OccupancySlot(TypedDict):
    locations: dict[str, str]


class CharacterOccupancy(StatefulPlugin[OccupancySlot]):
    name = "character_occupancy"
    display_name = "Character occupancy"
    state_key = "character_occupancy"
    slot_type = OccupancySlot
    fields = {"locations": dict}


CHARACTER_OCCUPANCY = CharacterOccupancy()
PLUGIN = CHARACTER_OCCUPANCY.plugin()
```

#### The slot is as small as the job

One field. A character's whereabouts is one place id, so the slot is
`{character_id: location_id}` and nothing more. It deliberately does **not**
hold the map — that belongs to `LocationGraph`, which knows places and
edges and nothing about characters.

That asymmetry is the design: **occupancy depends on the map; the map
depends on nothing.** A story with no map still runs occupancy, unchecked.
A story with no occupancy still has a map. Had either plugin held the
other's data, neither could be used alone.

#### Looking up the map instead of owning it

`CharacterOccupancy` never reaches into `LocationGraph`'s code. When it
needs the map, it looks it up in `game_state` by name, at the moment it is
asked — through a `BindingContext`, which is [section 3.4](#34-reading-another-plugins-state-and-needs_context)'s subject.

That difference matters. Reaching for the map directly would make it
*required* — a story with no map could not use occupancy at all. Looking it
up by name means a missing map is just a missing entry, and the plugin
chooses what to do about it. Here it chooses to skip the check rather than
refuse to run.

#### Validating against the other plugin's vocabulary

The payoff is `set_location` refusing a place the map never declared,
raising `UnknownLocationError` rather than storing a typo that will never
match anything again. The map is the vocabulary; occupancy is held to it.

That check is only possible because one plugin can see another's slot — and
only safe because it reads with a default, so a story that declares no map
is unchecked rather than broken.

### 3.4 Reading another plugin's state, and `needs_context`

A method that needs more than its own slot takes the binding context
instead:

```python
    @external(needs_context=True)
    def set_location(self, context: BindingContext[OccupancySlot], character: str, place_id: str) -> None:
        declared = context.slot_of("location_graph").get("declared", [])
        if place_id not in declared:
            raise UnknownLocationError(place_id)
        ...
```

`BindingContext` carries `slot`, `engine_state` and `list_defs`, and
`slot_of(state_key)` reads another plugin's slot with a `{}` default. **Use
the default rather than indexing.** A cross-plugin read can legitimately
find nothing: the other plugin may not be active in this session, or the
save may predate it. Readers throughout the shipped plugins use
`.get(..., default)` for exactly this reason, and a new plugin that indexes
directly will KeyError on an old save.

`list_defs` is the story's own compiled LIST tables, for a plugin that must
answer in terms of real LIST members. It is passed as an argument rather
than parked in `engine_state` so it cannot outlive the bind, be read late
from a closure, or reach a application's persisted save.

### 3.5 The flat `Plugin` contract, and stateless plugins

`StatefulPlugin.plugin()` produces the frozen dataclass everything
downstream actually resolves:

```python
@dataclass(frozen=True)
class Plugin:
    name: str
    display_name: str
    bindings: dict[str, Callable[..., Any]] = field(default_factory=dict)
    validate_config: Callable[[Any], None] | None = None
    state_key: str | None = None
    init_state: Callable[[Any], dict[str, Any]] | None = None
    default_config: Any = None
    bind: Callable[[dict, EngineState, ListDefs], dict[str, Callable]] | None = None
```

A plugin with only `bindings` set is a **stateless** plugin: pure functions,
no per-session data, no slot. Declare one directly as a `Plugin`, or hang
one off a stateful plugin's `stateless_bindings` when the functions belong
to the same subject — a distance-between-two-places helper is stateless
while the map's explored set is not. `state_key is not None` is the real
test for "does this
plugin own state" — not the presence of `bind`, which every plugin has.

`ink_engine.discovery.discover_plugins(sources)` scans a application-supplied list
of sources (a `Path` to a directory of independent `.py` files, or a `str`
naming an importable dotted module) and merges every `PLUGIN` /
`PLUGINS` it finds into one dict keyed by name. **This function has no
trust concept whatsoever** — every source given is scanned and imported
unconditionally. Deciding which sources are even safe to pass is entirely
the application's job, upstream of this call.

### 3.6 Two-phase resolution: allocate, then bind

`resolve_bindings(plugins, active_names, engine_state, configs=None)` runs
in two passes, and the split is what makes activation order stop mattering.

#### Pass 1: allocate

**`allocate_state()`** creates every missing slot before anything
binds — so a plugin whose `bind()` reads a neighbour's slot finds it there
regardless of which was activated first. Of the active plugins sharing one
slot, those carrying a config (an application entry, else `default_config`)
are its
**seeders**:

- exactly one seeder — it builds the slot: `validate_config(config)`, then
  `init_state(config)`;
- no seeder — the first tenant builds it from `init_state(None)`;
- two seeders — `AmbiguousSlotConfigError`, because whichever won would be
  an accident of ordering. This is the loud failure you get from activating
  both a base plugin and its configured subclass; activate one.

**A slot already present is left alone** — no validation, no re-seeding.
That is the resumed-save path, and it is why config must never be the place
a running session's data lives.

#### Pass 2: bind

Binds each active plugin and merges the results into the
`dict[str, Callable]` that goes to `InkRuntimeState(engine_bindings=...)`.

## 4. Testing that a binding is really wired

A declared-but-unwired `EXTERNAL` falls through to its Ink fallback and
answers whatever that fallback returns, forever — so "the tests pass" on
its own proves very little. Two checks that do prove something:

- **Assert each plugin's exact binding-name set.** Compare
  `plugin.bindings.keys()` (or the keys returned by `plugin.bind(...)`)
  against an explicit expected list in a test, so an accidental
  addition/removal fails loudly rather than silently changing the surface
  a story can call.
- **Give the Ink fallback an impossible sentinel.** Have the story's own
  fallback function return a value the real binding can never produce
  (e.g. `-1` for a function that only ever returns a real count), then
  assert the observed value during a real play-through is not that
  sentinel. That distinguishes "the binding ran" from "the fallback ran" —
  no ordinary assertion on the returned value alone can tell those apart
  when the fallback's own default happens to overlap with a legitimate
  real answer.
- **Assert the slot stays JSON-safe and encapsulated.** `json.dumps()` the
  slot after exercising the plugin's writers. A slot that will not
  serialize is a save that will not persist, and the usual cause is a
  definition object (a dataclass, an Enum) reaching state that should hold
  only plain data. `init_state()` checks this for a *fresh* slot; only a
  test covers what the writers put there later.

## 5. Runtime notes — for anyone working on `engine.py` itself

- **The output buffer is truncated per turn**, not accumulated forever.
  `continue_story()` records `len(self.output.tokens)` at its own start and
  slices only the new tokens for `last_turn_text` — serializing the whole
  history instead would grow saved state without bound.
- **Glue lookups are cached, not a rescan.** `_latest_glue_index()`
  (`OutputStream`) only rescans the suffix appended since the last call,
  not the whole turn's buffer.
- **Every transient mid-dispatch flag is part of serialized state**
  (`_eval_run_depth`, `_pending_thread`, `_in_tag`, `_tag_buffer`,
  `_string_capture_stack`, and the rest of `to_dict()`'s own field list) —
  omitting any of them from a save/resume path can leave a resumed session
  in a state the live interpreter would never actually produce on its own
  (e.g. a function-call return marker routed through the wrong branch).
- **An application that writes state mid-turn calls `refresh_choices()`.** A panel
  action that changes what a plugin's slot holds does not by itself change
  the choices already evaluated for this turn; `refresh_choices()` replays
  the turn from its own start so their guards see the new state. Nothing
  advances — the turn count, the emitted text and the position are all
  unchanged, and visit counts are carried across deliberately so the
  replay cannot retire a once-only choice the player never took.
- **[Ink] Tags are cleared per turn.** `current_tags` is reset at the start
  of every `continue_story()` call, matching inkle's own documented
  `currentTags` contract (`RunningYourInk.md`: scoped to "every time you
  get content with `Continue()`") — an interpreter or application that skips this
  leaves every tag ever seen "active" for the rest of the story.
- **Shuffle seeding is a character-sum hash of the container's own path,
  combined with the story's seed** — reproducing Ink's documented
  shuffle/`shuffle once`/`shuffle stopping` behavior
  (`WritingWithInk.md`), and reproducible only if the story seed itself is
  pinned (real Ink seeds from the wall clock by default). `_shuffle_index`
  notes in its own docstring which part of the port is unverified.
- **[Ink] String operators are only `+`/`==`/`!=`**; `?`/`!?` are LIST-only.
  Confirmed directly: `not` applied to a raw string (`not s`, not a
  comparison result) raises `RUNTIME ERROR: ... Cannot perform operation
  '!' on String`; `not` applied to the *result* of a string comparison
  (`not (s == "world")`) works fine, since `==` already produces a boolean
  (see [section 1.3 of the pitfalls guide](ink_pitfalls_and_debugging.md#13-not-binds-tighter-than-comparison)).

## 6. Saving a game

A save covers the whole game world and everything in it: the story's own
progress, and every plugin's state along with it. A restored game
continues exactly where it stopped.

### 6.1 Saving to a folder

Give it a folder to write to:

```python
from pathlib import Path
from if_session import GameSavesDirectory, save_game, load_game_save, list_game_saves

game_saves_directory = GameSavesDirectory(Path("saves"))

# Save into slot 0, with a label the player chose.
save_game("thehauntedhouse", 0, state, "Before the bridge",
          saves_in=game_saves_directory, maximum_gamesave_slots=5, saved_at=when)

# Later, read it back.
state = load_game_save("thehauntedhouse", 0, saves_in=game_saves_directory, maximum_gamesave_slots=5)
```

There is no file opening, closing or folder creation to do: the folder is
made when the first save is written. `"thehauntedhouse"` is whatever name
tells your games apart -- a folder name is the usual answer.

Slots are numbered from 0, the way a Python list is. What a player sees
is your own decision: both shipped applications show the same slots
numbered from 1, and convert at the edge.

`list_game_saves()` gives you a save menu directly. It always returns one
entry per slot, empty ones included, so nothing has to fill the gaps:

```python
for save in list_game_saves("thehauntedhouse", saves_in=game_saves_directory, maximum_gamesave_slots=5):
    if save["used"]:
        print(f'{save["gamesave_slot"]}: {save["label"]} (turn {save["turn_count"]})')
    else:
        print(f'{save["gamesave_slot"]}: (empty)')
```

The rest work the same way: `delete_game_save()` empties a slot,
`quicksave()` and `quickload()` use a single reserved slot of their own
that never disturbs a numbered one, and `has_quicksave()` answers whether
there is one to load.

### 6.2 Sharing a save between installations

`export_game_save()` returns a plain dictionary you can write to a file
and a player can keep or send on. `import_game_save()` takes one back:

```python
envelope = export_game_save("thehauntedhouse", 0, saves_in=game_saves_directory, maximum_gamesave_slots=5)
Path("my-save.json").write_text(json.dumps(envelope))

# Coming back the other way, from a file a player supplied.
import_game_save("thehauntedhouse", 1, json.loads(uploaded), saves_in=game_saves_directory,
                 maximum_gamesave_slots=5, saved_at=when)
```

An imported file is checked before anything is written, so a save that
turns out to be damaged, or to belong to a different game, never
overwrites the slot it was aimed at. A refusal raises `GameSaveError`
with a message you can show the player.

### 6.3 Keeping saves somewhere else

A game that stores saves in a database, or online, supplies its own
answer instead of using `GameSavesDirectory`. Write a class with these
five methods and pass it as `saves_in=`:

```python
class MyGameSavesLocation:
    def read_game_save(self, game_id, gamesave_slot): ...
    def write_game_save(self, game_id, game_save): ...
    def delete_game_save(self, game_id, gamesave_slot): ...
    def game_save_exists(self, game_id, gamesave_slot): ...
    def summarize_game_saves(self, game_id): ...
```

Everything above still applies unchanged -- slots, labels, exporting and
quicksave are the same work whatever is underneath. A game save is a
plain dictionary, so a database can store it as a JSON column without
converting anything.

## 7. When something does not work

Most problems with plugin bindings show up as a scene that quietly does
nothing — a choice that never appears, a check that always answers no.
This is where to look.

### 7.1 A binding answers, but always says no

**The most common cause: the plugin was never switched on.**

Remember from [section 1.3](#13-calling-a-plugin-from-your-story) that a story
falls back to its own Ink version of a
function when nothing provides it. That fallback usually returns something
harmless — `false`, `0`, an empty string — which is exactly what an
honest "no" looks like. So a plugin that was never activated and a plugin
answering truthfully are indistinguishable from inside the story.

To tell them apart, give the Ink fallback an answer the real plugin would
never give:

```ink
=== function where_is(character) ===
~ return "NOT WIRED"
```

If that string turns up in your game, the plugin is not running. Once you
have confirmed the wiring, put the sensible fallback back.

The fix is almost always in the application: the plugin's name belongs in the
list the application passes to `resolve_bindings` ([section
2.0](#20-turning-them-on)), or in the game's
`REQUIRED_PLUGINS`.

### 7.2 The story stops with a missing-function error

`EXTERNAL greet(name)` with nothing to answer it — no plugin, and no
`=== function greet(name) ===` in your story either — stops the story,
naming the function. `inklecate` behaves the same way, so this one is
familiar.

Two ways to avoid meeting it in front of a player:

- **Write the Ink fallback.** Any story that declares an `EXTERNAL` should
  usually have one, so the game stays playable whatever the application provides.
- **Check ahead of time.** `find_unbound_externals(root)` reads a compiled
  story and lists every `EXTERNAL` with no fallback, before anyone plays
  it.

### 7.3 A plugin name that does not exist

Asking the application to switch on a plugin nothing provides is reported
immediately, by name, rather than leaving you to wonder why its functions
are missing. A typo in that list is the usual cause.

This is deliberately different from an `EXTERNAL` a story declares and
never uses — that is ordinary and silent, because a story is free to ask
for more than the application offers.

### 7.4 Names that collide

**An `EXTERNAL` parameter may not share a name with a global `VAR`.**
`inklecate` rejects it outright: *"argument 'x': name has already been
used for a var on line N"*. Worth checking across every file you compile
together — a collision can exist only once `INCLUDE` has combined them,
so a single-file test will not show it.

### 7.5 A function that returns nothing

A story's own Ink function that runs off its end without `~ return`
produces Void, not `0`. Comparing it raises *"Attempting to perform == on
a void value. Did you forget to 'return' a value from a function you
called here?"*

The same applies to a plugin binding: **return a real value on every
path.** A binding marked `-> None` is fine — the engine publishes a
placeholder for it ([section 3.1](#31-a-first-plugin-line-by-line-quests)) — but a binding that sometimes returns a value
and sometimes falls off its end will surprise the story that called it.
