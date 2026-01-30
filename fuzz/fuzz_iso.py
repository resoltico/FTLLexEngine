#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: iso - ISO 3166/4217 Introspection
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""ISO Introspection Fuzzer (Atheris).

Targets ISO 3166-1 territory and ISO 4217 currency introspection APIs.
Tests cache integrity, type guard correctness, Babel data access patterns,
list function invariants, and territory-currency cross-referencing.

Metrics:
- Pattern coverage (territory_lookup, currency_lookup, type_guards, etc.)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
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
import string
import sys
import time
from collections import deque
from dataclasses import dataclass, field
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


# --- Test Constants ---
ALPHA_UPPER = string.ascii_uppercase
ALPHA_LOWER = string.ascii_lowercase

SAMPLE_TERRITORIES = ("US", "GB", "DE", "FR", "JP", "CN", "IN", "BR", "AU", "LV",
                       "EG", "SA", "PL", "ZZ", "XK", "AN")
SAMPLE_CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CNY", "INR", "BRL", "AUD",
                     "CHF", "CAD", "BHD", "KWD", "OMR", "CLF", "XAU", "XXX")
SAMPLE_LOCALES = ("en", "en_US", "de_DE", "ja_JP", "lv_LV", "ar_SA", "zh_CN",
                  "fr_FR", "pl_PL", "ko_KR", "", "C", "root")

# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("territory_lookup", 15),
    ("currency_lookup", 15),
    ("type_guards", 15),
    ("cache_consistency", 12),
    ("list_functions", 10),
    ("territory_currencies", 10),
    ("cache_clear_stress", 8),
    ("cross_reference", 8),
    ("invalid_input_stress", 7),
)


class ISOFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# Exception contract
ALLOWED_EXCEPTIONS = (ValueError, KeyError, LookupError)


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
        report_file = pathlib.Path(".fuzz_corpus") / "iso" / "fuzz_iso_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.introspection.iso import (
        BabelImportError,
        CurrencyInfo,
        TerritoryInfo,
        clear_iso_cache,
        get_currency,
        get_territory,
        get_territory_currencies,
        is_valid_currency_code,
        is_valid_territory_code,
        list_currencies,
        list_territories,
    )

# Add BabelImportError to allowed exceptions
_ALLOWED = (*ALLOWED_EXCEPTIONS, BabelImportError)


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
    is_interesting = duration_ms > 50.0 or "stress" in pattern or "cross" in pattern

    if is_interesting:
        input_hash = hashlib.sha256(input_data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_data
            _state.corpus_entries_added += 1


# --- Input Generators ---

def _gen_territory_code(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a potential ISO 3166-1 alpha-2 code."""
    if not fdp.remaining_bytes():
        return "US"
    strategy = fdp.ConsumeIntInRange(0, 4)
    match strategy:
        case 0:
            return fdp.PickValueInList(list(SAMPLE_TERRITORIES))
        case 1:
            c1 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2
        case 2:
            c1 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2
        case 3:
            length = fdp.ConsumeIntInRange(0, 6)
            return fdp.ConsumeUnicodeNoSurrogates(length)
        case _:
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 10))


def _gen_currency_code(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a potential ISO 4217 currency code."""
    if not fdp.remaining_bytes():
        return "USD"
    strategy = fdp.ConsumeIntInRange(0, 4)
    match strategy:
        case 0:
            return fdp.PickValueInList(list(SAMPLE_CURRENCIES))
        case 1:
            c1 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c3 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2 + c3
        case 2:
            c1 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c3 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2 + c3
        case 3:
            length = fdp.ConsumeIntInRange(0, 7)
            return fdp.ConsumeUnicodeNoSurrogates(length)
        case _:
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 10))


