# Examples

**Date Created:** 2026-09-08  
**Last Updated:** 2026-09-20  
**Last Reviewed:** 2026-09-19

- **`hello.ink`** — the tiny example story walked through in the main
  [README](../README.md)'s own quickstart section: one choice, two
  branches, both ending the story.
- **`hello.ink.json`** — `hello.ink`, compiled with `inklecate` (see the
  main README's "Compiling stories" section). This is the file
  `ink-engine` actually reads.
- **`play_hello.py`** — the same walkthrough as a script: opens the
  compiled story, plays one turn, prints the text and the choices.

Recompile after editing `hello.ink`:

```bash
inklecate -o hello.ink.json hello.ink
```

Play it, from the repository root:

```bash
poetry run python examples/play_hello.py
```

```
You wake in a small stone room. A single door stands to the north.

0 Try the door
1 Look around first
```

`play_hello.py` is that same program as a file, so you can edit it and
run it again:

```python
import json
from pathlib import Path

from ink_engine.engine import InkRuntimeState, load_list_defs, load_story_root

compiled = json.loads(Path("examples/hello.ink.json").read_text(encoding="utf-8"))
state = InkRuntimeState(load_story_root(compiled), load_list_defs(compiled))

state.continue_story()
print(state.last_turn_text)

for index, choice in enumerate(state.current_choices):
    print(index, choice.text)
```

Pick a choice by index and play on with `state.choose(0)`, then
`state.continue_story()` again.
