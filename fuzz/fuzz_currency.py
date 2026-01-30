#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: currency - Currency symbol & numeric extraction
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Currency Parsing Fuzzer (Atheris).

Targets: ftllexengine.parsing.currency.parse_currency
Tests tiered loading, ambiguous symbol resolution, and numeric extraction.

Metrics:
- Fast tier vs full tier usage (CLDR scan trigger rate)
- Ambiguous symbol resolution accuracy
- Locale inference success rate
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution (parse failures, invalid codes, ambiguous symbols)
- Seed corpus management (interesting inputs)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks with Clear Errors ---
_MISSING_DEPS: list[str] = []

try:
    import psutil
except ImportError:
    _MISSING_DEPS.append("psutil")
    psutil = None  # type: ignore[assignment]

try:
    import atheris
except ImportError:
    _MISSING_DEPS.append("atheris")
    atheris = None  # type: ignore[assignment]

if _MISSING_DEPS:
    print("-" * 80, file=sys.stderr)
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- Type Aliases (PEP 695, requires Python 3.12+) ---
type FuzzStats = dict[str, int | str | float]
type InterestingInput = tuple[float, str, str]  # (parse_time_ms, pattern, input_hash)


# --- Observability State (Dataclass for better organization) ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest, in-memory corpus)
    slowest_parses: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, str] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Currency-specific metrics
    fast_tier_hits: int = 0
    full_tier_hits: int = 0
    ambiguous_resolutions: int = 0
    locale_inferences: int = 0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 1000


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
    }

    # Performance percentiles
    if _state.performance_history:
        perf_data = list(_state.performance_history)
        n = len(perf_data)
        stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        stats["perf_min_ms"] = round(min(perf_data), 3)
        stats["perf_max_ms"] = round(max(perf_data), 3)
        # Only compute percentiles if we have enough data
        if n >= 20:
            quantiles = statistics.quantiles(perf_data, n=20)
            stats["perf_p95_ms"] = round(quantiles[18], 3)
        if n >= 100:
            quantiles = statistics.quantiles(perf_data, n=100)
            stats["perf_p99_ms"] = round(quantiles[98], 3)

    # Memory tracking
    if _state.memory_history:
        mem_data = list(_state.memory_history)
        stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        stats["memory_peak_mb"] = round(max(mem_data), 2)
        stats["memory_delta_mb"] = round(max(mem_data) - _state.initial_memory_mb, 2)

        # Memory leak detection (compare first vs last quartile for better accuracy)
        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            first_avg = statistics.mean(first_quarter)
            last_avg = statistics.mean(last_quarter)
            growth_mb = last_avg - first_avg
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution (clean keys)
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        # Sanitize error key for JSON (limit length, remove problematic chars)
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Currency-specific metrics
    stats["fast_tier_hits"] = _state.fast_tier_hits
    stats["full_tier_hits"] = _state.full_tier_hits
    stats["ambiguous_resolutions"] = _state.ambiguous_resolutions
    stats["locale_inferences"] = _state.locale_inferences

    # Tier ratio
    total_tier_hits = _state.fast_tier_hits + _state.full_tier_hits
    if total_tier_hits > 0:
        stats["fast_tier_ratio"] = round(_state.fast_tier_hits / total_tier_hits, 3)

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_parses_tracked"] = len(_state.slowest_parses)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    # Emit to stderr for capture
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    # Write to file for shell script parsing (best-effort)
    try:
        report_file = pathlib.Path(".fuzz_corpus") / "currency" / "fuzz_currency_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

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
    "\u20ac",  # € Euro
    "\u20b9",  # ₹ Indian Rupee
    "\u20bd",  # ₽ Russian Ruble
    "\u20ba",  # ₺ Turkish Lira
    "\u20aa",  # ₪ Israeli Shekel
    "\u20a6",  # ₦ Nigerian Naira
    "\u20b1",  # ₱ Philippine Peso
    "\u20bf",  # ₿ Bitcoin
    "\u20ab",  # ₫ Vietnamese Dong
    "\u20b4",  # ₴ Ukrainian Hryvnia
    "\u20b8",  # ₸ Kazakh Tenge
    "\u20bc",  # ₼ Azerbaijani Manat
)