def _gen_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a locale string for testing."""
    if not fdp.remaining_bytes():
        return "en"
    strategy = fdp.ConsumeIntInRange(0, 3)
    match strategy:
        case 0:
            return fdp.PickValueInList(list(SAMPLE_LOCALES))
        case 1:
            lang = (ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
                    + ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)])
            if fdp.ConsumeBool():
                territory = (ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
                             + ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)])
                return f"{lang}_{territory}"
            return lang
        case 2:
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
        case _:
            return "x" * fdp.ConsumeIntInRange(100, 300)


# --- Pattern Implementations ---

def _pattern_territory_lookup(fdp: atheris.FuzzedDataProvider) -> None:
    """Fuzz get_territory with invariant checks."""
    code = _gen_territory_code(fdp)
    locale = _gen_locale(fdp)

    try:
        result = get_territory(code, locale)
        if result is not None:
            if result.alpha2 != code.upper():
                msg = f"TerritoryInfo.alpha2 mismatch: {result.alpha2!r} != {code.upper()!r}"
                raise ISOFuzzError(msg)
            if not isinstance(result.name, str) or not result.name:
                msg = f"TerritoryInfo.name invalid: {result.name!r}"
                raise ISOFuzzError(msg)
            _ = hash(result)
            _ = {result}
    except _ALLOWED:
        pass


def _pattern_currency_lookup(fdp: atheris.FuzzedDataProvider) -> None:
    """Fuzz get_currency with invariant checks."""
    code = _gen_currency_code(fdp)
    locale = _gen_locale(fdp)

    try:
        result = get_currency(code, locale)
        if result is not None:
            if result.code != code.upper():
                msg = f"CurrencyInfo.code mismatch: {result.code!r} != {code.upper()!r}"
                raise ISOFuzzError(msg)
            if not isinstance(result.name, str) or not result.name:
                msg = f"CurrencyInfo.name invalid: {result.name!r}"
                raise ISOFuzzError(msg)
            if not isinstance(result.symbol, str) or not result.symbol:
                msg = f"CurrencyInfo.symbol invalid: {result.symbol!r}"
                raise ISOFuzzError(msg)
            if result.decimal_digits not in (0, 2, 3, 4):
                msg = f"CurrencyInfo.decimal_digits invalid: {result.decimal_digits}"
                raise ISOFuzzError(msg)
            _ = hash(result)
            _ = {result}
    except _ALLOWED:
        pass


def _pattern_type_guards(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify type guards are consistent with lookup functions."""
    territory_code = _gen_territory_code(fdp)
    currency_code = _gen_currency_code(fdp)

    try:
        is_valid_t = is_valid_territory_code(territory_code)
        t_result = get_territory(territory_code)

        if is_valid_t and t_result is None:
            msg = f"Type guard says valid territory but lookup returned None: {territory_code!r}"
            raise ISOFuzzError(msg)
        if not is_valid_t and t_result is not None:
            msg = f"Type guard says invalid territory but lookup succeeded: {territory_code!r}"
            raise ISOFuzzError(msg)

        is_valid_c = is_valid_currency_code(currency_code)
        c_result = get_currency(currency_code)

        if is_valid_c and c_result is None:
            msg = f"Type guard says valid currency but lookup returned None: {currency_code!r}"
            raise ISOFuzzError(msg)
        if not is_valid_c and c_result is not None:
            msg = f"Type guard says invalid currency but lookup succeeded: {currency_code!r}"
            raise ISOFuzzError(msg)
    except _ALLOWED:
        pass


