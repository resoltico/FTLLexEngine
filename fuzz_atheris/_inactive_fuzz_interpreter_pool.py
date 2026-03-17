#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: interpreter_pool - InterpreterPool Subinterpreter Lifecycle
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""InterpreterPool Subinterpreter Lifecycle Fuzzer (Atheris).

Targets:
- ftllexengine.runtime.interpreter_pool.InterpreterPool
- Construction validation (min_size, max_size, acquire_timeout)
- acquire() / release() / close() lifecycle
- _PooledInterpreter.call() with module-level callables
- ExecutionFailed crash isolation (interpreter reused after user-code raise)
- Pool-as-context-manager (__enter__/__exit__)

Concern boundary: This fuzzer targets the pool lifecycle and crash-isolation
contract. It does NOT test concurrent multi-threaded access (covered by
test_runtime_interpreter_pool.py) or FTL formatting inside subinterpreters
(a deployment concern, not a library invariant).

Pattern categories (6 patterns):
- CONSTRUCTION (2): Valid and invalid min_size/max_size configurations
- LIFECYCLE (2): acquire/release/call cycles and context manager protocol
- CRASH_ISOLATION (1): ExecutionFailed leaves interpreter healthy
- CLOSE (1): close() semantics and acquire-after-close

Metrics:
- Pool construction attempts and validation failures
- Acquire/release cycle counts
- ExecutionFailed instances caught and reuse confirmations
- Close idempotency checks
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)

Requires Python 3.13+ (uses concurrent.interpreters, PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any

# --- Dependency Capture (for check_dependencies) ---
_psutil_mod: Any = None
_atheris_mod: Any = None
_ci_mod: Any = None

try:  # noqa: SIM105 - captures module for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - captures module for check_dependencies
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - concurrent.interpreters is a provisional module; absent from
    #                   some Python 3.13 builds (requires subinterpreter compile support)
    import concurrent.interpreters as _ci_mod  # type: ignore[no-redef]
except ImportError:
    pass

import pathlib  # noqa: E402 - after dependency capture  # pylint: disable=C0411,C0412,C0413

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

check_dependencies(
    ["psutil", "atheris", "concurrent.interpreters"],
    [_psutil_mod, _atheris_mod, _ci_mod],
)

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Type Aliases (PEP 695) ---
type FuzzStats = dict[str, int | str | float]

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.runtime.interpreter_pool import InterpreterPool

# concurrent.interpreters already captured as _ci_mod above; alias for call sites.
_ci = _ci_mod


# --- Module-level callables for subinterpreter call() ---
# Must be module-level (not lambdas) to be importable inside a subinterpreter.

def _sub_return_int() -> int:
    """Return a fixed integer — basic call verification."""
    return 42


def _sub_return_arg(x: int) -> int:
    """Return the argument unchanged — argument passing verification."""
    return x


def _sub_raise_value_error() -> None:
    """Raise ValueError inside the subinterpreter — ExecutionFailed probe."""
    msg = "execution_failed_probe"
    raise ValueError(msg)


# --- Report Directory ---
_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "interpreter_pool"


# --- Domain-Specific Metrics ---
@dataclass
class InterpreterPoolMetrics:
    """Domain-specific metrics for InterpreterPool fuzzing."""

    construction_attempts: int = 0
    construction_failures: int = 0
    acquire_release_cycles: int = 0
    call_successes: int = 0
    execution_failed_caught: int = 0
    close_calls: int = 0
    acquire_after_close_caught: int = 0
    context_manager_uses: int = 0


# --- Global State ---
_state = BaseFuzzerState(
    fuzzer_name="interpreter_pool",
    fuzzer_target="InterpreterPool, _PooledInterpreter, acquire, release, close",
)
_domain = InterpreterPoolMetrics()


# --- Pattern Weights ---
# 6 patterns across 3 categories
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # CONSTRUCTION (2 patterns) - Configuration validation
    ("construction_valid", 8),
    ("construction_invalid", 8),
    # LIFECYCLE (2 patterns) - acquire/release/call cycles
    ("lifecycle_call", 10),
    ("lifecycle_context_manager", 10),
    # CRASH_ISOLATION (1 pattern) - ExecutionFailed does not corrupt interpreter
    ("crash_isolation", 8),
    # CLOSE (1 pattern) - close() semantics
    ("close_behavior", 8),
)

