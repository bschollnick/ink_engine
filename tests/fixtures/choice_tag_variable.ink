// A variable printed inside a choice's own tag belongs to the tag.
// Compiled to choice_tag_variable.ink.json via inklecate; inklecate -j -p
// reports text "Wave to Sam" and tags ["group: sam",
// "image: sam/Winter/sam-facec.jpg"].
VAR friendly = true
VAR season = "Winter"
Hello.
+ [Wave to Sam # group: sam # image: sam/{season}/sam-face{friendly:c|u}.jpg] -> DONE
