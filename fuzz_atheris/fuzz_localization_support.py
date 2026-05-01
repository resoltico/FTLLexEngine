"""Shared state, imports, and constants for the localization Atheris fuzzer."""

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

atheris = cast("Any", _atheris_mod)

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

_ALLOWED_EXCEPTIONS = (
    ValueError,  # empty locale list, locale not in chain, whitespace
    TypeError,  # invalid argument types
    UnicodeEncodeError,  # surrogate characters in FTL source
)
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
    stats = cast("dict[str, Any]", build_base_stats_dict(_state))
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


__all__ = [
    "GC_INTERVAL",
    "MAX_LOCALE_LENGTH_HARD_LIMIT",
    "_ALLOWED_EXCEPTIONS",
    "_LOCALE_PAIRS",
    "_LOCALE_TRIPLES",
    "_NON_STRING_LOCALES",
    "_PATTERN_SCHEDULE",
    "_PATTERN_WEIGHTS",
    "_SINGLE_LOCALES",
    "_STRUCTURALLY_INVALID_LOCALES",
    "_VALID_AUDIT_OPERATIONS",
    "Any",
    "CacheAuditLogEntry",
    "CacheConfig",
    "DataIntegrityError",
    "FallbackInfo",
    "FluentLocalization",
    "FormattingIntegrityError",
    "FrozenFluentError",
    "IntegrityCheckFailedError",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
    "LocalizationFuzzError",
    "Message",
    "PathResourceLoader",
    "SyntaxIntegrityError",
    "TemporaryDirectory",
    "Term",
    "_domain",
    "_emit_checkpoint",
    "_state",
    "argparse",
    "atheris",
    "gc",
    "gen_ftl_identifier",
    "gen_ftl_value",
    "get_process",
    "normalize_locale",
    "pathlib",
    "print_fuzzer_banner",
    "record_iteration_metrics",
    "record_memory",
    "require_locale_code",
    "run_fuzzer",
    "select_pattern_round_robin",
    "sys",
    "time",
    "validate_message_variables",
]
