#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: parse_decimal - Locale-aware decimal parsing and locale utils
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Locale-aware decimal parsing fuzzer (Atheris).

Targets:
- ftllexengine.parsing.numbers.parse_decimal
- ftllexengine.parsing.guards.is_valid_decimal
- ftllexengine.core.locale_utils helpers used by parse_decimal

Concern boundary: this fuzzer targets the text-to-Decimal API surface rather
than runtime formatting. It exercises:
- parse_decimal() success and soft-error contracts
- locale normalization equivalence (BCP-47 vs POSIX vs mixed case)
- Babel locale cache behavior and cache clearing
- get_system_locale() precedence and fallback branches
- Decimal type-guard invariants for None/NaN/Infinity

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    pass

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
class ParseDecimalMetrics:
    """Domain-specific metrics for parse_decimal fuzzing."""

    parse_calls: int = 0
    parse_successes: int = 0
    soft_errors: int = 0
    locale_variant_checks: int = 0
    type_guard_checks: int = 0
    locale_cache_checks: int = 0
    system_locale_checks: int = 0


class ParseDecimalFuzzError(Exception):
    """Raised when a parse_decimal contract is violated."""


_ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OSError,
    RuntimeError,
    UnicodeEncodeError,
)

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("canonical_values", 14),
    ("locale_variants", 12),
    ("invalid_soft_error", 12),
    ("type_guard_contract", 10),
    ("babel_locale_cache", 10),
    ("system_locale_resolution", 10),
    ("raw_unicode_stability", 12),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

_CANONICAL_CASES: tuple[tuple[str, str, Decimal], ...] = (
    ("1,234.56", "en_US", Decimal("1234.56")),
    ("-123.45", "en_US", Decimal("-123.45")),
    ("1.234,56", "de_DE", Decimal("1234.56")),
    ("1 234,56", "lv_LV", Decimal("1234.56")),
    ("42", "en_US", Decimal("42")),
    ("0,01", "de_DE", Decimal("0.01")),
)

_LOCALE_VARIANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("1,234.56", ("en-US", "en_US", "EN-us")),
    ("1.234,56", ("de-DE", "de_DE", "DE-de")),
)

_INVALID_INPUTS: tuple[str, ...] = (
    "",
    " ",
    "\x00",
    "not-a-number",
    "1,2,3",
    "++10",
    "--5",
    "12..3",
)

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "parse_decimal"
_REPORT_FILENAME = "fuzz_parse_decimal_report.json"

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=250,
    fuzzer_name="parse_decimal",
    fuzzer_target="parse_decimal, is_valid_decimal, locale_utils",
    pattern_intended_weights={name: float(weight) for name, weight in _PATTERN_WEIGHTS},
)
_domain = ParseDecimalMetrics()


def _build_stats_dict() -> dict[str, Any]:
    """Build stats dictionary including parse_decimal metrics."""
    stats = build_base_stats_dict(_state)
    stats["parse_calls"] = _domain.parse_calls
    stats["parse_successes"] = _domain.parse_successes
    stats["soft_errors"] = _domain.soft_errors
    stats["locale_variant_checks"] = _domain.locale_variant_checks
    stats["type_guard_checks"] = _domain.type_guard_checks
    stats["locale_cache_checks"] = _domain.locale_cache_checks
    stats["system_locale_checks"] = _domain.system_locale_checks
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
    from ftllexengine.core.locale_utils import (
        _get_babel_locale_normalized,
        clear_locale_cache,
        get_babel_locale,
        get_system_locale,
        normalize_locale,
    )
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.parsing import is_valid_decimal, parse_decimal


def _assert_parse_contract(
    result: Decimal | None,
    errors: tuple[FrozenFluentError, ...],
) -> None:
    """Validate parse_decimal's soft-result contract."""
    if not isinstance(errors, tuple):
        msg = f"errors must be tuple[FrozenFluentError, ...], got {type(errors).__name__}"
        raise ParseDecimalFuzzError(msg)

    if any(not isinstance(error, FrozenFluentError) for error in errors):
        msg = "parse_decimal returned non-FrozenFluentError entries"
        raise ParseDecimalFuzzError(msg)

    if result is not None and errors:
        msg = f"parse_decimal returned both result={result!r} and errors"
        raise ParseDecimalFuzzError(msg)

    if result is None and not errors:
        msg = "parse_decimal returned neither result nor errors"
        raise ParseDecimalFuzzError(msg)


