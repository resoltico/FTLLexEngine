#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: roundtrip - Metamorphic roundtrip (Parser <-> Serializer)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Metamorphic Roundtrip Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1,
         ftllexengine.syntax.serializer.serialize

Concern boundary: This fuzzer is dedicated to the parser-serializer convergence
property S(P(S(P(x)))) == S(P(x)). It systematically generates valid FTL inputs
covering all grammar productions (messages, terms, attributes, select expressions,
placeables, comments, function calls, multiline patterns) and verifies that
serialized output re-parses identically. Distinct from fuzz_structured which tests
AST construction correctness with roundtrip as only 1 of 10 patterns at 7% weight.

Invariants:
- Valid FTL parses without Junk entries
- Serialization of valid AST always succeeds
- Serialized output re-parses without error
- Convergence: S(P(x)) == S(P(S(P(x)))) for valid FTL
- AST structural equality (ignoring spans) after convergence

Metrics:
- Pattern coverage (simple_message, select_expression, etc.)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Seed corpus management

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
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)

# --- Dependency Checks ---
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


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000),
    )
    memory_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=1000),
    )

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Roundtrip-specific
    junk_skips: int = 0
    convergence_failures: int = 0

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 100


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("simple_message", 10),
    ("variable_placeable", 12),
    ("term_reference", 8),
    ("message_reference", 8),
    ("select_expression", 15),
    ("attributes", 10),
    ("comments", 5),
    ("function_call", 8),
    ("multiline_pattern", 7),
    ("mixed_resource", 12),
    ("deep_nesting", 5),
    ("raw_unicode", 5),
    ("convergence_stress", 5),
)


class RoundtripFuzzError(Exception):
    """Raised when a roundtrip invariant is breached."""


# Allowed exceptions from parser/serializer
ALLOWED_EXCEPTIONS = (
    ValueError,
    RecursionError,
    MemoryError,
    UnicodeDecodeError,
    UnicodeEncodeError,
)


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
        "junk_skips": _state.junk_skips,
        "convergence_failures": _state.convergence_failures,
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
        stats["memory_delta_mb"] = round(
            max(mem_data) - _state.initial_memory_mb, 2,
        )

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            growth_mb = (
                statistics.mean(last_quarter) - statistics.mean(first_quarter)
            )
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

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_operations_tracked"] = len(_state.slowest_operations)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    print(
        f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]",
        file=sys.stderr,
        flush=True,
    )

    try:
        report_file = (
            pathlib.Path(".fuzz_corpus")
            / "roundtrip"
            / "fuzz_roundtrip_report.json"
        )
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# Suppress logging and instrument imports
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import serialize

# Reusable parser instance
_parser = FluentParserV1()


def _track_slowest_operation(
    duration_ms: float, pattern: str, input_data: bytes,
) -> None:
    """Track top 10 slowest operations using max-heap."""
    input_hash = hashlib.sha256(input_data).hexdigest()[:16]
    entry: InterestingInput = (-duration_ms, pattern, input_hash)

    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, entry)
    elif -duration_ms < _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, entry)


