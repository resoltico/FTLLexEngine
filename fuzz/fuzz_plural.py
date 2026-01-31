#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: plural - Plural Rule Boundary & CLDR
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Plural Rule Boundary Fuzzer (Atheris).

Targets: ftllexengine.runtime.plural_rules.select_plural_category

Concern boundary: This fuzzer stress-tests CLDR plural category selection
directly. Tests category validity across all number types (int, float, Decimal),
precision-aware v-operand handling, locale fallback chains, deterministic output,
boundary number behavior, and locale cache consistency. Distinct from runtime
fuzzers which exercise plural rules only as a side effect of FluentBundle
formatting.

Metrics:
- Pattern coverage (category_validity, precision_sensitivity, etc.)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Seed corpus management

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
from decimal import Decimal, InvalidOperation
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)

# --- Dependency Checks ---
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
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)


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

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 100


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# Valid CLDR plural categories
VALID_CATEGORIES = frozenset({"zero", "one", "two", "few", "many", "other"})

# High-leverage locales for plural testing
# ar: all 6 categories (zero, one, two, few, many, other) -- most complex
# ru: one, few, many, other -- Slavic pattern
# pl: one, few, many, other -- Polish (different from Russian)
# lv: zero, one, other -- Latvian (decimal rules)
# en: one, other -- simple
# ja: other only -- no plurals
# fr: one, many, other -- French
# ga: one, two, few, many, other -- Irish
# root: other only -- CLDR root fallback
_HIGH_LEVERAGE_LOCALES: tuple[str, ...] = (
    "ar", "ar_SA", "ar_EG",
    "ru", "ru_RU",
    "pl", "pl_PL",
    "lv", "lv_LV",
    "en", "en_US", "en_GB",
    "ja", "ja_JP",
    "fr", "fr_FR",
    "ga", "ga_IE",
    "root",
    "de", "de_DE",
    "zh", "zh_CN",
    "ko", "ko_KR",
    "cs", "cs_CZ",
    "uk", "uk_UA",
    "he", "he_IL",
    "cy", "cy_GB",
)

# CLDR boundary numbers: values where plural category transitions occur
_BOUNDARY_NUMBERS: tuple[int, ...] = (
    0, 1, 2, 3, 4, 5, 6, 10, 11, 12, 19, 20, 21, 100, 101, 102, 1000,
)

# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("category_validity", 15),
    ("precision_sensitivity", 15),
    ("locale_coverage", 12),
    ("locale_fallback", 8),
    ("determinism", 12),
    ("number_type_variety", 10),
    ("boundary_numbers", 12),
    ("cache_consistency", 8),
    ("extreme_inputs", 5),
    ("raw_bytes", 3),
)

# Allowed exceptions from plural operations
ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError, InvalidOperation)


class PluralFuzzError(Exception):
    """Raised when a plural rule invariant is breached."""


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
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

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            growth_mb = statistics.mean(last_quarter) - statistics.mean(first_quarter)
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0
            stats["memory_growth_mb"] = 0.0

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_operations_tracked"] = len(_state.slowest_operations)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    try:
        report_file = pathlib.Path(".fuzz_corpus") / "plural" / "fuzz_plural_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.plural_rules import select_plural_category


def _track_slowest_operation(duration_ms: float, pattern: str, input_data: bytes) -> None:
    """Track top 10 slowest operations using max-heap."""
    input_hash = hashlib.sha256(input_data).hexdigest()[:16]
    entry: InterestingInput = (-duration_ms, pattern, input_hash)

    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, entry)
    elif -duration_ms < _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, entry)


def _track_seed_corpus(input_data: bytes, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs with FIFO eviction."""
    is_interesting = (
        duration_ms > 10.0
        or "extreme" in pattern
        or "fallback" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(input_data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_data
            _state.corpus_entries_added += 1


def _generate_number(fdp: atheris.FuzzedDataProvider) -> int | float | Decimal:
    """Generate a number from fuzzed data (int, float, or Decimal)."""
    num_type = fdp.ConsumeIntInRange(0, 2)
    if num_type == 0:
        return fdp.ConsumeInt(8)
    if num_type == 1:
        return fdp.ConsumeFloat()
    # Decimal from float string
    return Decimal(str(fdp.ConsumeFloat()))


def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick a locale: high-leverage or random."""
    if fdp.ConsumeBool():
        return fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 12))


# --- Pattern Implementations ---