_PATTERN_NAMES = tuple(name for name, _ in _PATTERN_WEIGHTS)
_PATTERN_WEIGHT_VALUES = tuple(w for _, w in _PATTERN_WEIGHTS)
_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(_PATTERN_NAMES, _PATTERN_WEIGHT_VALUES)

# Register intended weights for skew detection
for _name, _weight in _PATTERN_WEIGHTS:
    _state.pattern_intended_weights[_name] = float(_weight)


# --- Stats and Reporting ---
def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["construction_attempts"] = _domain.construction_attempts
    stats["construction_failures"] = _domain.construction_failures
    stats["acquire_release_cycles"] = _domain.acquire_release_cycles
    stats["call_successes"] = _domain.call_successes
    stats["execution_failed_caught"] = _domain.execution_failed_caught
    stats["close_calls"] = _domain.close_calls
    stats["acquire_after_close_caught"] = _domain.acquire_after_close_caught
    stats["context_manager_uses"] = _domain.context_manager_uses
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint report."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, "fuzz_interpreter_pool_report.json")


def _emit_report() -> None:
    """Emit final report on exit."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_interpreter_pool_report.json")


atexit.register(_emit_report)


# --- CONSTRUCTION patterns ---

def _check_construction_defaults(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool(): default min_size=2, max_size=8 constructs without error."""
    pool = InterpreterPool()
    assert pool.min_size == 2
    assert pool.max_size == 8
    pool.close()
    _domain.construction_attempts += 1


