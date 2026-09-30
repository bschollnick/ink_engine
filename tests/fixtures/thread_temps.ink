LIST letters = alpha, beta, gamma, delta, epsilon, zeta
VAR here = (alpha, beta, gamma, delta, epsilon, zeta)
-> room
=== room ===
In the room.
<- offers(here)
+ [Leave] -> END
=== offers(remaining) ===
{ LIST_COUNT(remaining) == 0: -> DONE }
~ temp which = LIST_MIN(remaining)
<- offers(remaining - which)
+ [Pick {which}] You pick {which}. -> END
