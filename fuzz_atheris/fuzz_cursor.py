#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: cursor - Cursor, ParseError, and source position utilities
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Cursor and position utility fuzzer (Atheris).

Targets:
- ftllexengine.syntax.cursor.Cursor
- ftllexengine.syntax.cursor.LineOffsetCache
- ftllexengine.syntax.cursor.ParseError / ParseResult
- ftllexengine.syntax.position helpers

Concern boundary: existing parser fuzzers exercise Cursor only through parser
control flow. This fuzzer targets the cursor subsystem directly:
- constructor and EOF invariants
- peek/advance/expect semantics
- whitespace and line-navigation helpers
- parity between Cursor.compute_line_col() and cached position helpers
- ParseError rendering with contextual source excerpts
- standalone position helper behavior on raw and CRLF sources

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
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413


@dataclass
class CursorMetrics:
    """Domain-specific metrics for cursor fuzzing."""

    constructor_checks: int = 0
    navigation_checks: int = 0
    whitespace_checks: int = 0
    line_col_checks: int = 0
    parse_error_checks: int = 0
    position_helper_checks: int = 0
    parse_result_checks: int = 0


class CursorFuzzError(Exception):
    """Raised when a cursor/position invariant is violated."""


_ALLOWED_EXCEPTIONS = (
    ValueError,
    EOFError,
    UnicodeEncodeError,
)

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("constructor_guards", 12),
    ("peek_advance_expect", 14),
    ("whitespace_skips", 12),
    ("line_navigation", 10),
    ("line_col_parity", 12),
    ("parse_error_formatting", 10),
    ("position_helpers", 12),
    ("parse_result_contract", 8),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

_SOURCES: tuple[str, ...] = (
    "",
    "hello",
    "hello world",
    "  leading",
    "  \n  spaced\nvalue",
    "line1\nline2\nline3",
    "alpha\n\nbeta\n",
    "a\r\nb\r\nc",
    "tabs\tstay\tliteral",
    "unicode граница\nline2",
)

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "cursor"
_REPORT_FILENAME = "fuzz_cursor_report.json"

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=250,
    fuzzer_name="cursor",
    fuzzer_target="Cursor, LineOffsetCache, ParseError, syntax.position",
    pattern_intended_weights={name: float(weight) for name, weight in _PATTERN_WEIGHTS},
)
_domain = CursorMetrics()


def _build_stats_dict() -> dict[str, Any]:
    """Build stats dictionary including cursor metrics."""
    stats = build_base_stats_dict(_state)
    stats["constructor_checks"] = _domain.constructor_checks
    stats["navigation_checks"] = _domain.navigation_checks
    stats["whitespace_checks"] = _domain.whitespace_checks
    stats["line_col_checks"] = _domain.line_col_checks
    stats["parse_error_checks"] = _domain.parse_error_checks
    stats["position_helper_checks"] = _domain.position_helper_checks
    stats["parse_result_checks"] = _domain.parse_result_checks
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint report."""
    emit_checkpoint_report(
        _state, _build_stats_dict(), _REPORT_DIR, _REPORT_FILENAME,
    )


def _emit_report() -> None:
    """Emit crash-proof final report."""
    emit_final_report(
        _state, _build_stats_dict(), _REPORT_DIR, _REPORT_FILENAME,
    )


atexit.register(_emit_report)

logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.syntax.cursor import (
        Cursor,
        LineOffsetCache,
        ParseError,
        ParseResult,
    )
    from ftllexengine.syntax.position import (
        column_offset,
        format_position,
        get_error_context,
        get_line_content,
        line_offset,
    )


def _normalize_cursor_source(source: str) -> str:
    """Normalize CRLF/CR to LF for direct Cursor usage."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _manual_skip_spaces(source: str, pos: int) -> int:
    """Manual reference implementation for skip_spaces()."""
    while pos < len(source) and source[pos] == " ":
        pos += 1
    return pos


def _manual_skip_whitespace(source: str, pos: int) -> int:
    """Manual reference implementation for skip_whitespace()."""
    while pos < len(source) and source[pos] in (" ", "\n"):
        pos += 1
    return pos


def _pattern_constructor_guards(fdp: atheris.FuzzedDataProvider) -> None:
    """Cursor constructor enforces position invariants and EOF behavior."""
    _domain.constructor_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES)))
    mode = fdp.ConsumeIntInRange(0, 3)

    match mode:
        case 0:
            pos = -fdp.ConsumeIntInRange(1, 8)
            try:
                Cursor(source, pos)
            except ValueError:
                return
            msg = "Cursor accepted negative position"
            raise CursorFuzzError(msg)
        case 1:
            pos = len(source) + fdp.ConsumeIntInRange(1, 8)
            try:
                Cursor(source, pos)
            except ValueError:
                return
            msg = "Cursor accepted position beyond source length"
            raise CursorFuzzError(msg)
        case _:
            pos = fdp.ConsumeIntInRange(0, len(source))
            cursor = Cursor(source, pos)
            if cursor.is_eof != (pos >= len(source)):
                msg = f"Cursor.is_eof mismatch for pos={pos}, len={len(source)}"
                raise CursorFuzzError(msg)
            if cursor.is_eof:
                try:
                    _ = cursor.current
                except EOFError:
                    return
                msg = "EOF cursor.current did not raise EOFError"
                raise CursorFuzzError(msg)


