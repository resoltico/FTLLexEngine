"""Runtime survivability and integrity tests for cache and error-handling modules.

These tests execute potentially crashing code in isolated subprocesses to detect:
- Interpreter crashes (segfaults, aborts)
- Hard exits (sys.exit, os._exit)
- Infinite hangs (deadlocks, infinite loops)
- Memory exhaustion (OOM kills)
- Stack overflows (recursion limits)
- Data Integrity breaches (Strict mode, Cache corruption)

Python 3.13+ Excellence:
- Uses PEP 695 type aliases.
- Uses subprocess process groups (PEP-style logic) for clean isolation.
- Highly optimized execution harness (no disk I/O for test scripts).
- Dunder-bypass protocol for integrity testing.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

# --- PEP 695 Type Aliases (Python 3.13) ---
type JSONDict = dict[str, Any]


@pytest.fixture(autouse=True)
def _suppress_ftllexengine_logging() -> Generator[None]:
    """Suppress noisy logging for survivability tests (module-scoped, auto-resets)."""
    logger = logging.getLogger("ftllexengine")
    original_level = logger.level
    logger.setLevel(logging.CRITICAL)
    yield
    logger.setLevel(original_level)


# =============================================================================
# OPTIMIZED SUBPROCESS EXECUTION FRAMEWORK
# =============================================================================

@dataclass(frozen=True, slots=True)
class SubprocessResult:
    """Result of subprocess execution with survivability metrics."""

    returncode: int | None
    stdout: str
    stderr: str
    execution_time: float
    signal: int | None
    crashed: bool

    @property
    def success(self) -> bool:
        """Return True if subprocess completed normally with exit code 0."""
        return self.returncode == 0 and not self.crashed

    @property
    def timed_out(self) -> bool:
        """Return True if subprocess was killed due to timeout."""
        return self.signal == signal.SIGKILL or self.returncode == -signal.SIGKILL

    @property
    def crashed_abnormally(self) -> bool:
        """Return True if subprocess crashed (segfault, abort, etc.)."""
        return self.crashed or (self.signal is not None and self.signal != signal.SIGKILL)


def run_in_subprocess(
    func_code: str,
    func_name: str,
    args: JSONDict | None = None,
    timeout: float = 30.0,
    env: JSONDict | None = None,
) -> SubprocessResult:
    """Execute a function in an isolated subprocess via STDIN.

    Optimized to avoid disk I/O. Uses process groups for clean cleanup.
    """
    start_time = time.monotonic()

    # Pre-compute the script to minimize overhead
    args_json = json.dumps(args or {})
    full_script = f"""
import json
import sys
import traceback

# The test function definition
{func_code}

