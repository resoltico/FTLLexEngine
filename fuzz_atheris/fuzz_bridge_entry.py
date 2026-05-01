from __future__ import annotations

import argparse
import gc
import sys
import time
from typing import Any

import atheris
from fuzz_bridge_patterns_dispatch import (
    _pattern_call_dispatch,
    _pattern_dict_interface,
    _pattern_error_wrapping,
    _pattern_evil_objects,
    _pattern_fluent_function_decorator,
    _pattern_freeze_copy_lifecycle,
    _pattern_locale_injection,
    _pattern_metadata_api,
)
from fuzz_bridge_patterns_numbers import (
    _pattern_camel_case_conversion,
    _pattern_fluent_number_contracts,
    _pattern_make_fluent_number_api,
    _pattern_signature_immutability,
)
from fuzz_bridge_patterns_registration import (
    _pattern_param_mapping_custom,
    _pattern_register_basic,
    _pattern_register_signatures,
    _pattern_signature_validation,
)
from fuzz_bridge_support import (
    _ALLOWED_EXCEPTIONS,
    _PATTERN_SCHEDULE,
    BridgeFuzzError,
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
    "register_basic": _pattern_register_basic,
    "register_signatures": _pattern_register_signatures,
    "param_mapping_custom": _pattern_param_mapping_custom,
    "signature_validation": _pattern_signature_validation,
    "fluent_number_contracts": _pattern_fluent_number_contracts,
    "make_fluent_number_api": _pattern_make_fluent_number_api,
    "signature_immutability": _pattern_signature_immutability,
    "camel_case_conversion": _pattern_camel_case_conversion,
    "call_dispatch": _pattern_call_dispatch,
    "locale_injection": _pattern_locale_injection,
    "error_wrapping": _pattern_error_wrapping,
    "evil_objects": _pattern_evil_objects,
    "dict_interface": _pattern_dict_interface,
    "freeze_copy_lifecycle": _pattern_freeze_copy_lifecycle,
    "fluent_function_decorator": _pattern_fluent_function_decorator,
    "metadata_api": _pattern_metadata_api,
}

def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz FunctionRegistry bridge machinery."""
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

    except BridgeFuzzError:
        _state.findings += 1
        raise

    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError):
        pass  # Expected for invalid inputs

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        # Semantic interestingness: patterns exercising complex paths,
        # error paths, or wall-time > 1ms indicating unusual code path
        is_interesting = (
            pattern
            in (
                "evil_objects",
                "signature_validation",
                "locale_injection",
                "metadata_api",
                "error_wrapping",
                "make_fluent_number_api",
                "dict_interface",
                "signature_immutability",
                "register_signatures",
            )
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state,
            pattern,
            start_time,
            data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)

def main() -> None:
    """Run the bridge machinery fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="FunctionRegistry bridge machinery fuzzer using Atheris/libFuzzer",
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
        default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    # Inject RSS limit if not specified
    if not any(arg.startswith("-rss_limit_mb") for arg in sys.argv):
        sys.argv.append("-rss_limit_mb=4096")

    print_fuzzer_banner(
        title="FunctionRegistry Bridge Machinery Fuzzer (Atheris)",
        target="FunctionRegistry, FunctionSignature, FluentNumber, make_fluent_number",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
    )

    run_fuzzer(_state, test_one_input=test_one_input)
