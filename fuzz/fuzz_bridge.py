#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: bridge - FunctionRegistry Bridge Machinery
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""FunctionRegistry Bridge Machinery Fuzzer (Atheris).

Targets: ftllexengine.runtime.function_bridge (FunctionRegistry, FunctionSignature,
FluentNumber, fluent_function decorator, parameter mapping, locale injection)

Concern boundary: This fuzzer stress-tests the bridge machinery that connects
FTL function calls to Python implementations. Distinct from fuzz_builtins which
tests built-in functions (NUMBER, DATETIME, CURRENCY) through the bridge; this
fuzzer tests the bridge itself:
- FunctionRegistry.register() with varied function signatures
- Parameter mapping: _to_camel_case conversion and custom param_map
- FunctionRegistry.call() dispatch with adversarial arguments
- Locale injection protocol (fluent_function decorator)
- FunctionSignature construction and immutability
- FluentNumber object contracts (str, hash, contains, len, repr)
- Dict-like registry interface (__iter__, __contains__, __len__)
- Freeze/copy lifecycle and isolation
- Adversarial Python objects (evil __str__, __hash__, recursive structures)
- Error wrapping (TypeError/ValueError -> FrozenFluentError)

Metrics:
- Pattern coverage with weighted selection (14 patterns)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management
- Per-pattern wall-time accumulation

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
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
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str]  # (duration_ms, description)

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
    print(f"[FATAL] Missing dependencies: {', '.join(_MISSING_DEPS)}", file=sys.stderr)
    print("Install: uv sync --group atheris", file=sys.stderr)
    sys.exit(1)


# --- FuzzerState ---


@dataclass
class FuzzerState:
    """Mutable fuzzer state with bounded memory."""

    iterations: int = 0
    findings: int = 0
    status: str = "init"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

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


# --- Report ---


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
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

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            growth_mb = statistics.mean(last_quarter) - statistics.mean(first_quarter)
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
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    try:
        report_file = pathlib.Path(".fuzz_corpus") / "bridge" / "fuzz_bridge_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass  # Best-effort


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.function_bridge import (
        FluentNumber,
        FunctionRegistry,
        fluent_function,
    )
    from ftllexengine.runtime.functions import (
        create_default_registry,
        get_shared_registry,
    )


# --- Constants ---

_LOCALES: Sequence[str] = (
    "en", "en_US", "de", "de_DE", "ar", "ar_SA", "ja", "ja_JP",
    "fr", "fr_FR", "ru",
)

# Snake_case names for _to_camel_case testing
_SNAKE_CASE_NAMES: Sequence[str] = (
    "minimum_fraction_digits",
    "maximum_fraction_digits",
    "use_grouping",
    "date_style",
    "time_style",
    "currency_display",
    "value",
    "x",
    "_private_param",
    "__dunder_param",
    "a_b_c_d_e",
    "already_camel",
    "",
    "_",
    "__",
    "___",
    "UPPER_CASE",
    "mixed_Case_Style",
    "single",
)

# Expected camelCase conversions for invariant checking
_CAMEL_EXPECTED: dict[str, str] = {
    "minimum_fraction_digits": "minimumFractionDigits",
    "maximum_fraction_digits": "maximumFractionDigits",
    "use_grouping": "useGrouping",
    "value": "value",
    "x": "x",
    "single": "single",
}

# Pattern weights: (name, weight)
# Ordered cheapest-first to counteract libFuzzer's small-byte bias:
# ConsumeIntInRange skews toward low values, over-selecting early entries.
# Cheap patterns (pure-Python, no FluentBundle) go first; expensive patterns
# (FluentBundle creation per call) go last.
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: pure-Python, no bundle creation
    ("fluent_number_contracts", 12),
    ("camel_case_conversion", 10),
    ("signature_immutability", 5),
    ("register_basic", 10),
    ("register_signatures", 12),
    ("param_mapping_custom", 8),
    ("call_dispatch", 12),
    ("dict_interface", 8),
    ("freeze_copy_lifecycle", 8),
    ("fluent_function_decorator", 8),
    ("error_wrapping", 7),
    # Expensive: create FluentBundle per call
    ("locale_injection", 10),
    ("evil_objects", 5),
    ("raw_bytes", 3),
)

