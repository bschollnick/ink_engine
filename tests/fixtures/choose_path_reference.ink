// The reference for choose_path.ink: each choice diverts where the tests
// jump, so inklecate's -p transcript gives the expected text.
VAR visits = 0
+ [kitchen] -> kitchen
+ [pantry] -> kitchen.pantry
+ [greet] -> greet("Sam")
+ [counted] -> counted

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
