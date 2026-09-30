-> hub
=== hub ===
<- offer("left", -> went)
<- offer("right", -> went)
<- walk("north")
<- walk("south")
-> DONE
=== offer(side, -> next) ===
+ [Go {side}] -> next(side)
=== walk(direction) ===
+ [Walk {direction}] -> walked(direction)
=== went(where) ===
You went {where}. -> END
=== walked(heading) ===
You walked {heading}. -> END
