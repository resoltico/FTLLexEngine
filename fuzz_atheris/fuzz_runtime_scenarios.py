# mypy: disable-error-code=name-defined
from fuzz_runtime_support import (
    _NON_STRING_LOCALES,
    _SECURITY_SCHEDULE,
    _STRUCTURALLY_INVALID_LOCALES,
    MAX_LOCALE_LENGTH_HARD_LIMIT,
    TARGET_MESSAGE_IDS,
    Any,
    CacheConfig,
    CacheCorruptionError,
    ComplexArgs,
    FluentBundle,
    FormattingIntegrityError,
    FrozenFluentError,
    IntegrityCacheEntry,
    RuntimeIntegrityError,
    WriteConflictError,
    _domain,
    atheris,
    contextlib,
    require_locale_code,
)


def _test_dict_functions(_fdp: atheris.FuzzedDataProvider) -> None:
    """Test FluentBundle rejects dict as functions parameter."""
    try:
        invalid_functions: Any = {"NUMBER": lambda *_args, **_kwargs: "x"}
        FluentBundle("en", functions=invalid_functions)
        msg = "FluentBundle accepted dict as functions parameter"
        raise RuntimeIntegrityError(msg)
    except TypeError:
        pass
    except RuntimeIntegrityError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _execute_runtime_invariants(  # noqa: PLR0912, PLR0915 - dispatch
    fdp: atheris.FuzzedDataProvider,
    bundle: FluentBundle,
    args: ComplexArgs,
    strict: bool,
    enable_cache: bool,
    cache_write_once: bool,
) -> None:
    """Verify core runtime invariants across operations."""
    target_ids = list(TARGET_MESSAGE_IDS)
    fdp_sample = fdp.ConsumeIntInRange(3, len(target_ids))
    sampled_ids = target_ids[:fdp_sample]

    for msg_id in sampled_ids:
        attribute = fdp.PickValueInList([None, "title", "nonexistent"])
        try:
            # Primary formatting
            res1, err1 = bundle.format_pattern(msg_id, args, attribute=attribute)

            # INVARIANT: Strict Mode Integrity
            if strict and len(err1) > 0:
                _domain.strict_mode_tests += 1
                msg = f"Strict mode breach: {len(err1)} errors for '{msg_id}'."
                raise RuntimeIntegrityError(msg)

            # INVARIANT: Frozen Error Integrity
            for e in err1:
                _domain.frozen_error_verifications += 1
                if not e.verify_integrity():
                    msg = "FrozenFluentError checksum verification failed."
                    raise RuntimeIntegrityError(msg)

            # INVARIANT: Cache Stability
            if enable_cache and bundle._cache is not None:
                _domain.cache_operations += 1
                res2, err2 = bundle.format_pattern(msg_id, args, attribute=attribute)
                _domain.cache_stability_checks += 1

                if res1 != res2 or len(err1) != len(err2):
                    msg = f"Cache stability breach: non-deterministic result for '{msg_id}'."
                    raise RuntimeIntegrityError(msg)

                # Corruption simulation (5% chance)
                if fdp.ConsumeProbability() < 0.05:
                    _domain.corruption_simulations += 1
                    _simulate_corruption(bundle)
                    try:
                        bundle.format_pattern(msg_id, args, attribute=attribute)
                    except CacheCorruptionError as exc:
                        if not strict:
                            msg = "Non-strict cache raised CacheCorruptionError."
                            raise RuntimeIntegrityError(msg) from exc
                    except Exception as e:  # pylint: disable=broad-exception-caught
                        is_corruption = "corruption" in str(e).lower()
                        if is_corruption and not isinstance(e, CacheCorruptionError):
                            msg = f"Wrong exception type for corruption: {type(e)}"
                            raise RuntimeIntegrityError(msg) from e

        except FormattingIntegrityError as e:
            _domain.integrity_checks += 1
            if not strict:
                msg = "Non-strict bundle raised FormattingIntegrityError."
                raise RuntimeIntegrityError(msg) from e
            if not e.fluent_errors:
                msg = "FormattingIntegrityError empty."
                raise RuntimeIntegrityError(msg) from e

        except WriteConflictError as e:
            if not cache_write_once:
                msg = "WriteConflictError raised when write_once=False."
                raise RuntimeIntegrityError(msg) from e

        except (RecursionError, MemoryError, FrozenFluentError):
            # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED as a safety
            # mechanism regardless of strict mode to prevent stack overflow
            pass


