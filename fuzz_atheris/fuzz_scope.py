#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: scope - Variable Shadowing & Scoping Invariants
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Variable Scope & Resolution Context Fuzzer (Atheris).

Targets: ftllexengine.runtime.resolver (FluentResolver, ResolutionContext,
         GlobalDepthGuard) via ftllexengine.runtime.bundle.FluentBundle

Concern boundary: This fuzzer stress-tests variable scoping, term argument
isolation, message reference scope inheritance, ResolutionContext push/pop
symmetry, GlobalDepthGuard cross-context depth tracking, select expression
scope, function call argument scope, attribute resolution scope, and
bidirectional isolation mark correctness.

Distinct from fuzz_runtime.py which exercises the full runtime stack
(caching, concurrency, strict mode). This fuzzer focuses exclusively on
the resolver's scoping invariants.

Metrics:
- Pattern coverage with weighted selection (12 patterns)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management
- Per-pattern wall-time accumulation

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)

# --- Dependency Checks with Clear Errors ---
_MISSING_DEPS: list[str] = []

try:
    import psutil
except ImportError:
    _MISSING_DEPS.append("psutil")
    psutil = None  # type: ignore[assignment]

try:
    import atheris
except ImportError:
    _MISSING_DEPS.append("atheris")
    atheris = None  # type: ignore[assignment]

if _MISSING_DEPS:
    print("-" * 80, file=sys.stderr)
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=10000)
    )
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 100


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


def _emit_final_report() -> None:
    """Emit JSON report to stderr and file (crash-proof via atexit)."""
    perf = list(_state.performance_history)
    mem = list(_state.memory_history)

    report: dict[str, Any] = {
        "status": "complete" if _state.iterations > 0 else "incomplete",
        "iterations": _state.iterations,
        "findings": _state.findings,
        "error_types": len(_state.error_counts),
        "patterns_tested": len(_state.pattern_coverage),
        "corpus_entries_added": _state.corpus_entries_added,
        "seed_corpus_size": len(_state.seed_corpus),
        "slowest_operations_tracked": len(_state.slowest_operations),
    }

    if perf:
        sorted_perf = sorted(perf)
        n = len(sorted_perf)
        report.update({
            "perf_min_ms": round(sorted_perf[0], 3),
            "perf_mean_ms": round(statistics.mean(sorted_perf), 3),
            "perf_median_ms": round(statistics.median(sorted_perf), 3),
            "perf_p95_ms": round(sorted_perf[min(int(n * 0.95), n - 1)], 3),
            "perf_p99_ms": round(sorted_perf[min(int(n * 0.99), n - 1)], 3),
            "perf_max_ms": round(sorted_perf[-1], 3),
        })

    if mem:
        report.update({
            "memory_peak_mb": round(max(mem), 2),
            "memory_mean_mb": round(statistics.mean(mem), 2),
            "memory_delta_mb": round(max(mem) - min(mem), 2),
            "memory_growth_mb": round(mem[-1] - mem[0], 2) if len(mem) > 1 else 0.0,
            "memory_leak_detected": int(
                len(mem) > 100
                and statistics.mean(list(mem)[-25:])
                > statistics.mean(list(mem)[:25]) * 1.1
            ),
        })

    # Per-pattern coverage and wall time
    for name, count in sorted(_state.pattern_coverage.items()):
        report[f"pattern_{name}"] = count
    for name, ms in sorted(_state.pattern_wall_time.items()):
        report[f"wall_time_ms_{name}"] = round(ms, 1)

    report_json = json.dumps(report)
    print(f"\n[SUMMARY-JSON-BEGIN]{report_json}[SUMMARY-JSON-END]", file=sys.stderr)

    # Write to corpus directory
    corpus_dir = pathlib.Path(".fuzz_atheris_corpus") / "scope"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    report_path = corpus_dir / "fuzz_scope_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.runtime.bundle import FluentBundle


# --- Custom error for scope invariant violations ---
class ScopeFuzzError(Exception):
    """Raised when a scope invariant is violated."""