def _pattern_canonical_values(fdp: atheris.FuzzedDataProvider) -> None:
    """Known locale-formatted decimals parse to exact Decimal values."""
    _domain.parse_calls += 1
    value, locale, expected = fdp.PickValueInList(list(_CANONICAL_CASES))
    result, errors = parse_decimal(value, locale)
    _assert_parse_contract(result, errors)

    if result != expected:
        msg = (
            f"parse_decimal({value!r}, {locale!r}) -> {result!r}, "
            f"expected {expected!r}"
        )
        raise ParseDecimalFuzzError(msg)
    if not is_valid_decimal(result):
        msg = f"is_valid_decimal returned False for valid result {result!r}"
        raise ParseDecimalFuzzError(msg)

    _domain.parse_successes += 1


def _pattern_locale_variants(fdp: atheris.FuzzedDataProvider) -> None:
    """Equivalent locale spellings produce identical parse results."""
    _domain.locale_variant_checks += 1
    _domain.parse_calls += 1
    value, variants = fdp.PickValueInList(list(_LOCALE_VARIANTS))

    results: list[Decimal] = []
    locale_objs: list[Any] = []
    for locale in variants:
        parsed, errors = parse_decimal(value, locale)
        _assert_parse_contract(parsed, errors)
        if parsed is None:
            msg = f"Variant locale {locale!r} failed to parse {value!r}"
            raise ParseDecimalFuzzError(msg)
        results.append(parsed)
        locale_objs.append(get_babel_locale(locale))

    if any(parsed != results[0] for parsed in results[1:]):
        msg = f"Locale variants diverged for {value!r}: {results!r}"
        raise ParseDecimalFuzzError(msg)

    if not all(obj is locale_objs[0] for obj in locale_objs[1:]):
        msg = "get_babel_locale did not canonicalize variant locale spellings to one cache entry"
        raise ParseDecimalFuzzError(msg)

    normalized = [normalize_locale(locale) for locale in variants]
    if any(code != normalized[0] for code in normalized[1:]):
        msg = f"normalize_locale disagreement across variants: {normalized!r}"
        raise ParseDecimalFuzzError(msg)

    _domain.parse_successes += len(results)


def _pattern_invalid_soft_error(fdp: atheris.FuzzedDataProvider) -> None:
    """Malformed input and unknown locales return soft errors, not results."""
    _domain.parse_calls += 1
    if fdp.ConsumeBool():
        value = fdp.PickValueInList(list(_INVALID_INPUTS))
        locale = "en_US"
    else:
        value = "123.45"
        locale = f"invalid_{fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 8)) or 'x'}"

    result, errors = parse_decimal(value, locale)
    _assert_parse_contract(result, errors)

    if result is not None:
        msg = f"Invalid parse unexpectedly returned result={result!r}"
        raise ParseDecimalFuzzError(msg)

    _domain.soft_errors += 1


