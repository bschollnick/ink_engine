VAR score = 10
LIST Bag = apple, pear, plum
VAR sack = (apple, pear)

Before: {score}
~ bump(score)
After: {score}
Popped: {pop(sack)}
Sack now: {sack}
-> END

=== function bump(ref n)
   ~ n = n + 5

=== function pop(ref list)
   ~ temp x = LIST_MIN(list)
   ~ list -= x
   ~ return x
