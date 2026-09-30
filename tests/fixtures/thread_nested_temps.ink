-> start
=== start ===
~ temp x = "main"
Start {x}.
<- outer("A")
<- outer("B")
+ [Main {x}] Main chose, x is {x}. -> END
=== outer(tag) ===
~ temp x = "outer-" + tag
<- inner(tag + "1")
<- inner(tag + "2")
+ [Outer {tag} {x}] Outer chose {tag}, x is {x}. -> END
=== inner(name) ===
~ temp x = "inner-" + name
+ [Inner {name} {x}] Inner chose {name}, x is {x}. -> END
