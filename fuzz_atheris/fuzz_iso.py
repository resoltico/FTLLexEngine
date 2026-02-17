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
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import string
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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

# --- Domain Metrics ---


@dataclass
class ISOMetrics:
    """Domain-specific metrics for ISO introspection fuzzer."""

    cache_clear_cycles: int = 0
    cross_reference_checks: int = 0
    type_guard_checks: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    fuzzer_name="iso",
    fuzzer_target="get_territory, get_currency, type guards, cache, list functions",
)
_domain = ISOMetrics()


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

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class ISOFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# Exception contract
ALLOWED_EXCEPTIONS = (ValueError, KeyError, LookupError)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "iso"
_REPORT_FILENAME = "fuzz_iso_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["cache_clear_cycles"] = _domain.cache_clear_cycles
    stats["cross_reference_checks"] = _domain.cross_reference_checks
    stats["type_guard_checks"] = _domain.type_guard_checks
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

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
    _domain.type_guard_checks += 1
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
    _domain.cache_clear_cycles += 1
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
    _domain.cross_reference_checks += 1
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

    except ISOFuzzError:
        _state.findings += 1
        raise

    except _ALLOWED:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = "stress" in pattern or "cross" in pattern or (
            (time.perf_counter() - start_time) * 1000 > 50.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the ISO introspection fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="ISO introspection fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=100,
        help="Maximum size of in-memory seed corpus (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="ISO Introspection Fuzzer (Atheris)",
        target="get_territory, get_currency, type guards, cache, list functions",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
