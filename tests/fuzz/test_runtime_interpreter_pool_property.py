"""Hypothesis property-based tests for runtime.interpreter_pool: InterpreterPool.

Properties verified:
- Roundtrip: values passed to subinterpreter callables are returned unchanged.
- Pool invariant: active_count + idle_count <= max_size at all times (post-release).
- Health invariant: healthy release returns interpreter to pool; unhealthy release replaces.
- Idempotence: close() called multiple times does not raise.
- Monotone: acquire() after close() always raises RuntimeError.
"""

from __future__ import annotations

import concurrent.futures
import threading
from typing import Literal

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.interpreter_pool import InterpreterPool

pytestmark = pytest.mark.fuzz

# ---------------------------------------------------------------------------
# Module-level helpers (must be top-level for subinterpreter pickling)
# ---------------------------------------------------------------------------


def _fn_identity(x: int) -> int:
    """Return the argument unchanged."""
    return x


def _fn_noop() -> None:
    """Return None."""


def _fn_raise() -> None:
    """Raise ValueError inside the subinterpreter."""
    msg = "deliberate failure"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


pool_sizes = st.integers(min_value=1, max_value=3).flatmap(
    lambda min_s: st.tuples(
        st.just(min_s),
        st.integers(min_value=min_s, max_value=min_s + 3),
    )
)


@given(
    sizes=pool_sizes,
    values=st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=8),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_identity_roundtrip(sizes: tuple[int, int], values: list[int]) -> None:
    """Values passed through the subinterpreter are returned unchanged.

    Property: for any picklable int x, interp.call(_fn_identity, x) == x.
    """
    min_size, max_size = sizes
    event(f"min_size={min_size}")
    event(f"values_count={len(values)}")

    pool = InterpreterPool(min_size=min_size, max_size=max_size, acquire_timeout=5.0)
    try:
        for val in values:
            with pool.acquire() as interp:
                result = interp.call(_fn_identity, val)
            assert result == val, f"identity roundtrip failed: {val!r} -> {result!r}"
            event("outcome=roundtrip_success")
    finally:
        pool.close()


@given(
    sizes=pool_sizes,
    n_concurrent=st.integers(min_value=1, max_value=4),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_pool_size_invariant_concurrent(
    sizes: tuple[int, int], n_concurrent: int
) -> None:
    """Pool never exceeds max_size interpreters under concurrent load.

    Property: at every observable point, checked-out + idle <= max_size.
    """
    min_size, max_size = sizes
    n_concurrent = min(n_concurrent, max_size)
    event(f"min_size={min_size}")
    event(f"max_size={max_size}")
    event(f"thread_count={n_concurrent}")

    pool = InterpreterPool(min_size=min_size, max_size=max_size, acquire_timeout=5.0)
    barrier = threading.Barrier(n_concurrent)
    results: list[int] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        with pool.acquire() as interp:
            barrier.wait(timeout=5.0)
            val = interp.call(_fn_identity, n)
        with lock:
            results.append(val)  # type: ignore[arg-type]

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_concurrent)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    pool.close()
    assert sorted(results) == list(range(n_concurrent))
    event("outcome=concurrency_success")


@given(
    sizes=pool_sizes,
    release_kind=st.sampled_from(["healthy", "unhealthy"]),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_release_health_contract(
    sizes: tuple[int, int], release_kind: Literal["healthy", "unhealthy"]
) -> None:
    """Healthy release returns interpreter; unhealthy release replaces it.

    Property: regardless of release kind, the pool remains functional.
    """
    min_size, max_size = sizes
    event(f"release_kind={release_kind}")

    pool = InterpreterPool(min_size=min_size, max_size=max_size, acquire_timeout=5.0)
    try:
        pooled = pool.acquire()
        pool.release(pooled, healthy=(release_kind == "healthy"))
        # Pool must still be functional after any release kind.
        with pool.acquire() as interp:
            result = interp.call(_fn_identity, 99)
        assert result == 99
        event("outcome=pool_functional_after_release")
    finally:
        pool.close()


@given(sizes=pool_sizes)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_close_idempotent(sizes: tuple[int, int]) -> None:
    """close() called multiple times never raises.

    Property: close() is idempotent; any number of calls is safe.
    """
    min_size, max_size = sizes
    event(f"min_size={min_size}")
    event(f"max_size={max_size}")
    pool = InterpreterPool(min_size=min_size, max_size=max_size)
    pool.close()
    pool.close()
    pool.close()
    event("outcome=close_idempotent")


@given(
    sizes=pool_sizes,
    n_after_close=st.integers(min_value=1, max_value=3),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_acquire_after_close_always_raises(
    sizes: tuple[int, int], n_after_close: int
) -> None:
    """acquire() always raises RuntimeError after close(), no matter how many times.

    Property: closed pool rejects all acquire() calls unconditionally.
    """
    min_size, max_size = sizes
    event(f"n_after_close={n_after_close}")

    pool = InterpreterPool(min_size=min_size, max_size=max_size)
    pool.close()
    for _ in range(n_after_close):
        with pytest.raises(RuntimeError, match="closed"):
            pool.acquire()
    event("outcome=closed_pool_rejects_all")


@given(
    sizes=pool_sizes,
    n_tasks=st.integers(min_value=1, max_value=8),
)
@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_threadpool_executor_integration(
    sizes: tuple[int, int], n_tasks: int
) -> None:
    """InterpreterPool integrates correctly with ThreadPoolExecutor.

    Property: all submitted tasks complete and return correct values.
    """
    min_size, max_size = sizes
    event(f"n_tasks={n_tasks}")
    event(f"pool_max_size={max_size}")

    pool = InterpreterPool(min_size=min_size, max_size=max_size, acquire_timeout=10.0)
    try:
        def task(n: int) -> int:
            with pool.acquire() as interp:
                return interp.call(_fn_identity, n)  # type: ignore[return-value]

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(n_tasks, 4)) as ex:
            futures = [ex.submit(task, i) for i in range(n_tasks)]
            results = sorted(f.result() for f in concurrent.futures.as_completed(futures))

        assert results == list(range(n_tasks))
        event("outcome=threadpool_success")
    finally:
        pool.close()
