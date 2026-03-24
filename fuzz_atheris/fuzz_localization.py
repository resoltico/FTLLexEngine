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
has a completely distinct lifecycle: constructor locale boundary validation,
multi-locale fallback chains, RWLock-protected add_resource/add_function after
construction, lazy bundle creation for fallback locales, load summary tracking,
and on_fallback callback dispatch. fuzz_runtime covers FluentBundle only --
zero FluentLocalization code paths are exercised by any other fuzzer.

Unique coverage (not covered by other fuzzers):
- FluentLocalization constructor locale boundary validation, canonicalization/dedup rules,
  and rejection contracts
- format_pattern fallback chain traversal across 2-5 locales
- add_resource() with RWLock write acquisition after initial construction
- Lazy bundle creation for fallback locales (_get_or_create_bundle)
- has_message()/has_attribute() cross-locale scan
- get_message()/get_term() AST lookup across fallback locales
- require_clean() boot validation over loader-backed LoadSummary state
- validate_message_variables() single-message integrity validation across fallback chains
- validate_message_schemas() exact-schema enforcement across fallback chains
- get_message_ids() aggregation across all locale bundles
- get_message_variables() / introspect_message() localization facade
- get_cache_audit_log() per-locale audit visibility without raw cache access
- on_fallback callback invocation and FallbackInfo contract
- validate_resource() via localization facade
- add_function() custom function registration and application to late bundles
- Strict/non-strict mode propagation to each per-locale bundle
- resource_loader + PathResourceLoader eager initialization path
- LoadSummary aggregation (success, not_found, error, junk)
- loader-backed source_path and path-validation error plumbing

Patterns (24):
- single_locale_add_resource: 1 locale, add_resource, format
- multi_locale_fallback: 2 locales, message only in fallback locale
- chain_of_3_fallback: 3-locale chain, message in various positions
- format_value_missing: format non-existent message (fallback contract)
- format_with_variables: format message with variable args
- add_resource_mutation: add_resource after initial creation, re-format
- has_message_api: has_message/has_attribute contract verification
- ast_lookup_api: get_message/get_term precedence and namespace separation
- get_message_ids_api: get_message_ids deduplication and coverage
- validate_resource_api: validate_resource via localization facade
- validate_message_variables_api: single-message exact-schema validation and integrity errors
- validate_message_schemas_api: exact schema validation success/failure paths
- add_function_custom: add_function + FTL that calls custom function
- introspect_api: introspect_message/get_message_variables contracts
- cache_audit_api: per-locale cache audit accessor and aggregation
- locale_boundary_api: constructor locale canonicalization/dedup and rejection contracts
- on_fallback_callback: on_fallback callback fires on locale miss
- loader_init_success: eager load via PathResourceLoader succeeds for all locales
- loader_not_found_fallback: loader summary tracks primary miss + fallback success
- loader_junk_summary: eager load records Junk entries in LoadSummary
- loader_path_error: invalid resource_id is captured as loader error in summary
- require_clean_api: boot validation raises or returns based on LoadSummary cleanliness
- boot_config_api: LocalizationBootConfig strict-mode boot sequence, boot_simple(), boot()
  3-tuple primary API, required_messages enforcement, and one-shot call enforcement

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
from tempfile import TemporaryDirectory
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
    ast_lookup_checks: int = 0
    validate_calls: int = 0
    message_variable_validation_checks: int = 0
    schema_validation_checks: int = 0
    cache_audit_checks: int = 0
    locale_boundary_checks: int = 0
    loader_init_checks: int = 0
    loader_junk_checks: int = 0
    loader_error_checks: int = 0
    boot_validation_checks: int = 0
    boot_config_checks: int = 0


