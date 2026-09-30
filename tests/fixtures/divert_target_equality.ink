VAR v = -> event_scene
A{ -> event_scene == -> event_scene: T | F }
B{ v == -> event_scene: T | F }
C{ v == -> plain_scene: T | F }
-> k(-> event_scene)
=== k(-> d) ===
D{ d == -> event_scene: T | F }
E{ d == v: T | F }
-> END
=== event_scene ===
-> END
=== plain_scene ===
-> END
