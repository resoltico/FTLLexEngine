#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: integrity - Semantic Validation and Data Integrity
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Semantic Validation and Data Integrity Fuzzer (Atheris).

Targets:
- ftllexengine.validation.validate_resource (standalone 6-pass validation)
- ftllexengine.syntax.validator.SemanticValidator (Fluent spec E0001-E0013)
- ftllexengine.integrity (DataIntegrityError hierarchy)
- FluentBundle strict mode (SyntaxIntegrityError, FormattingIntegrityError)

Concern boundary: This fuzzer targets the validation gauntlet -- semantic integrity
checks, cross-resource validation, chain depth limits, strict mode enforcement,
and DataIntegrityError triggering. This is distinct from:
- fuzz_roundtrip: Parser-serializer convergence (no validation checks)
- fuzz_structured: Grammar coverage (no cross-resource, no strict mode)
- fuzz_runtime: Resolver/cache stack (runtime, not validation)
- fuzz_graph: Direct cycle detection API (algorithm, not integration)

Pattern categories (25 patterns):
- VALIDATION (10): Standalone validate_resource() with various inputs
- SEMANTIC (6): SemanticValidator (E0001-E0013) targeted violations
- STRICT_MODE (5): DataIntegrityError triggering in strict FluentBundle
- CROSS_RESOURCE (4): Multi-resource dependency and conflict scenarios

Metrics:
- Validation code classification (VALIDATION_*, E0001-E0013)
- Strict mode exception tracking (SyntaxIntegrityError, FormattingIntegrityError)
- Cross-resource conflict detection
- Chain depth violation detection
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Capture (for check_dependencies) ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:  # noqa: SIM105 - captures module for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - captures module for check_dependencies
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

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Type Aliases (PEP 695) ---
type FuzzStats = dict[str, int | str | float]

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.constants import MAX_DEPTH
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.integrity import (
        DataIntegrityError,
        FormattingIntegrityError,
        SyntaxIntegrityError,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.validation import validate_resource


# --- Report Directory ---
import pathlib  # noqa: E402  # pylint: disable=C0411,C0412,C0413

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "integrity"


# --- Domain-Specific Metrics ---
@dataclass
class IntegrityMetrics:
    """Domain-specific metrics for integrity fuzzing."""

    # Validation code tracking
    validation_codes: dict[str, int] = field(default_factory=dict)

    # Exception tracking
    syntax_integrity_errors: int = 0
    formatting_integrity_errors: int = 0
    immutability_violations: int = 0
    data_integrity_errors: int = 0

    # Validation result tracking
    total_errors: int = 0
    total_warnings: int = 0
    total_annotations: int = 0

    # Cross-resource tracking
    cross_resource_tests: int = 0
    cross_resource_conflicts: int = 0

    # Chain depth tracking
    chain_depth_violations: int = 0

    # Strict mode tracking
    strict_mode_tests: int = 0
    non_strict_tests: int = 0


# --- Global State ---
_state = BaseFuzzerState()
_domain = IntegrityMetrics()

# --- Shared Parser (reused across iterations) ---
_parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=100)


# --- Pattern Weights ---
# 25 patterns across 4 categories
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # VALIDATION (10 patterns) - Standalone validate_resource()
    ("valid_simple", 8),
    ("valid_complex", 6),
    ("syntax_errors", 8),
    ("undefined_refs", 10),
    ("circular_2way", 8),
    ("circular_3way", 6),
    ("circular_self", 6),
    ("duplicate_ids", 8),
    ("chain_depth_limit", 10),
    ("mixed_issues", 6),
    # SEMANTIC (6 patterns) - SemanticValidator violations
    ("semantic_no_default", 8),
    ("semantic_duplicate_variant", 6),
    ("semantic_duplicate_named_arg", 6),
    ("semantic_term_positional", 6),
    ("semantic_no_variants", 6),
    ("semantic_combined", 5),
    # STRICT_MODE (5 patterns) - DataIntegrityError triggering
    ("strict_syntax_junk", 10),
    ("strict_format_missing", 8),
    ("strict_format_cycle", 6),
    ("strict_add_invalid", 8),
    ("strict_combined", 5),
    # CROSS_RESOURCE (4 patterns) - Multi-resource scenarios
    ("cross_shadow", 8),
    ("cross_cycle", 10),
    ("cross_undefined", 8),
    ("cross_chain_depth", 6),
)

