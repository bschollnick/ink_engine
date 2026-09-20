LIST Vignette = v1, v2, v3, v4

~ temp eligible = LIST_ALL(Vignette)
{ prune(eligible) }
Remaining: {eligible}
Count: {LIST_COUNT(eligible)}
-> END

=== function ok(v) ===
~ return v == v2 || v == v4

=== function prune(ref eligible) ===
{ not ok(v1):
    ~ eligible -= v1
}
{ not ok(v2):
    ~ eligible -= v2
}
{ not ok(v3):
    ~ eligible -= v3
}
{ not ok(v4):
    ~ eligible -= v4
}
