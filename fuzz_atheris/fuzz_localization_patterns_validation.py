# mypy: disable-error-code=name-defined
from fuzz_localization_patterns_basic import (
    _assert_integrity_failure,
    _build_variable_message,
)
from fuzz_localization_support import (
    _LOCALE_PAIRS,
    _SINGLE_LOCALES,
    FluentLocalization,
    IntegrityCheckFailedError,
    LocalizationFuzzError,
    _domain,
    atheris,
    gen_ftl_identifier,
    validate_message_variables,
)


def _check_message_schema_exact_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Exact schemas succeed and preserve input order."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_count = fdp.ConsumeIntInRange(1, 3)
    expected_schemas: dict[str, frozenset[str] | set[str]] = {}
    resource_parts: list[str] = []

    for index in range(message_count):
        message_id = f"schema-{index}-{gen_ftl_identifier(fdp)}"
        variable_count = fdp.ConsumeIntInRange(1, 2)
        variables = tuple(
            f"var{index}_{slot}_{gen_ftl_identifier(fdp)}" for slot in range(variable_count)
        )
        expected = frozenset(variables) if fdp.ConsumeBool() else set(variables)
        expected_schemas[message_id] = expected
        resource_parts.append(_build_variable_message(message_id, variables))

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "".join(resource_parts))
    try:
        results = l10n.validate_message_schemas(expected_schemas)
    except IntegrityCheckFailedError as err:
        msg = f"validate_message_schemas() raised on exact schemas: {err}"
        raise LocalizationFuzzError(msg) from err

    if [result.message_id for result in results] != list(expected_schemas):
        msg = (
            "validate_message_schemas() returned results out of input order: "
            f"{[result.message_id for result in results]!r} vs {list(expected_schemas)!r}"
        )
        raise LocalizationFuzzError(msg)
    for result in results:
        expected_variables = frozenset(expected_schemas[result.message_id])
        if not result.is_valid or result.declared_variables != expected_variables:
            msg = (
                "validate_message_schemas() returned invalid exact-match result: "
                f"{result!r} vs {expected_variables!r}"
            )
            raise LocalizationFuzzError(msg)


def _assert_localization_message_validation_matches_lookup(
    l10n: FluentLocalization,
    message_id: str,
    expected_variables: frozenset[str] | set[str],
) -> None:
    """Single-message validation should match direct AST validation."""
    message = l10n.get_message(message_id)
    if message is None:
        msg = f"get_message('{message_id}') returned None during schema validation"
        raise LocalizationFuzzError(msg)

    direct = validate_message_variables(message, frozenset(expected_variables))
    resolved = l10n.validate_message_variables(message_id, expected_variables)
    if resolved != direct:
        msg = (
            "validate_message_variables() diverged from direct AST validation: "
            f"{resolved!r} vs {direct!r}"
        )
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-message exact-schema validation succeeds for direct hits."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"single-{gen_ftl_identifier(fdp)}"
    variable_count = fdp.ConsumeIntInRange(1, 2)
    variables = tuple(
        f"var_{slot}_{gen_ftl_identifier(fdp)}" for slot in range(variable_count)
    )
    expected_variables: frozenset[str] | set[str] = (
        frozenset(variables) if fdp.ConsumeBool() else set(variables)
    )

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, variables))
    _assert_localization_message_validation_matches_lookup(
        l10n,
        message_id,
        expected_variables,
    )


