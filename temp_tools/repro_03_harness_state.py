#!/usr/bin/env python3
"""Reproduction 3: Test whether the fuzzer harness state accumulates memory.

Simulates the full test_one_input code path (without Atheris) using
random bytes, measuring RSS every 1000 iterations to detect harness-level leaks.
Key suspects: _state.seed_corpus, _state.slowest_operations, error_counts dict.
"""
import gc
import hashlib
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field

import psutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ftllexengine.runtime.bundle import FluentBundle

proc = psutil.Process(os.getpid())


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


# Simulate the harness state that accumulates
@dataclass
class SimState:
    iterations: int = 0
    performance_history: deque = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque = field(default_factory=lambda: deque(maxlen=1000))
    scenario_coverage: dict = field(default_factory=dict)
    error_counts: dict = field(default_factory=dict)
    slowest_operations: list = field(default_factory=list)
    seed_corpus: dict = field(default_factory=dict)  # This is the suspect
    seed_corpus_max_size: int = 500


state = SimState()

ITERATIONS = 17000

print(f"Simulating {ITERATIONS} iterations of harness state accumulation...")
print(f"Baseline RSS: {rss_mb():.1f} MB\n")

for i in range(ITERATIONS):
    data = random.randbytes(random.randint(4, 64))
    start = time.perf_counter()

    # Simulate core_runtime path
    try:
        b = FluentBundle("en", strict=False, enable_cache=True)
        b.add_resource("msg = Hello { $var }\nmsg2 = { msg }\n")
        b.format_pattern("msg", {"var": "test"})
        b.format_pattern("msg2", {"var": "test"})
    except Exception:
        pass

    elapsed_ms = (time.perf_counter() - start) * 1000
    state.performance_history.append(elapsed_ms)
    state.iterations += 1

    # Simulate seed corpus accumulation (the likely memory hog)
    is_interesting = elapsed_ms > 50.0 or random.random() < 0.15
    if is_interesting:
        h = hashlib.sha256(data).hexdigest()[:16]
        if h not in state.seed_corpus:
            if len(state.seed_corpus) >= state.seed_corpus_max_size:
                oldest = next(iter(state.seed_corpus))
                del state.seed_corpus[oldest]
            state.seed_corpus[h] = data

    # Simulate error_counts accumulation
    if random.random() < 0.3:
        etype = f"SomeError_{random.randint(0, 50)}"
        state.error_counts[etype] = state.error_counts.get(etype, 0) + 1

    # Memory tracking every 100
    if i % 100 == 0:
        state.memory_history.append(rss_mb())

    if i % 1000 == 0:
        print(
            f"  iter {i:5d}: RSS = {rss_mb():.1f} MB, "
            f"corpus = {len(state.seed_corpus)}, "
            f"errors = {len(state.error_counts)}"
        )

gc.collect()
print(f"\nFinal RSS: {rss_mb():.1f} MB")
print(f"Corpus size: {len(state.seed_corpus)}")
print(f"Error types: {len(state.error_counts)}")
print("[DONE]")
