VAR score = 0
VAR visits = 0
EXTERNAL double_it(x)

-> intro

=== intro
Welcome to the story.
~ visits = visits + 1
+ [Continue]
    -> chapter_two

=== chapter_two
This is chapter two.
-> END

=== function add(x, y)
~ score = score + 1
~ return x + y

=== function greet(name)
~ return "Hello, " + name + "!"

=== function describe_score(current)
~ temp label = "low"
{ current >= 10:
    ~ label = "high"
- else:
    { current >= 5:
        ~ label = "medium"
    }
}
~ return "score is " + label + " (" + "{current}" + ")"

=== function noisy(x)
This function prints text.
~ return x * 2

=== function callsExternal(x)
~ return double_it(x)
