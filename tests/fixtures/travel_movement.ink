VAR destination = -> nowhere
VAR travel_text = ""

-> foyer

=== nowhere ===
-> DONE

=== movement ===
{travel_text}
-> destination

// The GO choice is unguarded, so it is present in every turn's choice
// list without a refresh. The application writes the destination and
// takes it; a player never sees it, because an application that offers
// an exits panel hides it from the story's own choices.
=== foyer ===
You are in the Foyer of the Opera House.
+ [Look at the chandeliers] -> foyer_look
+ [GO] -> movement

=== foyer_look ===
They glitter.
-> foyer

=== bar ===
The bar is empty. A message is scrawled in the sawdust.
+ [Read the message] -> ending
+ [GO] -> movement

=== cloakroom ===
A small brass hook is on the wall.
+ [Examine the hook] -> cloakroom
+ [GO] -> movement

=== ending ===
You have won.
-> END
