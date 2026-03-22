#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: parse_currency - Locale-aware currency parsing and symbol resolution
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Locale-aware currency parsing fuzzer (Atheris).

Targets:
- ftllexengine.parsing.currency.parse_currency
- ftllexengine.parsing.currency symbol-resolution helpers
- ftllexengine.parsing.guards.is_valid_currency

Concern boundary: this fuzzer targets the text-to-(Decimal, ISO code) surface.
It covers:
- ISO-code parsing and symbol parsing
- ambiguous-symbol resolution via default_currency and infer_from_locale
- longest-match regex behavior for multi-character symbols
- cache clearing and semantic stability
- public soft-error contracts and currency type guards

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
from decimal import Decimal
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


@dataclass
class ParseCurrencyMetrics:
    """Domain-specific metrics for parse_currency fuzzing."""

    parse_calls: int = 0
    parse_successes: int = 0
    soft_errors: int = 0
    ambiguous_tests: int = 0
    longest_match_checks: int = 0
    cache_cycles: int = 0
    guard_checks: int = 0
    symbol_resolution_checks: int = 0


class ParseCurrencyFuzzError(Exception):
    """Raised when a parse_currency invariant is violated."""


_ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OSError,
    UnicodeEncodeError,
)

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("iso_code_values", 14),
    ("default_currency_ambiguous", 12),
    ("infer_from_locale", 12),
    ("ambiguous_symbol_resolution", 10),
    ("longest_symbol_match", 10),
    ("invalid_currency_inputs", 12),
    ("cache_clear_cycle", 10),
    ("type_guard_contract", 10),
    ("raw_unicode_stability", 12),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

_ISO_CASES: tuple[tuple[str, str, Decimal, str], ...] = (
    ("USD 1,234.56", "en_US", Decimal("1234.56"), "USD"),
    ("EUR100.50", "en_US", Decimal("100.50"), "EUR"),
    ("JPY 1000", "en_US", Decimal(1000), "JPY"),
    ("BHD 1.005", "en_US", Decimal("1.005"), "BHD"),
)

_DEFAULT_CASES: tuple[tuple[str, str, str, Decimal], ...] = (
    ("$100", "en_US", "USD", Decimal(100)),
    ("$100", "en_CA", "CAD", Decimal(100)),
    ("£100", "en_GB", "GBP", Decimal(100)),
)

_INFER_CASES: tuple[tuple[str, str, Decimal, str], ...] = (
    ("$100", "en_CA", Decimal(100), "CAD"),
    ("$100", "en_US", Decimal(100), "USD"),
    ("¥100", "zh_CN", Decimal(100), "CNY"),
    ("¥100", "ja_JP", Decimal(100), "JPY"),
)

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "parse_currency"
_REPORT_FILENAME = "fuzz_parse_currency_report.json"

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=250,
    fuzzer_name="parse_currency",
    fuzzer_target="parse_currency, currency symbol resolution, is_valid_currency",
    pattern_intended_weights={name: float(weight) for name, weight in _PATTERN_WEIGHTS},
)
_domain = ParseCurrencyMetrics()


def _build_stats_dict() -> dict[str, Any]:
    """Build stats dictionary including parse_currency metrics."""
    stats = build_base_stats_dict(_state)
    stats["parse_calls"] = _domain.parse_calls
    stats["parse_successes"] = _domain.parse_successes
    stats["soft_errors"] = _domain.soft_errors
    stats["ambiguous_tests"] = _domain.ambiguous_tests
    stats["longest_match_checks"] = _domain.longest_match_checks
    stats["cache_cycles"] = _domain.cache_cycles
    stats["guard_checks"] = _domain.guard_checks
    stats["symbol_resolution_checks"] = _domain.symbol_resolution_checks
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint report."""
    emit_checkpoint_report(
        _state, _build_stats_dict(), _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit crash-proof final report."""
    emit_final_report(
        _state, _build_stats_dict(), _REPORT_DIR, _REPORT_FILENAME,
    )


atexit.register(_emit_report)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.parsing import is_valid_currency
    from ftllexengine.parsing.currency import (
        _get_currency_pattern,
        clear_currency_caches,
        parse_currency,
        resolve_ambiguous_symbol,
    )


def _assert_parse_contract(
    result: tuple[Decimal, str] | None,
    errors: tuple[FrozenFluentError, ...],
) -> None:
    """Validate parse_currency's public result contract."""
    if not isinstance(errors, tuple):
        msg = f"errors must be tuple[FrozenFluentError, ...], got {type(errors).__name__}"
        raise ParseCurrencyFuzzError(msg)

    if any(not isinstance(error, FrozenFluentError) for error in errors):
        msg = "parse_currency returned non-FrozenFluentError entries"
        raise ParseCurrencyFuzzError(msg)

    if result is not None and errors:
        msg = f"parse_currency returned both result={result!r} and errors"
        raise ParseCurrencyFuzzError(msg)

    if result is None and not errors:
        msg = "parse_currency returned neither result nor errors"
        raise ParseCurrencyFuzzError(msg)


