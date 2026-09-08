// Same as conditional_choice.ink but with the condition false, so the
// choice must not appear at all.
VAR unlocked = false
A door.
* { unlocked } [Enter] You entered.
- Locked.
-> DONE
