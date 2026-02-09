#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: serializer - AST-construction serializer roundtrip
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""AST-Construction Serializer Fuzzer (Atheris).

Targets: ftllexengine.syntax.serializer.serialize,
         ftllexengine.syntax.parser.FluentParserV1

Concern boundary: This fuzzer programmatically constructs AST nodes
(bypassing the parser) and feeds them to the serializer. This is the
ONLY Atheris fuzzer that can produce AST states the parser would never
emit -- e.g. TextElement values with leading whitespace, syntax characters
in pattern-initial positions, empty patterns, or structurally valid but
semantically unusual combinations.

This directly addresses the blind spot where text-based fuzzers
(fuzz_roundtrip, fuzz_structured) start from the parser, which normalizes
inputs before the serializer ever sees them.

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

import argparse
import atexit
import gc
import logging
import pathlib
import random
import sys
import time
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

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
    gen_ftl_identifier,
    gen_ftl_value,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    select_pattern_round_robin,
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


# --- Global State ---

_state = BaseFuzzerState(seed_corpus_max_size=100)
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
atheris.enabled_hooks.add("RegEx")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import (
        Attribute,
        Identifier,
        Junk,
        Message,
        NumberLiteral,
        Pattern,
        Placeable,
        Resource,
        SelectExpression,
        StringLiteral,
        Term,
        TermReference,
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


# --- Pattern Implementations ---


def _pattern_leading_whitespace(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values with leading whitespace.

    Targets BUG-SERIALIZER-LEADING-WS-001: the parser consumes post-=
    whitespace as syntax, so leading spaces in TextElement values must
    be wrapped in StringLiteral placeables by the serializer.
    """
    num_spaces = fdp.ConsumeIntInRange(1, 8)
    base_value = gen_ftl_value(fdp)
    value_text = " " * num_spaces + base_value

    # Message with leading-whitespace value
    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

    # Attribute with leading-whitespace value
    attr = _mk_attr(fdp, value_text)
    msg2 = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=(attr,),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg2,)), pattern)


def _pattern_trailing_whitespace(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values with trailing whitespace."""
    num_spaces = fdp.ConsumeIntInRange(1, 8)
    base_value = gen_ftl_value(fdp)
    value_text = base_value + " " * num_spaces

    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_syntax_chars_value(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values containing FTL syntax characters.

    Tests that the serializer correctly escapes or wraps braces,
    dots, hash, asterisk, and brackets at various positions.
    """
    base_value = gen_ftl_value(fdp)
    char = _FTL_SYNTAX_CHARS[
        fdp.ConsumeIntInRange(0, len(_FTL_SYNTAX_CHARS) - 1)
    ]
    pos = fdp.ConsumeIntInRange(0, len(base_value))
    value_text = base_value[:pos] + char + base_value[pos:]

    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

    # Also test in attribute value
    attr = _mk_attr(fdp, value_text)
    msg2 = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=(attr,),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg2,)), pattern)


def _pattern_simple_message(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Baseline: simple message with clean text value."""
    value = gen_ftl_value(fdp)
    msg = _mk_message(fdp, value=_mk_pattern(value))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_string_literal_placeable(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Patterns with StringLiteral placeables containing edge-case content."""
    literal_value = gen_ftl_value(fdp, max_length=20)

    # Optionally inject special content
    special = fdp.ConsumeIntInRange(0, 3)
    match special:
        case 0:
            literal_value = " " * fdp.ConsumeIntInRange(1, 5)
        case 1:
            literal_value = "\\" + literal_value
        case 2:
            literal_value = '"' + literal_value + '"'

    placeable = Placeable(expression=StringLiteral(value=literal_value))
    text_before = TextElement(value=gen_ftl_value(fdp, max_length=15))
    elements: tuple[TextElement | Placeable, ...] = (text_before, placeable)
    pat = Pattern(elements=elements)

    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_attribute_edge_cases(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Attributes with edge-case values: leading/trailing spaces, syntax chars."""
    num_attrs = fdp.ConsumeIntInRange(1, 4)
    attrs: list[Attribute] = []
    for _ in range(num_attrs):
        edge_type = fdp.ConsumeIntInRange(0, 3)
        base = gen_ftl_value(fdp)
        match edge_type:
            case 0:
                val = " " * fdp.ConsumeIntInRange(1, 5) + base
            case 1:
                val = base + " " * fdp.ConsumeIntInRange(1, 5)
            case 2:
                ch = _FTL_SYNTAX_CHARS[
                    fdp.ConsumeIntInRange(
                        0, len(_FTL_SYNTAX_CHARS) - 1,
                    )
                ]
                val = ch + base
            case _:
                val = base
        attrs.append(_mk_attr(fdp, val))

    msg = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=tuple(attrs),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_term_edge_cases(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Terms with edge-case attribute and value content."""
    num_spaces = fdp.ConsumeIntInRange(0, 5)
    base = gen_ftl_value(fdp)
    value_text = " " * num_spaces + base if num_spaces > 0 else base

    attrs: tuple[Attribute, ...] = ()
    if fdp.ConsumeBool():
        attr_val = " " * fdp.ConsumeIntInRange(1, 3) + gen_ftl_value(fdp)
        attrs = (_mk_attr(fdp, attr_val),)

    term = _mk_term(fdp, value=_mk_pattern(value_text), attributes=attrs)
    _verify_serializer_roundtrip(Resource(entries=(term,)), pattern)


def _pattern_select_expression(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Select expressions constructed from AST nodes."""
    var_id = _mk_id(fdp)
    selector = VariableReference(id=var_id)

    num_variants = fdp.ConsumeIntInRange(1, 4)
    variants: list[Variant] = []
    for _ in range(num_variants):
        key_is_number = fdp.ConsumeBool()
        if key_is_number:
            num = fdp.ConsumeIntInRange(0, 99)
            key: Identifier | NumberLiteral = NumberLiteral(
                value=num, raw=str(num),
            )
        else:
            key = _mk_id(fdp)

        val = gen_ftl_value(fdp)
        # Optionally add leading whitespace to variant value
        if fdp.ConsumeBool():
            val = " " + val
        variants.append(Variant(key=key, value=_mk_pattern(val)))

    # Ensure exactly one default
    variants.append(
        Variant(
            key=Identifier(name="other"),
            value=_mk_pattern(gen_ftl_value(fdp)),
            default=True,
        ),
    )

    sel = SelectExpression(
        selector=selector, variants=tuple(variants),
    )
    pat = Pattern(elements=(Placeable(expression=sel),))
    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_mixed_elements(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Patterns with interleaved TextElement and Placeable nodes."""
    num_elements = fdp.ConsumeIntInRange(2, 6)
    elements: list[TextElement | Placeable] = []

    for _ in range(num_elements):
        is_placeable = fdp.ConsumeBool()
        if is_placeable:
            expr_type = fdp.ConsumeIntInRange(0, 2)
            match expr_type:
                case 0:
                    expr: Any = StringLiteral(
                        value=gen_ftl_value(fdp, max_length=10),
                    )
                case 1:
                    expr = VariableReference(id=_mk_id(fdp))
                case _:
                    expr = TermReference(id=_mk_id(fdp))
            elements.append(Placeable(expression=expr))
        else:
            val = gen_ftl_value(fdp, max_length=15)
            # Optionally inject leading space
            if fdp.ConsumeBool() and elements:
                val = " " + val
            elements.append(TextElement(value=val))

    pat = Pattern(elements=tuple(elements))
    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


def _pattern_multiline_value(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Multi-line TextElement values with newlines and indentation."""
    num_lines = fdp.ConsumeIntInRange(2, 5)
    lines: list[str] = []
    for _ in range(num_lines):
        line = gen_ftl_value(fdp, max_length=30)
        # Optionally add leading spaces
        if fdp.ConsumeBool():
            line = " " * fdp.ConsumeIntInRange(1, 4) + line
        lines.append(line)

    # Join with newlines and indentation (4 spaces for FTL continuation)
    value_text = ("\n    ").join(lines)
    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)


# --- Pattern Dispatch ---

_PATTERN_DISPATCH: dict[str, Any] = {
    "leading_whitespace": _pattern_leading_whitespace,
    "trailing_whitespace": _pattern_trailing_whitespace,
    "syntax_chars_value": _pattern_syntax_chars_value,
    "simple_message": _pattern_simple_message,
    "string_literal_placeable": _pattern_string_literal_placeable,
    "attribute_edge_cases": _pattern_attribute_edge_cases,
    "term_edge_cases": _pattern_term_edge_cases,
    "select_expression": _pattern_select_expression,
    "mixed_elements": _pattern_mixed_elements,
    "multiline_value": _pattern_multiline_value,
}


# --- Custom Mutator ---


def _mutate_constructed_ast(ast: Resource, seed: int) -> Resource:
    """Apply mutations targeting serializer edge cases.

    Mutations focus on whitespace injection and syntax character
    insertion -- the exact bug classes that text-based fuzzers miss.
    """
    rng = random.Random(seed)
    entries = list(ast.entries)
    if not entries:
        return ast

    mut_type = rng.randint(0, 3)

    match mut_type:
        case 0:
            entries = _mut_add_leading_spaces(entries, rng)
        case 1:
            entries = _mut_add_syntax_char(entries, rng)
        case 2:
            entries = _mut_add_attribute_ws(entries, rng)
        case 3:
            entries = _mut_nest_placeable(entries, rng)

    return Resource(entries=tuple(entries))


def _mut_add_leading_spaces(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Inject leading spaces into the first TextElement of a pattern."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        elements = list(entry.value.elements)
        for idx, elem in enumerate(elements):
            if isinstance(elem, TextElement) and elem.value:
                n = rng.randint(1, 6)
                elements[idx] = dc_replace(
                    elem, value=" " * n + elem.value,
                )
                new_pat = dc_replace(
                    entry.value, elements=tuple(elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries


def _mut_add_syntax_char(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Insert a syntax character at a random position in a TextElement."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        elements = list(entry.value.elements)
        for idx, elem in enumerate(elements):
            if isinstance(elem, TextElement) and elem.value:
                ch = rng.choice(_FTL_SYNTAX_CHARS)
                pos = rng.randint(0, len(elem.value))
                new_val = elem.value[:pos] + ch + elem.value[pos:]
                elements[idx] = dc_replace(elem, value=new_val)
                new_pat = dc_replace(
                    entry.value, elements=tuple(elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries


def _mut_add_attribute_ws(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Add leading whitespace to an attribute value."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or not entry.attributes:
            continue
        attr = rng.choice(entry.attributes)
        if attr.value and attr.value.elements:
            elem = attr.value.elements[0]
            if isinstance(elem, TextElement) and elem.value:
                n = rng.randint(1, 5)
                new_elem = dc_replace(
                    elem, value=" " * n + elem.value,
                )
                new_elements = (new_elem, *attr.value.elements[1:])
                new_pat = dc_replace(
                    attr.value, elements=new_elements,
                )
                new_attr = dc_replace(attr, value=new_pat)
                new_attrs = tuple(
                    new_attr if a is attr else a
                    for a in entry.attributes
                )
                entries[i] = dc_replace(entry, attributes=new_attrs)
                return entries
    return entries


def _mut_nest_placeable(
    entries: list[Any],
    _rng: random.Random,
) -> list[Any]:
    """Wrap a StringLiteral in an additional Placeable layer."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        for idx, elem in enumerate(entry.value.elements):
            if (
                isinstance(elem, Placeable)
                and isinstance(elem.expression, StringLiteral)
            ):
                inner = Placeable(expression=elem.expression)
                new_elem = dc_replace(elem, expression=inner)
                new_elements = list(entry.value.elements)
                new_elements[idx] = new_elem
                new_pat = dc_replace(
                    entry.value, elements=tuple(new_elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries


def _custom_mutator(data: bytes, max_size: int, seed: int) -> bytes:
    """Structure-aware mutator for AST-constructed inputs.

    Parses the serialized output, applies AST-level mutations targeting
    serializer edge cases, re-serializes, then applies byte-level mutation.
    """
    try:
        source = data.decode("utf-8", errors="replace")
        ast = _parser.parse(source)

        if ast.entries and not any(
            isinstance(e, Junk) for e in ast.entries
        ):
            mutated = _mutate_constructed_ast(ast, seed)
            serialized = serialize(mutated, validate=False)
            result = serialized.encode("utf-8")
            if len(result) <= max_size:
                return atheris.Mutate(result, max_size)
    except KeyboardInterrupt:
        _state.status = "stopped"
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return atheris.Mutate(data, max_size)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz serializer via AST construction."""
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = (
        _state.pattern_coverage.get(pattern, 0) + 1
    )

    if fdp.remaining_bytes() < 4:
        return

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp, pattern)

    except SerializerFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = (
            _state.error_counts.get(error_key, 0) + 1
        )

    finally:
        is_interesting = pattern in (
            "leading_whitespace", "syntax_chars_value",
            "attribute_edge_cases",
        ) or ((time.perf_counter() - start_time) * 1000 > 10.0)
        record_iteration_metrics(
            _state, pattern, start_time, data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the AST-construction serializer fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description=(
            "AST-construction serializer roundtrip fuzzer "
            "using Atheris/libFuzzer"
        ),
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=100,
        help="Maximum size of in-memory seed corpus (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="AST-Construction Serializer Fuzzer (Atheris)",
        target="serialize (AST-constructed), FluentParserV1",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=(
            "Mode:       AST-construction (bypasses parser normalization)",
        ),
    )

    atheris.Setup(
        sys.argv, test_one_input, custom_mutator=_custom_mutator,
    )
    atheris.Fuzz()


if __name__ == "__main__":
    main()
