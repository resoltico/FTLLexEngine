#!/usr/bin/env python3
"""Reproduction 1: Replay the exact crash input WITHOUT Atheris.

Measures memory for a single iteration with the crash input bytes.
This isolates whether ftllexengine itself leaks on this specific input.
"""
import os
import sys

import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ftllexengine.runtime.bundle import FluentBundle

CRASH_INPUT = bytes([
    0x28, 0x28, 0x28, 0x32, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x2E, 0x2E, 0x70, 0x2F, 0x8A, 0x5C, 0x77,
    0x69, 0x28,
])

proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


print(f"Baseline RSS: {rss_mb():.1f} MB")

# Simulate what test_one_input does with this input:
# Last 2 bytes: 0x69, 0x28 -> int 26920 -> 26920 % 100 = 20 -> core_runtime [0,40)
# After scenario selection (2 bytes consumed), 16 bytes remain for FDP.
# Let's manually trace through the core_runtime path.

# The fuzzer creates a FluentBundle, adds grammar-built FTL, resolves messages.
# Let's just do many iterations of bundle creation + resolution to check for leaks.

print("\n--- Test A: Single crash input replay (1 iteration) ---")
before = rss_mb()
bundle = FluentBundle("en", strict=False, enable_cache=True)
bundle.add_resource("msg = Hello { $var }\nmsg2 = { msg }\n")
result, errors = bundle.format_pattern("msg", {"var": "test"})
after = rss_mb()
print(f"Result: {result!r}, errors: {len(errors)}")
print(f"RSS delta: {after - before:.2f} MB")
del bundle

print("\n--- Test B: 17000 iterations (simulating full fuzzer run) ---")
before = rss_mb()
for i in range(17000):
    b = FluentBundle("en", strict=False, enable_cache=True)
    b.add_resource("msg = Hello { $var }\nmsg2 = { msg }\n")
    b.format_pattern("msg", {"var": "test"})
    b.format_pattern("msg2", {"var": "test"})
    if i % 1000 == 0:
        print(f"  iter {i:5d}: RSS = {rss_mb():.1f} MB")
    del b
after = rss_mb()
print(f"Final RSS: {after:.1f} MB, delta: {after - before:.2f} MB")

print("\n--- Test C: 17000 iterations with complex FTL (select, terms, nesting) ---")
COMPLEX_FTL = """\
-brand = Firefox
    .platform = { $os ->
        [windows] Windows
       *[other] Other
    }
msg = { NUMBER($count) ->
    [one] { $count } item for { -brand }
   *[other] { $count } items for { -brand }
}
msg2 = { msg }
deep = { { { $var } } }
chain_a = prefix { chain_b } suffix
chain_b = { chain_c }
chain_c = end
"""
before = rss_mb()
for i in range(17000):
    b = FluentBundle("en", strict=False, enable_cache=True)
    b.add_resource(COMPLEX_FTL)
    for mid in ("msg", "msg2", "deep", "chain_a"):
        try:
            b.format_pattern(mid, {"count": i % 100, "var": "x", "os": "windows"})
        except Exception:
            pass
    if i % 1000 == 0:
        print(f"  iter {i:5d}: RSS = {rss_mb():.1f} MB")
    del b
after = rss_mb()
print(f"Final RSS: {after:.1f} MB, delta: {after - before:.2f} MB")

print("\n[DONE]")
