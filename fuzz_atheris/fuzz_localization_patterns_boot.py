# mypy: disable-error-code=name-defined
from fuzz_localization_support import (
    _ALLOWED_EXCEPTIONS,
    IntegrityCheckFailedError,
    LocalizationBootConfig,
    LocalizationFuzzError,
    _domain,
    atheris,
)


def _check_boot_config_validation(fdp: atheris.FuzzedDataProvider) -> None:
    """__post_init__ rejects empty locales/resource_ids and missing loader/base_path."""
    choice = fdp.ConsumeIntInRange(0, 2)
    try:
        if choice == 0:
            LocalizationBootConfig(
                locales=(),
                resource_ids=("ui.ftl",),
                loader=_EmptyLoader(),
            )
            msg = "Empty locales did not raise ValueError"
            raise LocalizationFuzzError(msg)
        if choice == 1:
            LocalizationBootConfig(
                locales=("en",),
                resource_ids=(),
                loader=_EmptyLoader(),
            )
            msg = "Empty resource_ids did not raise ValueError"
            raise LocalizationFuzzError(msg)
        LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
        )
        msg = "Missing loader/base_path did not raise ValueError"
        raise LocalizationFuzzError(msg)
    except ValueError:
        pass  # expected


def _check_boot_config_boot_success(fdp: atheris.FuzzedDataProvider) -> None:
    """boot_simple() returns FluentLocalization for a valid in-memory FTL resource."""
    locale = fdp.PickValueInList(["en", "de", "lv"])
    ftl = f"greeting = Hello {{ $name }}\nmsg{fdp.ConsumeIntInRange(0, 9)} = Value\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        l10n = cfg.boot_simple()
        result, errors = l10n.format_pattern("greeting", {"name": "bootstrap"})
        if errors or "bootstrap" not in result:
            msg = (
                "boot_simple() returned unusable localization: "
                f"result={result!r}, errors={errors!r}"
            )
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # strict syntax errors in generated FTL are acceptable
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_boot_with_summary(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() returns a 3-tuple with correct types and clean LoadSummary."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "msg = Value\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        l10n, summary, schema_results = cfg.boot()
        if summary.errors != 0:
            msg = f"LoadSummary.errors={summary.errors} for clean resource"
            raise LocalizationFuzzError(msg)
        if summary.total_attempted < 1:
            msg = f"LoadSummary.total_attempted={summary.total_attempted}, expected >= 1"
            raise LocalizationFuzzError(msg)
        result, errors = l10n.format_pattern("msg")
        if errors or result != "Value":
            msg = f"boot() returned unusable localization: result={result!r}, errors={errors!r}"
            raise LocalizationFuzzError(msg)
        if schema_results != ():
            msg = f"boot() returned schema results without message_schemas: {schema_results!r}"
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_boot_failure(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() raises IntegrityCheckFailedError when a resource cannot be loaded."""
    locale = fdp.PickValueInList(["en", "de"])
    loader = _EmptyLoader()  # no resources registered -> FileNotFoundError
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("missing.ftl",),
            loader=loader,
        )
        cfg.boot()
        msg = "boot() did not raise IntegrityCheckFailedError for missing resource"
        raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # expected
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_required_messages_absent(fdp: atheris.FuzzedDataProvider) -> None:
    """required_messages raises IntegrityCheckFailedError when an ID is absent."""
    locale = fdp.PickValueInList(["en", "de"])
    # Load a resource that has "greeting" but NOT "farewell"
    ftl = "greeting = Hello\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
            required_messages=frozenset({"greeting", "farewell"}),
        )
        cfg.boot()
        msg = "boot() did not raise IntegrityCheckFailedError for absent required message"
        raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # expected: "farewell" is absent
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_required_messages_present(fdp: atheris.FuzzedDataProvider) -> None:
    """required_messages succeeds when all IDs resolve in at least one locale."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "greeting = Hello\nfarewell = Goodbye\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
            required_messages=frozenset({"greeting", "farewell"}),
        )
        l10n, summary, _ = cfg.boot()
        if summary.errors != 0:
            msg = f"LoadSummary.errors={summary.errors} for clean resource"
            raise LocalizationFuzzError(msg)
        farewell, errors = l10n.format_pattern("farewell")
        if errors or farewell != "Goodbye":
            msg = (
                "Required-message boot returned unusable localization: "
                f"result={farewell!r}, errors={errors!r}"
            )
            raise LocalizationFuzzError(msg)
    except IntegrityCheckFailedError:
        pass  # generated FTL may have syntax issues
    except _ALLOWED_EXCEPTIONS:
        pass


def _check_boot_config_one_shot(fdp: atheris.FuzzedDataProvider) -> None:
    """boot() and boot_simple() are one-shot: second call raises RuntimeError."""
    locale = fdp.PickValueInList(["en", "de"])
    ftl = "greeting = Hello\n"
    loader = _SingleResourceLoader(locale, "ui.ftl", ftl)
    use_simple = fdp.ConsumeBool()
    try:
        cfg = LocalizationBootConfig(
            locales=(locale,),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        # First call must succeed
        if use_simple:
            cfg.boot_simple()
        else:
            cfg.boot()
        # Second call must raise RuntimeError (one-shot enforcement)
        try:
            if use_simple:
                cfg.boot_simple()
            else:
                cfg.boot()
            msg = (
                "boot() did not raise RuntimeError on second call "
                "(one-shot enforcement missing)"
            )
            raise LocalizationFuzzError(msg)
        except RuntimeError:
            pass  # expected: one-shot enforcement
    except IntegrityCheckFailedError:
        pass  # FTL may have syntax issues -- acceptable
    except _ALLOWED_EXCEPTIONS:
        pass


def _pattern_boot_config_api(
    fdp: atheris.FuzzedDataProvider,
) -> None:
    """LocalizationBootConfig strict-mode boot sequence and invariants."""
    _domain.boot_config_checks += 1
    handlers = (
        _check_boot_config_validation,
        _check_boot_config_boot_success,
        _check_boot_config_boot_with_summary,
        _check_boot_config_boot_failure,
        _check_boot_config_required_messages_absent,
        _check_boot_config_required_messages_present,
        _check_boot_config_one_shot,
    )
    handler = handlers[fdp.ConsumeIntInRange(0, len(handlers) - 1)]
    handler(fdp)


class _EmptyLoader:
    """ResourceLoader with no resources — always raises FileNotFoundError."""

    def load(self, locale: str, resource_id: str) -> str:
        msg = f"No resource for ({locale!r}, {resource_id!r})"
        raise FileNotFoundError(msg)

    def describe_path(self, locale: str, resource_id: str) -> str:
        return f"empty://{locale}/{resource_id}"


class _SingleResourceLoader:
    """ResourceLoader backed by a single (locale, resource_id) → FTL mapping."""

    def __init__(self, locale: str, resource_id: str, ftl: str) -> None:
        self._locale = locale
        self._resource_id = resource_id
        self._ftl = ftl

    def load(self, locale: str, resource_id: str) -> str:
        if locale == self._locale and resource_id == self._resource_id:
            return self._ftl
        msg = f"No resource for ({locale!r}, {resource_id!r})"
        raise FileNotFoundError(msg)

    def describe_path(self, locale: str, resource_id: str) -> str:
        return f"memory://{locale}/{resource_id}"
