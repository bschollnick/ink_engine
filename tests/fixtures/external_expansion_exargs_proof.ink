Hand-authored compiled JSON (not run through inklecate) — isolates parsing
of a non-zero "exArgs" arity on a real "x()" EXTERNAL call
(claude_docs/plans/external_expansion_IF_engine.md's Step 1: FunctionCall
previously discarded this field entirely since no dispatch path needed it;
a real Python-callable binding does, to know how many eval_stack values to
pop before invoking the callable).

Ink-equivalent source:

~ SUM3(1, 2, 3)
-> END

EXTERNAL SUM3(a, b, c)
=== function SUM3(a, b, c)
    ~ return a + b + c
