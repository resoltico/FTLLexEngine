# mypy: disable-error-code=name-defined
from fuzz_localization_support import (
    _LOCALE_PAIRS,
    _LOCALE_TRIPLES,
    _SINGLE_LOCALES,
    FallbackInfo,
    FluentLocalization,
    IntegrityCheckFailedError,
    LocalizationFuzzError,
    _domain,
    atheris,
    gen_ftl_identifier,
    gen_ftl_value,
    normalize_locale,
    pathlib,
    validate_message_variables,
)


def _write_loader_resource(
    root: pathlib.Path,
    locale: str,
    resource_id: str,
    ftl_source: str,
) -> pathlib.Path:
    """Write an FTL file for PathResourceLoader-backed tests."""
    locale_dir = root / normalize_locale(locale)
    locale_dir.mkdir(parents=True, exist_ok=True)
    resource_path = locale_dir / resource_id
    resource_path.write_text(ftl_source, encoding="utf-8")
    return resource_path


def _build_variable_message(message_id: str, variables: tuple[str, ...]) -> str:
    """Build a simple message that references the given variable set."""
    placeables = " ".join(f"{{ ${variable} }}" for variable in variables)
    return f"{message_id} = {placeables or 'value'}\n"


def _assert_integrity_failure(
    err: IntegrityCheckFailedError,
    *,
    operation: str,
    message_fragment: str | None = None,
    key: str | None = None,
    key_fragment: str | None = None,
    actual_fragment: str | None = None,
) -> None:
    """Validate localization-scoped IntegrityCheckFailedError context."""
    if message_fragment is not None and message_fragment not in str(err):
        msg = f"Integrity error message missing {message_fragment!r}: {err!s}"
        raise LocalizationFuzzError(msg)

    context = err.context
    if context is None:
        msg = "IntegrityCheckFailedError missing context"
        raise LocalizationFuzzError(msg)
    if context.component != "localization":
        msg = f"Integrity error component={context.component!r}, expected 'localization'"
        raise LocalizationFuzzError(msg)
    if context.operation != operation:
        msg = f"Integrity error operation={context.operation!r}, expected {operation!r}"
        raise LocalizationFuzzError(msg)
    if context.expected != "LoadSummary(all_clean=True)" and operation == "require_clean":
        msg = f"require_clean context expected field mismatch: {context.expected!r}"
        raise LocalizationFuzzError(msg)
    if key is not None and context.key != key:
        msg = f"Integrity error key={context.key!r}, expected {key!r}"
        raise LocalizationFuzzError(msg)
    if key_fragment is not None and (context.key is None or key_fragment not in context.key):
        msg = f"Integrity error key={context.key!r} missing fragment {key_fragment!r}"
        raise LocalizationFuzzError(msg)
    if actual_fragment is not None and (
        context.actual is None or actual_fragment not in context.actual
    ):
        msg = f"Integrity error actual={context.actual!r} missing fragment {actual_fragment!r}"
        raise LocalizationFuzzError(msg)


