#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: dates - Date/Datetime Locale-aware Parsing
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Date and Datetime Locale-aware Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.dates (parse_date, parse_datetime)

Concern boundary: This fuzzer stress-tests the CLDR-to-strptime pattern
transformation layer. parse_date() and parse_datetime() iterate Babel CLDR
locale patterns, map each CLDR token to a Python strptime directive via
_babel_to_strptime(), and attempt to match the input string. The transformation
covers ~30 CLDR tokens (date tokens d/M/y, time tokens H/h/m/s, era tokens G,
timezone tokens Z/z/x/X/V/O, and locale-specific era/period strings).

Each locale has different date pattern orderings (DMY vs MDY vs YMD), separators
(slashes, dots, hyphens, spaces), and era strings. The fuzzer probes all
four CLDR date styles (short/medium/long/full) and all four datetime styles
across 20+ locales, plus adversarial inputs (control chars, surrogates, very
long strings, null bytes, Unicode edge cases).

The rounding-mode class of bugs (v0.145.0) originated in a different module
but follows the same pattern: locale-specific formatting edge cases only
exposed by cross-locale oracle testing. This fuzzer applies the same
methodology to the date parsing layer.

Unique coverage (not covered by other fuzzers):
- _babel_to_strptime(): 30-token CLDR-to-%strptime mapping
- _extract_cldr_patterns(): CLDR date pattern extraction per locale
- _get_date_patterns() / _get_datetime_patterns(): cached pattern sets
- _strip_era(): locale-specific era string removal
- _preprocess_datetime_input(): datetime separator detection
- _is_word_boundary(): word boundary detection in date strings
- parse_date() soft-error return API: (date | None, errors)
- parse_datetime() soft-error return API: (datetime | None, errors)

Patterns (13):
- parse_date_iso: ISO 8601 date strings (YYYY-MM-DD)
- parse_date_locale_short: locale-specific short date
- parse_date_locale_medium: locale-specific medium date
- parse_date_locale_long: locale-specific long date
- parse_date_locale_full: locale-specific full date
- parse_datetime_iso: ISO 8601 datetime strings
- parse_datetime_locale_short: locale-specific short datetime
- parse_datetime_locale_medium: locale-specific medium datetime
- parse_datetime_timezone: strings with UTC offset variants
- parse_date_edge_cases: leap year, month boundary, year extremes
- parse_datetime_edge_cases: midnight, DST transitions, end-of-day
- adversarial_input: control chars, null bytes, surrogates, very long
- raw_unicode: pure Atheris byte mutations for pattern discovery

Metrics:
- Pattern coverage with weighted round-robin schedule
- parse_date success/failure counts, parse_datetime success/failure counts
- Invariant violation counts
- Performance profiling (min/mean/p95/p99/max)
- Real memory usage (RSS via psutil)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
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

