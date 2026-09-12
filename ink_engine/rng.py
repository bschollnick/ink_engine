"""Seeded random number generation for story runtimes.

A story format's RANDOM/shuffle output must match the reference
implementation authors test against, so the generator is a property of
the STORY FORMAT: a runtime takes the `RandomEngine` its format
specifies.

`NetRandom` is Ink's: a port of the legacy .NET `System.Random(int seed)`
that `inklecate` runs on.
"""

from __future__ import annotations

import time
from typing import Protocol


class RandomEngine(Protocol):
    """A seeded generator of raw pseudo-random integers.

    Implementations reproduce some specific reference implementation
    exactly; callers do their own range-mapping on the raw result.
    """

    def next(self) -> int:
        """Return the next raw pseudo-random integer in the sequence."""


def wrap_int32(value: int) -> int:
    """Wrap a Python int into C#'s 32-bit signed integer range.

    Python ints never overflow, so int32 arithmetic must be wrapped
    explicitly. Returns `value` modulo 2**32, reinterpreted as signed.
    """
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


class NetRandom:  # pylint: disable=too-few-public-methods
    """A faithful Python port of the legacy .NET `System.Random(int seed)`
    algorithm (the Knuth subtractive/lagged-Fibonacci generator).

    Only the bare parameterless `.Next()` is implemented: Ink never calls
    C#'s other `Next(...)` overloads, since RANDOM/shuffle/LIST_RANDOM all
    do their own range-mapping on the raw int32 result.

    .NET Core 3.0+ (including net6.0, which `inklecate` targets) keeps
    this legacy algorithm for the explicit-seed constructor, though the
    parameterless `Random()` switched to xoshiro128**. The Int32.MinValue
    seed is special-cased to Int32.MaxValue during seed-array init,
    matching the real algorithm.

    Args:
        seed: The seed value. Any int32 is accepted.
    """

    _MBIG = 2147483647
    _MSEED = 161803398

    def __init__(self, seed: int) -> None:
        seed_array = [0] * 56
        subtraction = self._MBIG if seed == -2147483648 else abs(seed)
        mj = wrap_int32(self._MSEED - subtraction)
        seed_array[55] = mj
        mk = 1
        ii = 0
        for i in range(1, 55):
            ii += 21
            if ii >= 55:
                ii -= 55
            seed_array[ii] = mk
            mk = wrap_int32(mj - mk)
            if mk < 0:
                mk = wrap_int32(mk + self._MBIG)
            mj = seed_array[ii]
        for _ in range(1, 5):
            for i in range(1, 56):
                seed_array[i] = wrap_int32(seed_array[i] - seed_array[1 + (i + 30) % 55])
                if seed_array[i] < 0:
                    seed_array[i] = wrap_int32(seed_array[i] + self._MBIG)
        self._seed_array = seed_array
        self._inext = 0
        self._inextp = 21

    def next(self) -> int:
        """Return the next pseudo-random int32 in this generator's sequence.

        Ports Random.InternalSample(): two rolling indices into the
        56-element seed array, each call advancing both and folding the
        difference back into the array.

        Returns:
            A value in [0, Int32.MaxValue), matching C#'s
            `Random.Next()` (the parameterless overload) exactly for the
            same seed.
        """
        inext = self._inext + 1
        if inext >= 56:
            inext = 1
        inextp = self._inextp + 1
        if inextp >= 56:
            inextp = 1
        ret_val = wrap_int32(self._seed_array[inext] - self._seed_array[inextp])
        if ret_val == self._MBIG:
            ret_val -= 1
        if ret_val < 0:
            ret_val = wrap_int32(ret_val + self._MBIG)
        self._seed_array[inext] = ret_val
        self._inext = inext
        self._inextp = inextp
        return ret_val


def time_seed() -> int:
    """Return a nondeterministic int32 seed derived from the current time.

    Ports the construction-time default in Story.ResetState
    (ink-engine-runtime/StoryState.cs: `storySeed = new
    Random(timeSeed).Next() % 100`) — a story has no fixed seed unless
    the author calls `SEED_RANDOM()`. Uses time.time_ns() truncated to
    int32, not C#'s own clock-seed formula; only nondeterminism matters.
    """
    return wrap_int32(time.time_ns())
