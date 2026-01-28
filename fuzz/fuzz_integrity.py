#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: integrity - Multi-Resource Semantic Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Multi-Resource Integrity Fuzzer (Atheris).

Targets: ftllexengine.validation.validate_resource + FluentBundle cross-resource checks
Tests: circular references, undefined references, term visibility, duplicate IDs,
       cross-resource dependencies, strict mode enforcement.
"""

from __future__ import annotations

import atexit
import heapq
import json
import logging
import os
import statistics
import sys
import time
from collections import deque

import psutil

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str]

_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

# Performance profiling globals
performance_history: deque[float] = deque(maxlen=1000)
memory_history: deque[float] = deque(maxlen=100)
# Heapq min-heaps: (value, data) tuples for efficient top-N tracking
slowest_validations: list[tuple[float, str]] = []
fastest_validations: list[tuple[float, str]] = []
error_counts: dict[str, int] = {}
warning_counts: dict[str, int] = {}
pattern_coverage: set[str] = set()

# Process handle (created once, reused for all iterations)
_process: psutil.Process = psutil.Process(os.getpid())

# Seed corpus management
seed_corpus: list[bytes] = []
interesting_inputs: list[tuple[bytes, str]] = []

def _add_to_seed_corpus(data: bytes, reason: str) -> None:
    """Add input to seed corpus if it's interesting."""
    if len(seed_corpus) < 1000:  # Limit corpus size
        seed_corpus.append(data)
        interesting_inputs.append((data, reason))

def _is_interesting_input(
    ftl_snippet: str,
    duration: float,
    exception: Exception | None = None,
) -> str | None:
    """Determine if input is interesting for corpus expansion."""
    reasons = []

    # Exception-triggering inputs
    if exception:
        reasons.append(f"exception_{type(exception).__name__}")

    # Slow validations
    if duration > 0.05:  # >50ms
        reasons.append("slow_validation")

    # Unique pattern (first 30 chars)
    pattern = ftl_snippet[:30]
    if pattern not in pattern_coverage:
        pattern_coverage.add(pattern)
        reasons.append("new_pattern")

    # Edge cases
    if any(keyword in ftl_snippet for keyword in ["{", "}", "->", ".attr", "-term"]):
        reasons.append("complex_structure")

    if len(ftl_snippet) > 500:
        reasons.append("long_ftl")

    return reasons[0] if reasons else None

def _get_performance_summary() -> dict[str, float]:
    """Get comprehensive performance statistics."""
    if not performance_history:
        return {}

    return {
        "mean": statistics.mean(performance_history),
        "median": statistics.median(performance_history),
        "stdev": (
            statistics.stdev(performance_history) if len(performance_history) > 1 else 0
        ),
        "min": min(performance_history),
        "max": max(performance_history),
        "p95": (
            statistics.quantiles(performance_history, n=20)[18]
            if len(performance_history) >= 20
            else max(performance_history)
        ),
        "p99": (
            statistics.quantiles(performance_history, n=100)[98]
            if len(performance_history) >= 100
            else max(performance_history)
        ),
        "memory_mean": statistics.mean(memory_history) if memory_history else 0,
        "memory_max": max(memory_history) if memory_history else 0,
    }

def _emit_final_report() -> None:
    """Emit comprehensive fuzzing statistics."""
    perf_summary = _get_performance_summary()

    # Extract top 5 slowest/fastest (heapq stores as (duration, input) tuples)
    slowest_top5 = [(inp, dur) for dur, inp in heapq.nlargest(5, slowest_validations)]
    fastest_top5 = [(inp, -dur) for dur, inp in heapq.nsmallest(5, fastest_validations)]

    stats = {
        "status": _fuzz_stats["status"],
        "iterations": _fuzz_stats["iterations"],
        "findings": _fuzz_stats["findings"],
        "slow_validations": _fuzz_stats.get("slow_validations", 0),
        "coverage_estimate": (
            "high" if int(_fuzz_stats["iterations"]) > 1000000 else "medium"
        ),
        "performance": perf_summary,
        "pattern_coverage": len(pattern_coverage),
        "error_types": error_counts,
        "warning_types": warning_counts,
        "slowest_validations": slowest_top5,
        "fastest_validations": fastest_top5,
        "seed_corpus_size": len(seed_corpus),
        "interesting_inputs": len(interesting_inputs),
        "memory_leaks_detected": _fuzz_stats.get("memory_leaks", 0),
    }
    report = json.dumps(stats, default=str)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)