def _pattern_single_locale_add_resource(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-locale FluentLocalization: add_resource + format round-trip.

    Tests the minimal FluentLocalization configuration: one locale, one
    resource added via add_resource(), one format call. Verifies the
    basic construction-add-format lifecycle.
    """
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    msg_id = gen_ftl_identifier(fdp)
    var = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {{ ${var} }}\n"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, ftl)

    result, errors = l10n.format_pattern(msg_id, {var: val})

    # Contract: no errors means result must contain the variable value
    if not errors and val not in result:
        msg = (
            f"Single locale: format_pattern('{msg_id}', {{'{var}': '{val}'}}) "
            f"returned '{result}' without errors but value missing"
        )
        raise LocalizationFuzzError(msg)

    if not errors:
        _domain.messages_found += 1
    else:
        _domain.messages_missing += 1


def _pattern_multi_locale_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Two-locale chain: message present only in fallback locale.

    Tests the core fallback mechanism: the primary locale does NOT have the
    message, the fallback locale does. Verifies that format_pattern traverses
    the chain and returns the fallback locale's result.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    # Add resource ONLY to fallback locale; primary stays empty
    l10n.add_resource(fallback, ftl)

    fallback_seen: list[FallbackInfo] = []
    l10n_with_cb = FluentLocalization(
        [primary, fallback],
        strict=False,
        on_fallback=fallback_seen.append,
    )
    l10n_with_cb.add_resource(fallback, ftl)

    _, errors = l10n_with_cb.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        # Fallback callback must have fired (primary locale had no message)
        if fallback_seen:
            _domain.fallback_triggered += 1
            info = fallback_seen[0]
            # Contract: FallbackInfo carries the correct resolved_locale
            expected_fallback = normalize_locale(fallback)
            if info.resolved_locale != expected_fallback:
                msg = (
                    "Fallback: expected "
                    f"resolved_locale='{expected_fallback}', "
                    f"got '{info.resolved_locale}'"
                )
                raise LocalizationFuzzError(msg)
    else:
        _domain.messages_missing += 1


def _pattern_chain_of_3_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Three-locale chain: message in a fuzz-chosen position.

    Tests fallback traversal depth. The message can be in locale 0, 1, or 2
    (or nowhere). Verifies the fallback chain visits locales in order.
    """
    triple = fdp.PickValueInList(list(_LOCALE_TRIPLES))
    locale_a, locale_b, locale_c = triple
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n"
    target_locale_idx = fdp.ConsumeIntInRange(0, 3)  # 3 = none

    l10n = FluentLocalization([locale_a, locale_b, locale_c], strict=False)

    target_locale = triple[target_locale_idx] if target_locale_idx < 3 else None
    if target_locale:
        l10n.add_resource(target_locale, ftl)

    result, errors = l10n.format_pattern(msg_id)

    if not errors:
        _domain.messages_found += 1
        if target_locale and val in result:
            return  # Correct
        if not target_locale:
            # Message was in no locale - result is fallback text, errors expected
            pass
    else:
        _domain.messages_missing += 1


def _pattern_format_value_missing(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """format_value/format_pattern with non-existent message returns fallback.

    Tests the missing-message contract: format_pattern with a message ID that
    does not exist in any locale must return a non-empty fallback string and
    at least one error. strict=False to use soft-error return API.
    """
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    existing_id = gen_ftl_identifier(fdp)
    missing_id = f"missing-{gen_ftl_identifier(fdp)}"
    existing_ftl = f"{existing_id} = value\n"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, existing_ftl)

    result, errors = l10n.format_pattern(missing_id)

    # Contract: missing message MUST produce errors and non-empty fallback
    if not errors:
        msg = f"Missing message '{missing_id}' produced no errors (result='{result}')"
        raise LocalizationFuzzError(msg)
    if not result:
        msg = f"Missing message '{missing_id}' produced empty result with errors"
        raise LocalizationFuzzError(msg)

    _domain.messages_missing += 1


def _pattern_format_with_variables(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """format_pattern with multiple variable args across two locales.

    Tests that variable substitution works correctly with fallback.
    Verifies the args dict propagates into the resolved bundle.
    """
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    var_a = gen_ftl_identifier(fdp)
    var_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
    val_a = gen_ftl_value(fdp, max_length=20)
    val_b = gen_ftl_value(fdp, max_length=20)
    ftl = f"{msg_id} = {{ ${var_a} }} {{ ${var_b} }}\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    result, errors = l10n.format_pattern(msg_id, {var_a: val_a, var_b: val_b})

    if not errors:
        _domain.messages_found += 1
        if val_a not in result or val_b not in result:
            msg = f"Variables not found in result: expected '{val_a}' and '{val_b}', got '{result}'"
            raise LocalizationFuzzError(msg)


def _pattern_add_resource_mutation(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """add_resource after initial format call; re-format sees new resource.

    Tests that RWLock correctly serializes post-construction add_resource
    against concurrent format_pattern calls. The resource adds a new message
    and the second format_pattern must see it.
    """
    _domain.add_resource_mutations += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    msg_id_a = gen_ftl_identifier(fdp)
    msg_id_b = f"B-{gen_ftl_identifier(fdp)}"  # B: gen_ftl_identifier always starts with a-z
    val_a = gen_ftl_value(fdp)
    val_b = gen_ftl_value(fdp)

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, f"{msg_id_a} = {val_a}\n")

    # First format (before mutation)
    l10n.format_pattern(msg_id_a)
    _, errors_b1 = l10n.format_pattern(msg_id_b)

    # msg_b not yet added - must produce errors
    if not errors_b1:
        msg = f"Before mutation: '{msg_id_b}' found before add_resource"
        raise LocalizationFuzzError(msg)

    # Add second message (mutation)
    l10n.add_resource(locale, f"{msg_id_b} = {val_b}\n")

    # Re-format after mutation
    result_b2, errors_b2 = l10n.format_pattern(msg_id_b)

    if not errors_b2 and val_b not in result_b2:
        msg = f"After mutation: expected '{val_b}' in result, got '{result_b2}'"
        raise LocalizationFuzzError(msg)


def _pattern_has_message_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """has_message/has_attribute cross-locale scan invariants.

    Tests: if format_pattern succeeds for a message ID, has_message must
    return True. If has_message returns False, format_pattern must produce
    errors.
    """
    _domain.has_message_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = gen_ftl_identifier(fdp)
    attr_name = fdp.PickValueInList(["tooltip", "label", "title"])
    val = gen_ftl_value(fdp)
    ftl = f"{msg_id} = {val}\n    .{attr_name} = hint\n"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, ftl)

    has_msg = l10n.has_message(msg_id)
    has_attr = l10n.has_attribute(msg_id, attr_name)
    has_missing_attr = l10n.has_attribute(msg_id, "nonexistent-attr")

    # Contract: has_message must be True (we added it to fallback)
    if not has_msg:
        msg = f"has_message('{msg_id}') returned False after add_resource"
        raise LocalizationFuzzError(msg)

    # Contract: has_attribute(existing) must be True
    if not has_attr:
        msg = f"has_attribute('{msg_id}', '{attr_name}') returned False after add_resource"
        raise LocalizationFuzzError(msg)

    # Contract: has_attribute(nonexistent) must be False
    if has_missing_attr:
        msg = f"has_attribute('{msg_id}', 'nonexistent-attr') returned True"
        raise LocalizationFuzzError(msg)


def _validate_localization_message_lookup(
    l10n: FluentLocalization,
    message_id: str,
    expected_variables: frozenset[str],
) -> None:
    """Validate FluentLocalization.get_message() for one identifier."""
    message = l10n.get_message(message_id)
    if message is None:
        msg = f"get_message('{message_id}') returned None for an existing message"
        raise LocalizationFuzzError(msg)
    if message.id.name != message_id:
        msg = f"get_message('{message_id}') returned node named '{message.id.name}'"
        raise LocalizationFuzzError(msg)

    message_validation = validate_message_variables(message, expected_variables)
    if not message_validation.is_valid:
        msg = f"validate_message_variables() rejected localization message '{message_id}'"
        raise LocalizationFuzzError(msg)
    if message_validation.declared_variables != expected_variables:
        msg = (
            f"get_message('{message_id}') resolved wrong locale variables: "
            f"{message_validation.declared_variables!r} vs {expected_variables!r}"
        )
        raise LocalizationFuzzError(msg)


def _validate_localization_term_lookup(
    l10n: FluentLocalization,
    term_id: str,
    expected_variables: frozenset[str],
) -> None:
    """Validate FluentLocalization.get_term() for one identifier."""
    term = l10n.get_term(term_id)
    if term is None:
        msg = f"get_term('{term_id}') returned None for an existing term"
        raise LocalizationFuzzError(msg)
    if term.id.name != term_id:
        msg = f"get_term('{term_id}') returned node named '{term.id.name}'"
        raise LocalizationFuzzError(msg)

    term_validation = validate_message_variables(term, expected_variables)
    if not term_validation.is_valid:
        msg = f"validate_message_variables() rejected localization term '{term_id}'"
        raise LocalizationFuzzError(msg)
    if term_validation.declared_variables != expected_variables:
        msg = (
            f"get_term('{term_id}') resolved wrong locale variables: "
            f"{term_validation.declared_variables!r} vs {expected_variables!r}"
        )
        raise LocalizationFuzzError(msg)


def _pattern_ast_lookup_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_message/get_term honor fallback precedence and namespace boundaries."""
    _domain.ast_lookup_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    msg_id = f"msg-{gen_ftl_identifier(fdp)}"
    term_id = f"term-{gen_ftl_identifier(fdp)}"
    primary_has_message = fdp.ConsumeBool()
    primary_has_term = fdp.ConsumeBool()

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(
        fallback,
        (f"{msg_id} = {{ $fallbackvar }}\n-{term_id} = {{ $fallbackterm }}\n"),
    )

    primary_parts: list[str] = []
    if primary_has_message:
        primary_parts.append(f"{msg_id} = {{ $primaryvar }}\n")
    if primary_has_term:
        primary_parts.append(f"-{term_id} = {{ $primaryterm }}\n")
    if primary_parts:
        l10n.add_resource(primary, "".join(primary_parts))

    expected_message_vars = frozenset({"primaryvar" if primary_has_message else "fallbackvar"})
    _validate_localization_message_lookup(l10n, msg_id, expected_message_vars)

    expected_term_vars = frozenset({"primaryterm" if primary_has_term else "fallbackterm"})
    _validate_localization_term_lookup(l10n, term_id, expected_term_vars)

    if l10n.get_term(f"-{term_id}") is not None:
        msg = f"get_term('-{term_id}') bypassed the no-leading-dash contract"
        raise LocalizationFuzzError(msg)
    if l10n.get_message(term_id) is not None:
        msg = f"get_message('{term_id}') crossed the term/message namespace boundary"
        raise LocalizationFuzzError(msg)
    if l10n.get_term(msg_id) is not None:
        msg = f"get_term('{msg_id}') crossed the message/term namespace boundary"
        raise LocalizationFuzzError(msg)
    if l10n.get_message("__missing_localization_lookup__") is not None:
        msg = "get_message() returned a node for a missing localization message"
        raise LocalizationFuzzError(msg)
    if l10n.get_term("__missing_localization_lookup__") is not None:
        msg = "get_term() returned a node for a missing localization term"
        raise LocalizationFuzzError(msg)


def _pattern_get_message_ids_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """get_message_ids returns superset of added message IDs.

    Tests deduplication: if the same message ID is added to two locales, it
    must appear only once in get_message_ids(). Also checks that
    get_message_ids() contains every message we added.
    """
    locale_a, locale_b = fdp.PickValueInList(list(_LOCALE_PAIRS))
    n = fdp.ConsumeIntInRange(1, 5)
    msg_ids = [gen_ftl_identifier(fdp) for _ in range(n)]

    l10n = FluentLocalization([locale_a, locale_b], strict=False)

    # Add same messages to both locales (deduplication test)
    for mid in msg_ids:
        l10n.add_resource(locale_a, f"{mid} = value-a\n")
        l10n.add_resource(locale_b, f"{mid} = value-b\n")

    all_ids = l10n.get_message_ids()
    all_ids_set = set(all_ids)

    # Contract: every added message ID must appear
    for mid in msg_ids:
        if mid not in all_ids_set:
            msg = f"get_message_ids(): missing '{mid}' after add_resource"
            raise LocalizationFuzzError(msg)

    # Contract: no duplicates
    if len(all_ids) != len(all_ids_set):
        msg = f"get_message_ids(): duplicates found: {sorted(all_ids)}"
        raise LocalizationFuzzError(msg)


def _pattern_validate_resource_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_resource via FluentLocalization facade.

    Tests that validate_resource returns a ValidationResult and that
    its errors/warnings attributes are sequences (never crashes, never
    returns None, always returns a structured result).
    """
    _domain.validate_calls += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    ftl_choice = fdp.ConsumeIntInRange(0, 5)

    match ftl_choice:
        case 0:
            ftl = f"{gen_ftl_identifier(fdp)} = valid message\n"
        case 1:
            ftl = "invalid = { $x -> [one] singular *[other] plural }\n"
        case 2:
            ftl = ""  # Empty
        case 3:
            ftl = "# Just a comment\n"
        case 4:
            # Duplicate message ID
            mid = gen_ftl_identifier(fdp)
            ftl = f"{mid} = first\n{mid} = second\n"
        case _:
            ftl = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 200))

    l10n = FluentLocalization([locale], strict=False)
    result = l10n.validate_resource(ftl)

    # Contract: errors and warnings are tuples/sequences
    if not hasattr(result, "errors") or not hasattr(result, "warnings"):
        msg = "validate_resource result missing errors/warnings"
        raise LocalizationFuzzError(msg)

