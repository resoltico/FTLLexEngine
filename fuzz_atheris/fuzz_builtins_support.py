#!/usr/bin/env python3
"""Built-in Function Boundary Fuzzer (Atheris).

Targets: ftllexengine.runtime.functions (NUMBER, DATETIME, CURRENCY)

Concern boundary: This fuzzer stress-tests the Babel formatting boundary by
calling NUMBER, DATETIME, and CURRENCY functions directly through the Python
API. This is distinct from fuzz_runtime which invokes these functions through
FTL syntax and the resolver stack. Direct API testing isolates the Babel layer
from resolver/cache behavior and enables:
- Fuzz-generated Babel pattern strings (pattern= parameter)
- FluentNumber precision (CLDR v operand) correctness verification
- Currency-specific decimal digit enforcement (JPY=0, BHD=3)
- Type coercion across int/float/Decimal/FluentNumber inputs
- Cross-locale formatting consistency (same value, multiple locales)
- Edge value handling (NaN, Inf, -0.0, extreme magnitudes)

FunctionRegistry lifecycle, parameter mapping, and locale injection protocol
are covered by fuzz_bridge.py. This fuzzer focuses exclusively on the
formatting output correctness boundary.

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import atexit
import logging
import pathlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isnan
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:  # noqa: SIM105 - need module ref for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - need module ref for check_dependencies
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    pass

from fuzz_common import (  # noqa: E402 - after dependency capture  # pylint: disable=C0413
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class BuiltinsMetrics:
    """Domain-specific metrics for builtins fuzzer."""

    # Per-function call counts
    number_calls: int = 0
    datetime_calls: int = 0
    currency_calls: int = 0

    # Precision tracking
    precision_checks: int = 0
    precision_violations: int = 0

    # Cross-locale tests
    cross_locale_tests: int = 0
    cross_locale_empty_results: int = 0

    # Type coercion tests
    type_coercion_tests: int = 0

    # Custom pattern tests
    custom_pattern_tests: int = 0

    # Edge value encounters
    edge_nan_count: int = 0
    edge_inf_count: int = 0
    edge_zero_count: int = 0

    # Rounding oracle: ROUND_HALF_EVEN verification (Babel default)
    rounding_oracle_checks: int = 0
    rounding_oracle_violations: int = 0

    # Input domain coverage: min_frac > max_frac cases
    min_gt_max_tests: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=500,
    fuzzer_name="builtins",
    fuzzer_target="NUMBER, DATETIME, CURRENCY (Babel boundary)",
)
_domain = BuiltinsMetrics()

# Pattern weights: (name, weight) - focused on Babel boundary, no bridge overlap
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("number_basic", 12),
    ("number_precision", 15),
    ("number_edges", 8),
    ("number_type_variety", 8),
    ("datetime_styles", 10),
    ("datetime_edges", 8),
    ("datetime_timezone_stress", 6),
    ("currency_codes", 12),
    ("currency_precision", 10),
    ("currency_cross_locale", 8),
    ("custom_pattern", 8),
    ("cross_locale_consistency", 8),
    ("error_paths", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class BuiltinsFuzzError(Exception):
    """Raised when a fuzzer invariant is violated."""


# Allowed exceptions from Babel / formatting functions
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OverflowError,
    InvalidOperation,
    OSError,
    ArithmeticError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "builtins"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Per-function call counts
    stats["number_calls"] = _domain.number_calls
    stats["datetime_calls"] = _domain.datetime_calls
    stats["currency_calls"] = _domain.currency_calls

    # Precision tracking
    stats["precision_checks"] = _domain.precision_checks
    stats["precision_violations"] = _domain.precision_violations

    # Cross-locale
    stats["cross_locale_tests"] = _domain.cross_locale_tests
    stats["cross_locale_empty_results"] = _domain.cross_locale_empty_results

    # Type coercion
    stats["type_coercion_tests"] = _domain.type_coercion_tests

    # Custom patterns
    stats["custom_pattern_tests"] = _domain.custom_pattern_tests

    # Edge values
    stats["edge_nan_count"] = _domain.edge_nan_count
    stats["edge_inf_count"] = _domain.edge_inf_count
    stats["edge_zero_count"] = _domain.edge_zero_count

    # Rounding oracle
    stats["rounding_oracle_checks"] = _domain.rounding_oracle_checks
    stats["rounding_oracle_violations"] = _domain.rounding_oracle_violations

    # Input domain coverage
    stats["min_gt_max_tests"] = _domain.min_gt_max_tests

    return stats


_REPORT_FILENAME = "fuzz_builtins_report.json"


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    pass


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
    Decimal(0), Decimal(1), Decimal("1.0"), Decimal("1.00"),
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
_MAX_TIMESTAMP = 253402300799.0  # 9999-12-31T23:59:59 UTC


# --- Helpers ---

def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(2, 15))


def _make_decimal(fdp: atheris.FuzzedDataProvider) -> Decimal:
    """Generate a Decimal from fuzzed float, including NaN and Infinity.

    Decimal(str(float('nan'))) -> Decimal('NaN') and
    Decimal(str(float('inf'))) -> Decimal('Infinity') without raising;
    no exception handler needed.
    """
    return Decimal(str(fdp.ConsumeFloat()))


def _values_match(a: object, b: object) -> bool:
    """NaN-safe value comparison for cross-locale invariant checks.

    IEEE 754 defines NaN != NaN, so naive != comparison falsely reports
    value drift when both sides are NaN. This function treats two NaN
    values of the same type as matching.
    """
    if isinstance(a, Decimal) and isinstance(b, Decimal) and a.is_nan() and b.is_nan():
        return True
    if isinstance(a, float) and isinstance(b, float) and isnan(a) and isnan(b):
        return True
    return a == b


def _extract_oracle_digits(formatted: str, locale: str) -> str | None:
    """Extract absolute numeric digits from a formatted string for oracle comparison.

    Uses Babel to look up locale-specific decimal and grouping separators.
    Returns None when digit extraction is not possible (non-ASCII digits,
    ambiguous separators, or unknown locale).

    The extraction algorithm:
    1. Skip if any digit character is non-ASCII (e.g., ar-EG Arabic-Indic,
       hi-IN Devanagari); these cannot be compared against ASCII oracle values.
    2. Look up locale decimal and group symbols via Babel.
    3. Remove group separators (critical for de-DE where group sep is '.').
    4. Replace decimal separator with ASCII '.'.
    5. Strip all remaining non-digit, non-dot characters (currency codes,
       whitespace, signs) via regex. Whitespace-based group separators
       (lv-LV, fr-FR thin-space) are handled by this final strip.
    """
    # Skip locales where any digit character is non-ASCII.
    if any(c.isdigit() and not c.isascii() for c in formatted):
        return None
    try:
        # Deferred import: Babel is optional at ftllexengine package level.
        # At fuzzing time Babel is always present (required by the functions
        # under test), but the import is deferred to match project conventions.
        from babel.numbers import (
            get_decimal_symbol,
            get_group_symbol,
        )
        # Babel expects underscore-separated locale IDs ('en_US', 'de_DE');
        # ftllexengine uses BCP 47 hyphen-separated codes ('en-US', 'de-DE').
        babel_locale = locale.replace("-", "_")
        decimal_sym = get_decimal_symbol(babel_locale)
        group_sym = get_group_symbol(babel_locale)
    except ValueError:
        # Babel raises UnknownLocaleError (ValueError subclass) for invalid locales.
        return None
    # Guard: ambiguous separators (same symbol for both) cannot be parsed reliably.
    if decimal_sym == group_sym:
        return None
    # Step 1: remove group separators before replacing decimal separator.
    # This is critical when group_sym == '.' (e.g., de-DE): removing it first
    # prevents '1.234,56' → '1.234.56' (two dots, wrong result).
    normalized = formatted.replace(group_sym, "").replace(decimal_sym, ".")
    # Step 2: strip all remaining non-digit, non-dot characters (currency codes,
    # whitespace, signs). Handles whitespace-variant group seps (lv-LV, fr-FR).
    digits = re.sub(r"[^\d.]", "", normalized)
    return digits or None

__all__ = [name for name in globals() if not name.startswith("__")]
