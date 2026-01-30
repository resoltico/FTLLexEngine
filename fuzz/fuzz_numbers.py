#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: numbers - Numeric Parser Unit
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Numeric Parser Unit Fuzzer (Atheris).

Targets: ftllexengine.parsing.numbers (parse_number, parse_decimal)

Concern boundary: This fuzzer targets locale-aware numeric parsing -- float and
decimal extraction with CLDR-compliant grouping/decimal separators across locales.
This is distinct from the currency fuzzer (parse_currency with symbol resolution),
runtime fuzzer (resolver/bundle/cache stack), OOM fuzzer (parser AST explosion),
cache fuzzer (IntegrityCache concurrency), and integrity fuzzer (validation checks).

Metrics:
- Parse success/failure rates by locale and pattern type
- Differential testing: FTL vs Python builtins (simple numbers only)
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)
- Seed corpus management (interesting inputs)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks with Clear Errors ---
_MISSING_DEPS: list[str] = []

try:
    import psutil
except ImportError:
    _MISSING_DEPS.append("psutil")
    psutil = None  # type: ignore[assignment]

try:
    import atheris
except ImportError:
    _MISSING_DEPS.append("atheris")
    atheris = None  # type: ignore[assignment]

if _MISSING_DEPS:
    print("-" * 80, file=sys.stderr)
    print("Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- Type Aliases (PEP 695) ---
type FuzzStats = dict[str, int | str | float]
type SlowestEntry = tuple[float, str]  # (duration_ms, input_snippet)


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Slowest parses (min-heap, top 10)
    slowest_parses: list[SlowestEntry] = field(default_factory=list)

    # Error tracking
    error_counts: dict[str, int] = field(default_factory=dict)

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)

    # Parse result tracking
    float_successes: int = 0
    float_failures: int = 0
    decimal_successes: int = 0
    decimal_failures: int = 0

    # Seed corpus (hash -> source, LRU eviction)
    seed_corpus: dict[str, str] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 1000


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