def _pattern_peek_advance_expect(fdp: atheris.FuzzedDataProvider) -> None:
    """peek(), advance(), slice helpers, and expect() match manual semantics."""
    _domain.navigation_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES)))
    pos = fdp.ConsumeIntInRange(0, len(source))
    cursor = Cursor(source, pos)

    offset = fdp.ConsumeIntInRange(-4, 4)
    expected_peek = None
    target = pos + offset
    if 0 <= target < len(source):
        expected_peek = source[target]
    if cursor.peek(offset) != expected_peek:
        msg = f"peek({offset}) mismatch: {cursor.peek(offset)!r} != {expected_peek!r}"
        raise CursorFuzzError(msg)

    count = fdp.ConsumeIntInRange(1, 6)
    advanced = cursor.advance(count)
    if advanced.pos != min(pos + count, len(source)):
        msg = (
            f"advance({count}) produced pos={advanced.pos}, "
            f"expected {min(pos + count, len(source))}"
        )
        raise CursorFuzzError(msg)

    ahead = cursor.slice_ahead(count)
    if ahead != source[pos : pos + count]:
        msg = f"slice_ahead({count}) mismatch: {ahead!r}"
        raise CursorFuzzError(msg)

    sliced = cursor.slice_to(min(len(source), pos + count))
    if sliced != source[pos : min(len(source), pos + count)]:
        msg = "slice_to() mismatch against source slice"
        raise CursorFuzzError(msg)

    expected_char = cursor.peek(0)
    if expected_char is not None:
        next_cursor = cursor.expect(expected_char)
        if next_cursor is None or next_cursor.pos != min(pos + 1, len(source)):
            msg = "expect(current_char) failed to advance cursor"
            raise CursorFuzzError(msg)
    if cursor.expect("\u2603") is not None:
        msg = "expect(non-matching-char) unexpectedly advanced cursor"
        raise CursorFuzzError(msg)


def _pattern_whitespace_skips(fdp: atheris.FuzzedDataProvider) -> None:
    """skip_spaces() and skip_whitespace() match manual scans exactly."""
    _domain.whitespace_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES)))
    pos = fdp.ConsumeIntInRange(0, len(source))
    cursor = Cursor(source, pos)

    spaces = cursor.skip_spaces()
    expected_spaces = _manual_skip_spaces(source, pos)
    if spaces.pos != expected_spaces:
        msg = f"skip_spaces() mismatch: {spaces.pos} != {expected_spaces}"
        raise CursorFuzzError(msg)

    whitespace = cursor.skip_whitespace()
    expected_whitespace = _manual_skip_whitespace(source, pos)
    if whitespace.pos != expected_whitespace:
        msg = f"skip_whitespace() mismatch: {whitespace.pos} != {expected_whitespace}"
        raise CursorFuzzError(msg)


def _pattern_line_navigation(fdp: atheris.FuzzedDataProvider) -> None:
    """skip_to_line_end() and skip_line_end() obey LF navigation semantics."""
    _domain.navigation_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES)))
    pos = fdp.ConsumeIntInRange(0, len(source))
    cursor = Cursor(source, pos)

    line_end = cursor.skip_to_line_end()
    expected = source.find("\n", pos)
    expected_pos = len(source) if expected == -1 else expected
    if line_end.pos != expected_pos:
        msg = f"skip_to_line_end() mismatch: {line_end.pos} != {expected_pos}"
        raise CursorFuzzError(msg)

    consumed = line_end.skip_line_end()
    if line_end.pos < len(source) and source[line_end.pos] == "\n":
        if consumed.pos != min(line_end.pos + 1, len(source)):
            msg = "skip_line_end() failed to consume LF"
            raise CursorFuzzError(msg)
    elif consumed.pos != line_end.pos:
        msg = "skip_line_end() changed position when not at LF"
        raise CursorFuzzError(msg)

    if cursor.count_newlines_before() != source.count("\n", 0, pos):
        msg = "count_newlines_before() mismatch"
        raise CursorFuzzError(msg)


