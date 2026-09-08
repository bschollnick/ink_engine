Hand-authored compiled JSON (not run through inklecate) — modeled directly
on external_uppercase.ink.json's own real, inklecate-compiled call-site
shape, with "x()" swapped for an ordinary "f()" so this fixture isolates
the void-return-printed-as-expression bug without also depending on
EXTERNAL/"x()" dispatch.

Ink-equivalent source:

{say("Give me wine!")}
-> END

=== function say(txt)
    {txt}