# Ambiguous symbols (require locale for disambiguation)
AMBIGUOUS_SYMBOLS: Sequence[str] = (
    "$",  # USD, CAD, AUD, etc.
    "\u00a3",  # £ GBP, EGP, GIP, etc.
    "\u00a5",  # ¥ JPY, CNY
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


def _generate_currency_pattern(  # noqa: PLR0911, PLR0912, PLR0915
    fdp: atheris.FuzzedDataProvider,
) -> tuple[str, str, str]:
    """Generate currency pattern for testing.

    Returns:
        (pattern_name, input_string, locale)
    """
    # Weight pattern selection to reduce bias toward specific patterns
    # Patterns 0-15: original 12 + raw_bytes, fullwidth, code_symbol_combo, differential
    weights = [8, 8, 7, 7, 7, 7, 7, 8, 7, 7, 7, 5, 10, 5, 5, 5]  # 16 patterns
    total_weight = sum(weights)
    choice = fdp.ConsumeIntInRange(0, total_weight - 1)

    cumulative = 0
    pattern_choice = 0
    for i, weight in enumerate(weights):
        cumulative += weight
        if choice < cumulative:
            pattern_choice = i
            break

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
            return ("unambiguous_unicode", input_str, locale)

        case 1:  # Ambiguous dollar sign (requires locale)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"${amount:.2f}" if fdp.ConsumeBool() else f"{amount:.2f}$"
            return ("ambiguous_dollar", input_str, locale)

        case 2:  # Ambiguous pound sign (GBP, EGP, GIP)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a3{amount:.2f}"
            return ("ambiguous_pound", input_str, locale)

        case 3:  # Ambiguous yen/yuan sign (JPY, CNY)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"\u00a5{amount:.2f}"
            return ("ambiguous_yen_yuan", input_str, locale)

        case 4:  # Ambiguous "kr" (SEK, NOK, DKK, ISK)
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = (
                f"{amount:.2f} kr" if fdp.ConsumeBool() else f"kr {amount:.2f}"
            )
            return ("ambiguous_kr", input_str, locale)

        case 5:  # Comma as decimal separator (European format)
            symbol = fdp.PickValueInList(["\u20ac", "$", "\u00a3"])
            amount_int = fdp.ConsumeIntInRange(1, 999999)
            amount_frac = fdp.ConsumeIntInRange(0, 99)
            input_str = f"{symbol}{amount_int},{amount_frac:02d}"
            return ("comma_decimal", input_str, locale)

        case 6:  # Period as grouping separator (European format) - varied amounts
            symbol = fdp.PickValueInList(["\u20ac", "$"])
            # Generate varied amounts instead of fixed string
            thousands = fdp.ConsumeIntInRange(1, 999)
            hundreds = fdp.ConsumeIntInRange(0, 999)
            ones = fdp.ConsumeIntInRange(0, 999)
            cents = fdp.ConsumeIntInRange(0, 99)
            input_str = f"{symbol}{thousands}.{hundreds:03d}.{ones:03d},{cents:02d}"
            return ("period_grouping", input_str, locale)

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
            return ("negative_format", input_str, locale)

        case 8:  # Explicit ISO code (bypass symbol resolution)
            code = fdp.PickValueInList(list(ISO_CODES))
            amount = fdp.ConsumeFloatInRange(0.01, 999999.99)
            input_str = f"{amount:.2f} {code}"
            return ("explicit_iso_code", input_str, locale)

        case 9:  # Invalid ISO codes (error testing)
            invalid_code = fdp.PickValueInList(list(INVALID_ISO_CODES))
            amount = fdp.ConsumeFloatInRange(0.01, 9999.99)
            input_str = f"{amount:.2f} {invalid_code}"
            return ("invalid_iso_code", input_str, locale)

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
            return ("whitespace_variation", input_str, locale)

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
            return ("edge_case", input_str, locale)

        case 12:  # Raw bytes pass-through (let libFuzzer mutations drive)
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 200))
            return ("raw_bytes", raw, locale)

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
            return ("fullwidth_digits", input_str, locale)

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
            return ("code_symbol_combo", input_str, locale)

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
            return ("special_number", input_str, locale)

        case _:
            # Unreachable fallback
            return ("fallback", "$100.00", "en-US")


