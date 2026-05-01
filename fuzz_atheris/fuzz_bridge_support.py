#!/usr/bin/env python3
"""FunctionRegistry Bridge Machinery Fuzzer (Atheris).

Targets: ftllexengine.runtime.function_bridge, ftllexengine.core.value_types
(FunctionRegistry, FunctionSignature, FluentNumber, make_fluent_number,
fluent_function decorator, parameter mapping, locale injection)

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
- make_fluent_number() visible-precision inference and typed construction
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

import atexit
import logging
import pathlib
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
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
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
    make_fluent_number_checks: int = 0

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

_state = BaseFuzzerState(
    fuzzer_name="bridge",
    fuzzer_target="FunctionRegistry, FunctionSignature, FluentNumber, make_fluent_number",
)
_domain = BridgeMetrics()

# Pattern weights: (name, weight)
# 16 patterns across 4 categories:
# REGISTRATION (4): register_basic, register_signatures, param_mapping_custom,
#                    signature_validation
# CONTRACTS (4): fluent_number_contracts, make_fluent_number_api,
#                signature_immutability, camel_case_conversion
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
    ("make_fluent_number_api", 10),
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
    ValueError,
    TypeError,
    OverflowError,
    ArithmeticError,
    RecursionError,
    RuntimeError,
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
    stats["make_fluent_number_checks"] = _domain.make_fluent_number_checks

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


_REPORT_FILENAME = "fuzz_bridge_report.json"


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state,
        stats,
        _REPORT_DIR,
        _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.core.value_types import make_fluent_number
    from ftllexengine.runtime.function_bridge import (
        FluentNumber,
    )


# --- Constants ---

_LOCALES: Sequence[str] = (
    "en",
    "en_US",
    "de",
    "de_DE",
    "ar",
    "ar_SA",
    "ja",
    "ja_JP",
    "fr",
    "fr_FR",
    "ru",
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


def _group_ascii_thousands(value: int) -> str:
    """Render an integer with ASCII comma grouping."""
    digits = str(abs(value))
    groups: list[str] = []
    while digits:
        groups.append(digits[-3:])
        digits = digits[:-3]
    grouped = ",".join(reversed(groups))
    return f"-{grouped}" if value < 0 else grouped


def _call_make_fluent_number(
    value: int | Decimal,
    *,
    formatted: str | None = None,
) -> FluentNumber:
    """Call make_fluent_number and fail hard on unexpected valid-input errors."""
    try:
        return make_fluent_number(value, formatted=formatted)
    except (TypeError, ValueError) as err:
        msg = (
            "make_fluent_number unexpectedly rejected a valid contract input: "
            f"value={value!r}, formatted={formatted!r}, error={err}"
        )
        raise BridgeFuzzError(msg) from err

__all__ = [name for name in globals() if not name.startswith("__")]
