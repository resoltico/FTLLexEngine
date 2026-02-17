#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: currency - Currency symbol & numeric extraction
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Currency Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.currency.parse_currency
Tests tiered loading, ambiguous symbol resolution, and numeric extraction.

Shared infrastructure from fuzz_common (BaseFuzzerState, round-robin scheduling,
stratified corpus, metrics). Domain-specific metrics in CurrencyMetrics.

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
class CurrencyMetrics:
    """Domain-specific metrics for currency fuzzer."""

    fast_tier_hits: int = 0
    full_tier_hits: int = 0
    ambiguous_resolutions: int = 0
    locale_inferences: int = 0


class CurrencyFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# --- Constants ---

ALLOWED_EXCEPTIONS = (ValueError, TypeError, UnicodeEncodeError)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    ("unambiguous_unicode", 8),
    ("ambiguous_dollar", 8),
    ("ambiguous_pound", 7),
    ("ambiguous_yen_yuan", 7),
    ("ambiguous_kr", 7),
    ("comma_decimal", 7),
    ("period_grouping", 7),
    ("negative_format", 8),
    ("explicit_iso_code", 7),
    ("invalid_iso_code", 7),
    ("whitespace_variation", 7),
    ("edge_case", 5),
    ("raw_bytes", 10),
    ("fullwidth_digits", 5),
    ("code_symbol_combo", 5),
    ("special_number", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Map pattern name to match/case index for _generate_currency_input
_PATTERN_INDEX: dict[str, int] = {name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)}


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="currency",
    fuzzer_target="parse_currency (tiered loading, ambiguous resolution, numeric extraction)",
    pattern_intended_weights={name: float(weight) for name, weight in _PATTERN_WEIGHTS},
)
_domain = CurrencyMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "currency"
_REPORT_FILENAME = "fuzz_currency_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["fast_tier_hits"] = _domain.fast_tier_hits
    stats["full_tier_hits"] = _domain.full_tier_hits
    stats["ambiguous_resolutions"] = _domain.ambiguous_resolutions
    stats["locale_inferences"] = _domain.locale_inferences

    # Tier ratio (domain-specific derived metric)
    total_tier_hits = _domain.fast_tier_hits + _domain.full_tier_hits
    if total_tier_hits > 0:
        stats["fast_tier_ratio"] = round(_domain.fast_tier_hits / total_tier_hits, 3)

    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit crash-proof final report."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.parsing.currency import parse_currency

# --- Test Locales (comprehensive set including RTL and edge cases) ---
TEST_LOCALES: Sequence[str] = (
    # Major Latin-script locales
    "en-US",
    "en-CA",
    "en-GB",
    "de-DE",
    "fr-FR",
    "es-ES",
    # Asian locales (CJK)
    "zh-CN",
    "zh-TW",
    "ja-JP",
    "ko-KR",
    # RTL locales
    "ar-EG",
    "ar-SA",
    "he-IL",
    # Nordic (for kr symbol)
    "sv-SE",
    "nb-NO",
    "da-DK",
    "is-IS",
    # Edge cases
    "lv-LV",  # Latvian (specific formatting)
    "root",  # CLDR root fallback
)

# --- Comprehensive Currency Symbols ---
# Unambiguous Unicode symbols (fast tier candidates)
UNAMBIGUOUS_SYMBOLS: Sequence[str] = (
    "\u20ac",  # Euro
    "\u20b9",  # Indian Rupee
    "\u20bd",  # Russian Ruble
    "\u20ba",  # Turkish Lira
    "\u20aa",  # Israeli Shekel
    "\u20a6",  # Nigerian Naira
    "\u20b1",  # Philippine Peso
    "\u20bf",  # Bitcoin
    "\u20ab",  # Vietnamese Dong
    "\u20b4",  # Ukrainian Hryvnia
    "\u20b8",  # Kazakh Tenge
    "\u20bc",  # Azerbaijani Manat
)

# Ambiguous symbols (require locale for disambiguation)
AMBIGUOUS_SYMBOLS: Sequence[str] = (
    "$",  # USD, CAD, AUD, etc.
    "\u00a3",  # GBP, EGP, GIP, etc.
    "\u00a5",  # JPY, CNY
    "kr",  # SEK, NOK, DKK, ISK
    "R$",  # BRL
    "R",  # ZAR
)

