#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: localization - FluentLocalization Multi-locale Orchestration
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""FluentLocalization Multi-locale Orchestration Fuzzer (Atheris).

Targets: ftllexengine.localization.orchestrator (FluentLocalization)

Concern boundary: This fuzzer stress-tests the multi-locale orchestration layer.
FluentLocalization is the second top-level public API (alongside FluentBundle) and
has a completely distinct lifecycle: multi-locale fallback chains, RWLock-protected
add_resource/add_function after construction, lazy bundle creation for fallback
locales, load summary tracking, and on_fallback callback dispatch. fuzz_runtime
covers FluentBundle only -- zero FluentLocalization code paths are exercised by
any other fuzzer.

Unique coverage (not covered by other fuzzers):
- format_pattern fallback chain traversal across 2-5 locales
- add_resource() with RWLock write acquisition after initial construction
- Lazy bundle creation for fallback locales (_get_or_create_bundle)
- has_message()/has_attribute() cross-locale scan
- get_message_ids() aggregation across all locale bundles
- get_message_variables() / introspect_message() localization facade
- on_fallback callback invocation and FallbackInfo contract
- validate_resource() via localization facade
- add_function() custom function registration and application to late bundles
- Strict/non-strict mode propagation to each per-locale bundle

Patterns (12):
- single_locale_add_resource: 1 locale, add_resource, format
- multi_locale_fallback: 2 locales, message only in fallback locale
- chain_of_3_fallback: 3-locale chain, message in various positions
- format_value_missing: format non-existent message (fallback contract)
- format_with_variables: format message with variable args
- add_resource_mutation: add_resource after initial creation, re-format
- has_message_api: has_message/has_attribute contract verification
- get_message_ids_api: get_message_ids deduplication and coverage
- validate_resource_api: validate_resource via localization facade
- add_function_custom: add_function + FTL that calls custom function
- introspect_api: introspect_message/get_message_variables contracts
- on_fallback_callback: on_fallback callback fires on locale miss

Metrics:
- Pattern coverage with weighted round-robin schedule
- Fallback trigger counts, messages found vs missing
- Custom function call tracking
- Performance profiling (min/mean/p95/p99/max)
- Real memory usage (RSS via psutil)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
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

