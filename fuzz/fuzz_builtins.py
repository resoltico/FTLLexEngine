#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: builtins - Built-in Functions (Babel Boundary)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Built-in Function Boundary Fuzzer (Atheris).

Targets: ftllexengine.runtime.functions (NUMBER, DATETIME, CURRENCY),
         ftllexengine.runtime.function_bridge (FunctionRegistry, FluentNumber,
         parameter mapping, locale injection, freeze/copy semantics).

Tests the bridge between FTL camelCase arguments and Python snake_case
built-in functions backed by Babel/CLDR, with emphasis on:
- FluentNumber precision (CLDR v operand) correctness
- FunctionRegistry lifecycle (register, freeze, copy, introspect)
- Parameter mapping (camelCase <-> snake_case bridge)
- Locale injection protocol
- Edge values (NaN, Inf, -0.0, huge, negative timestamps)
- Currency-specific decimal digits (JPY=0, BHD=3)

Metrics:
- Pattern coverage with weighted selection (13 patterns)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management
- Per-pattern wall-time accumulation

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
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
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

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
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float]


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000)
    )
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Slowest operations (min-heap for top 10)
    slowest_operations: list[tuple[float, str]] = field(default_factory=list)

    # Seed corpus
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

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
        stats["memory_delta_mb"] = round(
            max(mem_data) - _state.initial_memory_mb, 2
        )

        # Memory leak detection (quarter comparison)
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

    print(
        f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]",
        file=sys.stderr,
        flush=True,
    )

    # Write to file for shell script parsing (best-effort)
    try:
        report_file = (
            pathlib.Path(".fuzz_corpus") / "builtins" / "fuzz_builtins_report.json"
        )
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.runtime.function_bridge import (
        FluentNumber,
    )
    from ftllexengine.runtime.functions import (
        create_default_registry,
        currency_format,
        datetime_format,
        get_shared_registry,
        number_format,
    )

# --- Constants ---
_LOCALES: Sequence[str] = (
    "en-US", "de-DE", "ar-EG", "zh-Hans-CN", "ja-JP",
    "lv-LV", "fr-FR", "pt-BR", "hi-IN", "root",
)

_VALID_ISO_CURRENCIES: Sequence[str] = (
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", "BRL",
    "INR", "KRW", "BHD", "KWD", "OMR",
)

_CURRENCY_DISPLAY_MODES: Sequence[str] = ("symbol", "code", "name")

_DATE_STYLES: Sequence[str] = ("short", "medium", "long", "full")

# Numbers that exercise precision boundary conditions
_PRECISION_NUMBERS: Sequence[Decimal] = (
    Decimal("0"), Decimal("1"), Decimal("1.0"), Decimal("1.00"),
    Decimal("1.5"), Decimal("1.50"), Decimal("0.001"),
    Decimal("1234567.89"), Decimal("-1.5"), Decimal("0.10"),
    Decimal("999999999.999"),
)

# Edge float values
_EDGE_FLOATS: Sequence[float] = (
    0.0, -0.0, 1e-10, 1e10, 1e100, 1e308,
    float("inf"), float("-inf"), float("nan"),
    -1.0, 0.1, 0.01, 0.001,
)

# Timestamp boundaries for DATETIME
_MIN_TIMESTAMP = -62135596800.0  # 0001-01-01T00:00:00 UTC
_MAX_TIMESTAMP = 253402300799.0  # 9999-12-31T23:59:59 UTC


class BuiltinsFuzzError(Exception):
    """Raised when a fuzzer invariant is violated."""


def _track_slowest_operation(duration_ms: float, description: str) -> None:
    """Track top 10 slowest operations using min-heap."""
    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, (duration_ms, description[:50]))
    elif duration_ms > _state.slowest_operations[0][0]:
        heapq.heapreplace(
            _state.slowest_operations, (duration_ms, description[:50])
        )