def _pattern_iso_code_values(fdp: atheris.FuzzedDataProvider) -> None:
    """ISO currency codes parse directly to exact amount/code pairs."""
    _domain.parse_calls += 1
    value, locale, expected_amount, expected_code = fdp.PickValueInList(list(_ISO_CASES))
    result, errors = parse_currency(value, locale)
    _assert_parse_contract(result, errors)

    if result != (expected_amount, expected_code):
        msg = (
            f"parse_currency({value!r}, {locale!r}) -> {result!r}, "
            f"expected {(expected_amount, expected_code)!r}"
        )
        raise ParseCurrencyFuzzError(msg)

    _domain.parse_successes += 1


def _pattern_default_currency_ambiguous(fdp: atheris.FuzzedDataProvider) -> None:
    """Ambiguous symbols resolve via default_currency when explicitly supplied."""
    _domain.parse_calls += 1
    _domain.ambiguous_tests += 1
    value, locale, default_currency, expected_amount = fdp.PickValueInList(list(_DEFAULT_CASES))
    result, errors = parse_currency(
        value, locale, default_currency=default_currency,
    )
    _assert_parse_contract(result, errors)

    if result != (expected_amount, default_currency):
        msg = (
            f"default_currency resolution mismatch: {result!r} != "
            f"{(expected_amount, default_currency)!r}"
        )
        raise ParseCurrencyFuzzError(msg)

    _domain.parse_successes += 1


def _pattern_infer_from_locale(fdp: atheris.FuzzedDataProvider) -> None:
    """Ambiguous symbols resolve from locale inference when requested."""
    _domain.parse_calls += 1
    _domain.ambiguous_tests += 1
    value, locale, expected_amount, expected_code = fdp.PickValueInList(list(_INFER_CASES))
    result, errors = parse_currency(value, locale, infer_from_locale=True)
    _assert_parse_contract(result, errors)

    if result != (expected_amount, expected_code):
        msg = (
            f"infer_from_locale mismatch: {result!r} != "
            f"{(expected_amount, expected_code)!r}"
        )
        raise ParseCurrencyFuzzError(msg)

    _domain.parse_successes += 1


def _pattern_ambiguous_symbol_resolution(fdp: atheris.FuzzedDataProvider) -> None:
    """Direct helper resolution follows documented locale defaults."""
    _domain.symbol_resolution_checks += 1
    symbol, locale, expected = fdp.PickValueInList([
        ("$", "en_US", "USD"),
        ("$", "en_CA", "CAD"),
        ("£", "en_GB", "GBP"),
        ("£", "ar_EG", "EGP"),
        ("¥", "zh_CN", "CNY"),
        ("¥", "ja_JP", "JPY"),
    ])

    actual = resolve_ambiguous_symbol(symbol, locale)
    if actual != expected:
        msg = (
            f"resolve_ambiguous_symbol({symbol!r}, {locale!r}) -> "
            f"{actual!r}, expected {expected!r}"
        )
        raise ParseCurrencyFuzzError(msg)


def _pattern_longest_symbol_match(fdp: atheris.FuzzedDataProvider) -> None:
    """Compiled currency regex matches longest symbol before shorter prefixes."""
    _domain.longest_match_checks += 1
    sample, expected = fdp.PickValueInList([
        ("R$ 1.234,56", "R$"),
        ("S/ 123.45", "S/"),
        ("USD100", "USD"),
        ("£100", "£"),
        ("kr100", "kr"),
    ])
    pattern = _get_currency_pattern()
    match = pattern.search(sample)

    if match is None:
        msg = f"_get_currency_pattern().search({sample!r}) returned no match"
        raise ParseCurrencyFuzzError(msg)
    if match.group(1) != expected:
        msg = f"Longest-match failed: {match.group(1)!r} != {expected!r}"
        raise ParseCurrencyFuzzError(msg)


def _pattern_invalid_currency_inputs(fdp: atheris.FuzzedDataProvider) -> None:
    """Invalid codes and unresolved ambiguities produce soft errors."""
    _domain.parse_calls += 1
    scenario = fdp.ConsumeIntInRange(0, 4)

    match scenario:
        case 0:
            result, errors = parse_currency("$100", "en_US")
        case 1:
            result, errors = parse_currency("$100", "en_US", default_currency="usd")
        case 2:
            result, errors = parse_currency("ZZZ 100", "en_US")
        case 3:
            result, errors = parse_currency("???", "en_US")
        case _:
            result, errors = parse_currency("100", "invalid_LOCALE")

    _assert_parse_contract(result, errors)

    if result is not None:
        msg = f"Invalid parse unexpectedly succeeded with result={result!r}"
        raise ParseCurrencyFuzzError(msg)

    _domain.soft_errors += 1