def _simulate_corruption(bundle: FluentBundle) -> None:
    """Simulate cache corruption for integrity testing."""
    if bundle._cache is None:
        return
    with bundle._cache._lock:
        if not bundle._cache._cache:
            return
        key = next(iter(bundle._cache._cache))
        entry = bundle._cache._cache[key]

        corrupted = IntegrityCacheEntry(
            formatted=entry.formatted + "CORRUPTION",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
            key_hash=entry.key_hash,
        )
        bundle._cache._cache[key] = corrupted


def _perform_security_fuzzing(fdp: atheris.FuzzedDataProvider) -> str:
    """Perform security fuzzing with attack vectors."""
    _domain.security_tests += 1

    attack_idx = fdp.ConsumeIntInRange(0, len(_SECURITY_SCHEDULE) - 1)
    attack = str(_SECURITY_SCHEDULE[attack_idx])

    match attack:
        case "security_recursion":
            _test_deep_recursion(fdp)
        case "security_memory":
            _test_memory_exhaustion(fdp)
        case "security_cache_poison":
            _test_cache_poisoning(fdp)
        case "security_function_inject":
            _test_function_injection(fdp)
        case "security_locale_boundary":
            _test_locale_boundary(fdp)
        case "security_expansion_budget":
            _test_expansion_budget(fdp)
        case "security_dag_expansion":
            _test_dag_expansion(fdp)
        case "security_dict_functions":
            _test_dict_functions(fdp)

    return attack


def _test_deep_recursion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test deep recursion via nested placeables and cyclic references."""
    attack_type = fdp.ConsumeIntInRange(0, 2)
    try:
        bundle = FluentBundle("en", strict=False)
        match attack_type:
            case 0:
                # Deep nested placeables
                depth = fdp.ConsumeIntInRange(50, 200)
                ftl = "msg = " + "{ " * depth + "$var" + " }" * depth + "\n"
                bundle.add_resource(ftl)
            case 1:
                # Cyclic reference chain
                chain_len = fdp.ConsumeIntInRange(2, 20)
                parts = []
                for i in range(chain_len):
                    next_id = f"c{(i + 1) % chain_len}"
                    parts.append(f"c{i} = {{ {next_id} }}\n")
                bundle.add_resource("\n".join(parts))
            case _:
                # Self-referencing term with select
                ftl = "-self = { -self ->\n    *[other] { -self }\n}\nmsg = { -self }\n"
                bundle.add_resource(ftl)
        bundle.format_pattern("msg" if attack_type == 0 else "c0", {"var": "test"})
    except (RecursionError, MemoryError, ValueError, FrozenFluentError):
        # FrozenFluentError: depth guard fires MAX_DEPTH_EXCEEDED regardless of strict mode
        pass


def _test_memory_exhaustion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test memory exhaustion via large values and many variants."""
    attack_type = fdp.ConsumeIntInRange(0, 2)
    try:
        bundle = FluentBundle("en", strict=False)
        match attack_type:
            case 0:
                # Large string value
                size = fdp.ConsumeIntInRange(10000, 100000)
                bundle.add_resource(f"msg = {'x' * size}\n")
            case 1:
                # Many variants in select
                n = fdp.ConsumeIntInRange(50, 200)
                variants = "\n".join(f"    [{'*' if i == 0 else ''}v{i}] val{i}" for i in range(n))
                bundle.add_resource(f"msg = {{ $var ->\n{variants}\n}}\n")
            case _:
                # Many attributes
                n = fdp.ConsumeIntInRange(50, 200)
                attrs = "\n".join(f"    .a{i} = val{i}" for i in range(n))
                bundle.add_resource(f"msg = val\n{attrs}\n")
        bundle.format_pattern("msg", {"var": "test"})
    except (MemoryError, ValueError, FrozenFluentError):
        pass


