"""Integration tests for the diagnostics domain.

Tests the end-to-end pipeline:
    ErrorTemplate -> Diagnostic -> FrozenFluentError -> DiagnosticFormatter

Also contains regression tests for specific DiagnosticCode integer values,
which are part of the public contract for financial systems that log or
reference codes in runbooks and alerting configurations.

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    DiagnosticCode,
    DiagnosticFormatter,
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
    OutputFormat,
)

# ===========================================================================
# Regression: DiagnosticCode integer values (public API contract)
# These values appear in logs, runbooks, and alerting configs for financial
# systems. Changes here are BREAKING and require a major version bump.
# ===========================================================================


class TestReferenceCodeValues:
    """Regression: reference error codes (1000-1099) — breaking API contract."""

    def test_message_not_found_value(self) -> None:
        assert DiagnosticCode.MESSAGE_NOT_FOUND.value == 1001

    def test_attribute_not_found_value(self) -> None:
        assert DiagnosticCode.ATTRIBUTE_NOT_FOUND.value == 1002

    def test_term_not_found_value(self) -> None:
        assert DiagnosticCode.TERM_NOT_FOUND.value == 1003

    def test_term_attribute_not_found_value(self) -> None:
        assert DiagnosticCode.TERM_ATTRIBUTE_NOT_FOUND.value == 1004

    def test_variable_not_provided_value(self) -> None:
        assert DiagnosticCode.VARIABLE_NOT_PROVIDED.value == 1005

    def test_message_no_value_value(self) -> None:
        assert DiagnosticCode.MESSAGE_NO_VALUE.value == 1006


class TestResolutionCodeValues:
    """Regression: resolution error codes (2000-2999) — breaking API contract."""

    def test_cyclic_reference_value(self) -> None:
        assert DiagnosticCode.CYCLIC_REFERENCE.value == 2001

    def test_no_variants_value(self) -> None:
        assert DiagnosticCode.NO_VARIANTS.value == 2002

    def test_function_not_found_value(self) -> None:
        assert DiagnosticCode.FUNCTION_NOT_FOUND.value == 2003

    def test_function_failed_value(self) -> None:
        assert DiagnosticCode.FUNCTION_FAILED.value == 2004

    def test_unknown_expression_value(self) -> None:
        assert DiagnosticCode.UNKNOWN_EXPRESSION.value == 2005

    def test_type_mismatch_value(self) -> None:
        assert DiagnosticCode.TYPE_MISMATCH.value == 2006

    def test_invalid_argument_value(self) -> None:
        assert DiagnosticCode.INVALID_ARGUMENT.value == 2007

    def test_argument_required_value(self) -> None:
        assert DiagnosticCode.ARGUMENT_REQUIRED.value == 2008

    def test_pattern_invalid_value(self) -> None:
        assert DiagnosticCode.PATTERN_INVALID.value == 2009

    def test_max_depth_exceeded_value(self) -> None:
        assert DiagnosticCode.MAX_DEPTH_EXCEEDED.value == 2010

    def test_function_arity_mismatch_value(self) -> None:
        assert DiagnosticCode.FUNCTION_ARITY_MISMATCH.value == 2011

    def test_term_positional_args_ignored_value(self) -> None:
        assert DiagnosticCode.TERM_POSITIONAL_ARGS_IGNORED.value == 2012

    def test_plural_support_unavailable_value(self) -> None:
        assert DiagnosticCode.PLURAL_SUPPORT_UNAVAILABLE.value == 2013

    def test_formatting_failed_value(self) -> None:
        assert DiagnosticCode.FORMATTING_FAILED.value == 2014

    def test_expansion_budget_exceeded_value(self) -> None:
        assert DiagnosticCode.EXPANSION_BUDGET_EXCEEDED.value == 2015


class TestSyntaxCodeValues:
    """Regression: syntax error codes (3000-3999) — breaking API contract."""

    def test_unexpected_eof_value(self) -> None:
        assert DiagnosticCode.UNEXPECTED_EOF.value == 3001

    def test_parse_junk_value(self) -> None:
        assert DiagnosticCode.PARSE_JUNK.value == 3004

    def test_parse_nesting_depth_exceeded_value(self) -> None:
        assert DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.value == 3005


class TestParsingCodeValues:
    """Regression: parsing error codes (4000-4999) — breaking API contract."""

    def test_parse_number_failed_value(self) -> None:
        assert DiagnosticCode.PARSE_NUMBER_FAILED.value == 4001

    def test_parse_decimal_failed_value(self) -> None:
        assert DiagnosticCode.PARSE_DECIMAL_FAILED.value == 4002

    def test_parse_date_failed_value(self) -> None:
        assert DiagnosticCode.PARSE_DATE_FAILED.value == 4003

    def test_parse_datetime_failed_value(self) -> None:
        assert DiagnosticCode.PARSE_DATETIME_FAILED.value == 4004

    def test_parse_currency_failed_value(self) -> None:
        assert DiagnosticCode.PARSE_CURRENCY_FAILED.value == 4005

    def test_parse_locale_unknown_value(self) -> None:
        assert DiagnosticCode.PARSE_LOCALE_UNKNOWN.value == 4006

    def test_parse_currency_ambiguous_value(self) -> None:
        assert DiagnosticCode.PARSE_CURRENCY_AMBIGUOUS.value == 4007

    def test_parse_currency_symbol_unknown_value(self) -> None:
        assert DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN.value == 4008

    def test_parse_amount_invalid_value(self) -> None:
        assert DiagnosticCode.PARSE_AMOUNT_INVALID.value == 4009

    def test_parse_currency_code_invalid_value(self) -> None:
        assert DiagnosticCode.PARSE_CURRENCY_CODE_INVALID.value == 4010


class TestValidationCodeValues:
    """Regression: validation codes (5000-5199) — breaking API contract."""

    def test_validation_term_no_value_value(self) -> None:
        assert DiagnosticCode.VALIDATION_TERM_NO_VALUE.value == 5004

    def test_validation_select_no_default_value(self) -> None:
        assert DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT.value == 5005

    def test_validation_select_no_variants_value(self) -> None:
        assert DiagnosticCode.VALIDATION_SELECT_NO_VARIANTS.value == 5006

    def test_validation_variant_duplicate_value(self) -> None:
        assert DiagnosticCode.VALIDATION_VARIANT_DUPLICATE.value == 5007

    def test_validation_named_arg_duplicate_value(self) -> None:
        assert DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE.value == 5010

    def test_validation_parse_error_value(self) -> None:
        assert DiagnosticCode.VALIDATION_PARSE_ERROR.value == 5100

    def test_validation_critical_parse_error_value(self) -> None:
        assert DiagnosticCode.VALIDATION_CRITICAL_PARSE_ERROR.value == 5101

    def test_validation_duplicate_id_value(self) -> None:
        assert DiagnosticCode.VALIDATION_DUPLICATE_ID.value == 5102

    def test_validation_no_value_or_attrs_value(self) -> None:
        assert DiagnosticCode.VALIDATION_NO_VALUE_OR_ATTRS.value == 5103

    def test_validation_undefined_reference_value(self) -> None:
        assert DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.value == 5104

    def test_validation_circular_reference_value(self) -> None:
        assert DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.value == 5105

    def test_validation_chain_depth_exceeded_value(self) -> None:
        assert DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.value == 5106

    def test_validation_duplicate_attribute_value(self) -> None:
        assert DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.value == 5107

    def test_validation_shadow_warning_value(self) -> None:
        assert DiagnosticCode.VALIDATION_SHADOW_WARNING.value == 5108

    def test_validation_term_positional_args_value(self) -> None:
        assert DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS.value == 5109


# ===========================================================================
# Integration: ErrorTemplate -> Diagnostic -> formatted output
# ===========================================================================


class TestTemplateToDiagnosticPipeline:
    """End-to-end: template factory -> diagnostic -> formatted output."""

    def test_type_mismatch_full_pipeline(self) -> None:
        """type_mismatch template produces correctly-structured Rust output."""
        diag = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )
        formatted = diag.format_error()
        assert "error[TYPE_MISMATCH]" in formatted
        assert "= function: NUMBER" in formatted
        assert "= argument: value" in formatted
        assert "= expected: Number" in formatted
        assert "= received: String" in formatted
        assert "= help:" in formatted

    def test_type_mismatch_with_ftl_location(self) -> None:
        """ftl_location appears in formatted output when supplied."""
        diag = ErrorTemplate.type_mismatch(
            function_name="DATETIME",
            argument_name="date",
            expected_type="DateTime",
            received_type="String",
            ftl_location="ui.ftl:509",
        )
        formatted = diag.format_error()
        assert "ui.ftl:509" in formatted

    def test_all_formats_produce_code_name(self) -> None:
        """type_mismatch diagnostic formats correctly across all OutputFormats."""
        diag = ErrorTemplate.type_mismatch("NUMBER", "val", "Number", "String")
        for fmt in OutputFormat:
            formatter = DiagnosticFormatter(output_format=fmt)
            result = formatter.format(diag)
            assert "TYPE_MISMATCH" in result

    def test_function_failed_pipeline(self) -> None:
        """function_failed template integrates into FrozenFluentError correctly."""
        diag = ErrorTemplate.function_failed("NUMBER", "domain error")
        err = FrozenFluentError(diag.message, ErrorCategory.RESOLUTION, diagnostic=diag)
        assert err.category == ErrorCategory.RESOLUTION
        assert err.diagnostic is not None
        assert err.diagnostic.function_name == "NUMBER"
        assert err.verify_integrity()

    def test_cyclic_reference_pipeline(self) -> None:
        """cyclic_reference template produces FrozenFluentError with CYCLIC category."""
        path = ["msg-a", "msg-b", "msg-a"]
        diag = ErrorTemplate.cyclic_reference(path)
        err = FrozenFluentError(diag.message, ErrorCategory.CYCLIC, diagnostic=diag)
        assert err.category == ErrorCategory.CYCLIC
        assert err.verify_integrity()
        formatted = diag.format_error()
        assert "CYCLIC_REFERENCE" in formatted

    @given(
        fn=st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]),
        arg=st.from_regex(r"[a-z][a-z]{0,9}", fullmatch=True),
        expected=st.text(min_size=1, max_size=30),
        received=st.text(min_size=1, max_size=30),
    )
    def test_type_mismatch_to_frozen_error_roundtrip(
        self, fn: str, arg: str, expected: str, received: str
    ) -> None:
        """PROPERTY: type_mismatch -> FrozenFluentError -> verify_integrity."""
        diag = ErrorTemplate.type_mismatch(fn, arg, expected, received)
        err = FrozenFluentError(diag.message, ErrorCategory.RESOLUTION, diagnostic=diag)
        assert err.verify_integrity()
        assert err.diagnostic is diag
        assert err.category == ErrorCategory.RESOLUTION
        event(f"fn={fn}")


# ===========================================================================
# Integration: FrozenFluentError in exception handling
# ===========================================================================


class TestFrozenFluentErrorExceptionIntegration:
    """FrozenFluentError used as a live exception in try/except blocks."""

    def test_diagnostic_accessible_after_catch(self) -> None:
        """Diagnostic is accessible on caught FrozenFluentError."""
        diag = ErrorTemplate.message_not_found("greeting")
        with pytest.raises(FrozenFluentError) as exc_info:
            raise FrozenFluentError(diag.message, ErrorCategory.REFERENCE, diagnostic=diag)
        assert exc_info.value.diagnostic is not None
        assert exc_info.value.diagnostic.code == DiagnosticCode.MESSAGE_NOT_FOUND

    def test_category_accessible_after_catch(self) -> None:
        """Category is accessible on caught FrozenFluentError."""
        msg = "not found"
        with pytest.raises(FrozenFluentError) as exc_info:
            raise FrozenFluentError(msg, ErrorCategory.REFERENCE)
        assert exc_info.value.category == ErrorCategory.REFERENCE

    def test_integrity_preserved_through_exception_chain(self) -> None:
        """verify_integrity() passes on a re-raised / chained exception."""
        original_msg = "original"
        wrapper_msg = "wrapper"
        original = FrozenFluentError(original_msg, ErrorCategory.RESOLUTION)
        wrapper: FrozenFluentError | None = None
        try:
            try:
                raise original
            except FrozenFluentError as inner:
                raise FrozenFluentError(wrapper_msg, ErrorCategory.RESOLUTION) from inner
        except FrozenFluentError as final:
            wrapper = final

        assert wrapper is not None
        assert wrapper.verify_integrity()
        cause = wrapper.__cause__
        assert isinstance(cause, FrozenFluentError)
        # isinstance narrows at runtime; Pylint does not track this narrowing.
        assert cause.verify_integrity()  # pylint: disable=no-member
