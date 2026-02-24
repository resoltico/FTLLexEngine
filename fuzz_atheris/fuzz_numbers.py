#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: numbers - Numeric Parser Unit
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Numeric Parser Unit Fuzzer (Atheris).

Targets: ftllexengine.parsing.numbers (parse_decimal)

Concern boundary: This fuzzer targets locale-aware numeric parsing --
decimal extraction with CLDR-compliant grouping/decimal separators across locales.
This is distinct from the currency fuzzer (parse_currency with symbol resolution),
runtime fuzzer (resolver/bundle/cache stack), OOM fuzzer (parser AST explosion),
cache fuzzer (IntegrityCache concurrency), and integrity fuzzer (validation checks).

Shared infrastructure from fuzz_common (BaseFuzzerState, round-robin scheduling,
stratified corpus, metrics). Domain-specific metrics in NumbersMetrics.

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
class NumbersMetrics:
    """Domain-specific metrics for numbers fuzzer."""

    decimal_successes: int = 0
    decimal_failures: int = 0


class NumbersFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# --- Constants ---

ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    # Valid (10 patterns)
    ("basic_integer", 8),
    ("decimal_period", 8),
    ("us_thousands", 7),
    ("space_thousands", 7),
    ("de_format", 7),
    ("ch_format", 7),
    ("scientific", 7),
    ("signed_number", 7),
    ("small_decimal", 7),
    ("large_integer", 7),
    # Edge cases (5 patterns)
    ("zero_variant", 6),
    ("special_float", 6),
    ("extreme_magnitude", 6),
    ("unicode_digits", 6),
    ("malformed", 6),
    # Security/invalid (4 patterns)
    ("null_bytes", 5),
    ("very_long", 5),
    ("invalid_string", 5),
    ("raw_bytes", 10),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Map pattern name to match/case index for _generate_number_input
_PATTERN_INDEX: dict[str, int] = {
    name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)
}

_TEST_LOCALES: Sequence[str] = (
    "en-US",
    "de-DE",
    "lv-LV",
    "ar-SA",
    "ja-JP",
    "fr-FR",
    "root",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="numbers",
    fuzzer_target="parse_decimal (locale-aware numeric parsing)",
    pattern_intended_weights={
        name: float(weight) for name, weight in _PATTERN_WEIGHTS
    },
)
_domain = NumbersMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "numbers"
_REPORT_FILENAME = "fuzz_numbers_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["decimal_successes"] = _domain.decimal_successes
    stats["decimal_failures"] = _domain.decimal_failures
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
    from ftllexengine.parsing.numbers import parse_decimal


# --- Input Generation ---


def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


