-> start
=== start ===
~ temp x = "caller"
-> t("tunnel") ->
After t: x is {x}.
-> outer ->
After outer: x is {x}.
-> END
=== t(x) ===
~ temp y = 1
~ bump(y)
Inside t: x is {x}, y is {y}.
->->
=== outer ===
~ temp x = "outer"
-> t("nested") ->
Back in outer: x is {x}.
->->
=== function bump(ref value) ===
~ value = value + 1
