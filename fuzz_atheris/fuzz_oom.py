#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: oom - Memory Density (Object Explosion)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Memory Density and Object Explosion Fuzzer (Atheris).

Targets: ftllexengine.syntax.parser.FluentParserV1
Detects "Billion Laughs" style attacks where small inputs generate massive ASTs.

Concern boundary: This fuzzer targets parser-level amplification -- small FTL
inputs that produce disproportionately large AST trees. This is distinct from
the runtime fuzzer (resolver/bundle/cache stack) and currency fuzzer (numeric
parsing). The threat model is denial-of-service via parser object explosion.

Metrics:
- AST node density (nodes per KB of source)
- Real memory usage (RSS via psutil)
- Performance profiling (min/mean/median/p95/p99/max)
- Pathological pattern detection (top 10 densest inputs)
- Seed corpus management (interesting inputs)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import hashlib
import heapq
import logging
import pathlib
import sys
import time
from collections import deque
from dataclasses import dataclass, field
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

# --- Domain Metrics ---

@dataclass
class OOMMetrics:
    """Domain-specific metrics for OOM/density fuzzer."""

    # Density tracking
    density_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000),
    )
    densest_inputs: list[tuple[float, int, int, str]] = field(
        default_factory=list,
    )

    # Corpus productivity
    seed_corpus_entries_added: int = 0
    seed_corpus_max_size: int = 1000

    # In-memory seed corpus (interesting inputs)
    seed_corpus_local: dict[str, str] = field(default_factory=dict)


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=1000,
    fuzzer_name="oom",
    fuzzer_target="FluentParserV1",
)
_domain = OOMMetrics()


