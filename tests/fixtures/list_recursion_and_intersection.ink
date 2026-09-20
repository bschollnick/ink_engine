LIST Values = strength, courage, compassion, greed, nepotism, self_belief
VAR desired = (strength, courage, compassion, self_belief)
VAR actual = (greed, nepotism, self_belief)
LIST Chain = a1, a2, a3, b1, b2
VAR knowledgeState = ()

Overlap: {desired ^ actual}
SubsetAll: {actual ? (greed, nepotism)}
SubsetPartial: {actual ? (greed, strength)}
NotEmpty: {not ()}
NotFull: {not actual}
POW: {POW(3,2)}
~ temp got = reach((a3, b2))
Reached: {knowledgeState}
-> END

=== function pop(ref list)
   ~ temp x = LIST_MIN(list)
   ~ list -= x
   ~ return x

=== function reached(x)
   ~ return knowledgeState ? x

=== function reach(statesToSet)
   ~ temp x = pop(statesToSet)
   {
   - not x:
      ~ return false
   - not reached(x):
      ~ temp chain = LIST_ALL(x)
      ~ temp statesGained = LIST_RANGE(chain, LIST_MIN(chain), x)
      ~ knowledgeState += statesGained
      ~ reach(statesToSet)
      ~ return true
   - else:
      ~ return false || reach(statesToSet)
   }