_PATTERN_NAMES = tuple(name for name, _ in _PATTERN_WEIGHTS)
_PATTERN_WEIGHT_VALUES = tuple(w for _, w in _PATTERN_WEIGHTS)
_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(_PATTERN_NAMES, _PATTERN_WEIGHT_VALUES)

# Register intended weights for skew detection
for _name, _weight in _PATTERN_WEIGHTS:
    _state.pattern_intended_weights[_name] = float(_weight)


# --- Test Locales ---
_TEST_LOCALES: Sequence[str] = ("en-US", "de-DE", "ja-JP", "ar-SA", "root")


# --- Stats and Reporting ---
def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["syntax_integrity_errors"] = _domain.syntax_integrity_errors
    stats["formatting_integrity_errors"] = _domain.formatting_integrity_errors
    stats["immutability_violations"] = _domain.immutability_violations
    stats["data_integrity_errors"] = _domain.data_integrity_errors
    stats["total_errors"] = _domain.total_errors
    stats["total_warnings"] = _domain.total_warnings
    stats["total_annotations"] = _domain.total_annotations
    stats["cross_resource_tests"] = _domain.cross_resource_tests
    stats["cross_resource_conflicts"] = _domain.cross_resource_conflicts
    stats["chain_depth_violations"] = _domain.chain_depth_violations
    stats["strict_mode_tests"] = _domain.strict_mode_tests
    stats["non_strict_tests"] = _domain.non_strict_tests

    # Top validation codes
    for code, count in sorted(
        _domain.validation_codes.items(), key=lambda x: -x[1]
    )[:20]:
        stats[f"vcode_{code}"] = count

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_integrity_report.json")


atexit.register(_emit_report)


# --- Helper Functions ---
def _generate_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate locale (90% valid, 10% fuzzed)."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_TEST_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 10))


def _track_validation_result(result: Any) -> None:
    """Track validation result codes."""
    if hasattr(result, "errors"):
        _domain.total_errors += len(result.errors)
        for error in result.errors:
            code = getattr(error, "code", "UNKNOWN")
            _domain.validation_codes[code] = _domain.validation_codes.get(code, 0) + 1

    if hasattr(result, "warnings"):
        _domain.total_warnings += len(result.warnings)
        for warning in result.warnings:
            code = getattr(warning, "code", "UNKNOWN")
            _domain.validation_codes[code] = _domain.validation_codes.get(code, 0) + 1

    if hasattr(result, "annotations"):
        _domain.total_annotations += len(result.annotations)
        for annotation in result.annotations:
            code = getattr(annotation, "code", "UNKNOWN")
            _domain.validation_codes[code] = _domain.validation_codes.get(code, 0) + 1


# --- Pattern Handlers ---

# VALIDATION patterns (standalone validate_resource)

def _pattern_valid_simple(fdp: atheris.FuzzedDataProvider) -> None:
    """Valid simple messages."""
    idx = fdp.ConsumeIntInRange(0, 999)
    ftl = f"msg_{idx} = Simple value {{ $var }}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_valid_complex(fdp: atheris.FuzzedDataProvider) -> None:
    """Valid complex resource."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"""# Resource {idx}
