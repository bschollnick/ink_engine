VAR stamina = 3
-> main
=== main ===
You slip.
-> hurt(5) ->
Back in main.
-> END
=== hurt(x) ===
Ouch.
~ stamina = stamina - x
{ stamina <= 0:
    ->-> youre_dead
}
You're still alive!
->->
=== youre_dead ===
You lost, buddy.
-> END
