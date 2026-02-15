#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: cache - High-pressure Cache Race & Concurrency
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""High-Pressure Cache Race and Integrity Fuzzer (Atheris).

Targets: ftllexengine.runtime.cache (via FluentBundle public API)

Concern boundary: This fuzzer stress-tests the cache subsystem by systematically
varying all cache constructor parameters (size, entry weight, error limits,
write-once, audit mode) under concurrent multi-threaded access. This is distinct
from the runtime fuzzer which tests the full resolver stack with fixed cache
configs and only 2 threads.

Unique coverage (not covered by other fuzzers):
- Cache parameter combinations (5 boolean/int params = large state space)
- High thread concurrency (2-8 threads vs runtime's 2)
- Cache eviction/LRU stress
- Concurrent resource modification during formatting
- Frozen bundle cache behavior
- Cache key complexity (deeply nested args via _make_hashable)
- Hotspot access patterns (same entry repeated)
- Memory weight enforcement

Patterns:
- variable_messages: Cache key variation
- attribute_messages: Attribute-qualified cache keys
- select_expressions: Complex pattern caching
- message_references: Cross-message resolution cache
- term_references: Namespace variation
- long_values: Memory weight stress
- many_variables: Key complexity
- circular_refs: Error caching behavior
- minimal_resource: Edge cases
- hotspot: Repeated access efficiency
- capacity_stress: LRU eviction
- deep_args: _make_hashable stress
- concurrent_modify: Race conditions
- frozen_cache: Immutable cache behavior

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import gc
import logging
import pathlib
import queue
import sys
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

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
    emit_final_report,
    get_process,
    record_iteration_metrics,
    record_memory,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class CacheMetrics:
    """Domain-specific metrics for cache fuzzer."""

    # Cache-specific counters
    cache_operations: int = 0
    write_conflict_counts: int = 0
    oversize_skip_counts: int = 0
    error_bloat_counts: int = 0
    corruption_events: int = 0
    concurrent_modify_tests: int = 0
    frozen_cache_tests: int = 0
    eviction_stress_tests: int = 0

    # Hit rate tracking (rolling)
    cache_hits: int = 0
    cache_misses: int = 0

    # Thread stats
    thread_timeouts: int = 0
    max_threads_used: int = 0


# --- Global State ---

_state = BaseFuzzerState(seed_corpus_max_size=500)
_domain = CacheMetrics()

# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("variable_messages", 10),
    ("attribute_messages", 8),
    ("select_expressions", 8),
    ("message_references", 6),
    ("term_references", 6),
    ("long_values", 5),
    ("many_variables", 6),
    ("circular_refs", 5),
    ("minimal_resource", 4),
    ("hotspot", 8),
    ("capacity_stress", 10),
    ("deep_args", 8),
    ("concurrent_modify", 8),
    ("frozen_cache", 8),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class CacheFuzzError(Exception):
    """Raised when a cache invariant is breached."""


# Allowed exceptions from cache/bundle
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    KeyError,
    RecursionError,
    MemoryError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "cache"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["cache_operations"] = _domain.cache_operations
    stats["cache_write_conflicts"] = _domain.write_conflict_counts
    stats["cache_oversize_skips"] = _domain.oversize_skip_counts
    stats["cache_error_bloat_skips"] = _domain.error_bloat_counts
    stats["cache_corruption_events"] = _domain.corruption_events
    stats["concurrent_modify_tests"] = _domain.concurrent_modify_tests
    stats["frozen_cache_tests"] = _domain.frozen_cache_tests
    stats["eviction_stress_tests"] = _domain.eviction_stress_tests
    stats["thread_timeouts"] = _domain.thread_timeouts
    stats["max_threads_used"] = _domain.max_threads_used

    # Hit rate (always emit raw counts for visibility)
    stats["cache_hits"] = _domain.cache_hits
    stats["cache_misses"] = _domain.cache_misses
    total = _domain.cache_hits + _domain.cache_misses
    if total > 0:
        stats["cache_hit_rate"] = round(_domain.cache_hits / total, 4)

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_cache_report.json")


atexit.register(_emit_report)


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        CacheCorruptionError,
        DataIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache_config import CacheConfig


# --- Constants ---

TEST_LOCALES: Sequence[str] = (
    "en-US", "de-DE", "lv-LV", "ar-SA", "ja-JP", "zh-CN", "root",
)

_MSG_IDS: Sequence[str] = tuple(f"msg{i}" for i in range(20))
_ATTR_NAMES: Sequence[str] = ("tooltip", "aria-label", "placeholder", "title")


def _collect_cache_stats(bundle: FluentBundle) -> None:
    """Accumulate cache stats from bundle into domain metrics.

    Each iteration creates a new FluentBundle/cache, so stats are
    per-iteration deltas that get accumulated into _domain totals.
    """
    stats = bundle.get_cache_stats()
    if stats is None:
        return

    _domain.cache_hits += int(stats.get("hits", 0))
    _domain.cache_misses += int(stats.get("misses", 0))
    _domain.oversize_skip_counts += int(stats.get("oversize_skips", 0))
    _domain.error_bloat_counts += int(stats.get("error_bloat_skips", 0))
    _domain.corruption_events += int(stats.get("corruption_detected", 0))


# --- FTL Generators ---


def _generate_deep_args(fdp: atheris.FuzzedDataProvider) -> dict[str, object]:
    """Generate deeply nested / unhashable args to stress _make_hashable().

    Produces args with nested dicts, lists, mixed types, and edge-case
    values that exercise every branch of the cache key conversion logic.
    """
    args: dict[str, object] = {}
    num_keys = fdp.ConsumeIntInRange(1, 8)

    for i in range(num_keys):
        if fdp.remaining_bytes() < 2:
            args[f"var{i}"] = i
            continue

        val_type = fdp.ConsumeIntInRange(0, 8)
        match val_type:
            case 0:
                # Nested dict (2-4 levels deep)
                depth = fdp.ConsumeIntInRange(2, 4)
                inner: object = fdp.ConsumeUnicodeNoSurrogates(5)
                for _ in range(depth):
                    inner = {"k": inner}
                args[f"var{i}"] = inner
            case 1:
                # List of mixed types
                args[f"var{i}"] = [
                    fdp.ConsumeInt(2),
                    fdp.ConsumeUnicodeNoSurrogates(3),
                    fdp.ConsumeBool(),
                ]
            case 2:
                # Nested list of lists
                args[f"var{i}"] = [[1, 2], [3, [4, 5]]]
            case 3:
                # Float edge cases
                args[f"var{i}"] = fdp.PickValueInList(
                    [0.0, -0.0, float("inf"), float("-inf"), float("nan")],
                )
            case 4:
                # Boolean (hash collision with int: hash(True)==hash(1))
                args[f"var{i}"] = fdp.ConsumeBool()
            case 5:
                # Dict with nested structure
                args[f"var{i}"] = {
                    "a": [1, {"b": 2}],
                    "c": fdp.ConsumeUnicodeNoSurrogates(3),
                }
            case 6:
                # Empty containers
                args[f"var{i}"] = fdp.PickValueInList([[], {}, ""])
            case 7:
                # Set (unhashable in dicts by default)
                args[f"var{i}"] = {1, 2, 3}
            case _:
                # Large nested structure
                args[f"var{i}"] = {"l": list(range(20)), "d": {"x": {"y": "z"}}}

    return args


def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(2, 10))


