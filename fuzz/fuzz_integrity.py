#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: integrity - Multi-Resource Semantic Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Multi-Resource Integrity Fuzzer (Atheris).

Targets: ftllexengine.validation.validate_resource + FluentBundle cross-resource checks

Concern boundary: This fuzzer targets semantic integrity validation -- circular
references, undefined references, term visibility, duplicate IDs, cross-resource
dependencies, and strict mode enforcement. This is distinct from the runtime fuzzer
(resolver/cache stack), currency fuzzer (numeric parsing), OOM fuzzer (parser AST
explosion), and cache fuzzer (IntegrityCache concurrency).

Metrics:
- Validation error/warning classification and counting
- Cross-resource conflict detection
- Strict vs. non-strict mode coverage
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)
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
    print("Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- Type Aliases (PEP 695) ---
type FuzzStats = dict[str, int | str | float]
type SlowestEntry = tuple[float, str]  # (duration_ms, ftl_snippet)


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

    # Slowest validations (min-heap, top 10)
    slowest_validations: list[SlowestEntry] = field(default_factory=list)

    # Validation result tracking
    error_counts: dict[str, int] = field(default_factory=dict)
    warning_counts: dict[str, int] = field(default_factory=dict)

    # Coverage tracking
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    strict_mode_count: int = 0
    non_strict_mode_count: int = 0

    # Seed corpus (hash -> source, LRU eviction)
    seed_corpus: dict[str, str] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

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
    """Build flat stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
        "strict_mode_iterations": _state.strict_mode_count,
        "non_strict_mode_iterations": _state.non_strict_mode_count,
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

        # Memory leak detection (quarter comparison for accuracy)
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

    # Validation error/warning distribution
    for error_code, count in sorted(_state.error_counts.items()):
        stats[f"error_{error_code}"] = count
    for warning_code, count in sorted(_state.warning_counts.items()):
        stats[f"warning_{warning_code}"] = count

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Corpus
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_validations_tracked"] = len(_state.slowest_validations)

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
        report_file = pathlib.Path(".fuzz_corpus") / "integrity" / "fuzz_integrity_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort file write


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import DataIntegrityError
    from ftllexengine.runtime.bundle import FluentBundle


# --- Constants ---
_TEST_LOCALES: Sequence[str] = (
    "en-US",
    "de-DE",
    "lv-LV",
    "ar-SA",
    "ja-JP",
    "root",
)


def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale for bundle creation.

    Weighted 90% valid / 10% invalid to ensure validation logic is exercised.
    """
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


def _generate_ftl_resource(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
    resource_idx: int,
) -> tuple[str, str]:
    """Generate FTL resource with weighted integrity-focused strategies.

    23 pattern types targeting validation and cross-resource integrity.
    Returns (pattern_name, ftl_source).
    """
    # Weights: valid(9) + edge(9) + invalid(5) = 23 patterns
    weights = [
        # Valid (9 patterns)
        8,
        8,
        7,
        7,
        8,
        7,
        7,
        7,
        7,
        # Edge cases (9 patterns)
        6,
        6,
        6,
        6,
        6,
        6,
        6,
        6,
        6,
        # Invalid (5 patterns)
        5,
        5,
        5,
        5,
        10,
    ]
    total_weight = sum(weights)
    choice = fdp.ConsumeIntInRange(0, total_weight - 1)

    cumulative = 0
    pattern_choice = 0
    for i, weight in enumerate(weights):
        cumulative += weight
        if choice < cumulative:
            pattern_choice = i
            break

    ri = resource_idx

    match pattern_choice:
        # --- VALID FTL (9 patterns) ---
        case 0:  # Simple message
            return ("simple_message", f"msg_{ri} = Simple value\n")

        case 1:  # Message with attribute
            return ("message_attr", f"msg_{ri} = Value\n    .attr = Attribute\n")

        case 2:  # Message referencing another (same resource)
            return ("message_ref", (f"msg_{ri}_a = First\nmsg_{ri}_b = {{ msg_{ri}_a }}\n"))

        case 3:  # Term definition
            return ("term_def", f"-term_{ri} = Term value\n")

        case 4:  # Message using term
            return ("term_usage", (f"-term_{ri} = T\nmsg_{ri} = {{ -term_{ri} }}\n"))

        case 5:  # Select expression
            return (
                "select_expr",
                (f"msg_{ri} = {{ $count ->\n    [one] One item\n   *[other] Many items\n}}\n"),
            )

        case 6:  # Multiple entries
            return (
                "multiple_entries",
                (f"msg_{ri}_1 = First\nmsg_{ri}_2 = Second\n-term_{ri} = Term\n"),
            )

        case 7:  # Message with comment
            return ("comment_message", f"# Comment\nmsg_{ri} = Value\n")

        case 8:  # Complex pattern with variable
            return ("complex_pattern", f"msg_{ri} = Start {{ $var }} end\n")

        # --- EDGE CASES (9 patterns) ---
        case 9:  # Circular reference (within resource)
            return (
                "circular_2way",
                (f"msg_{ri}_a = {{ msg_{ri}_b }}\nmsg_{ri}_b = {{ msg_{ri}_a }}\n"),
            )

        case 10:  # Undefined reference
            return ("undefined_ref", f"msg_{ri} = {{ undefined_msg }}\n")

        case 11:  # Duplicate ID
            return ("duplicate_id", (f"msg_{ri} = First\nmsg_{ri} = Duplicate\n"))

        case 12:  # Message without value (attributes only)
            return ("attr_only", f"msg_{ri} =\n    .attr = Attribute only\n")

        case 13:  # Deep reference chain
            depth = fdp.ConsumeIntInRange(3, 10)
            chain = "\n".join(f"msg_{ri}_{j} = {{ msg_{ri}_{j + 1} }}" for j in range(depth))
            return ("deep_chain", f"{chain}\nmsg_{ri}_{depth} = Deep\n")

        case 14:  # Cross-resource reference attempt
            target = (ri + 1) % 4
            return ("cross_resource_ref", f"msg_{ri} = {{ msg_{target} }}\n")

        case 15:  # Term with attributes
            return ("term_attr", f"-term_{ri} = Value\n    .attr = Attr\n")

        case 16:  # Function call references (NUMBER, DATETIME)
            func = fdp.PickValueInList(["NUMBER", "DATETIME", "CURRENCY"])
            return ("function_ref", f"msg_{ri} = {{ {func}($var) }}\n")

        case 17:  # Multi-resource ID conflict (same ID, different resource)
            return ("id_conflict", f"shared_msg = Resource {ri} value\n")

        # --- INVALID FTL (5 patterns) ---
        case 18:  # Unclosed brace
            return ("unclosed_brace", f"msg_{ri} = {{ unclosed\n")

        case 19:  # Invalid identifier
            return ("invalid_id", "123invalid = Value\n")

        case 20:  # Malformed pattern
            return ("malformed_pattern", f"msg_{ri} = {{ }}\n")

        case 21:  # Null bytes
            return ("null_bytes", f"msg_{ri} = Value\x00\x00\x00\n")

        case 22:  # Raw bytes pass-through
            raw = fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 500))
            return ("raw_bytes", raw)

        case _:
            return ("fallback", f"msg_{ri} = Fallback\n")