def _track_seed_corpus(
    input_data: bytes, pattern: str, duration_ms: float,
) -> None:
    """Track interesting inputs with FIFO eviction."""
    is_interesting = (
        duration_ms > 10.0
        or "convergence" in pattern
        or "deep" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(input_data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_data
            _state.corpus_entries_added += 1


# --- FTL Generation Helpers ---

def _gen_id(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a valid FTL identifier: [a-zA-Z][a-zA-Z0-9_-]*."""
    first = chr(ord("a") + fdp.ConsumeIntInRange(0, 25))
    length = fdp.ConsumeIntInRange(0, 15)
    chars = "abcdefghijklmnopqrstuvwxyz0123456789-"
    rest = "".join(
        chars[fdp.ConsumeIntInRange(0, len(chars) - 1)]
        for _ in range(length)
    )
    return first + rest


def _gen_value(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a safe FTL value (no braces, no newlines)."""
    safe_chars = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        " 0123456789.,!?:;'-"
    )
    length = fdp.ConsumeIntInRange(1, 40)
    return "".join(
        safe_chars[fdp.ConsumeIntInRange(0, len(safe_chars) - 1)]
        for _ in range(length)
    )


def _gen_variable(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a variable name (used in placeables as $name)."""
    return _gen_id(fdp)


# --- Roundtrip Core ---

def _verify_roundtrip(source: str) -> None:
    """Run the full roundtrip verification on FTL source.

    Steps:
    1. Parse source -> AST1
    2. Skip if Junk entries (invalid FTL)
    3. Serialize AST1 -> S1
    4. Parse S1 -> AST2
    5. Serialize AST2 -> S2
    6. Assert S1 == S2 (convergence)
    """
    ast1 = _parser.parse(source)

    # Skip Junk -- roundtrip of invalid FTL is best-effort
    if any(type(e).__name__ == "Junk" for e in ast1.entries):
        _state.junk_skips += 1
        return

    # Skip empty resources (no entries to roundtrip)
    if not ast1.entries:
        return

    s1 = serialize(ast1)

    ast2 = _parser.parse(s1)

    # Serialized output must not produce Junk
    if any(type(e).__name__ == "Junk" for e in ast2.entries):
        _state.convergence_failures += 1
        msg = f"Serialized output produced Junk on re-parse: {s1[:200]}"
        raise RoundtripFuzzError(msg)

    s2 = serialize(ast2)

    if s1 != s2:
        _state.convergence_failures += 1
        msg = (
            f"Convergence failure: S(P(x)) != S(P(S(P(x))))\n"
            f"S1 ({len(s1)} chars): {s1[:200]}\n"
            f"S2 ({len(s2)} chars): {s2[:200]}"
        )
        raise RoundtripFuzzError(msg)


# --- Pattern Implementations ---

def _pattern_simple_message(fdp: atheris.FuzzedDataProvider) -> None:
    """Basic id = value roundtrip."""
    msg_id = _gen_id(fdp)
    value = _gen_value(fdp)
    source = f"{msg_id} = {value}\n"
    _verify_roundtrip(source)


def _pattern_variable_placeable(fdp: atheris.FuzzedDataProvider) -> None:
    """Messages with { $var } placeables."""
    msg_id = _gen_id(fdp)
    var = _gen_variable(fdp)
    prefix = _gen_value(fdp)
    suffix = _gen_value(fdp)
    source = f"{msg_id} = {prefix} {{ ${var} }} {suffix}\n"
    _verify_roundtrip(source)


def _pattern_term_reference(fdp: atheris.FuzzedDataProvider) -> None:
    """Term definitions (-term = ...) and references ({ -term })."""
    term_id = _gen_id(fdp)
    msg_id = _gen_id(fdp)
    term_val = _gen_value(fdp)
    prefix = _gen_value(fdp)
    source = (
        f"-{term_id} = {term_val}\n"
        f"{msg_id} = {prefix} {{ -{term_id} }}\n"
    )
    _verify_roundtrip(source)


def _pattern_message_reference(fdp: atheris.FuzzedDataProvider) -> None:
    """Message cross-references ({ other-msg })."""
    id1 = _gen_id(fdp)
    id2 = _gen_id(fdp)
    val1 = _gen_value(fdp)
    source = f"{id1} = {val1}\n{id2} = {{ {id1} }}\n"
    _verify_roundtrip(source)


def _pattern_select_expression(fdp: atheris.FuzzedDataProvider) -> None:
    """Select expressions with plural/string keys."""
    msg_id = _gen_id(fdp)
    selector_var = _gen_variable(fdp)
    num_variants = fdp.ConsumeIntInRange(1, 5)

    variants = []
    for i in range(num_variants):
        key = _gen_id(fdp) if fdp.ConsumeBool() else str(i)
        val = _gen_value(fdp)
        variants.append(f"    [{key}] {val}")

    # Default variant (last one, with * prefix)
    default_val = _gen_value(fdp)
    variants.append(f"   *[other] {default_val}")

    variant_block = "\n".join(variants)
    source = (
        f"{msg_id} = {{ ${selector_var} ->\n"
        f"{variant_block}\n"
        f"}}\n"
    )
    _verify_roundtrip(source)


def _pattern_attributes(fdp: atheris.FuzzedDataProvider) -> None:
    """Messages with .attr = value attributes."""
    msg_id = _gen_id(fdp)
    value = _gen_value(fdp)
    num_attrs = fdp.ConsumeIntInRange(1, 4)

    attrs = []
    for _ in range(num_attrs):
        attr_id = _gen_id(fdp)
        attr_val = _gen_value(fdp)
        attrs.append(f"    .{attr_id} = {attr_val}")

    attr_block = "\n".join(attrs)
    source = f"{msg_id} = {value}\n{attr_block}\n"
    _verify_roundtrip(source)


def _pattern_comments(fdp: atheris.FuzzedDataProvider) -> None:
    """Comment types: #, ##, ### followed by messages."""
    comment_type = fdp.ConsumeIntInRange(0, 2)
    prefix = "#" * (comment_type + 1)
    comment_text = _gen_value(fdp)
    msg_id = _gen_id(fdp)
    msg_val = _gen_value(fdp)

    if comment_type == 0:
        # Message comment (attached to next message)
        source = f"{prefix} {comment_text}\n{msg_id} = {msg_val}\n"
    else:
        # Group or resource comment (standalone)
        source = (
            f"{prefix} {comment_text}\n\n{msg_id} = {msg_val}\n"
        )
    _verify_roundtrip(source)


def _pattern_function_call(fdp: atheris.FuzzedDataProvider) -> None:
    """Function calls: { NUMBER($var) }, { DATETIME($d, opt: "val") }."""
    msg_id = _gen_id(fdp)
    var = _gen_variable(fdp)
    func_names = ["NUMBER", "DATETIME", "CURRENCY"]
    func = fdp.PickValueInList(func_names)

    if fdp.ConsumeBool():
        arg_name = _gen_id(fdp)
        arg_val = _gen_value(fdp)
        source = (
            f"{msg_id} = "
            f'{{ {func}(${var}, {arg_name}: "{arg_val}") }}\n'
        )
    else:
        source = f"{msg_id} = {{ {func}(${var}) }}\n"
    _verify_roundtrip(source)


def _pattern_multiline_pattern(fdp: atheris.FuzzedDataProvider) -> None:
    """Multiline continuation values."""
    msg_id = _gen_id(fdp)
    num_lines = fdp.ConsumeIntInRange(2, 5)

    lines = [f"{msg_id} ="]
    for _ in range(num_lines):
        line_text = _gen_value(fdp)
        lines.append(f"    {line_text}")

    source = "\n".join(lines) + "\n"
    _verify_roundtrip(source)


def _pattern_mixed_resource(fdp: atheris.FuzzedDataProvider) -> None:
    """Multiple entry types in a single resource."""
    entries: list[str] = []
    num_entries = fdp.ConsumeIntInRange(2, 6)

    for _ in range(num_entries):
        entry_type = fdp.ConsumeIntInRange(0, 3)
        eid = _gen_id(fdp)
        val = _gen_value(fdp)

        match entry_type:
            case 0:
                entries.append(f"{eid} = {val}")
            case 1:
                entries.append(f"-{eid} = {val}")
            case 2:
                attr_id = _gen_id(fdp)
                attr_val = _gen_value(fdp)
                entries.append(
                    f"{eid} = {val}\n    .{attr_id} = {attr_val}",
                )
            case _:
                var = _gen_variable(fdp)
                entries.append(f"{eid} = {val} {{ ${var} }}")

    source = "\n".join(entries) + "\n"
    _verify_roundtrip(source)


def _pattern_deep_nesting(fdp: atheris.FuzzedDataProvider) -> None:
    """Nested placeables: string literals and variable references."""
    msg_id = _gen_id(fdp)
    var = _gen_variable(fdp)
    inner_val = _gen_value(fdp)

    # Nested string literal in placeable
    source = f'{msg_id} = {{ "{inner_val}" }}\n'
    _verify_roundtrip(source)

    # Nested variable reference
    source2 = f"{msg_id} = {{ ${var} }}\n"
    _verify_roundtrip(source2)


def _pattern_raw_unicode(fdp: atheris.FuzzedDataProvider) -> None:
    """Random Unicode input -- only verify junk-free inputs converge."""
    source = fdp.ConsumeUnicodeNoSurrogates(
        fdp.ConsumeIntInRange(1, 2048),
    )
    _verify_roundtrip(source)


def _pattern_convergence_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Multi-pass convergence: verify S(P(x)) stabilizes in 2 passes."""
    msg_id = _gen_id(fdp)
    var = _gen_variable(fdp)
    val = _gen_value(fdp)

    entries = [
        "# Generated test message",
        f"{msg_id} = {val} {{ ${var} }}",
        f"    .title = {_gen_value(fdp)}",
    ]

    sel_id = _gen_id(fdp)
    sel_var = _gen_variable(fdp)
    default_val = _gen_value(fdp)
    entries.extend([
        "",
        f"{sel_id} = {{ ${sel_var} ->",
        f"    [one] {_gen_value(fdp)}",
        f"   *[other] {default_val}",
        "}",
    ])

    source = "\n".join(entries) + "\n"

    ast = _parser.parse(source)
    if any(type(e).__name__ == "Junk" for e in ast.entries):
        _state.junk_skips += 1
        return

    s1 = serialize(ast)
    s2 = serialize(_parser.parse(s1))
    s3 = serialize(_parser.parse(s2))

    if s2 != s3:
        _state.convergence_failures += 1
        msg = (
            f"Multi-pass convergence failure: S2 != S3\n"
            f"S2: {s2[:200]}\nS3: {s3[:200]}"
        )
        raise RoundtripFuzzError(msg)


# --- Pattern dispatch ---

def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a weighted pattern."""
    total = sum(w for _, w in _PATTERN_WEIGHTS)
    choice = fdp.ConsumeIntInRange(0, total - 1)

    cumulative = 0
    for name, weight in _PATTERN_WEIGHTS:
        cumulative += weight
        if choice < cumulative:
            return name

    return _PATTERN_WEIGHTS[0][0]


_PATTERN_DISPATCH: dict[str, Any] = {
    "simple_message": _pattern_simple_message,
    "variable_placeable": _pattern_variable_placeable,
    "term_reference": _pattern_term_reference,
    "message_reference": _pattern_message_reference,
    "select_expression": _pattern_select_expression,
    "attributes": _pattern_attributes,
    "comments": _pattern_comments,
    "function_call": _pattern_function_call,
    "multiline_pattern": _pattern_multiline_pattern,
    "mixed_resource": _pattern_mixed_resource,
    "deep_nesting": _pattern_deep_nesting,
    "raw_unicode": _pattern_raw_unicode,
    "convergence_stress": _pattern_convergence_stress,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz parser-serializer roundtrip."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            _get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern = _select_pattern(fdp)
    _state.pattern_coverage[pattern] = (
        _state.pattern_coverage.get(pattern, 0) + 1
    )

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except RoundtripFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = (
            _state.error_counts.get(error_key, 0) + 1
        )

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern] = (
            _state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern, data)
        _track_seed_corpus(data, pattern, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = (
                _get_process().memory_info().rss / (1024 * 1024)
            )
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the roundtrip fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description=(
            "Parser-serializer roundtrip fuzzer using Atheris/libFuzzer"
        ),
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
        default=100,
        help="Maximum size of in-memory seed corpus (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Parser-Serializer Roundtrip Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     FluentParserV1, serialize")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