def _check_single_message_validation_fallback_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Single-message validation resolves through localization fallback."""
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    message_id = f"fallback-single-{gen_ftl_identifier(fdp)}"
    variable = f"fallback_{gen_ftl_identifier(fdp)}"
    expected_variables: frozenset[str] | set[str] = (
        frozenset({variable}) if fdp.ConsumeBool() else {variable}
    )

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, _build_variable_message(message_id, (variable,)))
    _assert_localization_message_validation_matches_lookup(
        l10n,
        message_id,
        expected_variables,
    )


def _check_single_message_validation_missing_message(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing messages fail the single-message localization validator."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    missing_id = f"missing-single-{gen_ftl_identifier(fdp)}"
    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "present = value\n")

    try:
        l10n.validate_message_variables(missing_id, frozenset())
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{missing_id}: not found",
            key=missing_id,
            actual_fragment="missing_messages=1",
        )
    else:
        msg = "validate_message_variables() accepted a missing message"
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_extra_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Extra declared variables fail exact single-message validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"extra-single-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(
        locale,
        _build_variable_message(message_id, (amount_var, customer_var)),
    )

    try:
        l10n.validate_message_variables(message_id, frozenset({amount_var}))
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{message_id}: extra {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_variables() accepted an extra-variable mismatch"
        raise LocalizationFuzzError(msg)


def _check_single_message_validation_missing_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing expected variables fail exact single-message validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"missing-var-single-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, (amount_var,)))

    try:
        l10n.validate_message_variables(message_id, {amount_var, customer_var})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_variables",
            message_fragment=f"{message_id}: missing {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_variables() accepted a missing-variable mismatch"
        raise LocalizationFuzzError(msg)


def _pattern_validate_message_variables_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_message_variables enforces exact schemas per message."""
    _domain.message_variable_validation_checks += 1
    handlers = (
        _check_single_message_validation_success,
        _check_single_message_validation_fallback_success,
        _check_single_message_validation_missing_message,
        _check_single_message_validation_extra_variable,
        _check_single_message_validation_missing_variable,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


def _check_message_schema_fallback_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Fallback-resolved messages validate through the localization facade."""
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    message_id = f"fallback-{gen_ftl_identifier(fdp)}"
    variable = f"fallback_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([primary, fallback], strict=False)
    l10n.add_resource(fallback, _build_variable_message(message_id, (variable,)))
    try:
        results = l10n.validate_message_schemas({message_id: frozenset({variable})})
    except IntegrityCheckFailedError as err:
        msg = f"validate_message_schemas() rejected fallback-resolved schema: {err}"
        raise LocalizationFuzzError(msg) from err

    if len(results) != 1 or not results[0].is_valid:
        msg = f"Fallback schema validation returned {results!r}"
        raise LocalizationFuzzError(msg)


def _check_message_schema_missing_message(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing messages fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    missing_id = f"missing-{gen_ftl_identifier(fdp)}"
    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, "present = value\n")

    try:
        l10n.validate_message_schemas({missing_id: frozenset()})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{missing_id}: not found",
            key=missing_id,
            actual_fragment="missing_messages=1",
        )
    else:
        msg = "validate_message_schemas() accepted a missing message"
        raise LocalizationFuzzError(msg)


def _check_message_schema_extra_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Extra variables in the message fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"extra-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(
        locale,
        _build_variable_message(message_id, (amount_var, customer_var)),
    )

    try:
        l10n.validate_message_schemas({message_id: frozenset({amount_var})})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{message_id}: extra {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_schemas() accepted an extra-variable mismatch"
        raise LocalizationFuzzError(msg)


def _check_message_schema_missing_variable(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing expected variables fail exact schema validation."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    message_id = f"missing-var-{gen_ftl_identifier(fdp)}"
    amount_var = f"amount_{gen_ftl_identifier(fdp)}"
    customer_var = f"customer_{gen_ftl_identifier(fdp)}"

    l10n = FluentLocalization([locale], strict=False)
    l10n.add_resource(locale, _build_variable_message(message_id, (amount_var,)))

    try:
        l10n.validate_message_schemas({message_id: {amount_var, customer_var}})
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="validate_message_schemas",
            message_fragment=f"{message_id}: missing {{{customer_var}}}",
            key=message_id,
            actual_fragment="schema_mismatches=1",
        )
    else:
        msg = "validate_message_schemas() accepted a missing-variable mismatch"
        raise LocalizationFuzzError(msg)


def _pattern_validate_message_schemas_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """validate_message_schemas enforces exact schemas through localization."""
    _domain.schema_validation_checks += 1
    handlers = (
        _check_message_schema_exact_success,
        _check_message_schema_fallback_success,
        _check_message_schema_missing_message,
        _check_message_schema_extra_variable,
        _check_message_schema_missing_variable,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)

