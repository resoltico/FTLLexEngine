#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: currency - Currency symbol & numeric extraction
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Currency Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.currency.parse_currency
Tests tiered loading, ambiguous symbol resolution, and numeric extraction.

Metrics:
- Fast tier vs full tier usage (CLDR scan trigger rate)
- Ambiguous symbol resolution accuracy
- Locale inference success rate
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution (parse failures, invalid codes, ambiguous symbols)
- Seed corpus management (interesting inputs)

Built for Python 3.13+.
"""

from __future__ import annotations

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
from decimal import Decimal

try:
    import psutil
except ImportError:
    print("[ERROR] psutil not found. Install: uv pip install psutil", file=sys.stderr)
    sys.exit(1)

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float]
type InterestingInput = tuple[float, str, str]  # (parse_time_ms, pattern, input_hash)

# --- Global Observability State ---
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}
performance_history: deque[float] = deque(maxlen=1000)
memory_history: deque[float] = deque(maxlen=100)
pattern_coverage: dict[str, int] = {}
error_counts: dict[str, int] = {}
slowest_parses: list[InterestingInput] = []  # Max-heap for top 10 slowest
seed_corpus: dict[str, str] = {}  # hash -> input (interesting inputs)
_process: psutil.Process = psutil.Process(os.getpid())
_initial_memory_mb: float = 0.0

# Currency-specific metrics
fast_tier_hits: int = 0
full_tier_hits: int = 0
ambiguous_resolutions: int = 0
locale_inferences: int = 0

def _emit_final_report() -> None:
    """Emit comprehensive final report matching fuzz_oom.py pattern."""
    # Performance percentiles
    if performance_history:
        perf_data = list(performance_history)
        _fuzz_stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        _fuzz_stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        _fuzz_stats["perf_p95_ms"] = round(
            statistics.quantiles(perf_data, n=20)[18], 3
        ) if len(perf_data) >= 20 else 0.0
        _fuzz_stats["perf_p99_ms"] = round(
            statistics.quantiles(perf_data, n=100)[98], 3
        ) if len(perf_data) >= 100 else 0.0
        _fuzz_stats["perf_min_ms"] = round(min(perf_data), 3)
        _fuzz_stats["perf_max_ms"] = round(max(perf_data), 3)

    # Memory tracking
    if memory_history:
        mem_data = list(memory_history)
        _fuzz_stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        _fuzz_stats["memory_peak_mb"] = round(max(mem_data), 2)
        _fuzz_stats["memory_delta_mb"] = round(
            max(mem_data) - _initial_memory_mb, 2
        )

    # Memory leak detection
    if len(memory_history) >= 10:
        mem_data = list(memory_history)
        first_10_avg = statistics.mean(mem_data[:10])
        last_10_avg = statistics.mean(mem_data[-10:])
        growth_mb = last_10_avg - first_10_avg
        if growth_mb > 5.0:
            _fuzz_stats["memory_leak_detected"] = 1
            _fuzz_stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            _fuzz_stats["memory_leak_detected"] = 0

    # Pattern coverage
    _fuzz_stats["patterns_tested"] = len(pattern_coverage)
    for pattern, count in sorted(pattern_coverage.items()):
        _fuzz_stats[f"pattern_{pattern}"] = count

    # Error distribution
    _fuzz_stats["error_types"] = len(error_counts)
    for error_type, count in sorted(error_counts.items()):
        _fuzz_stats[f"error_{error_type}"] = count

    # Currency-specific metrics
    _fuzz_stats["fast_tier_hits"] = fast_tier_hits
    _fuzz_stats["full_tier_hits"] = full_tier_hits
    _fuzz_stats["ambiguous_resolutions"] = ambiguous_resolutions
    _fuzz_stats["locale_inferences"] = locale_inferences

    # Tier ratio (fast vs full CLDR scan)
    total_tier_hits = fast_tier_hits + full_tier_hits
    if total_tier_hits > 0:
        _fuzz_stats["fast_tier_ratio"] = round(
            fast_tier_hits / total_tier_hits, 3
        )

    # Seed corpus
    _fuzz_stats["seed_corpus_size"] = len(seed_corpus)
    _fuzz_stats["slowest_parses_tracked"] = len(slowest_parses)

    _fuzz_stats["status"] = "complete"

    report = json.dumps(_fuzz_stats, sort_keys=True)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    # ALSO write to file for shell script parsing (Atheris may not flush stderr on exit)
    # Best-effort write: catch all exceptions to avoid breaking fuzzer
    try:
        report_file = pathlib.Path(".fuzz_corpus") / "fuzz_currency_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except Exception:  # pylint: disable=broad-exception-caught
        pass

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.parsing.currency import parse_currency

TEST_LOCALES = ["en-US", "en-CA", "zh-CN", "lv-LV", "ar-EG", "de-DE", "fr-FR", "ja-JP", "root"]

def _generate_currency_pattern(  # noqa: PLR0911, PLR0912, PLR0915 - Pattern generation
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str, str]:
    """Generate currency pattern for testing.

    Returns:
        (pattern_name, input_string, locale)
    """
    pattern_choice = fdp.ConsumeIntInRange(0, 11)
    locale = fdp.PickValueInList(TEST_LOCALES)

    match pattern_choice:
        case 0:  # Unambiguous Unicode symbols (fast tier)
            symbol = fdp.PickValueInList([
                "\u20ac",  # Euro
                "\u20b9",  # Indian Rupee
                "\u20bd",  # Russian Ruble
                "\u20ba",  # Turkish Lira
                "\u20aa",  # Israeli Shekel
                "\u20a6",  # Nigerian Naira
            ])
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"{symbol}{amount:.2f}" if fdp.ConsumeBool()
                else f"{amount:.2f} {symbol}"
            )
            return ("unambiguous_unicode", input_str, locale)

        case 1:  # Ambiguous dollar sign (requires locale)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"${amount:.2f}" if fdp.ConsumeBool()
                else f"{amount:.2f}$"
            )
            return ("ambiguous_dollar", input_str, locale)

        case 2:  # Ambiguous pound sign (GBP, EGP, GIP)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a3{amount:.2f}"
            return ("ambiguous_pound", input_str, locale)

        case 3:  # Ambiguous yen/yuan sign (JPY, CNY)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a5{amount:.2f}"
            return ("ambiguous_yen_yuan", input_str, locale)

        case 4:  # Ambiguous "kr" (SEK, NOK, DKK, ISK)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"{amount:.2f} kr" if fdp.ConsumeBool()
                else f"kr {amount:.2f}"
            )
            return ("ambiguous_kr", input_str, locale)

        case 5:  # Comma as decimal separator (European format)
            symbol = fdp.PickValueInList(["\u20ac", "$", "\u00a3"])
            amount_int = fdp.ConsumeIntInRange(1, 999999)
            amount_frac = fdp.ConsumeIntInRange(0, 99)
            input_str = f"{symbol}{amount_int},{amount_frac:02d}"
            return ("comma_decimal", input_str, locale)

        case 6:  # Period as grouping separator (European format)
            symbol = fdp.PickValueInList(["\u20ac", "$"])
            input_str = f"{symbol}1.234.567,89"
            return ("period_grouping", input_str, locale)

        case 7:  # Negative formats (4 common patterns)
            symbol = "$"
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            neg_choice = fdp.ConsumeIntInRange(0, 3)
            match neg_choice:
                case 0:
                    input_str = f"-{symbol}{amount:.2f}"  # -$100.00
                case 1:
                    input_str = f"({symbol}{amount:.2f})"  # ($100.00)
                case 2:
                    input_str = f"{symbol}-{amount:.2f}"  # $-100.00
                case _:
                    input_str = f"{symbol}{amount:.2f}-"  # $100.00-
            return ("negative_format", input_str, locale)

        case 8:  # Explicit ISO code (bypass symbol resolution)
            code = fdp.PickValueInList(["USD", "EUR", "GBP", "JPY", "CNY", "INR"])
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"{amount:.2f} {code}"
            return ("explicit_iso_code", input_str, locale)

        case 9:  # Invalid ISO codes (error testing)
            invalid_code = fdp.PickValueInList(["US", "EURO", "GB", "XYZ", "1234"])
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            input_str = f"{amount:.2f} {invalid_code}"
            return ("invalid_iso_code", input_str, locale)

        case 10:  # Whitespace variations
            symbol = fdp.PickValueInList(["\u20ac", "$", "\u00a3"])
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            spaces = " " * fdp.ConsumeIntInRange(0, 5)
            if fdp.ConsumeBool():
                input_str = f"{symbol}{spaces}{amount:.2f}"
            else:
                input_str = f"{amount:.2f}{spaces}{symbol}"
            return ("whitespace_variation", input_str, locale)

        case 11:  # Edge cases
            edge_choice = fdp.ConsumeIntInRange(0, 4)
            match edge_choice:
                case 0:
                    input_str = ""  # Empty
                case 1:
                    input_str = "   "  # Whitespace only
                case 2:
                    input_str = "$"  # Symbol only
                case 3:
                    input_str = "123.45"  # Number only (no symbol)
                case _:
                    input_str = "abc def"  # Invalid
            return ("edge_case", input_str, locale)

        case _:
            # Fallback (unreachable)
            return ("fallback", "$100.00", "en-US")

def _track_slowest_parse(
    parse_time_ms: float,
    pattern: str,
    input_str: str,
) -> None:
    """Track top 10 slowest parses using max-heap (negated values)."""
    input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]
    # Negate parse_time to create max-heap (heapq is min-heap by default)
    entry: InterestingInput = (-parse_time_ms, pattern, input_hash)

    if len(slowest_parses) < 10:
        heapq.heappush(slowest_parses, entry)
    elif -parse_time_ms < slowest_parses[0][0]:  # Slower than minimum (remember negation)
        heapq.heapreplace(slowest_parses, entry)

def _track_seed_corpus(input_str: str, pattern: str, parse_time_ms: float) -> None:
    """Track interesting inputs for seed corpus."""
    # Interesting if: slow parse (>10ms), ambiguous symbol, or edge case
    is_interesting = (
        parse_time_ms > 10.0
        or "ambiguous" in pattern
        or "edge_case" in pattern
    )

    if is_interesting and len(seed_corpus) < 1000:
        input_hash = hashlib.sha256(input_str.encode()).hexdigest()[:16]
        if input_hash not in seed_corpus:
            seed_corpus[input_hash] = input_str

def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915 - Validation logic
    """Atheris entry point: Test currency parsing boundary conditions.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil
    - Pattern coverage: 12 currency format types
    - Error distribution: Categorized parse failures
    - Corpus: Interesting inputs (slow/ambiguous/edge cases)
    """
    # Fuzzing observability pattern: global state for memory baseline tracking
    global _initial_memory_mb  # noqa: PLW0603  # pylint: disable=global-statement
    global fast_tier_hits, full_tier_hits  # noqa: PLW0603  # pylint: disable=global-statement
    global ambiguous_resolutions, locale_inferences  # noqa: PLW0603  # pylint: disable=global-statement

    # Initialize memory baseline on first iteration
    if _fuzz_stats["iterations"] == 0:
        _initial_memory_mb = _process.memory_info().rss / (1024 * 1024)

    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    # Periodic report write (every 10k iterations) for shell script parsing
    if _fuzz_stats["iterations"] % 10000 == 0:
        _emit_final_report()

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    # Generate currency pattern (12 pattern types)
    pattern_name, input_str, locale = _generate_currency_pattern(fdp)
    pattern_coverage[pattern_name] = pattern_coverage.get(pattern_name, 0) + 1

    # Optional: override with default_currency and infer_from_locale
    default_curr = fdp.ConsumeUnicodeNoSurrogates(3) if fdp.ConsumeBool() else None
    infer = fdp.ConsumeBool()

    if infer:
        locale_inferences += 1

    try:
        res, errors = parse_currency(
            input_str,
            locale,
            default_currency=default_curr,
            infer_from_locale=infer,
        )

        # Track tier usage (heuristic: fast tier for unambiguous, full tier for ambiguous)
        if "unambiguous" in pattern_name:
            fast_tier_hits += 1
        elif "ambiguous" in pattern_name:
            full_tier_hits += 1
            ambiguous_resolutions += 1

        # Track API contract violations (instead of asserting/crashing)
        if res:
            amount, code = res

            # Validate return types
            if not isinstance(amount, Decimal):
                error_counts["contract_invalid_amount_type"] = (
                    error_counts.get("contract_invalid_amount_type", 0) + 1
                )
            if not isinstance(code, str):
                error_counts["contract_invalid_code_type"] = (
                    error_counts.get("contract_invalid_code_type", 0) + 1
                )

            # ISO 4217 validation: currency codes MUST be exactly 3 uppercase ASCII letters
            if isinstance(code, str):
                if len(code) != 3:
                    # Track length violations by actual length for diagnostics
                    error_key = f"contract_iso4217_length_{len(code)}"
                    error_counts[error_key] = error_counts.get(error_key, 0) + 1
                    _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                elif not code.isupper():
                    error_counts["contract_iso4217_not_uppercase"] = (
                        error_counts.get("contract_iso4217_not_uppercase", 0) + 1
                    )
                    _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
                elif not code.isalpha():
                    error_counts["contract_iso4217_not_alpha"] = (
                        error_counts.get("contract_iso4217_not_alpha", 0) + 1
                    )
                    _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1

        # Track parse errors (expected errors)
        if errors:
            for error in errors:
                # FrozenFluentError has category (ErrorCategory) and message (str)
                error_key = f"{error.category.value}_{error.message[:30]}"
                error_counts[error_key] = error_counts.get(error_key, 0) + 1

    except (ValueError, TypeError) as e:
        # Expected: invalid locale, invalid input format
        error_type = f"{type(e).__name__}_{str(e)[:20]}"
        error_counts[error_type] = error_counts.get(error_type, 0) + 1
    except Exception:
        # Unexpected exceptions are findings
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise
    finally:
        # Performance tracking
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        performance_history.append(elapsed_ms)

        # Track interesting inputs
        _track_slowest_parse(elapsed_ms, pattern_name, input_str)
        _track_seed_corpus(input_str, pattern_name, elapsed_ms)

        # Memory tracking (every 100 iterations to reduce overhead)
        if _fuzz_stats["iterations"] % 100 == 0:
            current_memory_mb = _process.memory_info().rss / (1024 * 1024)
            memory_history.append(current_memory_mb)

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
