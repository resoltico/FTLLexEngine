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
- Dict-like registry interface (__iter__, __contains__, __len__, has_function)
- Freeze/copy lifecycle and isolation
- Metadata API (get_expected_positional_args, get_builtin_metadata)
- Signature validation error paths (arity, collision, auto-naming)
- Adversarial Python objects (evil __str__, __hash__, recursive structures)
- Error wrapping (TypeError/ValueError -> FrozenFluentError)

Shared infrastructure imported from fuzz_common (BaseFuzzerState, metrics,
reporting); domain-specific metrics tracked in BridgeMetrics dataclass.
Pattern selection uses deterministic round-robin through a pre-built weighted
schedule (select_pattern_round_robin), immune to coverage-guided mutation bias.
Periodic gc.collect() every 256 iterations and -rss_limit_mb=4096 default.

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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

import atheris  # noqa: E402, I001  # pylint: disable=C0412,C0413


# --- Domain Metrics ---


@dataclass
class BridgeMetrics:
    """Domain-specific metrics for bridge fuzzer."""

    # Registration tests
    register_calls: int = 0
    register_failures: int = 0

    # Call dispatch
    call_dispatch_tests: int = 0
    call_dispatch_errors: int = 0

    # FluentNumber contract checks
    fluent_number_checks: int = 0

    # Camel case conversions
    camel_case_tests: int = 0

    # Freeze/copy operations
    freeze_copy_tests: int = 0

    # Locale injection tests
    locale_injection_tests: int = 0

    # Signature validation
    signature_validation_tests: int = 0

    # Metadata API tests
    metadata_api_tests: int = 0

    # Evil object tests
    evil_object_tests: int = 0


# --- Global State ---

_state = BaseFuzzerState(seed_corpus_max_size=500)
_domain = BridgeMetrics()

# Pattern weights: (name, weight)
# 15 patterns across 4 categories:
# REGISTRATION (4): register_basic, register_signatures, param_mapping_custom,
#                    signature_validation
# CONTRACTS (3): fluent_number_contracts, signature_immutability, camel_case_conversion
# DISPATCH (4): call_dispatch, locale_injection, error_wrapping, evil_objects
# INTROSPECTION (4): dict_interface, freeze_copy_lifecycle, fluent_function_decorator,
#                     metadata_api
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # REGISTRATION
    ("register_basic", 10),
    ("register_signatures", 12),
    ("param_mapping_custom", 8),
    ("signature_validation", 6),
    # CONTRACTS
    ("fluent_number_contracts", 12),
    ("signature_immutability", 5),
    ("camel_case_conversion", 10),
    # DISPATCH
    ("call_dispatch", 12),
    ("locale_injection", 10),
    ("error_wrapping", 7),
    ("evil_objects", 5),
    # INTROSPECTION
    ("dict_interface", 8),
    ("freeze_copy_lifecycle", 8),
    ("fluent_function_decorator", 8),
    ("metadata_api", 6),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class BridgeFuzzError(Exception):
    """Raised when a bridge invariant is breached."""


# Allowed exceptions from bridge operations
_ALLOWED_EXCEPTIONS = (
    ValueError, TypeError, OverflowError, ArithmeticError,
    RecursionError, RuntimeError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "bridge"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Registration
    stats["register_calls"] = _domain.register_calls
    stats["register_failures"] = _domain.register_failures

    # Call dispatch
    stats["call_dispatch_tests"] = _domain.call_dispatch_tests
    stats["call_dispatch_errors"] = _domain.call_dispatch_errors

    # FluentNumber
    stats["fluent_number_checks"] = _domain.fluent_number_checks

    # Camel case
    stats["camel_case_tests"] = _domain.camel_case_tests

    # Freeze/copy
    stats["freeze_copy_tests"] = _domain.freeze_copy_tests

    # Locale injection
    stats["locale_injection_tests"] = _domain.locale_injection_tests

    # Signature validation
    stats["signature_validation_tests"] = _domain.signature_validation_tests

    # Metadata API
    stats["metadata_api_tests"] = _domain.metadata_api_tests

    # Evil objects
    stats["evil_object_tests"] = _domain.evil_object_tests

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_bridge_report.json")


atexit.register(_emit_report)


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


def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 20))


# --- Pattern Implementations ---
# REGISTRATION (4 patterns)


def _pattern_register_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """Basic function registration: name generation, simple callables."""
    _domain.register_calls += 1
    reg = FunctionRegistry()
    num_funcs = fdp.ConsumeIntInRange(1, 5)

    for i in range(num_funcs):
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
    _domain.register_calls += 1
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