def _check_construction_custom(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool(min_size, max_size): custom sizes store correctly."""
    min_s = fdp.ConsumeIntInRange(1, 3)
    max_s = fdp.ConsumeIntInRange(min_s, min_s + 4)
    pool = InterpreterPool(min_size=min_s, max_size=max_s)
    assert pool.min_size == min_s
    assert pool.max_size == max_s
    pool.close()
    _domain.construction_attempts += 1


def _pattern_construction_valid(fdp: atheris.FuzzedDataProvider) -> None:
    """Valid InterpreterPool construction scenarios."""
    handlers = (
        _check_construction_defaults,
        _check_construction_custom,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


def _check_construction_zero_min(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool(min_size=0) raises ValueError."""
    _domain.construction_attempts += 1
    raised = False
    try:
        InterpreterPool(min_size=0)
    except ValueError:
        raised = True
    if not raised:
        msg = "InterpreterPool(min_size=0) did not raise ValueError"
        raise RuntimeError(msg)
    _domain.construction_failures += 1


def _check_construction_max_less_than_min(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool(min_size=N, max_size=N-1) raises ValueError."""
    min_s = fdp.ConsumeIntInRange(2, 5)
    max_s = min_s - 1
    _domain.construction_attempts += 1
    raised = False
    try:
        InterpreterPool(min_size=min_s, max_size=max_s)
    except ValueError:
        raised = True
    if not raised:
        msg = f"InterpreterPool(min_size={min_s}, max_size={max_s}) did not raise ValueError"
        raise RuntimeError(msg)
    _domain.construction_failures += 1


def _pattern_construction_invalid(fdp: atheris.FuzzedDataProvider) -> None:
    """Invalid InterpreterPool construction scenarios raise ValueError."""
    handlers = (
        _check_construction_zero_min,
        _check_construction_max_less_than_min,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


# --- LIFECYCLE patterns ---

def _check_lifecycle_basic_call(fdp: atheris.FuzzedDataProvider) -> None:
    """acquire() + call(_sub_return_int) + release via context manager."""
    pool = InterpreterPool(min_size=1, max_size=2)
    try:
        with pool.acquire() as interp:
            result = interp.call(_sub_return_int)
        assert result == 42
        _domain.acquire_release_cycles += 1
        _domain.call_successes += 1
    finally:
        pool.close()


def _check_lifecycle_call_with_arg(fdp: atheris.FuzzedDataProvider) -> None:
    """call(_sub_return_arg, value) passes argument and returns correct result."""
    value = fdp.ConsumeIntInRange(0, 1000)
    pool = InterpreterPool(min_size=1, max_size=2)
    try:
        with pool.acquire() as interp:
            result = interp.call(_sub_return_arg, value)
        assert result == value
        _domain.acquire_release_cycles += 1
        _domain.call_successes += 1
    finally:
        pool.close()


def _check_lifecycle_repeated_cycles(fdp: atheris.FuzzedDataProvider) -> None:
    """Multiple sequential acquire/release cycles work correctly."""
    count = fdp.ConsumeIntInRange(2, 5)
    pool = InterpreterPool(min_size=1, max_size=2)
    try:
        for i in range(count):
            with pool.acquire() as interp:
                result = interp.call(_sub_return_arg, i)
            assert result == i
            _domain.acquire_release_cycles += 1
            _domain.call_successes += 1
    finally:
        pool.close()


def _pattern_lifecycle_call(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool acquire/call/release lifecycle scenarios."""
    handlers = (
        _check_lifecycle_basic_call,
        _check_lifecycle_call_with_arg,
        _check_lifecycle_repeated_cycles,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


def _check_context_manager_pool(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool as context manager closes on exit."""
    with InterpreterPool(min_size=1, max_size=2) as pool:
        with pool.acquire() as interp:
            result = interp.call(_sub_return_int)
        assert result == 42
    # After the with block, acquire() must raise RuntimeError
    raised = False
    try:
        pool.acquire()
    except RuntimeError:
        raised = True
    if not raised:
        msg = "acquire() after context-manager exit did not raise RuntimeError"
        raise RuntimeError(msg)
    _domain.context_manager_uses += 1
    _domain.acquire_release_cycles += 1


def _check_context_manager_acquire(fdp: atheris.FuzzedDataProvider) -> None:
    """_PooledInterpreter context manager auto-releases on exit."""
    pool = InterpreterPool(min_size=1, max_size=1)
    try:
        with pool.acquire():
            pass  # interpreter checked out then released
        # Pool is now available again for a second acquire
        with pool.acquire() as interp:
            result = interp.call(_sub_return_int)
        assert result == 42
        _domain.acquire_release_cycles += 2
    finally:
        pool.close()
    _domain.context_manager_uses += 1


def _pattern_lifecycle_context_manager(fdp: atheris.FuzzedDataProvider) -> None:
    """Context manager protocol for pool and interpreter wrapper."""
    handlers = (
        _check_context_manager_pool,
        _check_context_manager_acquire,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


# --- CRASH_ISOLATION pattern ---

def _check_execution_failed_propagates(fdp: atheris.FuzzedDataProvider) -> None:
    """ExecutionFailed propagates from call(); interpreter remains reusable."""
    pool = InterpreterPool(min_size=1, max_size=2)
    try:
        # First: ExecutionFailed must propagate
        exec_failed_raised = False
        try:
            with pool.acquire() as interp:
                interp.call(_sub_raise_value_error)
        except _ci.ExecutionFailed:
            exec_failed_raised = True
        if not exec_failed_raised:
            msg = "ExecutionFailed was not propagated from call(_sub_raise_value_error)"
            raise RuntimeError(msg)
        _domain.execution_failed_caught += 1

        # Second: interpreter must still be reusable (pool returned it)
        with pool.acquire() as interp:
            result = interp.call(_sub_return_int)
        assert result == 42
        _domain.acquire_release_cycles += 2
        _domain.call_successes += 1
    finally:
        pool.close()


def _check_execution_failed_multiple(fdp: atheris.FuzzedDataProvider) -> None:
    """Multiple ExecutionFailed cycles do not exhaust the pool."""
    count = fdp.ConsumeIntInRange(2, 4)
    pool = InterpreterPool(min_size=1, max_size=2)
    try:
        for _ in range(count):
            try:
                with pool.acquire() as interp:
                    interp.call(_sub_raise_value_error)
            except _ci.ExecutionFailed:
                _domain.execution_failed_caught += 1
        # Pool must still be functional
        with pool.acquire() as interp:
            result = interp.call(_sub_return_int)
        assert result == 42
        _domain.acquire_release_cycles += count + 1
        _domain.call_successes += 1
    finally:
        pool.close()


def _pattern_crash_isolation(fdp: atheris.FuzzedDataProvider) -> None:
    """ExecutionFailed crash isolation: interpreter healthy after user-code raise."""
    handlers = (
        _check_execution_failed_propagates,
        _check_execution_failed_multiple,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


# --- CLOSE pattern ---

def _check_close_prevents_acquire(fdp: atheris.FuzzedDataProvider) -> None:
    """close() causes subsequent acquire() to raise RuntimeError."""
    pool = InterpreterPool(min_size=1, max_size=2)
    pool.close()
    _domain.close_calls += 1
    raised = False
    try:
        pool.acquire()
    except RuntimeError:
        raised = True
    if not raised:
        msg = "acquire() after close() did not raise RuntimeError"
        raise RuntimeError(msg)
    _domain.acquire_after_close_caught += 1


def _check_close_idempotent(fdp: atheris.FuzzedDataProvider) -> None:
    """close() is idempotent: calling it multiple times does not raise."""
    pool = InterpreterPool(min_size=1, max_size=2)
    count = fdp.ConsumeIntInRange(2, 5)
    for _ in range(count):
        pool.close()
    _domain.close_calls += count


def _check_close_after_acquire_in_progress(fdp: atheris.FuzzedDataProvider) -> None:
    """close() on a pool where no interpreters are checked out works cleanly."""
    pool = InterpreterPool(min_size=1, max_size=2)
    with pool.acquire() as interp:
        result = interp.call(_sub_return_int)
    assert result == 42
    # interpreter was released; pool can now be closed
    pool.close()
    _domain.close_calls += 1
    _domain.acquire_release_cycles += 1


def _pattern_close_behavior(fdp: atheris.FuzzedDataProvider) -> None:
    """InterpreterPool.close() semantics: prevents acquire, idempotent."""
    handlers = (
        _check_close_prevents_acquire,
        _check_close_idempotent,
        _check_close_after_acquire_in_progress,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


# --- Pattern Dispatch ---
_PATTERN_DISPATCH: dict[str, Any] = {
    # CONSTRUCTION
    "construction_valid": _pattern_construction_valid,
    "construction_invalid": _pattern_construction_invalid,
    # LIFECYCLE
    "lifecycle_call": _pattern_lifecycle_call,
    "lifecycle_context_manager": _pattern_lifecycle_context_manager,
    # CRASH_ISOLATION
    "crash_isolation": _pattern_crash_isolation,
    # CLOSE
    "close_behavior": _pattern_close_behavior,
}


# --- Allowed Exceptions ---
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    TimeoutError,
    RuntimeError,
    _ci.ExecutionFailed,
    _ci.InterpreterError,
)


# --- Fuzzer Entry Point ---
def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test InterpreterPool lifecycle and crash isolation.

    Observability:
    - Performance: Tracks timing per iteration (ms)
    - Memory: Tracks RSS via psutil (every 100 iterations)
    - Construction: Attempt and failure counts
    - Lifecycle: Acquire/release cycle and call success counts
    - CrashIsolation: ExecutionFailed instances caught and interpreter reuse
    - Close: close() call counts and acquire-after-close behavior
    - Patterns: 6 interpreter-pool-focused pattern types
    """
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    if fdp.remaining_bytes() < 2:
        return

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            pattern.startswith(("crash_isolation", "close_"))
            or (time.perf_counter() - start_time) * 1000 > 20.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the InterpreterPool fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="InterpreterPool lifecycle fuzzer using Atheris/libFuzzer",
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
        default=50,
        help="Maximum size of in-memory seed corpus (default: 50)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="InterpreterPool Subinterpreter Lifecycle Fuzzer (Atheris)",
        target="InterpreterPool, _PooledInterpreter, acquire, release, close",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