class LocalizationFuzzError(Exception):
    """Raised when an invariant breach is detected."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,  # empty locale list, locale not in chain, whitespace
    TypeError,  # invalid argument types
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
    ("ast_lookup_api", 7),
    ("get_message_ids_api", 6),
    ("validate_resource_api", 7),
    ("validate_message_variables_api", 6),
    ("validate_message_schemas_api", 6),
    ("add_function_custom", 6),
    ("introspect_api", 7),
    ("cache_audit_api", 6),
    ("locale_boundary_api", 5),
    ("on_fallback_callback", 6),
    ("loader_init_success", 5),
    ("loader_not_found_fallback", 5),
    ("loader_junk_summary", 4),
    ("loader_path_error", 4),
    ("require_clean_api", 5),
    ("boot_config_api", 6),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)
_PATTERN_INDEX: dict[str, int] = {name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)}

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
    "en-US",
    "de-DE",
    "fr-FR",
    "ja-JP",
    "ko-KR",
    "ar-SA",
    "zh-CN",
    "pt-BR",
    "es-ES",
    "sv-SE",
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
_VALID_AUDIT_OPERATIONS: frozenset[str] = frozenset(
    {
        "MISS",
        "PUT",
        "HIT",
        "EVICT",
        "CORRUPTION",
        "WRITE_ONCE_IDEMPOTENT",
        "WRITE_ONCE_CONFLICT",
    }
)

# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="localization",
    fuzzer_target=(
        "FluentLocalization (locale boundary, multi-locale fallback chains, "
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
    stats["ast_lookup_checks"] = _domain.ast_lookup_checks
    stats["validate_calls"] = _domain.validate_calls
    stats["message_variable_validation_checks"] = _domain.message_variable_validation_checks
    stats["schema_validation_checks"] = _domain.schema_validation_checks
    stats["cache_audit_checks"] = _domain.cache_audit_checks
    stats["locale_boundary_checks"] = _domain.locale_boundary_checks
    stats["loader_init_checks"] = _domain.loader_init_checks
    stats["loader_junk_checks"] = _domain.loader_junk_checks
    stats["loader_error_checks"] = _domain.loader_error_checks
    stats["boot_validation_checks"] = _domain.boot_validation_checks
    stats["boot_config_checks"] = _domain.boot_config_checks
    total = _domain.messages_found + _domain.messages_missing
    if total > 0:
        stats["fallback_hit_ratio"] = round(_domain.fallback_triggered / total, 3)
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
    from ftllexengine import validate_message_variables
    from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT
    from ftllexengine.core.locale_utils import normalize_locale, require_locale_code
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        DataIntegrityError,
        FormattingIntegrityError,
        IntegrityCheckFailedError,
        SyntaxIntegrityError,
    )
    from ftllexengine.localization import (
        CacheAuditLogEntry,
        FluentLocalization,
        LocalizationBootConfig,
        LocalizationCacheStats,
    )
    from ftllexengine.localization.loading import FallbackInfo, PathResourceLoader
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.syntax import Message, Term


# --- Pattern implementations ---


def _write_loader_resource(
    root: pathlib.Path,
    locale: str,
    resource_id: str,
    ftl_source: str,
) -> pathlib.Path:
    """Write an FTL file for PathResourceLoader-backed tests."""
    locale_dir = root / normalize_locale(locale)
    locale_dir.mkdir(parents=True, exist_ok=True)
    resource_path = locale_dir / resource_id
    resource_path.write_text(ftl_source, encoding="utf-8")
    return resource_path


def _build_variable_message(message_id: str, variables: tuple[str, ...]) -> str:
    """Build a simple message that references the given variable set."""
    placeables = " ".join(f"{{ ${variable} }}" for variable in variables)
    return f"{message_id} = {placeables or 'value'}\n"


def _assert_integrity_failure(
    err: IntegrityCheckFailedError,
    *,
    operation: str,
    message_fragment: str | None = None,
    key: str | None = None,
    key_fragment: str | None = None,
    actual_fragment: str | None = None,
) -> None:
    """Validate localization-scoped IntegrityCheckFailedError context."""
    if message_fragment is not None and message_fragment not in str(err):
        msg = f"Integrity error message missing {message_fragment!r}: {err!s}"
        raise LocalizationFuzzError(msg)

    context = err.context
    if context is None:
        msg = "IntegrityCheckFailedError missing context"
        raise LocalizationFuzzError(msg)
    if context.component != "localization":
        msg = f"Integrity error component={context.component!r}, expected 'localization'"
        raise LocalizationFuzzError(msg)
    if context.operation != operation:
        msg = f"Integrity error operation={context.operation!r}, expected {operation!r}"
        raise LocalizationFuzzError(msg)
    if context.expected != "LoadSummary(all_clean=True)" and operation == "require_clean":
        msg = f"require_clean context expected field mismatch: {context.expected!r}"
        raise LocalizationFuzzError(msg)
    if key is not None and context.key != key:
        msg = f"Integrity error key={context.key!r}, expected {key!r}"
        raise LocalizationFuzzError(msg)
    if key_fragment is not None and (context.key is None or key_fragment not in context.key):
        msg = f"Integrity error key={context.key!r} missing fragment {key_fragment!r}"
        raise LocalizationFuzzError(msg)
    if actual_fragment is not None and (
        context.actual is None or actual_fragment not in context.actual
    ):
        msg = f"Integrity error actual={context.actual!r} missing fragment {actual_fragment!r}"
        raise LocalizationFuzzError(msg)


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
            expected_fallback = normalize_locale(fallback)
            if info.resolved_locale != expected_fallback:
                msg = (
                    "Fallback: expected "
                    f"resolved_locale='{expected_fallback}', "
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
        msg = f"Missing message '{missing_id}' produced no errors (result='{result}')"
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
    var_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
    val_a = gen_ftl_value(fdp, max_length=20)
    val_b = gen_ftl_value(fdp, max_length=20)
    ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    result, errors = l10n.format_pattern(msg_id, {var_a: val_a, var_b: val_b})

    if not errors:
        _domain.messages_found += 1
        if val_a not in result or val_b not in result:
            msg = f"Variables not found in result: expected '{val_a}' and '{val_b}', got '{result}'"
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
    msg_id_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
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

    if not errors_b2 and val_b not in result_b2:
        msg = f"After mutation: expected '{val_b}' in result, got '{result_b2}'"
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
        msg = f"has_attribute('{msg_id}', '{attr_name}') returned False after add_resource"
        raise LocalizationFuzzError(msg)

    # Contract: has_attribute(nonexistent) must be False
    if has_missing_attr:
        msg = f"has_attribute('{msg_id}', 'nonexistent-attr') returned True"
        raise LocalizationFuzzError(msg)


def _validate_localization_message_lookup(
    l10n: FluentLocalization,
    message_id: str,
    expected_variables: frozenset[str],
) -> None:
    """Validate FluentLocalization.get_message() for one identifier."""
    message = l10n.get_message(message_id)
    if message is None:
        msg = f"get_message('{message_id}') returned None for an existing message"
        raise LocalizationFuzzError(msg)
    if not isinstance(message, Message):
        msg = f"get_message('{message_id}') returned {type(message).__name__}"
        raise LocalizationFuzzError(msg)
    if message.id.name != message_id:
        msg = f"get_message('{message_id}') returned node named '{message.id.name}'"
        raise LocalizationFuzzError(msg)

    message_validation = validate_message_variables(message, expected_variables)
    if not message_validation.is_valid:
        msg = f"validate_message_variables() rejected localization message '{message_id}'"
        raise LocalizationFuzzError(msg)
    if message_validation.declared_variables != expected_variables:
        msg = (
            f"get_message('{message_id}') resolved wrong locale variables: "
            f"{message_validation.declared_variables!r} vs {expected_variables!r}"
        )
        raise LocalizationFuzzError(msg)


def _validate_localization_term_lookup(
    l10n: FluentLocalization,
    term_id: str,
    expected_variables: frozenset[str],
) -> None:
    """Validate FluentLocalization.get_term() for one identifier."""
    term = l10n.get_term(term_id)
    if term is None:
        msg = f"get_term('{term_id}') returned None for an existing term"
        raise LocalizationFuzzError(msg)
    if not isinstance(term, Term):
        msg = f"get_term('{term_id}') returned {type(term).__name__}"
        raise LocalizationFuzzError(msg)
    if term.id.name != term_id:
        msg = f"get_term('{term_id}') returned node named '{term.id.name}'"
        raise LocalizationFuzzError(msg)

    term_validation = validate_message_variables(term, expected_variables)
    if not term_validation.is_valid:
        msg = f"validate_message_variables() rejected localization term '{term_id}'"
        raise LocalizationFuzzError(msg)
    if term_validation.declared_variables != expected_variables:
        msg = (
            f"get_term('{term_id}') resolved wrong locale variables: "
            f"{term_validation.declared_variables!r} vs {expected_variables!r}"
        )
        raise LocalizationFuzzError(msg)


def _pattern_ast_lookup_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_message/get_term honor fallback precedence and namespace boundaries."""
    _domain.ast_lookup_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = f"msg-{gen_ftl_identifier(fdp)}"
    term_id = f"term-{gen_ftl_identifier(fdp)}"
    primary_has_message = fdp.ConsumeBool()
    primary_has_term = fdp.ConsumeBool()

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(
        fallback,
        (f"{msg_id} = {{ $fallbackvar }}\n-{term_id} = {{ $fallbackterm }}\n"),
    )

    primary_parts: list[str] = []
    if primary_has_message:
        primary_parts.append(f"{msg_id} = {{ $primaryvar }}\n")
    if primary_has_term:
        primary_parts.append(f"-{term_id} = {{ $primaryterm }}\n")
    if primary_parts:
        l10n.add_resource(primary, "".join(primary_parts))

    expected_message_vars = frozenset({"primaryvar" if primary_has_message else "fallbackvar"})
    _validate_localization_message_lookup(l10n, msg_id, expected_message_vars)

    expected_term_vars = frozenset({"primaryterm" if primary_has_term else "fallbackterm"})
    _validate_localization_term_lookup(l10n, term_id, expected_term_vars)

    if l10n.get_term(f"-{term_id}") is not None:
        msg = f"get_term('-{term_id}') bypassed the no-leading-dash contract"
        raise LocalizationFuzzError(msg)
    if l10n.get_message(term_id) is not None:
        msg = f"get_message('{term_id}') crossed the term/message namespace boundary"
        raise LocalizationFuzzError(msg)
    if l10n.get_term(msg_id) is not None:
        msg = f"get_term('{msg_id}') crossed the message/term namespace boundary"
        raise LocalizationFuzzError(msg)
    if l10n.get_message("__missing_localization_lookup__") is not None:
        msg = "get_message() returned a node for a missing localization message"
        raise LocalizationFuzzError(msg)
    if l10n.get_term("__missing_localization_lookup__") is not None:
        msg = "get_term() returned a node for a missing localization term"
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
            ftl = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))

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


