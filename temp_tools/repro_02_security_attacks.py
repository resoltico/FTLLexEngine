#!/usr/bin/env python3
"""Reproduction 2: Isolate memory from each security attack vector.

Runs each attack type 2000 times and measures RSS growth.
This identifies if any specific attack vector leaks memory.
"""
import gc
import os
import sys

import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ftllexengine.diagnostics.errors import FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle

proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


ITERATIONS = 2000


def test_deep_recursion() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            b = FluentBundle("en", strict=False)
            depth = 50 + (i % 150)
            ftl = "msg = " + "{ " * depth + "$var" + " }" * depth + "\n"
            b.add_resource(ftl)
            b.format_pattern("msg", {"var": "test"})
        except (RecursionError, MemoryError, FrozenFluentError, ValueError):
            pass
        del b
    gc.collect()
    return rss_mb() - before


def test_memory_exhaustion_large_string() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            b = FluentBundle("en", strict=False)
            size = 10000 + (i % 90000)
            b.add_resource(f"msg = {'x' * size}\n")
            b.format_pattern("msg", {"var": "test"})
        except (MemoryError, ValueError, FrozenFluentError):
            pass
        del b
    gc.collect()
    return rss_mb() - before


def test_memory_exhaustion_many_variants() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            b = FluentBundle("en", strict=False)
            n = 50 + (i % 150)
            variants = "\n".join(
                f"    [{'*' if j == 0 else ''}v{j}] val{j}" for j in range(n)
            )
            b.add_resource(f"msg = {{ $var ->\n{variants}\n}}\n")
            b.format_pattern("msg", {"var": "test"})
        except (MemoryError, ValueError, FrozenFluentError):
            pass
        del b
    gc.collect()
    return rss_mb() - before


def test_expansion_budget() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            budget = [100, 1000, 10000, None][i % 4]
            kwargs = {"strict": False}
            if budget is not None:
                kwargs["max_expansion_size"] = budget
            b = FluentBundle("en", **kwargs)
            depth = 5 + (i % 15)
            parts = []
            for d in range(depth):
                parts.append(f"m{d} = {{ m{d + 1} }}{{ m{d + 1} }}\n")
            parts.append(f"m{depth} = payload\n")
            b.add_resource("\n".join(parts))
            b.format_pattern("m0", {})
        except (RecursionError, MemoryError, FrozenFluentError, ValueError):
            pass
    gc.collect()
    return rss_mb() - before


def test_dag_expansion() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            b = FluentBundle("en", enable_cache=True, strict=False)
            b.add_resource("msg = Hello { $name }\n")
            depth = 10 + (i % 20)
            dag = ["leaf"]
            for _ in range(depth):
                dag = [dag, dag]
            try:
                b.format_pattern("msg", {"name": dag})
            except Exception:
                pass
            b.format_pattern("msg", {"name": "safe"})
        except Exception:
            pass
    gc.collect()
    return rss_mb() - before


def test_recursive_function() -> float:
    before = rss_mb()
    for i in range(ITERATIONS):
        try:
            b = FluentBundle("en", strict=False)
            call_depth = 1 + (i % 10)
            counter = {"n": 0}

            def recursive_func(*_a, _b=b, _c=counter, _d=call_depth, **_k):
                _c["n"] += 1
                if _c["n"] < _d:
                    result, _ = _b.format_pattern("recurse", {})
                    return str(result)
                return "base"

            b.add_function("RECURSE_FN", recursive_func)
            b.add_resource("recurse = { RECURSE_FN() }\nmsg = { RECURSE_FN() }\n")
            b.format_pattern("msg", {})
        except Exception:
            pass
    gc.collect()
    return rss_mb() - before


attacks = [
    ("deep_recursion", test_deep_recursion),
    ("large_string", test_memory_exhaustion_large_string),
    ("many_variants", test_memory_exhaustion_many_variants),
    ("expansion_budget", test_expansion_budget),
    ("dag_expansion", test_dag_expansion),
    ("recursive_function", test_recursive_function),
]

print(f"Running {ITERATIONS} iterations per attack vector...")
print(f"Baseline RSS: {rss_mb():.1f} MB\n")

for name, func in attacks:
    gc.collect()
    delta = func()
    print(f"  {name:25s}: RSS delta = {delta:+.1f} MB")

print(f"\nFinal RSS: {rss_mb():.1f} MB")
print("[DONE]")