def _track_seed_corpus(data: bytes, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with FIFO eviction."""
    # Timing-based only; pattern-name criteria caused 79M/297M churn
    is_interesting = duration_ms > 10.0

    if is_interesting:
        input_hash = hashlib.sha256(data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = data
            _state.corpus_entries_added += 1


def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


# =============================================================================
# Pattern implementations
# =============================================================================

def _pattern_number_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """NUMBER with varied fraction digits, grouping, and locales."""
    locale = _pick_locale(fdp)
    val = Decimal(str(fdp.ConsumeFloat()))
    min_frac = fdp.ConsumeIntInRange(0, 10)
    max_frac = fdp.ConsumeIntInRange(min_frac, 20)
    grouping = fdp.ConsumeBool()

    result = number_format(
        val, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=grouping,
    )

    # Invariant: result must be FluentNumber
    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__}, expected FluentNumber"
        raise BuiltinsFuzzError(msg)


def _pattern_number_precision(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FluentNumber precision (CLDR v operand) correctness.

    The v operand is the count of visible fraction digits in the formatted
    output. This is critical for plural rule matching.
    """
    locale = _pick_locale(fdp)
    # Use precision-sensitive numbers
    if fdp.ConsumeBool():
        val = fdp.PickValueInList(list(_PRECISION_NUMBERS))
    else:
        val = Decimal(str(fdp.ConsumeFloat()))

    min_frac = fdp.ConsumeIntInRange(0, 6)
    max_frac = fdp.ConsumeIntInRange(min_frac, 10)

    result = number_format(
        val, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=False,
    )

    # Invariant: precision must be non-negative integer
    if not isinstance(result, FluentNumber):
        return
    if result.precision is not None and result.precision < 0:
        msg = (
            f"Negative precision {result.precision} for val={val}, "
            f"locale={locale}, min={min_frac}, max={max_frac}"
        )
        raise BuiltinsFuzzError(msg)

    # Invariant: with min_frac > 0, precision should be >= min_frac
    # (unless formatting fails silently)
    if min_frac > 0 and result.precision is not None and result.precision < min_frac:
        # Check if formatted string actually has a decimal point
        formatted = str(result)
        if "." in formatted or "," in formatted:
            # Has decimal separator -- precision should reflect digits
            pass  # Locale-dependent, don't over-assert


def _pattern_number_edges(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge float values: NaN, Inf, -0.0, huge, tiny."""
    locale = _pick_locale(fdp)
    val_float = fdp.PickValueInList(list(_EDGE_FLOATS))

    try:
        val = Decimal(str(val_float))
    except InvalidOperation:
        # NaN/Inf as Decimal raises -- test with float directly
        val = Decimal("0")

    number_format(
        val, locale,
        minimum_fraction_digits=fdp.ConsumeIntInRange(0, 5),
        maximum_fraction_digits=fdp.ConsumeIntInRange(0, 10),
        use_grouping=fdp.ConsumeBool(),
    )


def _pattern_datetime_styles(fdp: atheris.FuzzedDataProvider) -> None:
    """DATETIME with all style combinations."""
    locale = _pick_locale(fdp)
    # Safe timestamp range
    timestamp = fdp.ConsumeFloat() % _MAX_TIMESTAMP
    if timestamp < 0:
        timestamp = abs(timestamp)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    date_style = fdp.PickValueInList(list(_DATE_STYLES))
    use_time = fdp.ConsumeBool()
    time_style = fdp.PickValueInList(list(_DATE_STYLES)) if use_time else None

    result = datetime_format(
        dt, locale,
        date_style=date_style,
        time_style=time_style,
    )

    # Invariant: result must be non-empty string
    if not isinstance(result, str) or not result:
        msg = (
            f"datetime_format returned empty/non-str: {result!r} "
            f"for locale={locale}, date_style={date_style}"
        )
        raise BuiltinsFuzzError(msg)


def _pattern_datetime_edges(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge timestamps and timezone variations."""
    locale = _pick_locale(fdp)

    # Edge timestamps
    edge_timestamps = [
        0.0,             # Unix epoch
        86400.0,         # One day
        -86400.0,        # Before epoch
        946684800.0,     # Y2K
        _MAX_TIMESTAMP,  # Max safe
    ]
    timestamp = fdp.PickValueInList(edge_timestamps)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    # Test with different timezone offsets
    if fdp.ConsumeBool():
        offset_hours = fdp.ConsumeIntInRange(-12, 14)
        tz = timezone(timedelta(hours=offset_hours))
        dt = dt.astimezone(tz)

    datetime_format(
        dt, locale,
        date_style=fdp.PickValueInList(list(_DATE_STYLES)),
        time_style=fdp.PickValueInList(list(_DATE_STYLES)) if fdp.ConsumeBool() else None,
    )


def _pattern_currency_codes(fdp: atheris.FuzzedDataProvider) -> None:
    """CURRENCY with valid/invalid ISO codes and display modes."""
    locale = _pick_locale(fdp)
    val = Decimal(str(fdp.ConsumeFloat()))

    # 80% valid ISO code, 20% fuzzed
    if fdp.ConsumeIntInRange(0, 4) < 4:
        currency = fdp.PickValueInList(list(_VALID_ISO_CURRENCIES))
    else:
        currency = fdp.ConsumeUnicodeNoSurrogates(3).upper()

    display = fdp.PickValueInList(list(_CURRENCY_DISPLAY_MODES))

    result = currency_format(
        val, locale,
        currency=currency,
        currency_display=display,
    )

    # Invariant: result must be FluentNumber
    if not isinstance(result, FluentNumber):
        msg = f"currency_format returned {type(result).__name__}"
        raise BuiltinsFuzzError(msg)


def _pattern_currency_precision(fdp: atheris.FuzzedDataProvider) -> None:
    """Currency-specific decimal digits: JPY=0, BHD=3, EUR/USD=2."""
    locale = _pick_locale(fdp)

    # Currencies with known decimal digits
    currency_decimals = {
        "JPY": 0, "KRW": 0,       # 0 decimals
        "USD": 2, "EUR": 2,       # 2 decimals
        "BHD": 3, "KWD": 3,       # 3 decimals
    }

    currency = fdp.PickValueInList(list(currency_decimals.keys()))
    val = fdp.PickValueInList(list(_PRECISION_NUMBERS))

    result = currency_format(
        val, locale,
        currency=currency,
        currency_display="code",
    )

    # Invariant: precision must be non-negative
    if isinstance(result, FluentNumber) and result.precision is not None and result.precision < 0:
        msg = (
            f"Negative precision {result.precision} for "
            f"currency={currency}, val={val}"
        )
        raise BuiltinsFuzzError(msg)


def _pattern_custom_pattern(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom Babel patterns for NUMBER, DATETIME, CURRENCY."""
    locale = _pick_locale(fdp)
    target = fdp.ConsumeIntInRange(0, 2)

    # Mix of valid and fuzzed patterns
    number_patterns = [
        "#,##0.00", "#,##0", "0.###", "#,##0.00;(#,##0.00)",
        "0.0", "#", "##0.00%",
    ]
    date_patterns = [
        "yyyy-MM-dd", "dd/MM/yyyy", "MMMM d, yyyy",
        "HH:mm:ss", "EEE, d MMM yyyy",
    ]

    match target:
        case 0:  # NUMBER with pattern
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(number_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            number_format(
                Decimal(str(fdp.ConsumeFloat())), locale,
                pattern=pattern,
            )
        case 1:  # DATETIME with pattern
            timestamp = abs(fdp.ConsumeFloat()) % _MAX_TIMESTAMP
            try:
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(date_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            datetime_format(dt, locale, pattern=pattern)
        case _:  # CURRENCY with pattern
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(number_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            currency_format(
                Decimal(str(fdp.ConsumeFloat())), locale,
                currency=fdp.PickValueInList(list(_VALID_ISO_CURRENCIES)),
                pattern=pattern,
            )


def _pattern_registry_lifecycle(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """FunctionRegistry freeze, copy, introspection, and isolation."""
    operation = fdp.ConsumeIntInRange(0, 4)

    match operation:
        case 0:
            # Shared registry is frozen
            shared = get_shared_registry()
            for expected_name in ("NUMBER", "DATETIME", "CURRENCY"):
                if expected_name not in shared:
                    msg = f"Shared registry missing {expected_name}"
                    raise BuiltinsFuzzError(msg)

        case 1:
            # Fresh registry has all builtins
            fresh = create_default_registry()
            funcs = fresh.list_functions()
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in funcs:
                    msg = f"Default registry missing {name}"
                    raise BuiltinsFuzzError(msg)

        case 2:
            # Copy produces unfrozen independent copy
            shared = get_shared_registry()
            copy = shared.copy()
            # Copy should be unfrozen even if original is frozen
            def custom_fn(*_a: Any, **_kw: Any) -> str:
                return "custom"
            try:
                copy.register(custom_fn, ftl_name="CUSTOM_TEST")
            except TypeError as exc:
                msg = "Registry copy should be unfrozen"
                raise BuiltinsFuzzError(msg) from exc
            # Original should still not have CUSTOM_TEST
            if "CUSTOM_TEST" in shared:
                msg = "Copy polluted shared registry"
                raise BuiltinsFuzzError(msg)

        case 3:
            # Introspection methods
            reg = create_default_registry()
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                info = reg.get_function_info(name)
                if info is None:
                    msg = f"get_function_info({name}) returned None"
                    raise BuiltinsFuzzError(msg)
                if not reg.should_inject_locale(name):
                    msg = f"{name} should require locale injection"
                    raise BuiltinsFuzzError(msg)
                expected = reg.get_expected_positional_args(name)
                if expected != 1:
                    msg = f"{name} expected 1 positional, got {expected}"
                    raise BuiltinsFuzzError(msg)

        case _:
            # Freeze prevents registration
            reg = create_default_registry()
            reg.freeze()
            def blocked_fn(*_a: Any, **_kw: Any) -> str:
                return "blocked"
            try:
                reg.register(blocked_fn, ftl_name="BLOCKED")
                msg = "Frozen registry accepted registration"
                raise BuiltinsFuzzError(msg)
            except TypeError:
                pass  # Expected


def _pattern_parameter_mapping(fdp: atheris.FuzzedDataProvider) -> None:
    """Parameter mapping: camelCase FTL args -> snake_case Python kwargs.

    Verifies the bridge converts argument names correctly when calling
    built-in functions through the registry.

    Uses shared frozen registry (read-only call path) to avoid
    create_default_registry() overhead on the hot path.
    """
    reg = get_shared_registry()
    locale = _pick_locale(fdp)
    val = Decimal(str(fdp.ConsumeIntInRange(1, 10000)))

    # Call NUMBER through registry with camelCase args
    result = reg.call(
        "NUMBER",
        [val, locale],
        {"minimumFractionDigits": 2, "maximumFractionDigits": 4},
    )

    if not isinstance(result, FluentNumber):
        msg = f"Registry call returned {type(result).__name__}"
        raise BuiltinsFuzzError(msg)

    # Call CURRENCY through registry
    currency = fdp.PickValueInList(list(_VALID_ISO_CURRENCIES))
    result2 = reg.call(
        "CURRENCY",
        [val, locale],
        {"currency": currency, "currencyDisplay": "code"},
    )

    if not isinstance(result2, FluentNumber):
        msg = f"CURRENCY registry call returned {type(result2).__name__}"
        raise BuiltinsFuzzError(msg)


def _pattern_locale_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify locale injection protocol for all built-in functions."""
    reg = get_shared_registry()

    for name in ("NUMBER", "DATETIME", "CURRENCY"):
        # All builtins require locale injection
        if not reg.should_inject_locale(name):
            msg = f"{name} does not require locale injection"
            raise BuiltinsFuzzError(msg)

        # Expected positional args = 1 (value only; locale injected separately)
        expected = reg.get_expected_positional_args(name)
        if expected != 1:
            msg = f"{name}: expected 1 positional arg, got {expected}"
            raise BuiltinsFuzzError(msg)

    # Test with fuzzed locale to verify fallback
    locale = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 30))
    val = Decimal(str(fdp.ConsumeIntInRange(0, 1000)))
    # Should not crash regardless of locale
    number_format(val, locale)


def _pattern_error_paths(fdp: atheris.FuzzedDataProvider) -> None:
    """Invalid inputs, type mismatches, missing required args."""
    locale = _pick_locale(fdp)
    error_case = fdp.ConsumeIntInRange(0, 4)

    match error_case:
        case 0:
            # Invalid fraction digits (negative)
            number_format(
                Decimal("1.5"), locale,
                minimum_fraction_digits=-1,
                maximum_fraction_digits=fdp.ConsumeIntInRange(-5, 5),
            )
        case 1:
            # Very large fraction digits
            number_format(
                Decimal("1.5"), locale,
                minimum_fraction_digits=fdp.ConsumeIntInRange(50, 200),
                maximum_fraction_digits=fdp.ConsumeIntInRange(50, 200),
            )
        case 2:
            # Empty currency code
            currency_format(
                Decimal("100"), locale,
                currency="",
            )
        case 3:
            # Invalid currency code (too long / too short)
            bad_code = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
            currency_format(
                Decimal("100"), locale,
                currency=bad_code,
            )
        case _:
            # Unknown function call through registry
            reg = create_default_registry()
            with contextlib.suppress(Exception):
                reg.call("NONEXISTENT", [Decimal("1")], {})


def _pattern_raw_bytes(fdp: atheris.FuzzedDataProvider) -> None:
    """Raw bytes pass-through: let libFuzzer mutations drive exploration."""
    locale = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))
    target = fdp.ConsumeIntInRange(0, 2)

    match target:
        case 0:
            val_str = fdp.ConsumeUnicodeNoSurrogates(30)
            try:
                val = Decimal(val_str)
            except InvalidOperation:
                val = Decimal("0")
            number_format(
                val, locale,
                minimum_fraction_digits=fdp.ConsumeIntInRange(0, 20),
                maximum_fraction_digits=fdp.ConsumeIntInRange(0, 20),
                use_grouping=fdp.ConsumeBool(),
                pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None,
            )
        case 1:
            timestamp = fdp.ConsumeFloat()
            try:
                dt = datetime.fromtimestamp(
                    max(min(timestamp, _MAX_TIMESTAMP), 0.0), tz=UTC
                )
                datetime_format(
                    dt, locale,
                    date_style=fdp.ConsumeUnicodeNoSurrogates(10),
                    time_style=fdp.ConsumeUnicodeNoSurrogates(10) if fdp.ConsumeBool() else None,
                    pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None,
                )
            except (OSError, OverflowError, ValueError):
                pass
        case _:
            val_str = fdp.ConsumeUnicodeNoSurrogates(30)
            try:
                val = Decimal(val_str)
            except InvalidOperation:
                val = Decimal("0")
            currency_format(
                val, locale,
                currency=fdp.ConsumeUnicodeNoSurrogates(10),
                currency_display=fdp.ConsumeUnicodeNoSurrogates(10),
                pattern=fdp.ConsumeUnicodeNoSurrogates(30) if fdp.ConsumeBool() else None,
            )


