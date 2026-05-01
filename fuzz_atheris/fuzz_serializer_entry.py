from __future__ import annotations

import argparse
import gc
import sys
import time
from typing import Any

import atheris
from fuzz_common import (
    GC_INTERVAL,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)
from fuzz_serializer_mutators import _custom_mutator
from fuzz_serializer_patterns_text import (
    _pattern_attribute_edge_cases,
    _pattern_leading_whitespace,
    _pattern_mixed_elements,
    _pattern_multiline_value,
    _pattern_select_expression,
    _pattern_simple_message,
    _pattern_string_literal_placeable,
    _pattern_syntax_chars_value,
    _pattern_term_edge_cases,
    _pattern_trailing_whitespace,
)
from fuzz_serializer_patterns_transform import (
    _pattern_transformer_roundtrip,
    _pattern_transformer_validation,
    _pattern_visitor_dispatch,
)
from fuzz_serializer_support import (
    _PATTERN_SCHEDULE,
    ALLOWED_EXCEPTIONS,
    SerializerFuzzError,
    _emit_report,
    _state,
)

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
    "visitor_dispatch": _pattern_visitor_dispatch,
    "transformer_roundtrip": _pattern_transformer_roundtrip,
    "transformer_validation": _pattern_transformer_validation,
}

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
            "attribute_edge_cases", "visitor_dispatch",
            "transformer_roundtrip", "transformer_validation",
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

    run_fuzzer(
        _state,
        test_one_input=test_one_input,
        custom_mutator=_custom_mutator,
    )
