// A story that counts its own turns, for the session-isolation test.
// Each turn increments one global and stops, so a finished playthrough
// leaves `turns` at exactly TOTAL -- any other value means turns were
// lost or double-counted.
CONST TOTAL = 400
VAR turns = 0

-> tick

=== tick ===
~ turns = turns + 1
Turn {turns}.
{ turns >= TOTAL: -> END }
-> tick