# --- Pattern Weights and Schedule ---

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("placeable_nest", 8),
    ("attribute_explosion", 8),
    ("select_nest", 7),
    ("variant_explosion", 7),
    ("reference_chain", 8),
    ("term_nest", 7),
    ("mixed_placeable_select", 7),
    ("attribute_select_combo", 7),
    ("raw_bytes", 10),
    ("comment_flood", 6),
    ("message_flood", 6),
    ("multiline_value", 6),
    ("variant_expression_explosion", 6),
    ("cyclic_chain", 6),
    ("term_message_cross_ref", 6),
    ("attr_deep_placeable", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {
    name: float(weight) for name, weight in _PATTERN_WEIGHTS
}


class OOMFuzzError(Exception):
    """Raised when an OOM/density invariant is breached."""


# Allowed exceptions from parser (expected safety mechanisms)
ALLOWED_EXCEPTIONS = (
    ValueError,
    RecursionError,
    MemoryError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "oom"
_REPORT_FILENAME = "fuzz_oom_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific: density distribution
    if _domain.density_history:
        import statistics  # noqa: PLC0415 - only needed for reporting

        density_data = list(_domain.density_history)
        stats["density_mean"] = round(statistics.mean(density_data), 1)
        stats["density_median"] = round(statistics.median(density_data), 1)
        stats["density_max"] = round(max(density_data), 1)

    # Domain-specific: densest inputs and local corpus
    stats["densest_inputs_tracked"] = len(_domain.densest_inputs)
    stats["domain_corpus_entries_added"] = _domain.seed_corpus_entries_added
    stats["domain_seed_corpus_size"] = len(_domain.seed_corpus_local)

    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(
        _state, stats, _REPORT_DIR, _REPORT_FILENAME,
    )


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.syntax.parser import FluentParserV1


def count_nodes(node: Any) -> int:
    """Count AST nodes via recursive attribute traversal.

    Uses attribute probing to handle all AST node types without importing
    the full AST module (which would add coupling to node class internals).
    """
    count = 1
    if hasattr(node, "entries"):  # Resource
        for entry in node.entries:
            count += count_nodes(entry)
    if hasattr(node, "value") and node.value:  # Message/Term/Attribute
        count += count_nodes(node.value)
    if hasattr(node, "attributes"):  # Message/Term
        for attr in node.attributes:
            count += count_nodes(attr)
    if hasattr(node, "elements"):  # Pattern
        for elem in node.elements:
            count += count_nodes(elem)
    if hasattr(node, "expression"):  # Placeable
        count += count_nodes(node.expression)
    if hasattr(node, "selector"):  # SelectExpression
        count += count_nodes(node.selector)
    if hasattr(node, "variants"):  # SelectExpression
        for variant in node.variants:
            count += count_nodes(variant)
    return count


# --- Pathological Pattern Constants ---
_IDENTIFIERS: Sequence[str] = (
    "msg", "msg2", "msg3", "a", "b", "c", "d", "e",
)

_VAR_NAMES: Sequence[str] = (
    "$var", "$sel", "$count", "$type", "$x",
)

_SELECTOR_KEYS: Sequence[str] = (
    "one", "two", "few", "many", "other", "zero",
)


def _generate_pathological_ftl(  # noqa: PLR0911, PLR0912
    fdp: atheris.FuzzedDataProvider,
    pattern_name: str,
) -> str:
    """Generate pathological FTL for the given pattern targeting AST explosion.

    16 pattern types targeting distinct amplification vectors.
    High branch count maps fuzzed bytes to structurally diverse attack patterns.

    Returns:
        ftl_source string
    """
    depth = fdp.ConsumeIntInRange(1, 200)
    msg_id = "msg"

    match pattern_name:
        case "placeable_nest":
            return f"{msg_id} = " + ("{ " * depth) + "$var" + (" }" * depth) + "\n"

        case "attribute_explosion":
            attrs = "\n".join(f"    .attr{i} = val" for i in range(depth))
            return f"{msg_id} = val\n{attrs}\n"

        case "select_nest":
            nested = "$type"
            for i in range(depth):
                nested = f"{{ {nested} ->\n    [opt{i}] Inner\n   *[other] Outer\n}}"
            return f"{msg_id} = {nested}\n"

        case "variant_explosion":
            variants = "\n".join(f"    [var{i}] Value {i}" for i in range(depth))
            return f"{msg_id} = {{ $sel ->\n{variants}\n   *[other] Default\n}}\n"

        case "reference_chain":
            refs = "\n".join(f"msg{i} = {{ msg{i + 1} }}" for i in range(depth))
            return f"{refs}\nmsg{depth} = Final\n"

        case "term_nest":
            terms = "\n".join(f"-term{i} = {{ -term{i + 1} }}" for i in range(depth))
            return f"{terms}\n-term{depth} = Base\n{msg_id} = {{ -term0 }}\n"

        case "mixed_placeable_select":
            mixed = "{ " * (depth // 2) + "$var" + " }" * (depth // 2)
            return f"{msg_id} = {{ $sel ->\n    [a] {mixed}\n   *[b] Other\n}}\n"

        case "attribute_select_combo":
            attrs = "\n".join(
                f"    .attr{i} = {{ $sel ->\n        [a] Val\n       *[b] Other\n    }}"
                for i in range(min(depth, 50))
            )
            return f"{msg_id} = Root\n{attrs}\n"

        case "raw_bytes":
            return fdp.ConsumeUnicode(fdp.ConsumeIntInRange(0, 500))

        case "comment_flood":
            comments = "\n".join(f"# Comment line {i}" for i in range(depth))
            return f"{comments}\n{msg_id} = value\n"

        case "message_flood":
            messages = "\n".join(f"m{i} = value{i}" for i in range(depth))
            return messages + "\n"

        case "multiline_value":
            lines = "\n    ".join(f"line {i}" for i in range(depth))
            return f"{msg_id} =\n    {lines}\n"

        case "variant_expression_explosion":
            var = fdp.PickValueInList(list(_VAR_NAMES))
            variants_parts: list[str] = []
            for i in range(min(depth, 100)):
                # Each variant arm has a placeable
                prefix = "*" if i == 0 else ""
                variants_parts.append(
                    f"    [{prefix}v{i}] {{ {var} }} text {i}"
                )
            variants_str = "\n".join(variants_parts)
            return f"{msg_id} = {{ $sel ->\n{variants_str}\n}}\n"

        case "cyclic_chain":
            chain_len = min(depth, 50)
            parts: list[str] = []
            for i in range(chain_len):
                next_id = f"c{(i + 1) % chain_len}"
                parts.append(f"c{i} = {{ {next_id} }}")
            return "\n".join(parts) + "\n"

        case "term_message_cross_ref":
            terms = "\n".join(f"-t{i} = Term{i}" for i in range(min(depth, 50)))
            msgs = "\n".join(
                f"m{i} = {{ -t{i % min(depth, 50)} }}" for i in range(min(depth, 50))
            )
            return f"{terms}\n{msgs}\n"

        case "attr_deep_placeable":
            nest_depth = min(depth, 30)
            inner = "$var"
            for _ in range(nest_depth):
                inner = f"{{ {inner} }}"
            num_attrs = fdp.ConsumeIntInRange(1, 20)
            attrs_list = "\n".join(f"    .a{i} = {inner}" for i in range(num_attrs))
            return f"{msg_id} = root\n{attrs_list}\n"

        case _:
            # Unreachable fallback
            return f"{msg_id} = Fallback\n"


# --- Pattern Dispatch ---

_PATTERN_DISPATCH: dict[str, str] = {
    name: name for name, _ in _PATTERN_WEIGHTS
}


def _track_densest_input(
    density: float,
    node_count: int,
    source_bytes: int,
    source: str,
) -> None:
    """Track top 10 densest inputs using min-heap."""
    source_hash = hashlib.sha256(
        source.encode("utf-8", errors="surrogatepass")
    ).hexdigest()[:16]
    entry = (density, node_count, source_bytes, source_hash)

    if len(_domain.densest_inputs) < 10:
        heapq.heappush(_domain.densest_inputs, entry)
    elif density > _domain.densest_inputs[0][0]:  # Beat minimum
        heapq.heapreplace(_domain.densest_inputs, entry)


def _track_seed_corpus(source: str, pattern: str, density: float) -> None:
    """Track interesting inputs for seed corpus with LRU-like eviction."""
    is_interesting = density > 1000 or "raw_bytes" in pattern or "cyclic" in pattern

    if is_interesting:
        source_hash = hashlib.sha256(
            source.encode("utf-8", errors="surrogatepass")
        ).hexdigest()[:16]
        if source_hash not in _domain.seed_corpus_local:
            if len(_domain.seed_corpus_local) >= _domain.seed_corpus_max_size:
                oldest_key = next(iter(_domain.seed_corpus_local))
                del _domain.seed_corpus_local[oldest_key]
            _domain.seed_corpus_local[source_hash] = source
            _domain.seed_corpus_entries_added += 1


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Detect billion laughs style AST explosion attacks.

    Observability:
    - Performance: Tracks timing per iteration
    - Memory: Tracks RSS via psutil
    - Density: Tracks AST nodes per KB (threshold: 5000 nodes/KB)
    - Patterns: Coverage of 16 pathological pattern types
    - Corpus: Interesting inputs (density > 1000, raw bytes, cyclic)
    """
    # Initialize memory baseline on first iteration
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint report
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    # Performance timing
    start_time = time.perf_counter()

    fdp = atheris.FuzzedDataProvider(data)

    # Pattern selection via deterministic round-robin
    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    source = ""
    parser = FluentParserV1(max_source_size=1024 * 1024, max_nesting_depth=500)

    try:
        source = _generate_pathological_ftl(fdp, pattern_name)

        res = parser.parse(source)
        node_count = count_nodes(res)

        # Density check: Nodes per KB of source
        source_bytes = len(source.encode("utf-8", errors="surrogatepass"))
        source_size_kb = max(source_bytes / 1024.0, 0.1)
        density = node_count / source_size_kb

        # Track domain-specific metrics
        _domain.density_history.append(density)
        _track_densest_input(density, node_count, source_bytes, source)
        _track_seed_corpus(source, pattern_name, density)

        # Threshold: 5000 nodes/KB is pathological for Fluent 1.0 spec
        # Record as finding but do NOT raise -- crashing the fuzzer prevents
        # further exploration and causes libFuzzer to treat it as a bug
        if density > 5000:
            _state.findings += 1

    except (ValueError, RecursionError, MemoryError, FrozenFluentError):
        # Expected: Parser enforces max_nesting_depth and max_source_size.
        # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED as a safety
        # mechanism regardless of strict mode to prevent stack overflow.
        pass
    except Exception:
        # Unexpected exceptions are findings -- re-raise for Atheris to capture
        _state.findings += 1
        raise
    finally:
        is_interesting = pattern_name in ("raw_bytes", "cyclic_chain") or (
            (time.perf_counter() - start_time) * 1000 > 10.0
        )
        record_iteration_metrics(
            _state, pattern_name, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the OOM fuzzer with optional --help."""
    parser = argparse.ArgumentParser(
        description="Memory density / object explosion fuzzer using Atheris/libFuzzer",
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

    # Parse known args, pass rest to Atheris/libFuzzer
    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Inject RSS limit if not already specified
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    # Reconstruct sys.argv for Atheris
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Memory Density / Object Explosion Fuzzer (Atheris)",
        target="FluentParserV1",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            "Threshold:  5000 nodes/KB (pathological density)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
