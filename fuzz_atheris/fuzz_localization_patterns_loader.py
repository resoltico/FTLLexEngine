# mypy: disable-error-code=name-defined
from fuzz_localization_patterns_basic import (
    _assert_integrity_failure,
    _write_loader_resource,
)
from fuzz_localization_support import (
    _LOCALE_PAIRS,
    _SINGLE_LOCALES,
    FluentLocalization,
    IntegrityCheckFailedError,
    LocalizationFuzzError,
    PathResourceLoader,
    TemporaryDirectory,
    _domain,
    atheris,
    gen_ftl_identifier,
    gen_ftl_value,
    normalize_locale,
    pathlib,
)


def _pattern_loader_init_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """PathResourceLoader eager-init path records all-success summary data."""
    _domain.loader_init_checks += 1
    locale_a, locale_b = fdp.PickValueInList(list(_LOCALE_PAIRS))
    resource_id = "main.ftl"
    msg_id = gen_ftl_identifier(fdp)
    primary_val = gen_ftl_value(fdp)
    fallback_val = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale_a, resource_id, f"{msg_id} = {primary_val}\n")
        _write_loader_resource(root, locale_b, resource_id, f"{msg_id} = {fallback_val}\n")

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale_a, locale_b],
            [resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.successful != 2 or not summary.all_successful:
            msg = (
                f"Expected two successful eager loads, got successful={summary.successful}, "
                f"not_found={summary.not_found}, errors={summary.errors}"
            )
            raise LocalizationFuzzError(msg)
        if summary.has_errors or summary.has_junk:
            msg = (
                f"Unexpected summary state: has_errors={summary.has_errors}, "
                f"has_junk={summary.has_junk}"
            )
            raise LocalizationFuzzError(msg)
        if any(result.source_path is None for result in summary.results):
            msg = "Loader summary missing source_path on successful result"
            raise LocalizationFuzzError(msg)

        result, errors = l10n.format_pattern(msg_id)
        if errors:
            msg = f"Loader-backed localization unexpectedly returned errors: {errors!r}"
            raise LocalizationFuzzError(msg)
        if primary_val not in result:
            msg = f"Primary locale value {primary_val!r} missing from result {result!r}"
            raise LocalizationFuzzError(msg)


def _pattern_loader_not_found_fallback(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Primary miss is tracked as not_found while fallback still resolves."""
    _domain.loader_init_checks += 1
    primary, fallback = fdp.PickValueInList(list(_LOCALE_PAIRS))
    resource_id = "main.ftl"
    msg_id = gen_ftl_identifier(fdp)
    val = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, fallback, resource_id, f"{msg_id} = {val}\n")

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [primary, fallback],
            [resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.successful != 1 or summary.not_found != 1 or summary.errors != 0:
            msg = (
                f"Unexpected mixed summary: successful={summary.successful}, "
                f"not_found={summary.not_found}, errors={summary.errors}"
            )
            raise LocalizationFuzzError(msg)

        result, errors = l10n.format_pattern(msg_id)
        if errors:
            msg = f"Fallback load should resolve successfully, got errors={errors!r}"
            raise LocalizationFuzzError(msg)
        if val not in result:
            msg = f"Fallback value {val!r} missing from result {result!r}"
            raise LocalizationFuzzError(msg)


def _pattern_loader_junk_summary(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Junk entries discovered during eager load are preserved in LoadSummary."""
    _domain.loader_junk_checks += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "broken.ftl"
    junk_source = f"{gen_ftl_identifier(fdp)} = {{\n"

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, junk_source)

        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)
        summary = l10n.get_load_summary()

        if summary.successful != 1 or not summary.has_junk or summary.junk_count < 1:
            msg = (
                f"Expected junk-bearing successful load, got successful={summary.successful}, "
                f"has_junk={summary.has_junk}, junk_count={summary.junk_count}"
            )
            raise LocalizationFuzzError(msg)
        if summary.all_clean:
            msg = "LoadSummary.all_clean unexpectedly true for junk input"
            raise LocalizationFuzzError(msg)
        if not summary.get_with_junk():
            msg = "LoadSummary.get_with_junk() returned empty tuple"
            raise LocalizationFuzzError(msg)