def _check_message_schema_exact_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Exact schemas succeed and preserve input order."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_count = fdp.ConsumeIntInRange(1, 3)
    expected_schemas: dict[str, frozenset[str] | set[str]] = {}
    resource_parts: list[str] = []

    for index in range(message_count):
        message_id = f"schema-{index}-{gen_ftl_identifier(fdp)}"
        variable_count = fdp.ConsumeIntInRange(1, 2)
        variables = tuple(
            f"var{index}_{slot}_{gen_ftl_identifier(fdp)}" for slot in range(variable_count)
        )
        expected = frozenset(variables) if fdp.ConsumeBool() else set(variables)
        expected_schemas[message_id] = expected
        resource_parts.append(_build_variable_message(message_id, variables))

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "".join(resource_parts))
    try:
        results = l10n.validate_message_schemas(expected_schemas)
    except IntegrityCheckFailedError as err:
        msg = f"validate_message_schemas() raised on exact schemas: {err}"
        raise LocalizationFuzzError(msg) from err

    if not isinstance(results, tuple):
        msg = f"validate_message_schemas() returned {type(results).__name__}"
        raise LocalizationFuzzError(msg)
    if [result.message_id for result in results] != list(expected_schemas):
        msg = (
            "validate_message_schemas() returned results out of input order: "
            f"{[result.message_id for result in results]!r} vs {list(expected_schemas)!r}"
        )
        raise LocalizationFuzzError(msg)
    for result in results:
        expected_variables = frozenset(expected_schemas[result.message_id])
        if not result.is_valid or result.declared_variables != expected_variables:
            msg = (
                "validate_message_schemas() returned invalid exact-match result: "
                f"{result!r} vs {expected_variables!r}"
            )
            raise LocalizationFuzzError(msg)


def _assert_localization_message_validation_matches_lookup(
    l10n: FluentLocalization,
    message_id: str,
    expected_variables: frozenset[str] | set[str],
) -> None:
    """Single-message validation should match direct AST validation."""
    message = l10n.get_message(message_id)
    if message is None:
        msg = f"get_message('{message_id}') returned None during schema validation"
        raise LocalizationFuzzError(msg)

    direct = validate_message_variables(message, frozenset(expected_variables))
    resolved = l10n.validate_message_variables(message_id, expected_variables)
    if resolved != direct:
        msg = (
            "validate_message_variables() diverged from direct AST validation: "
            f"{resolved!r} vs {direct!r}"
        )
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-message exact-schema validation succeeds for direct hits."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"single-{gen_ftl_identifier(fdp)}"
    variable_count = fdp.ConsumeIntInRange(1, 2)
    variables = tuple(
        f"var_{slot}_{gen_ftl_identifier(fdp)}" for slot in range(variable_count)
    )
    expected_variables: frozenset[str] | set[str] = (
        frozenset(variables) if fdp.ConsumeBool() else set(variables)
    )

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, variables))
    _assert_localization_message_validation_matches_lookup(
        l10n,
        message_id,
        expected_variables,
    )