def _update_performance_stats(duration: float, ftl_snippet: str, memory_mb: float) -> None:
    """Update performance statistics with advanced analysis."""
    performance_history.append(duration)
    memory_history.append(memory_mb)

    # Track slowest validations using min-heap (maintain top 10 largest)
    if len(slowest_validations) < 10:
        heapq.heappush(slowest_validations, (duration, ftl_snippet[:50]))
    elif duration > slowest_validations[0][0]:
        heapq.heapreplace(slowest_validations, (duration, ftl_snippet[:50]))

    # Track fastest validations using max-heap (maintain top 10 smallest)
    neg_duration = -duration
    if len(fastest_validations) < 10:
        heapq.heappush(fastest_validations, (neg_duration, ftl_snippet[:50]))
    elif neg_duration > fastest_validations[0][0]:
        heapq.heapreplace(fastest_validations, (neg_duration, ftl_snippet[:50]))

    # Track patterns
    pattern_coverage.add(ftl_snippet[:30])

atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    sys.exit(1)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.integrity import DataIntegrityError
    from ftllexengine.runtime.bundle import FluentBundle

TEST_LOCALES = ["en-US", "de-DE", "lv-LV", "ar-SA", "ja-JP", "root"]

def generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale for bundle creation.

    Weighted 90% valid / 10% invalid to ensure validation logic is exercised.
    """
    # 90% valid locales
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(TEST_LOCALES)
    # 10% malformed locales
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))

def generate_ftl_resource(fdp: atheris.FuzzedDataProvider, resource_idx: int) -> str:
    """Generate FTL resource content with weighted strategies.

    Args:
        fdp: FuzzedDataProvider for randomization
        resource_idx: Resource index for creating cross-resource references

    Returns:
        FTL source code string
    """
    # Weighted strategy selection: 70% valid, 20% edge cases, 10% invalid
    strategy_type = fdp.ConsumeIntInRange(0, 9)

    # 70% VALID FTL (strategies 0-6): Exercise validation logic
    if strategy_type <= 6:
        valid_strategies = [
            # Simple message
            lambda: f"msg_{resource_idx} = Simple value\n",
            # Message with attribute
            lambda: f"msg_{resource_idx} = Value\n    .attr = Attribute\n",
            # Message referencing another message (same resource)
            lambda: (
                f"msg_{resource_idx}_a = First\n"
                f"msg_{resource_idx}_b = {{ msg_{resource_idx}_a }}\n"
            ),
            # Term definition
            lambda: f"-term_{resource_idx} = Term value\n",
            # Message using term
            lambda: f"-term_{resource_idx} = T\nmsg_{resource_idx} = {{ -term_{resource_idx} }}\n",
            # Select expression
            lambda: (
                f"msg_{resource_idx} = {{ $count ->\n"
                f"    [one] One item\n"
                f"   *[other] Many items\n"
                f"}}\n"
            ),
            # Multiple entries
            lambda: (
                f"msg_{resource_idx}_1 = First\n"
                f"msg_{resource_idx}_2 = Second\n"
                f"-term_{resource_idx} = Term\n"
            ),
            # Message with comment
            lambda: f"# Comment\nmsg_{resource_idx} = Value\n",
            # Complex pattern
            lambda: f"msg_{resource_idx} = Start {{ $var }} end\n",
        ]
        return fdp.PickValueInList(valid_strategies)()

    # 20% EDGE CASES (strategies 7-8): Test boundary conditions
    if strategy_type <= 8:
        edge_strategies = [
            # Circular reference (within resource)
            lambda: (
                f"msg_{resource_idx}_a = {{ msg_{resource_idx}_b }}\n"
                f"msg_{resource_idx}_b = {{ msg_{resource_idx}_a }}\n"
            ),
            # Undefined reference
            lambda: f"msg_{resource_idx} = {{ undefined_msg }}\n",
            # Private term used in message (valid)
            lambda: "-term = Private\nmsg = { -term }\n",
            # Duplicate ID
            lambda: f"msg_{resource_idx} = First\nmsg_{resource_idx} = Duplicate\n",
            # Message without value (only attributes)
            lambda: f"msg_{resource_idx} =\n    .attr = Attribute only\n",
            # Very deep nesting
            lambda: (
                "msg_1 = { msg_2 }\n"
                "msg_2 = { msg_3 }\n"
                "msg_3 = { msg_4 }\n"
                "msg_4 = { msg_5 }\n"
                "msg_5 = Deep\n"
            ),
            # Term with attributes (edge case)
            lambda: f"-term_{resource_idx} = Value\n    .attr = Attr\n",
            # Empty resource
            lambda: "\n\n",
            # Cross-resource reference attempt
            lambda: f"msg_{resource_idx} = {{ msg_{(resource_idx + 1) % 4} }}\n",
        ]
        return fdp.PickValueInList(edge_strategies)()

    # 10% INVALID FTL (strategy 9): Test error handling
    invalid_strategies = [
        # Syntax error: unclosed brace
        lambda: f"msg_{resource_idx} = {{ unclosed\n",
        # Syntax error: invalid identifier
        lambda: "123invalid = Value\n",
        # Malformed pattern
        lambda: f"msg_{resource_idx} = {{ }}\n",
        # Random Unicode (should parse as Junk)
        lambda: fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(10, 50)) + "\n",
        # Null bytes (security)
        lambda: f"msg_{resource_idx} = Value\x00\x00\x00\n",
    ]
    return fdp.PickValueInList(invalid_strategies)()

def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Test multi-resource integrity validation."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    # Generate locale with variation
    locale = generate_locale(fdp)

    # Vary strict mode (50/50)
    strict_mode = fdp.ConsumeBool()

    # Create bundle
    try:
        bundle = FluentBundle(locale, strict=strict_mode)
    except (ValueError, TypeError):
        # Invalid locale, skip this iteration
        return

    # Generate multiple resources (1-4 resources)
    num_resources = fdp.ConsumeIntInRange(1, 4)
    resources_ftl: list[str] = []

    for i in range(num_resources):
        ftl = generate_ftl_resource(fdp, i)
        resources_ftl.append(ftl)

        # Fast-path rejection: empty or whitespace-only
        if not ftl.strip():
            continue

        # Track performance and memory
        start_time = time.perf_counter()
        start_memory = _process.memory_info().rss / 1024 / 1024  # MB

        try:
            # Add resource to bundle (may raise in strict mode)
            bundle.add_resource(ftl)

            # Validate the resource (tests integrity checks)
            result = bundle.validate_resource(ftl)

            # Track validation results
            if result.error_count > 0:
                for error in result.errors:
                    error_code = error.code if hasattr(error, "code") else "UNKNOWN"
                    error_counts[error_code] = error_counts.get(error_code, 0) + 1

            if result.warning_count > 0:
                for warning in result.warnings:
                    warning_code = (
                        warning.code if hasattr(warning, "code") else "UNKNOWN"
                    )
                    warning_counts[warning_code] = warning_counts.get(warning_code, 0) + 1

        except ValueError as e:
            # Expected: invalid input, duplicate IDs, etc.
            error_type = f"ValueError_{str(e)[:30]}"
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        except TypeError as e:
            # Expected: type errors in strict mode
            error_type = f"TypeError_{str(e)[:30]}"
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        except DataIntegrityError as e:
            # Expected: strict mode integrity violations (syntax errors, formatting failures)
            error_type = f"DataIntegrity_{type(e).__name__}"
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
            # Do NOT re-raise - this is expected behavior in strict mode
        except Exception as e:
            # Unexpected exceptions are findings
            error_type = type(e).__name__
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

            # Calculate duration for interesting input detection
            duration = time.perf_counter() - start_time

            # Add to seed corpus
            interesting_reason = _is_interesting_input(ftl, duration, e)
            if interesting_reason:
                _add_to_seed_corpus(data, interesting_reason)

            _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
            raise

        # Monitor for performance regressions (normal path)
        duration = time.perf_counter() - start_time
        end_memory = _process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = end_memory - start_memory

        _update_performance_stats(duration, ftl, end_memory)

        # Add interesting inputs to seed corpus
        interesting_reason = _is_interesting_input(ftl, duration)
        if interesting_reason:
            _add_to_seed_corpus(data, interesting_reason)

        if duration > 0.05:  # Log slow validations (>50ms)
            slow_count = int(_fuzz_stats.get("slow_validations", 0)) + 1
            _fuzz_stats["slow_validations"] = slow_count

        # Detect memory leaks (rough heuristic)
        if memory_delta > 50:  # >50MB increase
            leak_count = int(_fuzz_stats.get("memory_leaks", 0)) + 1
            _fuzz_stats["memory_leaks"] = leak_count

if __name__ == "__main__":
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