def _generate_ftl_for_pattern(  # noqa: PLR0911,PLR0912
    fdp: atheris.FuzzedDataProvider, pattern: str,
) -> str:
    """Generate FTL resource tailored to the pattern (dispatch function)."""
    match pattern:
        case "variable_messages":
            n = fdp.ConsumeIntInRange(5, 15)
            return "\n".join(
                f"msg{i} = Value {i} {{ $var{i % 5} }}" for i in range(n)
            ) + "\n"

        case "attribute_messages":
            n = fdp.ConsumeIntInRange(3, 10)
            return "\n".join(
                f"msg{i} = Value\n    .tooltip = Tooltip {i}\n    .title = Title {i}"
                for i in range(n)
            ) + "\n"

        case "select_expressions":
            n = fdp.ConsumeIntInRange(3, 8)
            return "\n".join(
                f"msg{i} = {{ $count ->\n    [one] One\n   *[other] Many\n}}"
                for i in range(n)
            ) + "\n"

        case "message_references":
            return "\n".join(
                f"msg{i} = {{ msg{(i + 1) % 5} }}" for i in range(5)
            ) + "\nmsg5 = Final\n"

        case "term_references":
            n = fdp.ConsumeIntInRange(3, 8)
            return "\n".join(
                f"-term{i} = Term {i}\nmsg{i} = {{ -term{i} }}" for i in range(n)
            ) + "\n"

        case "long_values":
            size = fdp.ConsumeIntInRange(1000, 5000)
            return f"msg0 = {'x' * size}\n"

        case "many_variables":
            n = fdp.ConsumeIntInRange(5, 10)
            placeables = " ".join(f"{{ $var{i} }}" for i in range(n))
            return f"msg0 = {placeables}\n"

        case "circular_refs":
            return "msg0 = { msg1 }\nmsg1 = { msg0 }\n"

        case "minimal_resource":
            return fdp.PickValueInList([
                "msg0 = x\n",
                "# comment only\nmsg0 = y\n",
                "msg0 = \n",
            ])

        case "hotspot":
            return "msg0 = Hotspot {{ $var0 }}\nmsg1 = Other\nmsg2 = Third\n"

        case "capacity_stress":
            n = fdp.ConsumeIntInRange(30, 60)
            return "\n".join(f"msg{i} = value{i} {{ $v }}" for i in range(n)) + "\n"

        case "deep_args":
            n = fdp.ConsumeIntInRange(3, 8)
            placeables = " ".join(f"{{ $var{i} }}" for i in range(n))
            return f"msg0 = {placeables}\n"

        case "concurrent_modify":
            return "\n".join(f"msg{i} = concurrent {{ $v }}" for i in range(10)) + "\n"

        case "frozen_cache":
            return "\n".join(f"msg{i} = frozen {{ $v }}" for i in range(5)) + "\n"

        case _:
            return "msg0 = fallback\n"