def _pattern_line_col_parity(fdp: atheris.FuzzedDataProvider) -> None:
    """Cursor, LineOffsetCache, and format_position agree on line/column."""
    _domain.line_col_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES)))
    pos = fdp.ConsumeIntInRange(0, len(source))
    cursor = Cursor(source, pos)
    cache = LineOffsetCache(source)

    cursor_line, cursor_col = cursor.compute_line_col()
    cache_line, cache_col = cache.get_line_col(pos)
    if (cursor_line, cursor_col) != (cache_line, cache_col):
        msg = (
            f"compute_line_col/cache mismatch: {(cursor_line, cursor_col)!r} "
            f"!= {(cache_line, cache_col)!r}"
        )
        raise CursorFuzzError(msg)

    if format_position(source, pos, zero_based=False) != f"{cursor_line}:{cursor_col}":
        msg = "format_position(zero_based=False) disagrees with Cursor.compute_line_col()"
        raise CursorFuzzError(msg)


def _pattern_parse_error_formatting(fdp: atheris.FuzzedDataProvider) -> None:
    """ParseError formatting includes location data and contextual caret output."""
    _domain.parse_error_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES))) or "fallback"
    pos = fdp.ConsumeIntInRange(0, len(source))
    cursor = Cursor(source, pos)
    error = ParseError(
        "Expected closing brace",
        cursor,
        expected=("}", "]") if fdp.ConsumeBool() else (),
    )

    line, col = cursor.compute_line_col()
    formatted = error.format_error()
    if not formatted.startswith(f"{line}:{col}:"):
        msg = f"format_error() missing line/col prefix: {formatted!r}"
        raise CursorFuzzError(msg)

    contextual = error.format_with_context(context_lines=fdp.ConsumeIntInRange(0, 2))
    if "^" not in contextual:
        msg = f"format_with_context() missing caret marker: {contextual!r}"
        raise CursorFuzzError(msg)
    if "Expected closing brace" not in contextual:
        msg = "format_with_context() missing original message"
        raise CursorFuzzError(msg)


def _pattern_position_helpers(fdp: atheris.FuzzedDataProvider) -> None:
    """Standalone position helpers stay self-consistent on raw sources."""
    _domain.position_helper_checks += 1
    source = fdp.PickValueInList(list(_SOURCES)) or "line"
    pos = fdp.ConsumeIntInRange(0, len(source))

    line = line_offset(source, pos)
    col = column_offset(source, pos)
    if format_position(source, pos, zero_based=True) != f"{line}:{col}":
        msg = "format_position(zero_based=True) disagrees with line_offset/column_offset"
        raise CursorFuzzError(msg)

    context = get_error_context(source, pos, context_lines=fdp.ConsumeIntInRange(0, 2))
    if "^" not in context:
        msg = f"get_error_context() missing caret marker: {context!r}"
        raise CursorFuzzError(msg)

    line_content = get_line_content(source, line, zero_based=True)
    if line_content not in context and source:
        msg = "get_line_content() returned line not present in error context"
        raise CursorFuzzError(msg)


def _pattern_parse_result_contract(fdp: atheris.FuzzedDataProvider) -> None:
    """ParseResult stores value and advanced cursor without mutation."""
    _domain.parse_result_checks += 1
    source = _normalize_cursor_source(fdp.PickValueInList(list(_SOURCES))) or "x"
    pos = fdp.ConsumeIntInRange(0, len(source) - 1)
    cursor = Cursor(source, pos)
    value = cursor.current
    result = ParseResult(value=value, cursor=cursor.advance())

    if result.value != value:
        msg = "ParseResult.value mismatch"
        raise CursorFuzzError(msg)
    if result.cursor.pos != min(pos + 1, len(source)):
        msg = "ParseResult.cursor did not store advanced cursor"
        raise CursorFuzzError(msg)


_PATTERN_DISPATCH: dict[str, Any] = {
    "constructor_guards": _pattern_constructor_guards,
    "peek_advance_expect": _pattern_peek_advance_expect,
    "whitespace_skips": _pattern_whitespace_skips,
    "line_navigation": _pattern_line_navigation,
    "line_col_parity": _pattern_line_col_parity,
    "parse_error_formatting": _pattern_parse_error_formatting,
    "position_helpers": _pattern_position_helpers,
    "parse_result_contract": _pattern_parse_result_contract,
}


def test_one_input(data: bytes) -> None:
    """Atheris entry point for cursor and position invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        _PATTERN_DISPATCH[pattern](fdp)

    except CursorFuzzError:
        _state.findings += 1
        raise

    except _ALLOWED_EXCEPTIONS as exc:
        error_key = f"{type(exc).__name__}_{str(exc)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    except Exception as exc:  # pylint: disable=broad-exception-caught
        error_key = f"{type(exc).__name__}_{str(exc)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = (
            "line" in pattern
            or "position" in pattern
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
    """Run the cursor fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Cursor and position utility fuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=250,
        help="Maximum size of in-memory seed corpus (default: 250)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Cursor Fuzzer (Atheris)",
        target="Cursor, LineOffsetCache, ParseError, syntax.position",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=(
            "Focus:      direct cursor state-machine and source-position helpers",
        ),
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
