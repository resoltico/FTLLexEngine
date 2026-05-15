"""Parsing diagnostics for locale and non-currency value input."""

from __future__ import annotations

from ftllexengine.diagnostics._redaction import redacted_parse_failure

from .codes import Diagnostic, DiagnosticCode


class _ParsingInputErrorTemplateMixin:
    """ErrorTemplate methods for generic parsing failures."""

    @staticmethod
    def parse_decimal_failed(
        value: object,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Decimal parsing failed."""
        value_summary = redacted_parse_failure(value, parse_type="decimal")
        msg = f"Failed to parse decimal for locale '{locale_code}': {reason} ({value_summary})"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DECIMAL_FAILED,
            message=msg,
            span=None,
            hint="Check that the decimal format matches the locale's conventions",
        )

    @staticmethod
    def parse_date_failed(
        value: object,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Date parsing failed."""
        value_summary = redacted_parse_failure(value, parse_type="date")
        msg = f"Failed to parse date for locale '{locale_code}': {reason} ({value_summary})"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DATE_FAILED,
            message=msg,
            span=None,
            hint="Use ISO 8601 (YYYY-MM-DD) for unambiguous, locale-independent dates",
        )

    @staticmethod
    def parse_datetime_failed(
        value: object,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Datetime parsing failed."""
        value_summary = redacted_parse_failure(value, parse_type="datetime")
        msg = f"Failed to parse datetime for locale '{locale_code}': {reason} ({value_summary})"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DATETIME_FAILED,
            message=msg,
            span=None,
            hint="Use ISO 8601 (YYYY-MM-DD HH:MM:SS) for unambiguous, locale-independent datetimes",
        )

    @staticmethod
    def parse_locale_unknown(locale_code: str) -> Diagnostic:
        """Unknown locale for parsing."""
        msg = f"Unknown locale '{locale_code}'"
        return Diagnostic(
            code=DiagnosticCode.PARSE_LOCALE_UNKNOWN,
            message=msg,
            span=None,
            hint="Use BCP 47 locale codes (e.g., 'en_US', 'de_DE', 'lv_LV')",
        )
