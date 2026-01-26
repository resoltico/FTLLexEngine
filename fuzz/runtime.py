#!/usr/bin/env python3
"""Runtime End-to-End Fuzzer (Atheris).

Targets the full v0.8.x runtime stack: FluentBundle, IntegrityCache, Resolver,
and Strict Mode integrity guarantees.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import sys
import threading
from datetime import UTC, datetime
from typing import Any

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]
type ComplexArgs = dict[str, Any]

# Crash-proof reporting
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}


def _emit_final_report() -> None:
    """Emit a JSON report of the fuzzing session."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)


atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("Error: atheris not found. See docs/FUZZING_GUIDE.md")
    sys.exit(1)

# Suppress logging
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):  # type: ignore[attr-defined]
    from ftllexengine.integrity import (
        CacheCorruptionError,
        FormattingIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache import IntegrityCacheEntry


class RuntimeIntegrityError(Exception):
    """Raised when a runtime invariant is breached."""


def generate_complex_args(fdp: atheris.FuzzedDataProvider) -> ComplexArgs:  # type: ignore[name-defined]
    """Generate a dictionary of fuzzed arguments for resolution."""
    args: ComplexArgs = {}
    num_args = fdp.ConsumeIntInRange(0, 15)
    for i in range(num_args):
        key = f"var_{i}"
        val_type = fdp.ConsumeIntInRange(0, 6)
        match val_type:
            case 0:
                args[key] = fdp.ConsumeUnicodeNoSurrogates(20)
            case 1:
                args[key] = fdp.ConsumeFloat()
            case 2:
                args[key] = fdp.ConsumeInt(4)
            case 3:
                args[key] = datetime.now(tz=UTC)  # Real-world temporal
            case 4:
                args[key] = [fdp.ConsumeUnicodeNoSurrogates(5) for _ in range(3)]
            case 5:
                args[key] = {"nested": fdp.ConsumeInt(2)}
            case 6:
                args[key] = fdp.ConsumeBool()
    return args


def fuzzed_function(args: list[Any], kwargs: dict[str, Any]) -> str:
    """A mock custom function for testing FunctionRegistry integration."""
    return f"PROCESSED_{len(args)}_{len(kwargs)}"


def _add_random_resources(
    fdp: atheris.FuzzedDataProvider, bundle: FluentBundle  # type: ignore[name-defined]
) -> None:
    """Add random FTL resources to the bundle for testing."""
    num_resources = fdp.ConsumeIntInRange(1, 5)
    for _ in range(num_resources):
        patterns = [
            "msg = Value\n",
            "msg2 = Hello { $var }\n",
            "msg3 = { $var -> \n  [one] 1\n  *[other] other\n}\n",
            "-term = Term Value\n",
            "ref = { -term }\n",
            "attr = Value\n  .title = Title\n",
            "cyclic = { cyclic }\n",
            "deep = " + ("{ " * 50) + "val" + (" }" * 50) + "\n",
            "func_call = { FUZZ_FUNC($var, key: 'val') }\n",
        ]

        ftl = fdp.PickValueInList(patterns)
        if fdp.ConsumeBool():
            ftl += fdp.ConsumeUnicodeNoSurrogates(50)

        try:
            # aspect: Cross-verification of Resource Integrity
            v_res = bundle.validate_resource(ftl)
            bundle.add_resource(ftl)

            # If validly added but validator failed catastrophically (finding)
            # Note: is_valid checks BOTH errors AND annotations (see ValidationResult)
            if (
                v_res.is_valid is False
                and not v_res.errors
                and not v_res.annotations
                and fdp.ConsumeProbability() < 0.01
            ):
                msg = "Validator reported invalid but no diagnostics collected."
                raise RuntimeIntegrityError(msg)
        except RuntimeIntegrityError:
            raise
        except Exception:  # pylint: disable=broad-exception-caught
            pass


def _execute_runtime_invariants(  # noqa: PLR0912
    fdp: atheris.FuzzedDataProvider,  # type: ignore[name-defined]
    bundle: FluentBundle,
    target_ids: list[str],
    args: ComplexArgs,
    strict: bool,
    enable_cache: bool,
    cache_write_once: bool,
) -> None:
    """Verify core runtime invariants across multiple operations."""
    for msg_id in target_ids:
        attribute = fdp.PickValueInList([None, "title", "nonexistent"])
        try:
            # Primary formatting attempt
            res1, err1 = bundle.format_pattern(msg_id, args, attribute=attribute)

            # INVARIANT: Strict Mode Integrity
            if strict and len(err1) > 0:
                msg = f"Strict mode breach: returned {len(err1)} errors for '{msg_id}'."
                raise RuntimeIntegrityError(msg)

            # INVARIANT: Frozen Error Integrity
            for e in err1:
                if not e.verify_integrity():
                    msg = "FrozenFluentError checksum verification failed."
                    raise RuntimeIntegrityError(msg)

            # aspect: Cache Operations & Invariants
            if enable_cache and bundle._cache is not None:
                # Hit secondary hit immediately
                res2, err2 = bundle.format_pattern(msg_id, args, attribute=attribute)
                if res1 != res2 or len(err1) != len(err2):
                    msg = f"Cache stability breach in '{msg_id}': non-deterministic result."
                    raise RuntimeIntegrityError(msg)

                # aspect: Simulation of Data Corruption (Bypassing Protection)
                if fdp.ConsumeProbability() < 0.05:
                    _simulate_corruption_incident(bundle)
                    try:
                        # This should either fail-fast (strict) or evict (non-strict)
                        bundle.format_pattern(msg_id, args, attribute=attribute)
                    except CacheCorruptionError as exc:
                        if not strict:
                            msg = "Non-strict cache raised CacheCorruptionError."
                            raise RuntimeIntegrityError(msg) from exc
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        # Catching type-incorrect exceptions
                        if "corruption" in str(e).lower() and not isinstance(
                            e, CacheCorruptionError
                        ):
                            msg = f"Wrong exception type for corruption: {type(e)}"
                            raise RuntimeIntegrityError(msg) from e

        except FormattingIntegrityError as e:
            if not strict:
                msg = "Non-strict bundle raised FormattingIntegrityError."
                raise RuntimeIntegrityError(msg) from e
            if not e.fluent_errors:
                msg = "FormattingIntegrityError empty."
                raise RuntimeIntegrityError(msg) from e

        except WriteConflictError as e:
            # aspect: Write-once semantics verification
            if not cache_write_once:
                msg = "WriteConflictError raised when write_once=False."
                raise RuntimeIntegrityError(msg) from e

        except (RecursionError, MemoryError):
            pass
        except Exception as e:  # pylint: disable=broad-exception-caught
            if "ftllexengine" in str(getattr(e, "__module__", "")):
                print(f"\n[CRASH] {type(e).__name__}: {e}")
                raise


def test_one_input(data: bytes) -> None:
    """Fuzzer entry point for Atheris."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)  # type: ignore[attr-defined]

    # 1. Configuration (Full Permutation Matrix)
    strict = fdp.ConsumeBool()
    enable_cache = fdp.ConsumeBool()
    use_isolating = fdp.ConsumeBool()
    cache_write_once = fdp.ConsumeBool()

    # 2. Locale & Initialization
    locales = ["en-US", "lv", "ar", "pl_PL", "", "invalid!!", "x" * 256]
    locale = (
        fdp.PickValueInList(locales)
        if fdp.ConsumeBool()
        else fdp.ConsumeUnicodeNoSurrogates(10)
    )

    try:
        try:
            bundle = FluentBundle(
                locale,
                strict=strict,
                enable_cache=enable_cache,
                use_isolating=use_isolating,
                cache_write_once=cache_write_once,
            )
            if fdp.ConsumeBool():
                bundle.add_function("FUZZ_FUNC", fuzzed_function)
        except (ValueError, TypeError):
            return

        # 3. Resource & Validation Aspect
        _add_random_resources(fdp, bundle)

        # 4. Arguments
        args = generate_complex_args(fdp)
        target_ids = [
            "msg",
            "msg2",
            "msg3",
            "ref",
            "attr",
            "cyclic",
            "deep",
            "func_call",
            "nonexistent",
        ]

        # 5. Concurrent Execution (RWLock & Race Testing)
        barrier = threading.Barrier(2)

        def worker_job() -> None:
            """Concurrent worker to stress-test RWLock and Cache."""
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait(timeout=2.0)

            _execute_runtime_invariants(
                fdp,
                bundle,
                target_ids,
                args,
                strict,
                enable_cache,
                cache_write_once,
            )

        # 6. Thread Execution
        threads = [threading.Thread(target=worker_job) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
            if t.is_alive():
                msg = "RWLock Deadlock detected."
                raise RuntimeIntegrityError(msg)

    except CacheCorruptionError:
        # If we are in strict mode, this is EXPECTED behavior when corruption occurs.
        # We catch it here to prevent the fuzzer from treating it as a crash.
        if strict:
            return  # Correct behavior verified
        
        # If not strict, it should have been handled gracefully.
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise

    except KeyboardInterrupt:
        _fuzz_stats["status"] = "stopped"
        raise

    except Exception:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        raise


def _simulate_corruption_incident(bundle: FluentBundle) -> None:
    """Reach into internal state to simulate a hardware-level checksum mismatch."""
    if bundle._cache is None:
        return
    with bundle._cache._lock:
        if not bundle._cache._cache:
            return
        key = next(iter(bundle._cache._cache))
        entry = bundle._cache._cache[key]

        # Bypass 'frozen' dataclass to simulate bit-flip
        corrupted = IntegrityCacheEntry(
            formatted=entry.formatted + "CORRUPTION",
            errors=entry.errors,
            checksum=entry.checksum,  # Invalid now
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        bundle._cache._cache[key] = corrupted


def main() -> None:
    """Setup and run the fuzzer."""
    sys.setrecursionlimit(2000)
    atheris.Setup(sys.argv, test_one_input)  # type: ignore[attr-defined]
    atheris.Fuzz()  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
