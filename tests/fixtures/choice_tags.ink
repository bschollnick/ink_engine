// Standard Ink choice tags (RunningYourInk.md:186-194): a tag inside the
// choice's own brackets belongs to the choice, never to its content.
Who is she?
* A choice #shared_tag [ with detail #choice_tag ] and content # content_tag
    Content one.
    -> END
* [As a cleaner # image: louise/Monica/louise1b.jpg] -> picked
* [Casually # image: louise/Kayla/louise1b.jpg] -> picked
* {false} [Never shown # image: hidden.jpg] -> picked
* [Plain, no tag] -> picked
=== picked ===
You chose.
-> END
