#!/usr/bin/env python3
# @lint-plugin: ISO4217
"""Verify ISO 4217 decimal digits and active-code freshness against Babel CLDR.

Compares ``ISO_4217_DECIMAL_DIGITS`` and ``ISO_4217_VALID_CODES`` against
Babel CLDR data. Reports three categories of findings:

1. **Decimal-digit discrepancies** (informational, expected):
   Cases where ISO 4217 and CLDR disagree. Our data follows the ISO standard;
   Babel reflects practical usage. These differences are documented and expected.
   Examples: IQD (ISO=3 fils, CLDR=0 unused), XAU (ISO=0, CLDR=2 default).

2. **Stale active codes** (error — exits 1):
   Codes in ``ISO_4217_VALID_CODES`` that Babel identifies as retired via a
   date-range suffix in the currency name (e.g. "Leone (1964—2022)"). These
   indicate that our active-code set is out of date and ``get_currency_decimal_
   digits()`` returns a non-None value for a retired currency.

3. **Actionable coverage gaps** (error — exits 1):
   Babel codes absent from ``ISO_4217_VALID_CODES`` with non-default, non-zero
   precision. These are active currencies with unusual decimal digits that we
   are missing an explicit entry for.

**Unverifiable divergences** (Babel=0, our default=2) are split into:
   - Retired codes not in ``ISO_4217_VALID_CODES``: already handled correctly
     (``get_currency_decimal_digits`` returns None for them). No concern.
   - Active codes in ``ISO_4217_VALID_CODES`` with ISO=2/Babel=0: we return
     the ISO-standard value (2). These are currencies whose minor units exist
     per ISO 4217 but are not used in practice (IRR, KPW, LAK, etc.).

Exit codes:
    0: No stale codes, no actionable gaps (discrepancies are informational).
    1: Stale active codes detected, actionable gaps found, import failure,
       or structural errors (codes in our data not recognized by Babel).

Usage:
    verify_iso4217.py [--verbose]

Python 3.13+. Requires Babel.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Retirement detection
# ---------------------------------------------------------------------------

_RETIREMENT_MARKERS = (
    "\u2014",  # em-dash (\u2014): "Currency Name (YYYY\u2014YYYY)"
    "\u2013",  # en-dash (\u2013): "Currency Name (YYYY\u2013YYYY)"
)


def _babel_marks_as_retired(code: str) -> bool:
    """Return True if Babel's English currency name contains a date-range marker.

    Babel appends a date range in parentheses using em-dash (\u2014) or
    en-dash (\u2013) to names of historical currencies. This is a stable
    Babel convention for retired/superseded codes.
    """
    from babel.numbers import get_currency_name  # noqa: PLC0415 - Babel-optional

    name = get_currency_name(code, locale="en")
    return any(marker in name for marker in _RETIREMENT_MARKERS)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def _check_structural_errors(
    iso_digits: Mapping[str, int],
    babel_currencies: frozenset[str],
) -> list[str]:
    """Return codes in ISO_4217_DECIMAL_DIGITS not recognised by Babel at all."""
    return [
        f"  {code}: In ISO_4217_DECIMAL_DIGITS but not in Babel currency list"
        for code in iso_digits
        if code not in babel_currencies
    ]


def _check_decimal_discrepancies(
    iso_digits: Mapping[str, int],
) -> list[str]:
    """Compare explicit ISO_4217_DECIMAL_DIGITS entries against Babel precision."""
    from babel.numbers import get_currency_precision  # noqa: PLC0415 - Babel-optional

    result: list[str] = []
    for code, iso_val in sorted(iso_digits.items()):
        babel_val = get_currency_precision(code)
        if iso_val != babel_val:
            result.append(f"  {code}: ISO 4217={iso_val}, Babel CLDR={babel_val}")
    return result


def _check_stale_active_codes(
    valid_codes: frozenset[str],
    babel_currencies: frozenset[str],
) -> list[str]:
    """Find codes in ISO_4217_VALID_CODES that Babel name-marks as retired.

    A code is considered stale if Babel includes it and its English name
    contains a date-range suffix (em-dash or en-dash), indicating it has been
    superseded. Such codes should be removed from ISO_4217_VALID_CODES so that
    get_currency_decimal_digits() correctly returns None for them.
    """
    stale: list[str] = []
    for code in sorted(valid_codes):
        if code not in babel_currencies:
            continue
        if _babel_marks_as_retired(code):
            from babel.numbers import get_currency_name  # noqa: PLC0415 - Babel-optional
            name = get_currency_name(code, locale="en")
            stale.append(f"  {code}: {name!r} — marked retired by Babel")
    return stale


def _check_retired_correctly_excluded(
    valid_codes: frozenset[str],
    babel_currencies: frozenset[str],
) -> list[str]:
    """Scan all Babel currencies for retirement markers and confirm correct exclusion.

    Returns codes that Babel marks as retired AND are correctly absent from
    ISO_4217_VALID_CODES. These are positive confirmations — get_currency_decimal_
    digits() already returns None for them. Covers codes at any precision (including
    default=2), making them visible regardless of their decimal digit count.

    Any Babel-retired code found IN ISO_4217_VALID_CODES is caught by
    _check_stale_active_codes. This check covers the complement: confirmed absences.
    """
    from babel.numbers import get_currency_name  # noqa: PLC0415 - Babel-optional

    confirmed: list[str] = []
    for code in sorted(babel_currencies):
        if code in valid_codes:
            continue  # present in VALID_CODES — stale check handles this
        if _babel_marks_as_retired(code):
            name = get_currency_name(code, locale="en")
            confirmed.append(
                f"  {code}: {name!r} — Babel-retired, correctly absent"
            )
    return confirmed


def _check_coverage_gaps(
    iso_digits: Mapping[str, int],
    valid_codes: frozenset[str],
    babel_currencies: frozenset[str],
    default_decimals: int,
) -> tuple[list[str], list[str], list[str]]:
    """Scan Babel currencies for precision mismatches not in our data.

    Returns:
        Tuple of (actionable_gaps, active_practical_zero, retired_handled).
        - actionable_gaps: Babel codes absent from our data with non-default,
          non-zero precision. These need explicit entries.
        - active_practical_zero: Babel codes in ISO_4217_VALID_CODES where
          Babel says 0 but we return the ISO default of 2. Documented
          ISO-vs-usage divergence; not a bug.
        - retired_handled: Babel codes NOT in ISO_4217_VALID_CODES where
          Babel says 0. Already handled: get_currency_decimal_digits returns
          None for these. No concern.
    """
    from babel.numbers import get_currency_precision  # noqa: PLC0415 - Babel-optional

    actionable: list[str] = []
    active_practical_zero: list[str] = []
    retired_handled: list[str] = []

    for code in sorted(babel_currencies):
        if code in iso_digits:
            continue
        babel_val = get_currency_precision(code)
        if babel_val == default_decimals:
            continue  # matches our default, no entry needed

        if babel_val == 0:
            if code in valid_codes:
                # Active code: ISO says 2, practical usage is 0.
                active_practical_zero.append(
                    f"  {code}: Babel=0, our ISO default={default_decimals}"
                    f" (ISO-standard value; minor unit unused in practice)"
                )
            else:
                # Retired code: already returns None from our API.
                retired_handled.append(
                    f"  {code}: Babel=0, not in ISO_4217_VALID_CODES"
                    f" (correctly returns None)"
                )
        else:
            # Non-zero, non-default: a real gap we should cover.
            actionable.append(
                f"  {code}: Babel={babel_val}, our default={default_decimals}"
                f" (likely needs explicit entry in ISO_4217_DECIMAL_DIGITS)"
            )

    return actionable, active_practical_zero, retired_handled


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def _section(header: str, explanation: str, lines: list[str]) -> None:
    """Print a report section if non-empty."""
    if not lines:
        return
    print(f"{header} ({len(lines)}):")
    print(f"  ({explanation})")
    for line in lines:
        print(line)
    print()


def _print_report(
    *,
    structural_errors: list[str],
    stale_codes: list[str],
    discrepancies: list[str],
    actionable: list[str],
    active_practical_zero: list[str],
    retired_handled: list[str],
    retired_confirmed: list[str],
    entry_count: int,
    valid_count: int,
    babel_count: int,
    verbose: bool,
) -> None:
    """Print formatted verification report."""
    print("ISO 4217 Verification")
    print("=" * 50)
    print(f"Decimal-digit entries (non-default): {entry_count}")
    print(f"Active code set size:                {valid_count}")
    print(f"Babel currency count:                {babel_count}")
    print()

    _section(
        "[ERROR] Structural errors",
        "Code in ISO_4217_DECIMAL_DIGITS not in Babel; check spelling",
        structural_errors,
    )
    _section(
        "[ERROR] Stale active codes",
        "Code in ISO_4217_VALID_CODES that Babel marks as retired — remove it",
        stale_codes,
    )
    _section(
        "[WARN] ISO 4217 vs CLDR decimal discrepancies",
        "Our data follows ISO 4217 standard; Babel CLDR follows usage — expected",
        discrepancies,
    )
    _section(
        "[WARN] Actionable coverage gaps",
        "Babel reports non-default precision for code absent from our data",
        actionable,
    )

    if verbose:
        _section(
            "[INFO] Active codes: ISO=2, Babel=0 (practical non-usage)",
            "ISO 4217 standard specifies 2; minor unit unused — we return ISO value",
            active_practical_zero,
        )
        _section(
            "[INFO] Retired codes: Babel-precision=0, not in VALID_CODES",
            "Not in ISO_4217_VALID_CODES; get_currency_decimal_digits returns None",
            retired_handled,
        )
        _section(
            "[INFO] Babel-retired codes confirmed absent from VALID_CODES",
            "Babel name has date-range suffix; correctly excluded — returns None",
            retired_confirmed,
        )
    else:
        if active_practical_zero:
            print(
                f"[INFO] {len(active_practical_zero)} active code(s) where"
                f" ISO=2, Babel=0 (practical non-usage; we return ISO value)."
                f" Use --verbose to list."
            )
        if retired_handled:
            print(
                f"[INFO] {len(retired_handled)} retired code(s) with Babel=0"
                f" correctly returning None. Use --verbose to list."
            )
        if retired_confirmed:
            print(
                f"[INFO] {len(retired_confirmed)} Babel-retired code(s) confirmed"
                f" absent from VALID_CODES (returns None). Use --verbose to list."
            )
        if active_practical_zero or retired_handled or retired_confirmed:
            print()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Verify ISO 4217 decimal digits and code freshness.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show active-practical-zero and retired-handled details.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run ISO 4217 verification checks."""
    args = _parse_args(argv)

    try:
        from babel.numbers import list_currencies  # noqa: PLC0415 - Babel-optional
    except ImportError:
        print("[ERROR] Babel not installed. Install with: pip install babel")
        return 1

    from ftllexengine.constants import (  # noqa: PLC0415 - runtime import after Babel check
        ISO_4217_DECIMAL_DIGITS,
        ISO_4217_DEFAULT_DECIMALS,
        ISO_4217_VALID_CODES,
    )

    babel_currencies: frozenset[str] = frozenset(list_currencies())

    structural_errors = _check_structural_errors(ISO_4217_DECIMAL_DIGITS, babel_currencies)
    stale_codes = _check_stale_active_codes(ISO_4217_VALID_CODES, babel_currencies)
    discrepancies = _check_decimal_discrepancies(ISO_4217_DECIMAL_DIGITS)
    actionable, active_practical_zero, retired_handled = _check_coverage_gaps(
        ISO_4217_DECIMAL_DIGITS,
        ISO_4217_VALID_CODES,
        babel_currencies,
        ISO_4217_DEFAULT_DECIMALS,
    )
    retired_confirmed = _check_retired_correctly_excluded(
        ISO_4217_VALID_CODES,
        babel_currencies,
    )

    _print_report(
        structural_errors=structural_errors,
        stale_codes=stale_codes,
        discrepancies=discrepancies,
        actionable=actionable,
        active_practical_zero=active_practical_zero,
        retired_handled=retired_handled,
        retired_confirmed=retired_confirmed,
        entry_count=len(ISO_4217_DECIMAL_DIGITS),
        valid_count=len(ISO_4217_VALID_CODES),
        babel_count=len(babel_currencies),
        verbose=args.verbose,
    )

    fatal = structural_errors or stale_codes or actionable
    if fatal:
        total_errors = len(structural_errors) + len(stale_codes) + len(actionable)
        print(f"[FAIL] {total_errors} error(s) require remediation.")
        return 1

    total_info = (
        len(discrepancies) + len(active_practical_zero)
        + len(retired_handled) + len(retired_confirmed)
    )
    if total_info:
        print(
            f"[PASS] {len(discrepancies)} ISO/CLDR discrepancy(ies) (expected),"
            f" {len(active_practical_zero)} active-practical-zero,"
            f" {len(retired_handled)} retired-precision-zero,"
            f" {len(retired_confirmed)} Babel-retired confirmed absent."
        )
    else:
        print("[PASS] All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
