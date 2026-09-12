"""Per-turn cost of the plugin layer, measured on a real game build.

Reports absolute cost for the four things a turn actually pays for:
building a session's binding dict, allocating its state slots, reading a
hot binding, and round-tripping the state through JSON. The numbers are
meant to be read against a request's total time -- a plugin layer costing
a fraction of a millisecond on a build with this many bindings is not
where a slow turn comes from.

The measurement is absolute, not a comparison: there is no "before" tree
to run against (the conversion had already shipped when this was
written), so nothing here gates anything. It is a baseline for future
work.

This benchmark needs a real, trusted, compiled story and the host that
owns the trust decision, so it runs under that host's settings rather
than standalone:

    cd <host>/quickbbs && python -m benchmarks.plugin_turn_cost

with this directory importable, or simply run it by path from there.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import timeit

REPEATS = 5
CALLS_PER_SAMPLE = 100


def _setup_django() -> None:
    """Start Django using the host application's own settings.

    Raises:
        SystemExit: Django or the host application is not importable.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "quickbbs.settings")
    # Run by path from the host's working directory, that directory is not
    # on sys.path -- only the script's own is.
    if "" not in sys.path and os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    try:
        import django
    except ImportError:
        sys.exit("This benchmark runs against a host application; Django was not importable.")
    django.setup()


def _best_microseconds(statement, *, calls: int = CALLS_PER_SAMPLE) -> float:
    """Return the best per-call time in microseconds, best of REPEATS.

    Best-of rather than mean: the fastest run is the one least disturbed
    by other work on the machine.

    Args:
        statement: A zero-argument callable to time.
        calls: How many calls make up one timed sample.

    Returns:
        Microseconds per call.
    """
    samples = timeit.repeat(statement, repeat=REPEATS, number=calls)
    return min(samples) / calls * 1_000_000


def main() -> None:
    """Measure and print the per-turn plugin cost for the sample story."""
    _setup_django()

    from interactive_fiction.engine_services import bindings_for
    from interactive_fiction.models import Story

    story = Story.objects.filter(is_engine_trusted=True).exclude(compiled_json=None).first()
    if story is None:
        sys.exit("No trusted, compiled story to benchmark against.")

    engine_state: dict[str, object] = {}
    bindings = bindings_for(story, engine_state)
    binding_count = len(bindings)
    slot_count = len(engine_state)

    print(f"story: {story.slug}   bindings: {binding_count}   state slots: {slot_count}")
    print(f"best of {REPEATS}, {CALLS_PER_SAMPLE} calls per sample\n")

    # A full turn's binding construction: allocate every slot, then bind.
    print(f"{'bind a fresh session (allocate + bind)':<44}{_best_microseconds(lambda: bindings_for(story, {})):>9.1f} us")

    # The same, onto state that already exists -- the resumed-save path,
    # which is what every turn after the first actually runs.
    print(f"{'bind onto existing state (per turn)':<44}{_best_microseconds(lambda: bindings_for(story, engine_state)):>9.1f} us")

    # A hot read through a real binding, if the build publishes one that
    # takes no arguments.
    hot_name = next((name for name in ("clock", "hour_of_day_now", "hour_of_day") if name in bindings), None)
    if hot_name is not None:
        hot = bindings[hot_name]
        try:
            hot()
        except TypeError:
            hot_name = None
        else:
            # Nanoseconds: a slot read is far below microsecond resolution.
            print(f"{'hot read: ' + hot_name + '()':<44}{_best_microseconds(hot, calls=100_000) * 1000:>9.0f} ns")
    if hot_name is None:
        print(f"{'hot read':<44}{'skipped (no zero-arg binding)':>9}")

    encoded = json.dumps(engine_state)
    print(f"{'state -> JSON':<44}{_best_microseconds(lambda: json.dumps(engine_state)):>9.1f} us")
    print(f"{'JSON -> state':<44}{_best_microseconds(lambda: json.loads(encoded)):>9.1f} us")
    print(f"{'serialized state size':<44}{len(encoded):>9,} bytes")

    per_turn = statistics.mean(timeit.repeat(lambda: bindings_for(story, engine_state), repeat=REPEATS, number=CALLS_PER_SAMPLE)) / CALLS_PER_SAMPLE
    print(f"\nplugin layer per turn: {per_turn * 1000:.3f} ms (mean), against a request budget measured in tens of ms")


if __name__ == "__main__":
    main()
