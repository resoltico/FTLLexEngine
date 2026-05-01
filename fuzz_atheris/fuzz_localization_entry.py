# mypy: disable-error-code=name-defined
from fuzz_localization_patterns_basic import (
    _pattern_add_resource_mutation,
    _pattern_ast_lookup_api,
    _pattern_chain_of_3_fallback,
    _pattern_format_value_missing,
    _pattern_format_with_variables,
    _pattern_get_message_ids_api,
    _pattern_has_message_api,
    _pattern_multi_locale_fallback,
    _pattern_single_locale_add_resource,
    _pattern_validate_resource_api,
)
from fuzz_localization_patterns_boot import _pattern_boot_config_api
from fuzz_localization_patterns_introspection import (
    _pattern_add_function_custom,
    _pattern_cache_audit_api,
    _pattern_introspect_api,
    _pattern_locale_boundary_api,
    _pattern_on_fallback_callback,
)
from fuzz_localization_patterns_loader import (
    _pattern_loader_init_success,
    _pattern_loader_junk_summary,
    _pattern_loader_not_found_fallback,
    _pattern_loader_path_error,
    _pattern_require_clean_api,
)
from fuzz_localization_patterns_validation import (
    _pattern_validate_message_schemas_api,
    _pattern_validate_message_variables_api,
)
from fuzz_localization_support import (
    _ALLOWED_EXCEPTIONS,
    _PATTERN_SCHEDULE,
    _PATTERN_WEIGHTS,
    GC_INTERVAL,
    DataIntegrityError,
    FormattingIntegrityError,
    FrozenFluentError,
    SyntaxIntegrityError,
    _emit_checkpoint,
    _state,
    argparse,
    atheris,
    gc,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
    sys,
    time,
)

# --- Pattern dispatch ---

_PATTERN_DISPATCH = {
    "single_locale_add_resource": _pattern_single_locale_add_resource,
    "multi_locale_fallback": _pattern_multi_locale_fallback,
    "chain_of_3_fallback": _pattern_chain_of_3_fallback,
    "format_value_missing": _pattern_format_value_missing,
    "format_with_variables": _pattern_format_with_variables,
    "add_resource_mutation": _pattern_add_resource_mutation,
    "has_message_api": _pattern_has_message_api,
    "ast_lookup_api": _pattern_ast_lookup_api,
    "get_message_ids_api": _pattern_get_message_ids_api,
    "validate_resource_api": _pattern_validate_resource_api,
    "validate_message_variables_api": _pattern_validate_message_variables_api,
    "validate_message_schemas_api": _pattern_validate_message_schemas_api,
    "add_function_custom": _pattern_add_function_custom,
    "introspect_api": _pattern_introspect_api,
    "cache_audit_api": _pattern_cache_audit_api,
    "locale_boundary_api": _pattern_locale_boundary_api,
    "on_fallback_callback": _pattern_on_fallback_callback,
    "loader_init_success": _pattern_loader_init_success,
    "loader_not_found_fallback": _pattern_loader_not_found_fallback,
    "loader_junk_summary": _pattern_loader_junk_summary,
    "loader_path_error": _pattern_loader_path_error,
    "require_clean_api": _pattern_require_clean_api,
    "boot_config_api": _pattern_boot_config_api,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test FluentLocalization invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = _state.pattern_coverage.get(pattern_name, 0) + 1

    try:
        _PATTERN_DISPATCH[pattern_name](fdp)

    except (
        *_ALLOWED_EXCEPTIONS,
        FrozenFluentError,
        DataIntegrityError,
        FormattingIntegrityError,
        SyntaxIntegrityError,
    ) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = _state.error_counts.get(error_type, 0) + 1
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "fallback" in pattern_name
            or "loader" in pattern_name
            or pattern_name
            in (
                "add_resource_mutation",
                "introspect_api",
                "ast_lookup_api",
                "cache_audit_api",
                "locale_boundary_api",
                "validate_message_variables_api",
                "validate_message_schemas_api",
                "require_clean_api",
                "boot_config_api",
            )
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state,
            pattern_name,
            start_time,
            data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the localization fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="FluentLocalization multi-locale orchestration fuzzer",
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
        help="Maximum in-memory seed corpus size (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="FluentLocalization Multi-locale Orchestration Fuzzer (Atheris)",
        target="ftllexengine.localization.orchestrator.FluentLocalization",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
