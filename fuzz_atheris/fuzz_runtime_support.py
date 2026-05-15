"""Shared state, imports, and constants for the runtime Atheris fuzzer."""

from __future__ import annotations

import argparse
import atexit
import contextlib
import gc
import logging
import pathlib
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:
    import psutil as _psutil_import
except ImportError:
    pass
else:
    _psutil_mod = _psutil_import

try:
    import atheris as _atheris_import
except ImportError:
    pass
else:
    _atheris_mod = _atheris_import

from fuzz_common import (  # noqa: E402 - after dependency capture  # pylint: disable=C0413
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

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

atheris = cast("Any", _atheris_mod)

type ComplexArgs = dict[str, Any]

@dataclass
class RuntimeMetrics:
    """Domain-specific metrics for runtime fuzzer."""

    strict_mode_tests: int = 0
    cache_operations: int = 0
    integrity_checks: int = 0
    security_tests: int = 0
    concurrent_tests: int = 0
    differential_tests: int = 0

    # Contract validation
    frozen_error_verifications: int = 0
    cache_stability_checks: int = 0
    corruption_simulations: int = 0
    ast_lookup_checks: int = 0
    locale_boundary_checks: int = 0

_state = BaseFuzzerState(
    seed_corpus_max_size=500,
    fuzzer_name="runtime",
    fuzzer_target="FluentBundle, IntegrityCache, Resolver, Strict Mode, Locale Boundary",
)
_domain = RuntimeMetrics()

TEST_LOCALES: Sequence[str] = (
    "en-US",
    "en-GB",
    "lv-LV",
    "ar-EG",
    "ar-SA",
    "pl-PL",
    "zh-CN",
    "ja-JP",
    "de-DE",
    "fr-FR",
    "",  # Empty locale
    "C",  # POSIX
    "root",  # CLDR root
)

_STRUCTURALLY_INVALID_LOCALES: Sequence[str] = (
    "en/US",
    "en US",
    "en@US",
    "123_US",
    "\x00\x01\x02",
    "en-US" + "\x00" * 8,
    "invalid!!",
)

_NON_STRING_LOCALES: Sequence[object] = (
    None,
    0,
    1.5,
    ["en-US"],
    {"locale": "en-US"},
)

TARGET_MESSAGE_IDS: Sequence[str] = (
    "msg",
    "msg2",
    "msg3",
    "ref",
    "tref",
    "attr",
    "cyclic",
    "deep",
    "func_call",
    "num_sel",
    "str_sel",
    "nested",
    "chain_a",
    "chain_b",
    "chain_c",
    "nonexistent",
)
_IDENTIFIERS: Sequence[str] = (
    "msg",
    "msg2",
    "msg3",
    "ref",
    "tref",
    "attr",
    "func_call",
    "num_sel",
    "str_sel",
    "nested",
    "chain_a",
    "chain_b",
    "chain_c",
    "deep",
)

_TERM_IDENTIFIERS: Sequence[str] = (
    "-brand",
    "-term",
    "-os",
    "-platform",
    "-greeting",
)
_TERM_QUERY_IDS: Sequence[str] = tuple(
    term.removeprefix("-") for term in _TERM_IDENTIFIERS
)

_VAR_NAMES: Sequence[str] = (
    "$var",
    "$name",
    "$count",
    "$amount",
    "$date",
    "$var_0",
    "$var_1",
    "$var_2",
    "$var_3",
)

_BUILTIN_FUNCTIONS: Sequence[str] = (
    "NUMBER",
    "DATETIME",
    "CURRENCY",
)

_NUMBER_OPTS: Sequence[str] = (
    "minimumFractionDigits: 0",
    "minimumFractionDigits: 2",
    "maximumFractionDigits: 0",
    "maximumFractionDigits: 5",
    'useGrouping: "true"',
    'useGrouping: "false"',
)

_DATETIME_OPTS: Sequence[str] = (
    'dateStyle: "short"',
    'dateStyle: "medium"',
    'dateStyle: "long"',
    'dateStyle: "full"',
    'timeStyle: "short"',
    'timeStyle: "long"',
)

_CURRENCY_OPTS: Sequence[str] = (
    'currency: "USD"',
    'currency: "EUR"',
    'currency: "JPY"',
    'currency: "BHD"',
    'currencyDisplay: "symbol"',
    'currencyDisplay: "code"',
    'currencyDisplay: "name"',
)

_SELECTOR_KEYS: Sequence[str] = (
    "one",
    "two",
    "few",
    "many",
    "other",
    "zero",
)

_UNICODE_TEXTS: Sequence[str] = (
    "Hello",
    "© ® ™",
    "😀 🌟 🚀",
    "مرحبا عالم",
    "c\u0308a\u0308f\u0308e\u0308",
    "\u200b\u200e\u200f",
    "边界条件",
    "",
)


# Scenario weights: (name, weight)
_SCENARIO_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("core_runtime", 40),
    ("strict_mode", 20),
    ("caching", 15),
    ("security", 10),
    ("concurrent", 10),
    ("differential", 5),
)

