// The runnable example in the bindings guide, Section 4.5: a panel command
// whose reaction is a story turn. Compiled to panel_command.ink.json via
// inklecate.
VAR bell_rung = false
-> shop

=== shop ===
The shopkeeper eyes you warily.
+ {bell_rung} [Ask why the bell rang] The shopkeeper shrugs. -> shop
+ [Leave] You leave. -> END

=== bell_rings ===
~ bell_rung = true
The bell over the door rings.
-> shop
