"""Parsing and locale-input error template mixins."""

from __future__ import annotations

from .codes import Diagnostic, DiagnosticCode


class _ParsingErrorTemplateMixin:
    """ErrorTemplate methods for user-input parsing failures."""

    @staticmethod
    def parse_decimal_failed(
        value: str,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Decimal parsing failed."""
        msg = f"Failed to parse decimal '{value}' for locale '{locale_code}': {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DECIMAL_FAILED,
            message=msg,
            span=None,
            hint="Check that the decimal format matches the locale's conventions",
        )

    @staticmethod
    def parse_date_failed(
        value: str,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Date parsing failed."""
        msg = f"Failed to parse date '{value}' for locale '{locale_code}': {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DATE_FAILED,
            message=msg,
            span=None,
            hint="Use ISO 8601 (YYYY-MM-DD) for unambiguous, locale-independent dates",
        )

    @staticmethod
    def parse_datetime_failed(
        value: str,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Datetime parsing failed."""
        msg = f"Failed to parse datetime '{value}' for locale '{locale_code}': {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_DATETIME_FAILED,
            message=msg,
            span=None,
            hint="Use ISO 8601 (YYYY-MM-DD HH:MM:SS) for unambiguous, locale-independent datetimes",
        )

    @staticmethod
    def parse_currency_failed(
        value: str,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Currency parsing failed."""
        msg = f"Failed to parse currency '{value}' for locale '{locale_code}': {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_FAILED,
            message=msg,
            span=None,
            hint="Use ISO currency codes (USD, EUR, GBP) for unambiguous parsing",
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

    @staticmethod
    def parse_currency_ambiguous(
        symbol: str,
        value: str,
    ) -> Diagnostic:
        """Ambiguous currency symbol."""
        msg = (
            f"Ambiguous currency symbol '{symbol}' in '{value}'. "
            f"Symbol '{symbol}' is used by multiple currencies."
        )
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_AMBIGUOUS,
            message=msg,
            span=None,
            hint="Use default_currency parameter, infer_from_locale=True, or ISO code (USD, EUR)",
        )

    @staticmethod
    def parse_currency_symbol_unknown(
        symbol: str,
        value: str,
    ) -> Diagnostic:
        """Unknown currency symbol."""
        msg = f"Unknown currency symbol '{symbol}' in '{value}'"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN,
            message=msg,
            span=None,
            hint="Use ISO currency codes (USD, EUR, GBP) or supported symbols",
        )

    @staticmethod
    def parse_currency_code_invalid(
        code: str,
        value: str,
    ) -> Diagnostic:
        """Invalid ISO 4217 currency code."""
        msg = f"Invalid ISO 4217 currency code '{code}' in '{value}'"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_CODE_INVALID,
            message=msg,
            span=None,
            hint="Use valid ISO 4217 codes (USD, EUR, GBP, JPY, etc.)",
        )

    @staticmethod
    def parse_amount_invalid(
        amount_str: str,
        value: str,
        reason: str,
    ) -> Diagnostic:
        """Invalid amount in currency string."""
        msg = f"Failed to parse amount '{amount_str}' from '{value}': {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_AMOUNT_INVALID,
            message=msg,
            span=None,
            hint="Check that the amount format matches the locale's conventions",
        )
