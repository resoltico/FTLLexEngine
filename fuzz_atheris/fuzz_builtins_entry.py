from __future__ import annotations

import argparse
import gc
import sys
import time
from typing import Any

import atheris
from fuzz_builtins_patterns_currency import (
    _pattern_cross_locale_consistency,
    _pattern_currency_codes,
    _pattern_currency_cross_locale,
    _pattern_currency_precision,
    _pattern_custom_pattern,
    _pattern_error_paths,
)
from fuzz_builtins_patterns_datetime import (
    _pattern_datetime_edges,
    _pattern_datetime_styles,
    _pattern_datetime_timezone_stress,
)
from fuzz_builtins_patterns_number import (
    _pattern_number_basic,
    _pattern_number_edges,
    _pattern_number_precision,
    _pattern_number_type_variety,
)
from fuzz_builtins_support import (
    _PATTERN_SCHEDULE,
    ALLOWED_EXCEPTIONS,
    BuiltinsFuzzError,
    _emit_checkpoint,
    _state,
)
from fuzz_common import (
    GC_INTERVAL,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

from ftllexengine.diagnostics import FrozenFluentError

_PATTERN_DISPATCH: dict[str, Any] = {
    "number_basic": _pattern_number_basic,
    "number_precision": _pattern_number_precision,
    "number_edges": _pattern_number_edges,
    "number_type_variety": _pattern_number_type_variety,
    "datetime_styles": _pattern_datetime_styles,
    "datetime_edges": _pattern_datetime_edges,
    "datetime_timezone_stress": _pattern_datetime_timezone_stress,
    "currency_codes": _pattern_currency_codes,
    "currency_precision": _pattern_currency_precision,
    "currency_cross_locale": _pattern_currency_cross_locale,
    "custom_pattern": _pattern_custom_pattern,
    "cross_locale_consistency": _pattern_cross_locale_consistency,
    "error_paths": _pattern_error_paths,
}

def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test built-in formatting functions."""
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

    if fdp.remaining_bytes() < 4:
        return

    pattern_func = _PATTERN_DISPATCH[pattern]

    try:
        pattern_func(fdp)

    except BuiltinsFuzzError:
        _state.findings += 1
        raise

    except (*ALLOWED_EXCEPTIONS, FrozenFluentError):
        pass  # Expected for invalid inputs / Babel limitations

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        # Semantic interestingness: multi-locale, edge values, fuzzed patterns,
        # or wall-time > 1ms (12x P99) indicating unusual code path
        is_interesting = pattern in (
            "cross_locale_consistency", "currency_cross_locale",
            "number_edges", "number_type_variety", "custom_pattern",
        ) or (time.perf_counter() - start_time) * 1000 > 1.0
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)

def main() -> None:
    """Run the builtins fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Built-in function boundary fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Built-in Function Boundary Fuzzer (Atheris)",
        target="NUMBER, DATETIME, CURRENCY (Babel boundary)",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(_state, test_one_input=test_one_input)
