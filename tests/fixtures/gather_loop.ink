// Named knots, an unconditional divert loop back into its own knot,
// once-only pruning of a re-offered choice, and a divert to a second
// named knot. Compiled to gather_loop.ink.json via inklecate. Opens
// with "-> room" rather than the knot header directly: inklecate -p
// never enters a story whose first line is a "== knot ==" header.
-> room

== room ==
You are in a room.
* [Look around] -> room
* [Leave] -> outside

== outside ==
You step outside.
-> DONE
