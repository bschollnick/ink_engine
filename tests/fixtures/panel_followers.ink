// A followers section: entries declared outside the story (in Python),
// each with a head-shot function; a menu knot's tagged choices supply
// the "Speak to" actions some entries have and others do not. Compiled
// to panel_followers.ink.json via inklecate.
VAR sam_present = true
VAR sam_chatty = true
VAR ada_present = false
VAR season = "Winter"
-> scene

=== scene ===
The shopkeeper eyes you warily.
+ [Leave] -> END

=== function sam_head_shot() ===
~ return "sam/{season}/sam-face.jpg"

=== function ada_head_shot() ===
~ return "ada/ada-face.jpg"

=== companion_actions ===
+ {sam_present and sam_chatty} [Talk to Sam # group: sam] -> talk_to_sam
+ {ada_present} [Talk to Ada # group: ada] -> talk_to_ada
-> DONE

=== talk_to_sam ===
Sam grins.
->->

=== talk_to_ada ===
Ada nods.
->->
