#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: structured - Structure-aware fuzzing (Deep AST)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Structure-Aware Fuzzer (Atheris).

Generates syntactically plausible FTL using grammar-aware construction,
then applies byte-level mutations. This improves coverage penetration
compared to pure random byte fuzzing by exercising deep parser paths
that random bytes rarely reach.

Patterns:
- simple_messages: Basic message generation and parsing
- variable_messages: Messages with variable placeables
- term_definitions: Term entries with references
- attribute_messages: Messages with dot-attributes
- select_expressions: Select expressions with variant keys
- comment_entries: Comment generation (single/group/resource)
- multi_entry: Complete resources with mixed entry types
- corrupted_input: Grammar-aware FTL with byte corruption
- deep_nesting: Deeply nested placeables and references
- roundtrip_verify: Parse-serialize-reparse identity check

Metrics:
- Pattern coverage (10 patterns with weighted selection)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import string
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)


# --- Observability State ---
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

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest, in-memory corpus)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, str] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Structured-specific metrics
    parse_successes: int = 0
    parse_junk_entries: int = 0
    roundtrip_successes: int = 0
    roundtrip_mismatches: int = 0
    corruption_tests: int = 0
    deep_nesting_tests: int = 0

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


# Exception contract
ALLOWED_EXCEPTIONS = (ValueError, RecursionError, MemoryError, EOFError)

# Character sets for FTL generation per spec
IDENTIFIER_FIRST = string.ascii_letters
IDENTIFIER_REST = string.ascii_letters + string.digits + "-_"
TEXT_CHARS = string.ascii_letters + string.digits + " .,!?'-"
SPECIAL_CHARS = "\t\n\r\x00\x1f\x7f\u200b\ufeff"

# Weighted patterns for scenario selection
_PATTERNS: Sequence[str] = (
    "simple_messages",
    "variable_messages",
    "term_definitions",
    "attribute_messages",
    "select_expressions",
    "comment_entries",
    "multi_entry",
    "corrupted_input",
    "deep_nesting",
    "roundtrip_verify",
)
_PATTERN_WEIGHTS: Sequence[int] = (10, 12, 8, 10, 15, 5, 15, 10, 8, 7)


class StructuredFuzzError(Exception):
    """Raised when an unexpected exception is detected during structured fuzzing."""


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
            stats["memory_growth_mb"] = 0.0

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Structured-specific metrics
    stats["parse_successes"] = _state.parse_successes
    stats["parse_junk_entries"] = _state.parse_junk_entries
    stats["roundtrip_successes"] = _state.roundtrip_successes
    stats["roundtrip_mismatches"] = _state.roundtrip_mismatches
    stats["corruption_tests"] = _state.corruption_tests
    stats["deep_nesting_tests"] = _state.deep_nesting_tests

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_operations_tracked"] = len(_state.slowest_operations)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    try:
        report_file = (
            pathlib.Path(".fuzz_corpus") / "structured" / "fuzz_structured_report.json"
        )
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import Junk
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import FluentSerializer


# --- FTL Generators ---


def _generate_identifier(fdp: atheris.FuzzedDataProvider, max_len: int = 20) -> str:
    """Generate a valid FTL identifier using fuzzer decisions."""
    if not fdp.remaining_bytes():
        return "msg"

    first = IDENTIFIER_FIRST[fdp.ConsumeIntInRange(0, len(IDENTIFIER_FIRST) - 1)]
    rest_len = fdp.ConsumeIntInRange(0, max_len)

    rest_chars = []
    for _ in range(rest_len):
        if not fdp.remaining_bytes():
            break
        idx = fdp.ConsumeIntInRange(0, len(IDENTIFIER_REST) - 1)
        rest_chars.append(IDENTIFIER_REST[idx])

    return first + "".join(rest_chars)