def _track_slowest_parse(
    parse_time_ms: float,
    pattern: str,
    input_str: str,
) -> None:
    """Track top 10 slowest parses using max-heap (negated values)."""
    input_hash = hashlib.sha256(input_str.encode("utf-8", errors="surrogatepass")).hexdigest()[:16]
    # Negate parse_time to create max-heap (heapq is min-heap by default)
    entry: InterestingInput = (-parse_time_ms, pattern, input_hash)

    if len(_state.slowest_parses) < 10:
        heapq.heappush(_state.slowest_parses, entry)
    elif -parse_time_ms < _state.slowest_parses[0][0]:  # Slower than minimum
        heapq.heapreplace(_state.slowest_parses, entry)


def _track_seed_corpus(input_str: str, pattern: str, parse_time_ms: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    # Interesting if: slow parse (>10ms), ambiguous symbol, or edge case
    is_interesting = (
        parse_time_ms > 10.0 or "ambiguous" in pattern or "edge_case" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(
            input_str.encode("utf-8", errors="surrogatepass")
        ).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            # Evict oldest entry if at capacity (simple FIFO eviction)
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_str
            _state.corpus_entries_added += 1


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Test currency parsing boundary conditions.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil
    - Pattern coverage: 16 currency format types
    - Error distribution: Categorized parse failures
    - Corpus: Interesting inputs (slow/ambiguous/edge cases)
    """
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic report write for shell script parsing
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    # Generate currency pattern (12 pattern types with weighted selection)
    pattern_name, input_str, locale = _generate_currency_pattern(fdp)
    _state.pattern_coverage[pattern_name] = _state.pattern_coverage.get(pattern_name, 0) + 1

    # Optional: override with default_currency and infer_from_locale
    # Generate valid 3-letter uppercase codes or None
    default_curr: str | None = None
    if fdp.ConsumeBool():
        raw_curr = fdp.ConsumeBytes(3).decode("ascii", errors="ignore").upper()
        if len(raw_curr) == 3 and raw_curr.isalpha():
            default_curr = raw_curr

    infer = fdp.ConsumeBool()
    if infer:
        _state.locale_inferences += 1

    try:
        res, errors = parse_currency(
            input_str,
            locale,
            default_currency=default_curr,
            infer_from_locale=infer,
        )

        # Track tier usage (heuristic: fast tier for unambiguous, full tier for ambiguous)
        if "unambiguous" in pattern_name:
            _state.fast_tier_hits += 1
        elif "ambiguous" in pattern_name:
            _state.full_tier_hits += 1
            _state.ambiguous_resolutions += 1

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
        # Performance tracking
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        # Per-pattern wall time accumulation
        _state.pattern_wall_time[pattern_name] = (
            _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
        )

        # Track interesting inputs
        _track_slowest_parse(elapsed_ms, pattern_name, input_str)
        _track_seed_corpus(input_str, pattern_name, elapsed_ms)

        # Memory tracking (every 100 iterations to reduce overhead)
        if _state.iterations % 100 == 0:
            current_memory_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_memory_mb)


def main() -> None:
    """Run the currency fuzzer with optional --help."""
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
        default=1000,
        help="Maximum size of in-memory seed corpus (default: 1000)",
    )

    # Parse known args, pass rest to Atheris/libFuzzer
    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Currency Parsing Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.parsing.currency.parse_currency")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