def main():
    try:
        args = json.loads({args_json!r})
        result = {func_name}(**args)
        print(json.dumps({{"success": True, "result": result}}))
    except Exception as e:
        print(json.dumps({{
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
"""

    subprocess_env = os.environ.copy()
    if env:
        subprocess_env.update({k: str(v) for k, v in env.items()})

    # Use 'process_group=0' (Python 3.11+) to create a new process group.
    try:
        proc = subprocess.run(
            [sys.executable, "-"],
            input=full_script,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=subprocess_env,
            process_group=0,
            check=False,
        )

        execution_time = time.monotonic() - start_time
        returncode = proc.returncode
        crashed = False
        signal_num = None

        if returncode < 0:
            signal_num = -returncode
            crashed = signal_num in {
                signal.SIGSEGV,
                signal.SIGABRT,
                signal.SIGBUS,
                signal.SIGFPE,
            }

        return SubprocessResult(
            returncode=returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            execution_time=execution_time,
            signal=signal_num,
            crashed=crashed,
        )

    except subprocess.TimeoutExpired as e:
        execution_time = time.monotonic() - start_time
        return SubprocessResult(
            returncode=None,
            stdout=e.stdout.decode() if e.stdout else "",
            stderr="TIMEOUT",
            execution_time=execution_time,
            signal=signal.SIGKILL,
            crashed=False,
        )


# =============================================================================
# CACHE SURVIVABILITY TESTS
# =============================================================================

class TestCacheSurvivability:
    """Runtime survivability tests for IntegrityCache under extreme conditions."""

    @pytest.mark.survivability
    @given(
        maxsize=st.integers(min_value=1, max_value=100),
        max_entry_weight=st.integers(min_value=1000, max_value=100_000),
        entry_count=st.integers(min_value=10, max_value=1000),
    )
    @settings(max_examples=50, deadline=None)
    def test_cache_extreme_memory_pressure(
        self, maxsize: int, max_entry_weight: int, entry_count: int
    ) -> None:
        """PROPERTY: Cache survives extreme memory pressure without crashing."""
        func_code = """
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError

def test_extreme_memory_pressure(maxsize, max_entry_weight, entry_count):
    cache = IntegrityCache(
        maxsize=maxsize, max_entry_weight=max_entry_weight, strict=False
    )
    for i in range(entry_count):
        msg_id = f"msg_{i}"
        formatted = "x" * min(max_entry_weight * 2, 1_000_000)
        errors = []
        if i % 10 == 0:
            for _ in range(min(10, max_entry_weight // 1000)):
                errors.append(FrozenFluentError("x" * 1000, ErrorCategory.RESOLUTION))
        try:
            cache.put(msg_id, None, None, "en", False, formatted, tuple(errors))
            entry = cache.get(msg_id, None, None, "en", False)
            if entry:
                entry.verify()
        except Exception:
            pass
    return {"entries_processed": entry_count, "cache_size": len(cache)}
"""
        result = run_in_subprocess(
            func_code,
            "test_extreme_memory_pressure",
            args={
                "maxsize": maxsize,
                "max_entry_weight": max_entry_weight,
                "entry_count": entry_count,
            },
            timeout=60.0,
        )
        pressure = "high" if entry_count > maxsize * 5 else "low"
        event(f"outcome={'success' if result.success else 'crash'}")
        event(f"boundary={pressure}_pressure")
        assert result.success, f"Cache crashed under pressure: {result.stderr}"
        output = json.loads(result.stdout.strip())
        assert output["result"]["entries_processed"] > 0

    @pytest.mark.survivability
    @given(test_depth=st.integers(min_value=95, max_value=110))
    @settings(max_examples=5, deadline=None)
    def test_cache_deep_nesting_survival(self, test_depth: int) -> None:
        """PROPERTY: Cache gracefully handles structures exceeding MAX_DEPTH."""
        func_code = """
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.constants import MAX_DEPTH

def create_deep_structure(depth):
    if depth <= 0: return "leaf"
    return [create_deep_structure(depth - 1)]

def test_deep_nesting_survival(test_depth):
    cache = IntegrityCache(maxsize=100, strict=False)
    safe_depth = min(test_depth - 10, MAX_DEPTH - 5)
    safe_args = create_deep_structure(safe_depth)
    cache.put("safe_msg", {"arg": safe_args}, None, "en", False, "safe", ())
    safe_res = cache.get("safe_msg", {"arg": safe_args}, None, "en", False) is not None

    deep_args = create_deep_structure(test_depth)
    try:
        cache.put("deep_msg", {"arg": deep_args}, None, "en", False, "deep", ())
        deep_success = cache.get("deep_msg", {"arg": deep_args}, None, "en", False) is not None
    except (TypeError, RecursionError):
        deep_success = False

    return {"safe_success": safe_res, "deep_success": deep_success}
"""
        result = run_in_subprocess(
            func_code, "test_deep_nesting_survival", args={"test_depth": test_depth}
        )
        event(f"depth={test_depth}")
        event(f"outcome={'survived' if not result.crashed_abnormally else 'crash'}")
        assert not result.crashed_abnormally

    @pytest.mark.survivability
    @given(
        thread_count=st.integers(min_value=2, max_value=10),
        operation_count=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=10, deadline=None)
    def test_cache_concurrent_access_survival(
        self, thread_count: int, operation_count: int
    ) -> None:
        """PROPERTY: Cache survives concurrent access without data corruption."""
        func_code = """
import threading
from ftllexengine.runtime.cache import IntegrityCache

def worker(cache, tid, ops):
    for i in range(ops):
        mid = f"m_{tid}_{i}"
        try:
            if i % 2: cache.put(mid, None, None, "en", False, f"r_{i}", ())
            else:
                e = cache.get(mid, None, None, "en", False)
                if e: e.verify()
        except Exception: pass

def test_concurrent(thread_count, operation_count):
    cache = IntegrityCache(maxsize=1000, strict=False)
    ts = [
        threading.Thread(target=worker, args=(cache, i, operation_count))
        for i in range(thread_count)
    ]
    for t in ts: t.start()
    for t in ts: t.join(timeout=10.0)

    cur = list(cache._cache.keys())[:50]
    corrupt = sum(1 for k in cur if not cache._cache[k].verify())
    return {"corruption_detected": corrupt}
"""
        result = run_in_subprocess(
            func_code,
            "test_concurrent",
            args={"thread_count": thread_count, "operation_count": operation_count},
            timeout=30.0,
        )
        event(f"thread_count={thread_count}")
        event(f"outcome={'success' if result.success else 'failure'}")
        assert result.success
        assert json.loads(result.stdout)["result"]["corruption_detected"] == 0


# =============================================================================
# INTEGRITY AND CORRECTNESS TESTS (v0.80.0+)
# =============================================================================

class TestRuntimeIntegrityBehavior:
    """Verifies that strict mode and cache integrity behave as designed."""

    @pytest.mark.survivability
    @given(
        strict=st.booleans(),
        resource_ftl=st.sampled_from([
            "msg = { $missing }\n",
            "cyclic = { cyclic }\n",
        ]),
    )
    @settings(max_examples=20, deadline=None)
    def test_strict_mode_formatting_integrity(self, strict: bool, resource_ftl: str) -> None:
        """PROPERTY: Strict mode raises FormattingIntegrityError vs fallback."""
        func_code = """
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.integrity import FormattingIntegrityError

def test_strict_formatting(strict, ftl):
    bundle = FluentBundle("en-US", strict=strict)
    bundle.add_resource(ftl)
    msg_id = ftl.split(" ")[0].strip()
    try:
        _, errs = bundle.format_pattern(msg_id, {})
        return {"status": "STRICT_BYPASS" if strict and errs else "OK"}
    except FormattingIntegrityError:
        return {"status": "RAISED" if strict else "UNEXPECTED_RAISE"}
"""
        result = run_in_subprocess(
            func_code, "test_strict_formatting", args={"strict": strict, "ftl": resource_ftl}
        )
        event(f"strict={strict}")
        has_cycle = "cyclic" in resource_ftl
        event(f"resource={'cyclic' if has_cycle else 'missing_var'}")
        assert result.success
        status = json.loads(result.stdout)["result"]["status"]
        if strict:
            assert status == "RAISED"
        else:
            assert status == "OK"

    @pytest.mark.survivability
    @given(strict=st.booleans())
    @settings(max_examples=10, deadline=None)
    def test_cache_corruption_strategy(self, strict: bool) -> None:
        """PROPERTY: Strict cache fails-fast on data corruption."""
        func_code = """
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.integrity import CacheCorruptionError

def test_corruption(strict):
    cache = IntegrityCache(maxsize=10, strict=strict)
    cache.put("k", None, None, "en", False, "valid", ())
    entry = cache._cache[next(iter(cache._cache))]

    # Bypass frozen slots using the base object's descriptor mechanism
    # to simulate low-level data corruption.
    object.__setattr__(entry, "formatted", "CORRUPTED")

    try:
        val = cache.get("k", None, None, "en", False)
        return {"result": "val" if val else "evicted"}
    except CacheCorruptionError:
        return {"result": "fail_fast"}
"""
        result = run_in_subprocess(func_code, "test_corruption", args={"strict": strict})
        event(f"strict={strict}")
        assert result.success
        res = json.loads(result.stdout)["result"]["result"]
        event(f"outcome={res}")
        assert res == ("fail_fast" if strict else "evicted")


# =============================================================================
# HYPOFUZZ AND QUALITY CHECKS
# =============================================================================

@pytest.mark.hypofuzz
@given(
    cache_config=st.fixed_dictionaries({
        "maxsize": st.integers(min_value=1, max_value=1000),
        "write_once": st.booleans(),
        "strict": st.booleans(),
    }),
    ops=st.lists(
        st.tuples(st.sampled_from(["put", "get"]), st.integers(0, 100)),
        min_size=5, max_size=50,
    ),
)
@settings(max_examples=50, deadline=None)
def test_cache_hypofuzz(cache_config, ops):
    """HypoFuzz target for continuous cache survivability testing."""
    func_code = """
from ftllexengine.runtime.cache import IntegrityCache, WriteConflictError, CacheCorruptionError

def test_ops(cfg, ops):
    cache = IntegrityCache(**cfg)
    for op, p in ops:
        try:
            if op == 'put': cache.put(f"m_{p}", None, None, "en", False, f"r_{p}", ())
            else:
                e = cache.get(f"m_{p}", None, None, "en", False)
                if e: e.verify()
        except (WriteConflictError, CacheCorruptionError): pass
    return "ok"
"""
    result = run_in_subprocess(func_code, "test_ops", args={"cfg": cache_config, "ops": ops})
    event(f"strict={cache_config['strict']}")
    event(f"write_once={cache_config['write_once']}")
    put_count = sum(1 for op, _ in ops if op == "put")
    event(f"op_mix={'put_heavy' if put_count > len(ops) // 2 else 'get_heavy'}")
    assert result.success
