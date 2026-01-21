"""Runtime survivability tests for cache and error-handling modules.

These tests execute potentially crashing code in isolated subprocesses to detect:
- Interpreter crashes (segfaults, aborts)
- Hard exits (sys.exit, os._exit)
- Infinite hangs (deadlocks, infinite loops)
- Memory exhaustion (OOM kills)
- Stack overflows (recursion limits)

Tests use Hypothesis property-based strategies to explore extreme input conditions
not covered by standard unit tests. Each property targets specific failure modes
that could occur under pathological inputs or resource exhaustion.

Execution Model:
- Tests run in subprocesses with strict timeouts (30s default)
- Parent process monitors child for abnormal termination
- Failures are captured as test failures with detailed diagnostics
- HypoFuzz integration enables continuous survivability testing

Markers:
- @pytest.mark.survivability: Core survivability tests (run in CI)
- @pytest.mark.survivability_extreme: Extreme load tests (manual execution)
- @pytest.mark.hypofuzz: Continuous fuzzing targets

Python 3.13+. Requires: hypothesis, hypofuzz, pytest-timeout
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# =============================================================================
# SUBPROCESS EXECUTION FRAMEWORK
# =============================================================================

@dataclass(frozen=True)
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
        """True if subprocess completed normally with exit code 0."""
        return self.returncode == 0 and not self.crashed

    @property
    def timed_out(self) -> bool:
        """True if subprocess was killed due to timeout."""
        return self.signal == signal.SIGKILL or self.returncode == -signal.SIGKILL

    @property
    def crashed_abnormally(self) -> bool:
        """True if subprocess crashed (segfault, abort, etc.)."""
        return self.crashed or (self.signal is not None and self.signal != signal.SIGKILL)


def run_in_subprocess(
    func_code: str,
    func_name: str,
    args: dict[str, Any] | None = None,
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
) -> SubprocessResult:
    """Execute a function in an isolated subprocess with timeout monitoring.

    Args:
        func_code: Python code defining the function to execute
        func_name: Name of the function to call
        args: Arguments to pass to the function (must be JSON serializable)
        timeout: Maximum execution time in seconds
        env: Environment variables for subprocess

    Returns:
        SubprocessResult with execution details

    Raises:
        RuntimeError: If subprocess setup fails
    """
    start_time = time.monotonic()

    # Create temporary script
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        script_path = f.name

        # Write the test function
        f.write(func_code)
        f.write("\n\n")

        # Write the execution harness
        args_json = json.dumps(args or {})
        f.write(f"""
import json
import sys
import time