_SCENARIO_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _SCENARIO_WEIGHTS],
    [weight for _, weight in _SCENARIO_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _SCENARIO_WEIGHTS}

# Security attack sub-schedule
_SECURITY_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("security_recursion", 25),
    ("security_memory", 20),
    ("security_cache_poison", 15),
    ("security_function_inject", 12),
    ("security_locale_boundary", 8),
    ("security_expansion_budget", 8),
    ("security_dag_expansion", 7),
    ("security_dict_functions", 5),
)

_SECURITY_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _SECURITY_WEIGHTS],
    [weight for _, weight in _SECURITY_WEIGHTS],
)


class RuntimeIntegrityError(Exception):
    """Raised when a runtime invariant is breached."""


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "runtime"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = cast(
        "dict[str, Any]",
        build_base_stats_dict(
            _state,
            coverage_key="scenarios_tested",
            coverage_prefix="scenario_",
        ),
    )

    # Domain-specific metrics
    stats["strict_mode_tests"] = _domain.strict_mode_tests
    stats["cache_operations"] = _domain.cache_operations
    stats["integrity_checks"] = _domain.integrity_checks
    stats["security_tests"] = _domain.security_tests
    stats["concurrent_tests"] = _domain.concurrent_tests
    stats["differential_tests"] = _domain.differential_tests

    # Contract validation metrics
    stats["frozen_error_verifications"] = _domain.frozen_error_verifications
    stats["cache_stability_checks"] = _domain.cache_stability_checks
    stats["corruption_simulations"] = _domain.corruption_simulations
    stats["ast_lookup_checks"] = _domain.ast_lookup_checks
    stats["locale_boundary_checks"] = _domain.locale_boundary_checks

    return stats


_REPORT_FILENAME = "fuzz_runtime_report.json"


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

# Enable string and regex comparison instrumentation for better coverage
# of message ID lookups, selector key matching, and pattern-based parsing
atheris.enabled_hooks.add("str")
atheris.enabled_hooks.add("RegEx")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine import validate_message_variables
    from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT
    from ftllexengine.core.locale_utils import require_locale_code
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        CacheCorruptionError,
        CacheKeySerializationError,
        FormattingIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache import IntegrityCacheEntry
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.syntax import Message, Term


__all__ = [
    "GC_INTERVAL",
    "MAX_LOCALE_LENGTH_HARD_LIMIT",
    "TARGET_MESSAGE_IDS",
    "TEST_LOCALES",
    "UTC",
    "_CURRENCY_OPTS",
    "_DATETIME_OPTS",
    "_IDENTIFIERS",
    "_NON_STRING_LOCALES",
    "_NUMBER_OPTS",
    "_SCENARIO_SCHEDULE",
    "_SECURITY_SCHEDULE",
    "_SELECTOR_KEYS",
    "_STRUCTURALLY_INVALID_LOCALES",
    "_TERM_IDENTIFIERS",
    "_TERM_QUERY_IDS",
    "_UNICODE_TEXTS",
    "_VAR_NAMES",
    "Any",
    "CacheConfig",
    "CacheCorruptionError",
    "CacheKeySerializationError",
    "ComplexArgs",
    "FluentBundle",
    "FormattingIntegrityError",
    "FrozenFluentError",
    "IntegrityCacheEntry",
    "Message",
    "RuntimeIntegrityError",
    "Term",
    "WriteConflictError",
    "_domain",
    "_emit_checkpoint",
    "_state",
    "argparse",
    "atheris",
    "contextlib",
    "datetime",
    "gc",
    "get_process",
    "print_fuzzer_banner",
    "record_iteration_metrics",
    "record_memory",
    "require_locale_code",
    "run_fuzzer",
    "select_pattern_round_robin",
    "sys",
    "threading",
    "time",
    "validate_message_variables",
]
