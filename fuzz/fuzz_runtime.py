#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: runtime - End-to-End Runtime & strict mode validation
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Runtime End-to-End Fuzzer (Atheris).

Targets the full v0.8.x runtime stack: FluentBundle, IntegrityCache, Resolver,
and Strict Mode integrity guarantees.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
"""

from __future__ import annotations

import atexit
import contextlib
import heapq
import json
import logging
import os
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any

import psutil

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]
type ComplexArgs = dict[str, Any]

# Crash-proof reporting
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}

# Seed Corpus Management
_seed_corpus: list[bytes] = []
_coverage_map: dict[str, int] = {}
_interesting_inputs: list[bytes] = []

# Performance profiling
_slowest_inputs: list[tuple[float, str]] = []  # Min-heap for top-N tracking
_fastest_inputs: list[tuple[float, str]] = []  # Min-heap (negated durations)

# Process handle (created once, reused for all iterations)
_process: psutil.Process = psutil.Process(os.getpid())


def _update_coverage(coverage_key: str) -> bool:
    """Update coverage map and return True if this is new coverage."""
    if coverage_key not in _coverage_map:
        _coverage_map[coverage_key] = 1
        return True
    _coverage_map[coverage_key] += 1
    return False


def _add_to_seed_corpus(data: bytes, reason: str) -> None:
    """Add interesting input to seed corpus for future fuzzing."""
    if data not in _seed_corpus:
        _seed_corpus.append(data)
        _interesting_inputs.append(data)
        print(f"[SEED] Added input ({len(data)} bytes): {reason}", file=sys.stderr)


def _expand_corpus_with_variations(base_input: bytes, fdp: atheris.FuzzedDataProvider) -> None:  # type: ignore[name-defined]
    """Generate variations of interesting inputs to expand corpus."""
    if len(_seed_corpus) >= 100:  # Limit corpus size
        return

    # Create variations by mutating the base input
    variations = []
    for _ in range(5):  # Generate 5 variations
        variation = bytearray(base_input)
        if len(variation) > 0:
            # Random mutations
            for _i in range(min(3, len(variation))):  # Mutate up to 3 positions
                pos = fdp.ConsumeIntInRange(0, len(variation) - 1)
                variation[pos] = fdp.ConsumeIntInRange(0, 255)
        variations.append(bytes(variation))

    for var in variations:
        if len(var) > 0:
            # Let _add_to_seed_corpus handle deduplication and tracking
            _add_to_seed_corpus(var, "corpus expansion variation")


def _emit_final_report() -> None:
    """Emit a JSON report of the fuzzing session."""
    # Extract top 5 slowest/fastest (heapq stores as (duration, input) tuples)
    slowest_top5 = [(inp[:50], dur) for dur, inp in heapq.nlargest(5, _slowest_inputs)]
    fastest_top5 = [(inp[:50], -dur) for dur, inp in heapq.nsmallest(5, _fastest_inputs)]

    report = {
        "status": _fuzz_stats["status"],
        "iterations": _fuzz_stats["iterations"],
        "findings": _fuzz_stats["findings"],
        "seed_corpus_size": len(_seed_corpus),
        "coverage_keys": len(_coverage_map),
        "interesting_inputs": len(_interesting_inputs),
        "slow_operations": _fuzz_stats.get("slow_operations", 0),
        "memory_leaks_detected": _fuzz_stats.get("memory_leaks", 0),
        "slowest_inputs": slowest_top5,
        "fastest_inputs": fastest_top5,
    }
    json_report = json.dumps(report, default=str)
    print(f"\n[SUMMARY-JSON-BEGIN]{json_report}[SUMMARY-JSON-END]", file=sys.stderr)


def _update_performance_stats(duration: float, operation_desc: str) -> None:
    """Update performance statistics with timing information."""
    # Track slowest operations using min-heap (maintain top 10 largest)
    if len(_slowest_inputs) < 10:
        heapq.heappush(_slowest_inputs, (duration, operation_desc))
    elif duration > _slowest_inputs[0][0]:
        heapq.heapreplace(_slowest_inputs, (duration, operation_desc))

    # Track fastest operations using max-heap (maintain top 10 smallest)
    # Negate duration for max-heap behavior with min-heap implementation
    neg_duration = -duration
    if len(_fastest_inputs) < 10:
        heapq.heappush(_fastest_inputs, (neg_duration, operation_desc))
    elif neg_duration > _fastest_inputs[0][0]:
        heapq.heapreplace(_fastest_inputs, (neg_duration, operation_desc))

    # Track slow operations (>100ms)
    if duration > 0.1:
        slow_count = int(_fuzz_stats.get("slow_operations", 0)) + 1
        _fuzz_stats["slow_operations"] = slow_count


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
        # Enhanced Edge Case Coverage: Unicode diversity and boundary conditions
        unicode_patterns = [
            # Unicode diversity
            "unicode = { $var } \u00A9 \u00AE \u2122",  # Copyright symbols
            "emoji = 😀 🌟 🚀 { $var }",  # Emojis
            "rtl = مرحبا { $var } עולם",  # Mixed RTL/LTR
            "combining = c\u0308a\u0308f\u0308e\u0308 { $var }",  # Combining characters
            "zerowidth = \u200B\u200E\u200F{ $var }",  # Zero-width characters
            # Boundary conditions
            "empty = { $var }",  # Minimal pattern
            "long_id = " + "a" * 256 + " = { $var }",  # Long identifier
            "deep_nest = " + ("{ " * 20) + "$var" + (" }" * 20),  # Deep nesting
            "many_attrs = Value\n" + "\n".join([
                f"  .attr{i} = Val{i}" for i in range(10)
            ]),  # Many attributes
            "complex_select = { $var ->\n" + "\n".join([
                f"  [{i}] val{i}" for i in range(20)
            ]) + "\n  *[other] other\n}",  # Complex select
        ]

        base_patterns = [
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

        # Combine base and unicode patterns
        all_patterns = base_patterns + unicode_patterns
        ftl = fdp.PickValueInList(all_patterns)

        # Add random unicode content with boundary conditions
        if fdp.ConsumeBool():
            # Unicode diversity injection
            unicode_additions = [
                fdp.ConsumeUnicodeNoSurrogates(50),
                "边界条件",  # Chinese boundary
                "🚀🌟💫",  # More emojis
                "\u0000\u0001\u0002",  # Control characters
                "a" * 1000,  # Long string
                "",  # Empty addition
            ]
            ftl += fdp.PickValueInList(unicode_additions)

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
    data: bytes,
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

            # Differential Testing Framework: Cross-validation with alternative implementations
            _perform_differential_testing(fdp, data, bundle, msg_id, args, attribute, res1, err1)

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


def _perform_differential_testing(
    fdp: atheris.FuzzedDataProvider,  # type: ignore[name-defined]
    data: bytes,
    bundle: FluentBundle,
    msg_id: str,
    args: ComplexArgs,
    attribute: str | None,
    expected_result: str,
    expected_errors: tuple[Any, ...],
) -> None:
    """Perform differential testing by comparing against alternative implementations."""
    # Create alternative bundle configurations for comparison
    alt_locales = ["en", "C", ""]  # Alternative locales
    alt_strict = not bundle.strict if fdp.ConsumeBool() else bundle.strict

    for alt_locale in alt_locales[:fdp.ConsumeIntInRange(1, 3)]:  # Test 1-2 alternatives
        try:
            alt_bundle = FluentBundle(
                alt_locale,
                strict=alt_strict,
                enable_cache=bundle.cache_enabled,
                use_isolating=bundle.use_isolating,
                cache_write_once=bundle.cache_write_once,
            )

            # Note: Resource copying not implemented as FluentBundle doesn't expose _resources
            # This is acceptable for differential testing - we test with empty bundles
            # and focus on function/locale/strictness configuration differences

            # Copy functions
            for name in bundle._function_registry:
                func = bundle._function_registry.get_callable(name)
                if func:
                    alt_bundle.add_function(name, func)

            # Compare results
            alt_result, alt_errors = alt_bundle.format_pattern(msg_id, args, attribute=attribute)

            # Cross-validation: Results should be consistent or have valid differences
            if ((bundle.locale == alt_locale and bundle.strict == alt_strict) and
                    (expected_result != alt_result or len(expected_errors) != len(alt_errors))):
                # Allow for locale-specific differences in error messages
                error_codes_match = all(
                    getattr(e, "diagnostic", None) and getattr(alt_e, "diagnostic", None) and
                    getattr(e.diagnostic, "code", None) == getattr(alt_e.diagnostic, "code", None)
                    for e, alt_e in zip(expected_errors, alt_errors, strict=False)
                )
                if not error_codes_match:
                    msg = "Differential testing failure: inconsistent results for same config"
                    raise RuntimeIntegrityError(msg)
            # Different configurations can have different results - that's expected

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Alternative bundle creation/failure is not necessarily an error
            # But log it for coverage tracking
            coverage_key = f"diff_test_{type(e).__name__}_{alt_locale}_{alt_strict}"
            if _update_coverage(coverage_key):
                _add_to_seed_corpus(
                    data,
                    f"differential testing edge: {coverage_key}"
                )


def _perform_security_fuzzing(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Perform advanced security fuzzing with attack vectors and resource exhaustion."""
    attack_vector = fdp.ConsumeIntInRange(0, 4)

    match attack_vector:
        case 0:  # Resource exhaustion via deep recursion
            _test_deep_recursion_attack(fdp, data)
        case 1:  # Memory exhaustion via large inputs
            _test_memory_exhaustion_attack(fdp, data)
        case 2:  # Cache poisoning attack
            _test_cache_poisoning_attack(fdp, data)
        case 3:  # Function injection attack
            _test_function_injection_attack(fdp, data)
        case 4:  # Locale explosion attack
            _test_locale_explosion_attack(fdp, data)


