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

Pattern Routing:
Pattern selection uses deterministic round-robin over a weighted schedule,
immune to libFuzzer's coverage-guided mutation bias. The iteration counter
cycles through the pre-computed schedule, ensuring actual distribution matches
intended weights exactly.

Metrics:
- Pattern coverage (category_validity, precision_sensitivity, etc.)
- Weight skew detection (actual vs intended distribution)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Corpus retention rate and eviction tracking
- Seed corpus management

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

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
    GC_INTERVAL,
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class PluralMetrics:
    """Domain-specific metrics for plural fuzzer."""

    babel_errors: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=100,
    fuzzer_name="plural",
    fuzzer_target="select_plural_category",
)
_domain = PluralMetrics()


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

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}

# Allowed exceptions from plural operations
ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError, InvalidOperation)


class PluralFuzzError(Exception):
    """Raised when a plural rule invariant is breached."""


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "plural"
_REPORT_FILENAME = "fuzz_plural_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["babel_errors"] = _domain.babel_errors

    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


atexit.register(_emit_report)


# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.plural_rules import select_plural_category


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
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except PluralFuzzError:
        _state.findings += 1
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        # BabelImportError should not happen in fuzz env, but handle gracefully
        if "Babel" in type(e).__name__ or "Babel" in str(e):
            error_key = f"BabelError_{type(e).__name__}"
            _domain.babel_errors += 1
        else:
            error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            "extreme" in pattern
            or "fallback" in pattern
            or (time.perf_counter() - start_time) * 1000 > 10.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


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

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Plural Rule Boundary Fuzzer (Atheris)",
        target="select_plural_category",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        mutator="Byte mutation (no custom mutator)",
    )

    run_fuzzer(
        _state,
        test_one_input=test_one_input,
    )


if __name__ == "__main__":
    main()
