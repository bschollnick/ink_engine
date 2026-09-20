"""Play `hello.ink.json` from the command line: one turn, then the choices.

Run from the repository root:

    poetry run python examples/play_hello.py
"""

from __future__ import annotations

import json
from pathlib import Path

from ink_engine.engine import InkRuntimeState, load_list_defs, load_story_root

STORY = Path(__file__).with_name("hello.ink.json")


def main() -> None:
    """Open the story, play its first turn, and list the choices offered."""
    compiled = json.loads(STORY.read_text(encoding="utf-8"))
    state = InkRuntimeState(load_story_root(compiled), load_list_defs(compiled))

    state.continue_story()
    print(state.last_turn_text)

    for index, choice in enumerate(state.current_choices):
        print(index, choice.text)


if __name__ == "__main__":
    main()