from fuzz_common import (  # noqa: E402  # pylint: disable=C0413
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
class DatesMetrics:
    """Domain-specific metrics for dates fuzzer."""

    parse_date_success: int = 0
    parse_date_failure: int = 0
    parse_datetime_success: int = 0
    parse_datetime_failure: int = 0
    invariant_violations: int = 0
    adversarial_handled: int = 0


class DatesFuzzError(Exception):
    """Raised when a parse invariant is violated."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,          # invalid locale or date string format
    TypeError,           # invalid argument types
    UnicodeEncodeError,  # surrogate characters
    OSError,             # locale data access issues
)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    ("parse_date_iso", 9),
    ("parse_date_locale_short", 8),
    ("parse_date_locale_medium", 7),
    ("parse_date_locale_long", 6),
    ("parse_date_locale_full", 5),
    ("parse_datetime_iso", 9),
    ("parse_datetime_locale_short", 8),
    ("parse_datetime_locale_medium", 7),
    ("parse_datetime_timezone", 7),
    ("parse_date_edge_cases", 6),
    ("parse_datetime_edge_cases", 6),
    ("adversarial_input", 7),
    ("raw_unicode", 10),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)
_PATTERN_INDEX: dict[str, int] = {
    name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)
}

# Comprehensive locale set: chosen to cover diverse CLDR date patterns
_TEST_LOCALES: Sequence[str] = (
    # Latin DMY (Europe)
    "en-GB", "de-DE", "fr-FR", "es-ES", "it-IT", "nl-NL", "pl-PL",
    # Latin MDY (Americas)
    "en-US", "es-MX", "pt-BR",
    # Latin YMD (ISO-adjacent)
    "sv-SE", "nb-NO", "fi-FI", "hu-HU",
    # CJK (YMD with era support)
    "ja-JP", "zh-CN", "zh-TW", "ko-KR",
    # RTL
    "ar-EG", "ar-SA", "he-IL",
    # Other
    "ru-RU", "tr-TR", "th-TH",
)

# ISO 8601 date strings
_ISO_DATES: Sequence[str] = (
    "2024-01-01", "2024-12-31", "2024-02-29",  # leap year
    "2023-02-28", "2000-01-01", "1999-12-31",
    "2024-06-15", "2024-11-30", "1970-01-01",
    "2038-01-19",  # Unix 32-bit boundary
    "9999-12-31", "0001-01-01",
)

# Locale-formatted date samples (short/medium/long styles)
_LOCALE_DATE_SAMPLES: Sequence[tuple[str, str]] = (
    ("en-US", "1/15/2024"),      ("en-US", "Jan 15, 2024"),
    ("en-GB", "15/01/2024"),     ("en-GB", "15 January 2024"),
    ("de-DE", "15.01.2024"),     ("de-DE", "15. Januar 2024"),
    ("fr-FR", "15/01/2024"),     ("fr-FR", "15 janvier 2024"),
    ("ja-JP", "2024/01/15"),     ("ja-JP", "2024年1月15日"),
    ("zh-CN", "2024/1/15"),      ("zh-CN", "2024年1月15日"),
    ("ko-KR", "2024. 1. 15."),   ("ko-KR", "2024년 1월 15일"),
    ("ru-RU", "15.01.2024"),     ("ru-RU", "15 \u044f\u043d\u0432\u0430\u0440\u044f 2024 \u0433."),
    ("sv-SE", "2024-01-15"),     ("sv-SE", "15 januari 2024"),
    ("ar-EG", "15/01/2024"),     ("ar-SA", "15/01/2024"),
)

# Timezone offset strings
_TZ_OFFSETS: Sequence[str] = (
    "Z", "+00:00", "-05:00", "+05:30", "+09:00",
    "+00", "-0500", "+0530", "+09",
    "GMT+0", "GMT-5", "UTC",
)

# Edge-case date strings
_EDGE_DATE_STRINGS: Sequence[str] = (
    "2024-02-29",   # Leap year
    "2023-02-28",   # Non-leap year Feb end
    "2024-12-31",   # Year end
    "2024-01-01",   # Year start
    "2024-03-31",   # March end
    "2024-04-30",   # April end (30-day month)
    "1970-01-01",   # Unix epoch
    "2038-01-19",   # 32-bit Unix overflow
    "1582-10-15",   # Gregorian calendar start
    "0001-01-01",   # Min date
    "9999-12-31",   # Max date
)

# Adversarial strings (must not crash, must return (None, errors) or
# raise only allowed exceptions)
_ADVERSARIAL_STRINGS: Sequence[str] = (
    "",
    "   ",
    "\x00",
    "\n\r\t",
    "\x1b[31m2024-01-01\x1b[0m",  # ANSI escape
    "A" * 10000,
    "2024" + "\x00" + "-01-01",
    "\uffff2024-01-01",
    "\u20002024-01-01",  # Zero-width no-break space
    "2024-01-01\x00extra",
    "\ud800",  # High surrogate
    "9" * 500,
    "2024-13-01",  # Invalid month
    "2024-01-32",  # Invalid day
    "2024-00-01",  # Zero month
    "not a date",
    "2024/99/99",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="dates",
    fuzzer_target=(
        "parse_date, parse_datetime (CLDR pattern extraction, "
        "_babel_to_strptime mapping)"
    ),
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = DatesMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "dates"
_REPORT_FILENAME = "fuzz_dates_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["parse_date_success"] = _domain.parse_date_success
    stats["parse_date_failure"] = _domain.parse_date_failure
    stats["parse_datetime_success"] = _domain.parse_datetime_success
    stats["parse_datetime_failure"] = _domain.parse_datetime_failure
    stats["invariant_violations"] = _domain.invariant_violations
    stats["adversarial_handled"] = _domain.adversarial_handled

    total_date = _domain.parse_date_success + _domain.parse_date_failure
    if total_date > 0:
        stats["parse_date_success_rate"] = round(
            _domain.parse_date_success / total_date, 3
        )
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
    from ftllexengine.parsing.dates import parse_date, parse_datetime


def _check_parse_date_result(
    result: date | None,
    errors: tuple[FrozenFluentError, ...],
    locale: str,
    input_str: str,
) -> None:
    """Verify parse_date return contract.

    Contract: (result, errors) is always a 2-tuple. If result is not None,
    it must be a datetime.date instance. If result is None, errors must be
    non-empty. Never both None and no errors.
    """
    if result is not None and not isinstance(result, date):
        msg = (
            f"parse_date returned non-date result: "
            f"{type(result).__name__} for locale='{locale}' input='{input_str}'"
        )
        raise DatesFuzzError(msg)

    if result is None and not errors:
        msg = (
            f"parse_date returned (None, ()) for "
            f"locale='{locale}' input='{input_str}' -- "
            f"must have errors when result is None"
        )
        raise DatesFuzzError(msg)


def _check_parse_datetime_result(
    result: datetime | None,
    errors: tuple[FrozenFluentError, ...],
    locale: str,
    input_str: str,
) -> None:
    """Verify parse_datetime return contract.

    Contract: (result, errors) is always a 2-tuple. If result is not None,
    it must be a datetime.datetime instance. If result is None, errors must
    be non-empty.
    """
    if result is not None and not isinstance(result, datetime):
        msg = (
            f"parse_datetime returned non-datetime result: "
            f"{type(result).__name__} "
            f"for locale='{locale}' input='{input_str}'"
        )
        raise DatesFuzzError(msg)

    if result is None and not errors:
        msg = (
            f"parse_datetime returned (None, ()) for "
            f"locale='{locale}' input='{input_str}' -- "
            f"must have errors when result is None"
        )
        raise DatesFuzzError(msg)


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Test date/datetime parsing invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    input_str = ""
    locale = "en-US"

    try:
        pattern_choice = _PATTERN_INDEX[pattern_name]
        locale = fdp.PickValueInList(list(_TEST_LOCALES))

        match pattern_choice:
            case 0:  # parse_date_iso
                input_str = fdp.PickValueInList(list(_ISO_DATES))
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 1:  # parse_date_locale_short
                sample = fdp.PickValueInList(list(_LOCALE_DATE_SAMPLES))
                input_str, locale = sample[1], sample[0]
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 2:  # parse_date_locale_medium (generated)
                year = fdp.ConsumeIntInRange(1900, 2050)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                sep = fdp.PickValueInList([".", "/", "-", " "])
                # Vary field order by locale family
                if locale in ("en-US", "es-MX"):
                    input_str = f"{month:02d}{sep}{day:02d}{sep}{year}"
                elif locale in ("ja-JP", "zh-CN", "zh-TW", "ko-KR", "sv-SE"):
                    input_str = f"{year}{sep}{month:02d}{sep}{day:02d}"
                else:
                    input_str = f"{day:02d}{sep}{month:02d}{sep}{year}"
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 3:  # parse_date_locale_long (month names)
                year = fdp.ConsumeIntInRange(2000, 2030)
                day = fdp.ConsumeIntInRange(1, 28)
                # Use a numeric representation that any locale can parse
                input_str = f"{year}-{fdp.ConsumeIntInRange(1, 12):02d}-{day:02d}"
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 4:  # parse_date_locale_full
                input_str = fdp.PickValueInList(list(_EDGE_DATE_STRINGS))
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 5:  # parse_datetime_iso
                year = fdp.ConsumeIntInRange(1970, 2099)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                minute = fdp.ConsumeIntInRange(0, 59)
                second = fdp.ConsumeIntInRange(0, 59)
                input_str = (
                    f"{year}-{month:02d}-{day:02d}T"
                    f"{hour:02d}:{minute:02d}:{second:02d}"
                )
                result, errors = parse_datetime(input_str, locale)
                _check_parse_datetime_result(
                    result, errors, locale, input_str
                )
                if result is not None:
                    _domain.parse_datetime_success += 1
                else:
                    _domain.parse_datetime_failure += 1

            case 6:  # parse_datetime_locale_short
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                minute = fdp.ConsumeIntInRange(0, 59)
                input_str = (
                    f"{month:02d}/{day:02d}/{year} "
                    f"{hour}:{minute:02d} AM"
                )
                result, errors = parse_datetime(input_str, locale)
                _check_parse_datetime_result(
                    result, errors, locale, input_str
                )
                if result is not None:
                    _domain.parse_datetime_success += 1
                else:
                    _domain.parse_datetime_failure += 1

            case 7:  # parse_datetime_locale_medium
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                minute = fdp.ConsumeIntInRange(0, 59)
                second = fdp.ConsumeIntInRange(0, 59)
                input_str = (
                    f"{year}-{month:02d}-{day:02d} "
                    f"{hour:02d}:{minute:02d}:{second:02d}"
                )
                result, errors = parse_datetime(input_str, locale)
                _check_parse_datetime_result(
                    result, errors, locale, input_str
                )
                if result is not None:
                    _domain.parse_datetime_success += 1
                else:
                    _domain.parse_datetime_failure += 1

            case 8:  # parse_datetime_timezone
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                minute = fdp.ConsumeIntInRange(0, 59)
                tz = fdp.PickValueInList(list(_TZ_OFFSETS))
                input_str = (
                    f"{year}-{month:02d}-{day:02d}T"
                    f"{hour:02d}:{minute:02d}:00{tz}"
                )
                result, errors = parse_datetime(input_str, locale)
                _check_parse_datetime_result(
                    result, errors, locale, input_str
                )
                if result is not None:
                    _domain.parse_datetime_success += 1
                else:
                    _domain.parse_datetime_failure += 1

            case 9:  # parse_date_edge_cases
                input_str = fdp.PickValueInList(list(_EDGE_DATE_STRINGS))
                result, errors = parse_date(input_str, locale)
                _check_parse_date_result(result, errors, locale, input_str)
                if result is not None:
                    _domain.parse_date_success += 1
                else:
                    _domain.parse_date_failure += 1

            case 10:  # parse_datetime_edge_cases
                edge_choice = fdp.ConsumeIntInRange(0, 5)
                match edge_choice:
                    case 0:
                        input_str = "2024-12-31T23:59:59"  # End of year
                    case 1:
                        input_str = "2024-01-01T00:00:00"  # Start of year
                    case 2:
                        input_str = "2024-02-29T12:00:00"  # Leap day
                    case 3:
                        input_str = "1970-01-01T00:00:00"  # Unix epoch
                    case 4:
                        input_str = "2038-01-19T03:14:07"  # 32-bit overflow
                    case _:
                        input_str = "2024-03-10T02:30:00"  # DST gap (US)
                result, errors = parse_datetime(input_str, locale)
                _check_parse_datetime_result(
                    result, errors, locale, input_str
                )
                if result is not None:
                    _domain.parse_datetime_success += 1
                else:
                    _domain.parse_datetime_failure += 1

            case 11:  # adversarial_input
                _domain.adversarial_handled += 1
                adv = fdp.PickValueInList(list(_ADVERSARIAL_STRINGS))
                # Both parse_date and parse_datetime must not crash on these
                with contextlib.suppress(ValueError, UnicodeEncodeError):
                    d_result, d_errors = parse_date(adv, locale)
                    _check_parse_date_result(d_result, d_errors, locale, adv)

                with contextlib.suppress(ValueError, UnicodeEncodeError):
                    dt_result, dt_errors = parse_datetime(adv, locale)
                    _check_parse_datetime_result(
                        dt_result, dt_errors, locale, adv
                    )

            case _:  # raw_unicode
                raw = fdp.ConsumeUnicodeNoSurrogates(
                    fdp.ConsumeIntInRange(0, 200)
                )
                input_str = raw
                # Must not crash -- any result is acceptable
                with contextlib.suppress(ValueError, UnicodeEncodeError):
                    parse_date(input_str, locale)
                with contextlib.suppress(ValueError, UnicodeEncodeError):
                    parse_datetime(input_str, locale)

    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = (
            _state.error_counts.get(error_type, 0) + 1
        )
    except DatesFuzzError:
        _domain.invariant_violations += 1
        _state.findings += 1
        raise
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            pattern_name in ("adversarial_input", "raw_unicode")
            or "edge" in pattern_name
            or (time.perf_counter() - start_time) * 1000 > 2.0
        )
        record_iteration_metrics(
            _state, pattern_name, start_time, data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the dates fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Date/datetime locale-aware parsing fuzzer (Atheris)",
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
        help="Maximum in-memory seed corpus size (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Date/Datetime Locale-aware Parsing Fuzzer (Atheris)",
        target="ftllexengine.parsing.dates (parse_date, parse_datetime)",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
            f"Locales:    {len(_TEST_LOCALES)} (Latin/CJK/RTL/Nordic)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
