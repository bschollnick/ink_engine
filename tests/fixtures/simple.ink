// Pure navigation, no variables/functions/lists. Compiled to
// simple.ink.json via inklecate.
//
// NOTE: this story opens directly with "== start ==" as its first line,
// which inklecate's -p play mode never actually enters (the default
// entry point is top-level content, not the first named knot) —
// harmless here since these tests only inspect the compiled JSON
// directly and never call -p, but do not reuse this fixture for playback
// tests. See glue.ink for a fixture written to be playable.
== start ==
First line.
Second line.
-> next_knot

== next_knot ==
Third line.
-> END
