LIST letters = alpha, beta, gamma, delta, epsilon
VAR here = (alpha, beta, gamma, delta, epsilon)
-> room
=== room ===
In the room.
-> offers ->
+ [Leave] -> END
=== offers ===
-> offer_each(here)
=== offer_each(remaining) ===
{ LIST_COUNT(remaining) == 0:
    ->->
}
~ temp one = LIST_MIN(remaining)
<- offer_each(remaining - one)
+ [Pick {one}] You pick {one}. -> END
- ->->