msg_{idx}_a = First {{ $x }}
msg_{idx}_b = {{ msg_{idx}_a }}
-term_{idx} = Term value
msg_{idx}_c = {{ -term_{idx} }}
msg_{idx}_d = {{ $count ->
    [one] One
   *[other] Many
}}
"""
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_syntax_errors(fdp: atheris.FuzzedDataProvider) -> None:
    """Syntax errors (Junk entries)."""
    choice = fdp.ConsumeIntInRange(0, 4)
    ftl = [
        "msg = { unclosed\n",
        "123invalid = value\n",
        "msg = { }\n",
        "= no identifier\n",
        "msg\n",
    ][choice]
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_undefined_refs(fdp: atheris.FuzzedDataProvider) -> None:
    """Undefined references."""
    choice = fdp.ConsumeIntInRange(0, 3)
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = [
        f"msg_{idx} = {{ undefined_msg }}\n",
        f"msg_{idx} = {{ -undefined_term }}\n",
        f"msg_{idx} = {{ other.attr }}\n",
        f"msg_{idx} = {{ -term.undefined_attr }}\n",
    ][choice]
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_circular_2way(fdp: atheris.FuzzedDataProvider) -> None:
    """2-way circular reference."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"msg_{idx}_a = {{ msg_{idx}_b }}\nmsg_{idx}_b = {{ msg_{idx}_a }}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_circular_3way(fdp: atheris.FuzzedDataProvider) -> None:
    """3-way circular reference."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"""msg_{idx}_a = {{ msg_{idx}_b }}
msg_{idx}_b = {{ msg_{idx}_c }}
msg_{idx}_c = {{ msg_{idx}_a }}
"""
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_circular_self(fdp: atheris.FuzzedDataProvider) -> None:
    """Self-referential message."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"msg_{idx} = {{ msg_{idx} }}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_duplicate_ids(fdp: atheris.FuzzedDataProvider) -> None:
    """Duplicate message/term IDs."""
    idx = fdp.ConsumeIntInRange(0, 99)
    choice = fdp.ConsumeIntInRange(0, 2)
    ftl = [
        f"msg_{idx} = First\nmsg_{idx} = Second\n",
        f"-term_{idx} = First\n-term_{idx} = Second\n",
        f"msg_{idx} = Value\n    .attr = First\n    .attr = Second\n",
    ][choice]
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_chain_depth_limit(fdp: atheris.FuzzedDataProvider) -> None:
    """Chain depth exceeding MAX_DEPTH."""
    # Generate chain of MAX_DEPTH + 5 to trigger violation
    depth = MAX_DEPTH + fdp.ConsumeIntInRange(5, 20)
    idx = fdp.ConsumeIntInRange(0, 99)
    lines = [f"msg_{idx}_{i} = {{ msg_{idx}_{i + 1} }}" for i in range(depth)]
    lines.append(f"msg_{idx}_{depth} = End")
    ftl = "\n".join(lines) + "\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)
    # Check if chain depth warning was emitted
    if hasattr(result, "warnings"):
        for w in result.warnings:
            if "CHAIN_DEPTH" in getattr(w, "code", ""):
                _domain.chain_depth_violations += 1


def _pattern_mixed_issues(fdp: atheris.FuzzedDataProvider) -> None:
    """Mixed validation issues."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"""msg_{idx}_a = {{ undefined }}
