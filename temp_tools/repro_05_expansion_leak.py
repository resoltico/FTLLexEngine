#!/usr/bin/env python3
"""Reproduction 5: Pinpoint the Billion Laughs memory leak.

Confirmed: depth=20, budget=None leaks ~0.15 MB/iter.
Now isolate: is it the resolver, the error objects, the parser, or gc cycles?
"""
import gc
import os
import sys
import tracemalloc

import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ftllexengine.diagnostics.errors import FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle

proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


def build_laughs_ftl(depth: int) -> str:
    parts = []
    for d in range(depth):
        parts.append(f"m{d} = {{ m{d + 1} }}{{ m{d + 1} }}\n")
    parts.append(f"m{depth} = payload\n")
    return "\n".join(parts)


# Test A: Does gc.collect() after each iteration prevent the leak?
print("--- Test A: Billion Laughs depth=20, budget=None, with gc.collect() ---")
before = rss_mb()
ftl = build_laughs_ftl(20)
for i in range(200):
    try:
        b = FluentBundle("en", strict=False)
        b.add_resource(ftl)
        b.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass
    del b
    gc.collect()
    if i % 20 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
after = rss_mb()
print(f"  delta = {after - before:+.1f} MB over 200 iters")

# Test B: Parse-only (no resolve) - is the leak in the parser?
print("\n--- Test B: Parse-only (no format_pattern) ---")
gc.collect()
before = rss_mb()
for i in range(200):
    try:
        b = FluentBundle("en", strict=False)
        b.add_resource(ftl)
        # Do NOT resolve
    except Exception:
        pass
    del b
    if i % 20 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
gc.collect()
after = rss_mb()
print(f"  delta = {after - before:+.1f} MB over 200 iters")

# Test C: Resolve with budget=100 (expansion caught early)
print("\n--- Test C: Billion Laughs depth=20, budget=100 (caught early) ---")
gc.collect()
before = rss_mb()
for i in range(200):
    try:
        b = FluentBundle("en", strict=False, max_expansion_size=100)
        b.add_resource(ftl)
        b.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass
    del b
    if i % 20 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
gc.collect()
after = rss_mb()
print(f"  delta = {after - before:+.1f} MB over 200 iters")

# Test D: tracemalloc snapshot diff for ONE iteration
print("\n--- Test D: tracemalloc top allocations for ONE Billion Laughs resolve ---")
gc.collect()
tracemalloc.start(25)
snap1 = tracemalloc.take_snapshot()

b = FluentBundle("en", strict=False)
b.add_resource(ftl)
try:
    b.format_pattern("m0", {})
except (RecursionError, MemoryError, FrozenFluentError, ValueError):
    pass

snap2 = tracemalloc.take_snapshot()
top_stats = snap2.compare_to(snap1, "lineno")
print("  Top 15 memory allocations:")
for stat in top_stats[:15]:
    print(f"    {stat}")

tracemalloc.stop()
del b

# Test E: What about depth=15 (which had 0.4 MB peak)?
print("\n--- Test E: Billion Laughs depth=15, budget=None x 200 ---")
gc.collect()
before = rss_mb()
ftl15 = build_laughs_ftl(15)
for i in range(200):
    try:
        b = FluentBundle("en", strict=False)
        b.add_resource(ftl15)
        b.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass
    del b
    if i % 20 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
gc.collect()
after = rss_mb()
print(f"  delta = {after - before:+.1f} MB over 200 iters")

# Test F: What about large strings (100K)?
print("\n--- Test F: Large string (100K) x 200 ---")
gc.collect()
before = rss_mb()
for i in range(200):
    try:
        b = FluentBundle("en", strict=False)
        b.add_resource(f"msg = {'x' * 100000}\n")
        b.format_pattern("msg", {})
    except (MemoryError, ValueError, FrozenFluentError):
        pass
    del b
    if i % 20 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
gc.collect()
after = rss_mb()
print(f"  delta = {after - before:+.1f} MB over 200 iters")

print("\n[DONE]")