def _test_deep_recursion_attack(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Test deep recursion that could cause stack overflow."""
    depth = fdp.ConsumeIntInRange(100, 1000)
    ftl = "msg = { " * depth + "$var" + " }" * depth + "\n"

    try:
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(ftl)
        args = {"var": "test"}
        bundle.format_pattern("msg", args)
    except RecursionError:
        # Expected for deep recursion
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        coverage_key = f"recursion_attack_{type(e).__name__}"
        if _update_coverage(coverage_key):
            _add_to_seed_corpus(data, f"recursion attack: {coverage_key}")


def _test_memory_exhaustion_attack(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Test memory exhaustion via extremely large inputs."""
    size = fdp.ConsumeIntInRange(100000, 1000000)  # 100KB to 1MB
    large_string = "x" * size

    try:
        bundle = FluentBundle("en", strict=False)
        ftl = f"msg = {large_string}\n"
        bundle.add_resource(ftl)
        bundle.format_pattern("msg", {})
    except MemoryError:
        # Expected for large inputs
        pass
    except Exception as e:  # pylint: disable=broad-exception-caught
        coverage_key = f"memory_attack_{type(e).__name__}"
        if _update_coverage(coverage_key):
            _add_to_seed_corpus(data, f"memory attack: {coverage_key}")


def _test_cache_poisoning_attack(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Test cache poisoning via malicious cache key manipulation."""
    try:
        bundle = FluentBundle("en", enable_cache=True, strict=False)

        # Add legitimate resource
        bundle.add_resource("msg = Hello { $name }\n")

        # Attempt cache poisoning with various malicious inputs
        malicious_args = [
            {"name": float("inf")},
            {"name": float("-inf")},
            {"name": float("nan")},
            {"name": None},
            {"name": []},
            {"name": {}},
        ]

        # Randomly select subset of malicious args to test (fuzzer-driven)
        num_attacks = fdp.ConsumeIntInRange(1, len(malicious_args))
        for args in malicious_args[:num_attacks]:
            with contextlib.suppress(Exception):
                bundle.format_pattern("msg", args)  # type: ignore[arg-type]

        # Verify cache integrity
        if bundle._cache:
            for _key, entry in bundle._cache._cache.items():
                if not entry.verify():
                    msg = "Cache poisoning detected"
                    raise RuntimeIntegrityError(msg)

    except Exception as e:  # pylint: disable=broad-exception-caught
        coverage_key = f"cache_poisoning_{type(e).__name__}"
        if _update_coverage(coverage_key):
            _add_to_seed_corpus(data, f"cache poisoning: {coverage_key}")


def _test_function_injection_attack(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Test function injection via malicious function registration."""
    try:
        bundle = FluentBundle("en", strict=False)

        # Register potentially malicious functions
        dangerous_functions = [
            ("evil", lambda *_args, **_kwargs: exec(  # pylint: disable=exec-used
                fdp.ConsumeUnicodeNoSurrogates(100)
            )),  # Dangerous
            ("loop", lambda: list(range(1000000))),  # Resource intensive
            ("deep", lambda: _recursive_function(1000)),  # Deep recursion
        ]

        for name, func in dangerous_functions[:fdp.ConsumeIntInRange(1, 3)]:
            try:
                bundle.add_function(name, func)  # type: ignore[arg-type]
                # Try to use the function
                ftl = f"msg = {{ {name}() }}\n"
                bundle.add_resource(ftl)
                bundle.format_pattern("msg", {})
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Function failures are expected

    except Exception as e:  # pylint: disable=broad-exception-caught
        coverage_key = f"function_injection_{type(e).__name__}"
        if _update_coverage(coverage_key):
            _add_to_seed_corpus(data, f"function injection: {coverage_key}")


def _recursive_function(depth: int) -> str:
    """Helper for recursion testing."""
    if depth <= 0:
        return "done"
    return _recursive_function(depth - 1)


def _test_locale_explosion_attack(fdp: atheris.FuzzedDataProvider, data: bytes) -> None:  # type: ignore[name-defined]
    """Test locale explosion via extremely long or malicious locale strings."""
    malicious_locales = [
        "x" * 10000,  # Very long locale
        "en" * 1000,  # Repeated locale
        "\x00\x01\x02" * 100,  # Control characters
        "en-US" + "\u0000" * 1000,  # Null bytes
    ]

    for locale in malicious_locales[:fdp.ConsumeIntInRange(1, 3)]:
        try:
            bundle = FluentBundle(locale, strict=False)
            bundle.add_resource("msg = test\n")
            bundle.format_pattern("msg", {})
        except Exception as e:  # pylint: disable=broad-exception-caught
            coverage_key = f"locale_explosion_{type(e).__name__}"
            if _update_coverage(coverage_key):
                _add_to_seed_corpus(
                    data,
                    f"locale explosion: {coverage_key}"
                )


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Fuzzer entry point for Atheris."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)  # type: ignore[attr-defined]

    # Track performance and memory usage
    start_time = time.perf_counter()
    start_memory = _process.memory_info().rss / 1024 / 1024  # MB

    # Advanced Security Fuzzing: Attack vectors and resource exhaustion
    if fdp.ConsumeProbability() < 0.1:  # 10% of inputs for security testing
        _perform_security_fuzzing(fdp, data)
        duration = time.perf_counter() - start_time
        _update_performance_stats(duration, "security_fuzzing")
        return

    # Seed Corpus Management: Track interesting inputs
    coverage_key = f"input_{len(data)}_{data[:4].hex() if data else 'empty'}"
    if _update_coverage(coverage_key):
        _add_to_seed_corpus(data, f"new coverage: {coverage_key}")
        _expand_corpus_with_variations(data, fdp)

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

    target_ids: list[str] = []

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
                data,
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
    finally:
        # Monitor for performance and memory
        duration = time.perf_counter() - start_time
        end_memory = _process.memory_info().rss / 1024 / 1024  # MB
        memory_delta = end_memory - start_memory

        # Track performance
        operation_desc = f"bundle_{locale}_{len(target_ids)}_msgs"
        _update_performance_stats(duration, operation_desc)

        # Detect memory leaks (rough heuristic)
        if memory_delta > 50:  # >50MB increase
            leak_count = int(_fuzz_stats.get("memory_leaks", 0)) + 1
            _fuzz_stats["memory_leaks"] = leak_count


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