def _pattern_category_validity(fdp: atheris.FuzzedDataProvider) -> None:
    """Every call must return one of the 6 CLDR categories."""
    n = _generate_number(fdp)
    locale = _pick_locale(fdp)
    precision = fdp.ConsumeIntInRange(0, 10) if fdp.ConsumeBool() else None

    category = select_plural_category(n, locale, precision=precision)

    if category not in VALID_CATEGORIES:
        msg = f"Invalid category '{category}' for n={n}, locale={locale}, precision={precision}"
        raise PluralFuzzError(msg)


def _pattern_precision_sensitivity(fdp: atheris.FuzzedDataProvider) -> None:
    """Precision changes CLDR v operand, potentially changing category.

    Key invariant: with and without precision, both results are valid categories.
    Known behavior: en_US with n=1 returns 'one' (precision=None) but 'other' (precision=2).
    """
    n = fdp.ConsumeIntInRange(0, 100)
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))

    # Without precision
    cat_none = select_plural_category(n, locale, precision=None)
    if cat_none not in VALID_CATEGORIES:
        msg = f"Invalid category '{cat_none}' (no precision) for n={n}, locale={locale}"
        raise PluralFuzzError(msg)

    # With precision 0-6
    precision = fdp.ConsumeIntInRange(0, 6)
    cat_prec = select_plural_category(n, locale, precision=precision)
    if cat_prec not in VALID_CATEGORIES:
        msg = f"Invalid category '{cat_prec}' (precision={precision}) for n={n}, locale={locale}"
        raise PluralFuzzError(msg)


def _pattern_locale_coverage(fdp: atheris.FuzzedDataProvider) -> None:
    """Exercise all high-leverage locales with boundary numbers."""
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))
    n = fdp.PickValueInList(list(_BOUNDARY_NUMBERS))
    precision = fdp.ConsumeIntInRange(0, 3) if fdp.ConsumeBool() else None

    category = select_plural_category(n, locale, precision=precision)

    if category not in VALID_CATEGORIES:
        msg = f"Invalid category '{category}' for locale={locale}, n={n}"
        raise PluralFuzzError(msg)


def _pattern_locale_fallback(fdp: atheris.FuzzedDataProvider) -> None:
    """Invalid/unknown locales must fall back gracefully (never crash)."""
    invalid_locales = [
        "",
        "invalid-locale",
        "xx_XX",
        "zzz",
        "\x00\x01\x02",
        "a" * 200,
        "en_US_POSIX_extra_junk",
    ]
    if fdp.ConsumeBool():
        locale = fdp.PickValueInList(invalid_locales)
    else:
        locale = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
    n = fdp.ConsumeIntInRange(0, 100)

    category = select_plural_category(n, locale, precision=None)

    # Must still return a valid category (root fallback returns "other")
    if category not in VALID_CATEGORIES:
        msg = f"Invalid category '{category}' for invalid locale='{locale[:20]}'"
        raise PluralFuzzError(msg)


def _pattern_determinism(fdp: atheris.FuzzedDataProvider) -> None:
    """Same inputs must always return same category."""
    n = _generate_number(fdp)
    locale = _pick_locale(fdp)
    precision = fdp.ConsumeIntInRange(0, 6) if fdp.ConsumeBool() else None

    cat1 = select_plural_category(n, locale, precision=precision)
    cat2 = select_plural_category(n, locale, precision=precision)

    if cat1 != cat2:
        msg = (
            f"Non-deterministic: '{cat1}' != '{cat2}' "
            f"for n={n}, locale={locale}, precision={precision}"
        )
        raise PluralFuzzError(msg)


def _pattern_number_type_variety(fdp: atheris.FuzzedDataProvider) -> None:
    """int, float, and Decimal must all produce valid categories."""
    base_val = fdp.ConsumeIntInRange(0, 1000)
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))

    # Test all three types
    for n in (base_val, float(base_val), Decimal(str(base_val))):
        category = select_plural_category(n, locale, precision=None)
        if category not in VALID_CATEGORIES:
            msg = (
                f"Invalid category '{category}' for "
                f"type={type(n).__name__}, n={n}, locale={locale}"
            )
            raise PluralFuzzError(msg)


def _pattern_boundary_numbers(fdp: atheris.FuzzedDataProvider) -> None:
    """CLDR rule boundary values: 0, 1, 2, 5, 11, 21, 100, 101."""
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))

    for n in _BOUNDARY_NUMBERS:
        category = select_plural_category(n, locale, precision=None)
        if category not in VALID_CATEGORIES:
            msg = f"Invalid category '{category}' for boundary n={n}, locale={locale}"
            raise PluralFuzzError(msg)