# --- Pattern weights ---
# Ordered cheapest-first to counteract libFuzzer's small-byte bias:
# ConsumeIntInRange skews toward low values, over-selecting early entries.
# Cheap patterns (single FluentBundle, simple FTL) go first; expensive
# patterns (multiple bundles, deep nesting) go last.
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    # Cheap: simple FTL, single bundle
    ("term_arg_isolation", 12),
    ("variable_shadowing", 12),
    ("message_ref_scope", 10),
    ("select_scope", 10),
    ("attribute_scope", 8),
    ("bidi_isolation", 8),
    ("function_arg_scope", 8),
    # Medium: multiple messages/terms
    ("nested_term_scope", 8),
    ("scope_chain", 8),
    ("cross_message_isolation", 6),
    # Expensive: depth guards, error paths
    ("depth_guard_boundary", 5),
    ("adversarial_scope", 5),
)

_TOTAL_WEIGHT: int = sum(w for _, w in _PATTERN_WEIGHTS)

# Pre-compute cumulative weights for O(1) pattern selection
_CUMULATIVE_WEIGHTS: tuple[int, ...] = tuple(
    sum(w for _, w in _PATTERN_WEIGHTS[: i + 1])
    for i in range(len(_PATTERN_WEIGHTS))
)

# Allowed exceptions from scope operations
_ALLOWED_EXCEPTIONS = (
    ValueError, TypeError, OverflowError,
    FrozenFluentError, RecursionError, RuntimeError,
)

# Node ID pool for FTL message/term identifiers
_NODE_IDS: tuple[str, ...] = (
    "welcome", "greeting", "title", "description", "label",
    "heading", "footer", "nav", "content", "status",
)

# Variable name pool
_VAR_NAMES: tuple[str, ...] = (
    "name", "count", "user", "item", "value",
    "total", "index", "type", "lang", "size",
)

# Locale pool
_LOCALES: tuple[str, ...] = (
    "en-US", "de-DE", "fr-FR", "ja-JP", "ar-SA", "zh-CN", "pl-PL",
)


def _pick_id(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick a message/term identifier from pool."""
    return fdp.PickValueInList(list(_NODE_IDS))


def _pick_var(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick a variable name from pool."""
    return fdp.PickValueInList(list(_VAR_NAMES))


def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick a locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 10))


def _gen_value(fdp: atheris.FuzzedDataProvider) -> str:
    """Generate a short ASCII-safe string value for FTL patterns."""
    # Use ASCII to avoid FTL parsing issues with special Unicode
    length = fdp.ConsumeIntInRange(1, 10)
    raw = fdp.ConsumeBytes(length)
    # Map to safe ASCII range [a-z0-9]
    return "".join(chr(ord("a") + (b % 26)) for b in raw) or "x"


# --- Pattern Implementations ---