msg_{idx}_b = {{ msg_{idx}_c }}
msg_{idx}_c = {{ msg_{idx}_b }}
msg_{idx}_d = Value
msg_{idx}_d = Duplicate
"""
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


# SEMANTIC patterns (SemanticValidator E0001-E0013)

def _pattern_semantic_no_default(fdp: atheris.FuzzedDataProvider) -> None:
    """Select expression without default variant."""
    idx = fdp.ConsumeIntInRange(0, 99)
    # Parser requires a default, but we test validation anyway
    ftl = f"msg_{idx} = {{ $x ->\n    [one] One\n    [other] Other\n}}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_semantic_duplicate_variant(fdp: atheris.FuzzedDataProvider) -> None:
    """Select expression with duplicate variant keys."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"msg_{idx} = {{ $x ->\n    [one] First\n    [one] Second\n   *[other] Other\n}}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_semantic_duplicate_named_arg(fdp: atheris.FuzzedDataProvider) -> None:
    """Function call with duplicate named arguments."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f'msg_{idx} = {{ NUMBER($val, style: "decimal", style: "percent") }}\n'
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_semantic_term_positional(fdp: atheris.FuzzedDataProvider) -> None:
    """Term reference with positional arguments (ignored at runtime)."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f'-term_{idx} = Value\nmsg_{idx} = {{ -term_{idx}("positional") }}\n'
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_semantic_no_variants(fdp: atheris.FuzzedDataProvider) -> None:
    """Select expression parse error (malformed)."""
    idx = fdp.ConsumeIntInRange(0, 99)
    # This creates a Junk entry (parser rejects empty select)
    ftl = f"msg_{idx} = {{ $x -> }}\n"
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


def _pattern_semantic_combined(fdp: atheris.FuzzedDataProvider) -> None:
    """Combined semantic issues."""
    idx = fdp.ConsumeIntInRange(0, 99)
    ftl = f"""-term_{idx} = T
msg_{idx} = {{ -term_{idx}("pos", x: 1, x: 2) }}
msg_{idx}_b = {{ $y ->
    [a] A
    [a] Dup
   *[b] B
}}
"""
    result = validate_resource(ftl, parser=_parser)
    _track_validation_result(result)


# STRICT_MODE patterns (DataIntegrityError triggering)

def _pattern_strict_syntax_junk(fdp: atheris.FuzzedDataProvider) -> None:
    """Strict mode: syntax error triggers SyntaxIntegrityError."""
    _domain.strict_mode_tests += 1
    locale = _generate_locale(fdp)
    try:
        bundle = FluentBundle(locale, strict=True)
        bundle.add_resource("msg = { unclosed\n")
    except SyntaxIntegrityError:
        _domain.syntax_integrity_errors += 1
    except (ValueError, TypeError, DataIntegrityError):
        _domain.data_integrity_errors += 1


def _pattern_strict_format_missing(fdp: atheris.FuzzedDataProvider) -> None:
    """Strict mode: format missing message triggers FormattingIntegrityError."""
    _domain.strict_mode_tests += 1
    locale = _generate_locale(fdp)
    try:
        bundle = FluentBundle(locale, strict=True)
        bundle.add_resource("msg = Hello\n")
        # Try to format non-existent message
        bundle.format_pattern("nonexistent", {})
    except FormattingIntegrityError:
        _domain.formatting_integrity_errors += 1
    except (ValueError, TypeError, KeyError, DataIntegrityError):
        _domain.data_integrity_errors += 1
    except FrozenFluentError:
        pass  # Expected in strict mode