def _generate_number_input(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
    pattern_name: str,
) -> str:
    """Generate number input string for a given pattern.

    19 pattern types targeting locale-aware numeric parsing.

    Returns:
        Input string for the selected pattern.
    """
    pattern_choice = _PATTERN_INDEX[pattern_name]

    match pattern_choice:
        # --- VALID NUMBERS (10 patterns) ---
        case 0:  # Basic integer
            return str(fdp.ConsumeIntInRange(-999999, 999999))

        case 1:  # Decimal with period (en-US style)
            return (
                f"{fdp.ConsumeIntInRange(-9999, 9999)}.{abs(fdp.ConsumeInt(3))}"
            )

        case 2:  # US thousands (1,234.56)
            return (
                f"{fdp.ConsumeIntInRange(1, 999)},"
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            )

        case 3:  # Space separators (fr-FR/lv-LV: 1 234.56)
            return (
                f"{fdp.ConsumeIntInRange(1, 999)} "
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            )

        case 4:  # German format (1.234,56)
            return (
                f"{fdp.ConsumeIntInRange(1, 999)}."
                f"{abs(fdp.ConsumeInt(3))},{abs(fdp.ConsumeInt(2))}"
            )

        case 5:  # Swiss format (1'234.56)
            return (
                f"{fdp.ConsumeIntInRange(1, 999)}'"
                f"{abs(fdp.ConsumeInt(3))}.{abs(fdp.ConsumeInt(2))}"
            )

        case 6:  # Scientific notation
            return (
                f"{fdp.ConsumeIntInRange(1, 9)}.{abs(fdp.ConsumeInt(2))}"
                f"e{fdp.ConsumeIntInRange(-10, 10)}"
            )

        case 7:  # Signed number
            sign = fdp.PickValueInList(["+", "-"])
            return f"{sign}{abs(fdp.ConsumeInt(4))}"

        case 8:  # Small decimal (0.000123)
            return f"0.{abs(fdp.ConsumeInt(6))}"

        case 9:  # Large integer
            return str(fdp.ConsumeIntInRange(100000, 999999999))

        # --- EDGE CASES (5 patterns) ---
        case 10:  # Zero variants
            return fdp.PickValueInList(
                ["0", "-0", "+0", "0.0", "-0.0", "+0.0"],
            )

        case 11:  # Special float values
            return fdp.PickValueInList(
                ["NaN", "Infinity", "-Infinity", "nan", "inf", "-inf"],
            )

        case 12:  # Extreme magnitude
            exp = fdp.ConsumeIntInRange(50, 308)
            if fdp.ConsumeBool():
                return f"1e{exp}"
            return f"1e-{exp}"

        case 13:  # Unicode digits (Arabic-Indic, Thai, etc.)
            return fdp.PickValueInList(
                [
                    "\u0660\u0661\u0662\u0663",  # Arabic-Indic
                    "\u06f1\u06f2\u06f3\u06f4\u06f5",  # Extended Arabic-Indic
                    "\u0e51\u0e52\u0e53",  # Thai
                    "\u17e0\u17e1\u17e2",  # Khmer
                ],
            )

        case 14:  # Malformed numbers
            return fdp.PickValueInList(
                [
                    "1.2.3",
                    "1..2",
                    "1e",
                    "1e-",
                    "+-1",
                    "++1",
                    "--1",
                    ",123",
                    ".123.",
                    "1,2,3",
                ],
            )

        # --- SECURITY/INVALID (4 patterns) ---
        case 15:  # Null bytes
            return f"1\x00{fdp.ConsumeIntInRange(0, 999)}"

        case 16:  # Very long number
            length = fdp.ConsumeIntInRange(100, 1000)
            return "1" * length

        case 17:  # Invalid strings
            return fdp.PickValueInList(["", "   ", "abc", "\t\n", "$100"])

        case 18:  # Raw bytes pass-through
            return fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 200))

        case _:
            return "42"


# Pattern dispatch table (pattern_name -> handler)
_PATTERN_DISPATCH: dict[str, Any] = {
    name: _generate_number_input for name, _ in _PATTERN_WEIGHTS
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test locale-aware number parsing."""
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

    locale = _generate_locale(fdp)
    input_str = _generate_number_input(fdp, pattern_name)

    # Fast-path rejection: empty or whitespace-only
    if not input_str or not input_str.strip():
        return

    try:
        res_d, _ = parse_decimal(input_str, locale)
        if res_d is not None:
            _domain.decimal_successes += 1
        else:
            _domain.decimal_failures += 1

    except (ValueError, TypeError, OverflowError) as e:
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
    except (RecursionError, MemoryError, FrozenFluentError) as e:
        # Expected: depth guards, resource limits
        error_key = type(e).__name__
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
    except Exception:
        # Unexpected exceptions are findings
        _state.findings += 1
        raise
    finally:
        # Semantic interestingness: unicode, malformed, extreme, raw, or slow
        is_interesting = (
            "unicode" in pattern_name
            or pattern_name in ("malformed", "raw_bytes", "extreme_magnitude")
            or (time.perf_counter() - start_time) * 1000 > 1.0
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
    """Run the numbers fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Numeric parser fuzzer using Atheris/libFuzzer",
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

    # Inject -rss_limit_mb default if not already specified
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Numeric Parser Unit Fuzzer (Atheris)",
        target="ftllexengine.parsing.numbers (parse_decimal)",
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