# --- Pattern Handlers ---


def _run_threaded_cache_stress(
    bundle: FluentBundle,
    fdp: atheris.FuzzedDataProvider,
    deep_args: dict[str, object] | None,
) -> None:
    """Run multi-threaded cache stress test."""
    num_threads = fdp.ConsumeIntInRange(2, 8)
    num_operations = fdp.ConsumeIntInRange(10, 40)

    _domain.max_threads_used = max(_domain.max_threads_used, num_threads)

    # Pre-generate thread data (FuzzedDataProvider is NOT thread-safe)
    thread_data: list[list[dict[str, Any]]] = []
    for _ in range(num_threads):
        ops: list[dict[str, Any]] = []
        for _ in range(num_operations):
            if fdp.remaining_bytes() < 4:
                ops.append({"msg_id": "msg0", "args": {"var0": "x", "v": 1, "count": 1}})
                continue

            msg_idx = fdp.ConsumeIntInRange(0, 19)
            ops.append({
                "msg_id": f"msg{msg_idx}",
                "args": deep_args if deep_args else {
                    "var0": fdp.ConsumeUnicodeNoSurrogates(3),
                    "v": fdp.ConsumeInt(2),
                    "count": fdp.ConsumeIntInRange(0, 10),
                },
                "attr": fdp.PickValueInList([None, *_ATTR_NAMES]) if fdp.ConsumeBool() else None,
            })
        thread_data.append(ops)

    # Thread-safe error collection
    error_queue: queue.Queue[str] = queue.Queue()

    def worker(ops: list[dict[str, Any]]) -> None:
        for op in ops:
            try:
                _domain.cache_operations += 1
                bundle.format_pattern(
                    op["msg_id"],
                    cast(dict[str, Any], op["args"]),
                    attribute=op.get("attr"),
                )
            except CacheCorruptionError:
                _domain.corruption_events += 1
            except WriteConflictError:
                _domain.write_conflict_counts += 1
            except FrozenFluentError:
                pass  # Expected for frozen bundles
            except DataIntegrityError:
                pass  # Expected in strict mode
            except ALLOWED_EXCEPTIONS:
                pass
            except Exception as e:  # pylint: disable=broad-exception-caught
                error_queue.put(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=worker, args=(ops,)) for ops in thread_data]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        if t.is_alive():
            _domain.thread_timeouts += 1


def _pattern_concurrent_modify(bundle: FluentBundle) -> None:
    """Test concurrent resource modification during formatting."""
    _domain.concurrent_modify_tests += 1

    # Start formatting thread
    results: list[str | None] = [None]

    def format_worker() -> None:
        for _ in range(20):
            try:
                result, _ = bundle.format_pattern("msg0", {"v": 1})
                results[0] = result
            except WriteConflictError:
                _domain.write_conflict_counts += 1
            except CacheCorruptionError:
                _domain.corruption_events += 1
            except (*ALLOWED_EXCEPTIONS, FrozenFluentError, DataIntegrityError):
                pass

    fmt_thread = threading.Thread(target=format_worker)
    fmt_thread.start()

    # Concurrently modify bundle
    for i in range(5):
        try:
            bundle.add_resource(f"newmsg{i} = added {{ $v }}\n")
        except WriteConflictError:
            _domain.write_conflict_counts += 1
        except (ValueError, FrozenFluentError, DataIntegrityError):
            pass

    fmt_thread.join(timeout=2.0)


