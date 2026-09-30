EXTERNAL divert_to_knot(knot_path)
=== function divert_to_knot(knot_path) ===
~ return -> nowhere_to_go

=== start ===
You are at the start.
-> DONE

=== nowhere_to_go ===
This is reached only by the ink fallback, never the real binding.
-> DONE

=== a_destination ===
You arrive at the destination.
-> DONE

=== a_stitched_knot ===
Not the stitch.
-> DONE
= a_stitch
You arrive at the stitch.
-> DONE

=== go(knot_path) ===
~ temp target = divert_to_knot(knot_path)
-> target

=== function resolve(knot_path) ===
~ return divert_to_knot(knot_path)