def _pattern_strict_format_cycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Strict mode: format cyclic message."""
    _domain.strict_mode_tests += 1
    locale = _generate_locale(fdp)
    try:
        # Non-strict add to get cyclic messages in
        bundle_nonstrict = FluentBundle(locale, strict=False)
        bundle_nonstrict.add_resource("a = { b }\nb = { a }\n")
        # Try to format (would trigger cycle detection)
        bundle_nonstrict.format_pattern("a", {})
    except (RecursionError, DataIntegrityError, FrozenFluentError):
        _domain.data_integrity_errors += 1


def _pattern_strict_add_invalid(fdp: atheris.FuzzedDataProvider) -> None:
    """Strict mode: add resource with multiple syntax errors."""
    _domain.strict_mode_tests += 1
    locale = _generate_locale(fdp)
    try:
        bundle = FluentBundle(locale, strict=True)
        bundle.add_resource("bad = {\ninvalid = {\nalso = {\n")
    except SyntaxIntegrityError as e:
        _domain.syntax_integrity_errors += 1
        # Verify junk_entries are captured
        if hasattr(e, "junk_entries") and len(e.junk_entries) > 0:
            pass  # Good: exception carries context
    except (ValueError, TypeError, DataIntegrityError):
        _domain.data_integrity_errors += 1


def _pattern_strict_combined(fdp: atheris.FuzzedDataProvider) -> None:
    """Strict mode: combined scenarios."""
    _domain.strict_mode_tests += 1
    locale = _generate_locale(fdp)
    choice = fdp.ConsumeIntInRange(0, 2)
    try:
        bundle = FluentBundle(locale, strict=True)
        if choice == 0:
            bundle.add_resource("= no id\n")
        elif choice == 1:
            bundle.add_resource("msg = { $x ->\n")
        else:
            bundle.add_resource("123 = invalid id\n")
    except SyntaxIntegrityError:
        _domain.syntax_integrity_errors += 1
    except (ValueError, TypeError, DataIntegrityError):
        _domain.data_integrity_errors += 1


# CROSS_RESOURCE patterns (multi-resource scenarios)

def _pattern_cross_shadow(fdp: atheris.FuzzedDataProvider) -> None:
    """Cross-resource: shadowing existing entry."""
    _domain.cross_resource_tests += 1
    idx = fdp.ConsumeIntInRange(0, 99)
    # Simulate: first resource defined msg_{idx}, second resource shadows it
    ftl2 = f"msg_{idx} = Shadow\n"

    # Validate second with known_messages context
    result = validate_resource(
        ftl2,
        parser=_parser,
        known_messages=frozenset([f"msg_{idx}"]),
    )
    _track_validation_result(result)
    # Check for shadow warning
    if hasattr(result, "warnings"):
        for w in result.warnings:
            if "SHADOW" in getattr(w, "code", ""):
                _domain.cross_resource_conflicts += 1


def _pattern_cross_cycle(fdp: atheris.FuzzedDataProvider) -> None:
    """Cross-resource: cycle spanning resources."""
    _domain.cross_resource_tests += 1
    idx = fdp.ConsumeIntInRange(0, 99)
    # Resource 1 has msg_a -> msg_b (msg_b is in resource 2)
    # Resource 2 has msg_b -> msg_a (creates cycle)

    # Validate resource 2 with known deps from resource 1
    ftl2 = f"msg_{idx}_b = {{ msg_{idx}_a }}\n"
    result = validate_resource(
        ftl2,
        parser=_parser,
        known_messages=frozenset([f"msg_{idx}_a"]),
        known_msg_deps={f"msg_{idx}_a": {f"msg:msg_{idx}_b"}},
    )
    _track_validation_result(result)
    # Check for circular reference
    if hasattr(result, "warnings"):
        for w in result.warnings:
            if "CIRCULAR" in getattr(w, "code", ""):
                _domain.cross_resource_conflicts += 1


def _pattern_cross_undefined(fdp: atheris.FuzzedDataProvider) -> None:
    """Cross-resource: reference resolved by known_messages."""
    _domain.cross_resource_tests += 1
    idx = fdp.ConsumeIntInRange(0, 99)
    # msg_a references msg_b which is in known_messages
    ftl = f"msg_{idx}_a = {{ msg_{idx}_b }}\n"

    # Without known_messages: undefined
    result1 = validate_resource(ftl, parser=_parser)
    _track_validation_result(result1)

    # With known_messages: resolved
    result2 = validate_resource(
        ftl,
        parser=_parser,
        known_messages=frozenset([f"msg_{idx}_b"]),
    )
    _track_validation_result(result2)


def _pattern_cross_chain_depth(fdp: atheris.FuzzedDataProvider) -> None:
    """Cross-resource: chain depth violation across resources."""
    _domain.cross_resource_tests += 1
    idx = fdp.ConsumeIntInRange(0, 99)

    # Simulate existing chain of MAX_DEPTH-5 in known deps
    existing_depth = MAX_DEPTH - 5
    known_deps: dict[str, set[str]] = {}
    for i in range(existing_depth):
        known_deps[f"chain_{idx}_{i}"] = {f"msg:chain_{idx}_{i + 1}"}

    # New resource adds 10 more levels -> exceeds MAX_DEPTH
    new_chain = [f"ext_{idx}_{i} = {{ ext_{idx}_{i + 1} }}" for i in range(10)]
    new_chain.append(f"ext_{idx}_10 = {{ chain_{idx}_0 }}")
    ftl = "\n".join(new_chain) + "\n"

    result = validate_resource(
        ftl,
        parser=_parser,
        known_messages=frozenset(known_deps.keys()),
        known_msg_deps=known_deps,
    )
    _track_validation_result(result)


# --- Pattern Dispatch ---
_PATTERN_DISPATCH: dict[str, Any] = {
    # VALIDATION
    "valid_simple": _pattern_valid_simple,
    "valid_complex": _pattern_valid_complex,
    "syntax_errors": _pattern_syntax_errors,
    "undefined_refs": _pattern_undefined_refs,
    "circular_2way": _pattern_circular_2way,
    "circular_3way": _pattern_circular_3way,
    "circular_self": _pattern_circular_self,
    "duplicate_ids": _pattern_duplicate_ids,
    "chain_depth_limit": _pattern_chain_depth_limit,
    "mixed_issues": _pattern_mixed_issues,
    # SEMANTIC
    "semantic_no_default": _pattern_semantic_no_default,
    "semantic_duplicate_variant": _pattern_semantic_duplicate_variant,
    "semantic_duplicate_named_arg": _pattern_semantic_duplicate_named_arg,
    "semantic_term_positional": _pattern_semantic_term_positional,
    "semantic_no_variants": _pattern_semantic_no_variants,
    "semantic_combined": _pattern_semantic_combined,
    # STRICT_MODE
    "strict_syntax_junk": _pattern_strict_syntax_junk,
    "strict_format_missing": _pattern_strict_format_missing,
    "strict_format_cycle": _pattern_strict_format_cycle,
    "strict_add_invalid": _pattern_strict_add_invalid,
    "strict_combined": _pattern_strict_combined,
    # CROSS_RESOURCE
    "cross_shadow": _pattern_cross_shadow,
    "cross_cycle": _pattern_cross_cycle,
    "cross_undefined": _pattern_cross_undefined,
    "cross_chain_depth": _pattern_cross_chain_depth,
}


# --- Allowed Exceptions ---
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    KeyError,
    RecursionError,
    MemoryError,
    DataIntegrityError,
    FrozenFluentError,
)


# --- Fuzzer Entry Point ---
def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test validation and integrity stack.

    Observability:
    - Performance: Tracks timing per iteration (ms)
    - Memory: Tracks RSS via psutil (every 100 iterations)
    - Validation: Error/warning/annotation code tracking
    - DataIntegrity: Exception type counting
    - Patterns: 25 integrity-focused pattern types
    """
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

    if fdp.remaining_bytes() < 2:
        return

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            pattern.startswith(("strict_", "cross_"))
            or "chain_depth" in pattern
            or (time.perf_counter() - start_time) * 1000 > 10.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the integrity fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Semantic validation and data integrity fuzzer using Atheris/libFuzzer",
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
        default=1000,
        help="Maximum size of in-memory seed corpus (default: 1000)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    # Inject RSS limit if not specified
    if not any(arg.startswith("-rss_limit_mb") for arg in sys.argv):
        sys.argv.append("-rss_limit_mb=4096")

    print()
    print("=" * 80)
    print("Semantic Validation and Data Integrity Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     validate_resource, SemanticValidator, DataIntegrityError")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Routing:    Round-robin weighted schedule (length: {len(_PATTERN_SCHEDULE)})")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)} (10 validation + 6 semantic + 5 strict + 4 cross)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