def _test_cache_poisoning(fdp: atheris.FuzzedDataProvider) -> None:
    """Test cache poisoning attack."""
    try:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = Hello { $name }\n")

        malicious_args = [
            {"name": float("inf")},
            {"name": float("-inf")},
            {"name": float("nan")},
            {"name": None},
            {"name": []},
        ]

        for args in malicious_args[: fdp.ConsumeIntInRange(1, len(malicious_args))]:
            with contextlib.suppress(Exception):
                unsafe_args: Any = args
                bundle.format_pattern("msg", unsafe_args)

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _test_function_injection(fdp: atheris.FuzzedDataProvider) -> None:
    """Test function injection and recursive custom function attacks.

    Two sub-patterns:
    0 - No-op custom function (baseline injection)
    1 - Recursive custom function that calls back into bundle.format_pattern(),
        testing GlobalDepthGuard cross-context recursion protection
    """
    attack_variant = fdp.ConsumeIntInRange(0, 1)
    try:
        bundle = FluentBundle("en", strict=False)

        if attack_variant == 0:
            # Baseline: no-op custom function
            def noop_func(*_args: Any, **_kwargs: Any) -> str:
                return "safe_output"

            bundle.add_function("INJECT", noop_func)
            bundle.add_resource("msg = { INJECT() }\n")
            bundle.format_pattern("msg", {})
        else:
            # Recursive: custom function calls back into format_pattern,
            # exercising GlobalDepthGuard across function boundaries
            call_depth = fdp.ConsumeIntInRange(1, 10)
            counter = {"n": 0}

            def recursive_func(*_args: Any, **_kwargs: Any) -> str:
                counter["n"] += 1
                if counter["n"] < call_depth:
                    result, _ = bundle.format_pattern("recurse", {})
                    return str(result)
                return "base"

            bundle.add_function("RECURSE_FN", recursive_func)
            bundle.add_resource("recurse = { RECURSE_FN() }\nmsg = { RECURSE_FN() }\n")
            bundle.format_pattern("msg", {})

    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _assert_bundle_locale_accepts(raw_locale: str) -> None:
    """Accepted constructor locales are canonicalized to LocaleCode form."""
    try:
        bundle = FluentBundle(raw_locale, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        msg = f"FluentBundle rejected valid locale {raw_locale!r}: {err}"
        raise RuntimeIntegrityError(msg) from err

    expected_locale = require_locale_code(raw_locale, "locale")
    if bundle.locale != expected_locale:
        msg = (
            f"FluentBundle stored the wrong canonical locale for {raw_locale!r}: "
            f"{bundle.locale!r} vs {expected_locale!r}"
        )
        raise RuntimeIntegrityError(msg)

    bundle.add_resource("msg = ready\n")
    result, errors = bundle.format_pattern("msg", {})
    if result != "ready" or errors:
        msg = (
            f"FluentBundle with accepted locale {expected_locale!r} "
            f"failed basic formatting: result={result!r}, errors={errors!r}"
        )
        raise RuntimeIntegrityError(msg)


def _assert_bundle_locale_rejected(
    locale: object,
    *,
    expected_exception: type[ValueError | TypeError],
    expected_fragment: str,
) -> None:
    """Rejected constructor locales surface the canonical boundary error model."""
    locale_value: Any = locale

    try:
        FluentBundle(locale_value, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        if not isinstance(err, expected_exception):
            msg = (
                "FluentBundle raised the wrong locale-boundary exception for "
                f"{locale!r}: {type(err).__name__}"
            )
            raise RuntimeIntegrityError(msg) from err
        if expected_fragment not in str(err):
            msg = (
                "FluentBundle locale-boundary error message drifted for "
                f"{locale!r}: {err}"
            )
            raise RuntimeIntegrityError(msg) from err
        return

    msg = f"FluentBundle accepted invalid locale {locale!r}"
    raise RuntimeIntegrityError(msg)


def _test_locale_boundary(fdp: atheris.FuzzedDataProvider) -> None:
    """Test the FluentBundle constructor locale boundary contract."""
    _domain.locale_boundary_checks += 1
    scenario = fdp.ConsumeIntInRange(0, 5)
    boundary_locale = "a" + ("b" * (MAX_LOCALE_LENGTH_HARD_LIMIT - 2)) + "C"

    match scenario:
        case 0:
            raw_locale = fdp.PickValueInList(
                [
                    "  EN-us  ",
                    "\tpt-BR\n",
                    "  lv-LV  ",
                ]
            )
            _assert_bundle_locale_accepts(raw_locale)
        case 1:
            blank_locale = fdp.PickValueInList(["", " ", "\t\n", " \r\n "])
            _assert_bundle_locale_rejected(
                blank_locale,
                expected_exception=ValueError,
                expected_fragment="locale cannot be blank",
            )
        case 2:
            invalid_locale = fdp.PickValueInList(list(_STRUCTURALLY_INVALID_LOCALES))
            _assert_bundle_locale_rejected(
                invalid_locale,
                expected_exception=ValueError,
                expected_fragment="Invalid locale:",
            )
        case 3:
            _assert_bundle_locale_rejected(
                f"  {boundary_locale}  ",
                expected_exception=ValueError,
                expected_fragment="Unknown locale identifier",
            )
        case 4:
            overshoot = fdp.ConsumeIntInRange(1, 32)
            overlong_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + overshoot)
            _assert_bundle_locale_rejected(
                overlong_locale,
                expected_exception=ValueError,
                expected_fragment="locale exceeds maximum length",
            )
        case _:
            non_string_locale = fdp.PickValueInList(list(_NON_STRING_LOCALES))
            _assert_bundle_locale_rejected(
                non_string_locale,
                expected_exception=TypeError,
                expected_fragment="locale must be str",
            )


def _test_expansion_budget(fdp: atheris.FuzzedDataProvider) -> None:
    """Test Billion Laughs expansion budget.

    Constructs exponentially expanding message references:
    m0={m1}{m1}, m1={m2}{m2}, ... so small FTL produces huge output.
    The expansion budget (max_expansion_size) should halt resolution.
    """
    depth = fdp.ConsumeIntInRange(5, 20)
    # Use both default and small budgets to exercise the guard path
    budget = fdp.PickValueInList([100, 1000, 10000, None])
    try:
        kwargs: dict[str, Any] = {"strict": False}
        if budget is not None:
            kwargs["max_expansion_size"] = budget
        bundle = FluentBundle("en", **kwargs)
        parts = []
        for i in range(depth):
            parts.append(f"m{i} = {{ m{i + 1} }}{{ m{i + 1} }}\n")
        parts.append(f"m{depth} = payload\n")
        bundle.add_resource("\n".join(parts))
        bundle.format_pattern("m0", {})
    except (RecursionError, MemoryError, FrozenFluentError, ValueError):
        pass


def _test_dag_expansion(fdp: atheris.FuzzedDataProvider) -> None:
    """Test _make_hashable DAG expansion DoS.

    Constructs deeply shared references as cache args to stress the
    node budget in IntegrityCache._make_hashable().
    """
    try:
        bundle = FluentBundle("en", cache=CacheConfig(), strict=False)
        bundle.add_resource("msg = Hello { $name }\n")

        # Build DAG: l = [l, l] repeated N times.
        # Cap at 20: depth 20 creates 2^20 logical nodes which is sufficient
        # to trigger _make_hashable node budget (10,000). Higher depths cause
        # exponential str() expansion in the resolver (2^30 = 1B nodes).
        depth = fdp.ConsumeIntInRange(10, 20)
        dag: list[Any] = ["leaf"]
        for _ in range(depth):
            dag = [dag, dag]

        with contextlib.suppress(Exception):
            unsafe_args: Any = {"name": dag}
            bundle.format_pattern("msg", unsafe_args)

        # Lock must still be usable after DAG rejection
        with contextlib.suppress(Exception):
            bundle.format_pattern("msg", {"name": "safe"})

    except Exception:  # pylint: disable=broad-exception-caught
        pass
