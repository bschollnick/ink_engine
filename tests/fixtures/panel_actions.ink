// A menu knot whose tagged choices a side panel lists as actions, run as
// interludes in the middle of `scene`. Compiled to panel_actions.ink.json
// via inklecate.
VAR sam_present = true
VAR ada_present = false
VAR season = "Winter"
VAR chats = 0
-> scene

=== scene ===
The shopkeeper eyes you warily.
+ [Browse] You browse. -> scene
+ [Leave] You leave. -> END

=== companion_actions ===
+ {sam_present} [Talk to Sam # group: sam # image: sam/{season}/sam-face.jpg] -> talk_to_sam
* {sam_present} [Ask Sam about the shop # group: sam] -> sam_on_the_shop
+ {ada_present} [Talk to Ada # group: ada # image: ada/ada-face.jpg] -> talk_to_ada
+ [Check the time] -> check_time
-> DONE

=== talk_to_sam ===
~ chats += 1
Sam grins.
->->

=== sam_on_the_shop ===
"It's old," says Sam.
->->

=== talk_to_ada ===
Ada nods.
->->

=== check_time ===
It is noon.
->->
