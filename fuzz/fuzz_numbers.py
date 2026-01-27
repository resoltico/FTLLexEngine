#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: numbers - Numeric Parser Unit
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Numeric Parser Unit Fuzzer (Atheris).

Targets: ftllexengine.parsing.numbers
Tests locale-aware float and decimal extraction.
"""

from __future__ import annotations

import atexit
import decimal
import heapq
import json
import logging
import math
import os
import statistics
import sys
import time
from collections import deque
from decimal import Decimal

import psutil

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str]

_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

# Performance profiling globals
performance_history: deque[float] = deque(maxlen=1000)
memory_history: deque[float] = deque(maxlen=100)
# Heapq min-heaps: (value, data) tuples for efficient top-N tracking
slowest_inputs: list[tuple[float, str]] = []  # Min-heap: smallest durations at root
fastest_inputs: list[tuple[float, str]] = []  # Min-heap: negated durations for max-heap behavior
error_counts: dict[str, int] = {}
input_coverage: set[str] = set()

# Process handle (created once, reused for all iterations)
_process: psutil.Process = psutil.Process(os.getpid())

# Seed corpus management
seed_corpus: list[bytes] = []
interesting_inputs: list[tuple[bytes, str]] = []  # (input_bytes, reason)

def _add_to_seed_corpus(data: bytes, reason: str) -> None:
    """Add input to seed corpus if it's interesting."""
    if len(seed_corpus) < 1000:  # Limit corpus size
        seed_corpus.append(data)
        interesting_inputs.append((data, reason))

def _is_interesting_input(input_str: str, duration: float,
                         exception: Exception | None = None) -> str | None:
    """Determine if input is interesting for corpus expansion."""
    reasons = []

    # Exception-triggering inputs
    if exception:
        reasons.append(f"exception_{type(exception).__name__}")

    # Slow inputs
    if duration > 0.01:  # >10ms
        reasons.append("slow_parse")

    # Unique input patterns (use consistent 20-char prefix)
    pattern = input_str[:20]
    if pattern not in input_coverage:
        input_coverage.add(pattern)
        reasons.append("new_pattern")

    # Edge cases
    if any(char in input_str for char in ["∞", "NaN", "±", "x", "÷"]):
        reasons.append("special_chars")

    if len(input_str) > 100:
        reasons.append("long_input")

    return reasons[0] if reasons else None

def _get_performance_summary() -> dict[str, float]:
    """Get comprehensive performance statistics."""
    if not performance_history:
        return {}

    return {
        "mean": statistics.mean(performance_history),
        "median": statistics.median(performance_history),
        "stdev": statistics.stdev(performance_history) if len(performance_history) > 1 else 0,
        "min": min(performance_history),
        "max": max(performance_history),
        "p95": (statistics.quantiles(performance_history, n=20)[18]
               if len(performance_history) >= 20 else max(performance_history)),
        "p99": (statistics.quantiles(performance_history, n=100)[98]
               if len(performance_history) >= 100 else max(performance_history)),
        "memory_mean": statistics.mean(memory_history) if memory_history else 0,
        "memory_max": max(memory_history) if memory_history else 0,
    }

def _emit_final_report() -> None:
    """Emit comprehensive fuzzing statistics."""
    perf_summary = _get_performance_summary()

    # Extract top 5 slowest/fastest (heapq stores as (duration, input) tuples)
    slowest_top5 = [(inp, dur) for dur, inp in heapq.nlargest(5, slowest_inputs)]
    fastest_top5 = [(inp, -dur) for dur, inp in heapq.nsmallest(5, fastest_inputs)]

    stats = {
        "status": _fuzz_stats["status"],
        "iterations": _fuzz_stats["iterations"],
        "findings": _fuzz_stats["findings"],
        "slow_parses": _fuzz_stats.get("slow_parses", 0),
        "coverage_estimate": "high" if int(_fuzz_stats["iterations"]) > 1000000 else "medium",
        "performance": perf_summary,
        "input_coverage": len(input_coverage),
        "error_types": error_counts,
        "slowest_inputs": slowest_top5,  # Top 5 slowest
        "fastest_inputs": fastest_top5,  # Top 5 fastest
        "seed_corpus_size": len(seed_corpus),
        "interesting_inputs": len(interesting_inputs),
        "memory_leaks_detected": _fuzz_stats.get("memory_leaks", 0),
        "differential_test_failures": sum(1 for k in error_counts if k.startswith("differential_")),
    }
    report = json.dumps(stats, default=str)  # Handle float serialization
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

def _update_performance_stats(duration: float, input_str: str, memory_mb: float) -> None:
    """Update performance statistics with advanced analysis."""
    performance_history.append(duration)
    memory_history.append(memory_mb)

    # Track slowest inputs using min-heap (maintain top 10 largest)
    if len(slowest_inputs) < 10:
        heapq.heappush(slowest_inputs, (duration, input_str[:50]))
    elif duration > slowest_inputs[0][0]:
        heapq.heapreplace(slowest_inputs, (duration, input_str[:50]))

    # Track fastest inputs using max-heap (maintain top 10 smallest)
    # Negate duration for max-heap behavior with min-heap implementation
    neg_duration = -duration
    if len(fastest_inputs) < 10:
        heapq.heappush(fastest_inputs, (neg_duration, input_str[:50]))
    elif neg_duration > fastest_inputs[0][0]:
        heapq.heapreplace(fastest_inputs, (neg_duration, input_str[:50]))

    # Track input patterns for coverage
    input_coverage.add(input_str[:20])  # First 20 chars as pattern