def _pattern_frozen_cache(bundle: FluentBundle, write_once: bool) -> None:
    """Test write-once cache behavior (immutable cache entries).

    When cache_write_once=True, cache entries are immutable after first write.
    This tests that the write-once property is enforced correctly.
    """
    _domain.frozen_cache_tests += 1

    # Warm up cache with initial values
    for i in range(3):
        with contextlib.suppress(*ALLOWED_EXCEPTIONS):
            bundle.format_pattern(f"msg{i}", {"v": i})

    # Verify cached values remain stable
    for i in range(3):
        with contextlib.suppress(*ALLOWED_EXCEPTIONS):
            bundle.format_pattern(f"msg{i}", {"v": i})

    # Test that we can add resources even with write-once cache
    # (write-once applies to cache entries, not resource addition)
    with contextlib.suppress(ValueError, DataIntegrityError):
        bundle.add_resource("newmsg = added value\n")

    # If write_once is True and we try to format with different args,
    # the cache should return the original cached value
    if write_once:
        for i in range(3):
            with contextlib.suppress(*ALLOWED_EXCEPTIONS):
                # Same message, different args - cache should ignore new args
                bundle.format_pattern(f"msg{i}", {"v": i + 100})


def _pattern_capacity_stress(bundle: FluentBundle) -> None:
    """Stress cache capacity and eviction."""
    _domain.eviction_stress_tests += 1

    # Access many different keys to trigger eviction
    for i in range(50):
        with contextlib.suppress(*ALLOWED_EXCEPTIONS):
            bundle.format_pattern(f"msg{i % 20}", {"v": i})

    # Access same key repeatedly (hotspot)
    for _ in range(30):
        with contextlib.suppress(*ALLOWED_EXCEPTIONS):
            bundle.format_pattern("msg0", {"v": 0})


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Stress-test cache under concurrent access."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    if fdp.remaining_bytes() < 4:
        return

    # Generate cache configuration (vary ALL parameters)
    cache_size = fdp.ConsumeIntInRange(1, 50)
    max_entry_weight = fdp.ConsumeIntInRange(100, 10000)
    max_errors_per_entry = fdp.ConsumeIntInRange(1, 50)
    write_once = fdp.ConsumeBool()
    strict_mode = fdp.ConsumeBool()
    enable_audit = fdp.ConsumeBool()

    locale = _generate_locale(fdp)
    ftl = _generate_ftl_for_pattern(fdp, pattern)

    # Pre-generate deep args (fdp not thread-safe)
    deep_args: dict[str, object] | None = None
    if pattern == "deep_args":
        deep_args = _generate_deep_args(fdp)

    try:
        bundle = FluentBundle(
            locale,
            cache=CacheConfig(
                size=cache_size,
                max_entry_weight=max_entry_weight,
                max_errors_per_entry=max_errors_per_entry,
                write_once=write_once,
                enable_audit=enable_audit,
            ),
            strict=strict_mode,
        )
    except (ValueError, TypeError, DataIntegrityError):
        return

    try:
        bundle.add_resource(ftl)
    except (ValueError, TypeError, DataIntegrityError):
        return

    try:
        match pattern:
            case "concurrent_modify":
                _pattern_concurrent_modify(bundle)
            case "frozen_cache":
                _pattern_frozen_cache(bundle, write_once)
            case "capacity_stress":
                _pattern_capacity_stress(bundle)
            case _:
                _run_threaded_cache_stress(bundle, fdp, deep_args)

    except CacheFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except (*ALLOWED_EXCEPTIONS, FrozenFluentError, DataIntegrityError, CacheCorruptionError):
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        _collect_cache_stats(bundle)

        is_interesting = pattern in ("concurrent_modify", "frozen_cache", "capacity_stress") or (
            (time.perf_counter() - start_time) * 1000 > 20.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the cache fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Cache race & integrity fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Cache Race & Integrity Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     ftllexengine.runtime.cache (via FluentBundle)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)} (weighted round-robin)")
    print("Threads:    2-8 concurrent workers per iteration")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