def _pattern_type_guard_contract(fdp: atheris.FuzzedDataProvider) -> None:
    """is_valid_decimal accepts finite Decimal only."""
    _domain.type_guard_checks += 1
    valid_values: tuple[Decimal | None, ...] = (
        Decimal("0"),
        Decimal("1.23"),
        Decimal("-42.5"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        None,
    )
    value = fdp.PickValueInList(list(valid_values))

    expected = (
        value is not None
        and isinstance(value, Decimal)
        and value.is_finite()
    )
    if is_valid_decimal(value) is not expected:
        msg = f"is_valid_decimal({value!r}) mismatch: expected {expected}"
        raise ParseDecimalFuzzError(msg)


def _pattern_babel_locale_cache(fdp: atheris.FuzzedDataProvider) -> None:
    """Babel locale cache canonicalizes variants and is cleared correctly."""
    _domain.locale_cache_checks += 1
    locale = fdp.PickValueInList(["en-US", "de-DE", "fr-FR"])
    normalized = normalize_locale(locale)

    clear_locale_cache()
    if _get_babel_locale_normalized.cache_info().currsize != 0:
        msg = "clear_locale_cache() did not empty cache"
        raise ParseDecimalFuzzError(msg)

    loc_1 = get_babel_locale(locale)
    loc_2 = get_babel_locale(locale.replace("-", "_"))
    loc_3 = get_babel_locale(locale.upper())

    if not (loc_1 is loc_2 and loc_2 is loc_3):
        msg = "Locale cache did not reuse object identity across canonical variants"
        raise ParseDecimalFuzzError(msg)

    if _get_babel_locale_normalized.cache_info().currsize != 1:
        msg = (
            "Expected exactly one normalized cache entry, got "
            f"{_get_babel_locale_normalized.cache_info().currsize}"
        )
        raise ParseDecimalFuzzError(msg)

    if _get_babel_locale_normalized.cache_info().hits < 2:
        msg = "Expected cache hits after repeated locale lookups"
        raise ParseDecimalFuzzError(msg)

    if normalized != normalize_locale(locale):
        msg = f"normalize_locale instability for {locale!r}"
        raise ParseDecimalFuzzError(msg)


def _pattern_system_locale_resolution(fdp: atheris.FuzzedDataProvider) -> None:
    """get_system_locale obeys precedence and fallback contracts."""
    _domain.system_locale_checks += 1
    scenario = fdp.ConsumeIntInRange(0, 4)

    env: dict[str, str] = {"LC_ALL": "", "LC_MESSAGES": "", "LANG": ""}
    mock_locale: tuple[str | None, str | None]

    match scenario:
        case 0:
            mock_locale = ("de_DE", "UTF-8")
            expected = "de_de"
            raise_on_failure = False
        case 1:
            mock_locale = (None, None)
            env["LC_ALL"] = "fr_FR.UTF-8"
            expected = "fr_fr"
            raise_on_failure = False
        case 2:
            mock_locale = (None, None)
            env["LC_MESSAGES"] = "lv_LV.UTF-8"
            expected = "lv_lv"
            raise_on_failure = False
        case 3:
            mock_locale = (None, None)
            expected = "en_us"
            raise_on_failure = False
        case _:
            mock_locale = (None, None)
            expected = ""
            raise_on_failure = True

    with (
        patch("locale.getlocale", return_value=mock_locale),
        patch.dict(os.environ, env, clear=False),
    ):
        if raise_on_failure:
            try:
                get_system_locale(raise_on_failure=True)
            except RuntimeError:
                return
            msg = (
                "get_system_locale(raise_on_failure=True) did not raise on "
                "empty environment"
            )
            raise ParseDecimalFuzzError(msg)

        actual = get_system_locale(raise_on_failure=False)
        if actual != expected:
            msg = f"get_system_locale() -> {actual!r}, expected {expected!r}"
            raise ParseDecimalFuzzError(msg)


def _pattern_raw_unicode_stability(fdp: atheris.FuzzedDataProvider) -> None:
    """Arbitrary Unicode inputs must preserve parse_decimal result shape."""
    _domain.parse_calls += 1
    value = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 64))
    locale = (
        fdp.PickValueInList(["en_US", "de_DE", "lv_LV"])
        if fdp.ConsumeBool()
        else fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 16))
    )

    result, errors = parse_decimal(value, locale)
    _assert_parse_contract(result, errors)

    if result is not None and not isinstance(result, Decimal):
        msg = f"parse_decimal returned non-Decimal result type {type(result).__name__}"
        raise ParseDecimalFuzzError(msg)

    if result is None:
        _domain.soft_errors += 1
    else:
        _domain.parse_successes += 1


_PATTERN_DISPATCH: dict[str, Any] = {
    "canonical_values": _pattern_canonical_values,
    "locale_variants": _pattern_locale_variants,
    "invalid_soft_error": _pattern_invalid_soft_error,
    "type_guard_contract": _pattern_type_guard_contract,
    "babel_locale_cache": _pattern_babel_locale_cache,
    "system_locale_resolution": _pattern_system_locale_resolution,
    "raw_unicode_stability": _pattern_raw_unicode_stability,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point for parse_decimal and locale utility invariants."""
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

    except ParseDecimalFuzzError:
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
            "locale" in pattern
            or "cache" in pattern
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
    """Run the parse_decimal fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Locale-aware parse_decimal and locale-utils fuzzer",
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
        title="parse_decimal Fuzzer (Atheris)",
        target="parse_decimal, is_valid_decimal, locale_utils",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=(
            "Focus:      locale-aware decimal parsing and locale normalization",
        ),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
