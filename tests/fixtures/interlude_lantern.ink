// The runnable example in the bindings guide, Section 4.2: an interlude
// that takes an item the scene's choices depend on. Compiled to
// interlude_lantern.ink.json via inklecate.
EXTERNAL has_item(holder_id, item_id)
EXTERNAL take_item_from(holder_id, item_id)
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

=== lend_the_lantern ===
~ temp lent = take_item_from("player", "lantern")
You hand Sam the lantern.
->->

=== function has_item(holder_id, item_id) ===
~ return false

=== function take_item_from(holder_id, item_id) ===
~ return false