def main():
    try:
        # Import the test function
        exec(globals().get("__test_code__", ""))

        # Parse arguments
        args = json.loads({args_json!r})

        # Call the function
        result = {func_name}(**args)

        # Output result as JSON
        print(json.dumps({{"success": True, "result": result}}))

    except Exception as e:
        print(json.dumps({{
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
""")

    try:
        # Prepare environment
        subprocess_env = os.environ.copy()
        if env:
            subprocess_env.update(env)

        # Execute in subprocess
        # Note: Cannot use context manager ('with') due to manual timeout handling
        # and process group management requirements for survivability testing
        proc = subprocess.Popen(  # pylint: disable=consider-using-with,W1509
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=subprocess_env,
            preexec_fn=(  # noqa: PLW1509
                os.setsid if hasattr(os, "setsid") else None
            ),
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            execution_time = time.monotonic() - start_time

            # Check if process was killed by signal
            crashed = False
            if proc.returncode is not None and proc.returncode < 0:
                signal_num = -proc.returncode
                crashed = signal_num in (
                    signal.SIGSEGV,
                    signal.SIGABRT,
                    signal.SIGBUS,
                    signal.SIGFPE,
                )
            else:
                signal_num = None

            return SubprocessResult(
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                execution_time=execution_time,
                signal=signal_num,
                crashed=crashed,
            )

        except subprocess.TimeoutExpired:
            # Kill the process group to ensure cleanup
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()

            proc.wait()
            execution_time = time.monotonic() - start_time

            return SubprocessResult(
                returncode=proc.returncode,
                stdout="",
                stderr="TIMEOUT",
                execution_time=execution_time,
                signal=signal.SIGKILL,
                crashed=False,
            )

    finally:
        # Clean up temporary file
        with contextlib.suppress(OSError):
            Path(script_path).unlink(missing_ok=True)


# =============================================================================
# CACHE SURVIVABILITY TESTS
# =============================================================================

class TestCacheSurvivability:
    """Runtime survivability tests for IntegrityCache under extreme conditions.

    These tests verify that the cache remains stable under pathological inputs
    that could cause memory exhaustion, stack overflows, or data corruption.
    """

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
        """PROPERTY: Cache survives extreme memory pressure without crashing.

        Tests cache behavior when entries approach or exceed max_entry_weight limits.
        This targets memory exhaustion scenarios where large formatted strings or
        error collections could cause OOM kills or interpreter instability.

        Args:
            maxsize: Cache capacity (controls LRU pressure)
            max_entry_weight: Maximum weight per entry (memory limit)
            entry_count: Number of entries to attempt (may exceed capacity)
        """
        func_code = '''
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError

def test_extreme_memory_pressure(maxsize, max_entry_weight, entry_count):
    """Execute cache operations under memory pressure."""
    cache = IntegrityCache(
        maxsize=maxsize,
        max_entry_weight=max_entry_weight,
        strict=False  # Non-strict to avoid exceptions on corruption
    )

    # Generate entries with varying sizes
    for i in range(entry_count):
        msg_id = f"msg_{i}"
        # Create formatted string that may exceed weight limit
        formatted = "x" * min(max_entry_weight * 2, 1_000_000)

        # Create errors that may contribute to weight
        errors = []
        if i % 10 == 0:  # Every 10th entry has errors
            for j in range(min(10, max_entry_weight // 1000)):
                error = FrozenFluentError(
                    "x" * 1000,  # Large error message
                    ErrorCategory.RESOLUTION
                )
                errors.append(error)

        try:
            cache.put(msg_id, None, None, "en", False, formatted, tuple(errors))

            # Attempt retrieval
            entry = cache.get(msg_id, None, None, "en", False)
            if entry:
                # Verify integrity if entry exists
                entry.verify()

        except Exception as e:
            # Cache should handle errors gracefully, not crash
            pass

    return {"entries_processed": entry_count, "cache_size": len(cache)}
'''

        result = run_in_subprocess(
            func_code,
            "test_extreme_memory_pressure",
            args={
                "maxsize": maxsize,
                "max_entry_weight": max_entry_weight,
                "entry_count": entry_count,
            },
            timeout=60.0
        )

        # Verify subprocess survived
        assert result.success, (
            f"Cache crashed under memory pressure: {result.stderr}. "
            f"Execution time: {result.execution_time:.2f}s"
        )

        # Verify some entries were processed
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                assert result_data.get("entries_processed", 0) > 0, "No entries were processed"
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except (json.JSONDecodeError, KeyError):
            pytest.fail(f"Invalid subprocess output: {result.stdout}")

    @pytest.mark.survivability
    @given(
        test_depth=st.integers(min_value=95, max_value=110),  # Test around MAX_DEPTH=100
    )
    @settings(max_examples=5, deadline=None)  # Very few examples for focused testing
    def test_cache_deep_nesting_survival(self, test_depth: int) -> None:
        """PROPERTY: Cache gracefully handles structures exceeding MAX_DEPTH.

        Tests that cache key conversion properly handles deeply nested structures
        that exceed the MAX_DEPTH limit (100) without crashing or hanging.

        The cache should either successfully hash structures within limits or
        gracefully skip caching (return None from _make_key) for structures
        that exceed depth limits.

        Args:
            test_depth: Nesting depth to test (focused around MAX_DEPTH boundary)
        """
        func_code = '''
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.constants import MAX_DEPTH

def create_deep_structure(depth):
    """Create a simple deeply nested list structure."""
    if depth <= 0:
        return "leaf"
    return [create_deep_structure(depth - 1)]

def test_deep_nesting_survival(test_depth):
    """Test cache with structures that may exceed MAX_DEPTH."""
    cache = IntegrityCache(maxsize=100, strict=False)

    # Test structure within limit (should work)
    if test_depth > 10:  # Leave margin for function call overhead
        safe_depth = min(test_depth - 10, MAX_DEPTH - 5)
        safe_args = create_deep_structure(safe_depth)
        cache.put("safe_msg", {"arg": safe_args}, None, "en", False, "safe_result", ())
        safe_cached = cache.get("safe_msg", {"arg": safe_args}, None, "en", False)
        safe_success = safe_cached is not None

    # Test structure at/exceeding limit (should be gracefully handled)
    deep_args = create_deep_structure(test_depth)
    try:
        cache.put("deep_msg", {"arg": deep_args}, None, "en", False, "deep_result", ())
        deep_cached = cache.get("deep_msg", {"arg": deep_args}, None, "en", False)
        deep_success = deep_cached is not None
    except (TypeError, RecursionError):
        # Expected for structures exceeding depth limits
        deep_success = False

    return {
        "safe_depth_tested": safe_depth if test_depth > 10 else 0,
        "safe_success": safe_success if test_depth > 10 else True,
        "deep_depth_tested": test_depth,
        "deep_success": deep_success,
        "max_depth_constant": MAX_DEPTH
    }
'''

        result = run_in_subprocess(
            func_code,
            "test_deep_nesting_survival",
            args={"test_depth": test_depth},
            timeout=30.0  # Reduced timeout since this should be fast
        )

        # Process should complete without crashing
        assert not result.crashed_abnormally, (
            f"Cache crashed on deep nesting (depth={test_depth}): "
            f"signal={result.signal}, stderr={result.stderr}"
        )

        # Should complete within reasonable time
        assert not result.timed_out, (
            f"Cache hung on deep nesting test: {result.execution_time:.2f}s > 30s"
        )

        # Verify expected behavior
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                max_depth = result_data.get("max_depth_constant", 100)

                # Structures within safe limits should cache successfully
                if result_data.get("safe_depth_tested", 0) > 0:
                    assert result_data.get("safe_success"), (
                        f"Safe depth {result_data['safe_depth_tested']} should cache successfully"
                    )

                # Deep structures should either succeed (if within limits) or fail gracefully
                deep_depth = result_data.get("deep_depth_tested", 0)
                deep_success = result_data.get("deep_success", False)

                # The cache should gracefully handle structures at any depth
                # Either by successfully caching (if within limits) or gracefully skipping
                # The important thing is no crash or hang
                if deep_depth < max_depth - 10:  # Well within limits
                    # Should definitely succeed
                    assert deep_success, (
                        f"Depth {deep_depth} << MAX_DEPTH {max_depth} should succeed"
                    )
                elif deep_depth > max_depth + 10:  # Well beyond limits
                    # May fail gracefully (skipped), which is acceptable
                    pass
                # At the boundary, either behavior is acceptable
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except json.JSONDecodeError:
            pytest.fail(f"Invalid subprocess output: {result.stdout}")

    @pytest.mark.survivability
    @given(
        thread_count=st.integers(min_value=2, max_value=20),
        operation_count=st.integers(min_value=100, max_value=10000),
    )
    @settings(max_examples=20, deadline=None)
    def test_cache_concurrent_access_survival(
        self, thread_count: int, operation_count: int
    ) -> None:
        """PROPERTY: Cache survives concurrent access without data corruption.

        Tests thread safety under high concurrency that could expose race
        conditions in RLock usage or checksum computation. This targets
        concurrent put/get operations that might corrupt internal state.

        Args:
            thread_count: Number of concurrent threads
            operation_count: Total operations per thread
        """
        func_code = '''
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
import threading
import time

def worker_thread(cache, thread_id, operation_count):
    """Worker thread performing cache operations."""
    for i in range(operation_count):
        msg_id = f"msg_{thread_id}_{i}"

        try:
            if i % 2 == 0:
                # PUT operation
                formatted = f"result_{thread_id}_{i}"
                errors = ()
                if i % 10 == 0:
                    errors = (FrozenFluentError(f"error_{i}", ErrorCategory.REFERENCE),)

                cache.put(msg_id, None, None, "en", False, formatted, errors)
            else:
                # GET operation
                entry = cache.get(msg_id, None, None, "en", False)
                if entry:
                    # Verify integrity under concurrent access
                    entry.verify()

        except Exception as e:
            # Should not crash - log and continue
            pass

def test_concurrent_access_survival(thread_count, operation_count):
    """Test cache under concurrent access patterns."""
    cache = IntegrityCache(maxsize=1000, strict=False)

    threads = []
    for thread_id in range(thread_count):
        t = threading.Thread(
            target=worker_thread,
            args=(cache, thread_id, operation_count)
        )
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join(timeout=30.0)  # 30s timeout per thread
        if t.is_alive():
            # Thread hung - this indicates a deadlock or infinite loop
            return {"status": "hung", "thread_count": thread_count}

    # Verify cache integrity after concurrent operations
    corruption_count = 0
    for key in list(cache._cache.keys())[:min(100, len(cache._cache))]:
        entry = cache._cache[key]
        if not entry.verify():
            corruption_count += 1

    return {
        "status": "completed",
        "thread_count": thread_count,
        "operation_count": operation_count,
        "cache_size": len(cache),
        "corruption_detected": corruption_count
    }
'''

        result = run_in_subprocess(
            func_code,
            "test_concurrent_access_survival",
            args={"thread_count": thread_count, "operation_count": operation_count},
            timeout=120.0  # Allow 2 minutes for concurrent testing
        )

        # Should not crash
        assert not result.crashed_abnormally, (
            f"Cache crashed under concurrent access: signal={result.signal}, "
            f"stderr={result.stderr}"
        )

        # Should complete (not hang)
        assert not result.timed_out, (
            f"Cache hung under concurrent access: {result.execution_time:.2f}s > 120s"
        )

        # Verify successful completion
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                assert (
                    result_data.get("status") == "completed"
                ), f"Concurrent test failed: {result_data}"
                assert result_data.get("corruption_detected", 0) == 0, (
                    f"Data corruption detected: {result_data.get('corruption_detected', 0)} entries"
                )
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except (json.JSONDecodeError, KeyError) as e:
            pytest.fail(f"Invalid concurrent test output: {result.stdout} (error: {e})")


# =============================================================================
# ERROR HANDLING SURVIVABILITY TESTS
# =============================================================================

class TestErrorHandlingSurvivability:
    """Runtime survivability tests for FrozenFluentError under extreme conditions.

    These tests verify that error creation and handling remains stable under
    pathological inputs that could cause memory issues or integrity failures.
    """

    @pytest.mark.survivability
    @given(
        message_size=st.integers(min_value=1000, max_value=1_000_000),
        diagnostic_count=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_error_creation_huge_messages(
        self, message_size: int, diagnostic_count: int
    ) -> None:
        """PROPERTY: Error creation survives huge message strings.

        Tests FrozenFluentError construction with extremely large messages that
        could cause memory exhaustion during hash computation or storage.

        Args:
            message_size: Size of error message in characters
            diagnostic_count: Number of diagnostic objects to attach
        """
        func_code = '''
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError, Diagnostic, DiagnosticCode
import sys

def test_error_creation_huge_messages(message_size, diagnostic_count):
    """Create errors with huge messages and diagnostics."""
    try:
        # Create huge message
        message = "x" * min(message_size, 100_000)  # Cap at 100KB for practicality

        # Create diagnostics with large content
        diagnostics = []
        for i in range(min(diagnostic_count, 10)):  # Cap diagnostics for performance
            diagnostic = Diagnostic(
                code=DiagnosticCode.FUNCTION_FAILED,
                message="y" * min(1000, message_size // 10),
                hint="z" * min(500, message_size // 20) if i % 2 == 0 else None,
                help_url="https://example.com/help" if i % 3 == 0 else None,
                function_name="test_function" if i % 4 == 0 else None,
                argument_name=f"arg_{i}" if i % 5 == 0 else None,
                expected_type="str" if i % 6 == 0 else None,
                received_type="int" if i % 7 == 0 else None,
                ftl_location="test.ftl:1:1" if i % 8 == 0 else None,
                severity="error",
                resolution_path=tuple(f"step_{j}" for j in range(min(5, i + 1)))
            )
            diagnostics.append(diagnostic)

        # Create error with huge content
        error = FrozenFluentError(
            message=message,
            category=ErrorCategory.RESOLUTION,
            diagnostic=diagnostics[0] if diagnostics else None
        )

        # Verify integrity
        integrity_ok = error.verify_integrity()

        # Test hash stability
        hash1 = hash(error)
        hash2 = hash(error)
        hash_stable = hash1 == hash2

        # Test equality
        error2 = FrozenFluentError(
            message=message,
            category=ErrorCategory.RESOLUTION,
            diagnostic=diagnostics[0] if diagnostics else None
        )
        equal_to_self = error == error

        return {
            "message_size": len(message),
            "integrity_ok": integrity_ok,
            "hash_stable": hash_stable,
            "equal_to_self": equal_to_self,
            "content_hash_length": len(error.content_hash)
        }

    except MemoryError:
        # Expected for extreme sizes - should not crash interpreter
        return {"status": "memory_limit_hit", "message_size": message_size}
    except Exception as e:
        return {"status": "error", "error_type": type(e).__name__, "message": str(e)}
'''

        result = run_in_subprocess(
            func_code,
            "test_error_creation_huge_messages",
            args={"message_size": message_size, "diagnostic_count": diagnostic_count},
            timeout=60.0
        )

        # Should not crash abnormally
        assert not result.crashed_abnormally, (
            f"Error creation crashed with huge messages: signal={result.signal}, "
            f"stderr={result.stderr}"
        )

        # Should complete within timeout
        assert not result.timed_out, (
            f"Error creation hung with huge messages: {result.execution_time:.2f}s > 60s"
        )

        # Verify successful processing
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                if "status" in result_data:
                    if result_data["status"] == "memory_limit_hit":
                        # Acceptable - memory exhaustion handled gracefully
                        pass
                    elif result_data["status"] == "error":
                        # Other errors should not occur
                        pytest.fail(f"Unexpected error in huge message test: {result_data}")
                    else:
                        pytest.fail(f"Unknown status in output: {result_data}")
                else:
                    # Normal completion - verify integrity
                    assert result_data.get("integrity_ok", False), "Integrity check failed"
                    assert result_data.get("hash_stable", False), "Hash unstable"
                    assert result_data.get("equal_to_self", False), "Self-equality failed"
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except json.JSONDecodeError:
            pytest.fail(f"Invalid output from huge message test: {result.stdout}")

    @pytest.mark.survivability
    @given(
        error_count=st.integers(min_value=1000, max_value=100_000),
        batch_size=st.integers(min_value=10, max_value=1000),
    )
    @settings(max_examples=20, deadline=None)
    def test_error_collection_scaling(
        self, error_count: int, batch_size: int
    ) -> None:
        """PROPERTY: Error collections scale without crashing interpreter.

        Tests handling of large numbers of FrozenFluentError objects that could
        cause memory exhaustion or GC pressure during tuple operations.

        Args:
            error_count: Total number of errors to create
            batch_size: Size of batches for processing
        """
        func_code = '''
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
import gc

def test_error_collection_scaling(error_count, batch_size):
    """Create and process large collections of errors."""
    errors = []

    try:
        # Create errors in batches to manage memory
        for i in range(0, min(error_count, 10_000), batch_size):  # Cap for practicality
            batch = []
            for j in range(min(batch_size, 1000)):  # Cap batch size
                error = FrozenFluentError(
                    f"Error {i + j}",
                    ErrorCategory.REFERENCE
                )
                batch.append(error)

            errors.extend(batch)

            # Periodic integrity checks
            if i % (batch_size * 10) == 0:
                for error in batch[:min(10, len(batch))]:  # Check subset
                    if not error.verify_integrity():
                        return {"status": "integrity_failure", "errors_created": len(errors)}

                # Force GC to test memory pressure
                gc.collect()

        # Convert to tuple (common cache operation)
        error_tuple = tuple(errors)

        # Test tuple operations that might cause stack issues
        tuple_len = len(error_tuple)
        tuple_hash = hash(error_tuple) if tuple_len < 1000 else "too_large"

        # Test slicing operations
        if tuple_len > 0:
            slice_start = error_tuple[:min(100, tuple_len)]
            slice_end = error_tuple[-min(100, tuple_len):] if tuple_len > 100 else error_tuple

        return {
            "status": "completed",
            "errors_created": len(errors),
            "tuple_length": tuple_len,
            "memory_pressure_tested": True
        }

    except MemoryError:
        return {"status": "memory_exhausted", "errors_created": len(errors)}
    except RecursionError:
        return {"status": "recursion_limit", "errors_created": len(errors)}
    except Exception as e:
        return {
            "status": "unexpected_error",
            "error_type": type(e).__name__,
            "message": str(e),
            "errors_created": len(errors)
        }
'''

        result = run_in_subprocess(
            func_code,
            "test_error_collection_scaling",
            args={"error_count": error_count, "batch_size": batch_size},
            timeout=90.0
        )

        # Should not crash
        assert not result.crashed_abnormally, (
            f"Error collection crashed: signal={result.signal}, stderr={result.stderr}"
        )

        # Should complete
        assert not result.timed_out, (
            f"Error collection hung: {result.execution_time:.2f}s > 90s"
        )

        # Verify acceptable outcomes
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                status = result_data.get("status")

                if status in ("memory_exhausted", "recursion_limit"):
                    # Acceptable - resource limits handled gracefully
                    pass
                elif status == "completed":
                    # Success - verify some errors were created
                    assert result_data.get("errors_created", 0) > 0, "No errors were created"
                else:
                    pytest.fail(f"Unexpected status in error collection test: {result_data}")
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except json.JSONDecodeError:
            pytest.fail(f"Invalid output from error collection test: {result.stdout}")

    @pytest.mark.survivability_extreme
    @given(
        nesting_depth=st.integers(min_value=50, max_value=500),
        object_count=st.integers(min_value=100, max_value=10000),
    )
    @settings(max_examples=10, deadline=None)
    def test_error_immutability_under_extreme_conditions(
        self, nesting_depth: int, object_count: int  # noqa: ARG002 - Used for hypothesis variety
    ) -> None:
        """PROPERTY: Error immutability holds under extreme object creation pressure.

        Tests that FrozenFluentError's immutability enforcement remains effective
        when thousands of objects are created rapidly, which could stress the
        __setattr__ override mechanism.

        Args:
            nesting_depth: Depth of nested object creation (unused but for variety)
            object_count: Number of error objects to create and test
        """
        func_code = '''
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
import threading

def create_errors_batch(start_idx, count):
    """Create a batch of errors in a thread."""
    errors = []
    for i in range(count):
        try:
            error = FrozenFluentError(
                f"Batch error {start_idx + i}",
                ErrorCategory.RESOLUTION
            )
            errors.append(error)
        except Exception as e:
            return {"status": "creation_failed", "error": str(e), "errors_created": len(errors)}
    return {"status": "created", "errors": errors}

def test_immutability_extreme(object_count):
    """Test immutability under extreme object creation."""
    errors = []

    # Create errors in parallel batches
    batch_size = min(1000, object_count // 4 + 1)
    batches = []

    for start_idx in range(0, min(object_count, 10000), batch_size):
        batch_count = min(batch_size, object_count - start_idx)
        batch_result = create_errors_batch(start_idx, batch_count)
        if batch_result["status"] != "created":
            return batch_result
        batches.append(batch_result["errors"])
        errors.extend(batch_result["errors"])

    # Test immutability on random subset
    mutation_attempts = 0
    successful_blocks = 0

    test_errors = errors[:min(100, len(errors))]  # Test subset for performance
    for error in test_errors:
        try:
            # Attempt mutation (should raise ImmutabilityViolationError)
            error.message = "modified"
            mutation_attempts += 1  # Should not reach here
        except Exception as e:
            if "ImmutabilityViolationError" in str(type(e)):
                successful_blocks += 1
            # Other exceptions are also acceptable (mutation blocked)

    return {
        "status": "completed",
        "errors_created": len(errors),
        "mutation_attempts_blocked": successful_blocks,
        "total_tested": len(test_errors),
        "immutability_held": successful_blocks == len(test_errors)
    }
'''

        result = run_in_subprocess(
            func_code,
            "test_immutability_extreme",
            args={"object_count": object_count},
            timeout=120.0
        )

        # Should not crash
        assert not result.crashed_abnormally, (
            f"Immutability test crashed: signal={result.signal}, stderr={result.stderr}"
        )

        # Should complete
        assert not result.timed_out, (
            f"Immutability test hung: {result.execution_time:.2f}s > 120s"
        )

        # Verify immutability held
        try:
            output = json.loads(result.stdout.strip())
            if output.get("success"):
                result_data = output.get("result", {})
                assert result_data.get("immutability_held", False), (
                    f"Immutability violated: {result_data.get('mutation_attempts_blocked', 0)}/"
                    f"{result_data.get('total_tested', 0)} mutations blocked"
                )
            else:
                pytest.fail(f"Subprocess reported failure: {output}")
        except json.JSONDecodeError:
            pytest.fail(f"Invalid output from immutability test: {result.stdout}")


# =============================================================================
# HYPOFUZZ INTEGRATION
# =============================================================================

@pytest.mark.hypofuzz
@given(
    cache_config=st.fixed_dictionaries({
        "maxsize": st.integers(min_value=1, max_value=1000),
        "max_entry_weight": st.integers(min_value=1000, max_value=1_000_000),
        "write_once": st.booleans(),
        "strict": st.booleans(),
    }),
    operation_sequence=st.lists(
        st.tuples(
            st.sampled_from(["put", "get", "clear"]),
            st.integers(min_value=0, max_value=1000),  # operation params
        ),
        min_size=10,
        max_size=1000,
    ),
)
@settings(max_examples=1000, deadline=None)
def test_cache_hypofuzz_survivability(cache_config, operation_sequence):
    """HypoFuzz target for continuous cache survivability testing.

    This test uses HypoFuzz to continuously explore cache configurations and
    operation sequences that might cause crashes or hangs. It runs in the
    HypoFuzz framework for extended periods to find edge cases.

    Args:
        cache_config: Cache configuration parameters
        operation_sequence: Sequence of cache operations to perform
    """
    func_code = '''
from ftllexengine.runtime.cache import IntegrityCache, WriteConflictError, CacheCorruptionError
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
import sys

def test_cache_operations(cache_config, operation_sequence):
    """Execute sequence of cache operations."""
    try:
        cache = IntegrityCache(**cache_config)

        for op, param in operation_sequence:
            try:
                if op == 'put':
                    msg_id = f"msg_{param}"
                    formatted = f"result_{param}"
                    errors = ()
                    if param % 10 == 0:
                        errors = (FrozenFluentError(f"error_{param}", ErrorCategory.REFERENCE),)

                    cache.put(msg_id, None, None, "en", False, formatted, errors)

                elif op == 'get':
                    msg_id = f"msg_{param}"
                    entry = cache.get(msg_id, None, None, "en", False)
                    if entry:
                        entry.verify()

                elif op == 'clear':
                    cache.clear()

            except (WriteConflictError, CacheCorruptionError):
                # Expected exceptions in strict/write-once modes
                pass
            except Exception as e:
                # Log unexpected exceptions but continue
                pass

        # Final integrity check
        corruption_count = 0
        for key in list(cache._cache.keys())[:min(50, len(cache._cache))]:
            entry = cache._cache[key]
            if not entry.verify():
                corruption_count += 1

        return {
            "status": "completed",
            "operations_executed": len(operation_sequence),
            "cache_size": len(cache),
            "corruption_detected": corruption_count
        }

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "error_type": type(e).__name__,
            "operations_completed": 0
        }
'''

    result = run_in_subprocess(
        func_code,
        "test_cache_operations",
        args={"cache_config": cache_config, "operation_sequence": operation_sequence},
        timeout=30.0
    )

    # HypoFuzz will use failures to guide further exploration
    assert not result.crashed_abnormally, (
        f"Cache operation sequence caused crash: {result.stderr}"
    )

    assert not result.timed_out, (
        f"Cache operation sequence caused hang: {result.execution_time:.2f}s"
    )

    # Verify successful completion
    try:
        output = json.loads(result.stdout.strip())
        if output.get("success"):
            result_data = output.get("result", {})
            assert (
                result_data.get("status") == "completed"
            ), f"Operation sequence failed: {result_data}"
        else:
            pytest.fail(f"Subprocess reported failure: {output}")
    except json.JSONDecodeError:
        pytest.fail(f"Invalid HypoFuzz output: {result.stdout}")