def _pattern_term_arg_isolation(fdp: atheris.FuzzedDataProvider) -> None:
    """Term arguments are isolated: terms see ONLY explicit args, not caller's.

    Per Fluent spec, terms receive data from messages in which they are used,
    but ONLY through explicit parameterization like -term(arg: val).
    """
    var = _pick_var(fdp)
    outer_val = _gen_value(fdp)
    term_arg_val = _gen_value(fdp)

    ftl = (
        f'msg = {{ -brand({var}: "{term_arg_val}") }}\n'
        f"-brand = {{ ${var} }}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value("msg", {var: outer_val})

    # Term receives explicit arg, so should resolve to term_arg_val
    if result == term_arg_val:
        return  # Correct: term used its explicit arg

    # If the term resolved to outer_val, that's a scope leak
    if result == outer_val:
        msg = (
            f"Scope leak: term resolved to outer ${var}='{outer_val}' "
            f"instead of explicit arg '{term_arg_val}'"
        )
        raise ScopeFuzzError(msg)

    # If there are errors, the term couldn't resolve -- acceptable for edge cases
    if not errors:
        msg = f"Unexpected resolution: '{result}' (expected '{term_arg_val}')"
        raise ScopeFuzzError(msg)


def _pattern_variable_shadowing(fdp: atheris.FuzzedDataProvider) -> None:
    """External $var preserved around term call that uses same variable name.

    Tests that the resolver correctly saves/restores the outer scope
    when entering and leaving a term's isolated scope.
    """
    var = _pick_var(fdp)
    ext_val = _gen_value(fdp)
    term_val = _gen_value(fdp)

    ftl = (
        f'msg = {{ ${var} }} - {{ -term({var}: "{term_val}") }} - {{ ${var} }}\n'
        f"-term = {{ ${var} }}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value("msg", {var: ext_val})

    expected = f"{ext_val} - {term_val} - {ext_val}"
    if result != expected and not errors:
        msg = f"Shadowing failure: expected '{expected}', got '{result}'"
        raise ScopeFuzzError(msg)


def _pattern_message_ref_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Message references share the calling context's args (unlike terms).

    Per Fluent spec, when a message references another message, the
    referenced message has access to the same external arguments.
    """
    var = _pick_var(fdp)
    val = _gen_value(fdp)
    msg_a = _pick_id(fdp)
    msg_b = f"ref-{_pick_id(fdp)}"

    ftl = (
        f"{msg_a} = {{ {msg_b} }}\n"
        f"{msg_b} = {{ ${var} }}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value(msg_a, {var: val})

    # Referenced message should see the caller's args
    if result == val:
        return  # Correct

    # If there are resolution errors, acceptable (e.g., cycle if msg_a == msg_b)
    if not errors:
        msg = f"Message ref scope: expected '{val}', got '{result}'"
        raise ScopeFuzzError(msg)


def _pattern_select_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Select expression selector and variant patterns share message scope.

    The selector evaluates in the same scope as the message, and
    variant patterns also have access to the same args.
    """
    var = _pick_var(fdp)
    count = fdp.ConsumeIntInRange(0, 10)
    extra_val = _gen_value(fdp)

    ftl = (
        f"msg = {{ ${var} ->\n"
        f"    [0] zero {{ $extra }}\n"
        f"   *[other] other {{ $extra }}\n"
        f"}}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value(
        "msg", {var: count, "extra": extra_val}
    )

    # Both the selector ($var) and variant body ($extra) should resolve
    if extra_val in result:
        return  # Correct: variant body resolved the extra variable

    # Error path is acceptable for edge-case inputs
    if not errors:
        msg = (
            f"Select scope: expected '{extra_val}' in result, "
            f"got '{result}'"
        )
        raise ScopeFuzzError(msg)


def _pattern_attribute_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Attribute patterns share the message's scope."""
    var = _pick_var(fdp)
    val = _gen_value(fdp)
    msg_id = _pick_id(fdp)
    attr_name = fdp.PickValueInList(["tooltip", "label", "title", "placeholder"])

    ftl = (
        f"{msg_id} = Main {{ ${var} }}\n"
        f"    .{attr_name} = Attr {{ ${var} }}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    # Test message value
    result_val, errors_val = bundle.format_value(msg_id, {var: val})

    # Test attribute
    result_attr, errors_attr = bundle.format_pattern(
        msg_id, {var: val}, attribute=attr_name
    )

    # Both should contain the variable value
    if not errors_val and val not in result_val:
        msg = f"Attribute scope: message value missing ${var}='{val}': '{result_val}'"
        raise ScopeFuzzError(msg)

    if not errors_attr and val not in result_attr:
        msg = f"Attribute scope: attribute missing ${var}='{val}': '{result_attr}'"
        raise ScopeFuzzError(msg)


def _pattern_bidi_isolation(fdp: atheris.FuzzedDataProvider) -> None:
    """Bidi isolation marks wrap interpolated values but don't alter them.

    use_isolating=True wraps values in FSI/PDI but the variable
    value itself must remain unchanged.
    """
    var = _pick_var(fdp)
    val = _gen_value(fdp)
    use_isolating = fdp.ConsumeBool()

    ftl = f"msg = {{ ${var} }}\n"

    bundle = FluentBundle(
        _pick_locale(fdp), use_isolating=use_isolating
    )
    bundle.add_resource(ftl)

    result, errors = bundle.format_value("msg", {var: val})

    if errors:
        return

    if use_isolating:
        # FSI (U+2068) and PDI (U+2069) should wrap the value
        fsi = "\u2068"
        pdi = "\u2069"
        expected = f"{fsi}{val}{pdi}"
        if result != expected:
            msg = (
                f"Bidi isolation: expected FSI+'{val}'+PDI, "
                f"got '{result!r}'"
            )
            raise ScopeFuzzError(msg)
    elif result != val:
        msg = f"No-isolation: expected '{val}', got '{result}'"
        raise ScopeFuzzError(msg)


def _pattern_function_arg_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Function arguments are evaluated in the calling message's scope.

    When a function call like NUMBER($count) appears in a message,
    $count is resolved from the message's external args.
    """
    var = _pick_var(fdp)
    num_val = fdp.ConsumeIntInRange(1, 9999)

    ftl = f"msg = {{ NUMBER(${var}) }}\n"

    bundle = FluentBundle(_pick_locale(fdp), use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value("msg", {var: num_val})

    # NUMBER should format the value; the result should be non-empty
    if not errors and not result:
        msg = "Function arg scope: NUMBER() returned empty string"
        raise ScopeFuzzError(msg)

    # The numeric value should be present in some form in the result
    # (possibly with locale-specific grouping separators)
    if not errors:
        result_digits = "".join(c for c in result if c.isdigit())
        expected_digits = str(num_val)
        if result_digits != expected_digits:
            msg = (
                f"Function arg scope: NUMBER(${var}={num_val}) "
                f"produced '{result}', digits '{result_digits}' "
                f"!= expected '{expected_digits}'"
            )
            raise ScopeFuzzError(msg)


def _pattern_nested_term_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Nested term references maintain independent scopes.

    Term A calls Term B with different args; each term sees
    only its own explicitly-passed arguments.
    """
    var = _pick_var(fdp)
    val_a = _gen_value(fdp)
    val_b = _gen_value(fdp)

    ftl = (
        f'msg = {{ -outer({var}: "{val_a}") }}\n'
        f'-outer = {{ ${var} }} + {{ -inner({var}: "{val_b}") }}\n'
        f"-inner = {{ ${var} }}\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value("msg", {})

    if errors:
        return  # Acceptable: resolution errors from complex nesting

    expected = f"{val_a} + {val_b}"
    if result != expected:
        msg = f"Nested term scope: expected '{expected}', got '{result}'"
        raise ScopeFuzzError(msg)


def _pattern_scope_chain(fdp: atheris.FuzzedDataProvider) -> None:
    """Chain of message references all share the same args scope.

    msg_a -> msg_b -> msg_c: all three should see the external args.
    """
    var = _pick_var(fdp)
    val = _gen_value(fdp)
    depth = fdp.ConsumeIntInRange(2, 4)

    ids = [f"chain{i}" for i in range(depth)]
    lines = []
    for i, msg_id in enumerate(ids):
        if i < depth - 1:
            lines.append(f"{msg_id} = {{ {ids[i + 1]} }}")
        else:
            lines.append(f"{msg_id} = {{ ${var} }}")

    ftl = "\n".join(lines) + "\n"

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result, errors = bundle.format_value(ids[0], {var: val})

    if not errors and result != val:
        msg = f"Scope chain (depth={depth}): expected '{val}', got '{result}'"
        raise ScopeFuzzError(msg)


def _pattern_cross_message_isolation(fdp: atheris.FuzzedDataProvider) -> None:
    """Formatting one message does not affect another message's resolution.

    Two independent messages formatted with different args should
    produce independent results.
    """
    var = _pick_var(fdp)
    val_a = _gen_value(fdp)
    val_b = _gen_value(fdp)

    ftl = (
        "msg-alpha = { $" + var + " }\n"
        "msg-beta = { $" + var + " }\n"
    )

    bundle = FluentBundle("en-US", use_isolating=False)
    bundle.add_resource(ftl)

    result_a, errors_a = bundle.format_value("msg-alpha", {var: val_a})
    result_b, errors_b = bundle.format_value("msg-beta", {var: val_b})

    if not errors_a and result_a != val_a:
        msg = f"Cross-message: msg-alpha expected '{val_a}', got '{result_a}'"
        raise ScopeFuzzError(msg)

    if not errors_b and result_b != val_b:
        msg = f"Cross-message: msg-beta expected '{val_b}', got '{result_b}'"
        raise ScopeFuzzError(msg)

    # Critical: formatting msg-beta should not retroactively change msg-alpha
    result_a2, errors_a2 = bundle.format_value("msg-alpha", {var: val_a})
    if not errors_a2 and result_a2 != val_a:
        msg = (
            f"Cross-message pollution: msg-alpha changed after msg-beta: "
            f"'{result_a}' -> '{result_a2}'"
        )
        raise ScopeFuzzError(msg)


def _pattern_depth_guard_boundary(fdp: atheris.FuzzedDataProvider) -> None:
    """GlobalDepthGuard prevents unbounded recursion across format_pattern calls.

    Self-referencing messages and deep chains should hit the depth limit
    gracefully, producing errors rather than stack overflow.
    """
    variant = fdp.ConsumeIntInRange(0, 2)

    match variant:
        case 0:
            # Self-referencing message
            ftl = "msg = { msg }\n"
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("msg", {})
            # Must have errors (cyclic reference detected)
            if not errors:
                msg = "Depth guard: self-ref produced no errors"
                raise ScopeFuzzError(msg)

        case 1:
            # Mutual recursion: a -> b -> a
            ftl = "msg-a = { msg-b }\nmsg-b = { msg-a }\n"
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("msg-a", {})
            if not errors:
                msg = "Depth guard: mutual recursion produced no errors"
                raise ScopeFuzzError(msg)

        case _:
            # Deep chain at boundary
            depth = fdp.ConsumeIntInRange(5, 30)
            lines = []
            for i in range(depth):
                lines.append(f"d{i} = {{ d{i + 1} }}")
            lines.append(f"d{depth} = leaf")
            ftl = "\n".join(lines) + "\n"

            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("d0", {})
            # Either resolves to "leaf" or hits depth limit -- both acceptable
            if not errors and result != "leaf":
                msg = f"Depth chain: expected 'leaf' or errors, got '{result}'"
                raise ScopeFuzzError(msg)


def _pattern_adversarial_scope(fdp: atheris.FuzzedDataProvider) -> None:
    """Adversarial scope scenarios: empty vars, missing refs, scope leaks."""
    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # Term with no arguments -- $var should be missing
            ftl = "msg = { -brand }\n-brand = { $missing }\n"
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("msg", {"missing": "LEAKED"})
            # The term should NOT see the outer "missing" variable
            if "LEAKED" in result and not errors:
                msg = "Adversarial: term without args leaked outer scope"
                raise ScopeFuzzError(msg)

        case 1:
            # Multiple variables, only some provided
            var_a = _pick_var(fdp)
            var_b = _pick_var(fdp)
            val_a = _gen_value(fdp)

            ftl = f"msg = {{ ${var_a} }} {{ ${var_b} }}\n"
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("msg", {var_a: val_a})
            # Should have at least one error for missing var_b
            # (unless var_a == var_b, in which case both are provided)
            if var_a != var_b and not errors:
                msg = f"Adversarial: missing ${var_b} produced no errors"
                raise ScopeFuzzError(msg)

        case 2:
            # Empty string variable value
            var = _pick_var(fdp)
            ftl = f"msg = [{{ ${var} }}]\n"
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(ftl)
            result, errors = bundle.format_value("msg", {var: ""})
            if not errors and result != "[]":
                msg = f"Adversarial: empty string var produced '{result}'"
                raise ScopeFuzzError(msg)

        case _:
            # Fuzzed variable name as FTL input
            raw = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(1, 30))
            bundle = FluentBundle("en-US", use_isolating=False)
            with contextlib.suppress(*_ALLOWED_EXCEPTIONS):
                bundle.add_resource(f"msg = {{ ${raw} }}\n")
                bundle.format_value("msg", {raw: "test"})


# --- Pattern Dispatch ---
_PATTERN_DISPATCH: dict[str, Any] = {
    "term_arg_isolation": _pattern_term_arg_isolation,
    "variable_shadowing": _pattern_variable_shadowing,
    "message_ref_scope": _pattern_message_ref_scope,
    "select_scope": _pattern_select_scope,
    "attribute_scope": _pattern_attribute_scope,
    "bidi_isolation": _pattern_bidi_isolation,
    "function_arg_scope": _pattern_function_arg_scope,
    "nested_term_scope": _pattern_nested_term_scope,
    "scope_chain": _pattern_scope_chain,
    "cross_message_isolation": _pattern_cross_message_isolation,
    "depth_guard_boundary": _pattern_depth_guard_boundary,
    "adversarial_scope": _pattern_adversarial_scope,
}


def _track_slowest_operation(duration_ms: float, description: str) -> None:
    """Track top 10 slowest operations using min-heap."""
    if len(_state.slowest_operations) < 10:
        heapq.heappush(
            _state.slowest_operations, (duration_ms, description[:50], "")
        )
    elif duration_ms > _state.slowest_operations[0][0]:
        heapq.heapreplace(
            _state.slowest_operations, (duration_ms, description[:50], "")
        )


def _track_seed_corpus(data: bytes, duration_ms: float) -> None:
    """Track interesting inputs for seed corpus with FIFO eviction."""
    is_interesting = duration_ms > 10.0

    if is_interesting:
        input_hash = hashlib.sha256(data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = data
            _state.corpus_entries_added += 1


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test variable scoping and resolution context."""
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    fdp = atheris.FuzzedDataProvider(data)

    if fdp.remaining_bytes() < 4:
        return

    # Weighted pattern selection
    choice = fdp.ConsumeIntInRange(0, _TOTAL_WEIGHT - 1)
    pattern_name = _PATTERN_WEIGHTS[-1][0]  # Default to last
    for i, cumulative in enumerate(_CUMULATIVE_WEIGHTS):
        if choice < cumulative:
            pattern_name = _PATTERN_WEIGHTS[i][0]
            break

    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    handler = _PATTERN_DISPATCH[pattern_name]

    start = time.perf_counter()
    try:
        handler(fdp)
    except ScopeFuzzError:
        _state.findings += 1
        raise
    except _ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid inputs
    except Exception:  # pylint: disable=broad-exception-caught
        _state.findings += 1
        error_type = sys.exc_info()[0]
        if error_type is not None:
            key = error_type.__name__[:50]
            _state.error_counts[key] = _state.error_counts.get(key, 0) + 1
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    _state.performance_history.append(elapsed_ms)

    # Per-pattern wall time
    _state.pattern_wall_time[pattern_name] = (
        _state.pattern_wall_time.get(pattern_name, 0.0) + elapsed_ms
    )

    _track_slowest_operation(elapsed_ms, pattern_name)
    _track_seed_corpus(data, elapsed_ms)

    # Memory tracking (every 100 iterations)
    if _state.iterations % 100 == 0:
        current_mb = _get_process().memory_info().rss / (1024 * 1024)
        _state.memory_history.append(current_mb)

    # Checkpoint (periodic report)
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()


def main() -> None:
    """Entry point with argparse CLI."""
    parser = argparse.ArgumentParser(
        description="Variable Scope & Resolution Context Fuzzer"
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=500,
        help="Emit JSON report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size",
        type=int,
        default=100,
        help="Maximum seed corpus entries (FIFO eviction, default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print("=" * 80)
    print("Variable Scope & Resolution Context Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     runtime.resolver (via FluentBundle)")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)}")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