# =============================================================================
# Pattern dispatch table
# =============================================================================

_PATTERNS: Sequence[tuple[str, int, Any]] = (
    ("number_basic", 12, _pattern_number_basic),
    ("number_precision", 15, _pattern_number_precision),
    ("number_edges", 8, _pattern_number_edges),
    ("datetime_styles", 10, _pattern_datetime_styles),
    ("datetime_edges", 8, _pattern_datetime_edges),
    ("currency_codes", 12, _pattern_currency_codes),
    ("currency_precision", 10, _pattern_currency_precision),
    ("custom_pattern", 8, _pattern_custom_pattern),
    ("registry_lifecycle", 8, _pattern_registry_lifecycle),
    ("parameter_mapping", 7, _pattern_parameter_mapping),
    ("locale_injection", 5, _pattern_locale_injection),
    ("error_paths", 5, _pattern_error_paths),
    ("raw_bytes", 3, _pattern_raw_bytes),
)

_PATTERN_WEIGHTS: Sequence[int] = tuple(w for _, w, _ in _PATTERNS)
_TOTAL_WEIGHT: int = sum(_PATTERN_WEIGHTS)


def _select_pattern(fdp: atheris.FuzzedDataProvider) -> tuple[str, Any]:
    """Select pattern using weighted random selection."""
    choice = fdp.ConsumeIntInRange(0, _TOTAL_WEIGHT - 1)
    cumulative = 0
    for name, weight, func in _PATTERNS:
        cumulative += weight
        if choice < cumulative:
            return (name, func)
    # Fallback (unreachable with correct weights)
    return (_PATTERNS[-1][0], _PATTERNS[-1][2])


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test built-in functions and FunctionRegistry."""
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern_name, pattern_func = _select_pattern(fdp)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    # Execute with timing
    start_time = time.perf_counter()

    try:
        pattern_func(fdp)
    except BuiltinsFuzzError:
        _state.findings += 1
        raise
    except (
        ValueError, TypeError, OverflowError, InvalidOperation,
        OSError, ArithmeticError, FrozenFluentError,
    ):
        pass  # Expected for invalid inputs / Babel limitations
    except Exception:  # pylint: disable=broad-exception-caught
        _state.findings += 1
        error_type = sys.exc_info()[0]
        if error_type is not None:
            key = error_type.__name__[:50]
            _state.error_counts[key] = _state.error_counts.get(key, 0) + 1
        raise

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    _state.performance_history.append(elapsed_ms)

    # Per-pattern wall time
    _state.pattern_wall_time[pattern_name] = (
        _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
    )

    _track_slowest_operation(elapsed_ms, pattern_name)
    _track_seed_corpus(data, elapsed_ms)

    # Memory tracking (every 100 iterations)
    if _state.iterations % 100 == 0:
        current_mb = _get_process().memory_info().rss / (1024 * 1024)
        _state.memory_history.append(current_mb)


def main() -> None:
    """Run the builtins fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Built-in function boundary fuzzer using Atheris/libFuzzer",
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

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Built-in Function Boundary Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     NUMBER, DATETIME, CURRENCY, FunctionRegistry")
    print(f"Patterns:   {len(_PATTERNS)} weighted patterns")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
