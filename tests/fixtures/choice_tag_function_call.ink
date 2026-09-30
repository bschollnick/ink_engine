// A choice tag interpolating a function call whose body evaluates a
// comparison or a string concatenation. Regression coverage for the
// operator/eval-stack tokens ("==", "+") and a called function's own
// structural newline leaking into the tag's captured text instead of
// being evaluated or trimmed.
VAR x = 2

-> start

=== function literal_value() ===
~ return "lit.jpg"

=== function compared_value() ===
{ x == 2:
    ~ return "b.jpg"
}
~ return "a.jpg"

=== function concatenated_value() ===
~ return "face" + ".jpg"

=== function nested_value() ===
~ return compared_value()

=== function printing_value() ===
Side effect.
~ return "noisy.jpg"

=== start ===
Hello.
+ [Literal # image: {literal_value()}] -> END
+ [Compare # image: {compared_value()}] -> END
+ [Concat # image: {concatenated_value()}] -> END
+ [Nested # image: {nested_value()}] -> END
+ [Printing # image: {printing_value()}] -> END
