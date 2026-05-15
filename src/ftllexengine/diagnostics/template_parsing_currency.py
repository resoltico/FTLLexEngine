"""Parsing diagnostics for currency-specific failures."""

from __future__ import annotations

from ftllexengine.diagnostics._redaction import fingerprint_text, redacted_parse_failure

from .codes import Diagnostic, DiagnosticCode


class _ParsingCurrencyErrorTemplateMixin:
    """ErrorTemplate methods for currency parsing failures."""

    @staticmethod
    def parse_currency_failed(
        value: object,
        locale_code: str,
        reason: str,
    ) -> Diagnostic:
        """Currency parsing failed."""
        value_summary = redacted_parse_failure(value, parse_type="currency")
        msg = f"Failed to parse currency for locale '{locale_code}': {reason} ({value_summary})"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_FAILED,
            message=msg,
            span=None,
            hint="Use ISO currency codes (USD, EUR, GBP) for unambiguous parsing",
        )

    @staticmethod
    def parse_currency_ambiguous(
        symbol: object,
        value: object,
    ) -> Diagnostic:
        """Ambiguous currency symbol."""
        value_summary = redacted_parse_failure(value, parse_type="currency")
        symbol_summary = fingerprint_text(symbol, label="currency_symbol")
        msg = (
            f"Ambiguous currency symbol in {value_summary}. "
            f"Symbol {symbol_summary} is used by multiple currencies."
        )
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_AMBIGUOUS,
            message=msg,
            span=None,
            hint="Use default_currency parameter, infer_from_locale=True, or ISO code (USD, EUR)",
        )

    @staticmethod
    def parse_currency_symbol_unknown(
        symbol: object,
        value: object,
    ) -> Diagnostic:
        """Unknown currency symbol."""
        value_summary = redacted_parse_failure(value, parse_type="currency")
        symbol_summary = fingerprint_text(symbol, label="currency_symbol")
        msg = f"Unknown currency symbol {symbol_summary} in {value_summary}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN,
            message=msg,
            span=None,
            hint="Use ISO currency codes (USD, EUR, GBP) or supported symbols",
        )

    @staticmethod
    def parse_currency_code_invalid(
        code: object,
        value: object,
    ) -> Diagnostic:
        """Invalid ISO 4217 currency code."""
        value_summary = redacted_parse_failure(value, parse_type="currency")
        code_summary = fingerprint_text(code, label="currency_code")
        msg = f"Invalid ISO 4217 currency code {code_summary} in {value_summary}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_CURRENCY_CODE_INVALID,
            message=msg,
            span=None,
            hint="Use valid ISO 4217 codes (USD, EUR, GBP, JPY, etc.)",
        )

    @staticmethod
    def parse_amount_invalid(
        amount_str: object,
        value: object,
        reason: str,
    ) -> Diagnostic:
        """Invalid amount in currency string."""
        value_summary = redacted_parse_failure(value, parse_type="currency")
        amount_summary = fingerprint_text(amount_str, label="amount_fragment")
        msg = f"Failed to parse amount {amount_summary} from {value_summary}: {reason}"
        return Diagnostic(
            code=DiagnosticCode.PARSE_AMOUNT_INVALID,
            message=msg,
            span=None,
            hint="Check that the amount format matches the locale's conventions",
        )
