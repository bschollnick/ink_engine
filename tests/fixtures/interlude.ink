// Knots an application runs as interludes (InkRuntimeState.start_interlude)
// in the middle of `scene`. Compiled to interlude.ink.json via inklecate.
VAR talked = 0
-> scene

=== scene ===
The shopkeeper eyes you warily.
- (opts)
* [Ask about the vase] She shrugs. "Old."
    -> opts
* [Leave] You leave.
    -> END

=== quick_word ===
~ talked += 1
Sam whispers, "Let me handle this."
->->

=== question ===
Sam leans over. "Want to leave?"
* ["Yes"] "Then let's go."
    ->-> street
* ["Wander off"] You wander off.
    -> street
* ["Not yet"] "Fine."
- ->->

=== street ===
You are on the street.
-> errand ->
Back on the street.
+ [Wait] -> street

=== errand ===
You run an errand.
->->

=== farewell ===
Sam waves goodbye.
-> END