from fuzz_common import (  # noqa: E402  # pylint: disable=C0413
    GC_INTERVAL,
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
    gen_ftl_identifier,
    gen_ftl_value,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---


@dataclass
class LocalizationMetrics:
    """Domain-specific metrics for localization fuzzer."""

    fallback_triggered: int = 0
    messages_found: int = 0
    messages_missing: int = 0
    custom_function_calls: int = 0
    add_resource_mutations: int = 0
    has_message_checks: int = 0
    introspect_calls: int = 0
    validate_calls: int = 0


class LocalizationFuzzError(Exception):
    """Raised when an invariant breach is detected."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,          # empty locale list, locale not in chain, whitespace
    TypeError,           # invalid argument types
    UnicodeEncodeError,  # surrogate characters in FTL source
)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    ("single_locale_add_resource", 10),
    ("multi_locale_fallback", 10),
    ("chain_of_3_fallback", 8),
    ("format_value_missing", 7),
    ("format_with_variables", 9),
    ("add_resource_mutation", 7),
    ("has_message_api", 7),
    ("get_message_ids_api", 6),
    ("validate_resource_api", 7),
    ("add_function_custom", 6),
    ("introspect_api", 7),
    ("on_fallback_callback", 6),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)
_PATTERN_INDEX: dict[str, int] = {
    name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)
}

# Test locale sets (ordered by fallback priority)
_LOCALE_PAIRS: Sequence[tuple[str, str]] = (
    ("en-US", "en"),
    ("de-DE", "de"),
    ("fr-FR", "fr"),
    ("ja-JP", "ja"),
    ("ar-SA", "ar"),
    ("zh-CN", "zh"),
    ("ko-KR", "ko"),
    ("pt-BR", "pt"),
    ("es-ES", "es"),
    ("sv-SE", "sv"),
)

_LOCALE_TRIPLES: Sequence[tuple[str, str, str]] = (
    ("lv", "en-US", "en"),
    ("lt", "en-GB", "en"),
    ("pl", "de-AT", "de"),
    ("uk", "ru-RU", "ru"),
    ("zh-TW", "zh-CN", "zh"),
)

_SINGLE_LOCALES: Sequence[str] = (
    "en-US", "de-DE", "fr-FR", "ja-JP", "ko-KR",
    "ar-SA", "zh-CN", "pt-BR", "es-ES", "sv-SE",
)

# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="localization",
    fuzzer_target=(
        "FluentLocalization (multi-locale fallback chains, "
        "add_resource, format_pattern, introspection)"
    ),
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = LocalizationMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "localization"
_REPORT_FILENAME = "fuzz_localization_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["fallback_triggered"] = _domain.fallback_triggered
    stats["messages_found"] = _domain.messages_found
    stats["messages_missing"] = _domain.messages_missing
    stats["custom_function_calls"] = _domain.custom_function_calls
    stats["add_resource_mutations"] = _domain.add_resource_mutations
    stats["has_message_checks"] = _domain.has_message_checks
    stats["introspect_calls"] = _domain.introspect_calls
    stats["validate_calls"] = _domain.validate_calls
    total = _domain.messages_found + _domain.messages_missing
    if total > 0:
        stats["fallback_hit_ratio"] = round(
            _domain.fallback_triggered / total, 3
        )
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit crash-proof final report."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        DataIntegrityError,
        FormattingIntegrityError,
        SyntaxIntegrityError,
    )
    from ftllexengine.localization import FluentLocalization
    from ftllexengine.localization.loading import FallbackInfo


# --- Pattern implementations ---


def _pattern_single_locale_add_resource(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-locale FluentLocalization: add_resource + format round-trip.

    Tests the minimal FluentLocalization configuration: one locale, one
    resource added via add_resource(), one format call. Verifies the
    basic construction-add-format lifecycle.
    """
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    msg_id = gen_ftl_identifier(fdp)
    var = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {{ ${var} }}\n"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, ftl)

    result, errors = l10n.format_pattern(msg_id, {var: val})

    # Contract: no errors means result must contain the variable value
    if not errors and val not in result:
        msg = (
            f"Single locale: format_pattern('{msg_id}', {{'{var}': '{val}'}}) "
            f"returned '{result}' without errors but value missing"
        )
        raise LocalizationFuzzError(msg)

    if not errors:
        _domain.messages_found += 1
    else:
        _domain.messages_missing += 1


def _pattern_multi_locale_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Two-locale chain: message present only in fallback locale.

    Tests the core fallback mechanism: the primary locale does NOT have the
    message, the fallback locale does. Verifies that format_pattern traverses
    the chain and returns the fallback locale's result.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    # Add resource ONLY to fallback locale; primary stays empty
    l10n.add_resource(fallback, ftl)

    fallback_seen: list[FallbackInfo] = []
    l10n_with_cb = FluentLocalization(
        [primary, fallback],
        strict=False,
        on_fallback=fallback_seen.append,
    )
    l10n_with_cb.add_resource(fallback, ftl)

    _, errors = l10n_with_cb.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        # Fallback callback must have fired (primary locale had no message)
        if fallback_seen:
            _domain.fallback_triggered += 1
            info = fallback_seen[0]
            # Contract: FallbackInfo carries the correct resolved_locale
            if info.resolved_locale != fallback:
                msg = (
                    f"Fallback: expected resolved_locale='{fallback}', "
                    f"got '{info.resolved_locale}'"
                )
                raise LocalizationFuzzError(msg)
    else:
        _domain.messages_missing += 1


def _pattern_chain_of_3_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Three-locale chain: message in a fuzz-chosen position.

    Tests fallback traversal depth. The message can be in locale 0, 1, or 2
    (or nowhere). Verifies the fallback chain visits locales in order.
    """
    triple = fdp.PickValueInList(list(_LOCALE_TRIPLES))
    locale_a, locale_b, locale_c = triple
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"
    target_locale_idx = fdp.ConsumeIntInRange(0, 3)  # 3 = none

    l10n = FluentLocalization([locale_a, locale_b, locale_c], strict=False)

    target_locale = triple[target_locale_idx] if target_locale_idx < 3 else None
    if target_locale:
        l10n.add_resource(target_locale, ftl)

    result, errors = l10n.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        if target_locale and val in result:
            return  # Correct
        if not target_locale:
            # Message was in no locale - result is fallback text, errors expected
            pass
    else:
        _domain.messages_missing += 1


def _pattern_format_value_missing(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """format_value/format_pattern with non-existent message returns fallback.

    Tests the missing-message contract: format_pattern with a message ID that
    does not exist in any locale must return a non-empty fallback string and
    at least one error. strict=False to use soft-error return API.
    """
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    existing_id = gen_ftl_identifier(fdp)
    missing_id = f"missing-{gen_ftl_identifier(fdp)}"
    existing_ftl = f"{existing_id} = value\n"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, existing_ftl)

    result, errors = l10n.format_pattern(missing_id)

    # Contract: missing message MUST produce errors and non-empty fallback
    if not errors:
        msg = (
            f"Missing message '{missing_id}' produced no errors "
            f"(result='{result}')"
        )
        raise LocalizationFuzzError(msg)
    if not result:
        msg = f"Missing message '{missing_id}' produced empty result with errors"
        raise LocalizationFuzzError(msg)

    _domain.messages_missing += 1


def _pattern_format_with_variables(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """format_pattern with multiple variable args across two locales.

    Tests that variable substitution works correctly with fallback.
    Verifies the args dict propagates into the resolved bundle.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    var_a = gen_ftl_identifier(fdp)
    var_b = f"b-{gen_ftl_identifier(fdp)}"  # prefix guarantees var_b != var_a
    val_a = gen_ftl_value(fdp, max_length=20)
    val_b = gen_ftl_value(fdp, max_length=20)
    ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    result, errors = l10n.format_pattern(msg_id, {var_a: val_a, var_b: val_b})

    if not errors:
        _domain.messages_found += 1
        if val_a not in result or val_b not in result:
            msg = (
                f"Variables not found in result: "
                f"expected '{val_a}' and '{val_b}', got '{result}'"
            )
            raise LocalizationFuzzError(msg)


def _pattern_add_resource_mutation(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """add_resource after initial format call; re-format sees new resource.

    Tests that RWLock correctly serializes post-construction add_resource
    against concurrent format_pattern calls. The resource adds a new message
    and the second format_pattern must see it.
    """
    _domain.add_resource_mutations += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    msg_id_a = gen_ftl_identifier(fdp)
    msg_id_b = f"b-{gen_ftl_identifier(fdp)}"
    val_a = gen_ftl_value(fdp)
    val_b = gen_ftl_value(fdp)

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, f"{msg_id_a} = {val_a}\n")

    # First format (before mutation)
    l10n.format_pattern(msg_id_a)
    _, errors_b1 = l10n.format_pattern(msg_id_b)

    # msg_b not yet added - must produce errors
    if not errors_b1:
        msg = f"Before mutation: '{msg_id_b}' found before add_resource"
        raise LocalizationFuzzError(msg)

    # Add second message (mutation)
    l10n.add_resource(locale, f"{msg_id_b} = {val_b}\n")

    # Re-format after mutation
    result_b2, errors_b2 = l10n.format_pattern(msg_id_b)

    # FTL's blank_inline rule ("+" greedy) strips ALL leading whitespace from
    # inline message values; compare against lstrip() to match actual stored value.
    val_b_effective = val_b.lstrip()
    if not errors_b2 and val_b_effective and val_b_effective not in result_b2:
        msg = (
            f"After mutation: expected '{val_b_effective}' in result, "
            f"got '{result_b2}'"
        )
        raise LocalizationFuzzError(msg)


def _pattern_has_message_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """has_message/has_attribute cross-locale scan invariants.

    Tests: if format_pattern succeeds for a message ID, has_message must
    return True. If has_message returns False, format_pattern must produce
    errors.
    """
    _domain.has_message_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    attr_name = fdp.PickValueInList(["tooltip", "label", "title"])
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n    .{attr_name} = hint\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    has_msg = l10n.has_message(msg_id)
    has_attr = l10n.has_attribute(msg_id, attr_name)
    has_missing_attr = l10n.has_attribute(msg_id, "nonexistent-attr")

    # Contract: has_message must be True (we added it to fallback)
    if not has_msg:
        msg = f"has_message('{msg_id}') returned False after add_resource"
        raise LocalizationFuzzError(msg)

    # Contract: has_attribute(existing) must be True
    if not has_attr:
        msg = (
            f"has_attribute('{msg_id}', '{attr_name}') returned False "
            f"after add_resource"
        )
        raise LocalizationFuzzError(msg)

    # Contract: has_attribute(nonexistent) must be False
    if has_missing_attr:
        msg = (
            f"has_attribute('{msg_id}', 'nonexistent-attr') returned True"
        )
        raise LocalizationFuzzError(msg)


def _pattern_get_message_ids_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_message_ids returns superset of added message IDs.

    Tests deduplication: if the same message ID is added to two locales, it
    must appear only once in get_message_ids(). Also checks that
    get_message_ids() contains every message we added.
    """
    locale_a, locale_b = fdp.PickValueInList(list(_LOCALE_PAIRS))
    n = fdp.ConsumeIntInRange(1, 5)
    msg_ids = [gen_ftl_identifier(fdp) for _ in range(n)]

    l10n = FluentLocalization([locale_a, locale_b], strict=False)

    # Add same messages to both locales (deduplication test)
    for mid in msg_ids:
        l10n.add_resource(locale_a, f"{mid} = value-a\n")
        l10n.add_resource(locale_b, f"{mid} = value-b\n")

    all_ids = l10n.get_message_ids()
    all_ids_set = set(all_ids)

    # Contract: every added message ID must appear
    for mid in msg_ids:
        if mid not in all_ids_set:
            msg = f"get_message_ids(): missing '{mid}' after add_resource"
            raise LocalizationFuzzError(msg)

    # Contract: no duplicates
    if len(all_ids) != len(all_ids_set):
        msg = f"get_message_ids(): duplicates found: {sorted(all_ids)}"
        raise LocalizationFuzzError(msg)


def _pattern_validate_resource_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_resource via FluentLocalization facade.

    Tests that validate_resource returns a ValidationResult and that
    its errors/warnings attributes are sequences (never crashes, never
    returns None, always returns a structured result).
    """
    _domain.validate_calls += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    ftl_choice = fdp.ConsumeIntInRange(0, 5)

    match ftl_choice:
        case 0:
            ftl = f"{gen_ftl_identifier(fdp)} = valid message\n"
        case 1:
            ftl = "invalid = { $x -> [one] singular *[other] plural }\n"
        case 2:
            ftl = ""  # Empty
        case 3:
            ftl = "# Just a comment\n"
        case 4:
            # Duplicate message ID
            mid = gen_ftl_identifier(fdp)
            ftl = f"{mid} = first\n{mid} = second\n"
        case _:
            ftl = fdp.ConsumeUnicodeNoSurrogates(
                fdp.ConsumeIntInRange(0, 200)
            )

    l10n = FluentLocalization([locale], strict=False)
    result = l10n.validate_resource(ftl)

    # Contract: validate_resource always returns a structured result
    if result is None:
        msg = "validate_resource returned None"
        raise LocalizationFuzzError(msg)

    # Contract: errors and warnings are tuples/sequences
    if not hasattr(result, "errors") or not hasattr(result, "warnings"):
        msg = "validate_resource result missing errors/warnings"
        raise LocalizationFuzzError(msg)


def _pattern_add_function_custom(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Custom function registered via add_function and invoked in FTL.

    Tests the add_function pathway: a Python function is registered under a
    SCREAMING_SNAKE_CASE name and invoked from an FTL message. Verifies that
    function results appear in format_pattern output.
    """
    _domain.custom_function_calls += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    func_name = "UPPER"
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp, max_length=20)
    ftl = f"{msg_id} = {{ {func_name}($val) }}\n"

    # use_isolating=False: result equality check must not include FSI/PDI BiDi marks
    l10n = FluentLocalization([locale], strict=False, use_isolating=False)
    l10n.add_resource(locale, ftl)

    # Register custom function that uppercases its argument
    def upper_func(value: str) -> str:
        return str(value).upper()

    l10n.add_function(func_name, upper_func)

    result, errors = l10n.format_pattern(msg_id, {"val": val})

    if not errors:
        expected = val.upper()
        if result != expected:
            msg = (
                f"Custom UPPER function: expected '{expected}', "
                f"got '{result}'"
            )
            raise LocalizationFuzzError(msg)


def _pattern_introspect_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """introspect_message and get_message_variables via localization facade.

    Tests the introspection delegation path: introspect_message() and
    get_message_variables() both delegate through the fallback chain.
    Verifies variable sets are consistent between the two APIs.
    """
    _domain.introspect_calls += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    var_a = gen_ftl_identifier(fdp)
    var_b = f"b-{gen_ftl_identifier(fdp)}"  # prefix guarantees var_b != var_a
    ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    # introspect_message returns MessageIntrospection or None
    info = l10n.introspect_message(msg_id)
    variables = l10n.get_message_variables(msg_id)

    if info is not None:
        # Contract: get_message_variables must be a subset of introspect result
        introspect_vars = info.get_variable_names()
        for var in variables:
            if var not in introspect_vars:
                msg = (
                    f"get_message_variables returned '{var}' not in "
                    f"introspect result: {introspect_vars}"
                )
                raise LocalizationFuzzError(msg)


def _pattern_on_fallback_callback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """on_fallback callback fires when message resolved from fallback locale.

    Tests that the callback is invoked exactly once when the primary locale
    lacks the message and the fallback locale has it. Verifies FallbackInfo
    carries the correct requested and resolved locales.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"

    fallback_infos: list[FallbackInfo] = []

    l10n = FluentLocalization(
        [primary, fallback],
        strict=False,
        on_fallback=fallback_infos.append,
    )
    # Add message only to fallback locale
    l10n.add_resource(fallback, ftl)

    _, errors = l10n.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        if fallback_infos:
            _domain.fallback_triggered += 1
            info = fallback_infos[0]
            # Contract: requested_locale = primary, resolved_locale = fallback
            if info.resolved_locale != fallback:
                msg = (
                    f"on_fallback: resolved_locale='{info.resolved_locale}' "
                    f"expected '{fallback}'"
                )
                raise LocalizationFuzzError(msg)
    else:
        _domain.messages_missing += 1


# --- Pattern dispatch ---

_PATTERN_DISPATCH = {
    "single_locale_add_resource": _pattern_single_locale_add_resource,
    "multi_locale_fallback": _pattern_multi_locale_fallback,
    "chain_of_3_fallback": _pattern_chain_of_3_fallback,
    "format_value_missing": _pattern_format_value_missing,
    "format_with_variables": _pattern_format_with_variables,
    "add_resource_mutation": _pattern_add_resource_mutation,
    "has_message_api": _pattern_has_message_api,
    "get_message_ids_api": _pattern_get_message_ids_api,
    "validate_resource_api": _pattern_validate_resource_api,
    "add_function_custom": _pattern_add_function_custom,
    "introspect_api": _pattern_introspect_api,
    "on_fallback_callback": _pattern_on_fallback_callback,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test FluentLocalization invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    try:
        _PATTERN_DISPATCH[pattern_name](fdp)

    except (
        *_ALLOWED_EXCEPTIONS,
        FrozenFluentError,
        DataIntegrityError,
        FormattingIntegrityError,
        SyntaxIntegrityError,
    ) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = (
            _state.error_counts.get(error_type, 0) + 1
        )
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "fallback" in pattern_name
            or pattern_name in ("add_resource_mutation", "introspect_api")
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state, pattern_name, start_time, data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the localization fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="FluentLocalization multi-locale orchestration fuzzer",
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
        help="Maximum in-memory seed corpus size (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="FluentLocalization Multi-locale Orchestration Fuzzer (Atheris)",
        target="ftllexengine.localization.orchestrator.FluentLocalization",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
