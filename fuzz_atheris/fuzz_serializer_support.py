#!/usr/bin/env python3
"""AST-Construction Serializer Fuzzer (Atheris).

Targets: ftllexengine.syntax.serializer.serialize,
         ftllexengine.syntax.parser.FluentParserV1,
         ftllexengine.syntax.visitor.ASTVisitor / ASTTransformer

Concern boundary: This fuzzer programmatically constructs AST nodes
(bypassing the parser) and feeds them to the serializer. This is the
ONLY Atheris fuzzer that can produce AST states the parser would never
emit -- e.g. TextElement values with leading whitespace, syntax characters
in pattern-initial positions, empty patterns, or structurally valid but
semantically unusual combinations.

This directly addresses the blind spot where text-based fuzzers
(fuzz_roundtrip, fuzz_structured) start from the parser, which normalizes
inputs before the serializer ever sees them.

The same AST-construction model is also ideal for visitor/transformer
coverage because it can construct trees and transformation results that
ordinary parser-driven fuzzers do not reach.

Invariant:
- serialize(ast) must produce valid FTL (no Junk on reparse)
- Idempotence: serialize(parse(serialize(ast))) == serialize(ast)

Pattern Routing:
Deterministic round-robin from a weighted schedule (same infrastructure
as fuzz_roundtrip). Pattern selection is independent of fuzzed bytes
to avoid coverage-guided mutation bias.

Custom Mutator:
AST-level mutations applied to programmatically constructed ASTs:
inject leading/trailing whitespace, syntax characters, empty patterns,
deeply nested placeables. Byte-level mutation applied on top.

Finding Artifacts:
Convergence failures write source/S1/S2/metadata to
.fuzz_atheris_corpus/serializer/findings/ for standalone reproduction.

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import atexit
import logging
import pathlib
from dataclasses import dataclass
from typing import Any

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
    emit_final_report,
    gen_ftl_identifier,
    gen_ftl_value,
    write_finding_artifact,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---


@dataclass
class SerializerMetrics:
    """Domain-specific metrics for AST-construction serializer fuzzer."""

    ast_construction_failures: int = 0
    convergence_failures: int = 0
    junk_on_reparse: int = 0
    validation_errors: int = 0
    visitor_runs: int = 0
    transformer_runs: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=100,
    fuzzer_name="serializer",
    fuzzer_target="serialize (AST-constructed), FluentParserV1",
)
_domain = SerializerMetrics()


# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("leading_whitespace", 18),
    ("trailing_whitespace", 8),
    ("syntax_chars_value", 15),
    ("simple_message", 8),
    ("string_literal_placeable", 10),
    ("attribute_edge_cases", 12),
    ("term_edge_cases", 8),
    ("select_expression", 8),
    ("mixed_elements", 8),
    ("multiline_value", 5),
    ("visitor_dispatch", 8),
    ("transformer_roundtrip", 8),
    ("transformer_validation", 6),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {
    name: float(weight) for name, weight in _PATTERN_WEIGHTS
}


class SerializerFuzzError(Exception):
    """Raised when a serializer roundtrip invariant is breached."""


# Allowed exceptions from parser/serializer
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    RecursionError,
    MemoryError,
    UnicodeDecodeError,
    UnicodeEncodeError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "serializer"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    stats["ast_construction_failures"] = _domain.ast_construction_failures
    stats["convergence_failures"] = _domain.convergence_failures
    stats["junk_on_reparse"] = _domain.junk_on_reparse
    stats["validation_errors"] = _domain.validation_errors
    stats["visitor_runs"] = _domain.visitor_runs
    stats["transformer_runs"] = _domain.transformer_runs

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    emit_final_report(
        _state, _build_stats_dict(), _REPORT_DIR,
        "fuzz_serializer_report.json",
    )


atexit.register(_emit_report)


# --- Finding Artifacts ---

_FINDINGS_DIR = _REPORT_DIR / "findings"


# --- Instrumentation & Parser ---

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

atheris.enabled_hooks.add("str")
# RegEx hook omitted: serializer fuzzer constructs ASTs programmatically,
# no regex in the hot path. The hook triggers spurious Atheris errors on
# transitively imported stdlib regex patterns (e.g., email.charset).

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import (
        Attribute,
        Identifier,
        Junk,
        Message,
        Pattern,
        Placeable,
        Resource,
        SelectExpression,
        StringLiteral,
        Term,
        TextElement,
        VariableReference,
        Variant,
    )
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import serialize

_parser = FluentParserV1()


# --- AST Construction Helpers ---

# Characters that are syntactically significant in FTL pattern positions
_FTL_SYNTAX_CHARS = "{}.#*["


def _mk_id(fdp: atheris.FuzzedDataProvider) -> Identifier:
    """Construct an Identifier AST node from fuzzed bytes."""
    return Identifier(name=gen_ftl_identifier(fdp))


def _mk_pattern(text: str) -> Pattern:
    """Construct a single-element text Pattern."""
    return Pattern(elements=(TextElement(value=text),))


def _mk_attr(
    fdp: atheris.FuzzedDataProvider,
    value_text: str,
) -> Attribute:
    """Construct an Attribute with the given value text."""
    return Attribute(id=_mk_id(fdp), value=_mk_pattern(value_text))


def _mk_message(
    fdp: atheris.FuzzedDataProvider,
    *,
    value: Pattern | None = None,
    attributes: tuple[Attribute, ...] = (),
) -> Message:
    """Construct a Message AST node."""
    return Message(id=_mk_id(fdp), value=value, attributes=attributes)


def _mk_term(
    fdp: atheris.FuzzedDataProvider,
    *,
    value: Pattern,
    attributes: tuple[Attribute, ...] = (),
) -> Term:
    """Construct a Term AST node."""
    return Term(id=_mk_id(fdp), value=value, attributes=attributes)


def _mk_nonempty_value(
    fdp: atheris.FuzzedDataProvider,
    *,
    max_length: int = 24,
) -> str:
    """Generate a non-empty FTL-safe text fragment."""
    value = gen_ftl_value(fdp, max_length=max_length)
    return value or "value"


def _build_visitor_resource(fdp: atheris.FuzzedDataProvider) -> Resource:
    """Construct a small but structurally rich AST for visitor coverage."""
    selector = VariableReference(id=Identifier(name="count"))
    variants = (
        Variant(
            key=Identifier(name="one"),
            value=_mk_pattern(_mk_nonempty_value(fdp)),
        ),
        Variant(
            key=Identifier(name="other"),
            value=_mk_pattern(_mk_nonempty_value(fdp)),
            default=True,
        ),
    )
    select = SelectExpression(selector=selector, variants=variants)
    message = Message(
        id=Identifier(name=f"msg-{gen_ftl_identifier(fdp)}"),
        value=Pattern(
            elements=(
                TextElement(value=_mk_nonempty_value(fdp)),
                Placeable(expression=select),
            ),
        ),
        attributes=(
            Attribute(
                id=Identifier(name="label"),
                value=_mk_pattern(_mk_nonempty_value(fdp)),
            ),
        ),
    )
    term = Term(
        id=Identifier(name=f"term-{gen_ftl_identifier(fdp)}"),
        value=Pattern(
            elements=(
                TextElement(value=_mk_nonempty_value(fdp)),
                Placeable(
                    expression=StringLiteral(value=_mk_nonempty_value(fdp)),
                ),
            ),
        ),
        attributes=(),
    )
    return Resource(entries=(message, term))


# --- Roundtrip Verification ---


def _verify_serializer_roundtrip(
    ast: Resource,
    pattern: str,
) -> None:
    """Verify serialize(ast) -> parse -> serialize convergence.

    Steps:
    1. Serialize constructed AST -> S1
    2. Parse S1 -> AST2
    3. Check no Junk entries
    4. Serialize AST2 -> S2
    5. Assert S1 == S2 (idempotence)

    On failure, writes finding artifacts before raising.
    """
    s1 = serialize(ast, validate=False)

    ast2 = _parser.parse(s1)

    if any(isinstance(e, Junk) for e in ast2.entries):
        _domain.junk_on_reparse += 1
        write_finding_artifact(
            findings_dir=_FINDINGS_DIR, state=_state,
            source=f"[AST-constructed: {pattern}]", s1=s1, s2="",
            pattern=pattern,
            extra_meta={"failure_type": "junk_on_reparse"},
        )
        msg = (
            f"Serialized AST produced Junk on re-parse.\n"
            f"Pattern: {pattern}\n"
            f"S1 ({len(s1)} chars): {s1[:200]!r}"
        )
        raise SerializerFuzzError(msg)

    s2 = serialize(ast2)

    if s1 != s2:
        _domain.convergence_failures += 1
        write_finding_artifact(
            findings_dir=_FINDINGS_DIR, state=_state,
            source=f"[AST-constructed: {pattern}]", s1=s1, s2=s2,
            pattern=pattern,
            extra_meta={"failure_type": "convergence_failure"},
        )
        msg = (
            f"Convergence failure: S(AST) != S(P(S(AST)))\n"
            f"Pattern: {pattern}\n"
            f"S1 ({len(s1)} chars): {s1[:200]!r}\n"
            f"S2 ({len(s2)} chars): {s2[:200]!r}"
        )
        raise SerializerFuzzError(msg)

__all__ = [name for name in globals() if not name.startswith("__")]
