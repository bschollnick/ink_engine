EXTERNAL has_item(name)
EXTERNAL use_item(name)
EXTERNAL log_visit()
VAR has_rope = false
VAR has_key = true
VAR gold = 10
VAR visits_here = 0
-> hall
=== hall ===
~ visits_here += 1
~ gold -= 5
~ temp lamp_now = has_item("lamp")
~ log_visit()
In the hall.
{ has_rope:
    <- climb
}
+ {has_key} [Unlock the door] -> END
+ {gold >= 5} [Buy a drink] -> END
+ {visits_here == 1} [First look around] -> END
+ {lamp_now} [Light the lamp] -> END
+ {has_item("lamp")} [Polish the lamp] -> END
+ [Wait] -> END
=== climb ===
+ [Climb the rope] -> END
=== follower_action ===
~ has_key = false
~ has_rope = true
~ use_item("lamp")
The follower takes your key and lamp, and hands you a rope.
->->
=== follower_chat ===
~ has_key = false
~ use_item("lamp")
"Shall I?" the follower asks.
+ [Let them]
  ~ has_rope = true
  ->->
=== function has_item(name) ===
~ return false
=== function use_item(name) ===
~ return 0
=== function log_visit() ===
~ return 0
