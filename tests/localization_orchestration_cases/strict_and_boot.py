# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.integrity import (
    FormattingIntegrityError,
    IntegrityCheckFailedError,
)
from ftllexengine.localization import (
    FluentLocalization,
    LoadSummary,
)


class TestStrictMode:
    """Tests for FluentLocalization strict mode (fail-fast on errors)."""

    def test_strict_property_reflects_constructor(self) -> None:
        """strict property returns constructor value."""
        l10n_strict = FluentLocalization(["en"], strict=True)
        l10n_default = FluentLocalization(["en"])
        assert l10n_strict.strict is True
        assert l10n_default.strict is True

    def test_strict_raises_on_missing_message(self) -> None:
        """Strict mode raises FormattingIntegrityError for missing messages."""
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "hello = Hello\n")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_value("nonexistent")

        err = exc_info.value
        assert err.message_id == "nonexistent"
        assert err.fallback_value is not None
        assert len(err.fluent_errors) == 1
        ctx = err.context
        assert ctx is not None
        assert ctx.component == "localization"
        assert ctx.operation == "format_pattern"

    def test_strict_raises_on_empty_message_id(self) -> None:
        """Strict mode raises for empty/invalid message ID."""
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "hello = Hello\n")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_value("")

        err = exc_info.value
        assert err.message_id == ""
        assert len(err.fluent_errors) == 1

    def test_strict_format_pattern_raises_on_missing(self) -> None:
        """Strict mode raises via format_pattern path."""
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "hello = Hello\n")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_pattern("nonexistent")

        assert exc_info.value.message_id == "nonexistent"

    def test_strict_error_context_fields(self) -> None:
        """Strict error includes component, operation, and count metadata."""
        l10n = FluentLocalization(["en"], strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_value("missing")

        err = exc_info.value
        assert "failed:" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.actual == "<1 error>"
        assert ctx.expected == "<no errors>"

    def test_strict_raises_on_invalid_args_type(self) -> None:
        """Strict mode raises FormattingIntegrityError for invalid args type."""
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "hello = Hello\n")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_pattern("hello", "not-a-mapping")  # type: ignore[arg-type]

        err = exc_info.value
        assert len(err.fluent_errors) == 1
        ctx = err.context
        assert ctx is not None
        assert ctx.component == "localization"

    def test_strict_raises_on_invalid_attribute_type(self) -> None:
        """Strict mode raises FormattingIntegrityError for invalid attribute type."""
        l10n = FluentLocalization(["en"], strict=True)
        l10n.add_resource("en", "hello = Hello\n")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            l10n.format_pattern(
                "hello", attribute=42  # type: ignore[arg-type]
            )

        err = exc_info.value
        assert len(err.fluent_errors) == 1
        ctx = err.context
        assert ctx is not None
        assert ctx.component == "localization"

    def test_non_strict_returns_fallback_on_invalid_args_type(self) -> None:
        """Non-strict mode returns fallback for invalid args type without raising."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "hello = Hello\n")

        _, errors = l10n.format_pattern("hello", "not-a-mapping")  # type: ignore[arg-type]
        assert len(errors) == 1

    def test_strict_non_strict_returns_fallback(self) -> None:
        """Non-strict mode returns fallback value without raising."""
        l10n = FluentLocalization(["en"], strict=False)

        result, errors = l10n.format_value("nonexistent")
        assert "nonexistent" in result
        assert len(errors) == 1

class TestResourceLoadingErrors:
    """Tests for error handling during resource loading."""

    def test_custom_loader_source_path_format(self) -> None:
        """Non-PathResourceLoader uses locale/resource_id format."""

        class DictLoader:
            def load(self, locale: str, _resource_id: str) -> str:
                return f"msg = Hello from {locale}\n"

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(
            ["en", "de"], ["main.ftl"], DictLoader(),
        )
        summary = l10n.get_load_summary()
        assert summary.total_attempted == 2
        for result in summary.results:
            assert result.source_path is not None
            assert "/" in result.source_path

    def test_oserror_recorded_as_error(self) -> None:
        """OSError during loading recorded with ERROR status."""

        class FailLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Permission denied"
                raise OSError(msg)

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(["en"], ["main.ftl"], FailLoader())
        summary = l10n.get_load_summary()
        assert summary.errors == 1
        assert isinstance(summary.get_errors()[0].error, OSError)

    def test_valueerror_recorded_as_error(self) -> None:
        """ValueError during loading recorded with ERROR status."""

        class FailLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Path traversal"
                raise ValueError(msg)

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(["en"], ["main.ftl"], FailLoader())
        summary = l10n.get_load_summary()
        assert summary.errors == 1
        assert isinstance(summary.get_errors()[0].error, ValueError)

    def test_file_not_found_recorded_as_not_found(self) -> None:
        """FileNotFoundError recorded as NOT_FOUND status."""

        class MissingLoader:
            def load(
                self, _locale: str, _resource_id: str,
            ) -> str:
                msg = "Not found"
                raise FileNotFoundError(msg)

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(["en"], ["main.ftl"], MissingLoader())
        summary = l10n.get_load_summary()
        assert summary.not_found == 1

    def test_get_load_summary_returns_summary(self) -> None:
        """get_load_summary returns LoadSummary from init phase."""
        l10n = FluentLocalization(["en"])
        summary = l10n.get_load_summary()
        assert isinstance(summary, LoadSummary)
        assert summary.total_attempted == 0  # No resource_ids provided

class TestBootValidation:
    """Tests for FluentLocalization boot-time validation helpers."""

    def test_require_clean_returns_summary_when_all_resources_are_clean(self) -> None:
        """require_clean returns the immutable load summary on success."""
        l10n = FluentLocalization(["en"])

        summary = l10n.require_clean()

        assert isinstance(summary, LoadSummary)
        assert summary.all_clean is True
        assert summary.total_attempted == 0

    def test_require_clean_raises_integrity_error_for_unclean_summary(self) -> None:
        """require_clean raises IntegrityCheckFailedError with structured context."""

        class MissingLoader:
            def load(self, _locale: str, _resource_id: str) -> str:
                msg = "missing"
                raise FileNotFoundError(msg)

            def describe_path(self, locale: str, resource_id: str) -> str:
                return f"{locale}/{resource_id}"

        l10n = FluentLocalization(["en"], ["main.ftl"], MissingLoader())

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.require_clean()

        err = exc_info.value
        assert "not clean" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.component == "localization"
        assert ctx.operation == "require_clean"
        assert ctx.key == "en/main.ftl"
        assert ctx.expected == "LoadSummary(all_clean=True)"

    def test_validate_message_schemas_returns_results_in_input_order(self) -> None:
        """validate_message_schemas returns immutable validation results on success."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource(
            "en",
            "first = Hello { $name }\n"
            "second = Balance { $amount }\n",
        )

        results = l10n.validate_message_schemas({
            "first": frozenset({"name"}),
            "second": frozenset({"amount"}),
        })

        assert [result.message_id for result in results] == ["first", "second"]
        assert all(result.is_valid for result in results)

    def test_validate_message_schemas_uses_fallback_chain(self) -> None:
        """Schema validation resolves messages from fallback locales."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "welcome = Hello { $name }\n")

        results = l10n.validate_message_schemas({
            "welcome": frozenset({"name"}),
        })

        assert len(results) == 1
        assert results[0].is_valid is True

    def test_validate_message_variables_returns_single_result(self) -> None:
        """Single-message boot validation returns the exact validation result."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "invoice = Total { $amount } for { $customer }\n")

        result = l10n.validate_message_variables(
            "invoice",
            frozenset({"amount", "customer"}),
        )

        assert result.message_id == "invoice"
        assert result.is_valid is True

    def test_validate_message_variables_uses_fallback_chain(self) -> None:
        """Single-message validation resolves through localization fallback."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("en", "welcome = Hello { $name }\n")

        result = l10n.validate_message_variables("welcome", frozenset({"name"}))

        assert result.message_id == "welcome"
        assert result.is_valid is True

    def test_validate_message_schemas_raises_for_missing_message(self) -> None:
        """Missing messages fail boot validation with an integrity exception."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "present = Hello\n")

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_schemas({"missing": frozenset()})

        err = exc_info.value
        assert "missing: not found" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.operation == "validate_message_schemas"
        assert ctx.key == "missing"
        assert ctx.actual == "missing_messages=1"

    def test_validate_message_variables_raises_for_missing_message(self) -> None:
        """Missing single-message validation raises IntegrityCheckFailedError."""
        l10n = FluentLocalization(["en"])

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_variables("missing", frozenset())

        err = exc_info.value
        assert "missing: not found" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.operation == "validate_message_variables"
        assert ctx.key == "missing"
        assert ctx.actual == "missing_messages=1"

    def test_validate_message_schemas_raises_for_exact_schema_mismatch(self) -> None:
        """Extra or missing variables fail exact boot schema validation."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "checkout = Total { $amount } for { $customer }\n")

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_schemas({
                "checkout": frozenset({"amount"}),
            })

        err = exc_info.value
        assert "checkout: extra {customer}" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.operation == "validate_message_schemas"
        assert ctx.key == "checkout"
        assert ctx.actual == "schema_mismatches=1"

    def test_validate_message_variables_raises_for_exact_schema_mismatch(self) -> None:
        """Single-message validation raises on exact-schema mismatch."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "checkout = Total { $amount } for { $customer }\n")

        with pytest.raises(IntegrityCheckFailedError) as exc_info:
            l10n.validate_message_variables("checkout", frozenset({"amount"}))

        err = exc_info.value
        assert "checkout: extra {customer}" in str(err)
        ctx = err.context
        assert ctx is not None
        assert ctx.operation == "validate_message_variables"
        assert ctx.key == "checkout"
        assert ctx.actual == "schema_mismatches=1"
