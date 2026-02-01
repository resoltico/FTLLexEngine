#!/usr/bin/env python3
"""Reproduction 6: Find the reference cycles causing memory accumulation.

Confirmed: Billion Laughs + no gc.collect() = RSS growth.
gc.collect() fixes it. So there are reference cycles.
Find them.
"""
import gc
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ftllexengine.diagnostics.errors import FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle


def build_laughs_ftl(depth: int) -> str:
    parts = []
    for d in range(depth):
        parts.append(f"m{d} = {{ m{d + 1} }}{{ m{d + 1} }}\n")
    parts.append(f"m{depth} = payload\n")
    return "\n".join(parts)


# Collect all existing garbage first
gc.collect()
gc.set_debug(gc.DEBUG_SAVEALL)

# Clear any pre-existing garbage
gc.garbage.clear()

# Create one Billion Laughs bundle and resolve
ftl = build_laughs_ftl(15)
b = FluentBundle("en", strict=False)
b.add_resource(ftl)
try:
    b.format_pattern("m0", {})
except (RecursionError, MemoryError, FrozenFluentError):
    pass

# Delete bundle, then collect to find uncollectable cycles
del b
unreachable = gc.collect()
print(f"gc.collect() found {unreachable} unreachable objects")
print(f"gc.garbage has {len(gc.garbage)} uncollectable objects")

# Show types of garbage objects
type_counts: dict[str, int] = {}
for obj in gc.garbage[:200]:
    t = type(obj).__qualname__
    type_counts[t] = type_counts.get(t, 0) + 1

print("\nTypes of uncollectable objects:")
for t, count in sorted(type_counts.items(), key=lambda x: -x[1])[:20]:
    print(f"  {t}: {count}")

gc.set_debug(0)
gc.garbage.clear()

# Now: measure how many unreachable objects per iteration WITHOUT gc
print("\n--- Unreachable objects per Billion Laughs iteration ---")
gc.collect()  # clean slate
gc.disable()  # prevent automatic collection

for i in range(5):
    b = FluentBundle("en", strict=False)
    b.add_resource(ftl)
    try:
        b.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError):
        pass
    del b

gc.enable()
unreachable = gc.collect()
print(f"After 5 iterations without gc: {unreachable} unreachable objects collected")
print(f"That's ~{unreachable // 5} objects per iteration")

# What about simple FTL?
gc.collect()
gc.disable()
for i in range(5):
    b = FluentBundle("en", strict=False)
    b.add_resource("msg = Hello { $var }\n")
    b.format_pattern("msg", {"var": "test"})
    del b
gc.enable()
unreachable_simple = gc.collect()
print(f"\nSimple FTL: {unreachable_simple} unreachable objects from 5 iterations")
print(f"That's ~{unreachable_simple // 5} objects per iteration")

# Parse-only
gc.collect()
gc.disable()
for i in range(5):
    b = FluentBundle("en", strict=False)
    b.add_resource(ftl)
    del b
gc.enable()
unreachable_parse = gc.collect()
print(f"\nParse-only (Laughs): {unreachable_parse} unreachable objects from 5 iterations")
print(f"That's ~{unreachable_parse // 5} objects per iteration")

print("\n[DONE]")
