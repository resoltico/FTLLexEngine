#!/usr/bin/env python3
"""Reproduction 7: Find the EXACT reference cycle chain.

AST nodes are frozen+slots with no parent pointers. So what forms the cycle?
Use gc.get_referrers() to trace cycle paths.
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


# Clean slate
gc.collect()
gc.disable()

ftl = build_laughs_ftl(10)
b = FluentBundle("en", strict=False)
b.add_resource(ftl)
try:
    b.format_pattern("m0", {})
except (RecursionError, MemoryError, FrozenFluentError):
    pass

# Get a snapshot of what the bundle holds
print("=== FluentBundle referents ===")
for attr in sorted(dir(b)):
    if attr.startswith("_") and not attr.startswith("__"):
        val = getattr(b, attr, None)
        if val is not None and not callable(val):
            print(f"  {attr}: {type(val).__name__}")

del b

# Now collect and see what was cyclic
unreachable = gc.collect()
print(f"\nCollected {unreachable} unreachable objects")

# Try with a SIMPLE message (no Billion Laughs)
gc.collect()
gc.disable()
b2 = FluentBundle("en", strict=False)
b2.add_resource("msg = Hello\n")
b2.format_pattern("msg", {})
del b2
unreachable2 = gc.collect()
print(f"Simple message: collected {unreachable2} unreachable objects")

# Try bundle creation ONLY (no add_resource, no format_pattern)
gc.collect()
gc.disable()
b3 = FluentBundle("en", strict=False)
del b3
unreachable3 = gc.collect()
print(f"Empty bundle: collected {unreachable3} unreachable objects")

# Try bundle + add_resource ONLY (no format_pattern)
gc.collect()
gc.disable()
b4 = FluentBundle("en", strict=False)
b4.add_resource("msg = Hello\n")
del b4
unreachable4 = gc.collect()
print(f"Bundle + add_resource only: collected {unreachable4} unreachable objects")

# Try bundle + format_pattern with NO cache
gc.collect()
gc.disable()
b5 = FluentBundle("en", strict=False, enable_cache=False)
b5.add_resource("msg = Hello\n")
b5.format_pattern("msg", {})
del b5
unreachable5 = gc.collect()
print(f"No cache, format: collected {unreachable5} unreachable objects")

# Try bundle + format_pattern WITH cache
gc.collect()
gc.disable()
b6 = FluentBundle("en", strict=False, enable_cache=True)
b6.add_resource("msg = Hello\n")
b6.format_pattern("msg", {})
del b6
unreachable6 = gc.collect()
print(f"With cache, format: collected {unreachable6} unreachable objects")

# Now use gc.DEBUG_SAVEALL to inspect the actual objects for the simple case
gc.collect()
gc.set_debug(gc.DEBUG_SAVEALL)
gc.garbage.clear()
gc.disable()

b7 = FluentBundle("en", strict=False)
b7.add_resource("msg = Hello\n")
b7.format_pattern("msg", {})
del b7
gc.enable()
gc.collect()
gc.set_debug(0)

print(f"\n=== Simple message cycle objects ({len(gc.garbage)}) ===")
type_counts: dict[str, int] = {}
for obj in gc.garbage:
    t = type(obj).__qualname__
    type_counts[t] = type_counts.get(t, 0) + 1
for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {t}: {count}")

# Show the actual objects for small count
if len(gc.garbage) < 50:
    print("\n=== Detailed cycle objects ===")
    for i, obj in enumerate(gc.garbage):
        r = repr(obj)[:120]
        print(f"  [{i}] {type(obj).__qualname__}: {r}")

gc.garbage.clear()

# Now: the RWLock - is it the cycle source?
print("\n=== Testing RWLock isolation ===")
from ftllexengine.runtime.lock import RWLock

gc.collect()
gc.disable()
lock = RWLock()
del lock
unreachable_lock = gc.collect()
print(f"RWLock only: collected {unreachable_lock} unreachable objects")

# IntegrityCache?
gc.collect()
gc.disable()
from ftllexengine.runtime.cache import IntegrityCache

cache = IntegrityCache()
del cache
unreachable_cache = gc.collect()
print(f"IntegrityCache only: collected {unreachable_cache} unreachable objects")

# FluentParserV1?
gc.collect()
gc.disable()
from ftllexengine.syntax.parser import FluentParserV1

parser = FluentParserV1()
del parser
unreachable_parser = gc.collect()
print(f"FluentParserV1 only: collected {unreachable_parser} unreachable objects")

print("\n[DONE]")
