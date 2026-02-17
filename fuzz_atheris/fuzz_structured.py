#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: structured - Structure-aware fuzzing (Deep AST)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Structure-Aware Fuzzer (Atheris).

Generates syntactically plausible FTL using grammar-aware construction,
then applies byte-level mutations. This improves coverage penetration
compared to pure random byte fuzzing by exercising deep parser paths
that random bytes rarely reach.

Patterns:
- simple_messages: Basic message generation and parsing
- variable_messages: Messages with variable placeables
- term_definitions: Term entries with references
- attribute_messages: Messages with dot-attributes
- select_expressions: Select expressions with variant keys
- comment_entries: Comment generation (single/group/resource)
- multi_entry: Complete resources with mixed entry types
- corrupted_input: Grammar-aware FTL with byte corruption
- deep_nesting: Deeply nested placeables and references
- roundtrip_verify: Parse-serialize-reparse identity check

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
When a finding is detected, the fuzzer writes human-readable artifacts to
.fuzz_atheris_corpus/structured/findings/ containing the actual FTL source, S1, S2,
and metadata JSON. These artifacts enable debugging without Atheris.

Metrics:
- Pattern coverage (10 patterns with weighted selection)
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
import contextlib
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
    write_finding_artifact,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class StructuredMetrics:
    """Domain-specific metrics for structured fuzzer."""

    parse_successes: int = 0
    parse_junk_entries: int = 0
    roundtrip_successes: int = 0
    roundtrip_mismatches: int = 0
    corruption_tests: int = 0
    deep_nesting_tests: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=1000,
    fuzzer_name="structured",
    fuzzer_target="FluentParserV1, FluentSerializer",
)
_domain = StructuredMetrics()


# Exception contract
ALLOWED_EXCEPTIONS = (ValueError, RecursionError, MemoryError, EOFError)

# Pattern weights: (name, weight)
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("simple_messages", 10),
    ("variable_messages", 12),
    ("term_definitions", 8),
    ("attribute_messages", 10),
    ("select_expressions", 15),
    ("comment_entries", 5),
    ("multi_entry", 15),
    ("corrupted_input", 10),
    ("deep_nesting", 8),
    ("roundtrip_verify", 7),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class StructuredFuzzError(Exception):
    """Raised when an unexpected exception is detected during structured fuzzing."""


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "structured"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["parse_successes"] = _domain.parse_successes
    stats["parse_junk_entries"] = _domain.parse_junk_entries
    stats["roundtrip_successes"] = _domain.roundtrip_successes
    stats["roundtrip_mismatches"] = _domain.roundtrip_mismatches
    stats["corruption_tests"] = _domain.corruption_tests
    stats["deep_nesting_tests"] = _domain.deep_nesting_tests

    if _state.iterations > 0:
        stats["junk_ratio"] = round(_domain.parse_junk_entries / _state.iterations, 4)

    return stats


_REPORT_FILENAME = "fuzz_structured_report.json"


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()

    junk_ratio = stats.get("junk_ratio", 0.0)
    if isinstance(junk_ratio, float) and junk_ratio > 0.5:
        print(
            f"[WARN] Junk ratio {junk_ratio * 100:.1f}% exceeds 50% threshold",
            file=sys.stderr,
            flush=True,
        )

    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)


# --- Finding Artifacts (delegated to fuzz_common) ---

_FINDINGS_DIR = _REPORT_DIR / "findings"


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

# Enable string and regex comparison instrumentation for better coverage
# of message ID lookups, pattern-based parsing, and selector key matching
atheris.enabled_hooks.add("str")
atheris.enabled_hooks.add("RegEx")

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.ast import (
        Identifier,
        Junk,
        Message,
        Placeable,
        Resource,
        SelectExpression,
        StringLiteral,
        Term,
    )
    from ftllexengine.syntax.parser import FluentParserV1
    from ftllexengine.syntax.serializer import FluentSerializer, serialize

# Module-level reusable instances (criticism #7: avoid per-call allocation)
_parser = FluentParserV1()
_serializer = FluentSerializer()

# Plural categories for AST-level mutations
_PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")


# --- FTL Generation Helpers (delegated to fuzz_common) ---
# gen_ftl_identifier, gen_ftl_value imported from fuzz_common


