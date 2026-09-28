// The runnable example in the bindings guide, Section 4.1: a choice an
// application unlocks by giving the player an item mid-turn. Compiled to
// refresh_lantern.ink.json via inklecate.
EXTERNAL has_item(holder_id, item_id)
VAR visits = 0
-> cellar

=== cellar ===
~ visits += 1
The cellar is dark.
+ {has_item("player", "lantern")} [Light the lantern] -> lit
+ [Go back up] -> END

=== lit ===
The cellar glows.
-> END

=== function has_item(holder_id, item_id) ===
~ return false
