#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: introspection - MessageIntrospection Visitor & Reference Extraction
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""MessageIntrospection Visitor and Reference Extraction Fuzzer (Atheris).

Targets: ftllexengine.introspection.message (IntrospectionVisitor,
         ReferenceExtractor, extract_variables, extract_references,
         extract_references_by_attribute, introspect_message)

Concern boundary: This fuzzer stress-tests the AST introspection layer by
constructing programmatic Message/Term AST nodes and feeding them directly
to the introspection APIs. fuzz_iso covers introspection/iso; the message
introspection visitor (695 lines) has zero other Atheris coverage.

The IntrospectionVisitor and ReferenceExtractor walk arbitrary AST trees with
a MAX_DEPTH guard (prevents stack overflow on adversarial nesting) and a
weakref+threading.Lock result cache. The concern is:
- MAX_DEPTH guard fires correctly on deeply nested patterns
- Thread-safety: weakref cache does not leak across iterations
- Variable extraction: frozenset results are consistent across APIs
- Reference deduplication: same term/message referenced multiple times
  appears only once in the frozenset result
- Attribute scope: extract_references_by_attribute vs extract_references
  return consistent subsets

Unique coverage (not covered by other fuzzers):
- IntrospectionVisitor._visit_expression() over adversarial AST shapes
- ReferenceExtractor.visit_MessageReference/TermReference dispatch
- extract_variables() returns frozenset[str] (immutable, deduplicated)
- extract_references() returns (message_refs, term_refs) pair
- extract_references_by_attribute() returns per-attribute reference sets
- introspect_message() weakref cache lifecycle
- clear_introspection_cache() resets cache without data corruption
- MAX_DEPTH guard: deep SelectExpression trees trigger depth limit
- FluentBundle introspection facade delegation

Patterns (13):
- extract_variables_simple: simple Message with 1-3 variables
- extract_variables_nested: Message with select expr containing variables
- extract_references_msg: Message referencing other messages
- extract_references_term: Message referencing terms
- extract_references_by_attr: attribute-specific reference extraction
- introspect_message_full: full MessageIntrospection object contracts
- introspect_term_full: Term introspection contracts
- function_call_extraction: FunctionReference extraction
- deep_nesting_depth_guard: Triggers MAX_DEPTH guard via nested selects
- adversarial_ast: Programmatic AST with unusual combinations
- cache_invalidation: clear_introspection_cache + re-introspect
- bundle_introspection_facade: Introspection via FluentBundle public API
- validate_variables_schema: validate_message_variables exact/super/subset + immutability

Metrics:
- Pattern coverage with weighted round-robin schedule
- Variables extracted, references extracted
- Depth limit hits
- Cache hits/misses
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
class IntrospectionMetrics:
    """Domain-specific metrics for introspection fuzzer."""

    variables_extracted: int = 0
    references_extracted: int = 0
    depth_limit_hits: int = 0
    cache_operations: int = 0
    bundle_facade_calls: int = 0
    invariant_violations: int = 0
    schema_validations: int = 0  # validate_message_variables calls


