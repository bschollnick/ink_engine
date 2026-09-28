// A tunnel whose target is a divert-target variable, then a second
// tunnel through a divert-target parameter. Compiled to
// variable_tunnel.ink.json via inklecate.
VAR where = -> side
Before.
-> where ->
Middle.
-> through(-> side)
=== through(-> target) ===
-> target ->
After.
-> END

=== side ===
Inside.
->->
