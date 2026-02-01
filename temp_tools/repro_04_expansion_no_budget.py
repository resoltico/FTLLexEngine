#!/usr/bin/env python3
"""Reproduction 4: Test expansion budget = None (no limit).

The _test_expansion_budget function picks budget from [100, 1000, 10000, None].
When None, max_expansion_size is NOT passed to FluentBundle, meaning the default
applies. But what IS the default? And does the Billion Laughs pattern with
depth=20 and no budget cause unbounded memory growth?

This is the most likely OOM root cause.
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


# First: what is the default max_expansion_size?
b = FluentBundle("en", strict=False)
print(f"Default max_expansion_size: {getattr(b, 'max_expansion_size', 'NOT FOUND')}")
print(f"Default _max_expansion_size: {getattr(b, '_max_expansion_size', 'NOT FOUND')}")
# Check all attributes
for attr in sorted(dir(b)):
    if "expan" in attr.lower() or "budget" in attr.lower() or "max" in attr.lower():
        print(f"  bundle.{attr} = {getattr(b, attr, '?')}")
del b

print(f"\nBaseline RSS: {rss_mb():.1f} MB")

# Test: Billion Laughs at various depths WITH and WITHOUT budget
print("\n--- Billion Laughs expansion at various depths ---")
for depth in [5, 10, 15, 20]:
    for budget in [100, 1000, 10000, None]:
        gc.collect()
        before = rss_mb()
        tracemalloc.start()
        try:
            kwargs = {"strict": False}
            if budget is not None:
                kwargs["max_expansion_size"] = budget
            b = FluentBundle("en", **kwargs)
            parts = []
            for d in range(depth):
                parts.append(f"m{d} = {{ m{d + 1} }}{{ m{d + 1} }}\n")
            parts.append(f"m{depth} = payload\n")
            ftl = "\n".join(parts)
            b.add_resource(ftl)
            result, errors = b.format_pattern("m0", {})
            output_len = len(str(result)) if result else 0
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            after = rss_mb()
            print(
                f"  depth={depth:2d}, budget={budget!s:>5s}: "
                f"output={output_len:>10d} chars, "
                f"peak_alloc={peak / 1024 / 1024:.1f} MB, "
                f"RSS delta={after - before:+.1f} MB"
            )
        except (RecursionError, MemoryError, FrozenFluentError, ValueError) as e:
            if tracemalloc.is_tracing():
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            else:
                peak = 0
            after = rss_mb()
            print(
                f"  depth={depth:2d}, budget={budget!s:>5s}: "
                f"CAUGHT {type(e).__name__}, "
                f"peak_alloc={peak / 1024 / 1024:.1f} MB, "
                f"RSS delta={after - before:+.1f} MB"
            )

# Now: what happens with repeated expansion budget=None at depth=20?
print("\n--- Repeated Billion Laughs (budget=None, depth=20) x 100 ---")
before = rss_mb()
for i in range(100):
    try:
        b = FluentBundle("en", strict=False)
        parts = []
        for d in range(20):
            parts.append(f"m{d} = {{ m{d + 1} }}{{ m{d + 1} }}\n")
        parts.append("m20 = payload\n")
        b.add_resource("\n".join(parts))
        b.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass
    if i % 10 == 0:
        print(f"  iter {i:3d}: RSS = {rss_mb():.1f} MB")
    del b
gc.collect()
after = rss_mb()
print(f"  Final: RSS = {after:.1f} MB, delta = {after - before:+.1f} MB")

print("\n[DONE]")