def _track_slowest_validation(duration_ms: float, ftl_snippet: str) -> None:
    """Track top 10 slowest validations using min-heap."""
    snippet = ftl_snippet[:50]
    if len(_state.slowest_validations) < 10:
        heapq.heappush(_state.slowest_validations, (duration_ms, snippet))
    elif duration_ms > _state.slowest_validations[0][0]:
        heapq.heapreplace(_state.slowest_validations, (duration_ms, snippet))


def _track_seed_corpus(source: str, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    is_interesting = (
        duration_ms > 50.0
        or "circular" in pattern
        or "undefined" in pattern
        or "conflict" in pattern
        or "raw_bytes" in pattern
    )

    if is_interesting:
        source_hash = hashlib.sha256(source.encode("utf-8", errors="surrogatepass")).hexdigest()[
            :16
        ]
        if source_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[source_hash] = source
            _state.corpus_entries_added += 1


def _track_validation_result(result: object) -> None:
    """Track error and warning codes from validation result."""
    if hasattr(result, "error_count") and result.error_count > 0:  # type: ignore[attr-defined]
        for error in result.errors:  # type: ignore[attr-defined]
            error_code = error.code if hasattr(error, "code") else "UNKNOWN"
            _state.error_counts[error_code] = _state.error_counts.get(error_code, 0) + 1

    if hasattr(result, "warning_count") and result.warning_count > 0:  # type: ignore[attr-defined]
        for warning in result.warnings:  # type: ignore[attr-defined]
            warning_code = warning.code if hasattr(warning, "code") else "UNKNOWN"
            _state.warning_counts[warning_code] = _state.warning_counts.get(warning_code, 0) + 1


def test_one_input(data: bytes) -> None:  # noqa: PLR0912
    """Atheris entry point: Test multi-resource integrity validation.

    Observability:
    - Performance: Tracks timing per iteration (ms)
    - Memory: Tracks RSS via psutil (every 100 iterations)
    - Validation: Error/warning code classification
    - Strict mode: Tracks strict vs. non-strict distribution
    - Patterns: Coverage of 23 integrity-focused pattern types
    - Corpus: Interesting inputs (slow, circular, undefined, conflict, raw)
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

    # Generate locale with variation
    locale = _generate_locale(fdp)

    # Vary strict mode (50/50)
    strict_mode = fdp.ConsumeBool()
    if strict_mode:
        _state.strict_mode_count += 1
    else:
        _state.non_strict_mode_count += 1

    # Create bundle
    try:
        bundle = FluentBundle(locale, strict=strict_mode)
    except (ValueError, TypeError, DataIntegrityError):
        return

    # Generate multiple resources (1-4 resources)
    num_resources = fdp.ConsumeIntInRange(1, 4)

    for i in range(num_resources):
        pattern_name, ftl = _generate_ftl_resource(fdp, i)
        _state.pattern_coverage[pattern_name] = _state.pattern_coverage.get(pattern_name, 0) + 1

        # Fast-path rejection: empty or whitespace-only
        if not ftl.strip():
            continue

        try:
            # Add resource to bundle (may raise in strict mode)
            bundle.add_resource(ftl)

            # Validate the resource (tests integrity checks)
            result = bundle.validate_resource(ftl)
            _track_validation_result(result)

        except (ValueError, TypeError) as e:
            error_key = f"{type(e).__name__}_{str(e)[:30]}"
            _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1
        except DataIntegrityError as e:
            # Expected: strict mode integrity violations
            error_key = f"DataIntegrity_{type(e).__name__}"
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
            # Performance tracking
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            _state.performance_history.append(elapsed_ms)
            _track_slowest_validation(elapsed_ms, ftl)
            _track_seed_corpus(ftl, pattern_name, elapsed_ms)

            # Per-pattern wall time accumulation
            _state.pattern_wall_time[pattern_name] = (
                _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
            )

            # Memory tracking (every 100 iterations to reduce overhead)
            if _state.iterations % 100 == 0:
                current_memory_mb = _get_process().memory_info().rss / (1024 * 1024)
                _state.memory_history.append(current_memory_mb)


def main() -> None:
    """Run the integrity fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Multi-resource integrity validation fuzzer using Atheris/libFuzzer",
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
    print("Multi-Resource Integrity Validation Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.validation.validate_resource + FluentBundle")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Patterns:   23 (9 valid + 9 edge + 5 invalid)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
