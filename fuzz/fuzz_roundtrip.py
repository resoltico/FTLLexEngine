#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: roundtrip - Metamorphic roundtrip (Parser <-> Serializer)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Metamorphic Roundtrip Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1,
         ftllexengine.syntax.serializer.serialize

Concern boundary: This fuzzer is dedicated to the parser-serializer convergence
property S(P(S(P(x)))) == S(P(x)). It systematically generates valid FTL inputs
covering all grammar productions (messages, terms, attributes, select expressions,
placeables, comments, function calls, multiline patterns) and verifies that
serialized output re-parses identically. Distinct from fuzz_structured which tests
AST construction correctness with roundtrip as only 1 of 10 patterns at 7% weight.

Invariants:
- Valid FTL parses without Junk entries
- Serialization of valid AST always succeeds
- Serialized output re-parses without error
- Convergence: S(P(x)) == S(P(S(P(x)))) for valid FTL
- Multi-pass convergence: S2 == S3 == S4 (stabilization within 3 passes)
- AST structural equality (ignoring spans) after convergence

Pattern Routing:
Pattern selection is embedded in fuzzed bytes via FuzzedDataProvider so
that crash files are self-contained and replayable. The weighted schedule
preserves proportional coverage distribution while allowing libFuzzer to
reproduce findings from crash artifacts.

Custom Mutator:
Structure-aware mutation: parse valid FTL, apply AST-level mutations
(swap variants, duplicate attributes, mutate keys, nest placeables,
shuffle entries), serialize, then apply byte-level mutation on top.

Finding Artifacts:
When a convergence failure is detected, the fuzzer writes human-readable
artifacts to .fuzz_corpus/roundtrip/findings/ containing the actual FTL
source, S1, S2, and metadata JSON. These artifacts enable debugging without
Atheris and are consumed by replay_finding.py for standalone reproduction.

Metrics:
- Pattern coverage (13 patterns with weighted selection)
- Weight skew detection (actual vs intended distribution)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Corpus retention rate and eviction tracking
- Seed corpus management

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import datetime
import gc
import hashlib
import json
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
    get_process,
    record_iteration_metrics,
    record_memory,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class RoundtripMetrics:
    """Domain-specific metrics for roundtrip fuzzer."""

    junk_skips: int = 0
    convergence_failures: int = 0
    multi_pass_checks: int = 0


# --- Global State ---

_state = BaseFuzzerState(seed_corpus_max_size=100)
_domain = RoundtripMetrics()


# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("simple_message", 10),
    ("variable_placeable", 12),
    ("term_reference", 8),
    ("message_reference", 8),
    ("select_expression", 15),
    ("attributes", 10),
    ("comments", 5),
    ("function_call", 8),
    ("multiline_pattern", 7),
    ("mixed_resource", 12),
    ("deep_nesting", 5),
    ("raw_unicode", 5),
    ("convergence_stress", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class RoundtripFuzzError(Exception):
    """Raised when a roundtrip invariant is breached."""


# Allowed exceptions from parser/serializer
ALLOWED_EXCEPTIONS = (
    ValueError,
    RecursionError,
    MemoryError,
    UnicodeDecodeError,
    UnicodeEncodeError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_corpus") / "roundtrip"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["junk_skips"] = _domain.junk_skips
    stats["convergence_failures"] = _domain.convergence_failures
    stats["multi_pass_checks"] = _domain.multi_pass_checks

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_roundtrip_report.json")


atexit.register(_emit_report)


# --- Finding Artifacts ---

_FINDINGS_DIR = _REPORT_DIR / "findings"


def _write_finding_artifact(
    *,
    source: str,
    s1: str,
    s2: str,
    pattern: str,
    failure_type: str,
) -> None:
    """Write human-readable finding artifacts to disk for post-mortem debugging."""
    try:
        _FINDINGS_DIR.mkdir(parents=True, exist_ok=True)
        _state.finding_counter += 1
        prefix = f"finding_{_state.finding_counter:04d}"

        (_FINDINGS_DIR / f"{prefix}_source.ftl").write_text(source, encoding="utf-8")
        (_FINDINGS_DIR / f"{prefix}_s1.ftl").write_text(s1, encoding="utf-8")
        (_FINDINGS_DIR / f"{prefix}_s2.ftl").write_text(s2, encoding="utf-8")

        diff_pos = next(
            (i for i, (a, b) in enumerate(zip(s1, s2, strict=False)) if a != b),
            min(len(s1), len(s2)),
        )

        meta = {
            "iteration": _state.iterations,
            "pattern": pattern,
            "failure_type": failure_type,
            "timestamp": datetime.datetime.now(tz=datetime.UTC).isoformat(),
            "source_len": len(source),
            "s1_len": len(s1),
            "s2_len": len(s2),
            "source_hash": hashlib.sha256(
                source.encode("utf-8", errors="surrogatepass"),
            ).hexdigest(),
            "s1_hash": hashlib.sha256(
                s1.encode("utf-8", errors="surrogatepass"),
            ).hexdigest(),
            "s2_hash": hashlib.sha256(
                s2.encode("utf-8", errors="surrogatepass"),
            ).hexdigest(),
            "diff_offset": diff_pos,
        }
        (_FINDINGS_DIR / f"{prefix}_meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        print(
            f"\n[FINDING] Artifacts written to {_FINDINGS_DIR / prefix}_*.ftl",
            file=sys.stderr,
            flush=True,
        )
    except OSError:
        pass  # Finding artifacts are best-effort


# --- Instrumentation & Parser ---

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

atheris.enabled_hooks.add("str")
atheris.enabled_hooks.add("RegEx")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import (
        Attribute,
        Comment,
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
        TextElement,
        Variant,
    )
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import serialize

_parser = FluentParserV1()


# --- FTL Generation Helpers ---


def _gen_id(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a valid FTL identifier: [a-zA-Z][a-zA-Z0-9_-]*."""
    first = chr(ord("a") + fdp.ConsumeIntInRange(0, 25))
    length = fdp.ConsumeIntInRange(0, 15)
    chars = "abcdefghijklmnopqrstuvwxyz0123456789-"
    rest = "".join(chars[fdp.ConsumeIntInRange(0, len(chars) - 1)] for _ in range(length))
    return first + rest


def _gen_value(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a safe FTL value (no braces, no newlines)."""
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789.,!?:;'-"
    length = fdp.ConsumeIntInRange(1, 40)
    return "".join(safe_chars[fdp.ConsumeIntInRange(0, len(safe_chars) - 1)] for _ in range(length))


def _gen_variable(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a variable name (used in placeables as $name)."""
    return _gen_id(fdp)


# --- AST Structural Comparison ---


def _ast_structurally_equal(ast1: Resource, ast2: Resource) -> bool:
    """Compare AST structures ignoring spans and whitespace normalization.

    This catches bugs where serialization normalizes structural differences
    (comment attachment, attribute ordering) that string comparison misses.
    """
    if len(ast1.entries) != len(ast2.entries):
        return False
    return all(
        _entries_equal(e1, e2)
        for e1, e2 in zip(ast1.entries, ast2.entries, strict=True)
    )


def _entries_equal(e1: Any, e2: Any) -> bool:
    """Compare two AST entries structurally."""
    if type(e1) is not type(e2):
        return False

    match e1:
        case Message():
            return (
                e1.id.name == e2.id.name
                and _patterns_equal(e1.value, e2.value)
                and _attrs_equal(e1.attributes, e2.attributes)
            )
        case Term():
            return (
                e1.id.name == e2.id.name
                and _patterns_equal(e1.value, e2.value)
                and _attrs_equal(e1.attributes, e2.attributes)
            )
        case Comment():
            return e1.content == e2.content
        case Junk():
            return True
        case _:
            return False


def _patterns_equal(p1: Pattern | None, p2: Pattern | None) -> bool:
    """Compare two patterns structurally."""
    if p1 is None and p2 is None:
        return True
    if p1 is None or p2 is None:
        return False
    if len(p1.elements) != len(p2.elements):
        return False
    return all(
        _elements_equal(e1, e2)
        for e1, e2 in zip(p1.elements, p2.elements, strict=True)
    )


def _elements_equal(e1: Any, e2: Any) -> bool:
    """Compare two pattern elements structurally."""
    if type(e1) is not type(e2):
        return False
    match e1:
        case TextElement():
            # Normalize trailing whitespace for comparison
            return e1.value.rstrip() == e2.value.rstrip()
        case Placeable():
            return _expressions_equal(e1.expression, e2.expression)
        case _:
            return False


def _expressions_equal(e1: Any, e2: Any) -> bool:  # noqa: PLR0911
    """Compare two expressions structurally."""
    if type(e1) is not type(e2):
        return False
    match e1:
        case SelectExpression():
            if not _expressions_equal(e1.selector, e2.selector):
                return False
            if len(e1.variants) != len(e2.variants):
                return False
            return all(
                _variants_equal(v1, v2)
                for v1, v2 in zip(e1.variants, e2.variants, strict=True)
            )
        case StringLiteral():
            return e1.value == e2.value
        case NumberLiteral():
            return e1.value == e2.value
        case _:
            # For other expression types, compare by type and basic attributes
            return type(e1) is type(e2)


def _variants_equal(v1: Variant, v2: Variant) -> bool:
    """Compare two variants structurally."""
    if v1.default != v2.default:
        return False
    match v1.key, v2.key:
        case Identifier(), Identifier():
            if v1.key.name != v2.key.name:
                return False
        case NumberLiteral(), NumberLiteral():
            if v1.key.value != v2.key.value:
                return False
        case _:
            if type(v1.key) is not type(v2.key):
                return False
    return _patterns_equal(v1.value, v2.value)


def _attrs_equal(
    a1: tuple[Attribute, ...],
    a2: tuple[Attribute, ...],
) -> bool:
    """Compare attribute tuples structurally."""
    if len(a1) != len(a2):
        return False
    return all(
        attr1.id.name == attr2.id.name and _patterns_equal(attr1.value, attr2.value)
        for attr1, attr2 in zip(a1, a2, strict=True)
    )


# --- AST-Level Mutations ---

_PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")


def _mutate_ast(ast: Resource, seed: int) -> Resource:
    """Apply structural mutations to AST before serialization.

    Uses seed for deterministic mutation selection so crash files
    reproduce the exact mutation that triggered a finding.
    All AST nodes are frozen=True, so mutations use dataclasses.replace().
    """
    rng = random.Random(seed)
    entries = list(ast.entries)
    if not entries:
        return ast

    mut_type = rng.randint(0, 4)

    match mut_type:
        case 0:
            entries = _mut_swap_variants(entries, rng)
        case 1:
            entries = _mut_duplicate_attribute(entries, rng)
        case 2:
            entries = _mut_variant_keys(entries, rng)
        case 3:
            entries = _mut_nest_placeable(entries, rng)
        case 4:
            rng.shuffle(entries)

    return Resource(entries=tuple(entries))


def _mut_swap_variants(entries: list[Any], rng: random.Random) -> list[Any]:
    """Swap variant order in a SelectExpression."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        for elem in entry.value.elements:
            if isinstance(elem, Placeable) and isinstance(elem.expression, SelectExpression):
                sel = elem.expression
                if len(sel.variants) >= 2:
                    variants = list(sel.variants)
                    j = rng.randint(0, len(variants) - 2)
                    variants[j], variants[j + 1] = variants[j + 1], variants[j]
                    new_sel = dc_replace(sel, variants=tuple(variants))
                    new_elem = dc_replace(elem, expression=new_sel)
                    new_elements = tuple(
                        new_elem if e is elem else e for e in entry.value.elements
                    )
                    new_pattern = dc_replace(entry.value, elements=new_elements)
                    entries[i] = dc_replace(entry, value=new_pattern)
                    return entries
    return entries


def _mut_duplicate_attribute(entries: list[Any], rng: random.Random) -> list[Any]:
    """Duplicate an attribute with a mutated identifier."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or not entry.attributes:
            continue
        attr = rng.choice(entry.attributes)
        new_id = Identifier(name=attr.id.name + "x")
        new_attr = dc_replace(attr, id=new_id)
        entries[i] = dc_replace(entry, attributes=(*entry.attributes, new_attr))
        return entries
    return entries


def _mut_variant_keys(entries: list[Any], rng: random.Random) -> list[Any]:
    """Mutate variant keys by swapping plural categories."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        for elem in entry.value.elements:
            if isinstance(elem, Placeable) and isinstance(elem.expression, SelectExpression):
                sel = elem.expression
                if sel.variants:
                    variants = list(sel.variants)
                    j = rng.randint(0, len(variants) - 1)
                    v = variants[j]
                    if isinstance(v.key, Identifier):
                        new_key = Identifier(name=rng.choice(_PLURAL_CATEGORIES))
                        variants[j] = dc_replace(v, key=new_key)
                        new_sel = dc_replace(sel, variants=tuple(variants))
                        new_elem = dc_replace(elem, expression=new_sel)
                        new_elements = tuple(
                            new_elem if e is elem else e for e in entry.value.elements
                        )
                        new_pattern = dc_replace(entry.value, elements=new_elements)
                        entries[i] = dc_replace(entry, value=new_pattern)
                        return entries
    return entries


def _mut_nest_placeable(entries: list[Any], _rng: random.Random) -> list[Any]:
    """Wrap a string literal in an additional Placeable layer."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        for idx, elem in enumerate(entry.value.elements):
            if isinstance(elem, Placeable) and isinstance(elem.expression, StringLiteral):
                # Wrap: { "foo" } -> { { "foo" } }
                inner = Placeable(expression=elem.expression)
                new_elem = dc_replace(elem, expression=inner)
                new_elements = list(entry.value.elements)
                new_elements[idx] = new_elem
                new_pattern = dc_replace(entry.value, elements=tuple(new_elements))
                entries[i] = dc_replace(entry, value=new_pattern)
                return entries
    return entries


# --- Roundtrip Core ---


def _verify_roundtrip(source: str, pattern: str) -> None:
    """Run the full roundtrip verification on FTL source.

    Steps:
    1. Parse source -> AST1
    2. Skip if Junk entries (invalid FTL)
    3. Serialize AST1 -> S1
    4. Parse S1 -> AST2
    5. Serialize AST2 -> S2
    6. Assert S1 == S2 (convergence)
    7. Assert AST1 and AST2 are structurally equal

    On failure, writes finding artifacts before raising.
    """
    ast1 = _parser.parse(source)

    if any(isinstance(e, Junk) for e in ast1.entries):
        _domain.junk_skips += 1
        return

    if not ast1.entries:
        return

    s1 = serialize(ast1)
    ast2 = _parser.parse(s1)

    if any(isinstance(e, Junk) for e in ast2.entries):
        _domain.convergence_failures += 1
        _write_finding_artifact(
            source=source, s1=s1, s2="",
            pattern=pattern, failure_type="junk_on_reparse",
        )
        msg = (
            f"Serialized output produced Junk on re-parse.\n"
            f"Source ({len(source)} chars): {source[:200]!r}\n"
            f"S1 ({len(s1)} chars): {s1[:200]!r}"
        )
        raise RoundtripFuzzError(msg)

    s2 = serialize(ast2)

    if s1 != s2:
        _domain.convergence_failures += 1
        _write_finding_artifact(
            source=source, s1=s1, s2=s2,
            pattern=pattern, failure_type="convergence_failure",
        )
        msg = (
            f"Convergence failure: S(P(x)) != S(P(S(P(x))))\n"
            f"Source ({len(source)} chars): {source[:200]!r}\n"
            f"S1 ({len(s1)} chars): {s1[:200]!r}\n"
            f"S2 ({len(s2)} chars): {s2[:200]!r}"
        )
        raise RoundtripFuzzError(msg)

    # AST structural comparison: compare ast2 (from s1) with ast3 (from s2).
    # Since s1 == s2 at this point, a mismatch here indicates non-deterministic
    # parsing -- a serious bug. We do NOT compare ast1 vs ast2 because the
    # parser legitimately normalizes raw input (e.g. bare '[' -> Placeable).
    ast3 = _parser.parse(s2)
    if not _ast_structurally_equal(ast2, ast3):
        _domain.convergence_failures += 1
        _write_finding_artifact(
            source=source, s1=s1, s2=s2,
            pattern=pattern, failure_type="ast_structural_mismatch",
        )
        msg = (
            f"AST structural mismatch: P(S1) != P(S2) despite S1 == S2.\n"
            f"Source ({len(source)} chars): {source[:200]!r}\n"
            f"S1 ({len(s1)} chars): {s1[:200]!r}"
        )
        raise RoundtripFuzzError(msg)


def _verify_multi_pass_convergence(source: str, pattern: str) -> None:
    """Verify that serialization stabilizes within 3 passes.

    Parses the source, then runs 4 serialize-reparse passes (S1..S4)
    and asserts S2 == S3 == S4.
    """
    ast1 = _parser.parse(source)
    if any(isinstance(e, Junk) for e in ast1.entries):
        _domain.junk_skips += 1
        return
    if not ast1.entries:
        return

    _domain.multi_pass_checks += 1
    s1 = serialize(ast1)
    s2 = serialize(_parser.parse(s1))
    s3 = serialize(_parser.parse(s2))
    s4 = serialize(_parser.parse(s3))

    if s2 != s3 or s3 != s4:
        _domain.convergence_failures += 1
        _write_finding_artifact(
            source=source, s1=s2, s2=s3,
            pattern=pattern, failure_type="multi_pass_failure",
        )
        msg = (
            f"Multi-pass convergence failure: S2==S3={s2 == s3}, S3==S4={s3 == s4}\n"
            f"Source ({len(source)} chars): {source[:200]!r}\n"
            f"S2 ({len(s2)} chars): {s2[:200]!r}\n"
            f"S3 ({len(s3)} chars): {s3[:200]!r}\n"
            f"S4 ({len(s4)} chars): {s4[:200]!r}"
        )
        raise RoundtripFuzzError(msg)


# --- Pattern Implementations ---


def _pattern_simple_message(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Basic id = value roundtrip."""
    source = f"{_gen_id(fdp)} = {_gen_value(fdp)}\n"
    _verify_roundtrip(source, pattern)


def _pattern_variable_placeable(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Messages with { $var } placeables."""
    source = f"{_gen_id(fdp)} = {_gen_value(fdp)} {{ ${_gen_variable(fdp)} }} {_gen_value(fdp)}\n"
    _verify_roundtrip(source, pattern)


def _pattern_term_reference(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Term definitions (-term = ...) and references ({ -term })."""
    term_id = _gen_id(fdp)
    val = _gen_value(fdp)
    msg_id = _gen_id(fdp)
    msg_val = _gen_value(fdp)
    source = f"-{term_id} = {val}\n{msg_id} = {msg_val} {{ -{term_id} }}\n"
    _verify_roundtrip(source, pattern)


def _pattern_message_reference(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Message cross-references ({ other-msg })."""
    id1 = _gen_id(fdp)
    source = f"{id1} = {_gen_value(fdp)}\n{_gen_id(fdp)} = {{ {id1} }}\n"
    _verify_roundtrip(source, pattern)


def _pattern_select_expression(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Select expressions with plural/string keys."""
    msg_id = _gen_id(fdp)
    selector_var = _gen_variable(fdp)
    num_variants = fdp.ConsumeIntInRange(1, 5)

    variants = []
    for i in range(num_variants):
        key = _gen_id(fdp) if fdp.ConsumeBool() else str(i)
        variants.append(f"    [{key}] {_gen_value(fdp)}")

    variants.append(f"   *[other] {_gen_value(fdp)}")
    variant_block = "\n".join(variants)
    source = f"{msg_id} = {{ ${selector_var} ->\n{variant_block}\n}}\n"
    _verify_roundtrip(source, pattern)


def _pattern_attributes(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Messages with .attr = value attributes."""
    msg_id = _gen_id(fdp)
    num_attrs = fdp.ConsumeIntInRange(1, 4)
    attrs = [f"    .{_gen_id(fdp)} = {_gen_value(fdp)}" for _ in range(num_attrs)]
    source = f"{msg_id} = {_gen_value(fdp)}\n" + "\n".join(attrs) + "\n"
    _verify_roundtrip(source, pattern)


def _pattern_comments(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Comment types: #, ##, ### followed by messages."""
    comment_type = fdp.ConsumeIntInRange(0, 2)
    prefix = "#" * (comment_type + 1)
    separator = "\n\n" if comment_type > 0 else "\n"
    source = f"{prefix} {_gen_value(fdp)}{separator}{_gen_id(fdp)} = {_gen_value(fdp)}\n"
    _verify_roundtrip(source, pattern)


def _pattern_function_call(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Function calls: { NUMBER($var) }, { DATETIME($d, opt: "val") }."""
    func = fdp.PickValueInList(["NUMBER", "DATETIME", "CURRENCY"])
    var = _gen_variable(fdp)
    if fdp.ConsumeBool():
        source = f'{_gen_id(fdp)} = {{ {func}(${var}, {_gen_id(fdp)}: "{_gen_value(fdp)}") }}\n'
    else:
        source = f"{_gen_id(fdp)} = {{ {func}(${var}) }}\n"
    _verify_roundtrip(source, pattern)


def _pattern_multiline_pattern(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Multiline continuation values."""
    msg_id = _gen_id(fdp)
    num_lines = fdp.ConsumeIntInRange(2, 5)
    lines = [f"{msg_id} ="] + [f"    {_gen_value(fdp)}" for _ in range(num_lines)]
    source = "\n".join(lines) + "\n"
    _verify_roundtrip(source, pattern)


def _pattern_mixed_resource(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Multiple entry types in a single resource."""
    entries: list[str] = []
    for _ in range(fdp.ConsumeIntInRange(2, 6)):
        entry_type = fdp.ConsumeIntInRange(0, 3)
        eid = _gen_id(fdp)
        val = _gen_value(fdp)
        match entry_type:
            case 0:
                entries.append(f"{eid} = {val}")
            case 1:
                entries.append(f"-{eid} = {val}")
            case 2:
                entries.append(f"{eid} = {val}\n    .{_gen_id(fdp)} = {_gen_value(fdp)}")
            case _:
                entries.append(f"{eid} = {val} {{ ${_gen_variable(fdp)} }}")
    source = "\n".join(entries) + "\n"
    _verify_roundtrip(source, pattern)


def _pattern_deep_nesting(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Nested placeables: string literals and variable references."""
    msg_id = _gen_id(fdp)
    source = f'{msg_id} = {{ "{_gen_value(fdp)}" }}\n'
    _verify_roundtrip(source, pattern)
    source2 = f"{msg_id} = {{ ${_gen_variable(fdp)} }}\n"
    _verify_roundtrip(source2, pattern)


def _pattern_raw_unicode(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Random Unicode input -- only verify junk-free inputs converge."""
    source = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 2048))
    _verify_roundtrip(source, pattern)


def _pattern_convergence_stress(fdp: atheris.FuzzedDataProvider, pattern: str) -> None:
    """Multi-pass convergence: verify S(P(x)) stabilizes in 4 passes."""
    msg_id = _gen_id(fdp)
    var = _gen_variable(fdp)
    sel_id = _gen_id(fdp)
    sel_var = _gen_variable(fdp)
    entries = [
        "# Generated test message",
        f"{msg_id} = {_gen_value(fdp)} {{ ${var} }}",
        f"    .title = {_gen_value(fdp)}",
        "",
        f"{sel_id} = {{ ${sel_var} ->",
        f"    [one] {_gen_value(fdp)}",
        f"   *[other] {_gen_value(fdp)}",
        "}",
    ]
    source = "\n".join(entries) + "\n"
    _verify_multi_pass_convergence(source, pattern)


# --- Pattern dispatch ---

_PATTERN_DISPATCH: dict[str, Any] = {
    "simple_message": _pattern_simple_message,
    "variable_placeable": _pattern_variable_placeable,
    "term_reference": _pattern_term_reference,
    "message_reference": _pattern_message_reference,
    "select_expression": _pattern_select_expression,
    "attributes": _pattern_attributes,
    "comments": _pattern_comments,
    "function_call": _pattern_function_call,
    "multiline_pattern": _pattern_multiline_pattern,
    "mixed_resource": _pattern_mixed_resource,
    "deep_nesting": _pattern_deep_nesting,
    "raw_unicode": _pattern_raw_unicode,
    "convergence_stress": _pattern_convergence_stress,
}


# --- Custom Mutator ---


def _custom_mutator(data: bytes, max_size: int, seed: int) -> bytes:
    """Structure-aware mutator: parse, mutate AST, serialize, byte-mutate.

    AST-level mutations (swap variants, duplicate attributes, mutate keys,
    nest placeables, shuffle entries) are applied before serialization.
    LibFuzzer byte-level mutation is then applied on top for fine-grained
    exploration around structurally valid inputs.
    """
    try:
        source = data.decode("utf-8", errors="replace")
        ast = _parser.parse(source)

        if ast.entries and not any(isinstance(e, Junk) for e in ast.entries):
            mutated_ast = _mutate_ast(ast, seed)
            serialized = serialize(mutated_ast)
            result = serialized.encode("utf-8")
            if len(result) <= max_size:
                return atheris.Mutate(result, max_size)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return atheris.Mutate(data, max_size)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz parser-serializer roundtrip."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    if fdp.remaining_bytes() < 2:
        return

    pattern_idx = fdp.ConsumeIntInRange(0, len(_PATTERN_SCHEDULE) - 1)
    pattern = _PATTERN_SCHEDULE[pattern_idx]
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp, pattern)

    except RoundtripFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = pattern in ("convergence_stress", "deep_nesting") or (
            (time.perf_counter() - start_time) * 1000 > 10.0
        )
        record_iteration_metrics(_state, pattern, start_time, data, is_interesting=is_interesting)

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the roundtrip fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Parser-serializer roundtrip fuzzer using Atheris/libFuzzer",
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

    print()
    print("=" * 80)
    print("Parser-Serializer Roundtrip Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     FluentParserV1, serialize")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Routing:    FDP-based weighted selection (schedule length: {len(_PATTERN_SCHEDULE)})")
    print("Mutator:    Custom (AST mutation + byte mutation)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input, custom_mutator=_custom_mutator)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
