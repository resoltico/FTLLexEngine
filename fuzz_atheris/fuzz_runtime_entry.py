# mypy: disable-error-code=name-defined
from fuzz_runtime_builders import (
    _add_random_resources,
    _build_ftl_resource,
    _fuzzed_function,
    _generate_complex_args,
    _verify_ast_lookup_accessors,
)
from fuzz_runtime_scenarios import (
    _execute_runtime_invariants,
    _perform_security_fuzzing,
)
from fuzz_runtime_support import (
    _SCENARIO_SCHEDULE,
    GC_INTERVAL,
    TARGET_MESSAGE_IDS,
    TEST_LOCALES,
    CacheConfig,
    CacheCorruptionError,
    ComplexArgs,
    FluentBundle,
    FrozenFluentError,
    RuntimeIntegrityError,
    _domain,
    _emit_checkpoint,
    _state,
    argparse,
    atheris,
    contextlib,
    gc,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
    sys,
    threading,
    time,
)


def _perform_differential_testing(
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
) -> None:
    """Differential testing: same FTL, different configs must not crash differently."""
    _domain.differential_tests += 1

    alt_locale = fdp.PickValueInList(["en-US", "de-DE", "ar-EG", "ja-JP", "C", ""])
    alt_strict = not bundle.strict if fdp.ConsumeBool() else bundle.strict
    alt_cache = not bundle.cache_enabled if fdp.ConsumeBool() else bundle.cache_enabled

    try:
        alt_bundle = FluentBundle(
            alt_locale,
            strict=alt_strict,
            cache=CacheConfig() if alt_cache else None,
        )

        # Copy functions
        for name in bundle._function_registry:
            func = bundle._function_registry.get_callable(name)
            if func:
                alt_bundle.add_function(name, func)

        # Same FTL resource
        ftl = _build_ftl_resource(fdp)
        with contextlib.suppress(Exception):
            alt_bundle.add_resource(ftl)

        # Format all reachable messages
        for msg_id in TARGET_MESSAGE_IDS[:8]:
            with contextlib.suppress(Exception):
                alt_bundle.format_pattern(msg_id, args)

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _run_concurrent_test(
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
    strict: bool,
    enable_cache: bool,
    cache_write_once: bool,
) -> None:
    """Run concurrent execution test."""
    _domain.concurrent_tests += 1

    barrier = threading.Barrier(2)

    def worker() -> None:
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=1.0)
        try:
            _execute_runtime_invariants(fdp, bundle, args, strict, enable_cache, cache_write_once)
        except CacheCorruptionError:
            # Expected from corruption simulation in strict mode
            pass
        except (RecursionError, MemoryError, FrozenFluentError):
            # FrozenFluentError: depth guard (MAX_DEPTH_EXCEEDED)
            pass

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)
        if t.is_alive():
            msg = "RWLock deadlock detected."
            raise RuntimeIntegrityError(msg)


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915 - dispatch
    """Atheris entry point: Test runtime invariants and contracts."""
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

    scenario = select_pattern_round_robin(_state, _SCENARIO_SCHEDULE)
    _state.pattern_coverage[scenario] = _state.pattern_coverage.get(scenario, 0) + 1

    if fdp.remaining_bytes() < 2:
        return

    # Security fuzzing (separate path)
    if scenario == "security":
        security_scenario = _perform_security_fuzzing(fdp)
        _state.pattern_coverage[security_scenario] = (
            _state.pattern_coverage.get(security_scenario, 0) + 1
        )
        record_iteration_metrics(_state, scenario, start_time, data, is_interesting=True)
        return

    # Configuration
    strict = scenario == "strict_mode" or fdp.ConsumeBool()
    enable_cache = scenario == "caching" or fdp.ConsumeBool()
    use_isolating = fdp.ConsumeBool()
    cache_write_once = fdp.ConsumeBool()

    # Locale selection
    locale = fdp.PickValueInList(list(TEST_LOCALES))

    try:
        try:
            cache_cfg = CacheConfig(write_once=cache_write_once) if enable_cache else None
            bundle = FluentBundle(
                locale,
                strict=strict,
                cache=cache_cfg,
                use_isolating=use_isolating,
            )
            if fdp.ConsumeBool():
                bundle.add_function("FUZZ_FUNC", _fuzzed_function)
        except (ValueError, TypeError):
            return

        # Add resources
        _add_random_resources(fdp, bundle)
        _verify_ast_lookup_accessors(bundle)

        # Generate args
        args = _generate_complex_args(fdp)

        if strict:
            _domain.strict_mode_tests += 1

        # Execute based on scenario
        if scenario == "concurrent":
            _run_concurrent_test(fdp, bundle, args, strict, enable_cache, cache_write_once)
        elif scenario == "differential":
            _perform_differential_testing(fdp, bundle, args)
        else:
            _execute_runtime_invariants(fdp, bundle, args, strict, enable_cache, cache_write_once)

    except CacheCorruptionError:
        if strict:
            return  # Expected
        _state.findings += 1
        raise

    except RuntimeIntegrityError:
        _state.findings += 1
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        is_interesting = "security" in scenario or "integrity" in scenario or (
            (time.perf_counter() - start_time) * 1000 > 50.0
        )
        record_iteration_metrics(
            _state, scenario, start_time, data, is_interesting=is_interesting,
        )

        # Break reference cycles in AST/error objects to prevent RSS growth
        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the runtime fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Runtime end-to-end fuzzer using Atheris/libFuzzer",
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
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=2000,
        help="Python recursion limit (default: 2000)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.setrecursionlimit(args.recursion_limit)

    # Inject -rss_limit_mb default if not already specified.
    # AST reference cycles can accumulate between gc passes; 4096 MB provides
    # headroom while still catching true leaks before system OOM-kill.
    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="Runtime End-to-End Fuzzer (Atheris)",
        target="FluentBundle, IntegrityCache, Resolver, Strict Mode",
        state=_state,
        schedule_len=len(_SCENARIO_SCHEDULE),
        extra_lines=[f"Recursion:  {args.recursion_limit} limit"],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