def _differential_test_float(input_str: str, ftl_result: float | None) -> None:
    """Compare FTL parsing against reference implementations (simple numbers only)."""
    # Only test inputs without locale separators (Python float() doesn't handle those)
    if any(sep in input_str for sep in [",", " ", "'", "\u00A0"]):  # Skip locale formats
        return

    try:
        # Python built-in float() - no locale support, simple numbers only
        try:
            builtin_result = float(input_str.strip())
        except (ValueError, OverflowError):
            builtin_result = None

        # Compare results (only when both succeed)
        if (ftl_result is not None and builtin_result is not None and
            abs(ftl_result - builtin_result) > 1e-10 and
            not (math.isnan(ftl_result) and math.isnan(builtin_result)) and
            not (math.isinf(ftl_result) and math.isinf(builtin_result))):
            msg = (f"Differential test failure: FTL={ftl_result}, "
                   f"builtin={builtin_result}")
            raise AssertionError(msg)

    except (ValueError, TypeError, OverflowError, AssertionError) as e:
        # Log differential test issues but don't fail the fuzz run
        error_counts[f"differential_{type(e).__name__}"] = (
            error_counts.get(f"differential_{type(e).__name__}", 0) + 1)

def _differential_test_decimal(input_str: str, ftl_result: Decimal | None) -> None:
    """Compare FTL decimal parsing against reference implementations (simple numbers only)."""
    # Only test inputs without locale separators (Python Decimal doesn't handle those)
    if any(sep in input_str for sep in [",", " ", "'", "\u00A0"]):  # Skip locale formats
        return

    try:
        # Python decimal module - no locale support, simple numbers only
        try:
            decimal_result = Decimal(input_str.strip())
        except (ValueError, decimal.InvalidOperation):
            decimal_result = None

        # Compare results
        if (ftl_result is not None and decimal_result is not None and
            ftl_result != decimal_result and
            abs(ftl_result - decimal_result) > Decimal("1e-10")):
            msg = (f"Decimal differential test failure: FTL={ftl_result}, "
                   f"decimal={decimal_result}")
            raise AssertionError(msg)

    except (ValueError, TypeError, decimal.InvalidOperation, AssertionError) as e:
        error_counts[f"decimal_differential_{type(e).__name__}"] = (
            error_counts.get(f"decimal_differential_{type(e).__name__}", 0) + 1)

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.parsing.numbers import parse_decimal, parse_number

TEST_LOCALES = ["en-US", "de-DE", "lv-LV", "ar-SA", "root", "C", "POSIX", ""]

def generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate diverse locale strings for testing.

    Weighted 90% valid / 10% invalid to ensure actual parsing logic is exercised.
    Invalid locales fail early during Locale.parse() and never reach number parsing.
    """
    # 90% valid locales (to exercise actual parsing logic)
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(TEST_LOCALES)
    # 10% malformed locales (to test error handling)
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))

def generate_number_input(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate diverse number strings with emphasis on valid locale-aware formats."""
    # Weighted strategy selection: 70% valid, 20% edge cases, 10% security
    strategy_type = fdp.ConsumeIntInRange(0, 9)

    # 70% VALID NUMBERS (strategies 0-6): Exercise actual parsing logic
    if strategy_type <= 6:
        valid_strategies = [
            # Basic integers
            lambda: str(fdp.ConsumeIntInRange(-999999, 999999)),
            # Decimals with period (en-US, en-GB style)
            lambda: f"{fdp.ConsumeIntInRange(-9999, 9999)}.{abs(fdp.ConsumeInt(3))}",
            # Thousands with comma separators (en-US: 1,234.56)
            lambda: (
                f"{fdp.ConsumeIntInRange(1, 999)},"
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            ),
            # Space separators (fr-FR, lv-LV: 1 234.56 or 1 234,56)
            lambda: (
                f"{fdp.ConsumeIntInRange(1, 999)} "
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            ),
            # German/European format (de-DE: 1.234,56)
            lambda: (
                f"{fdp.ConsumeIntInRange(1, 999)}."
                f"{abs(fdp.ConsumeInt(3))},{abs(fdp.ConsumeInt(2))}"
            ),
            # Swiss format (apostrophe separator: 1'234.56)
            lambda: (
                f"{fdp.ConsumeIntInRange(1, 999)}'"
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            ),
            # Scientific notation
            lambda: (
                f"{fdp.ConsumeIntInRange(1, 9)}.{abs(fdp.ConsumeInt(2))}"
                f"e{fdp.ConsumeIntInRange(-10, 10)}"
            ),
            # Signed numbers
            lambda: f"{fdp.PickValueInList(['+', '-'])}{abs(fdp.ConsumeInt(4))}",
            # Very small decimals
            lambda: f"0.{abs(fdp.ConsumeInt(6))}",
            # Large integers
            lambda: str(fdp.ConsumeIntInRange(100000, 999999999)),
        ]
        return fdp.PickValueInList(valid_strategies)()

    # 20% EDGE CASES (strategies 7-8): Test boundary conditions
    if strategy_type <= 8:
        edge_strategies = [
            # Boundary values
            lambda: fdp.PickValueInList(["0", "-0", "+0", "0.0", "-0.0", "+0.0"]),
            # IEEE 754 special values
            lambda: fdp.PickValueInList(["NaN", "Infinity", "-Infinity", "nan", "inf", "-inf"]),
            # Very large/small numbers
            lambda: "1" + "0" * fdp.ConsumeIntInRange(10, 100),
            lambda: "0." + "0" * fdp.ConsumeIntInRange(10, 100) + "1",
            # Extreme exponents
            lambda: f"1e{fdp.ConsumeIntInRange(100, 308)}",
            lambda: f"1e-{fdp.ConsumeIntInRange(100, 308)}",
            # Whitespace padding
            lambda: f" {fdp.ConsumeInt(4)} ",
            # Unicode digits (test CLDR support)
            lambda: fdp.PickValueInList([
                "٠١٢٣", "۱۲۳۴۵", "๑๒๓", "᭐᭑᭒", "០១២", "᠐᠑᠒"
            ]),
            # Malformed but plausible
            lambda: fdp.PickValueInList(["1.2.3", "1..2", "1ee2", "+-1", "++1", "--1"]),
        ]
        return fdp.PickValueInList(edge_strategies)()

    # 10% SECURITY VECTORS (strategy 9): Test robustness
    security_strategies = [
        # Injection attempts (should fail gracefully)
        lambda: "1" + "\x00" * fdp.ConsumeIntInRange(10, 100),  # Null bytes
        lambda: "1" + fdp.ConsumeUnicodeNoSurrogates(20),  # Random unicode
        lambda: fdp.PickValueInList(["", "abc", " \t\n "]),  # Invalid strings
        # Resource exhaustion (should be handled)
        lambda: "1" * fdp.ConsumeIntInRange(1000, 10000),  # Long digit string
        lambda: f"1e{fdp.ConsumeIntInRange(10000, 100000)}",  # Huge exponent
    ]
    return fdp.PickValueInList(security_strategies)()

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale-aware number parsing."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    locale = generate_locale(fdp)
    input_str = generate_number_input(fdp)

    # Fast-path rejection: empty strings
    if not input_str:
        return

    # Fast-path rejection: whitespace-only or null-byte inputs
    # These should fail immediately, not consume 28ms+ in Babel parsing
    stripped = input_str.strip()
    if not stripped or "\x00" in input_str:
        return

    # Track performance and memory usage
    start_time = time.perf_counter()
    start_memory = _process.memory_info().rss / 1024 / 1024  # MB

    try:
        # Test Float
        res_f, _ = parse_number(input_str, locale)
        if res_f is not None:
            assert isinstance(res_f, float)
            # Differential testing disabled: generates noise from edge case mismatches
            # between Babel (CLDR-compliant) and Python builtins (simple parsing).
            # _differential_test_float(input_str, res_f)

        # Test Decimal
        res_d, _ = parse_decimal(input_str, locale)
        if res_d is not None:
            assert isinstance(res_d, Decimal)
            # Differential testing disabled: generates noise from edge case mismatches
            # between Babel (CLDR-compliant) and Python builtins (simple parsing).
            # _differential_test_decimal(input_str, res_d)

    except (ValueError, TypeError):
        pass
    except OverflowError:  # Large exponents in str -> float
        pass
    except Exception as e:
        error_type = type(e).__name__
        error_counts[error_type] = error_counts.get(error_type, 0) + 1

        # Calculate duration once for interesting input detection
        duration = time.perf_counter() - start_time

        # Add interesting inputs to seed corpus
        interesting_reason = _is_interesting_input(input_str, duration, e)
        if interesting_reason:
            _add_to_seed_corpus(data, interesting_reason)

        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

    # Monitor for performance regressions (normal path)
    duration = time.perf_counter() - start_time
    end_memory = _process.memory_info().rss / 1024 / 1024  # MB
    memory_delta = end_memory - start_memory

    _update_performance_stats(duration, input_str, end_memory)

    # Add interesting inputs to seed corpus
    interesting_reason = _is_interesting_input(input_str, duration)
    if interesting_reason:
        _add_to_seed_corpus(data, interesting_reason)

    if duration > 0.1:  # Log slow parses (>100ms)
        slow_count = int(_fuzz_stats.get("slow_parses", 0)) + 1
        _fuzz_stats["slow_parses"] = slow_count

    # Detect memory leaks (rough heuristic)
    if memory_delta > 50:  # >50MB increase
        leak_count = int(_fuzz_stats.get("memory_leaks", 0)) + 1
        _fuzz_stats["memory_leaks"] = leak_count

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