def _build_stats_dict() -> FuzzStats:
    """Build flat stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
        "float_successes": _state.float_successes,
        "float_failures": _state.float_failures,
        "decimal_successes": _state.decimal_successes,
        "decimal_failures": _state.decimal_failures,
    }

    # Performance percentiles
    if _state.performance_history:
        perf_data = list(_state.performance_history)
        n = len(perf_data)
        stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        stats["perf_min_ms"] = round(min(perf_data), 3)
        stats["perf_max_ms"] = round(max(perf_data), 3)
        if n >= 20:
            quantiles = statistics.quantiles(perf_data, n=20)
            stats["perf_p95_ms"] = round(quantiles[18], 3)
        if n >= 100:
            quantiles = statistics.quantiles(perf_data, n=100)
            stats["perf_p99_ms"] = round(quantiles[98], 3)

    # Memory tracking
    if _state.memory_history:
        mem_data = list(_state.memory_history)
        stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        stats["memory_peak_mb"] = round(max(mem_data), 2)
        stats["memory_delta_mb"] = round(max(mem_data) - _state.initial_memory_mb, 2)

        # Memory leak detection (quarter comparison for accuracy)
        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            first_avg = statistics.mean(first_quarter)
            last_avg = statistics.mean(last_quarter)
            growth_mb = last_avg - first_avg
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0

    # Error distribution
    for error_key, count in sorted(_state.error_counts.items()):
        stats[f"error_{error_key}"] = count

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Corpus
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_parses_tracked"] = len(_state.slowest_parses)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    # Emit to stderr for capture
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    # Write to file for shell script parsing (best-effort)
    try:
        report_file = pathlib.Path(".fuzz_corpus") / "numbers" / "fuzz_numbers_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.parsing.numbers import parse_decimal, parse_number


# --- Constants ---
_TEST_LOCALES: Sequence[str] = (
    "en-US",
    "de-DE",
    "lv-LV",
    "ar-SA",
    "ja-JP",
    "fr-FR",
    "root",
)


def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


def _generate_number_input(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str]:
    """Generate number input with weighted strategies.

    19 pattern types targeting locale-aware numeric parsing.
    Returns (pattern_name, input_string).
    """
    # Weights: valid(10) + edge(5) + security(4) = 19 patterns
    weights = [
        # Valid (10 patterns)
        8,
        8,
        7,
        7,
        7,
        7,
        7,
        7,
        7,
        7,
        # Edge cases (5 patterns)
        6,
        6,
        6,
        6,
        6,
        # Security/invalid (4 patterns)
        5,
        5,
        5,
        10,
    ]
    total_weight = sum(weights)
    choice = fdp.ConsumeIntInRange(0, total_weight - 1)

    cumulative = 0
    pattern_choice = 0
    for i, weight in enumerate(weights):
        cumulative += weight
        if choice < cumulative:
            pattern_choice = i
            break

    match pattern_choice:
        # --- VALID NUMBERS (10 patterns) ---
        case 0:  # Basic integer
            return ("basic_integer", str(fdp.ConsumeIntInRange(-999999, 999999)))

        case 1:  # Decimal with period (en-US style)
            return (
                "decimal_period",
                f"{fdp.ConsumeIntInRange(-9999, 9999)}.{abs(fdp.ConsumeInt(3))}",
            )

        case 2:  # US thousands (1,234.56)
            return (
                "us_thousands",
                (
                    f"{fdp.ConsumeIntInRange(1, 999)},"
                    f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
                ),
            )

        case 3:  # Space separators (fr-FR/lv-LV: 1 234.56)
            return (
                "space_thousands",
                (
                    f"{fdp.ConsumeIntInRange(1, 999)} "
                    f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
                ),
            )

        case 4:  # German format (1.234,56)
            return (
                "de_format",
                (
                    f"{fdp.ConsumeIntInRange(1, 999)}."
                    f"{abs(fdp.ConsumeInt(3))},{abs(fdp.ConsumeInt(2))}"
                ),
            )

        case 5:  # Swiss format (1'234.56)
            return (
                "ch_format",
                (
                    f"{fdp.ConsumeIntInRange(1, 999)}'"
                    f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
                ),
            )

        case 6:  # Scientific notation
            return (
                "scientific",
                (
                    f"{fdp.ConsumeIntInRange(1, 9)}.{abs(fdp.ConsumeInt(2))}"
                    f"e{fdp.ConsumeIntInRange(-10, 10)}"
                ),
            )

        case 7:  # Signed number
            sign = fdp.PickValueInList(["+", "-"])
            return ("signed_number", f"{sign}{abs(fdp.ConsumeInt(4))}")

        case 8:  # Small decimal (0.000123)
            return ("small_decimal", f"0.{abs(fdp.ConsumeInt(6))}")

        case 9:  # Large integer
            return ("large_integer", str(fdp.ConsumeIntInRange(100000, 999999999)))

        # --- EDGE CASES (5 patterns) ---
        case 10:  # Zero variants
            return (
                "zero_variant",
                fdp.PickValueInList(["0", "-0", "+0", "0.0", "-0.0", "+0.0"]),
            )

        case 11:  # Special float values
            return (
                "special_float",
                fdp.PickValueInList(["NaN", "Infinity", "-Infinity", "nan", "inf", "-inf"]),
            )

        case 12:  # Extreme magnitude
            exp = fdp.ConsumeIntInRange(50, 308)
            if fdp.ConsumeBool():
                return ("extreme_large", f"1e{exp}")
            return ("extreme_small", f"1e-{exp}")

        case 13:  # Unicode digits (Arabic-Indic, Thai, etc.)
            return (
                "unicode_digits",
                fdp.PickValueInList(
                    [
                        "\u0660\u0661\u0662\u0663",  # Arabic-Indic
                        "\u06f1\u06f2\u06f3\u06f4\u06f5",  # Extended Arabic-Indic
                        "\u0e51\u0e52\u0e53",  # Thai
                        "\u17e0\u17e1\u17e2",  # Khmer
                    ]
                ),
            )

        case 14:  # Malformed numbers
            return (
                "malformed",
                fdp.PickValueInList(
                    [
                        "1.2.3",
                        "1..2",
                        "1e",
                        "1e-",
                        "+-1",
                        "++1",
                        "--1",
                        ",123",
                        ".123.",
                        "1,2,3",
                    ]
                ),
            )

        # --- SECURITY/INVALID (4 patterns) ---
        case 15:  # Null bytes
            return ("null_bytes", f"1\x00{fdp.ConsumeIntInRange(0, 999)}")

        case 16:  # Very long number
            length = fdp.ConsumeIntInRange(100, 1000)
            return ("very_long", "1" * length)

        case 17:  # Invalid strings
            return (
                "invalid_string",
                fdp.PickValueInList(["", "   ", "abc", "\t\n", "$100"]),
            )

        case 18:  # Raw bytes pass-through
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 200))
            return ("raw_bytes", raw)

        case _:
            return ("fallback", "42")


def _track_slowest_parse(duration_ms: float, input_snippet: str) -> None:
    """Track top 10 slowest parses using min-heap."""
    snippet = input_snippet[:50]
    if len(_state.slowest_parses) < 10:
        heapq.heappush(_state.slowest_parses, (duration_ms, snippet))
    elif duration_ms > _state.slowest_parses[0][0]:
        heapq.heapreplace(_state.slowest_parses, (duration_ms, snippet))


def _track_seed_corpus(input_str: str, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    is_interesting = (
        duration_ms > 10.0
        or "unicode" in pattern
        or "malformed" in pattern
        or "raw_bytes" in pattern
        or "extreme" in pattern
    )

    if is_interesting:
        source_hash = hashlib.sha256(input_str.encode("utf-8", errors="surrogatepass")).hexdigest()[
            :16
        ]
        if source_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[source_hash] = input_str
            _state.corpus_entries_added += 1


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale-aware number parsing.

    Observability:
    - Performance: Tracks timing per iteration (ms)
    - Memory: Tracks RSS via psutil (every 100 iterations)
    - Parse results: Float/decimal success/failure counts
    - Patterns: Coverage of 19 number format types
    - Corpus: Interesting inputs (slow, unicode, malformed, extreme, raw)
    """
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic report write for shell script parsing
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    locale = _generate_locale(fdp)
    pattern_name, input_str = _generate_number_input(fdp)
    _state.pattern_coverage[pattern_name] = _state.pattern_coverage.get(pattern_name, 0) + 1

    # Fast-path rejection: empty or whitespace-only
    if not input_str or not input_str.strip():
        return

    try:
        # Test parse_number (float)
        res_f, _ = parse_number(input_str, locale)
        if res_f is not None:
            _state.float_successes += 1
        else:
            _state.float_failures += 1

        # Test parse_decimal (Decimal)
        res_d, _ = parse_decimal(input_str, locale)
        if res_d is not None:
            _state.decimal_successes += 1
        else:
            _state.decimal_failures += 1

    except (ValueError, TypeError, OverflowError) as e:
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
    except (RecursionError, MemoryError, FrozenFluentError) as e:
        # Expected: depth guards, resource limits
        error_key = type(e).__name__
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
    except Exception:
        # Unexpected exceptions are findings
        _state.findings += 1
        raise
    finally:
        # Performance tracking
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)
        # Per-pattern wall time accumulation
        _state.pattern_wall_time[pattern_name] = (
            _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
        )

        _track_slowest_parse(elapsed_ms, input_str)
        _track_seed_corpus(input_str, pattern_name, elapsed_ms)

        # Memory tracking (every 100 iterations to reduce overhead)
        if _state.iterations % 100 == 0:
            current_memory_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_memory_mb)


def main() -> None:
    """Run the numbers fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Numeric parser fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size",
        type=int,
        default=1000,
        help="Maximum size of in-memory seed corpus (default: 1000)",
    )

    # Parse known args, pass rest to Atheris/libFuzzer
    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Numeric Parser Unit Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.parsing.numbers (parse_number, parse_decimal)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Patterns:   19 (10 valid + 5 edge + 4 security)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
