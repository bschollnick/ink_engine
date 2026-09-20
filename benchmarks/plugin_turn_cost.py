"""Per-turn cost of the plugin layer, measured on a real game build.

Measures the four things a turn pays for: building a session's binding
dictionary, allocating its state slots, reading a hot binding, and
round-tripping the state through JSON.

The figures are absolute, not a comparison against an earlier tree, so
nothing here gates a build. It records a baseline to measure later work
against.

This benchmark is the one thing here that reads a consumer. The engine
depends on nothing but PyYAML; QuickBBS depends on the engine, and holds
the trusted compiled stories and the trust decision that says which may
run. Measuring a real build therefore means importing that application,
which in turn needs its Django settings loaded first:

    cd <application>/quickbbs && python -m benchmarks.plugin_turn_cost

Run it from that directory, either as a module with this directory
importable or by path. Nothing in `ink_engine` or `if_session` imports
Django, or QuickBBS, or anything this file reaches for.
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
    """Start Django, which the consuming application needs before import.

    Raises:
        SystemExit: Django or the application is not importable.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "quickbbs.settings")
    # Run by path, only the script's own directory is on sys.path, not
    # the working directory this needs to import the application from.
    if "" not in sys.path and os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    try:
        import django
    except ImportError:
        sys.exit("This benchmark runs against a Django application; Django was not importable.")
    django.setup()


def _best_microseconds(statement, *, calls: int = CALLS_PER_SAMPLE) -> float:
    """Return the best per-call time in microseconds, best of REPEATS.

    The fastest sample is the one least disturbed by other work on the
    machine.

    Args:
        statement: A zero-argument callable to time.
        calls: How many calls make up one timed sample.

    Returns:
        Microseconds per call.
    """
    samples = timeit.repeat(statement, repeat=REPEATS, number=calls)
    return min(samples) / calls * 1_000_000


def main() -> None:
    """Measure and print the per-turn plugin cost for one trusted story.

    Raises:
        SystemExit: No trusted, compiled story is in the database.
    """
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

    # A fresh session: allocate every slot, then bind.
    print(f"{'bind a fresh session (allocate + bind)':<44}{_best_microseconds(lambda: bindings_for(story, {})):>9.1f} us")

    # Onto state that already exists: the path every turn after the
    # first runs.
    print(f"{'bind onto existing state (per turn)':<44}{_best_microseconds(lambda: bindings_for(story, engine_state)):>9.1f} us")

    # A hot read, only if the build publishes a zero-argument binding.
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