def _pattern_cache_consistency(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify cache produces identical objects on repeated lookups."""
    territory_code = fdp.PickValueInList(list(SAMPLE_TERRITORIES[:10]))
    currency_code = fdp.PickValueInList(list(SAMPLE_CURRENCIES[:10]))
    locale = fdp.PickValueInList(["en", "de", "ja"])

    try:
        t1 = get_territory(territory_code, locale)
        c1 = get_currency(currency_code, locale)
        t2 = get_territory(territory_code, locale)
        c2 = get_currency(currency_code, locale)

        if t1 is not t2:
            msg = f"Cache returned different TerritoryInfo objects for {territory_code!r}"
            raise ISOFuzzError(msg)
        if c1 is not c2:
            msg = f"Cache returned different CurrencyInfo objects for {currency_code!r}"
            raise ISOFuzzError(msg)
    except _ALLOWED:
        pass


def _pattern_list_functions(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify list_territories and list_currencies invariants."""
    locale = _gen_locale(fdp)

    try:
        territories = list_territories(locale)
        currencies = list_currencies(locale)

        if not isinstance(territories, frozenset):
            msg = f"list_territories returned {type(territories)}, expected frozenset"
            raise ISOFuzzError(msg)
        if not isinstance(currencies, frozenset):
            msg = f"list_currencies returned {type(currencies)}, expected frozenset"
            raise ISOFuzzError(msg)

        for t in territories:
            if not isinstance(t, TerritoryInfo):
                msg = f"list_territories contains non-TerritoryInfo: {type(t)}"
                raise ISOFuzzError(msg)
        for c in currencies:
            if not isinstance(c, CurrencyInfo):
                msg = f"list_currencies contains non-CurrencyInfo: {type(c)}"
                raise ISOFuzzError(msg)

        # Known valid locales should return substantial sets
        if locale in ("en", "de", "ja"):
            if len(territories) < 200:
                msg = f"list_territories returned too few for '{locale}': {len(territories)}"
                raise ISOFuzzError(msg)
            if len(currencies) < 100:
                msg = f"list_currencies returned too few for '{locale}': {len(currencies)}"
                raise ISOFuzzError(msg)
    except _ALLOWED:
        pass


def _pattern_territory_currencies(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify get_territory_currencies invariants."""
    code = _gen_territory_code(fdp)

    try:
        currencies = get_territory_currencies(code)

        if not isinstance(currencies, tuple):
            msg = f"get_territory_currencies returned {type(currencies)}, expected tuple"
            raise ISOFuzzError(msg)
        for curr_code in currencies:
            if not isinstance(curr_code, str) or len(curr_code) != 3:
                msg = f"get_territory_currencies returned invalid code: {curr_code!r}"
                raise ISOFuzzError(msg)
            if not curr_code.isupper():
                msg = f"Currency code not uppercase: {curr_code!r}"
                raise ISOFuzzError(msg)
    except _ALLOWED:
        pass


def _pattern_cache_clear_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress test cache clear + re-lookup cycle."""
    code = fdp.PickValueInList(list(SAMPLE_TERRITORIES[:5]))
    locale = fdp.PickValueInList(["en", "de"])

    try:
        # Populate cache
        t1 = get_territory(code, locale)
        c1 = get_currency("USD", locale)

        # Clear and re-lookup
        clear_iso_cache()

        t2 = get_territory(code, locale)
        c2 = get_currency("USD", locale)

        # After clear, objects may differ in identity but must be equal in value
        if t1 is not None and t2 is not None and t1.alpha2 != t2.alpha2:
            msg = f"Post-clear territory mismatch: {t1.alpha2} != {t2.alpha2}"
            raise ISOFuzzError(msg)
        if c1 is not None and c2 is not None and c1.code != c2.code:
            msg = f"Post-clear currency mismatch: {c1.code} != {c2.code}"
            raise ISOFuzzError(msg)

        # Rapid clear cycles
        for _ in range(fdp.ConsumeIntInRange(2, 10)):
            clear_iso_cache()
            get_territory(code, locale)
            get_currency("USD", locale)
    except _ALLOWED:
        pass


def _pattern_cross_reference(fdp: atheris.FuzzedDataProvider) -> None:
    """Cross-reference territory currencies with currency lookups."""
    code = fdp.PickValueInList(list(SAMPLE_TERRITORIES[:10]))
    locale = _gen_locale(fdp)

    try:
        currencies_for_territory = get_territory_currencies(code)

        for curr_code in currencies_for_territory[:3]:
            result = get_currency(curr_code, locale)
            if result is not None and result.code != curr_code:
                msg = (f"Cross-ref mismatch: territory {code} lists {curr_code} "
                       f"but get_currency returned {result.code}")
                raise ISOFuzzError(msg)
    except _ALLOWED:
        pass


def _pattern_invalid_input_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress test with various invalid inputs."""
    attack_type = fdp.ConsumeIntInRange(0, 5)

    try:
        match attack_type:
            case 0:
                # Empty strings
                get_territory("")
                get_currency("")
                is_valid_territory_code("")
                is_valid_currency_code("")
            case 1:
                # Very long strings
                long_str = "A" * fdp.ConsumeIntInRange(100, 1000)
                get_territory(long_str)
                get_currency(long_str)
            case 2:
                # Null bytes and control chars
                bad = "\x00\x01\x02\x03"
                get_territory(bad)
                get_currency(bad)
            case 3:
                # Numeric strings
                get_territory("12")
                get_currency("123")
            case 4:
                # Unicode beyond ASCII
                get_territory("\u00C4\u00D6")
                get_currency("\u00C4\u00D6\u00DC")
            case _:
                # Mixed case
                get_territory("uS")
                get_currency("uSd")
                is_valid_territory_code("uS")
                is_valid_currency_code("uSd")
    except _ALLOWED:
        pass


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
    "territory_lookup": _pattern_territory_lookup,
    "currency_lookup": _pattern_currency_lookup,
    "type_guards": _pattern_type_guards,
    "cache_consistency": _pattern_cache_consistency,
    "list_functions": _pattern_list_functions,
    "territory_currencies": _pattern_territory_currencies,
    "cache_clear_stress": _pattern_cache_clear_stress,
    "cross_reference": _pattern_cross_reference,
    "invalid_input_stress": _pattern_invalid_input_stress,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz ISO introspection APIs."""
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

    except ISOFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
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
    """Run the ISO introspection fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="ISO introspection fuzzer using Atheris/libFuzzer",
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
    print("ISO Introspection Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     get_territory, get_currency, type guards, cache, list functions")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