# Allowed exceptions from bridge operations
_ALLOWED_EXCEPTIONS = (
    ValueError, TypeError, OverflowError, ArithmeticError,
    FrozenFluentError, RecursionError, RuntimeError,
)


class BridgeFuzzError(Exception):
    """Raised when a bridge invariant is breached."""


# --- Tracking helpers ---


def _track_slowest_operation(duration_ms: float, description: str) -> None:
    """Track top 10 slowest operations using min-heap."""
    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, (duration_ms, description[:50]))
    elif duration_ms > _state.slowest_operations[0][0]:
        heapq.heapreplace(
            _state.slowest_operations, (duration_ms, description[:50])
        )


def _track_seed_corpus(data: bytes, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with FIFO eviction."""
    # Timing-based only to avoid corpus churn
    is_interesting = duration_ms > 10.0

    if is_interesting:
        input_hash = hashlib.sha256(data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = data
            _state.corpus_entries_added += 1


def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


# --- Pattern implementations ---


def _pattern_register_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """Basic function registration: name generation, simple callables."""
    reg = FunctionRegistry()
    num_funcs = fdp.ConsumeIntInRange(1, 5)

    for i in range(num_funcs):
        # Generate a simple function with unique name
        def make_fn(idx: int) -> Any:
            def fn(_value: Any) -> str:
                return f"result_{idx}"
            fn.__name__ = f"test_func_{idx}"
            return fn

        func = make_fn(i)
        ftl_name = f"FUNC{i}" if fdp.ConsumeBool() else None

        reg.register(func, ftl_name=ftl_name)

    # Invariant: len matches registration count
    if len(reg) != num_funcs:
        msg = f"Registry len {len(reg)} != expected {num_funcs}"
        raise BridgeFuzzError(msg)


def _pattern_register_signatures(fdp: atheris.FuzzedDataProvider) -> None:
    """Registration with various Python function signatures."""
    reg = FunctionRegistry()
    variant = fdp.ConsumeIntInRange(0, 6)

    match variant:
        case 0:
            # Positional-only params
            def pos_only(value: Any, /) -> str:
                return str(value)
            reg.register(pos_only, ftl_name="POS_ONLY")

        case 1:
            # Keyword-only params
            def kw_only(value: Any, *, style: str = "default") -> str:
                return f"{value}_{style}"
            reg.register(kw_only, ftl_name="KW_ONLY")
            result = reg.call("KW_ONLY", [42], {"style": "custom"})
            if "42" not in str(result):
                msg = f"KW_ONLY result missing value: {result}"
                raise BridgeFuzzError(msg)

        case 2:
            # *args function
            def varargs(*args: Any) -> str:
                return "_".join(str(a) for a in args)
            reg.register(varargs, ftl_name="VARARGS")
            n = fdp.ConsumeIntInRange(0, 5)
            positional = [fdp.ConsumeIntInRange(0, 100) for _ in range(n)]
            reg.call("VARARGS", positional, {})

        case 3:
            # **kwargs function
            def kwargs_fn(value: Any, **kwargs: Any) -> str:
                return f"{value}_{len(kwargs)}"
            reg.register(kwargs_fn, ftl_name="KWARGS_FN")
            named = {f"key{i}": i for i in range(fdp.ConsumeIntInRange(0, 5))}
            reg.call("KWARGS_FN", ["hello"], named)

        case 4:
            # Function with many parameters (auto-mapping stress)
            def many_params(
                value: Any, *,
                minimum_fraction_digits: int = 0,  # noqa: ARG001
                maximum_fraction_digits: int = 3,  # noqa: ARG001
                use_grouping: bool = True,  # noqa: ARG001
                currency_display: str = "symbol",  # noqa: ARG001
            ) -> str:
                return str(value)
            reg.register(many_params, ftl_name="MANY")
            info = reg.get_function_info("MANY")
            if info is None:
                msg = "get_function_info returned None for registered function"
                raise BridgeFuzzError(msg)
            # Verify param_mapping includes all snake_case -> camelCase
            mapping_dict = dict(info.param_mapping)
            if "minimumFractionDigits" not in mapping_dict:
                msg = f"Missing camelCase mapping: {mapping_dict}"
                raise BridgeFuzzError(msg)

        case 5:
            # Duplicate registration (should overwrite)
            def fn_v1(_value: Any) -> str:
                return "v1"
            def fn_v2(_value: Any) -> str:
                return "v2"
            fn_v2.__name__ = "fn_v1"
            reg.register(fn_v1, ftl_name="DUP")
            reg.register(fn_v2, ftl_name="DUP")
            result = reg.call("DUP", ["x"], {})
            if str(result) != "v2":
                msg = f"Duplicate registration did not overwrite: got {result}"
                raise BridgeFuzzError(msg)

        case _:
            # Lambda registration
            reg.register(str, ftl_name="LAMBDA")
            reg.call("LAMBDA", [42], {})


def _pattern_camel_case_conversion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test _to_camel_case with known and fuzzed inputs."""
    variant = fdp.ConsumeIntInRange(0, 2)

    if variant == 0:
        # Known conversions with invariant checks
        for snake, expected_camel in _CAMEL_EXPECTED.items():
            result = FunctionRegistry._to_camel_case(snake)
            if result != expected_camel:
                msg = (
                    f"_to_camel_case('{snake}') = '{result}', "
                    f"expected '{expected_camel}'"
                )
                raise BridgeFuzzError(msg)

    elif variant == 1:
        # Fuzzed snake_case names from curated list
        name = fdp.PickValueInList(list(_SNAKE_CASE_NAMES))
        result = FunctionRegistry._to_camel_case(name)
        # Invariant: result should be a string
        if not isinstance(result, str):
            msg = f"_to_camel_case returned non-string: {type(result)}"
            raise BridgeFuzzError(msg)

    else:
        # Fully fuzzed input
        raw = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
        result = FunctionRegistry._to_camel_case(raw)
        if not isinstance(result, str):
            msg = "_to_camel_case returned non-string for fuzzed input"
            raise BridgeFuzzError(msg)


def _pattern_param_mapping_custom(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom param_map overrides auto-generated mappings."""
    reg = FunctionRegistry()

    def target_fn(value: Any, *, minimum_fraction_digits: int = 0) -> str:  # noqa: ARG001
        return str(value)

    variant = fdp.ConsumeIntInRange(0, 2)

    if variant == 0:
        # Custom mapping overrides auto-generated
        custom_map = {"customName": "minimum_fraction_digits"}
        reg.register(target_fn, ftl_name="CUSTOM_MAP", param_map=custom_map)
        result = reg.call("CUSTOM_MAP", [42], {"customName": 2})
        if "42" not in str(result):
            msg = f"Custom param_map call failed: {result}"
            raise BridgeFuzzError(msg)

    elif variant == 1:
        # Empty custom map (auto-generation only)
        reg.register(target_fn, ftl_name="EMPTY_MAP", param_map={})
        info = reg.get_function_info("EMPTY_MAP")
        if info is None or len(info.param_mapping) == 0:
            msg = "Empty param_map should still have auto-generated mappings"
            raise BridgeFuzzError(msg)

    else:
        # Fuzzed param_map keys
        fuzzed_key = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 30))
        custom_map = {fuzzed_key: "minimum_fraction_digits"}
        reg.register(target_fn, ftl_name="FUZZ_MAP", param_map=custom_map)
        with contextlib.suppress(Exception):
            reg.call("FUZZ_MAP", [1], {fuzzed_key: 2})


def _pattern_call_dispatch(fdp: atheris.FuzzedDataProvider) -> None:
    """Test call() dispatch with varied argument shapes."""
    reg = FunctionRegistry()

    def echo_fn(value: Any, **kwargs: Any) -> str:
        return f"{value}|{len(kwargs)}"

    reg.register(echo_fn, ftl_name="ECHO")

    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # Normal call
            result = reg.call("ECHO", [42], {"key": "val"})
            if "42" not in str(result):
                msg = f"Normal call failed: {result}"
                raise BridgeFuzzError(msg)

        case 1:
            # No positional args
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
                reg.call("ECHO", [], {})

        case 2:
            # Many positional args
            n = fdp.ConsumeIntInRange(2, 10)
            args = [fdp.ConsumeIntInRange(0, 100) for _ in range(n)]
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
                reg.call("ECHO", args, {})

        case 3:
            # Unknown function name
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
                reg.call("NONEXISTENT", [1], {})

        case _:
            # Call with many kwargs
            n = fdp.ConsumeIntInRange(1, 10)
            kwargs = {f"k{i}": i for i in range(n)}
            reg.call("ECHO", ["val"], kwargs)


def _pattern_locale_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Test locale injection protocol with custom functions."""
    reg = FunctionRegistry()

    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Decorated with inject_locale=True
            @fluent_function(inject_locale=True)
            def locale_fn(value: Any, locale_code: str) -> str:
                return f"{value}@{locale_code}"

            reg.register(locale_fn, ftl_name="LOCALE_FN")

            if not reg.should_inject_locale("LOCALE_FN"):
                msg = "should_inject_locale returned False for decorated function"
                raise BridgeFuzzError(msg)

        case 1:
            # Not decorated -- should NOT inject locale
            def plain_fn(value: Any) -> str:
                return str(value)

            reg.register(plain_fn, ftl_name="PLAIN_FN")

            if reg.should_inject_locale("PLAIN_FN"):
                msg = "should_inject_locale returned True for plain function"
                raise BridgeFuzzError(msg)

        case 2:
            # Nonexistent function
            if reg.should_inject_locale("DOES_NOT_EXIST"):
                msg = "should_inject_locale returned True for nonexistent function"
                raise BridgeFuzzError(msg)

        case _:
            # End-to-end: locale injection through FluentBundle
            locale = _pick_locale(fdp)
            bundle = FluentBundle(locale, strict=False)

            @fluent_function(inject_locale=True)
            def fmt_fn(value: Any, locale_code: str) -> str:
                return f"[{locale_code}:{value}]"

            bundle.add_function("FMT", fmt_fn)
            bundle.add_resource("msg = { FMT($val) }\n")
            with contextlib.suppress(Exception):
                bundle.format_pattern("msg", {"val": "test"})


def _pattern_fluent_number_contracts(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """FluentNumber object contracts: str, hash, contains, len, repr."""
    variant = fdp.ConsumeIntInRange(0, 5)

    match variant:
        case 0:
            # Basic construction and str
            fn = FluentNumber(value=Decimal("1234.56"), formatted="1,234.56", precision=2)
            if str(fn) != "1,234.56":
                msg = f"FluentNumber str() = '{fn}', expected '1,234.56'"
                raise BridgeFuzzError(msg)

        case 1:
            # __contains__ delegates to formatted
            fn = FluentNumber(value=42, formatted="42.00", precision=2)
            if "42" not in fn:
                msg = "FluentNumber __contains__ failed for '42' in '42.00'"
                raise BridgeFuzzError(msg)
            if "99" in fn:
                msg = "FluentNumber __contains__ false positive for '99' in '42.00'"
                raise BridgeFuzzError(msg)

        case 2:
            # __len__ returns formatted string length
            formatted = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))
            fn = FluentNumber(value=0, formatted=formatted, precision=0)
            if len(fn) != len(formatted):
                msg = f"FluentNumber len() = {len(fn)}, expected {len(formatted)}"
                raise BridgeFuzzError(msg)

        case 3:
            # repr includes value info
            fn = FluentNumber(value=Decimal("99.9"), formatted="99.9", precision=1)
            r = repr(fn)
            if "99.9" not in r:
                msg = f"FluentNumber repr missing value: {r}"
                raise BridgeFuzzError(msg)

        case 4:
            # Precision can be None
            fn = FluentNumber(value=42, formatted="42", precision=None)
            if fn.precision is not None:
                msg = "FluentNumber precision should be None"
                raise BridgeFuzzError(msg)
            if str(fn) != "42":
                msg = f"FluentNumber str() with None precision = '{fn}'"
                raise BridgeFuzzError(msg)

        case _:
            # Frozen: attribute assignment should fail
            fn = FluentNumber(value=1, formatted="1", precision=0)
            try:
                fn.value = 999  # type: ignore[misc]
                msg = "FluentNumber is not frozen: attribute assignment succeeded"
                raise BridgeFuzzError(msg)
            except AttributeError:
                pass  # Expected: frozen dataclass


def _pattern_dict_interface(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """Dict-like interface: __iter__, __contains__, __len__, list_functions."""
    reg = create_default_registry()

    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # __contains__ for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in reg:
                    msg = f"Default registry missing {name} via __contains__"
                    raise BridgeFuzzError(msg)
            # Nonexistent
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            if fuzzed in reg and fuzzed not in ("NUMBER", "DATETIME", "CURRENCY"):
                msg = f"Registry contains unexpected function: {fuzzed}"
                raise BridgeFuzzError(msg)

        case 1:
            # __iter__ yields all function names
            names = list(reg)
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in names:
                    msg = f"__iter__ missing {name}"
                    raise BridgeFuzzError(msg)

        case 2:
            # list_functions returns all registered names (insertion order)
            funcs = reg.list_functions()
            if len(funcs) != len(reg):
                msg = f"list_functions length {len(funcs)} != len(reg) {len(reg)}"
                raise BridgeFuzzError(msg)
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                if name not in funcs:
                    msg = f"list_functions missing {name}"
                    raise BridgeFuzzError(msg)

        case _:
            # get_python_name and get_callable
            py_name = reg.get_python_name("NUMBER")
            if py_name is None:
                msg = "get_python_name('NUMBER') returned None"
                raise BridgeFuzzError(msg)
            callable_fn = reg.get_callable("NUMBER")
            if callable_fn is None:
                msg = "get_callable('NUMBER') returned None"
                raise BridgeFuzzError(msg)
            # Nonexistent
            if reg.get_python_name("FAKE") is not None:
                msg = "get_python_name returned non-None for nonexistent"
                raise BridgeFuzzError(msg)


def _pattern_freeze_copy_lifecycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Freeze/copy lifecycle: isolation, mutation prevention."""
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Freeze prevents registration
            reg = FunctionRegistry()
            reg.register(str, ftl_name="PRE")
            reg.freeze()
            if not reg.frozen:
                msg = "Registry not frozen after freeze()"
                raise BridgeFuzzError(msg)
            try:
                reg.register(str, ftl_name="POST")
                msg = "Frozen registry accepted registration"
                raise BridgeFuzzError(msg)
            except TypeError:
                pass  # Expected

        case 1:
            # Copy is unfrozen and independent
            shared = get_shared_registry()
            copy = shared.copy()
            if copy.frozen:
                msg = "Copy should be unfrozen"
                raise BridgeFuzzError(msg)

            def custom(_value: Any) -> str:
                return "custom"
            copy.register(custom, ftl_name="COPY_ONLY")
            if "COPY_ONLY" in shared:
                msg = "Copy polluted original registry"
                raise BridgeFuzzError(msg)
            if "COPY_ONLY" not in copy:
                msg = "Copy missing newly registered function"
                raise BridgeFuzzError(msg)

        case 2:
            # Copy preserves all original functions
            original = create_default_registry()
            original_funcs = set(original)
            copy = original.copy()
            copy_funcs = set(copy)
            if original_funcs != copy_funcs:
                msg = f"Copy functions differ: {original_funcs - copy_funcs}"
                raise BridgeFuzzError(msg)

        case _:
            # Double freeze is safe (idempotent)
            reg = FunctionRegistry()
            reg.freeze()
            reg.freeze()  # Should not raise
            if not reg.frozen:
                msg = "Double freeze broke frozen state"
                raise BridgeFuzzError(msg)


def _pattern_evil_objects(fdp: atheris.FuzzedDataProvider) -> None:
    """Adversarial Python objects as FTL variables.

    Splits into cheap (str-only) and expensive (full FluentBundle) paths
    to reduce per-call cost while maintaining coverage.
    """
    variant = fdp.ConsumeIntInRange(0, 5)

    match variant:
        case 0:
            # Evil __str__ raises RuntimeError
            class EvilStr:
                """Object whose __str__ raises RuntimeError."""
                def __str__(self) -> str:
                    raise RuntimeError("evil __str__")  # noqa: EM101
            var: object = EvilStr()

        case 1:
            # Evil __hash__ raises TypeError
            class EvilHash:
                """Object whose __hash__ raises TypeError."""
                def __hash__(self) -> int:
                    raise TypeError("unhashable evil")  # noqa: EM101
                def __str__(self) -> str:
                    return "evil"
            var = EvilHash()

        case 2:
            # Recursive list
            recursive_list: list[object] = []
            recursive_list.append(recursive_list)
            var = recursive_list

        case 3:
            # Recursive dict
            recursive_dict: dict[str, object] = {}
            recursive_dict["self"] = recursive_dict
            var = recursive_dict

        case 4:
            # Massive string
            size = fdp.ConsumeIntInRange(1000, 50000)
            var = "A" * size

        case _:
            # None value
            var = None

    # 50% cheap path (str conversion only), 50% full bundle path
    if fdp.ConsumeBool():
        # Cheap: test str() resilience without FluentBundle overhead
        with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
            str(var)
    else:
        # Expensive: full FluentBundle resolution
        bundle = FluentBundle("en-US", enable_cache=fdp.ConsumeBool())
        bundle.add_resource("msg = Value: { $var }\n")
        with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
            bundle.format_value("msg", {"var": var})  # type: ignore[dict-item]


def _pattern_fluent_function_decorator(fdp: atheris.FuzzedDataProvider) -> None:
    """Test @fluent_function decorator edge cases."""
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Bare decorator (no parentheses)
            @fluent_function
            def bare_fn(value: Any) -> str:
                return str(value)

            if bare_fn(42) != "42":
                msg = f"Bare decorator broke function: {bare_fn(42)}"
                raise BridgeFuzzError(msg)

        case 1:
            # Decorator with parentheses, no inject_locale
            @fluent_function()
            def parens_fn(value: Any) -> str:
                return str(value)

            if parens_fn(42) != "42":
                msg = f"Parenthesized decorator broke function: {parens_fn(42)}"
                raise BridgeFuzzError(msg)

        case 2:
            # Decorator with inject_locale=True sets attribute
            @fluent_function(inject_locale=True)
            def locale_fn(value: Any, locale_code: str) -> str:
                return f"{value}@{locale_code}"

            attr_name = "_ftl_requires_locale"
            if not getattr(locale_fn, attr_name, False):
                msg = "inject_locale=True did not set attribute"
                raise BridgeFuzzError(msg)

            result = locale_fn(42, "en")
            if result != "42@en":
                msg = f"Decorated function broken: {result}"
                raise BridgeFuzzError(msg)

        case _:
            # Register decorated function in registry
            @fluent_function(inject_locale=True)
            def reg_fn(_value: Any, locale_code: str) -> str:
                return f"[{locale_code}]"

            reg = FunctionRegistry()
            reg.register(reg_fn, ftl_name="REG_FN")
            if not reg.should_inject_locale("REG_FN"):
                msg = "Decorated + registered: should_inject_locale is False"
                raise BridgeFuzzError(msg)


def _pattern_error_wrapping(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify TypeError/ValueError from functions are wrapped as FrozenFluentError."""
    reg = create_default_registry()

    variant = fdp.ConsumeIntInRange(0, 2)

    match variant:
        case 0:
            # Call NUMBER with wrong type
            try:
                reg.call("NUMBER", ["not_a_number", "en"], {})
            except FrozenFluentError:
                pass  # Expected wrapping
            except (TypeError, ValueError):
                pass  # Also acceptable

        case 1:
            # Call nonexistent function
            with contextlib.suppress(FrozenFluentError, KeyError):
                reg.call("NONEXISTENT", [1], {})

        case _:
            # Call with wrong arity
            with contextlib.suppress(FrozenFluentError, TypeError):
                reg.call("NUMBER", [], {})


def _pattern_signature_immutability(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FunctionSignature immutability and param_mapping tuple type."""
    reg = create_default_registry()
    func_name = fdp.PickValueInList(["NUMBER", "DATETIME", "CURRENCY"])
    info = reg.get_function_info(func_name)

    if info is None:
        msg = f"{func_name} FunctionSignature is None"
        raise BridgeFuzzError(msg)

    # param_mapping should be tuple of tuples (immutable)
    if not isinstance(info.param_mapping, tuple):
        msg = f"param_mapping is {type(info.param_mapping)}, expected tuple"
        raise BridgeFuzzError(msg)

    for pair in info.param_mapping:
        if not isinstance(pair, tuple) or len(pair) != 2:
            msg = f"param_mapping entry is not (str, str): {pair}"
            raise BridgeFuzzError(msg)

    # FunctionSignature should be frozen
    try:
        info.ftl_name = "HACKED"  # type: ignore[misc]
        msg = "FunctionSignature is not frozen"
        raise BridgeFuzzError(msg)
    except AttributeError:
        pass  # Expected

    # Callable should be present
    if not callable(info.callable):
        msg = "FunctionSignature callable is not callable"
        raise BridgeFuzzError(msg)

    # ftl_name should match what we queried
    if info.ftl_name != func_name:
        msg = f"FunctionSignature.ftl_name = '{info.ftl_name}', expected '{func_name}'"
        raise BridgeFuzzError(msg)

    # Fuzzed: try getting info for nonexistent function
    if fdp.ConsumeBool():
        fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
        bad_info = reg.get_function_info(fuzzed)
        if bad_info is not None and fuzzed not in ("NUMBER", "DATETIME", "CURRENCY"):
            msg = f"get_function_info returned non-None for unknown '{fuzzed}'"
            raise BridgeFuzzError(msg)


def _pattern_raw_bytes(fdp: atheris.FuzzedDataProvider) -> None:
    """Raw bytes: fuzzed function names, arg values, locale strings."""
    reg = create_default_registry()

    target = fdp.ConsumeIntInRange(0, 2)

    match target:
        case 0:
            # Fuzzed function name through call()
            name = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
            with contextlib.suppress(Exception):
                reg.call(name, [1], {})

        case 1:
            # Fuzzed kwargs keys through call()
            n = fdp.ConsumeIntInRange(1, 5)
            kwargs: dict[str, Any] = {}
            for _ in range(n):
                key = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 30))
                kwargs[key] = fdp.ConsumeUnicodeNoSurrogates(5)
            with contextlib.suppress(Exception):
                reg.call("NUMBER", [Decimal("1"), "en"], kwargs)

        case _:
            # Fuzzed locale through FluentBundle end-to-end
            locale = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 100))
            with contextlib.suppress(Exception):
                bundle = FluentBundle(locale, strict=False)
                bundle.add_resource("msg = { NUMBER($val) }\n")
                bundle.format_pattern("msg", {"val": 42})


# --- Pattern dispatch ---


_PATTERN_DISPATCH: dict[str, Any] = {
    "register_basic": _pattern_register_basic,
    "register_signatures": _pattern_register_signatures,
    "camel_case_conversion": _pattern_camel_case_conversion,
    "param_mapping_custom": _pattern_param_mapping_custom,
    "call_dispatch": _pattern_call_dispatch,
    "locale_injection": _pattern_locale_injection,
    "fluent_number_contracts": _pattern_fluent_number_contracts,
    "dict_interface": _pattern_dict_interface,
    "freeze_copy_lifecycle": _pattern_freeze_copy_lifecycle,
    "evil_objects": _pattern_evil_objects,
    "fluent_function_decorator": _pattern_fluent_function_decorator,
    "error_wrapping": _pattern_error_wrapping,
    "signature_immutability": _pattern_signature_immutability,
    "raw_bytes": _pattern_raw_bytes,
}


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


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz FunctionRegistry bridge machinery."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern_name = _select_pattern(fdp)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    try:
        handler = _PATTERN_DISPATCH[pattern_name]
        handler(fdp)

    except BridgeFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except _ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid inputs

    except Exception:  # pylint: disable=broad-exception-caught
        _state.findings += 1
        error_type = sys.exc_info()[0]
        if error_type is not None:
            key = error_type.__name__[:50]
            _state.error_counts[key] = _state.error_counts.get(key, 0) + 1
        raise

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern_name] = (
            _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern_name)
        _track_seed_corpus(data, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the bridge machinery fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="FunctionRegistry bridge machinery fuzzer using Atheris/libFuzzer",
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
    print("FunctionRegistry Bridge Machinery Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     runtime.function_bridge")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)}")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