def _pattern_cache_clear_cycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Cache clearing preserves semantic parse results across repeated calls."""
    _domain.cache_cycles += 1
    _domain.parse_calls += 2
    value, locale, expected_amount, expected_code = fdp.PickValueInList(list(_ISO_CASES))

    before, before_errors = parse_currency(value, locale)
    _assert_parse_contract(before, before_errors)
    clear_currency_caches()
    after, after_errors = parse_currency(value, locale)
    _assert_parse_contract(after, after_errors)

    if before != after or after != (expected_amount, expected_code):
        msg = (
            f"Cache clear changed semantic parse result: before={before!r}, "
            f"after={after!r}"
        )
        raise ParseCurrencyFuzzError(msg)

    _domain.parse_successes += 2


def _pattern_type_guard_contract(fdp: atheris.FuzzedDataProvider) -> None:
    """is_valid_currency accepts exactly finite (Decimal, code) tuples."""
    _domain.guard_checks += 1
    values: tuple[tuple[Decimal, str] | None, ...] = (
        (Decimal("1.23"), "USD"),
        (Decimal(0), "EUR"),
        (Decimal("NaN"), "USD"),
        (Decimal("Infinity"), "USD"),
        None,
    )
    value = fdp.PickValueInList(list(values))
    expected = value is not None and value[0].is_finite()
    if is_valid_currency(value) is not expected:
        msg = f"is_valid_currency({value!r}) mismatch: expected {expected}"
        raise ParseCurrencyFuzzError(msg)


def _pattern_raw_unicode_stability(fdp: atheris.FuzzedDataProvider) -> None:
    """Arbitrary Unicode inputs must preserve parse_currency result shape."""
    _domain.parse_calls += 1
    value = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 64))
    locale = (
        fdp.PickValueInList(["en_US", "en_CA", "ja_JP", "zh_CN"])
        if fdp.ConsumeBool()
        else fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 16))
    )
    default_currency = (
        fdp.PickValueInList(["USD", "CAD", "EUR", "JPY"])
        if fdp.ConsumeBool()
        else None
    )

    result, errors = parse_currency(
        value, locale,
        default_currency=default_currency,
        infer_from_locale=fdp.ConsumeBool(),
    )
    _assert_parse_contract(result, errors)

    if result is None:
        _domain.soft_errors += 1
        return

    amount, code = result
    if not isinstance(amount, Decimal) or not isinstance(code, str):
        msg = f"parse_currency returned invalid result types: {result!r}"
        raise ParseCurrencyFuzzError(msg)
    if len(code) != 3:
        msg = f"parse_currency returned non-ISO code {code!r}"
        raise ParseCurrencyFuzzError(msg)

    _domain.parse_successes += 1


_PATTERN_DISPATCH: dict[str, Any] = {
    "iso_code_values": _pattern_iso_code_values,
    "default_currency_ambiguous": _pattern_default_currency_ambiguous,
    "infer_from_locale": _pattern_infer_from_locale,
    "ambiguous_symbol_resolution": _pattern_ambiguous_symbol_resolution,
    "longest_symbol_match": _pattern_longest_symbol_match,
    "invalid_currency_inputs": _pattern_invalid_currency_inputs,
    "cache_clear_cycle": _pattern_cache_clear_cycle,
    "type_guard_contract": _pattern_type_guard_contract,
    "raw_unicode_stability": _pattern_raw_unicode_stability,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point for currency parsing invariants."""
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
        _PATTERN_DISPATCH[pattern](fdp)

    except ParseCurrencyFuzzError:
        _state.findings += 1
        raise

    except _ALLOWED_EXCEPTIONS as exc:
        error_key = f"{type(exc).__name__}_{str(exc)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    except Exception as exc:  # pylint: disable=broad-exception-caught
        error_key = f"{type(exc).__name__}_{str(exc)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            "ambiguous" in pattern
            or "match" in pattern
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
    """Run the parse_currency fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Locale-aware parse_currency fuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=250,
        help="Maximum size of in-memory seed corpus (default: 250)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="parse_currency Fuzzer (Atheris)",
        target="parse_currency, resolve_ambiguous_symbol, is_valid_currency",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=(
            "Focus:      currency text parsing, ambiguity resolution, regex priority",
        ),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
