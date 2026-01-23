#!/usr/bin/env python3
"""ISO Introspection Fuzzer (Atheris).

Targets ISO 3166-1 territory and ISO 4217 currency introspection APIs.
Tests cache integrity, type guard correctness, and Babel data access patterns.

Built for Python 3.13+ using modern PEPs (695, 742, 585, 563).
"""

from __future__ import annotations

import atexit
import json
import logging
import string
import sys
from typing import Any

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]
type LocaleStr = str

# Crash-proof reporting: ensure summary is always emitted
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}


def _emit_final_report() -> None:
    """Emit JSON summary on exit (crash-proof reporting)."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)


atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("-" * 80, file=sys.stderr)
    print("ERROR: 'atheris' not found.", file=sys.stderr)
    print("On macOS, install LLVM: brew install llvm", file=sys.stderr)
    print("Then run: ./scripts/check-atheris.sh --install", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# Suppress logging during fuzzing
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.introspection.iso import (
        BabelImportError,
        CurrencyInfo,
        TerritoryInfo,
        clear_iso_cache,
        get_currency,
        get_territory,
        get_territory_currency,
        is_valid_currency_code,
        is_valid_territory_code,
        list_currencies,
        list_territories,
    )


class ISOFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# Exception contract: only these exceptions are acceptable
# - BabelImportError: Babel not installed (expected in parser-only mode)
# - ValueError: Invalid locale format
# - KeyError: CLDR data lookup failure (Babel internal)
# - LookupError: Babel locale not found
ALLOWED_EXCEPTIONS = (BabelImportError, ValueError, KeyError, LookupError)

# Character sets for generating test inputs
ALPHA_UPPER = string.ascii_uppercase
ALPHA_LOWER = string.ascii_lowercase
DIGITS = string.digits

# Valid ISO 3166-1 alpha-2 codes (sample for seed generation)
SAMPLE_TERRITORIES = ["US", "GB", "DE", "FR", "JP", "CN", "IN", "BR", "AU", "LV"]
# Valid ISO 4217 currency codes (sample for seed generation)
SAMPLE_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "INR", "BRL", "AUD", "CHF", "CAD"]
# Locales for testing
SAMPLE_LOCALES = ["en", "en_US", "de_DE", "ja_JP", "lv_LV", "ar_SA", "zh_CN", ""]


def generate_territory_code(fdp: Any) -> str:
    """Generate a potential ISO 3166-1 alpha-2 code."""
    if not fdp.remaining_bytes():
        return "US"

    strategy = fdp.ConsumeIntInRange(0, 4)

    match strategy:
        case 0:
            # Valid code from sample
            return fdp.PickValueInList(SAMPLE_TERRITORIES)
        case 1:
            # Random 2-letter uppercase
            c1 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2
        case 2:
            # Invalid input: lowercase
            c1 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2
        case 3:
            # Invalid input: wrong length
            length = fdp.ConsumeIntInRange(1, 5)
            if length == 2:
                length = 3  # Force invalid
            return fdp.ConsumeUnicodeNoSurrogates(length)
        case _:
            # Unicode chaos
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 10))


def generate_currency_code(fdp: Any) -> str:
    """Generate a potential ISO 4217 currency code."""
    if not fdp.remaining_bytes():
        return "USD"

    strategy = fdp.ConsumeIntInRange(0, 4)

    match strategy:
        case 0:
            # Valid code from sample
            return fdp.PickValueInList(SAMPLE_CURRENCIES)
        case 1:
            # Random 3-letter uppercase
            c1 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            c3 = ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2 + c3
        case 2:
            # Invalid input: lowercase
            c1 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c2 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            c3 = ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            return c1 + c2 + c3
        case 3:
            # Invalid input: wrong length
            length = fdp.ConsumeIntInRange(1, 6)
            if length == 3:
                length = 4  # Force invalid
            return fdp.ConsumeUnicodeNoSurrogates(length)
        case _:
            # Unicode chaos
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 10))


def generate_locale(fdp: Any) -> LocaleStr:
    """Generate a locale string for testing."""
    if not fdp.remaining_bytes():
        return "en"

    strategy = fdp.ConsumeIntInRange(0, 3)

    match strategy:
        case 0:
            # Valid locale from sample
            return fdp.PickValueInList(SAMPLE_LOCALES)
        case 1:
            # Random locale pattern: xx or xx_XX
            lang = (
                ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
                + ALPHA_LOWER[fdp.ConsumeIntInRange(0, 25)]
            )
            if fdp.ConsumeBool():
                territory = (
                    ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
                    + ALPHA_UPPER[fdp.ConsumeIntInRange(0, 25)]
                )
                return f"{lang}_{territory}"
            return lang
        case 2:
            # Invalid input: special characters
            return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
        case _:
            # Edge case: very long locale
            return "x" * fdp.ConsumeIntInRange(100, 300)


def _verify_territory_invariants(
    code: str, _locale: str, result: TerritoryInfo | None
) -> None:
    """Verify TerritoryInfo invariants."""
    if result is None:
        return

    # Invariant: alpha2 matches input (case-normalized)
    if result.alpha2 != code.upper():
        msg = f"TerritoryInfo.alpha2 mismatch: {result.alpha2!r} != {code.upper()!r}"
        raise ISOFuzzError(msg)

    # Invariant: name is non-empty string
    if not isinstance(result.name, str) or not result.name:
        msg = f"TerritoryInfo.name invalid: {result.name!r}"
        raise ISOFuzzError(msg)

    # Invariant: default_currency is None or valid 3-letter code
    if result.default_currency is not None:
        if not isinstance(result.default_currency, str):
            msg = f"TerritoryInfo.default_currency type error: {type(result.default_currency)}"
            raise ISOFuzzError(msg)
        if len(result.default_currency) != 3:
            msg = f"TerritoryInfo.default_currency invalid length: {result.default_currency!r}"
            raise ISOFuzzError(msg)

    # Invariant: Hashable (can be used in sets/dicts)
    try:
        _ = hash(result)
        _ = {result}
    except TypeError as e:
        msg = f"TerritoryInfo not hashable: {e}"
        raise ISOFuzzError(msg) from e


def _verify_currency_invariants(
    code: str, _locale: str, result: CurrencyInfo | None
) -> None:
    """Verify CurrencyInfo invariants."""
    if result is None:
        return

    # Invariant: code matches input (case-normalized)
    if result.code != code.upper():
        msg = f"CurrencyInfo.code mismatch: {result.code!r} != {code.upper()!r}"
        raise ISOFuzzError(msg)

    # Invariant: name is non-empty string
    if not isinstance(result.name, str) or not result.name:
        msg = f"CurrencyInfo.name invalid: {result.name!r}"
        raise ISOFuzzError(msg)

    # Invariant: symbol is non-empty string
    if not isinstance(result.symbol, str) or not result.symbol:
        msg = f"CurrencyInfo.symbol invalid: {result.symbol!r}"
        raise ISOFuzzError(msg)

    # Invariant: decimal_digits is valid (0, 2, 3, or 4)
    if result.decimal_digits not in (0, 2, 3, 4):
        msg = f"CurrencyInfo.decimal_digits invalid: {result.decimal_digits}"
        raise ISOFuzzError(msg)

    # Invariant: Hashable (can be used in sets/dicts)
    try:
        _ = hash(result)
        _ = {result}
    except TypeError as e:
        msg = f"CurrencyInfo not hashable: {e}"
        raise ISOFuzzError(msg) from e


def _verify_type_guard_consistency(fdp: Any) -> None:
    """Verify type guards are consistent with lookup functions."""
    territory_code = generate_territory_code(fdp)
    currency_code = generate_currency_code(fdp)

    try:
        # Type guard should match lookup result
        is_valid_territory = is_valid_territory_code(territory_code)
        territory_result = get_territory(territory_code)

        if is_valid_territory and territory_result is None:
            msg = f"Type guard says valid but lookup returned None: {territory_code!r}"
            raise ISOFuzzError(msg)
        if not is_valid_territory and territory_result is not None:
            msg = f"Type guard says invalid but lookup succeeded: {territory_code!r}"
            raise ISOFuzzError(msg)

        is_valid_currency = is_valid_currency_code(currency_code)
        currency_result = get_currency(currency_code)

        if is_valid_currency and currency_result is None:
            msg = f"Type guard says valid but lookup returned None: {currency_code!r}"
            raise ISOFuzzError(msg)
        if not is_valid_currency and currency_result is not None:
            msg = f"Type guard says invalid but lookup succeeded: {currency_code!r}"
            raise ISOFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for edge cases


def _verify_cache_consistency(fdp: Any) -> None:
    """Verify cache produces consistent results."""
    territory_code = fdp.PickValueInList(SAMPLE_TERRITORIES)
    currency_code = fdp.PickValueInList(SAMPLE_CURRENCIES)
    locale = fdp.PickValueInList(["en", "de", "ja"])

    try:
        # First lookup
        t1 = get_territory(territory_code, locale)
        c1 = get_currency(currency_code, locale)

        # Second lookup (should hit cache)
        t2 = get_territory(territory_code, locale)
        c2 = get_currency(currency_code, locale)

        # Invariant: Cache returns identical objects
        if t1 is not t2:
            msg = f"Cache returned different TerritoryInfo objects for {territory_code!r}"
            raise ISOFuzzError(msg)
        if c1 is not c2:
            msg = f"Cache returned different CurrencyInfo objects for {currency_code!r}"
            raise ISOFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


def _verify_list_functions(fdp: Any) -> None:
    """Verify list_territories and list_currencies invariants."""
    locale = generate_locale(fdp)

    try:
        territories = list_territories(locale)
        currencies = list_currencies(locale)

        # Invariant: Returns frozenset
        if not isinstance(territories, frozenset):
            msg = f"list_territories returned {type(territories)}, expected frozenset"
            raise ISOFuzzError(msg)
        if not isinstance(currencies, frozenset):
            msg = f"list_currencies returned {type(currencies)}, expected frozenset"
            raise ISOFuzzError(msg)

        # Invariant: All elements are correct type
        for t in territories:
            if not isinstance(t, TerritoryInfo):
                msg = f"list_territories contains non-TerritoryInfo: {type(t)}"
                raise ISOFuzzError(msg)
        for c in currencies:
            if not isinstance(c, CurrencyInfo):
                msg = f"list_currencies contains non-CurrencyInfo: {type(c)}"
                raise ISOFuzzError(msg)

        # Invariant: Non-empty for valid locales
        if locale in ["en", "de", "ja"]:
            if len(territories) < 200:  # CLDR has 200+ territories
                msg = f"list_territories returned too few: {len(territories)}"
                raise ISOFuzzError(msg)
            if len(currencies) < 100:  # CLDR has 100+ currencies
                msg = f"list_currencies returned too few: {len(currencies)}"
                raise ISOFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


def _report_finding(
    e: Exception, territory_code: str, currency_code: str, locale: str
) -> None:
    """Report a finding with context information."""
    _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
    _fuzz_stats["status"] = "finding"

    print("\n" + "=" * 80)
    print("[FINDING] ISO INTROSPECTION STABILITY BREACH")
    print("=" * 80)
    print(f"Exception Type: {type(e).__module__}.{type(e).__name__}")
    print(f"Error Message:  {e}")
    print(f"Territory Code: {territory_code!r}")
    print(f"Currency Code:  {currency_code!r}")
    print(f"Locale:         {locale!r}")
    print("-" * 80)
    print("NEXT STEPS:")
    print("  1. Reproduce:  ./scripts/fuzz.sh --repro .fuzz_corpus/crash_*")
    print("  2. Create test in tests/test_introspection_iso.py")
    print("  3. Fix & Verify")
    print("=" * 80)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz ISO introspection APIs."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Randomly clear cache to test cold paths
    if fdp.ConsumeBool() and fdp.ConsumeBool():
        clear_iso_cache()

    # Generate test inputs
    territory_code = generate_territory_code(fdp)
    currency_code = generate_currency_code(fdp)
    locale = generate_locale(fdp)

    try:
        # Test get_territory
        territory = get_territory(territory_code, locale)
        _verify_territory_invariants(territory_code, locale, territory)

        # Test get_currency
        currency = get_currency(currency_code, locale)
        _verify_currency_invariants(currency_code, locale, currency)

        # Test get_territory_currency
        if territory is not None:
            default_currency = get_territory_currency(territory_code)
            if default_currency is not None and len(default_currency) != 3:
                msg = f"get_territory_currency returned invalid: {default_currency!r}"
                raise ISOFuzzError(msg)

        # Verify type guard consistency
        if fdp.ConsumeBool():
            _verify_type_guard_consistency(fdp)

        # Verify cache consistency
        if fdp.ConsumeBool():
            _verify_cache_consistency(fdp)

        # Verify list functions
        if fdp.ConsumeBool():
            _verify_list_functions(fdp)

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid input or missing Babel
    except ISOFuzzError:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"
        raise
    except Exception as e:
        _report_finding(e, territory_code, currency_code, locale)
        msg = f"{type(e).__name__}: {e}"
        raise ISOFuzzError(msg) from e


def main() -> None:
    """Run the ISO introspection fuzzer."""
    print("\n" + "=" * 80)
    print("ISO Introspection Fuzzer (Python 3.13 Edition)")
    print("=" * 80)
    print("Targets: get_territory, get_currency, type guards, cache")
    print("Contract: Only BabelImportError, ValueError, KeyError, LookupError allowed")
    print("Stopping: Press Ctrl+C at any time (findings auto-saved)")
    print("=" * 80 + "\n")

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
