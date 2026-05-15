# mypy: disable-error-code=name-defined
from fuzz_localization_support import (
    _LOCALE_PAIRS,
    _NON_STRING_LOCALES,
    _SINGLE_LOCALES,
    _STRUCTURALLY_INVALID_LOCALES,
    _VALID_DEBUG_OPERATIONS,
    MAX_LOCALE_LENGTH_HARD_LIMIT,
    Any,
    CacheConfig,
    CacheDebugLogEntry,
    FallbackInfo,
    FluentLocalization,
    LocalizationCacheStats,
    LocalizationFuzzError,
    _domain,
    atheris,
    gen_ftl_identifier,
    gen_ftl_value,
    normalize_locale,
    require_locale_code,
)


def _pattern_add_function_custom(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Custom function registered via add_function and invoked in FTL.

    Tests the add_function pathway: a Python function is registered under a
    SCREAMING_SNAKE_CASE name and invoked from an FTL message. Verifies that
    function results appear in format_pattern output.
    """
    _domain.custom_function_calls += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    func_name = "UPPER"
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp, max_length=20)
    ftl = f"{msg_id} = {{ {func_name}($val) }}\n"

    # use_isolating=False: result equality check must not include FSI/PDI BiDi marks
    l10n = FluentLocalization([locale], strict=False, use_isolating=False)
    l10n.add_resource(locale, ftl)
    # Register custom function that uppercases its argument
    def upper_func(value: str) -> str:
        return str(value).upper()
    l10n.add_function(func_name, upper_func)

    result, errors = l10n.format_pattern(msg_id, {"val": val})

    if not errors:
        expected = val.upper()
        if result != expected:
            msg = f"Custom UPPER function: expected '{expected}', got '{result}'"
            raise LocalizationFuzzError(msg)


def _pattern_introspect_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """introspect_message and get_message_variables via localization facade.

    Tests the introspection delegation path: introspect_message() and
    get_message_variables() both delegate through the fallback chain.
    Verifies variable sets are consistent between the two APIs.
    """
    _domain.introspect_calls += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    var_a = gen_ftl_identifier(fdp)
    var_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
    ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    # introspect_message returns MessageIntrospection or None
    info = l10n.introspect_message(msg_id)
    variables = l10n.get_message_variables(msg_id)

    if info is not None:
        # Contract: get_message_variables must be a subset of introspect result
        introspect_vars = info.get_variable_names()
        for var in variables:
            if var not in introspect_vars:
                msg = (
                    f"get_message_variables returned '{var}' not in "
                    f"introspect result: {introspect_vars}"
                )
                raise LocalizationFuzzError(msg)


def _validate_localization_debug_log(
    locale: str,
    debug_log: tuple[CacheDebugLogEntry, ...],
    *,
    enable_debug_log: bool,
) -> int:
    """Validate one locale's debug log and return its entry count."""
    if not enable_debug_log and debug_log != ():
        msg = f"Debug-log-disabled localization returned non-empty log for '{locale}'"
        raise LocalizationFuzzError(msg)

    last_timestamp = float("-inf")
    last_sequence = 0
    for entry in debug_log:
        if entry.operation not in _VALID_DEBUG_OPERATIONS:
            msg = f"Unexpected debug-log operation {entry.operation!r} for locale '{locale}'"
            raise LocalizationFuzzError(msg)
        if not entry.key_fingerprint:
            msg = f"Empty debug-log key fingerprint for locale '{locale}'"
            raise LocalizationFuzzError(msg)
        if entry.timestamp_monotonic < last_timestamp:
            msg = (
                f"Debug-log timestamps regressed for locale '{locale}': "
                f"{last_timestamp} -> {entry.timestamp_monotonic}"
            )
            raise LocalizationFuzzError(msg)
        if entry.debug_sequence <= last_sequence:
            msg = (
                f"Debug-log sequence regressed for locale '{locale}': "
                f"{last_sequence} -> {entry.debug_sequence}"
            )
            raise LocalizationFuzzError(msg)
        if entry.operation == "MISS":
            if entry.checksum_hex != "" or entry.cache_sequence < 0:
                msg = (
                    f"MISS debug entry for locale '{locale}' must have "
                    "empty checksum and non-negative cache_sequence"
                )
                raise LocalizationFuzzError(msg)
        elif entry.checksum_hex == "" or entry.cache_sequence <= 0:
            msg = (
                f"{entry.operation} debug entry for locale '{locale}' must carry "
                "a positive cache_sequence and non-empty checksum"
            )
            raise LocalizationFuzzError(msg)
        last_timestamp = entry.timestamp_monotonic
        last_sequence = entry.debug_sequence

    return len(debug_log)


def _validate_localization_cache_stats(
    stats: LocalizationCacheStats,
    *,
    enable_debug_log: bool,
    expected_locales: list[str],
) -> None:
    """Validate aggregate localization cache stats against configuration."""
    if stats["debug_log_enabled"] != enable_debug_log:
        msg = (
            "get_cache_stats()['debug_log_enabled'] disagrees with CacheConfig: "
            f"{stats['debug_log_enabled']} vs {enable_debug_log}"
        )
        raise LocalizationFuzzError(msg)
    if stats["bundle_count"] != len(expected_locales):
        msg = (
            "get_cache_stats()['bundle_count'] disagrees with initialized locales: "
            f"{stats['bundle_count']} vs {len(expected_locales)}"
        )
        raise LocalizationFuzzError(msg)


def _collect_localization_debug_entries(
    debug_logs: dict[str, tuple[CacheDebugLogEntry, ...]],
    *,
    enable_debug_log: bool,
) -> int:
    """Validate all per-locale debug logs and return their combined length."""
    total_debug_entries = 0
    for locale, debug_log in debug_logs.items():
        if any(not isinstance(entry, CacheDebugLogEntry) for entry in debug_log):
            msg = f"get_cache_debug_log()['{locale}'] returned non-CacheDebugLogEntry data"
            raise LocalizationFuzzError(msg)
        total_debug_entries += _validate_localization_debug_log(
            locale,
            debug_log,
            enable_debug_log=enable_debug_log,
        )
    return total_debug_entries


def _pattern_cache_debug_log_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_cache_debug_log exposes per-locale immutable debug histories."""
    _domain.cache_debug_log_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    enable_debug_log = fdp.ConsumeBool()
    initialize_fallback = fdp.ConsumeBool()
    primary_msg_id = f"debug-{gen_ftl_identifier(fdp)}"
    fallback_msg_id = f"fallback-{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization(
        [primary, fallback],
        cache=CacheConfig(enable_debug_log=enable_debug_log),
        strict=False,
    )
    l10n.add_resource(primary, f"{primary_msg_id} = primary\n")

    expected_locales = [normalize_locale(primary)]
    if initialize_fallback:
        l10n.add_resource(fallback, f"{fallback_msg_id} = fallback\n")
        expected_locales.append(normalize_locale(fallback))

    l10n.format_value(primary_msg_id)
    l10n.format_value(primary_msg_id)
    if initialize_fallback:
        l10n.format_value(fallback_msg_id)

    debug_logs = l10n.get_cache_debug_log()
    if debug_logs is None:
        msg = "Cached FluentLocalization returned None from get_cache_debug_log()"
        raise LocalizationFuzzError(msg)
    if list(debug_logs) != expected_locales:
        msg = (
            "get_cache_debug_log() returned wrong locale keys: "
            f"{list(debug_logs)!r} vs {expected_locales!r}"
        )
        raise LocalizationFuzzError(msg)

    stats = l10n.get_cache_stats()
    if stats is None:
        msg = "Cached FluentLocalization returned None from get_cache_stats()"
        raise LocalizationFuzzError(msg)
    _validate_localization_cache_stats(
        stats,
        enable_debug_log=enable_debug_log,
        expected_locales=expected_locales,
    )
    total_debug_entries = _collect_localization_debug_entries(
        debug_logs,
        enable_debug_log=enable_debug_log,
    )

    if total_debug_entries != int(stats.get("debug_log_entries", 0)):
        msg = (
            "Localization debug-log length disagrees with cache stats: "
            f"{total_debug_entries} vs {stats.get('debug_log_entries')}"
        )
        raise LocalizationFuzzError(msg)

    primary_locale = normalize_locale(primary)
    fallback_locale = normalize_locale(fallback)
    if enable_debug_log and len(debug_logs[primary_locale]) < 2:
        msg = f"Primary locale '{primary_locale}' did not record expected debug entries"
        raise LocalizationFuzzError(msg)
    if initialize_fallback and enable_debug_log and len(debug_logs[fallback_locale]) < 2:
        msg = f"Fallback locale '{fallback_locale}' did not record expected debug entries"
        raise LocalizationFuzzError(msg)


def _assert_localization_locale_accepts(
    raw_locales: list[str],
    *,
    expected_locales: tuple[str, ...],
) -> None:
    """Accepted locale chains are canonicalized, deduplicated, and remain usable."""
    try:
        l10n = FluentLocalization(raw_locales, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        msg = f"FluentLocalization rejected valid locales {raw_locales!r}: {err}"
        raise LocalizationFuzzError(msg) from err

    if l10n.locales != expected_locales:
        msg = (
            "FluentLocalization stored the wrong locale chain: "
            f"{l10n.locales!r} vs {expected_locales!r}"
        )
        raise LocalizationFuzzError(msg)

    l10n.add_resource(expected_locales[0], "msg = ready\n")
    result, errors = l10n.format_pattern("msg")
    if result != "ready" or errors:
        msg = (
            f"FluentLocalization with accepted locales {expected_locales!r} "
            f"failed basic formatting: result={result!r}, errors={errors!r}"
        )
        raise LocalizationFuzzError(msg)


def _assert_localization_locale_rejected(
    locales: list[object],
    *,
    expected_exception: type[ValueError | TypeError],
    expected_fragment: str,
) -> None:
    """Rejected locale chains surface the canonical constructor error contract."""
    locales_value: Any = locales

    try:
        FluentLocalization(locales_value, strict=False)
    except Exception as err:  # pylint: disable=broad-exception-caught
        if not isinstance(err, expected_exception):
            msg = (
                "FluentLocalization raised the wrong locale-boundary exception for "
                f"{locales!r}: {type(err).__name__}"
            )
            raise LocalizationFuzzError(msg) from err
        if expected_fragment not in str(err):
            msg = (
                "FluentLocalization locale-boundary error message drifted for "
                f"{locales!r}: {err}"
            )
            raise LocalizationFuzzError(msg) from err
        return

    msg = f"FluentLocalization accepted invalid locales {locales!r}"
    raise LocalizationFuzzError(msg)


def _pattern_locale_boundary_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """FluentLocalization constructor shares the canonical locale boundary contract."""
    _domain.locale_boundary_checks += 1
    scenario = fdp.ConsumeIntInRange(0, 5)
    boundary_locale = "a" + ("b" * (MAX_LOCALE_LENGTH_HARD_LIMIT - 2)) + "C"

    match scenario:
        case 0:
            if fdp.ConsumeBool():
                raw_locales = ["  EN-us  ", "\tEN-us\n", " de-DE "]
                expected_locales = (
                    require_locale_code("  EN-us  ", "locale"),
                    require_locale_code(" de-DE ", "locale"),
                )
            else:
                raw_locales = ["  LV-lv  ", "\nLV-lv\t", " en-US "]
                expected_locales = (
                    require_locale_code("  LV-lv  ", "locale"),
                    require_locale_code(" en-US ", "locale"),
                )
            _assert_localization_locale_accepts(
                raw_locales,
                expected_locales=expected_locales,
            )
        case 1:
            blank_locale = fdp.PickValueInList(["", " ", "\t\n", " \r\n "])
            _assert_localization_locale_rejected(
                ["en", blank_locale],
                expected_exception=ValueError,
                expected_fragment="locale cannot be blank",
            )
        case 2:
            invalid_locale = fdp.PickValueInList(list(_STRUCTURALLY_INVALID_LOCALES))
            _assert_localization_locale_rejected(
                ["en", invalid_locale],
                expected_exception=ValueError,
                expected_fragment="Invalid locale:",
            )
        case 3:
            _assert_localization_locale_rejected(
                ["en", f"  {boundary_locale}  "],
                expected_exception=ValueError,
                expected_fragment="Unknown locale identifier",
            )
        case 4:
            overshoot = fdp.ConsumeIntInRange(1, 32)
            overlong_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + overshoot)
            _assert_localization_locale_rejected(
                ["en", overlong_locale],
                expected_exception=ValueError,
                expected_fragment="locale exceeds maximum length",
            )
        case _:
            non_string_locale = fdp.PickValueInList(list(_NON_STRING_LOCALES))
            _assert_localization_locale_rejected(
                ["en", non_string_locale],
                expected_exception=TypeError,
                expected_fragment="locale must be str",
            )


def _pattern_on_fallback_callback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """on_fallback callback fires when message resolved from fallback locale.

    Tests that the callback is invoked exactly once when the primary locale
    lacks the message and the fallback locale has it. Verifies FallbackInfo
    carries the correct requested and resolved locales.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"

    fallback_infos: list[FallbackInfo] = []

    l10n = FluentLocalization(
        [primary, fallback],
        strict=False,
        on_fallback=fallback_infos.append,
    )
    # Add message only to fallback locale
    l10n.add_resource(fallback, ftl)

    _, errors = l10n.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        if fallback_infos:
            _domain.fallback_triggered += 1
            info = fallback_infos[0]
            # Contract: requested_locale = primary, resolved_locale = fallback
            expected_fallback = normalize_locale(fallback)
            if info.requested_locale != normalize_locale(primary):
                msg = (
                    "Fallback callback recorded the wrong requested locale: "
                    f"{info.requested_locale!r} vs {normalize_locale(primary)!r}"
                )
                raise LocalizationFuzzError(msg)
            if info.resolved_locale != expected_fallback:
                msg = (
                    "Fallback callback recorded the wrong resolved locale: "
                    f"{info.resolved_locale!r} vs {expected_fallback!r}"
                )
                raise LocalizationFuzzError(msg)
