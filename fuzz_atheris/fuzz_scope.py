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
import gc
import logging
import pathlib
import sys
import time
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
class ScopeMetrics:
    """Domain-specific metrics for scope fuzzer."""

    term_isolation_tests: int = 0
    shadowing_tests: int = 0
    message_ref_tests: int = 0
    depth_guard_tests: int = 0
    adversarial_tests: int = 0
    bidi_isolation_tests: int = 0


# --- Global State ---

_state = BaseFuzzerState(
    seed_corpus_max_size=500,
    fuzzer_name="scope",
    fuzzer_target="runtime.resolver (via FluentBundle)",
)
_domain = ScopeMetrics()


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

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}

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
    _domain.term_isolation_tests += 1
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
    _domain.shadowing_tests += 1
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
    _domain.message_ref_tests += 1
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
    _domain.bidi_isolation_tests += 1
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
    _domain.depth_guard_tests += 1
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
    _domain.adversarial_tests += 1
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


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "scope"
_REPORT_FILENAME = "fuzz_scope_report.json"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Domain-specific metrics
    stats["term_isolation_tests"] = _domain.term_isolation_tests
    stats["shadowing_tests"] = _domain.shadowing_tests
    stats["message_ref_tests"] = _domain.message_ref_tests
    stats["depth_guard_tests"] = _domain.depth_guard_tests
    stats["adversarial_tests"] = _domain.adversarial_tests
    stats["bidi_isolation_tests"] = _domain.bidi_isolation_tests

    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test variable scoping and resolution context."""
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

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    if fdp.remaining_bytes() < 4:
        return

    handler = _PATTERN_DISPATCH[pattern_name]

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

    finally:
        is_interesting = (time.perf_counter() - start_time) * 1000 > 10.0
        record_iteration_metrics(
            _state, pattern_name, start_time, data, is_interesting=is_interesting,
        )

        # Break reference cycles in AST/error objects to prevent RSS growth
        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            record_memory(_state)


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
        default=500,
        help="Maximum seed corpus entries (FIFO eviction, default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    # Inject -rss_limit_mb default if not already specified.
    # Scope patterns are lightweight but deep chains can accumulate; 4096 MB
    # provides headroom while still catching true leaks before system OOM-kill.
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Variable Scope & Resolution Context Fuzzer (Atheris)",
        target="runtime.resolver (via FluentBundle)",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        mutator="Byte mutation (scoping invariant patterns)",
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