def _generate_text(fdp: atheris.FuzzedDataProvider, max_len: int = 50) -> str:
    """Generate FTL-safe text content with Unicode support."""
    if not fdp.remaining_bytes():
        return "value"

    length = fdp.ConsumeIntInRange(1, max_len)

    # ~25% chance of full Unicode
    use_unicode = fdp.ConsumeBool() and fdp.ConsumeBool()

    if use_unicode and fdp.remaining_bytes() >= length:
        text = fdp.ConsumeUnicodeNoSurrogates(length)
        filtered = "".join(c for c in text if c not in "{}[]*$-.#\n\r")
        return filtered if filtered else "unicode"

    chars = []
    for _ in range(length):
        if not fdp.remaining_bytes():
            break
        if fdp.ConsumeBool() and fdp.ConsumeBool():
            idx = fdp.ConsumeIntInRange(0, len(SPECIAL_CHARS) - 1)
            chars.append(SPECIAL_CHARS[idx])
        else:
            idx = fdp.ConsumeIntInRange(0, len(TEXT_CHARS) - 1)
            chars.append(TEXT_CHARS[idx])

    return "".join(chars) or "value"


def _generate_variant_key(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a variant key (identifier or numeric literal)."""
    if not fdp.remaining_bytes():
        return "other"

    if fdp.ConsumeIntInRange(0, 9) < 4:
        is_decimal = fdp.ConsumeBool() if fdp.remaining_bytes() else False
        is_negative = fdp.ConsumeBool() if fdp.remaining_bytes() else False
        int_part = fdp.ConsumeIntInRange(0, 999) if fdp.remaining_bytes() else 1

        if is_decimal and fdp.remaining_bytes():
            decimal_part = fdp.ConsumeIntInRange(0, 99)
            num_str = f"{int_part}.{decimal_part:02d}"
        else:
            num_str = str(int_part)

        if is_negative:
            num_str = f"-{num_str}"
        return num_str

    return _generate_identifier(fdp, max_len=10)


def _generate_simple_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: msg-id = text value."""
    msg_id = _generate_identifier(fdp)
    value = _generate_text(fdp)
    return f"{msg_id} = {value}"


def _generate_variable_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: msg-id = prefix { $var } suffix."""
    msg_id = _generate_identifier(fdp)
    var_name = _generate_identifier(fdp, max_len=10)
    prefix = _generate_text(fdp, max_len=20)
    suffix = _generate_text(fdp, max_len=20)
    return f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"


def _generate_term(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: -term-id = value."""
    term_id = _generate_identifier(fdp)
    value = _generate_text(fdp)
    return f"-{term_id} = {value}"


def _generate_attribute_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate message with attributes."""
    msg_id = _generate_identifier(fdp)
    value = _generate_text(fdp)
    num_attrs = fdp.ConsumeIntInRange(1, 4) if fdp.remaining_bytes() else 1
    attrs = []
    for _ in range(num_attrs):
        if not fdp.remaining_bytes():
            break
        attr_name = _generate_identifier(fdp, max_len=10)
        attr_value = _generate_text(fdp, max_len=30)
        attrs.append(f"    .{attr_name} = {attr_value}")
    attr_block = "\n".join(attrs)
    return f"{msg_id} = {value}\n{attr_block}"


def _generate_select_expression(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate message with select expression."""
    msg_id = _generate_identifier(fdp)
    var_name = _generate_identifier(fdp, max_len=10)

    num_variants = fdp.ConsumeIntInRange(2, 5) if fdp.remaining_bytes() else 2
    default_idx = (
        fdp.ConsumeIntInRange(0, num_variants - 1)
        if fdp.remaining_bytes()
        else num_variants - 1
    )

    variants = []
    for i in range(num_variants):
        if not fdp.remaining_bytes():
            break
        key = _generate_variant_key(fdp)
        val = _generate_text(fdp, max_len=30)
        prefix = "*" if i == default_idx else " "
        variants.append(f"   {prefix}[{key}] {val}")

    variants_str = "\n".join(variants)
    return f"{msg_id} = {{ ${var_name} ->\n{variants_str}\n}}"


def _generate_comment(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate FTL comment (single, group, or resource)."""
    level = fdp.ConsumeIntInRange(1, 3) if fdp.remaining_bytes() else 1
    prefix = "#" * level
    content = _generate_text(fdp, max_len=40)
    return f"{prefix} {content}"


def _generate_ftl_resource(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a complete FTL resource with multiple entries."""
    if not fdp.remaining_bytes():
        return "fallback = Fallback value"

    num_entries = fdp.ConsumeIntInRange(1, 10)
    entries: list[str] = []

    generators = [
        _generate_simple_message,
        _generate_variable_message,
        _generate_term,
        _generate_attribute_message,
        _generate_select_expression,
        _generate_comment,
    ]

    for _ in range(num_entries):
        if not fdp.remaining_bytes():
            break
        gen_idx = fdp.ConsumeIntInRange(0, len(generators) - 1)
        try:
            entry = generators[gen_idx](fdp)
            entries.append(entry)
        except (IndexError, ValueError):
            break

    return "\n\n".join(entries) if entries else "fallback = Fallback value"


def _generate_deep_nesting(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate deeply nested placeables and references."""
    msg_id = _generate_identifier(fdp)
    depth = fdp.ConsumeIntInRange(3, 15) if fdp.remaining_bytes() else 5

    # Nested placeables: { { { $var } } }
    var_name = _generate_identifier(fdp, max_len=10)
    expr = f"${var_name}"
    for _ in range(depth):
        expr = f"{{ {expr} }}"

    result = f"{msg_id} = {expr}"

    # Optionally add a chain of message references
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 4:
        chain_len = fdp.ConsumeIntInRange(2, 8)
        chain_entries = [result]
        prev_id = msg_id
        for i in range(chain_len):
            if not fdp.remaining_bytes():
                break
            new_id = f"chain{i}"
            chain_entries.append(f"{new_id} = {{ {prev_id} }}")
            prev_id = new_id
        result = "\n".join(chain_entries)

    return result


# --- Pattern Selection ---


def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a test pattern using weighted distribution."""
    total = sum(_PATTERN_WEIGHTS)
    choice = fdp.ConsumeIntInRange(0, total - 1)

    cumulative = 0
    for i, w in enumerate(_PATTERN_WEIGHTS):
        cumulative += w
        if choice < cumulative:
            return _PATTERNS[i]

    return _PATTERNS[0]


# --- Verification ---


def _verify_roundtrip(source: str, parser: FluentParserV1) -> None:
    """Verify parse-serialize-reparse identity."""
    result = parser.parse(source)

    # Skip roundtrip if parse produced junk
    if any(isinstance(e, Junk) for e in result.entries):
        _state.parse_junk_entries += 1
        return

    _state.parse_successes += 1

    serializer = FluentSerializer()
    try:
        serialized = serializer.serialize(result)
        reparsed = parser.parse(serialized)

        # Entry count must match
        if len(result.entries) != len(reparsed.entries):
            _state.roundtrip_mismatches += 1
            msg = (
                f"Round-trip entry count mismatch: "
                f"{len(result.entries)} -> {len(reparsed.entries)}"
            )
            raise StructuredFuzzError(msg)

        # Convergence: serialize(reparse(serialize(parse(x)))) == serialize(parse(x))
        reserialized = serializer.serialize(reparsed)
        if serialized != reserialized:
            _state.roundtrip_mismatches += 1
            msg = "Round-trip convergence failure: S(P(S(P(x)))) != S(P(x))"
            raise StructuredFuzzError(msg)

        _state.roundtrip_successes += 1

    except ALLOWED_EXCEPTIONS:
        pass


def _parse_and_check(source: str, parser: FluentParserV1) -> None:
    """Parse source and verify non-trivial input produces entries."""
    result = parser.parse(source)

    if any(isinstance(e, Junk) for e in result.entries):
        _state.parse_junk_entries += 1
    else:
        _state.parse_successes += 1

    # Non-trivial input should produce entries
    if (
        len(result.entries) == 0
        and len(source.strip()) > 10
        and "corruption" not in source[:50]
    ):
        _state.findings += 1
        msg = f"Empty AST for non-trivial input: {source[:100]!r}"
        raise StructuredFuzzError(msg)


# --- Seed Corpus Management ---


def _track_slowest_operation(duration_ms: float, pattern: str, source: str) -> None:
    """Track top 10 slowest operations using max-heap."""
    input_hash = hashlib.sha256(
        source.encode("utf-8", errors="surrogatepass"),
    ).hexdigest()[:16]
    entry: InterestingInput = (-duration_ms, pattern, input_hash)

    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, entry)
    elif -duration_ms < _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, entry)


def _track_seed_corpus(source: str, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs with FIFO eviction."""
    is_interesting = (
        duration_ms > 50.0
        or "deep_nesting" in pattern
        or "corrupted" in pattern
        or "roundtrip" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(
            source.encode("utf-8", errors="surrogatepass"),
        ).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = source
            _state.corpus_entries_added += 1


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: generate structured FTL and detect crashes."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern = _select_pattern(fdp)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=100)
    source = ""

    try:
        match pattern:
            case "simple_messages":
                source = _generate_simple_message(fdp)
                _parse_and_check(source, parser)

            case "variable_messages":
                source = _generate_variable_message(fdp)
                _parse_and_check(source, parser)

            case "term_definitions":
                source = _generate_term(fdp)
                # Add a referencing message so term is exercised
                ref_id = _generate_identifier(fdp)
                term_name = source.split("=", maxsplit=1)[0].strip()
                source += f"\n{ref_id} = {{ {term_name} }}"
                _parse_and_check(source, parser)

            case "attribute_messages":
                source = _generate_attribute_message(fdp)
                _parse_and_check(source, parser)

            case "select_expressions":
                source = _generate_select_expression(fdp)
                _parse_and_check(source, parser)

            case "comment_entries":
                source = _generate_comment(fdp)
                # Comments alone produce entries
                parser.parse(source)

            case "multi_entry":
                source = _generate_ftl_resource(fdp)
                _parse_and_check(source, parser)

            case "corrupted_input":
                _state.corruption_tests += 1
                source = _generate_ftl_resource(fdp)
                if fdp.remaining_bytes() and len(source) > 0:
                    pos = fdp.ConsumeIntInRange(0, len(source) - 1)
                    corruption = fdp.ConsumeUnicodeNoSurrogates(
                        min(3, fdp.remaining_bytes()),
                    )
                    source = source[:pos] + corruption + source[pos + 1:]
                with contextlib.suppress(*ALLOWED_EXCEPTIONS):
                    parser.parse(source)

            case "deep_nesting":
                _state.deep_nesting_tests += 1
                source = _generate_deep_nesting(fdp)
                with contextlib.suppress(*ALLOWED_EXCEPTIONS):
                    _parse_and_check(source, parser)

            case "roundtrip_verify":
                source = _generate_ftl_resource(fdp)
                _verify_roundtrip(source, parser)

    except StructuredFuzzError:
        _state.findings += 1
        _state.status = "finding"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

        _state.findings += 1
        _state.status = "finding"

        print("\n" + "=" * 80, file=sys.stderr)
        print("[FINDING] STABILITY BREACH DETECTED (Structure-Aware)", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}", file=sys.stderr)
        print(f"Error Message:  {e}", file=sys.stderr)
        print(f"Input Preview:  {source[:200]!r}...", file=sys.stderr)
        print("-" * 80, file=sys.stderr)

        msg = f"{type(e).__name__}: {e}"
        raise StructuredFuzzError(msg) from e

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern] = (
            _state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern, source)
        _track_seed_corpus(source, pattern, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the structure-aware fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Structure-aware FTL fuzzer using Atheris/libFuzzer",
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

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Structure-Aware Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     FluentParserV1, FluentSerializer (grammar-aware construction)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