class IntrospectionFuzzError(Exception):
    """Raised when an introspection invariant is violated."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,    # invalid FTL identifiers
    TypeError,     # invalid AST node types
    RecursionError,  # pathological AST (shouldn't happen with MAX_DEPTH)
)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    ("extract_variables_simple", 9),
    ("extract_variables_nested", 8),
    ("extract_references_msg", 8),
    ("extract_references_term", 8),
    ("extract_references_by_attr", 7),
    ("introspect_message_full", 8),
    ("introspect_term_full", 7),
    ("function_call_extraction", 7),
    ("deep_nesting_depth_guard", 7),
    ("adversarial_ast", 6),
    ("cache_invalidation", 5),
    ("bundle_introspection_facade", 7),
    ("validate_variables_schema", 8),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)
_PATTERN_INDEX: dict[str, int] = {
    name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)
}

# Attribute names for attribute-scoped testing
_ATTR_NAMES: Sequence[str] = (
    "tooltip", "label", "title", "placeholder", "aria-label",
    "description", "hint", "value",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="introspection",
    fuzzer_target=(
        "introspection.message (IntrospectionVisitor, ReferenceExtractor, "
        "extract_variables, extract_references, introspect_message)"
    ),
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = IntrospectionMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "introspection"
_REPORT_FILENAME = "fuzz_introspection_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["variables_extracted"] = _domain.variables_extracted
    stats["references_extracted"] = _domain.references_extracted
    stats["depth_limit_hits"] = _domain.depth_limit_hits
    stats["cache_operations"] = _domain.cache_operations
    stats["bundle_facade_calls"] = _domain.bundle_facade_calls
    stats["invariant_violations"] = _domain.invariant_violations
    stats["schema_validations"] = _domain.schema_validations
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
    from ftllexengine.constants import MAX_DEPTH
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.introspection.message import (
        MessageVariableValidationResult,
        clear_introspection_cache,
        extract_references,
        extract_references_by_attribute,
        extract_variables,
        introspect_message,
        validate_message_variables,
    )
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.syntax.ast import (
        Attribute,
        CallArguments,
        FunctionReference,
        Identifier,
        Message,
        MessageReference,
        Pattern,
        Placeable,
        SelectExpression,
        Term,
        TermReference,
        TextElement,
        VariableReference,
        Variant,
    )


def _make_identifier(name: str) -> Identifier:
    """Create an Identifier AST node."""
    return Identifier(name=name)


def _make_text(value: str) -> TextElement:
    """Create a TextElement AST node."""
    return TextElement(value=value)


def _make_var_ref(name: str) -> Placeable:
    """Create a Placeable wrapping a VariableReference."""
    return Placeable(expression=VariableReference(id=_make_identifier(name)))


def _make_msg_ref(name: str) -> Placeable:
    """Create a Placeable wrapping a MessageReference."""
    return Placeable(
        expression=MessageReference(
            id=_make_identifier(name), attribute=None
        )
    )


def _make_term_ref(name: str) -> Placeable:
    """Create a Placeable wrapping a TermReference."""
    return Placeable(
        expression=TermReference(
            id=_make_identifier(name),
            attribute=None,
            arguments=CallArguments(positional=(), named=()),
        )
    )


def _make_func_ref(name: str, var: str) -> Placeable:
    """Create a Placeable wrapping a FunctionReference."""
    return Placeable(
        expression=FunctionReference(
            id=_make_identifier(name),
            arguments=CallArguments(
                positional=(VariableReference(id=_make_identifier(var)),),
                named=(),
            ),
        )
    )


def _make_simple_message(
    msg_id: str,
    elements: list[TextElement | Placeable],
) -> Message:
    """Create a simple Message AST node."""
    return Message(
        id=_make_identifier(msg_id),
        value=Pattern(elements=tuple(elements)),
        attributes=(),
        comment=None,
    )


def _make_message_with_attrs(
    msg_id: str,
    elements: list[TextElement | Placeable],
    attrs: list[tuple[str, list[TextElement | Placeable]]],
) -> Message:
    """Create a Message AST node with attributes."""
    attr_nodes = tuple(
        Attribute(
            id=_make_identifier(attr_name),
            value=Pattern(elements=tuple(attr_elems)),
        )
        for attr_name, attr_elems in attrs
    )
    return Message(
        id=_make_identifier(msg_id),
        value=Pattern(elements=tuple(elements)),
        attributes=attr_nodes,
        comment=None,
    )


def _make_select_placeable(
    selector_var: str,
    variant_vars: list[str],
) -> Placeable:
    """Create a SelectExpression placeable with variable selector and variants."""
    variants = []
    for i, var in enumerate(variant_vars):
        key = Identifier(name=f"variant{i}")
        pattern = Pattern(elements=(_make_var_ref(var),))
        variants.append(
            Variant(key=key, value=pattern, default=i == len(variant_vars) - 1)
        )
    return Placeable(
        expression=SelectExpression(
            selector=VariableReference(id=_make_identifier(selector_var)),
            variants=tuple(variants),
        )
    )


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915 - dispatch
    """Atheris entry point: Test introspection visitor invariants."""
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
        pattern_choice = _PATTERN_INDEX[pattern_name]
        msg_id = gen_ftl_identifier(fdp)

        match pattern_choice:
            case 0:  # extract_variables_simple
                n = fdp.ConsumeIntInRange(1, 5)
                var_names = [gen_ftl_identifier(fdp) for _ in range(n)]
                elements: list[Any] = []
                for var in var_names:
                    elements.append(_make_text(gen_ftl_value(fdp, max_length=10)))
                    elements.append(_make_var_ref(var))
                msg = _make_simple_message(msg_id, elements)

                result = extract_variables(msg)
                _domain.variables_extracted += len(result)

                # Contract: all generated variable names must be in the result
                for var in var_names:
                    if var not in result:
                        err_msg = f"extract_variables missing '{var}'"
                        raise IntrospectionFuzzError(err_msg)

                # Contract: result is a frozenset (immutable)
                if not isinstance(result, frozenset):
                    err_msg = f"extract_variables returned {type(result).__name__}"
                    raise IntrospectionFuzzError(err_msg)

            case 1:  # extract_variables_nested (select expression)
                var_selector = gen_ftl_identifier(fdp)
                n = fdp.ConsumeIntInRange(1, 4)
                variant_vars = [gen_ftl_identifier(fdp) for _ in range(n)]
                select_p = _make_select_placeable(var_selector, variant_vars)
                msg = _make_simple_message(msg_id, [select_p])

                result = extract_variables(msg)
                _domain.variables_extracted += len(result)

                # Contract: selector variable must be found
                if var_selector not in result:
                    err_msg = f"select selector '{var_selector}' not in extract_variables"
                    raise IntrospectionFuzzError(err_msg)

            case 2:  # extract_references_msg
                n = fdp.ConsumeIntInRange(1, 4)
                ref_ids = [gen_ftl_identifier(fdp) for _ in range(n)]
                elements = [_make_msg_ref(rid) for rid in ref_ids]
                msg = _make_simple_message(msg_id, elements)

                msg_refs, term_refs = extract_references(msg)
                _domain.references_extracted += len(msg_refs) + len(term_refs)

                # Contract: all generated message refs must be present
                for rid in ref_ids:
                    if rid not in msg_refs:
                        err_msg = f"extract_references missing msg ref '{rid}'"
                        raise IntrospectionFuzzError(err_msg)

                # Contract: term refs must be empty (no terms in this message)
                if term_refs:
                    err_msg = f"extract_references: unexpected term refs: {term_refs}"
                    raise IntrospectionFuzzError(err_msg)

            case 3:  # extract_references_term
                n = fdp.ConsumeIntInRange(1, 4)
                term_ids = [gen_ftl_identifier(fdp) for _ in range(n)]
                elements = [_make_term_ref(tid) for tid in term_ids]
                msg = _make_simple_message(msg_id, elements)

                msg_refs, term_refs = extract_references(msg)
                _domain.references_extracted += len(msg_refs) + len(term_refs)

                # Contract: all generated term refs must be present
                for tid in term_ids:
                    if tid not in term_refs:
                        err_msg = f"extract_references missing term ref '{tid}'"
                        raise IntrospectionFuzzError(err_msg)

            case 4:  # extract_references_by_attr
                attr_name = fdp.PickValueInList(list(_ATTR_NAMES))
                other_attr = fdp.PickValueInList(
                    [a for a in _ATTR_NAMES if a != attr_name]
                )
                ref_id = gen_ftl_identifier(fdp)
                msg = _make_message_with_attrs(
                    msg_id,
                    elements=[_make_text("main")],
                    attrs=[
                        (attr_name, [_make_msg_ref(ref_id)]),
                        (other_attr, [_make_text("other")]),
                    ],
                )

                by_attr = extract_references_by_attribute(msg)
                _domain.references_extracted += sum(
                    len(m) + len(t) for m, t in by_attr.values()
                )

                # Contract: ref_id must be in the correct attribute's refs
                if attr_name in by_attr:
                    attr_msg_refs, _ = by_attr[attr_name]
                    if ref_id not in attr_msg_refs:
                        err_msg = (
                            f"extract_references_by_attribute: '{ref_id}' "
                            f"missing from attr '{attr_name}'"
                        )
                        raise IntrospectionFuzzError(err_msg)

            case 5:  # introspect_message_full
                var_a = gen_ftl_identifier(fdp)
                var_b = gen_ftl_identifier(fdp)
                ref_id = gen_ftl_identifier(fdp)
                elements = [
                    _make_var_ref(var_a),
                    _make_text(" "),
                    _make_var_ref(var_b),
                    _make_text(" "),
                    _make_msg_ref(ref_id),
                ]
                msg = _make_simple_message(msg_id, elements)

                info = introspect_message(msg)
                _domain.cache_operations += 1

                if info is None:
                    err_msg = "introspect_message returned None for valid Message"
                    raise IntrospectionFuzzError(err_msg)

                # Contract: variables from get_variable_names match frozenset
                introspected_vars = info.get_variable_names()
                if not isinstance(introspected_vars, frozenset):
                    err_msg = f"get_variable_names returned {type(introspected_vars).__name__}"
                    raise IntrospectionFuzzError(err_msg)

                for var in (var_a, var_b):
                    if var not in introspected_vars:
                        err_msg = f"introspect_message missing variable '{var}'"
                        raise IntrospectionFuzzError(err_msg)

                # Contract: requires_variable must match get_variable_names
                if not info.requires_variable(var_a):
                    err_msg = f"requires_variable('{var_a}') returned False"
                    raise IntrospectionFuzzError(err_msg)

                _domain.variables_extracted += len(introspected_vars)

            case 6:  # introspect_term_full
                var = gen_ftl_identifier(fdp)
                term = Term(
                    id=_make_identifier(msg_id),
                    value=Pattern(elements=(_make_var_ref(var),)),
                    attributes=(),
                    comment=None,
                )

                info = introspect_message(term)
                _domain.cache_operations += 1

                if info is not None:
                    var_names2: frozenset[str] = info.get_variable_names()
                    if var not in var_names2:
                        err_msg = f"Term introspection missing variable '{var}'"
                        raise IntrospectionFuzzError(err_msg)
                    _domain.variables_extracted += len(var_names2)

            case 7:  # function_call_extraction
                var = gen_ftl_identifier(fdp)
                func_name = "NUMBER"
                func_p = _make_func_ref(func_name, var)
                msg = _make_simple_message(msg_id, [func_p])

                info = introspect_message(msg)
                if info is not None:
                    func_names = info.get_function_names()
                    if func_name not in func_names:
                        err_msg = f"function extraction missing '{func_name}'"
                        raise IntrospectionFuzzError(err_msg)

            case 8:  # deep_nesting_depth_guard
                # Build a deeply nested SelectExpression chain to trigger MAX_DEPTH
                depth = fdp.ConsumeIntInRange(MAX_DEPTH - 2, MAX_DEPTH + 5)
                # Build innermost element
                inner_var = gen_ftl_identifier(fdp)
                inner: Any = _make_var_ref(inner_var)

                # Wrap in nested select expressions
                for _ in range(depth):
                    selector_var = gen_ftl_identifier(fdp)
                    key = Identifier(name="other")
                    variant_pattern = Pattern(elements=(inner,))
                    select_expr = SelectExpression(
                        selector=VariableReference(
                            id=_make_identifier(selector_var)
                        ),
                        variants=(
                            Variant(key=key, value=variant_pattern, default=True),
                        ),
                    )
                    inner = Placeable(expression=select_expr)

                msg = _make_simple_message(msg_id, [inner])

                # Must not raise -- either returns result or hits depth limit
                info = introspect_message(msg)
                # If MAX_DEPTH was exceeded, info may have partial results
                if info is not None and depth > MAX_DEPTH:
                    _domain.depth_limit_hits += 1

            case 9:  # adversarial_ast
                # Programmatically construct unusual AST combinations
                adv_choice = fdp.ConsumeIntInRange(0, 4)
                match adv_choice:
                    case 0:
                        # Empty pattern
                        msg = _make_simple_message(msg_id, [])
                        info = introspect_message(msg)
                        if info is None:
                            err_msg = "introspect_message returned None for empty pattern"
                            raise IntrospectionFuzzError(err_msg)
                        if info.get_variable_names():
                            err_msg = "empty message has variables"
                            raise IntrospectionFuzzError(err_msg)
                    case 1:
                        # Text-only (no placeables)
                        msg = _make_simple_message(
                            msg_id,
                            [_make_text("no placeables here")]
                        )
                        info = introspect_message(msg)
                        if info is not None and info.get_variable_names():
                            err_msg = "text-only message should have no variables"
                            raise IntrospectionFuzzError(err_msg)
                    case 2:
                        # Same variable referenced multiple times
                        var = gen_ftl_identifier(fdp)
                        n = fdp.ConsumeIntInRange(2, 10)
                        elements = [_make_var_ref(var) for _ in range(n)]
                        msg = _make_simple_message(msg_id, elements)
                        result = extract_variables(msg)
                        # Contract: deduplication -- only 1 entry
                        if len(result) != 1 or var not in result:
                            err_msg = f"Deduplication failed: {var} x{n} -> {result}"
                            raise IntrospectionFuzzError(err_msg)
                    case 3:
                        # Term referenced multiple times -- deduplication
                        term_id = gen_ftl_identifier(fdp)
                        n = fdp.ConsumeIntInRange(2, 8)
                        elements = [_make_term_ref(term_id) for _ in range(n)]
                        msg = _make_simple_message(msg_id, elements)
                        _, term_refs = extract_references(msg)
                        if len(term_refs) != 1 or term_id not in term_refs:
                            err_msg = f"Term deduplication failed: {term_id} x{n} -> {term_refs}"
                            raise IntrospectionFuzzError(err_msg)
                    case _:
                        # Message with both variables and message refs
                        var = gen_ftl_identifier(fdp)
                        ref = gen_ftl_identifier(fdp)
                        msg = _make_simple_message(
                            msg_id, [_make_var_ref(var), _make_msg_ref(ref)]
                        )
                        info = introspect_message(msg)
                        if info is not None:
                            _domain.variables_extracted += len(
                                info.get_variable_names()
                            )

            case 10:  # cache_invalidation
                _domain.cache_operations += 1
                var = gen_ftl_identifier(fdp)
                msg = _make_simple_message(
                    msg_id, [_make_var_ref(var)]
                )

                # Introspect once (populates cache)
                info1 = introspect_message(msg)
                # Clear cache
                clear_introspection_cache()
                # Introspect again (cold cache -- must give same result)
                info2 = introspect_message(msg)

                if info1 is not None and info2 is not None:
                    vars1 = info1.get_variable_names()
                    vars2 = info2.get_variable_names()
                    if vars1 != vars2:
                        err_msg = f"Cache invalidation: {vars1} != {vars2}"
                        raise IntrospectionFuzzError(err_msg)

            case 12:  # validate_variables_schema
                _domain.schema_validations += 1
                # Build a message with a known variable set, then validate
                # against exact, subsets, and supersets of that set.
                var_a = gen_ftl_identifier(fdp)
                var_b = gen_ftl_identifier(fdp)
                elements = [_make_var_ref(var_a), _make_var_ref(var_b)]
                msg = _make_simple_message(msg_id, elements)
                declared = extract_variables(msg)

                # 1. Exact match: is_valid must be True
                result_exact = validate_message_variables(msg, declared)
                if not result_exact.is_valid:
                    err_msg = (
                        f"validate_message_variables: exact match should be valid "
                        f"declared={declared} expected={declared}"
                    )
                    raise IntrospectionFuzzError(err_msg)
                if result_exact.missing_variables or result_exact.extra_variables:
                    err_msg = (
                        f"Exact match: missing={result_exact.missing_variables} "
                        f"extra={result_exact.extra_variables} both must be empty"
                    )
                    raise IntrospectionFuzzError(err_msg)
                if result_exact.message_id != msg_id:
                    err_msg = (
                        f"message_id mismatch: {result_exact.message_id!r} != {msg_id!r}"
                    )
                    raise IntrospectionFuzzError(err_msg)

                # 2. Superset: extra_var added to expected -> missing_variables contains it.
                # Guard: FDP byte-exhaustion causes ConsumeIntInRange to return lo=0,
                # which may collide extra_var with var_a or var_b. When extra_var ∈ declared,
                # the set union is a no-op: declared == expected_super, so is_valid=True is
                # the correct library response. Only assert is_valid=False when extra_var
                # is genuinely absent from declared (i.e., the superset is a strict superset).
                extra_var = gen_ftl_identifier(fdp)
                if extra_var not in declared:
                    expected_super = declared | {extra_var}
                    result_super = validate_message_variables(msg, expected_super)
                    if result_super.is_valid:
                        err_msg = "Superset expected: is_valid must be False"
                        raise IntrospectionFuzzError(err_msg)
                    if extra_var not in result_super.missing_variables:
                        err_msg = (
                            f"Superset: {extra_var!r} must be in missing_variables "
                            f"{result_super.missing_variables}"
                        )
                        raise IntrospectionFuzzError(err_msg)

                # 3. Subset: expected is empty set -> all declared become extra
                result_empty = validate_message_variables(msg, frozenset())
                if result_empty.is_valid and declared:
                    err_msg = "Empty expected with declared vars: is_valid must be False"
                    raise IntrospectionFuzzError(err_msg)
                if result_empty.extra_variables != declared:
                    err_msg = (
                        f"Empty expected: extra_variables={result_empty.extra_variables} "
                        f"must equal declared={declared}"
                    )
                    raise IntrospectionFuzzError(err_msg)

                # 4. Immutability: result must be frozen.
                # Use setattr() not object.__setattr__(): the latter bypasses the
                # class's __setattr__ and writes directly to the slot descriptor —
                # the same mechanism frozen dataclass __init__ uses to initialize
                # fields, so it always succeeds. setattr() resolves through
                # type(obj).__setattr__ which IS the FrozenInstanceError-raising
                # override added by @dataclass(frozen=True).
                if not isinstance(result_exact, MessageVariableValidationResult):
                    err_msg = "validate_message_variables wrong return type"
                    raise IntrospectionFuzzError(err_msg)
                try:
                    result_exact.is_valid = not result_exact.is_valid  # type: ignore[misc]
                    err_msg = "MessageVariableValidationResult must be frozen (immutable)"
                    raise IntrospectionFuzzError(err_msg)
                except (AttributeError, TypeError):
                    pass  # Expected: FrozenInstanceError(AttributeError) from frozen dataclass

            case _:  # bundle_introspection_facade
                _domain.bundle_facade_calls += 1
                var_a = gen_ftl_identifier(fdp)
                var_b = gen_ftl_identifier(fdp)
                ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

                bundle = FluentBundle("en-US", use_isolating=False)
                bundle.add_resource(ftl)

                # FluentBundle.introspect_message delegates to introspection module
                info = bundle.introspect_message(msg_id)
                if info is not None:
                    bundle_vars = info.get_variable_names()
                    if var_a not in bundle_vars or var_b not in bundle_vars:
                        err_msg = f"Bundle facade missing vars: {bundle_vars}"
                        raise IntrospectionFuzzError(err_msg)

                # FluentBundle.get_message_variables
                direct_vars = bundle.get_message_variables(msg_id)
                if var_a not in direct_vars or var_b not in direct_vars:
                    err_msg = f"get_message_variables missing: {direct_vars}"
                    raise IntrospectionFuzzError(err_msg)

    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = (
            _state.error_counts.get(error_type, 0) + 1
        )
    except IntrospectionFuzzError:
        _domain.invariant_violations += 1
        _state.findings += 1
        raise
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "deep_nesting" in pattern_name
            or pattern_name in ("adversarial_ast", "cache_invalidation")
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
    """Run the introspection fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="MessageIntrospection visitor and reference extraction fuzzer",
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
        title="MessageIntrospection Visitor & Reference Extraction Fuzzer (Atheris)",
        target=(
            "ftllexengine.introspection.message "
            "(IntrospectionVisitor, ReferenceExtractor)"
        ),
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
            f"MAX_DEPTH:  {MAX_DEPTH} (depth guard tested in deep_nesting pattern)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