def _pattern_loader_path_error(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Invalid resource IDs surface as loader errors in the eager-load summary."""
    _domain.loader_error_checks += 1
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    invalid_resource_id = fdp.PickValueInList(
        [
            "../escape.ftl",
            " main.ftl",
            "/absolute.ftl",
        ]
    )

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale],
            [invalid_resource_id],
            loader,
            strict=False,
        )
        summary = l10n.get_load_summary()

        if summary.errors != 1 or not summary.has_errors:
            msg = (
                f"Expected one loader error for invalid resource_id, got "
                f"errors={summary.errors}, not_found={summary.not_found}"
            )
            raise LocalizationFuzzError(msg)

        first_error = summary.get_errors()[0].error
        if not isinstance(first_error, ValueError):
            msg = (
                "Expected ValueError from PathResourceLoader validation, got "
                f"{type(first_error).__name__}"
            )
            raise LocalizationFuzzError(msg)


def _check_require_clean_empty_init(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Empty initialization is considered clean."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    l10n = FluentLocalization([locale], strict=False)
    try:
        summary = l10n.require_clean()
    except IntegrityCheckFailedError as err:
        msg = f"require_clean() raised on empty initialization: {err}"
        raise LocalizationFuzzError(msg) from err

    if not summary.all_clean or summary.total_attempted != 0:
        msg = f"Empty initialization should be clean, got {summary!r}"
        raise LocalizationFuzzError(msg)


def _check_require_clean_loader_success(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """All-success loader summaries return from require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "main.ftl"
    message_id = f"clean-{gen_ftl_identifier(fdp)}"
    value = gen_ftl_value(fdp)

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, f"{message_id} = {value}\n")
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)
        try:
            summary = l10n.require_clean()
        except IntegrityCheckFailedError as err:
            msg = f"require_clean() rejected an all-success summary: {err}"
            raise LocalizationFuzzError(msg) from err

        if not summary.all_clean or summary.successful != 1 or summary.errors != 0:
            msg = f"Clean loader initialization returned wrong summary: {summary!r}"
            raise LocalizationFuzzError(msg)


def _check_require_clean_missing_loader(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Missing resources fail require_clean() with integrity context."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    normalized_locale = normalize_locale(locale)
    resource_id = "main.ftl"

    class MissingLoader:
        def load(self, _locale: str, _resource_id: str) -> str:
            msg = "missing"
            raise FileNotFoundError(msg)

        def describe_path(self, locale: str, resource_id: str) -> str:
            return f"{locale}/{resource_id}"

    l10n = FluentLocalization([locale], [resource_id], MissingLoader(), strict=False)

    try:
        l10n.require_clean()
    except IntegrityCheckFailedError as err:
        _assert_integrity_failure(
            err,
            operation="require_clean",
            message_fragment="not clean",
            key=f"{normalized_locale}/{resource_id}",
            actual_fragment="LoadSummary(",
        )
    else:
        msg = "require_clean() accepted a missing-resource summary"
        raise LocalizationFuzzError(msg)


def _check_require_clean_junk_resource(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Junk-bearing resources fail require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    resource_id = "broken.ftl"
    junk_source = f"{gen_ftl_identifier(fdp)} = {{\n"

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        _write_loader_resource(root, locale, resource_id, junk_source)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization([locale], [resource_id], loader, strict=False)

        try:
            l10n.require_clean()
        except IntegrityCheckFailedError as err:
            _assert_integrity_failure(
                err,
                operation="require_clean",
                message_fragment="junk",
                key_fragment=resource_id,
                actual_fragment="LoadSummary(",
            )
        else:
            msg = "require_clean() accepted a junk-bearing summary"
            raise LocalizationFuzzError(msg)


def _check_require_clean_loader_error(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """Loader validation errors fail require_clean()."""
    locale = fdp.PickValueInList(list(_SINGLE_LOCALES))
    invalid_resource_id = fdp.PickValueInList(
        [
            "../escape.ftl",
            " main.ftl",
            "/absolute.ftl",
        ]
    )

    with TemporaryDirectory(prefix="ftllexengine-fuzz-loader-") as tmp_dir:
        root = pathlib.Path(tmp_dir)
        loader = PathResourceLoader(str(root / "{locale}"))
        l10n = FluentLocalization(
            [locale],
            [invalid_resource_id],
            loader,
            strict=False,
        )

        try:
            l10n.require_clean()
        except IntegrityCheckFailedError as err:
            _assert_integrity_failure(
                err,
                operation="require_clean",
                message_fragment="load error",
                key_fragment=invalid_resource_id,
                actual_fragment="LoadSummary(",
            )
        else:
            msg = "require_clean() accepted a loader error summary"
            raise LocalizationFuzzError(msg)


def _pattern_require_clean_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """require_clean returns only for clean initialization summaries."""
    _domain.boot_validation_checks += 1
    handlers = (
        _check_require_clean_empty_init,
        _check_require_clean_loader_success,
        _check_require_clean_missing_loader,
        _check_require_clean_junk_resource,
        _check_require_clean_loader_error,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