def _generate_variant_key(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a variant key (identifier or numeric literal)."""
    if not fdp.remaining_bytes():
        return "other"

    if fdp.ConsumeIntInRange(0, 9) < 4:
        is_decimal = fdp.ConsumeBool() if fdp.remaining_bytes() else False
        is_negative = fdp.ConsumeBool() if fdp.remaining_bytes() else False
        int_part = fdp.ConsumeIntInRange(0, 999) if fdp.remaining_bytes() else 1

        if is_decimal and fdp.remaining_bytes():
            decimal_part = fdp.ConsumeIntInRange(0, 99)
            num_str = f"{int_part}.{decimal_part:02d}"
        else:
            num_str = str(int_part)

        if is_negative:
            num_str = f"-{num_str}"
        return num_str

    return gen_ftl_identifier(fdp)


def _generate_simple_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: msg-id = text value."""
    msg_id = gen_ftl_identifier(fdp)
    value = gen_ftl_value(fdp)
    return f"{msg_id} = {value}"


def _generate_variable_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: msg-id = prefix { $var } suffix."""
    msg_id = gen_ftl_identifier(fdp)
    var_name = gen_ftl_identifier(fdp)
    prefix = gen_ftl_value(fdp, max_length=20)
    suffix = gen_ftl_value(fdp, max_length=20)
    return f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"


def _generate_term(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate: -term-id = value."""
    term_id = gen_ftl_identifier(fdp)
    value = gen_ftl_value(fdp)
    return f"-{term_id} = {value}"


def _generate_attribute_message(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate message with attributes."""
    msg_id = gen_ftl_identifier(fdp)
    value = gen_ftl_value(fdp)
    num_attrs = fdp.ConsumeIntInRange(1, 4) if fdp.remaining_bytes() else 1
    attrs = []
    for _ in range(num_attrs):
        if not fdp.remaining_bytes():
            break
        attr_name = gen_ftl_identifier(fdp)
        attr_value = gen_ftl_value(fdp, max_length=30)
        attrs.append(f"    .{attr_name} = {attr_value}")
    attr_block = "\n".join(attrs)
    return f"{msg_id} = {value}\n{attr_block}"


def _generate_select_expression(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate message with select expression."""
    msg_id = gen_ftl_identifier(fdp)
    var_name = gen_ftl_identifier(fdp)

    num_variants = fdp.ConsumeIntInRange(2, 5) if fdp.remaining_bytes() else 2
    default_idx = (
        fdp.ConsumeIntInRange(0, num_variants - 1) if fdp.remaining_bytes() else num_variants - 1
    )

    variants = []
    for i in range(num_variants):
        if not fdp.remaining_bytes():
            break
        key = _generate_variant_key(fdp)
        val = gen_ftl_value(fdp, max_length=30)
        prefix = "*" if i == default_idx else " "
        variants.append(f"   {prefix}[{key}] {val}")

    variants_str = "\n".join(variants)
    return f"{msg_id} = {{ ${var_name} ->\n{variants_str}\n}}"


def _generate_comment(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate FTL comment (single, group, or resource)."""
    level = fdp.ConsumeIntInRange(1, 3) if fdp.remaining_bytes() else 1
    prefix = "#" * level
    content = gen_ftl_value(fdp, max_length=40)
    return f"{prefix} {content}"


def _generate_ftl_resource(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a complete FTL resource with multiple entries."""
    if not fdp.remaining_bytes():
        return "fallback = Fallback value"

    num_entries = fdp.ConsumeIntInRange(1, 10)
    entries: list[str] = []

    generators = [
        _generate_simple_message,
        _generate_variable_message,
        _generate_term,
        _generate_attribute_message,
        _generate_select_expression,
        _generate_comment,
    ]

    for _ in range(num_entries):
        if not fdp.remaining_bytes():
            break
        gen_idx = fdp.ConsumeIntInRange(0, len(generators) - 1)
        try:
            entry = generators[gen_idx](fdp)
            entries.append(entry)
        except (IndexError, ValueError):
            break

    return "\n\n".join(entries) if entries else "fallback = Fallback value"


def _generate_deep_nesting(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate deeply nested placeables and references."""
    msg_id = gen_ftl_identifier(fdp)
    depth = fdp.ConsumeIntInRange(3, 15) if fdp.remaining_bytes() else 5

    # Nested placeables: { { { $var } } }
    var_name = gen_ftl_identifier(fdp)
    expr = f"${var_name}"
    for _ in range(depth):
        expr = f"{{ {expr} }}"

    result = f"{msg_id} = {expr}"

    # Optionally add a chain of message references
    if fdp.ConsumeBool() and fdp.remaining_bytes() > 4:
        chain_len = fdp.ConsumeIntInRange(2, 8)
        chain_entries = [result]
        prev_id = msg_id
        for i in range(chain_len):
            if not fdp.remaining_bytes():
                break
            new_id = f"chain{i}"
            chain_entries.append(f"{new_id} = {{ {prev_id} }}")
            prev_id = new_id
        result = "\n".join(chain_entries)

    return result


# --- AST-Level Mutations ---


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
                inner = Placeable(expression=elem.expression)
                new_elem = dc_replace(elem, expression=inner)
                new_elements = list(entry.value.elements)
                new_elements[idx] = new_elem
                new_pattern = dc_replace(entry.value, elements=tuple(new_elements))
                entries[i] = dc_replace(entry, value=new_pattern)
                return entries
    return entries


# --- Verification ---


def _verify_roundtrip(source: str, parser: FluentParserV1) -> None:
    """Verify parse-serialize-reparse identity."""
    result = parser.parse(source)

    # Skip roundtrip if parse produced junk
    if any(isinstance(e, Junk) for e in result.entries):
        _domain.parse_junk_entries += 1
        return

    _domain.parse_successes += 1

    try:
        serialized = _serializer.serialize(result)
        reparsed = parser.parse(serialized)

        # Entry count must match
        if len(result.entries) != len(reparsed.entries):
            _domain.roundtrip_mismatches += 1
            write_finding_artifact(
                findings_dir=_FINDINGS_DIR, state=_state,
                source=source, s1=serialized,
                s2="<entry count mismatch -- S2 not computed>",
                pattern="roundtrip_verify",
                extra_meta={
                    "failure_type": "entry_count_mismatch",
                    "entries_parse1": len(result.entries),
                    "entries_parse2": len(reparsed.entries),
                },
            )
            msg = (
                f"Round-trip entry count mismatch: "
                f"{len(result.entries)} -> {len(reparsed.entries)}\n"
                f"Source ({len(source)} chars): {source[:300]!r}\n"
                f"S1 ({len(serialized)} chars): {serialized[:300]!r}"
            )
            raise StructuredFuzzError(msg)

        # Convergence: serialize(reparse(serialize(parse(x)))) == serialize(parse(x))
        reserialized = _serializer.serialize(reparsed)
        if serialized != reserialized:
            _domain.roundtrip_mismatches += 1
            write_finding_artifact(
                findings_dir=_FINDINGS_DIR, state=_state,
                source=source, s1=serialized, s2=reserialized,
                pattern="roundtrip_verify",
                extra_meta={"failure_type": "convergence_failure"},
            )
            msg = (
                f"Round-trip convergence failure: S(P(S(P(x)))) != S(P(x))\n"
                f"Source ({len(source)} chars): {source[:300]!r}\n"
                f"S1 ({len(serialized)} chars): {serialized[:300]!r}\n"
                f"S2 ({len(reserialized)} chars): {reserialized[:300]!r}"
            )
            raise StructuredFuzzError(msg)

        _domain.roundtrip_successes += 1

    except ALLOWED_EXCEPTIONS:
        pass


def _parse_and_check(source: str, parser: FluentParserV1) -> None:
    """Parse source and verify non-trivial input produces entries."""
    result = parser.parse(source)

    if any(isinstance(e, Junk) for e in result.entries):
        _domain.parse_junk_entries += 1
    else:
        _domain.parse_successes += 1

    # Non-trivial input should produce entries
    if len(result.entries) == 0 and len(source.strip()) > 10 and "corruption" not in source[:50]:
        _state.findings += 1
        msg = f"Empty AST for non-trivial input: {source[:100]!r}"
        raise StructuredFuzzError(msg)


# --- Custom Mutator ---


def _custom_mutator(data: bytes, max_size: int, seed: int) -> bytes:
    """Structure-aware mutator: parse, mutate AST, serialize, byte-mutate.

    AST-level mutations (swap variants, duplicate attributes, mutate keys,
    nest placeables, shuffle entries) are applied before serialization.
    LibFuzzer byte-level mutation is then applied on top for fine-grained
    exploration around structurally valid inputs.

    KeyboardInterrupt is caught separately to allow graceful shutdown
    without traceback noise when Ctrl+C is pressed during mutation.
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
    except KeyboardInterrupt:
        _state.status = "stopped"
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Fallback: standard byte-level mutation
    return atheris.Mutate(data, max_size)


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: generate structured FTL and detect crashes."""
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

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    if not fdp.remaining_bytes():
        return

    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=100)
    source = ""

    try:
        match pattern:
            case "simple_messages":
                source = _generate_simple_message(fdp)
                _parse_and_check(source, parser)

            case "variable_messages":
                source = _generate_variable_message(fdp)
                _parse_and_check(source, parser)

            case "term_definitions":
                source = _generate_term(fdp)
                # Add a referencing message so term is exercised
                ref_id = gen_ftl_identifier(fdp)
                term_name = source.split("=", maxsplit=1)[0].strip()
                source += f"\n{ref_id} = {{ {term_name} }}"
                _parse_and_check(source, parser)

            case "attribute_messages":
                source = _generate_attribute_message(fdp)
                _parse_and_check(source, parser)

            case "select_expressions":
                source = _generate_select_expression(fdp)
                _parse_and_check(source, parser)

            case "comment_entries":
                source = _generate_comment(fdp)
                # Comments alone produce entries
                parser.parse(source)

            case "multi_entry":
                source = _generate_ftl_resource(fdp)
                _parse_and_check(source, parser)

            case "corrupted_input":
                _domain.corruption_tests += 1
                source = _generate_ftl_resource(fdp)
                if fdp.remaining_bytes() and len(source) > 0:
                    pos = fdp.ConsumeIntInRange(0, len(source) - 1)
                    corruption = fdp.ConsumeUnicodeNoSurrogates(
                        min(3, fdp.remaining_bytes()),
                    )
                    source = source[:pos] + corruption + source[pos + 1 :]
                with contextlib.suppress(*ALLOWED_EXCEPTIONS):
                    parser.parse(source)

            case "deep_nesting":
                _domain.deep_nesting_tests += 1
                source = _generate_deep_nesting(fdp)
                with contextlib.suppress(*ALLOWED_EXCEPTIONS):
                    _parse_and_check(source, parser)

            case "roundtrip_verify":
                source = _generate_ftl_resource(fdp)
                _verify_roundtrip(source, parser)

    except StructuredFuzzError:
        _state.findings += 1
        _state.status = "finding"
        raise

    except ALLOWED_EXCEPTIONS:
        pass

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

        _state.findings += 1
        _state.status = "finding"

        print("\n" + "=" * 80, file=sys.stderr)
        print("[FINDING] STABILITY BREACH DETECTED (Structure-Aware)", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}", file=sys.stderr)
        print(f"Error Message:  {e}", file=sys.stderr)
        print(f"Input Preview:  {source[:200]!r}...", file=sys.stderr)
        print("-" * 80, file=sys.stderr)

        msg = f"{type(e).__name__}: {e}"
        raise StructuredFuzzError(msg) from e

    finally:
        is_interesting = (
            "deep_nesting" in pattern
            or "corrupted" in pattern
            or "roundtrip" in pattern
            or (time.perf_counter() - start_time) * 1000 > 50.0
        )
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        # Break reference cycles from Atheris instrumentation
        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the structure-aware fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Structure-aware FTL fuzzer using Atheris/libFuzzer",
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

    # Inject -rss_limit_mb default if not already specified.
    # AST allocations can accumulate between gc passes; 4096 MB provides
    # headroom while catching true leaks before system OOM-kill.
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Structure-Aware Fuzzer (Atheris)",
        target="FluentParserV1, FluentSerializer",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(
        _state,
        test_one_input=test_one_input,
        custom_mutator=_custom_mutator,
    )


if __name__ == "__main__":
    main()
