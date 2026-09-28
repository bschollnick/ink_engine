// Cloak of Darkness — a demonstration game.
//
// The game Roger Firth specified in 1999 so that one story could be
// implemented across many authoring systems and compared. Three rooms,
// three objects, five or six moves to win.
//
// Written from the published specification. Room descriptions are
// required to be identical across implementations and are quoted from
// it; everything below that is this implementation's own.
//
// The disturbance rule follows the 1999 original: moving in the dark
// costs two, any other action in the dark costs one, and the message is
// readable below two.

// The application writes these before taking the GO choice: where the
// story is going, and the prose for getting there. Both come from the
// exit the player clicked, which the map declares.
VAR destination = -> nowhere
VAR travel_text = ""

// The map's id for the room the player is in, so the side panel knows
// whose exits to draw. Each room's knot sets it on arrival.
VAR current_location = "foyer"

// 0 worn, 1 on the hook, 2 on the floor.
VAR cloak_place = 0
VAR disturbance = 0
VAR score = 0
VAR hook_point_taken = false

-> opening

=== nowhere ===
-> DONE

// Arriving anywhere: the travel prose, then the place itself. One knot
// serves every exit, because the exit supplies both.
=== movement ===
{travel_text}
-> destination

// The bar is lit exactly when the player is not carrying the cloak.
// Derived rather than stored, so it cannot disagree with the cloak.
=== function bar_is_lit() ===
~ return cloak_place != 0

=== function disturb(amount) ===
~ disturbance = disturbance + amount

=== opening ===
Hurrying through the rainswept November night, you're glad to see the
bright lights of the Opera House. It's surprising that there aren't more
people about but, hey, what do you expect in a cheap demo game...?
-> foyer

=== foyer ===
~ current_location = "foyer"
You are standing in a spacious hall, splendidly decorated in red and
gold, with glittering chandeliers overhead. The entrance from the street
is to the north, and there are doorways south and west.
+ [Go south, to the bar] -> bar
+ [Go west, to the cloakroom] -> cloakroom
+ [Go north, to the street] -> street_refused
+ [Check what you are carrying] -> foyer_inventory
+ [GO] -> movement

=== street_refused ===
You've only just arrived, and besides, the weather outside seems to be
getting worse.
-> foyer

=== foyer_inventory ===
{cloak_place == 0:
    You are wearing a black velvet cloak.
- else:
    You are carrying nothing.
}
-> foyer

=== cloakroom ===
~ current_location = "cloakroom"
The walls of this small room were clearly once lined with hooks, though
now only one remains. The exit is a door to the east.
+ [Examine the hook] -> hook_description
+ {cloak_place == 0} [Hang the cloak on the hook] -> hang_cloak
+ {cloak_place == 0} [Drop the cloak on the floor] -> drop_cloak
+ {cloak_place == 1} [Take the cloak from the hook] -> take_cloak
+ {cloak_place == 2} [Pick the cloak up off the floor] -> take_cloak
+ [Go east, to the foyer] -> foyer
+ [GO] -> movement

=== hook_description ===
It's just a small brass hook, {cloak_place == 1: with a cloak hanging on it.|screwed to the wall.}
-> cloakroom

=== hang_cloak ===
~ cloak_place = 1
{not hook_point_taken:
    ~ hook_point_taken = true
    ~ score = score + 1
}
You hang the cloak on the hook. The room feels no different, but
somewhere behind you a light seems to have been let in.
-> cloakroom

=== drop_cloak ===
~ cloak_place = 2
You drop the cloak on the floor. It is not the best place for a smart
cloak, but it is out of your hands.
-> cloakroom

=== take_cloak ===
~ cloak_place = 0
You put the cloak back on.
-> cloakroom

// The bar has two forms. Dark, almost everything the player does
// disturbs the sawdust; lit, the message can be read and the game ends.
=== bar ===
~ current_location = "bar"
{bar_is_lit():
    -> bar_lit
- else:
    -> bar_dark
}

=== bar_lit ===
The bar, much rougher than you'd have guessed after the opulence of the
foyer to the north, is completely empty. There seems to be some sort of
message scrawled in the sawdust on the floor.
+ [Read the message] -> read_message
+ [Go north, to the foyer] -> foyer
+ [GO] -> movement

=== bar_dark ===
It is pitch dark in here. You can just make out a doorway to the north.
+ [Go north, to the foyer] -> foyer
+ [Feel around on the floor] -> fumble_in_dark
+ [GO] -> movement
+ [Go south, further into the dark] -> blunder_in_dark
+ [Go east, further into the dark] -> blunder_in_dark
+ [Go west, further into the dark] -> blunder_in_dark

=== fumble_in_dark ===
~ disturb(1)
In the dark? You could easily disturb something!
-> bar

=== blunder_in_dark ===
~ disturb(2)
Blundering around in the dark isn't a good idea!
-> bar

=== read_message ===
{disturbance < 2:
    ~ score = score + 1
    The message, neatly marked in the sawdust, reads...
    -> ending_won
- else:
    The message has been carelessly trampled, making it difficult to
    read. You can just distinguish the words...
    -> ending_lost
}

=== ending_won ===
<b>You have won</b>
-> final_score

=== ending_lost ===
<b>You have lost</b>
-> final_score

=== final_score ===
In that game you scored {score} out of a possible 2.
-> END