# Valid ISO 4217 codes for testing
ISO_CODES: Sequence[str] = (
    "USD", "EUR", "GBP", "JPY", "CNY", "INR", "AUD", "CAD",
    "CHF", "HKD", "SGD", "SEK", "NOK", "DKK", "NZD", "ZAR",
)

# Invalid codes for error path testing
INVALID_ISO_CODES: Sequence[str] = (
    "US", "EURO", "GB", "XYZ", "1234", "usd", "Us", "",
    "ABCD", "A", "AB",
)


def _generate_currency_input(  # noqa: PLR0911, PLR0912, PLR0915
    fdp: atheris.FuzzedDataProvider,
    pattern_name: str,
) -> tuple[str, str]:
    """Generate currency input string for a given pattern.

    Returns:
        (input_string, locale)
    """
    pattern_choice = _PATTERN_INDEX[pattern_name]
    locale = fdp.PickValueInList(list(TEST_LOCALES))

    match pattern_choice:
        case 0:  # Unambiguous Unicode symbols (fast tier)
            symbol = fdp.PickValueInList(list(UNAMBIGUOUS_SYMBOLS))
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"{symbol}{amount:.2f}"
                if fdp.ConsumeBool()
                else f"{amount:.2f} {symbol}"
            )
            return (input_str, locale)

        case 1:  # Ambiguous dollar sign (requires locale)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"${amount:.2f}" if fdp.ConsumeBool() else f"{amount:.2f}$"
            return (input_str, locale)

        case 2:  # Ambiguous pound sign (GBP, EGP, GIP)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a3{amount:.2f}"
            return (input_str, locale)

        case 3:  # Ambiguous yen/yuan sign (JPY, CNY)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a5{amount:.2f}"
            return (input_str, locale)

        case 4:  # Ambiguous "kr" (SEK, NOK, DKK, ISK)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"{amount:.2f} kr" if fdp.ConsumeBool() else f"kr {amount:.2f}"
            )
            return (input_str, locale)

        case 5:  # Comma as decimal separator (European format)
            symbol = fdp.PickValueInList(["\u20ac", "$", "\u00a3"])
            amount_int = fdp.ConsumeIntInRange(1, 999999)
            amount_frac = fdp.ConsumeIntInRange(0, 99)
            input_str = f"{symbol}{amount_int},{amount_frac:02d}"
            return (input_str, locale)

        case 6:  # Period as grouping separator (European format) - varied amounts
            symbol = fdp.PickValueInList(["\u20ac", "$"])
            # Generate varied amounts instead of fixed string
            thousands = fdp.ConsumeIntInRange(1, 999)
            hundreds = fdp.ConsumeIntInRange(0, 999)
            ones = fdp.ConsumeIntInRange(0, 999)
            cents = fdp.ConsumeIntInRange(0, 99)
            input_str = f"{symbol}{thousands}.{hundreds:03d}.{ones:03d},{cents:02d}"
            return (input_str, locale)

        case 7:  # Negative formats (4 common patterns)
            symbol = "$"
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            neg_choice = fdp.ConsumeIntInRange(0, 3)
            match neg_choice:
                case 0:
                    input_str = f"-{symbol}{amount:.2f}"  # -$100.00
                case 1:
                    input_str = f"({symbol}{amount:.2f})"  # ($100.00)
                case 2:
                    input_str = f"{symbol}-{amount:.2f}"  # $-100.00
                case _:
                    input_str = f"{symbol}{amount:.2f}-"  # $100.00-
            return (input_str, locale)

        case 8:  # Explicit ISO code (bypass symbol resolution)
            code = fdp.PickValueInList(list(ISO_CODES))
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"{amount:.2f} {code}"
            return (input_str, locale)

        case 9:  # Invalid ISO codes (error testing)
            invalid_code = fdp.PickValueInList(list(INVALID_ISO_CODES))
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            input_str = f"{amount:.2f} {invalid_code}"
            return (input_str, locale)

        case 10:  # Whitespace variations (including Unicode spaces)
            symbol = fdp.PickValueInList(["\u20ac", "$", "\u00a3"])
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            # Include various Unicode whitespace characters
            space_chars = [" ", "\u00a0", "\u2009", "\u202f", "  ", ""]  # NBSP, thin, narrow
            spaces = fdp.PickValueInList(space_chars)
            if fdp.ConsumeBool():
                input_str = f"{symbol}{spaces}{amount:.2f}"
            else:
                input_str = f"{amount:.2f}{spaces}{symbol}"
            return (input_str, locale)

        case 11:  # Edge cases (expanded)
            edge_choice = fdp.ConsumeIntInRange(0, 15)
            match edge_choice:
                case 0:
                    input_str = ""  # Empty
                case 1:
                    input_str = "   "  # Whitespace only
                case 2:
                    input_str = "$"  # Symbol only
                case 3:
                    input_str = "123.45"  # Number only (no symbol)
                case 4:
                    input_str = "abc def"  # Invalid text
                case 5:
                    input_str = "\x00$100"  # Null byte
                case 6:
                    input_str = "\ufeff$100.00"  # BOM prefix
                case 7:
                    input_str = "$\u200b100.00"  # Zero-width space
                case 8:
                    input_str = "\u0661\u0662\u0663.\u0664\u0665 $"  # Arabic-Indic
                case 9:
                    input_str = "$" + "9" * 100 + ".99"  # Very large
                case 10:
                    input_str = "R$100.00"  # R$ (BRL) ambiguous
                case 11:
                    input_str = "R100.00"  # R (ZAR) ambiguous
                case 12:
                    input_str = "$$$100.00"  # Multiple symbols
                case 13:
                    input_str = "\u200e$\u200e100.00"  # LTR marks
                case 14:
                    input_str = "  $  100  .  00  "  # Spaces everywhere
                case _:
                    input_str = "\u00a3" + "0" * 300 + ".01"  # Very long
            return (input_str, locale)

        case 12:  # Raw bytes pass-through (let libFuzzer mutations drive)
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 200))
            return (raw, locale)

        case 13:  # Fullwidth digits and mixed scripts
            fw_choice = fdp.ConsumeIntInRange(0, 5)
            match fw_choice:
                case 0:
                    # Fullwidth digits: U+FF10-U+FF19
                    input_str = "$\uff11\uff12\uff13.\uff14\uff15"
                case 1:
                    # Devanagari digits: U+0966-U+096F
                    input_str = "\u20b9\u0967\u0968\u0969.\u0966\u0966"
                case 2:
                    # Thai digits: U+0E50-U+0E59
                    input_str = "$\u0e51\u0e52\u0e53.\u0e54\u0e55"
                case 3:
                    # Mixed: ASCII + fullwidth
                    input_str = "\u20ac1\uff12\uff13.45"
                case 4:
                    # RTL marks around currency
                    input_str = "\u200f$\u200f100.00"
                case _:
                    # Superscript/subscript digits
                    input_str = "$\u00b9\u00b2\u00b3.00"
            return (input_str, locale)

        case 14:  # ISO code + symbol combo (both present)
            code = fdp.PickValueInList(list(ISO_CODES))
            symbol = fdp.PickValueInList(["$", "\u20ac", "\u00a3", "\u00a5"])
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            combo_choice = fdp.ConsumeIntInRange(0, 3)
            match combo_choice:
                case 0:
                    input_str = f"{code} {symbol}{amount:.2f}"
                case 1:
                    input_str = f"{symbol}{amount:.2f} {code}"
                case 2:
                    input_str = f"{code}{amount:.2f}"  # Code without space
                case _:
                    input_str = f"{symbol}{symbol}{amount:.2f}"  # Double symbol
            return (input_str, locale)

        case 15:  # Exponent notation and special number forms
            exp_choice = fdp.ConsumeIntInRange(0, 5)
            match exp_choice:
                case 0:
                    input_str = "$1.23e5"  # Scientific notation
                case 1:
                    input_str = "\u20ac-0.00"  # Negative zero
                case 2:
                    input_str = "$0.001"  # Sub-cent
                case 3:
                    input_str = "\u20acINF"  # Infinity
                case 4:
                    input_str = "$NaN"  # NaN
                case _:
                    input_str = "\u00a3" + "0" * 300 + ".01"  # Very long number
            return (input_str, locale)

        case _:
            # Unreachable fallback
            return ("$100.00", "en-US")


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Test currency parsing boundary conditions."""
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Round-robin pattern selection (immune to coverage-guided bias)
    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    # Generate currency input for selected pattern
    input_str, locale = _generate_currency_input(fdp, pattern_name)

    # Optional: override with default_currency and infer_from_locale
    # Generate valid 3-letter uppercase codes or None
    default_curr: str | None = None
    if fdp.ConsumeBool():
        raw_curr = fdp.ConsumeBytes(3).decode("ascii", errors="ignore").upper()
        if len(raw_curr) == 3 and raw_curr.isalpha():
            default_curr = raw_curr

    infer = fdp.ConsumeBool()
    if infer:
        _domain.locale_inferences += 1

    try:
        res, errors = parse_currency(
            input_str,
            locale,
            default_currency=default_curr,
            infer_from_locale=infer,
        )

        # Track tier usage (heuristic: fast tier for unambiguous, full tier for ambiguous)
        if "unambiguous" in pattern_name:
            _domain.fast_tier_hits += 1
        elif "ambiguous" in pattern_name:
            _domain.full_tier_hits += 1
            _domain.ambiguous_resolutions += 1

        # Track API contract violations (instead of asserting/crashing)
        if res:
            amount, code = res

            # Validate return types (runtime contract validation)
            if not isinstance(amount, Decimal):
                _state.error_counts["contract_invalid_amount_type"] = (
                    _state.error_counts.get("contract_invalid_amount_type", 0) + 1
                )
                _state.findings += 1

            if not isinstance(code, str):
                _state.error_counts["contract_invalid_code_type"] = (
                    _state.error_counts.get("contract_invalid_code_type", 0) + 1
                )
                _state.findings += 1
            elif len(code) != 3:
                # ISO 4217 validation: codes MUST be exactly 3 uppercase ASCII letters
                error_key = f"contract_iso4217_length_{len(code)}"
                _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
                _state.findings += 1
            elif not code.isupper():
                _state.error_counts["contract_iso4217_not_uppercase"] = (
                    _state.error_counts.get("contract_iso4217_not_uppercase", 0) + 1
                )
                _state.findings += 1
            elif not code.isalpha():
                _state.error_counts["contract_iso4217_not_alpha"] = (
                    _state.error_counts.get("contract_iso4217_not_alpha", 0) + 1
                )
                _state.findings += 1

        # Track parse errors (expected errors from invalid input)
        if errors:
            for error in errors:
                # Extract clean error key from FrozenFluentError
                try:
                    if hasattr(error.category, "name"):
                        category_name = error.category.name
                    else:
                        category_name = str(error.category)
                    if hasattr(error, "code") and hasattr(error.code, "name"):
                        code_info = error.code.name
                    else:
                        code_info = ""
                    error_key = f"{category_name}_{code_info}"[:50]
                except (AttributeError, TypeError):
                    error_key = "parse_error_unknown"
                _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    except (ValueError, TypeError, UnicodeEncodeError, FrozenFluentError) as e:
        # Expected: invalid locale, invalid input format, surrogates, depth/safety guards
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = _state.error_counts.get(error_type, 0) + 1
    except Exception:
        # Unexpected exceptions are findings - re-raise for Atheris to capture
        _state.findings += 1
        raise
    finally:
        # Semantic interestingness: ambiguous patterns, edge cases, error paths,
        # or wall-time > 1ms indicating unusual code path
        is_interesting = (
            "ambiguous" in pattern_name
            or pattern_name in ("edge_case", "raw_bytes", "special_number")
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state, pattern_name, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the currency fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Currency parsing fuzzer using Atheris/libFuzzer",
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
        default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    # Parse known args, pass rest to Atheris/libFuzzer
    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Currency Parsing Fuzzer (Atheris)",
        target="ftllexengine.parsing.currency.parse_currency",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