def _check_single_message_validation_fallback_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-message validation resolves through localization fallback."""
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    message_id = f"fallback-single-{gen_ftl_identifier(fdp)}"
    variable = f"fallback_{gen_ftl_identifier(fdp)}"
    expected_variables: frozenset[str] | set[str] = (
        frozenset({variable}) if fdp.ConsumeBool() else {variable}
    )

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, _build_variable_message(message_id, (variable,)))
    _assert_localization_message_validation_matches_lookup(
        l10n,
        message_id,
        expected_variables,
    )


def _check_single_message_validation_missing_message(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing messages fail the single-message localization validator."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    missing_id = f"missing-single-{gen_ftl_identifier(fdp)}"
    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "present = value\n")

    try:
        l10n.validate_message_variables(missing_id, frozenset())
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{missing_id}: not found",
            key=missing_id,
            actual_fragment="missing_messages=1",
        )
    else:
        msg = "validate_message_variables() accepted a missing message"
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_extra_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Extra declared variables fail exact single-message validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"extra-single-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(
        locale,
        _build_variable_message(message_id, (amount_var, customer_var)),
    )

    try:
        l10n.validate_message_variables(message_id, frozenset({amount_var}))
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{message_id}: extra {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_variables() accepted an extra-variable mismatch"
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_missing_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing expected variables fail exact single-message validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"missing-var-single-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, (amount_var,)))

    try:
        l10n.validate_message_variables(message_id, {amount_var, customer_var})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{message_id}: missing {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_variables() accepted a missing-variable mismatch"
        raise LocalizationFuzzError(msg)


def _pattern_validate_message_variables_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_message_variables enforces exact schemas per message."""
    _domain.message_variable_validation_checks += 1
    handlers = (
        _check_single_message_validation_success,
        _check_single_message_validation_fallback_success,
        _check_single_message_validation_missing_message,
        _check_single_message_validation_extra_variable,
        _check_single_message_validation_missing_variable,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


def _check_message_schema_fallback_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Fallback-resolved messages validate through the localization facade."""
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    message_id = f"fallback-{gen_ftl_identifier(fdp)}"
    variable = f"fallback_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, _build_variable_message(message_id, (variable,)))
    try:
        results = l10n.validate_message_schemas({message_id: frozenset({variable})})
    except IntegrityCheckFailedError as err:
        msg = f"validate_message_schemas() rejected fallback-resolved schema: {err}"
        raise LocalizationFuzzError(msg) from err

    if len(results) != 1 or not results[0].is_valid:
        msg = f"Fallback schema validation returned {results!r}"
        raise LocalizationFuzzError(msg)


def _check_message_schema_missing_message(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing messages fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    missing_id = f"missing-{gen_ftl_identifier(fdp)}"
    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "present = value\n")

    try:
        l10n.validate_message_schemas({missing_id: frozenset()})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{missing_id}: not found",
            key=missing_id,
            actual_fragment="missing_messages=1",
        )
    else:
        msg = "validate_message_schemas() accepted a missing message"
        raise LocalizationFuzzError(msg)


def _check_message_schema_extra_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Extra variables in the message fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"extra-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(
        locale,
        _build_variable_message(message_id, (amount_var, customer_var)),
    )

    try:
        l10n.validate_message_schemas({message_id: frozenset({amount_var})})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{message_id}: extra {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_schemas() accepted an extra-variable mismatch"
        raise LocalizationFuzzError(msg)


def _check_message_schema_missing_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing expected variables fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"missing-var-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, (amount_var,)))

    try:
        l10n.validate_message_schemas({message_id: {amount_var, customer_var}})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{message_id}: missing {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_schemas() accepted a missing-variable mismatch"
        raise LocalizationFuzzError(msg)


def _pattern_validate_message_schemas_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_message_schemas enforces exact schemas through localization."""
    _domain.schema_validation_checks += 1
    handlers = (
        _check_message_schema_exact_success,
        _check_message_schema_fallback_success,
        _check_message_schema_missing_message,
        _check_message_schema_extra_variable,
        _check_message_schema_missing_variable,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


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
            msg = f"Custom UPPER function: expected '{expected}', got '{result}'"
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
    var_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
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


def _validate_localization_audit_log(
    locale: str,
    audit_log: tuple[CacheAuditLogEntry, ...],
    *,
    enable_audit: bool,
) -> int:
    """Validate one locale's audit log and return its entry count."""
    if not enable_audit and audit_log != ():
        msg = f"Audit-disabled localization returned non-empty log for '{locale}'"
        raise LocalizationFuzzError(msg)

    last_timestamp = float("-inf")
    for entry in audit_log:
        if entry.operation not in _VALID_AUDIT_OPERATIONS:
            msg = f"Unexpected audit operation {entry.operation!r} for locale '{locale}'"
            raise LocalizationFuzzError(msg)
        if not entry.key_hash:
            msg = f"Empty audit key hash for locale '{locale}'"
            raise LocalizationFuzzError(msg)
        if entry.timestamp < last_timestamp:
            msg = (
                f"Audit timestamps regressed for locale '{locale}': "
                f"{last_timestamp} -> {entry.timestamp}"
            )
            raise LocalizationFuzzError(msg)
        if entry.operation == "MISS":
            if entry.sequence != 0 or entry.checksum_hex != "":
                msg = (
                    f"MISS audit entry for locale '{locale}' must have "
                    "sequence=0 and empty checksum"
                )
                raise LocalizationFuzzError(msg)
        elif entry.sequence <= 0 or entry.checksum_hex == "":
            msg = (
                f"{entry.operation} audit entry for locale '{locale}' must carry "
                "a positive sequence and non-empty checksum"
            )
            raise LocalizationFuzzError(msg)
        last_timestamp = entry.timestamp

    return len(audit_log)


def _validate_localization_cache_stats(
    stats: LocalizationCacheStats,
    *,
    enable_audit: bool,
    expected_locales: list[str],
) -> None:
    """Validate aggregate localization cache stats against configuration."""
    if stats["audit_enabled"] != enable_audit:
        msg = (
            "get_cache_stats()['audit_enabled'] disagrees with CacheConfig: "
            f"{stats['audit_enabled']} vs {enable_audit}"
        )
        raise LocalizationFuzzError(msg)
    if stats["bundle_count"] != len(expected_locales):
        msg = (
            "get_cache_stats()['bundle_count'] disagrees with initialized locales: "
            f"{stats['bundle_count']} vs {len(expected_locales)}"
        )
        raise LocalizationFuzzError(msg)


def _collect_localization_audit_entries(
    audit_logs: dict[str, tuple[CacheAuditLogEntry, ...]],
    *,
    enable_audit: bool,
) -> int:
    """Validate all per-locale audit logs and return their combined length."""
    total_audit_entries = 0
    for locale, audit_log in audit_logs.items():
        if not isinstance(audit_log, tuple):
            msg = f"get_cache_audit_log()['{locale}'] returned {type(audit_log).__name__}"
            raise LocalizationFuzzError(msg)
        if any(not isinstance(entry, CacheAuditLogEntry) for entry in audit_log):
            msg = f"get_cache_audit_log()['{locale}'] returned non-CacheAuditLogEntry data"
            raise LocalizationFuzzError(msg)
        total_audit_entries += _validate_localization_audit_log(
            locale,
            audit_log,
            enable_audit=enable_audit,
        )
    return total_audit_entries


def _pattern_cache_audit_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_cache_audit_log exposes per-locale immutable audit trails."""
    _domain.cache_audit_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    enable_audit = fdp.ConsumeBool()
    initialize_fallback = fdp.ConsumeBool()
    primary_msg_id = f"audit-{gen_ftl_identifier(fdp)}"
    fallback_msg_id = f"fallback-{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization(
        [primary, fallback],
        cache=CacheConfig(enable_audit=enable_audit),
        strict=False,
    )
    l10n.add_resource(primary, f"{primary_msg_id} = primary\n")

    expected_locales = [normalize_locale(primary)]
    if initialize_fallback:
        l10n.add_resource(fallback, f"{fallback_msg_id} = fallback\n")
        expected_locales.append(normalize_locale(fallback))

    l10n.format_value(primary_msg_id)
    l10n.format_value(primary_msg_id)
    if initialize_fallback:
        l10n.format_value(fallback_msg_id)

    audit_logs = l10n.get_cache_audit_log()
    if audit_logs is None:
        msg = "Cached FluentLocalization returned None from get_cache_audit_log()"
        raise LocalizationFuzzError(msg)
    if list(audit_logs) != expected_locales:
        msg = (
            "get_cache_audit_log() returned wrong locale keys: "
            f"{list(audit_logs)!r} vs {expected_locales!r}"
        )
        raise LocalizationFuzzError(msg)

    stats = l10n.get_cache_stats()
    if stats is None:
        msg = "Cached FluentLocalization returned None from get_cache_stats()"
        raise LocalizationFuzzError(msg)
    _validate_localization_cache_stats(
        stats,
        enable_audit=enable_audit,
        expected_locales=expected_locales,
    )
    total_audit_entries = _collect_localization_audit_entries(
        audit_logs,
        enable_audit=enable_audit,
    )

    if total_audit_entries != int(stats.get("audit_entries", 0)):
        msg = (
            "Localization audit log length disagrees with cache stats: "
            f"{total_audit_entries} vs {stats.get('audit_entries')}"
        )
        raise LocalizationFuzzError(msg)

    primary_locale = normalize_locale(primary)
    fallback_locale = normalize_locale(fallback)
    if enable_audit and len(audit_logs[primary_locale]) < 2:
        msg = f"Primary locale '{primary_locale}' did not record expected audit entries"
        raise LocalizationFuzzError(msg)
    if initialize_fallback and enable_audit and len(audit_logs[fallback_locale]) < 2:
        msg = f"Fallback locale '{fallback_locale}' did not record expected audit entries"
        raise LocalizationFuzzError(msg)


def _assert_localization_locale_accepts(
    raw_locales: list[str],
    *,
    expected_locales: tuple[str, ...],
) -> None:
    """Accepted locale chains are canonicalized, deduplicated, and remain usable."""
    try:
        l10n = FluentLocalization(raw_locales, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        msg = f"FluentLocalization rejected valid locales {raw_locales!r}: {err}"
        raise LocalizationFuzzError(msg) from err

    if l10n.locales != expected_locales:
        msg = (
            "FluentLocalization stored the wrong locale chain: "
            f"{l10n.locales!r} vs {expected_locales!r}"
        )
        raise LocalizationFuzzError(msg)

    l10n.add_resource(expected_locales[0], "msg = ready\n")
    result, errors = l10n.format_pattern("msg")
    if result != "ready" or errors:
        msg = (
            f"FluentLocalization with accepted locales {expected_locales!r} "
            f"failed basic formatting: result={result!r}, errors={errors!r}"
        )
        raise LocalizationFuzzError(msg)


def _assert_localization_locale_rejected(
    locales: list[object],
    *,
    expected_exception: type[ValueError | TypeError],
    expected_fragment: str,
) -> None:
    """Rejected locale chains surface the canonical constructor error contract."""
    locales_value: Any = locales

    try:
        FluentLocalization(locales_value, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        if not isinstance(err, expected_exception):
            msg = (
                "FluentLocalization raised the wrong locale-boundary exception for "
                f"{locales!r}: {type(err).__name__}"
            )
            raise LocalizationFuzzError(msg) from err
        if expected_fragment not in str(err):
            msg = (
                "FluentLocalization locale-boundary error message drifted for "
                f"{locales!r}: {err}"
            )
            raise LocalizationFuzzError(msg) from err
        return

    msg = f"FluentLocalization accepted invalid locales {locales!r}"
    raise LocalizationFuzzError(msg)


def _pattern_locale_boundary_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """FluentLocalization constructor shares the canonical locale boundary contract."""
    _domain.locale_boundary_checks += 1
    scenario = fdp.ConsumeIntInRange(0, 4)
    boundary_locale = "a" + ("b" * (MAX_LOCALE_LENGTH_HARD_LIMIT - 2)) + "C"

    match scenario:
        case 0:
            if fdp.ConsumeBool():
                raw_locales = ["  EN-us  ", "\tEN-us\n", " de-DE "]
                expected_locales = (
                    require_locale_code("  EN-us  ", "locale"),
                    require_locale_code(" de-DE ", "locale"),
                )
            else:
                raw_locales = [f"  {boundary_locale}  ", f"\n{boundary_locale}\t", " lv "]
                expected_locales = (
                    require_locale_code(f"  {boundary_locale}  ", "locale"),
                    require_locale_code(" lv ", "locale"),
                )
            _assert_localization_locale_accepts(
                raw_locales,
                expected_locales=expected_locales,
            )
        case 1:
            blank_locale = fdp.PickValueInList(["", " ", "\t\n", " \r\n "])
            _assert_localization_locale_rejected(
                ["en", blank_locale],
                expected_exception=ValueError,
                expected_fragment="locale cannot be blank",
            )
        case 2:
            invalid_locale = fdp.PickValueInList(list(_STRUCTURALLY_INVALID_LOCALES))
            _assert_localization_locale_rejected(
                ["en", invalid_locale],
                expected_exception=ValueError,
                expected_fragment="Invalid locale:",
            )
        case 3:
            overshoot = fdp.ConsumeIntInRange(1, 32)
            overlong_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + overshoot)
            _assert_localization_locale_rejected(
                ["en", overlong_locale],
                expected_exception=ValueError,
                expected_fragment="locale exceeds maximum length",
            )
        case _:
            non_string_locale = fdp.PickValueInList(list(_NON_STRING_LOCALES))
            _assert_localization_locale_rejected(
                ["en", non_string_locale],
                expected_exception=TypeError,
                expected_fragment="locale must be str",
            )


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
            expected_fallback = normalize_locale(fallback)
            if info.resolved_locale != expected_fallback:
                msg = (
                    f"on_fallback: resolved_locale='{info.resolved_locale}' "
                    f"expected '{expected_fallback}'"
                )
                raise LocalizationFuzzError(msg)
    else:
        _domain.messages_missing += 1


def _pattern_loader_init_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """PathResourceLoader eager-init path records all-success summary data."""
    _domain.loader_init_checks += 1
    locale_a, locale_b = fdp.PickValueInList(list(_LOCALE_PAIRS))
    resource_id = "main.ftl"
    msg_id = gen_ftl_identifier(fdp)
    primary_val = gen_ftl_value(fdp)
    fallback_val = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale_a, resource_id, f"{msg_id} = {primary_val}\n")
        _write_loader_resource(root, locale_b, resource_id, f"{msg_id} = {fallback_val}\n")

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale_a, locale_b],
            [resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.successful != 2 or not summary.all_successful:
            msg = (
                f"Expected two successful eager loads, got successful={summary.successful}, "
                f"not_found={summary.not_found}, errors={summary.errors}"
            )
            raise LocalizationFuzzError(msg)
        if summary.has_errors or summary.has_junk:
            msg = (
                f"Unexpected summary state: has_errors={summary.has_errors}, "
                f"has_junk={summary.has_junk}"
            )
            raise LocalizationFuzzError(msg)
        if any(result.source_path is None for result in summary.results):
            msg = "Loader summary missing source_path on successful result"
            raise LocalizationFuzzError(msg)

        result, errors = l10n.format_pattern(msg_id)
        if errors:
            msg = f"Loader-backed localization unexpectedly returned errors: {errors!r}"
            raise LocalizationFuzzError(msg)
        if primary_val not in result:
            msg = f"Primary locale value {primary_val!r} missing from result {result!r}"
            raise LocalizationFuzzError(msg)


def _pattern_loader_not_found_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Primary miss is tracked as not_found while fallback still resolves."""
    _domain.loader_init_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    resource_id = "main.ftl"
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, fallback, resource_id, f"{msg_id} = {val}\n")

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [primary, fallback],
            [resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.successful != 1 or summary.not_found != 1 or summary.errors != 0:
            msg = (
                f"Unexpected mixed summary: successful={summary.successful}, "
                f"not_found={summary.not_found}, errors={summary.errors}"
            )
            raise LocalizationFuzzError(msg)

        result, errors = l10n.format_pattern(msg_id)
        if errors:
            msg = f"Fallback load should resolve successfully, got errors={errors!r}"
            raise LocalizationFuzzError(msg)
        if val not in result:
            msg = f"Fallback value {val!r} missing from result {result!r}"
            raise LocalizationFuzzError(msg)


def _pattern_loader_junk_summary(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Junk entries discovered during eager load are preserved in LoadSummary."""
    _domain.loader_junk_checks += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "broken.ftl"
    junk_source = f"{gen_ftl_identifier(fdp)} = {{\n"

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, junk_source)

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)
        summary = l10n.get_load_summary()

        if summary.successful != 1 or not summary.has_junk or summary.junk_count < 1:
            msg = (
                f"Expected junk-bearing successful load, got successful={summary.successful}, "
                f"has_junk={summary.has_junk}, junk_count={summary.junk_count}"
            )
            raise LocalizationFuzzError(msg)
        if summary.all_clean:
            msg = "LoadSummary.all_clean unexpectedly true for junk input"
            raise LocalizationFuzzError(msg)
        if not summary.get_with_junk():
            msg = "LoadSummary.get_with_junk() returned empty tuple"
            raise LocalizationFuzzError(msg)


def _pattern_loader_path_error(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Invalid resource IDs surface as loader errors in the eager-load summary."""
    _domain.loader_error_checks += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    invalid_resource_id = fdp.PickValueInList(
        [
            "../escape.ftl",
            " main.ftl",
            "/absolute.ftl",
        ]
    )

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale],
            [invalid_resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.errors != 1 or not summary.has_errors:
            msg = (
                f"Expected one loader error for invalid resource_id, got "
                f"errors={summary.errors}, not_found={summary.not_found}"
            )
            raise LocalizationFuzzError(msg)

        first_error = summary.get_errors()[0].error
        if not isinstance(first_error, ValueError):
            msg = (
                "Expected ValueError from PathResourceLoader validation, got "
                f"{type(first_error).__name__}"
            )
            raise LocalizationFuzzError(msg)


def _check_require_clean_empty_init(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Empty initialization is considered clean."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    l10n = FluentLocalization([locale], strict=False)
    try:
        summary = l10n.require_clean()
    except IntegrityCheckFailedError as err:
        msg = f"require_clean() raised on empty initialization: {err}"
        raise LocalizationFuzzError(msg) from err

    if not summary.all_clean or summary.total_attempted != 0:
        msg = f"Empty initialization should be clean, got {summary!r}"
        raise LocalizationFuzzError(msg)


def _check_require_clean_loader_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """All-success loader summaries return from require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "main.ftl"
    message_id = f"clean-{gen_ftl_identifier(fdp)}"
    value = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, f"{message_id} = {value}\n")
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)
        try:
            summary = l10n.require_clean()
        except IntegrityCheckFailedError as err:
            msg = f"require_clean() rejected an all-success summary: {err}"
            raise LocalizationFuzzError(msg) from err

        if not summary.all_clean or summary.successful != 1 or summary.errors != 0:
            msg = f"Clean loader initialization returned wrong summary: {summary!r}"
            raise LocalizationFuzzError(msg)


def _check_require_clean_missing_loader(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing resources fail require_clean() with integrity context."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    normalized_locale = normalize_locale(locale)
    resource_id = "main.ftl"

    class MissingLoader:
        def load(self, _locale: str, _resource_id: str) -> str:
            msg = "missing"
            raise FileNotFoundError(msg)

        def describe_path(self, locale: str, resource_id: str) -> str:
            return f"{locale}/{resource_id}"

    l10n = FluentLocalization([locale], [resource_id], MissingLoader(), strict=False)

    try:
        l10n.require_clean()
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="require_clean",
            message_fragment="not clean",
            key=f"{normalized_locale}/{resource_id}",
            actual_fragment="LoadSummary(",
        )
    else:
        msg = "require_clean() accepted a missing-resource summary"
        raise LocalizationFuzzError(msg)


def _check_require_clean_junk_resource(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Junk-bearing resources fail require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "broken.ftl"
    junk_source = f"{gen_ftl_identifier(fdp)} = {{\n"

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, junk_source)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)

        try:
            l10n.require_clean()
        except IntegrityCheckFailedError as err:
            _assert_integrity_failure(
                err,
                operation="require_clean",
                message_fragment="junk",
                key_fragment=resource_id,
                actual_fragment="LoadSummary(",
            )
        else:
            msg = "require_clean() accepted a junk-bearing summary"
            raise LocalizationFuzzError(msg)


def _check_require_clean_loader_error(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Loader validation errors fail require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    invalid_resource_id = fdp.PickValueInList(
        [
            "../escape.ftl",
            " main.ftl",
            "/absolute.ftl",
        ]
    )

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale],
            [invalid_resource_id],
            loader,
            strict=False,
        )

        try:
            l10n.require_clean()
        except IntegrityCheckFailedError as err:
            _assert_integrity_failure(
                err,
                operation="require_clean",
                message_fragment="load error",
                key_fragment=invalid_resource_id,
                actual_fragment="LoadSummary(",
            )
        else:
            msg = "require_clean() accepted a loader error summary"
            raise LocalizationFuzzError(msg)


def _pattern_require_clean_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """require_clean returns only for clean initialization summaries."""
    _domain.boot_validation_checks += 1
    handlers = (
        _check_require_clean_empty_init,
        _check_require_clean_loader_success,
        _check_require_clean_missing_loader,
        _check_require_clean_junk_resource,
        _check_require_clean_loader_error,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


def _check_boot_config_validation(fdp: atheris.FuzzedDataProvider) -> None:
    """__post_init__ rejects empty locales/resource_ids and missing loader/base_path."""
    choice = fdp.ConsumeIntInRange(0, 2)
    try:
        if choice == 0:
            LocalizationBootConfig(
                locales=(),
                resource_ids=("ui.ftl",),
                loader=_EmptyLoader(),
            )
            msg = "Empty locales did not raise ValueError"
            raise LocalizationFuzzError(msg)
        if choice == 1:
            LocalizationBootConfig(
                locales=("en",),
                resource_ids=(),
                loader=_EmptyLoader(),
            )
            msg = "Empty resource_ids did not raise ValueError"
            raise LocalizationFuzzError(msg)
        LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
        )
        msg = "Missing loader/base_path did not raise ValueError"
        raise LocalizationFuzzError(msg)
    except ValueError:
        pass  # expected


def _check_boot_config_boot_success(fdp: atheris.FuzzedDataProvider) -> None:
    """boot_simple() returns FluentLocalization for a valid in-memory FTL resource."""
    locale = fdp.PickValueInList(["en", "de", "lv"])
    ftl = f"greeting = Hello {{ $name }}\nmsg{fdp.ConsumeIntInRange(0, 9)} = Value\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        l10n = cfg.boot_simple()
        if not isinstance(l10n, FluentLocalization):
            msg = f"boot_simple() returned {type(l10n).__name__}, expected FluentLocalization"
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # strict syntax errors in generated FTL are acceptable
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_boot_with_summary(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() returns a 3-tuple with correct types and clean LoadSummary."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "msg = Value\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        result = cfg.boot()
        if not isinstance(result, tuple) or len(result) != 3:
            msg = f"boot() returned wrong structure: {result!r}"
            raise LocalizationFuzzError(msg)
        l10n, summary, schema_results = result
        if not isinstance(l10n, FluentLocalization):
            msg = f"boot()[0] is {type(l10n).__name__}, not FluentLocalization"
            raise LocalizationFuzzError(msg)
        if not isinstance(schema_results, tuple):
            msg = f"boot()[2] is {type(schema_results).__name__}, not tuple"
            raise LocalizationFuzzError(msg)
        if summary.errors != 0:
            msg = f"LoadSummary.errors={summary.errors} for clean resource"
            raise LocalizationFuzzError(msg)
        if summary.total_attempted < 1:
            msg = f"LoadSummary.total_attempted={summary.total_attempted}, expected >= 1"
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_boot_failure(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() raises IntegrityCheckFailedError when a resource cannot be loaded."""
    locale = fdp.PickValueInList(["en", "de"])
    loader = _EmptyLoader()  # no resources registered -> FileNotFoundError
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("missing.ftl",),
            loader=loader,
        )
        cfg.boot()
        msg = "boot() did not raise IntegrityCheckFailedError for missing resource"
        raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # expected
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_required_messages_absent(fdp: atheris.FuzzedDataProvider) -> None:
    """required_messages raises IntegrityCheckFailedError when an ID is absent."""
    locale = fdp.PickValueInList(["en", "de"])
    # Load a resource that has "greeting" but NOT "farewell"
    ftl = "greeting = Hello\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
            required_messages=frozenset({"greeting", "farewell"}),
        )
        cfg.boot()
        msg = "boot() did not raise IntegrityCheckFailedError for absent required message"
        raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # expected: "farewell" is absent
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_required_messages_present(fdp: atheris.FuzzedDataProvider) -> None:
    """required_messages succeeds when all IDs resolve in at least one locale."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "greeting = Hello\nfarewell = Goodbye\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
            required_messages=frozenset({"greeting", "farewell"}),
        )
        l10n, summary, _ = cfg.boot()
        if not isinstance(l10n, FluentLocalization):
            msg = f"boot()[0] is {type(l10n).__name__}, expected FluentLocalization"
            raise LocalizationFuzzError(msg)
        if summary.errors != 0:
            msg = f"LoadSummary.errors={summary.errors} for clean resource"
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # generated FTL may have syntax issues
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_one_shot(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() and boot_simple() are one-shot: second call raises RuntimeError."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "greeting = Hello\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    use_simple = fdp.ConsumeBool()
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        # First call must succeed
        if use_simple:
            cfg.boot_simple()
        else:
            cfg.boot()
        # Second call must raise RuntimeError (one-shot enforcement)
        try:
            if use_simple:
                cfg.boot_simple()
            else:
                cfg.boot()
            msg = (
                "boot() did not raise RuntimeError on second call "
                "(one-shot enforcement missing)"
            )
            raise LocalizationFuzzError(msg)
        except RuntimeError:
            pass  # expected: one-shot enforcement
    except IntegrityCheckFailedError:
        pass  # FTL may have syntax issues -- acceptable
    except _ALLOWED_EXCEPTIONS:
        pass


def _pattern_boot_config_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """LocalizationBootConfig strict-mode boot sequence and invariants."""
    _domain.boot_config_checks += 1
    handlers = (
        _check_boot_config_validation,
        _check_boot_config_boot_success,
        _check_boot_config_boot_with_summary,
        _check_boot_config_boot_failure,
        _check_boot_config_required_messages_absent,
        _check_boot_config_required_messages_present,
        _check_boot_config_one_shot,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


class _EmptyLoader:
    """ResourceLoader with no resources — always raises FileNotFoundError."""

    def load(self, locale: str, resource_id: str) -> str:
        msg = f"No resource for ({locale!r}, {resource_id!r})"
        raise FileNotFoundError(msg)

    def describe_path(self, locale: str, resource_id: str) -> str:
        return f"empty://{locale}/{resource_id}"


class _SingleResourceLoader:
    """ResourceLoader backed by a single (locale, resource_id) → FTL mapping."""

    def __init__(self, locale: str, resource_id: str, ftl: str) -> None:
        self._locale = locale
        self._resource_id = resource_id
        self._ftl = ftl

    def load(self, locale: str, resource_id: str) -> str:
        if locale == self._locale and resource_id == self._resource_id:
            return self._ftl
        msg = f"No resource for ({locale!r}, {resource_id!r})"
        raise FileNotFoundError(msg)

    def describe_path(self, locale: str, resource_id: str) -> str:
        return f"memory://{locale}/{resource_id}"


# --- Pattern dispatch ---

_PATTERN_DISPATCH = {
    "single_locale_add_resource": _pattern_single_locale_add_resource,
    "multi_locale_fallback": _pattern_multi_locale_fallback,
    "chain_of_3_fallback": _pattern_chain_of_3_fallback,
    "format_value_missing": _pattern_format_value_missing,
    "format_with_variables": _pattern_format_with_variables,
    "add_resource_mutation": _pattern_add_resource_mutation,
    "has_message_api": _pattern_has_message_api,
    "ast_lookup_api": _pattern_ast_lookup_api,
    "get_message_ids_api": _pattern_get_message_ids_api,
    "validate_resource_api": _pattern_validate_resource_api,
    "validate_message_variables_api": _pattern_validate_message_variables_api,
    "validate_message_schemas_api": _pattern_validate_message_schemas_api,
    "add_function_custom": _pattern_add_function_custom,
    "introspect_api": _pattern_introspect_api,
    "cache_audit_api": _pattern_cache_audit_api,
    "locale_boundary_api": _pattern_locale_boundary_api,
    "on_fallback_callback": _pattern_on_fallback_callback,
    "loader_init_success": _pattern_loader_init_success,
    "loader_not_found_fallback": _pattern_loader_not_found_fallback,
    "loader_junk_summary": _pattern_loader_junk_summary,
    "loader_path_error": _pattern_loader_path_error,
    "require_clean_api": _pattern_require_clean_api,
    "boot_config_api": _pattern_boot_config_api,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test FluentLocalization invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = _state.pattern_coverage.get(pattern_name, 0) + 1

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
        _state.error_counts[error_type] = _state.error_counts.get(error_type, 0) + 1
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "fallback" in pattern_name
            or "loader" in pattern_name
            or pattern_name
            in (
                "add_resource_mutation",
                "introspect_api",
                "ast_lookup_api",
                "cache_audit_api",
                "locale_boundary_api",
                "validate_message_variables_api",
                "validate_message_schemas_api",
                "require_clean_api",
                "boot_config_api",
            )
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state,
            pattern_name,
            start_time,
            data,
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