def _pattern_param_mapping_custom(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom param_map overrides auto-generated mappings."""
    _domain.register_calls += 1
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


def _pattern_signature_validation(fdp: atheris.FuzzedDataProvider) -> None:
    """Test registration error paths: locale arity, collision, auto-naming."""
    _domain.signature_validation_tests += 1
    reg = FunctionRegistry()
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # inject_locale with insufficient positional params -> TypeError
            @fluent_function(inject_locale=True)
            def bad_fn(value: Any) -> str:
                return str(value)

            try:
                reg.register(bad_fn, ftl_name="BAD_LOCALE")
                msg = "inject_locale with 1 positional param did not raise TypeError"
                raise BridgeFuzzError(msg)
            except TypeError:
                _domain.register_failures += 1

        case 1:
            # Underscore collision detection -> ValueError
            def colliding(
                value: Any, *,
                _data: int = 0,
                data: int = 0,  # noqa: ARG001
            ) -> str:
                return str(value)

            try:
                reg.register(colliding, ftl_name="COLLIDE")
                msg = "Underscore collision did not raise ValueError"
                raise BridgeFuzzError(msg)
            except ValueError:
                _domain.register_failures += 1

        case 2:
            # Auto-naming from __name__ (ftl_name=None)
            def my_custom_function(value: Any) -> str:
                return str(value)

            reg.register(my_custom_function)
            if "MY_CUSTOM_FUNCTION" not in reg:
                msg = "Auto-naming failed: MY_CUSTOM_FUNCTION not in registry"
                raise BridgeFuzzError(msg)

        case _:
            # inject_locale=True with *args function (should succeed)
            @fluent_function(inject_locale=True)
            def varargs_locale(*args: Any) -> str:
                return str(args)

            reg.register(varargs_locale, ftl_name="VARARGS_LOCALE")
            if not reg.should_inject_locale("VARARGS_LOCALE"):
                msg = "varargs function with inject_locale not detected"
                raise BridgeFuzzError(msg)


# CONTRACTS (3 patterns)


def _pattern_fluent_number_contracts(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """FluentNumber object contracts: str, hash, contains, len, repr."""
    _domain.fluent_number_checks += 1
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


def _pattern_camel_case_conversion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test _to_camel_case with known and fuzzed inputs."""
    _domain.camel_case_tests += 1
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


# DISPATCH (4 patterns)


def _pattern_call_dispatch(fdp: atheris.FuzzedDataProvider) -> None:
    """Test call() dispatch with varied argument shapes."""
    _domain.call_dispatch_tests += 1
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
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("ECHO", [], {})

        case 2:
            # Many positional args
            n = fdp.ConsumeIntInRange(2, 10)
            args = [fdp.ConsumeIntInRange(0, 100) for _ in range(n)]
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("ECHO", args, {})

        case 3:
            # Unknown function name
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
                reg.call("NONEXISTENT", [1], {})

        case _:
            # Call with many kwargs
            n = fdp.ConsumeIntInRange(1, 10)
            kwargs = {f"k{i}": i for i in range(n)}
            reg.call("ECHO", ["val"], kwargs)


def _pattern_locale_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Test locale injection protocol with custom functions."""
    _domain.locale_injection_tests += 1
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


def _pattern_error_wrapping(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify TypeError/ValueError from functions are wrapped as FrozenFluentError."""
    _domain.call_dispatch_errors += 1
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


def _pattern_evil_objects(fdp: atheris.FuzzedDataProvider) -> None:
    """Adversarial Python objects as FTL variables through FluentBundle."""
    _domain.evil_object_tests += 1
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

    # Full FluentBundle resolution path with adversarial objects
    bundle = FluentBundle("en-US", enable_cache=fdp.ConsumeBool())
    bundle.add_resource("msg = Value: { $var }\n")
    with contextlib.suppress(*_ALLOWED_EXCEPTIONS, FrozenFluentError):
        bundle.format_value("msg", {"var": var})  # type: ignore[dict-item]


# INTROSPECTION (4 patterns)


def _pattern_dict_interface(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """Dict-like interface: __iter__, __contains__, __len__, list_functions, __repr__."""
    reg = create_default_registry()
    variant = fdp.ConsumeIntInRange(0, 4)

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

        case 3:
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

        case _:
            # __repr__ consistency
            empty_reg = FunctionRegistry()
            r = repr(empty_reg)
            if "0" not in r:
                msg = f"Empty registry repr missing '0': {r}"
                raise BridgeFuzzError(msg)
            empty_reg.register(str, ftl_name="TEST")
            r2 = repr(empty_reg)
            if "1" not in r2:
                msg = f"Single-func registry repr missing '1': {r2}"
                raise BridgeFuzzError(msg)


def _pattern_freeze_copy_lifecycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Freeze/copy lifecycle: isolation, mutation prevention."""
    _domain.freeze_copy_tests += 1
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


def _pattern_metadata_api(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912
    """Test get_expected_positional_args, get_builtin_metadata, has_function."""
    _domain.metadata_api_tests += 1
    reg = create_default_registry()
    variant = fdp.ConsumeIntInRange(0, 4)

    match variant:
        case 0:
            # get_expected_positional_args for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                result = reg.get_expected_positional_args(name)
                if result is None:
                    msg = f"get_expected_positional_args({name}) returned None"
                    raise BridgeFuzzError(msg)
                if result != 1:
                    msg = f"get_expected_positional_args({name}) = {result}, expected 1"
                    raise BridgeFuzzError(msg)

        case 1:
            # get_expected_positional_args for unknown function
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            result = reg.get_expected_positional_args(fuzzed)
            if fuzzed not in ("NUMBER", "DATETIME", "CURRENCY") and result is not None:
                msg = f"get_expected_positional_args({fuzzed!r}) returned {result}"
                raise BridgeFuzzError(msg)

        case 2:
            # get_builtin_metadata for known builtins
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                meta = reg.get_builtin_metadata(name)
                if meta is None:
                    msg = f"get_builtin_metadata({name}) returned None"
                    raise BridgeFuzzError(msg)
                if not meta.requires_locale:
                    msg = f"Builtin {name} should require locale"
                    raise BridgeFuzzError(msg)

        case 3:
            # has_function vs __contains__ consistency
            for name in ("NUMBER", "DATETIME", "CURRENCY"):
                has = reg.has_function(name)
                contains = name in reg
                if has != contains:
                    msg = f"has_function != __contains__ for {name}"
                    raise BridgeFuzzError(msg)
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 20))
            has = reg.has_function(fuzzed)
            contains = fuzzed in reg
            if has != contains:
                msg = f"has_function != __contains__ for fuzzed {fuzzed!r}"
                raise BridgeFuzzError(msg)

        case _:
            # get_builtin_metadata for unknown function returns None
            fuzzed = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 30))
            meta = reg.get_builtin_metadata(fuzzed)
            if fuzzed not in ("NUMBER", "DATETIME", "CURRENCY") and meta is not None:
                msg = f"get_builtin_metadata({fuzzed!r}) returned non-None"
                raise BridgeFuzzError(msg)


# --- Pattern Dispatch ---

_PATTERN_DISPATCH: dict[str, Any] = {
    "register_basic": _pattern_register_basic,
    "register_signatures": _pattern_register_signatures,
    "param_mapping_custom": _pattern_param_mapping_custom,
    "signature_validation": _pattern_signature_validation,
    "fluent_number_contracts": _pattern_fluent_number_contracts,
    "signature_immutability": _pattern_signature_immutability,
    "camel_case_conversion": _pattern_camel_case_conversion,
    "call_dispatch": _pattern_call_dispatch,
    "locale_injection": _pattern_locale_injection,
    "error_wrapping": _pattern_error_wrapping,
    "evil_objects": _pattern_evil_objects,
    "dict_interface": _pattern_dict_interface,
    "freeze_copy_lifecycle": _pattern_freeze_copy_lifecycle,
    "fluent_function_decorator": _pattern_fluent_function_decorator,
    "metadata_api": _pattern_metadata_api,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz FunctionRegistry bridge machinery."""
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

    pattern_func = _PATTERN_DISPATCH[pattern]

    try:
        pattern_func(fdp)

    except BridgeFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError):
        pass  # Expected for invalid inputs

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        # Semantic interestingness: patterns exercising complex paths,
        # error paths, or wall-time > 1ms indicating unusual code path
        is_interesting = pattern in (
            "evil_objects", "signature_validation", "locale_injection",
            "metadata_api", "error_wrapping",
            "dict_interface", "signature_immutability", "register_signatures",
        ) or (time.perf_counter() - start_time) * 1000 > 1.0
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the bridge machinery fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="FunctionRegistry bridge machinery fuzzer using Atheris/libFuzzer",
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
    print("FunctionRegistry Bridge Machinery Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     runtime.function_bridge")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)} (weighted round-robin)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
