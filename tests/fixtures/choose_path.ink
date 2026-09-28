// Targets an application jumps to with InkRuntimeState.choose_path().
// Compiled to choose_path.ink.json via inklecate; choose_path_reference.ink
// reaches the same targets by ordinary diverts, for inklecate's transcript.
VAR visits = 0
-> start

=== start ===
Start.
-> helper ->
Unreached.
-> END

=== helper ===
In the helper.
~ temp mood = "calm"
+ [Wait] -> start

=== kitchen ===
~ visits += 1
The kitchen.
+ [Leave] -> END

= pantry
The pantry.
-> END

=== greet(name) ===
Hello, {name}.
-> END

=== counted ===
Counted {counted} times.
+ [Again] -> counted