def _pattern_cache_consistency(fdp: atheris.FuzzedDataProvider) -> None:
    """LRU-cached get_babel_locale must return consistent results across calls."""
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))
    n = fdp.ConsumeIntInRange(0, 100)
    precision = fdp.ConsumeIntInRange(0, 3) if fdp.ConsumeBool() else None

    # Call multiple times -- cache hit path must match cold path
    results = [select_plural_category(n, locale, precision=precision) for _ in range(5)]

    if len(set(results)) != 1:
        msg = f"Cache inconsistency: {results} for n={n}, locale={locale}"
        raise PluralFuzzError(msg)


def _pattern_extreme_inputs(fdp: atheris.FuzzedDataProvider) -> None:
    """Extreme/pathological numbers: huge, negative, NaN, Inf, high precision."""
    locale = fdp.PickValueInList(list(_HIGH_LEVERAGE_LOCALES))

    extreme_values: list[int | float | Decimal] = [
        fdp.ConsumeInt(8),
        -fdp.ConsumeInt(8),
        float("inf"),
        float("-inf"),
        float("nan"),
        10**18,
        -(10**18),
        Decimal("0.0000000000000001"),
        Decimal("999999999999999999"),
    ]

    val = fdp.PickValueInList(extreme_values)
    precision = fdp.ConsumeIntInRange(0, 20) if fdp.ConsumeBool() else None

    # Must not crash; category may be "other" for edge cases
    category = select_plural_category(val, locale, precision=precision)

    if category not in VALID_CATEGORIES:
        msg = f"Invalid category '{category}' for extreme n={val}, locale={locale}"
        raise PluralFuzzError(msg)


def _pattern_raw_bytes(fdp: atheris.FuzzedDataProvider) -> None:
    """Malformed input stability: raw bytes as locale, arbitrary numbers."""
    locale = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 100))

    num_type = fdp.ConsumeIntInRange(0, 3)
    if num_type == 0:
        n: int | float | Decimal = fdp.ConsumeInt(8)
    elif num_type == 1:
        n = fdp.ConsumeFloat()
    elif num_type == 2:
        try:
            n = Decimal(fdp.ConsumeUnicodeNoSurrogates(20))
        except InvalidOperation:
            n = 0
    else:
        n = fdp.ConsumeIntInRange(-(10**9), 10**9)

    precision_raw = fdp.ConsumeIntInRange(-5, 50)
    precision = precision_raw if fdp.ConsumeBool() else None

    # Must not crash with unhandled exception
    category = select_plural_category(n, locale, precision=precision)

    if category not in VALID_CATEGORIES:
        msg = f"Invalid category '{category}' for raw input"
        raise PluralFuzzError(msg)


# --- Pattern dispatch ---

def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a weighted pattern."""
    total = sum(w for _, w in _PATTERN_WEIGHTS)
    choice = fdp.ConsumeIntInRange(0, total - 1)

    cumulative = 0
    for name, weight in _PATTERN_WEIGHTS:
        cumulative += weight
        if choice < cumulative:
            return name

    return _PATTERN_WEIGHTS[0][0]


_PATTERN_DISPATCH: dict[str, Any] = {
    "category_validity": _pattern_category_validity,
    "precision_sensitivity": _pattern_precision_sensitivity,
    "locale_coverage": _pattern_locale_coverage,
    "locale_fallback": _pattern_locale_fallback,
    "determinism": _pattern_determinism,
    "number_type_variety": _pattern_number_type_variety,
    "boundary_numbers": _pattern_boundary_numbers,
    "cache_consistency": _pattern_cache_consistency,
    "extreme_inputs": _pattern_extreme_inputs,
    "raw_bytes": _pattern_raw_bytes,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz CLDR plural category selection."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern = _select_pattern(fdp)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except PluralFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        # BabelImportError should not happen in fuzz env, but handle gracefully
        if "Babel" in type(e).__name__ or "Babel" in str(e):
            error_key = f"BabelError_{type(e).__name__}"
        else:
            error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern] = (
            _state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern, data)
        _track_seed_corpus(data, pattern, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the plural rules fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Plural rule boundary fuzzer using Atheris/libFuzzer",
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
        default=100,
        help="Maximum size of in-memory seed corpus (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Plural Rule Boundary Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     select_plural_category")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
