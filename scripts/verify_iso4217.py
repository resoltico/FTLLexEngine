#!/usr/bin/env python3
"""Verify ISO 4217 decimal digits against Babel CLDR data.

Compares the hardcoded ISO_4217_DECIMAL_DIGITS constant against
babel.numbers.get_currency_precision() for all known currency codes.
Reports discrepancies between ISO 4217 standard data and Babel's CLDR data.

This script is informational: discrepancies are expected because Babel's
CLDR data may reflect common usage patterns rather than the ISO standard.
The hardcoded constant is authoritative for ISO 4217 compliance.

Checks:
    1. Structural: Hardcoded currencies not recognized by Babel.
    2. Discrepancies: Hardcoded value differs from Babel value.
    3. Coverage gaps: Babel reports non-zero, non-default precision for
       a currency we have no explicit entry for (actionable).
    4. Unverifiable: Babel reports 0 decimals where our default is 2.
       May be correct (usage) or a real gap (ISO 4217 also specifies 0).
       Cannot distinguish without a second ISO 4217 source. Shown only
       with --verbose.

Exit codes:
    0: All checks passed (discrepancies are warnings, not failures).
    1: Structural errors (missing currencies, import failures).

Usage:
    verify_iso4217.py [--verbose]

Python 3.13+. Requires Babel.
"""

from __future__ import annotations

import argparse
import sys


def _check_unrecognized(
    iso_digits: dict[str, int],
    babel_currencies: set[str],
) -> list[str]:
    """Check hardcoded currencies not recognized by Babel."""
    return [
        f"  {code}: In ISO_4217_DECIMAL_DIGITS but not recognized by Babel"
        for code in iso_digits
        if code not in babel_currencies
    ]


def _check_discrepancies(
    iso_digits: dict[str, int],
) -> list[str]:
    """Compare hardcoded values against Babel precision."""
    from babel.numbers import get_currency_precision  # noqa: PLC0415

    result: list[str] = []
    for code, iso_val in sorted(iso_digits.items()):
        babel_val = get_currency_precision(code)
        if iso_val != babel_val:
            result.append(f"  {code}: ISO 4217={iso_val}, Babel CLDR={babel_val}")
    return result


def _check_coverage_gaps(
    iso_digits: dict[str, int],
    babel_currencies: set[str],
    default_decimals: int,
) -> tuple[list[str], list[str]]:
    """Scan Babel currencies not in our list for precision mismatches.

    Separates actionable gaps (Babel reports non-zero, non-default precision
    we have no entry for) from unverifiable divergences (Babel reports 0
    where our default is 2 -- common for currencies whose minor units see
    no practical use, but could also indicate a genuine ISO 4217 = 0 case
    we're missing).

    Returns:
        Tuple of (actionable gaps, unverifiable divergences).
    """
    from babel.numbers import get_currency_precision  # noqa: PLC0415

    actionable: list[str] = []
    unverifiable: list[str] = []

    for code in sorted(babel_currencies):
        if code in iso_digits:
            continue
        babel_val = get_currency_precision(code)
        if babel_val == default_decimals:
            continue

        if babel_val == 0:
            # Babel reports 0 where we default to 2. Two possible causes:
            # (a) ISO 4217 specifies 2 but minor units are unused (common).
            # (b) ISO 4217 specifies 0 and we're missing the entry (gap).
            # Cannot distinguish without a second ISO 4217 data source.
            unverifiable.append(f"  {code}: Babel=0, our default={default_decimals}")
        else:
            actionable.append(
                f"  {code}: Babel={babel_val}, our default={default_decimals}"
                f" (likely needs explicit entry)"
            )

    return actionable, unverifiable


def _print_section(header: str, explanation: str, lines: list[str]) -> None:
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
    errors: list[str],
    discrepancies: list[str],
    actionable: list[str],
    unverifiable: list[str],
    entry_count: int,
    babel_count: int,
    verbose: bool,
) -> None:
    """Print formatted report."""
    print("ISO 4217 Decimal Digits Verification")
    print("=" * 50)
    print(f"Hardcoded entries: {entry_count}")
    print(f"Babel currencies:  {babel_count}")
    print()

    _print_section(
        "[ERROR] Structural errors",
        "Hardcoded currency not recognized by Babel",
        errors,
    )
    _print_section(
        "[WARN] ISO 4217 vs Babel discrepancies",
        "Hardcoded ISO 4217 data is authoritative; Babel CLDR may differ",
        discrepancies,
    )
    _print_section(
        "[WARN] Potential coverage gaps",
        "Babel reports non-default precision; verify against ISO 4217 standard",
        actionable,
    )

    if unverifiable:
        if verbose:
            _print_section(
                "[INFO] Unverifiable Babel divergences",
                "Babel reports 0 where our default is 2; may reflect"
                " usage or a missing ISO 4217 entry",
                unverifiable,
            )
        else:
            print(
                f"[INFO] {len(unverifiable)} Babel divergence(s) from"
                f" default (Babel=0, ours=2). Use --verbose to list."
            )
            print()

    has_findings = errors or discrepancies or actionable or unverifiable
    if not has_findings:
        print("[OK] All checks passed. No discrepancies found.")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Verify ISO 4217 decimal digits against Babel CLDR data.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show unverifiable Babel divergences (Babel=0, default=2).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run ISO 4217 verification checks."""
    args = _parse_args(argv)

    try:
        from babel.numbers import list_currencies  # noqa: PLC0415
    except ImportError:
        print("[ERROR] Babel not installed. Install with: pip install babel")
        return 1

    from ftllexengine.constants import (  # noqa: PLC0415
        ISO_4217_DECIMAL_DIGITS,
        ISO_4217_DEFAULT_DECIMALS,
    )

    babel_currencies = list_currencies()

    errors = _check_unrecognized(ISO_4217_DECIMAL_DIGITS, babel_currencies)
    discrepancies = _check_discrepancies(ISO_4217_DECIMAL_DIGITS)
    actionable, unverifiable = _check_coverage_gaps(
        ISO_4217_DECIMAL_DIGITS, babel_currencies, ISO_4217_DEFAULT_DECIMALS,
    )

    _print_report(
        errors=errors,
        discrepancies=discrepancies,
        actionable=actionable,
        unverifiable=unverifiable,
        entry_count=len(ISO_4217_DECIMAL_DIGITS),
        babel_count=len(babel_currencies),
        verbose=args.verbose,
    )

    if errors:
        print(f"[FAIL] {len(errors)} structural error(s) found.")
        print("[EXIT-CODE] 1")
        return 1

    total = len(discrepancies) + len(actionable) + len(unverifiable)
    if total:
        print(
            f"[PASS] {len(discrepancies)} discrepancy(ies),"
            f" {len(actionable)} gap(s),"
            f" {len(unverifiable)} unverifiable."
        )
    else:
        print("[PASS] All checks passed.")
    print("[EXIT-CODE] 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
