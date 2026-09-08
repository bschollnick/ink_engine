Hand-authored compiled JSON (not run through inklecate) — extends
external_expansion_exargs_proof.ink.json's SUM3(a,b,c) EXTERNAL to actually
print its return value, so a test can observe whether a real Python
dispatch's return value genuinely flows back onto eval_stack and into the
story's own print expression (claude_docs/plans/
external_expansion_IF_engine.md Step 3), not just that some call happened.

Ink-equivalent source:

Result: {SUM3(1, 2, 3)}
-> END

EXTERNAL SUM3(a, b, c)
=== function SUM3(a, b, c)
    ~ return a + b + c
