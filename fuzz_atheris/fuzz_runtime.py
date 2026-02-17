#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: runtime - End-to-End Runtime & strict mode validation
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Runtime End-to-End Fuzzer (Atheris).

Grammar-aware fuzzer targeting the full runtime stack: FluentBundle,
IntegrityCache, Resolver, and Strict Mode integrity guarantees.

Uses structured construction from fuzzed bytes so that libFuzzer mutations
map to meaningful FTL grammar variations (message structure, selector types,
function calls, term references, attribute access, nesting depth). This
enables coverage-guided exploration of resolver dispatch paths, select
expression matching, built-in function formatting, cache key construction,
cycle detection, and error recovery.

Metrics:
- Scenario coverage (strict mode, caching, integrity, security, concurrent)
- Weight skew detection (actual vs intended distribution)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Corpus retention rate and eviction tracking
- Error distribution and contract violations
- Seed corpus management

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
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
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

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- PEP 695 Type Alias ---
type ComplexArgs = dict[str, Any]


# --- Domain Metrics ---

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


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=500,
    fuzzer_name="runtime",
    fuzzer_target="FluentBundle, IntegrityCache, Resolver, Strict Mode",
)
_domain = RuntimeMetrics()


# --- Test Configuration Constants ---
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

MALICIOUS_LOCALES: Sequence[str] = (
    "x" * 10000,  # Very long
    "en" * 1000,  # Repeated
    "\x00\x01\x02" * 100,  # Control chars
    "en-US" + "\x00" * 1000,  # Null bytes
    "invalid!!",  # Invalid chars
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

# --- Grammar-Aware FTL Construction ---

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
    ("security_locale_explosion", 8),
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
    stats = build_base_stats_dict(
        _state,
        coverage_key="scenarios_tested",
        coverage_prefix="scenario_",
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
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        CacheCorruptionError,
        FormattingIntegrityError,
        WriteConflictError,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache import IntegrityCacheEntry
    from ftllexengine.runtime.cache_config import CacheConfig


# --- Grammar-Aware FTL Construction ---


def _build_expression(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
    depth: int = 0,
) -> str:
    """Build a random FTL expression from fuzzed bytes.

    Maps byte values to grammar productions so mutations are meaningful.
    High branch count mirrors FTL grammar production rules (10 expression types).
    """
    if depth > 3 or fdp.remaining_bytes() < 2:
        return fdp.PickValueInList(list(_VAR_NAMES))

    expr_type = fdp.ConsumeIntInRange(0, 9)
    match expr_type:
        case 0:
            # Variable reference
            return fdp.PickValueInList(list(_VAR_NAMES))
        case 1:
            # String literal
            return f'"{fdp.PickValueInList(list(_UNICODE_TEXTS))}"'
        case 2:
            # Number literal
            num = fdp.ConsumeIntInRange(-9999, 9999)
            if fdp.ConsumeBool():
                return str(num)
            frac = fdp.ConsumeIntInRange(0, 99)
            return f"{num}.{frac:02d}"
        case 3:
            # Message reference
            ref_id = fdp.PickValueInList(list(_IDENTIFIERS))
            if fdp.ConsumeBool():
                return f"{{ {ref_id}.title }}"
            return f"{{ {ref_id} }}"
        case 4:
            # Term reference
            term_id = fdp.PickValueInList(list(_TERM_IDENTIFIERS))
            if fdp.ConsumeBool():
                return f"{{ {term_id} }}"
            return f"{{ {term_id}.attr }}"
        case 5:
            # NUMBER() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_NUMBER_OPTS))
            return f"{{ NUMBER({var}{opts}) }}"
        case 6:
            # DATETIME() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_DATETIME_OPTS))
            return f"{{ DATETIME({var}{opts}) }}"
        case 7:
            # CURRENCY() call
            var = fdp.PickValueInList(list(_VAR_NAMES))
            opts = ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts += ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            return f"{{ CURRENCY({var}{opts}) }}"
        case 8:
            # Nested placeable
            inner = _build_expression(fdp, depth + 1)
            return f"{{ {inner} }}"
        case 9:
            # Custom function
            var = fdp.PickValueInList(list(_VAR_NAMES))
            return f'{{ FUZZ_FUNC({var}, key: "val") }}'

    return fdp.PickValueInList(list(_VAR_NAMES))


def _build_select_expression(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a select expression with plural/string keys."""
    var = fdp.PickValueInList(list(_VAR_NAMES))

    # Selector: raw var, NUMBER(), or CURRENCY()
    selector_type = fdp.ConsumeIntInRange(0, 2)
    match selector_type:
        case 0:
            selector = var
        case 1:
            opts = ""
            if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
                opts = ", " + fdp.PickValueInList(list(_NUMBER_OPTS))
            selector = f"NUMBER({var}{opts})"
        case _:
            opts = ", " + fdp.PickValueInList(list(_CURRENCY_OPTS))
            selector = f"CURRENCY({var}{opts})"

    # Build variants
    num_variants = fdp.ConsumeIntInRange(1, 5)
    variants: list[str] = []
    default_idx = fdp.ConsumeIntInRange(0, num_variants - 1)

    for i in range(num_variants):
        # Key: plural category or number literal
        if fdp.ConsumeBool():
            key = fdp.PickValueInList(list(_SELECTOR_KEYS))
        else:
            key = str(fdp.ConsumeIntInRange(0, 100))

        value = _build_expression(fdp, depth=1) if fdp.ConsumeBool() else "value"
        prefix = "*" if i == default_idx else ""
        variants.append(f"    [{prefix}{key}] {value}")

    body = "\n".join(variants)
    return f"{{ {selector} ->\n{body}\n}}"


def _build_message(fdp: atheris.FuzzedDataProvider, msg_id: str) -> str:  # noqa: PLR0912
    """Build a complete FTL message entry."""
    if fdp.remaining_bytes() < 2:
        return f"{msg_id} = fallback\n"

    msg_type = fdp.ConsumeIntInRange(0, 5)
    match msg_type:
        case 0:
            # Simple value with expressions
            parts: list[str] = []
            num_parts = fdp.ConsumeIntInRange(1, 3)
            for _ in range(num_parts):
                if fdp.ConsumeBool():
                    parts.append(_build_expression(fdp))
                else:
                    parts.append(fdp.PickValueInList(list(_UNICODE_TEXTS)))
            value = " ".join(parts)
            msg = f"{msg_id} = {value}\n"
        case 1:
            # Select expression
            sel = _build_select_expression(fdp)
            msg = f"{msg_id} =\n    {sel}\n"
        case 2:
            # Message with attributes
            value = _build_expression(fdp)
            attrs: list[str] = []
            num_attrs = fdp.ConsumeIntInRange(1, 3)
            for j in range(num_attrs):
                attr_val = _build_expression(fdp, depth=1)
                attrs.append(f"    .attr{j} = {attr_val}")
            attr_block = "\n".join(attrs)
            msg = f"{msg_id} = {value}\n{attr_block}\n"
        case 3:
            # Cyclic reference
            target = fdp.PickValueInList(list(_IDENTIFIERS))
            msg = f"{msg_id} = {{ {target} }}\n"
        case 4:
            # Reference chain
            target = fdp.PickValueInList(list(_IDENTIFIERS))
            if fdp.ConsumeBool():
                msg = f"{msg_id} = prefix {{ {target} }} suffix\n"
            else:
                msg = f"{msg_id} = {{ {target}.title }}\n"
        case _:
            # Deep nesting
            nesting = fdp.ConsumeIntInRange(1, 8)
            expr = fdp.PickValueInList(list(_VAR_NAMES))
            for _ in range(nesting):
                expr = f"{{ {expr} }}"
            msg = f"{msg_id} = {expr}\n"

    # Optionally add attributes even to non-attribute messages
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 2:
        msg = msg.rstrip("\n") + f"\n    .title = {_build_expression(fdp)}\n"

    return msg


def _build_term(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a term definition."""
    term_id = fdp.PickValueInList(list(_TERM_IDENTIFIERS))

    if fdp.ConsumeBool():
        # Term with select
        sel = _build_select_expression(fdp)
        term = f"{term_id} =\n    {sel}\n"
    else:
        value = _build_expression(fdp)
        term = f"{term_id} = {value}\n"

    # Optional attributes
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 1:
        attr_val = _build_expression(fdp, depth=1)
        term = term.rstrip("\n") + f"\n    .attr = {attr_val}\n"

    return term


def _build_ftl_resource(fdp: atheris.FuzzedDataProvider) -> str:
    """Build a complete FTL resource from fuzzed bytes.

    Grammar-aware: each byte decision maps to a structural choice in the FTL
    grammar, so libFuzzer coverage feedback drives exploration of new resolver
    code paths rather than random noise.
    """
    parts: list[str] = []

    # Always include some terms for term references to resolve
    num_terms = fdp.ConsumeIntInRange(0, 3)
    for _ in range(num_terms):
        if fdp.remaining_bytes() < 2:
            break
        parts.append(_build_term(fdp))

    # Build messages - use deterministic IDs so TARGET_MESSAGE_IDS can find them
    ids_to_build = list(_IDENTIFIERS)
    num_messages = fdp.ConsumeIntInRange(2, min(8, len(ids_to_build)))
    for i in range(num_messages):
        if fdp.remaining_bytes() < 2:
            break
        parts.append(_build_message(fdp, ids_to_build[i]))

    return "\n".join(parts)


def _generate_complex_args(fdp: atheris.FuzzedDataProvider) -> ComplexArgs:
    """Generate fuzzed arguments matching grammar variable names.

    Uses the same variable names as _build_expression so that constructed
    FTL messages can resolve their variable references.
    """
    # Always provide the core variables so resolution paths are exercised
    arg_keys = ("var", "name", "count", "amount", "date", "var_0", "var_1", "var_2", "var_3")

    args: ComplexArgs = {}
    for key in arg_keys:
        if fdp.remaining_bytes() < 2:
            # Provide defaults for remaining keys
            args[key] = 42
            continue

        val_type = fdp.ConsumeIntInRange(0, 9)
        match val_type:
            case 0:
                args[key] = fdp.ConsumeUnicodeNoSurrogates(20)
            case 1:
                args[key] = fdp.ConsumeFloat()
            case 2:
                args[key] = fdp.ConsumeInt(4)
            case 3:
                args[key] = datetime.now(tz=UTC)
            case 4:
                args[key] = [fdp.ConsumeUnicodeNoSurrogates(5) for _ in range(3)]
            case 5:
                args[key] = {"nested": fdp.ConsumeInt(2)}
            case 6:
                args[key] = fdp.ConsumeBool()
            case 7:
                # Numeric edge cases for NUMBER/CURRENCY selectors
                args[key] = fdp.PickValueInList([0, 1, 2, 3, 5, 10, 100, 1000000])
            case 8:
                # Float edge cases
                args[key] = fdp.PickValueInList(
                    [0.0, -0.0, 1.5, float("inf"), float("-inf"), float("nan")]
                )
            case 9:
                # Decimal-like for precision testing
                args[key] = fdp.ConsumeIntInRange(-99999, 99999) / 100

    return args


def _fuzzed_function(args: list[Any], kwargs: dict[str, Any]) -> str:
    """Mock custom function for FunctionRegistry testing."""
    return f"PROCESSED_{len(args)}_{len(kwargs)}"


def _add_random_resources(fdp: atheris.FuzzedDataProvider, bundle: FluentBundle) -> None:
    """Add grammar-aware FTL resources to bundle.

    Constructs structurally valid FTL from fuzzed bytes so that libFuzzer
    mutations map to meaningful grammar variations rather than random noise.
    """
    ftl = _build_ftl_resource(fdp)

    with contextlib.suppress(Exception):
        bundle.add_resource(ftl)

    # Optionally add a second resource (tests message dedup / last-wins behavior)
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 4:
        ftl2 = _build_ftl_resource(fdp)
        with contextlib.suppress(Exception):
            bundle.add_resource(ftl2)


def _execute_runtime_invariants(  # noqa: PLR0912, PLR0915
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
    strict: bool,
    enable_cache: bool,
    cache_write_once: bool,
) -> None:
    """Verify core runtime invariants across operations."""
    target_ids = list(TARGET_MESSAGE_IDS)
    fdp_sample = fdp.ConsumeIntInRange(3, len(target_ids))
    sampled_ids = target_ids[:fdp_sample]

    for msg_id in sampled_ids:
        attribute = fdp.PickValueInList([None, "title", "nonexistent"])
        try:
            # Primary formatting
            res1, err1 = bundle.format_pattern(msg_id, args, attribute=attribute)

            # INVARIANT: Strict Mode Integrity
            if strict and len(err1) > 0:
                _domain.strict_mode_tests += 1
                msg = f"Strict mode breach: {len(err1)} errors for '{msg_id}'."
                raise RuntimeIntegrityError(msg)

            # INVARIANT: Frozen Error Integrity
            for e in err1:
                _domain.frozen_error_verifications += 1
                if not e.verify_integrity():
                    msg = "FrozenFluentError checksum verification failed."
                    raise RuntimeIntegrityError(msg)

            # INVARIANT: Cache Stability
            if enable_cache and bundle._cache is not None:
                _domain.cache_operations += 1
                res2, err2 = bundle.format_pattern(msg_id, args, attribute=attribute)
                _domain.cache_stability_checks += 1

                if res1 != res2 or len(err1) != len(err2):
                    msg = f"Cache stability breach: non-deterministic result for '{msg_id}'."
                    raise RuntimeIntegrityError(msg)

                # Corruption simulation (5% chance)
                if fdp.ConsumeProbability() < 0.05:
                    _domain.corruption_simulations += 1
                    _simulate_corruption(bundle)
                    try:
                        bundle.format_pattern(msg_id, args, attribute=attribute)
                    except CacheCorruptionError as exc:
                        if not strict:
                            msg = "Non-strict cache raised CacheCorruptionError."
                            raise RuntimeIntegrityError(msg) from exc
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        is_corruption = "corruption" in str(e).lower()
                        if is_corruption and not isinstance(e, CacheCorruptionError):
                            msg = f"Wrong exception type for corruption: {type(e)}"
                            raise RuntimeIntegrityError(msg) from e

        except FormattingIntegrityError as e:
            _domain.integrity_checks += 1
            if not strict:
                msg = "Non-strict bundle raised FormattingIntegrityError."
                raise RuntimeIntegrityError(msg) from e
            if not e.fluent_errors:
                msg = "FormattingIntegrityError empty."
                raise RuntimeIntegrityError(msg) from e

        except WriteConflictError as e:
            if not cache_write_once:
                msg = "WriteConflictError raised when write_once=False."
                raise RuntimeIntegrityError(msg) from e

        except (RecursionError, MemoryError, FrozenFluentError):
            # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED as a safety
            # mechanism regardless of strict mode to prevent stack overflow
            pass


def _simulate_corruption(bundle: FluentBundle) -> None:
    """Simulate cache corruption for integrity testing."""
    if bundle._cache is None:
        return
    with bundle._cache._lock:
        if not bundle._cache._cache:
            return
        key = next(iter(bundle._cache._cache))
        entry = bundle._cache._cache[key]

        corrupted = IntegrityCacheEntry(
            formatted=entry.formatted + "CORRUPTION",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        bundle._cache._cache[key] = corrupted


def _perform_security_fuzzing(fdp: atheris.FuzzedDataProvider) -> str:
    """Perform security fuzzing with attack vectors."""
    _domain.security_tests += 1

    attack_idx = fdp.ConsumeIntInRange(0, len(_SECURITY_SCHEDULE) - 1)
    attack = _SECURITY_SCHEDULE[attack_idx]

    match attack:
        case "security_recursion":
            _test_deep_recursion(fdp)
        case "security_memory":
            _test_memory_exhaustion(fdp)
        case "security_cache_poison":
            _test_cache_poisoning(fdp)
        case "security_function_inject":
            _test_function_injection(fdp)
        case "security_locale_explosion":
            _test_locale_explosion(fdp)
        case "security_expansion_budget":
            _test_expansion_budget(fdp)
        case "security_dag_expansion":
            _test_dag_expansion(fdp)
        case "security_dict_functions":
            _test_dict_functions(fdp)

    return attack


def _test_deep_recursion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test deep recursion via nested placeables and cyclic references."""
    attack_type = fdp.ConsumeIntInRange(0, 2)
    try:
        bundle = FluentBundle("en", strict=False)
        match attack_type:
            case 0:
                # Deep nested placeables
                depth = fdp.ConsumeIntInRange(50, 200)
                ftl = "msg = " + "{ " * depth + "$var" + " }" * depth + "\n"
                bundle.add_resource(ftl)
            case 1:
                # Cyclic reference chain
                chain_len = fdp.ConsumeIntInRange(2, 20)
                parts = []
                for i in range(chain_len):
                    next_id = f"c{(i + 1) % chain_len}"
                    parts.append(f"c{i} = {{ {next_id} }}\n")
                bundle.add_resource("\n".join(parts))
            case _:
                # Self-referencing term with select
                ftl = "-self = { -self ->\n    *[other] { -self }\n}\nmsg = { -self }\n"
                bundle.add_resource(ftl)
        bundle.format_pattern("msg" if attack_type == 0 else "c0", {"var": "test"})
    except (RecursionError, MemoryError, ValueError, FrozenFluentError):
        # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED regardless of strict mode
        pass


def _test_memory_exhaustion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test memory exhaustion via large values and many variants."""
    attack_type = fdp.ConsumeIntInRange(0, 2)
    try:
        bundle = FluentBundle("en", strict=False)
        match attack_type:
            case 0:
                # Large string value
                size = fdp.ConsumeIntInRange(10000, 100000)
                bundle.add_resource(f"msg = {'x' * size}\n")
            case 1:
                # Many variants in select
                n = fdp.ConsumeIntInRange(50, 200)
                variants = "\n".join(f"    [{'*' if i == 0 else ''}v{i}] val{i}" for i in range(n))
                bundle.add_resource(f"msg = {{ $var ->\n{variants}\n}}\n")
            case _:
                # Many attributes
                n = fdp.ConsumeIntInRange(50, 200)
                attrs = "\n".join(f"    .a{i} = val{i}" for i in range(n))
                bundle.add_resource(f"msg = val\n{attrs}\n")
        bundle.format_pattern("msg", {"var": "test"})
    except (MemoryError, ValueError, FrozenFluentError):
        pass


def _test_cache_poisoning(fdp: atheris.FuzzedDataProvider) -> None:
    """Test cache poisoning attack."""
    try:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = Hello { $name }\n")

        malicious_args = [
            {"name": float("inf")},
            {"name": float("-inf")},
            {"name": float("nan")},
            {"name": None},
            {"name": []},
        ]

        for args in malicious_args[: fdp.ConsumeIntInRange(1, len(malicious_args))]:
            with contextlib.suppress(Exception):
                bundle.format_pattern("msg", args)  # type: ignore[arg-type]

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _test_function_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Test function injection and recursive custom function attacks.

    Two sub-patterns:
    0 - No-op custom function (baseline injection)
    1 - Recursive custom function that calls back into bundle.format_pattern(),
        testing GlobalDepthGuard cross-context recursion protection
    """
    attack_variant = fdp.ConsumeIntInRange(0, 1)
    try:
        bundle = FluentBundle("en", strict=False)

        if attack_variant == 0:
            # Baseline: no-op custom function
            def noop_func(*_args: Any, **_kwargs: Any) -> str:
                return "safe_output"

            bundle.add_function("INJECT", noop_func)
            bundle.add_resource("msg = { INJECT() }\n")
            bundle.format_pattern("msg", {})
        else:
            # Recursive: custom function calls back into format_pattern,
            # exercising GlobalDepthGuard across function boundaries
            call_depth = fdp.ConsumeIntInRange(1, 10)
            counter = {"n": 0}

            def recursive_func(*_args: Any, **_kwargs: Any) -> str:
                counter["n"] += 1
                if counter["n"] < call_depth:
                    result, _ = bundle.format_pattern("recurse", {})
                    return str(result)
                return "base"

            bundle.add_function("RECURSE_FN", recursive_func)
            bundle.add_resource("recurse = { RECURSE_FN() }\nmsg = { RECURSE_FN() }\n")
            bundle.format_pattern("msg", {})

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _test_locale_explosion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test locale explosion attack."""
    locale = fdp.PickValueInList(list(MALICIOUS_LOCALES))

    try:
        bundle = FluentBundle(locale, strict=False)
        bundle.add_resource("msg = test\n")
        bundle.format_pattern("msg", {})
    except (ValueError, TypeError):
        pass


def _test_expansion_budget(fdp: atheris.FuzzedDataProvider) -> None:
    """Test Billion Laughs expansion budget.

    Constructs exponentially expanding message references:
    m0={m1}{m1}, m1={m2}{m2}, ... so small FTL produces huge output.
    The expansion budget (max_expansion_size) should halt resolution.
    """
    depth = fdp.ConsumeIntInRange(5, 20)
    # Use both default and small budgets to exercise the guard path
    budget = fdp.PickValueInList([100, 1000, 10000, None])
    try:
        kwargs: dict[str, Any] = {"strict": False}
        if budget is not None:
            kwargs["max_expansion_size"] = budget
        bundle = FluentBundle("en", **kwargs)
        parts = []
        for i in range(depth):
            parts.append(f"m{i} = {{ m{i + 1} }}{{ m{i + 1} }}\n")
        parts.append(f"m{depth} = payload\n")
        bundle.add_resource("\n".join(parts))
        bundle.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass


def _test_dag_expansion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test _make_hashable DAG expansion DoS.

    Constructs deeply shared references as cache args to stress the
    node budget in IntegrityCache._make_hashable().
    """
    try:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = Hello { $name }\n")

        # Build DAG: l = [l, l] repeated N times.
        # Cap at 20: depth 20 creates 2^20 logical nodes which is sufficient
        # to trigger _make_hashable node budget (10,000). Higher depths cause
        # exponential str() expansion in the resolver (2^30 = 1B nodes).
        depth = fdp.ConsumeIntInRange(10, 20)
        dag: list[Any] = ["leaf"]
        for _ in range(depth):
            dag = [dag, dag]

        with contextlib.suppress(Exception):
            bundle.format_pattern("msg", {"name": dag})  # type: ignore[arg-type]

        # Lock must still be usable after DAG rejection
        with contextlib.suppress(Exception):
            bundle.format_pattern("msg", {"name": "safe"})

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _test_dict_functions(_fdp: atheris.FuzzedDataProvider) -> None:
    """Test FluentBundle rejects dict as functions parameter.

    Passing a raw dict should raise TypeError at construction time.
    """
    try:
        FluentBundle("en", functions={"NUMBER": lambda *_a, **_k: "x"})  # type: ignore[arg-type]
        # If we get here, the guard didn't fire -- that's a finding
        msg = "FluentBundle accepted dict as functions parameter"
        raise RuntimeIntegrityError(msg)
    except TypeError:
        pass  # Expected
    except RuntimeIntegrityError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _perform_differential_testing(
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
) -> None:
    """Differential testing: same FTL, different configs must not crash differently."""
    _domain.differential_tests += 1

    alt_locale = fdp.PickValueInList(["en-US", "de-DE", "ar-EG", "ja-JP", "C", ""])
    alt_strict = not bundle.strict if fdp.ConsumeBool() else bundle.strict
    alt_cache = not bundle.cache_enabled if fdp.ConsumeBool() else bundle.cache_enabled

    try:
        alt_bundle = FluentBundle(
            alt_locale,
            strict=alt_strict,
            cache=CacheConfig() if alt_cache else None,
        )

        # Copy functions
        for name in bundle._function_registry:
            func = bundle._function_registry.get_callable(name)
            if func:
                alt_bundle.add_function(name, func)

        # Same FTL resource
        ftl = _build_ftl_resource(fdp)
        with contextlib.suppress(Exception):
            alt_bundle.add_resource(ftl)

        # Format all reachable messages
        for msg_id in TARGET_MESSAGE_IDS[:8]:
            with contextlib.suppress(Exception):
                alt_bundle.format_pattern(msg_id, args)

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _run_concurrent_test(
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
    strict: bool,
    enable_cache: bool,
    cache_write_once: bool,
) -> None:
    """Run concurrent execution test."""
    _domain.concurrent_tests += 1

    barrier = threading.Barrier(2)

    def worker() -> None:
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=1.0)
        try:
            _execute_runtime_invariants(fdp, bundle, args, strict, enable_cache, cache_write_once)
        except CacheCorruptionError:
            # Expected from corruption simulation in strict mode
            pass
        except (RecursionError, MemoryError, FrozenFluentError):
            # FrozenFluentError: depth guard (MAX_DEPTH_EXCEEDED)
            pass

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
        if t.is_alive():
            msg = "RWLock deadlock detected."
            raise RuntimeIntegrityError(msg)


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: Test runtime invariants and contracts."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    scenario = select_pattern_round_robin(_state, _SCENARIO_SCHEDULE)
    _state.pattern_coverage[scenario] = _state.pattern_coverage.get(scenario, 0) + 1

    if fdp.remaining_bytes() < 2:
        return

    # Security fuzzing (separate path)
    if scenario == "security":
        security_scenario = _perform_security_fuzzing(fdp)
        _state.pattern_coverage[security_scenario] = (
            _state.pattern_coverage.get(security_scenario, 0) + 1
        )
        record_iteration_metrics(_state, scenario, start_time, data, is_interesting=True)
        return

    # Configuration
    strict = scenario == "strict_mode" or fdp.ConsumeBool()
    enable_cache = scenario == "caching" or fdp.ConsumeBool()
    use_isolating = fdp.ConsumeBool()
    cache_write_once = fdp.ConsumeBool()

    # Locale selection
    locale = fdp.PickValueInList(list(TEST_LOCALES))

    try:
        try:
            cache_cfg = CacheConfig(write_once=cache_write_once) if enable_cache else None
            bundle = FluentBundle(
                locale,
                strict=strict,
                cache=cache_cfg,
                use_isolating=use_isolating,
            )
            if fdp.ConsumeBool():
                bundle.add_function("FUZZ_FUNC", _fuzzed_function)
        except (ValueError, TypeError):
            return

        # Add resources
        _add_random_resources(fdp, bundle)

        # Generate args
        args = _generate_complex_args(fdp)

        if strict:
            _domain.strict_mode_tests += 1

        # Execute based on scenario
        if scenario == "concurrent":
            _run_concurrent_test(fdp, bundle, args, strict, enable_cache, cache_write_once)
        elif scenario == "differential":
            _perform_differential_testing(fdp, bundle, args)
        else:
            _execute_runtime_invariants(fdp, bundle, args, strict, enable_cache, cache_write_once)

    except CacheCorruptionError:
        if strict:
            return  # Expected
        _state.findings += 1
        raise

    except RuntimeIntegrityError:
        _state.findings += 1
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = "security" in scenario or "integrity" in scenario or (
            (time.perf_counter() - start_time) * 1000 > 50.0
        )
        record_iteration_metrics(
            _state, scenario, start_time, data, is_interesting=is_interesting,
        )

        # Break reference cycles in AST/error objects to prevent RSS growth
        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the runtime fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Runtime end-to-end fuzzer using Atheris/libFuzzer",
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
        default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=2000,
        help="Python recursion limit (default: 2000)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.setrecursionlimit(args.recursion_limit)

    # Inject -rss_limit_mb default if not already specified.
    # AST reference cycles can accumulate between gc passes; 4096 MB provides
    # headroom while still catching true leaks before system OOM-kill.
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Runtime End-to-End Fuzzer (Atheris)",
        target="FluentBundle, IntegrityCache, Resolver, Strict Mode",
        state=_state,
        schedule_len=len(_SCENARIO_SCHEDULE),
        extra_lines=[f"Recursion:  {args.recursion_limit} limit"],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
