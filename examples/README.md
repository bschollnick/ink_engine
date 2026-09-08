# Examples

- **`hello.ink`** — the tiny example story walked through in the main
  [README](../README.md)'s own quickstart section: one choice, two
  branches, both ending the story.
- **`hello.ink.json`** — `hello.ink`, compiled with `inklecate` (see the
  main README's "Compiling stories" section). This is the file
  `ink-engine` actually reads.

Recompile after editing `hello.ink`:

```bash
inklecate -o hello.ink.json hello.ink
```

Play it directly:

```bash
poetry run python -c "
import json
from ink_engine.engine import InkRuntimeState, load_story_root, load_list_defs

with open('examples/hello.ink.json') as f:
    compiled = json.load(f)

state = InkRuntimeState(load_story_root(compiled), load_list_defs(compiled))
state.continue_story()
print(state.last_turn_text)
for i, choice in enumerate(state.current_choices):
    print(i, choice.text)
"
```
