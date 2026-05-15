"""Runtime diagnostics for function and formatting boundaries."""

from __future__ import annotations

from ._redaction import fingerprint_text
from .codes import Diagnostic, DiagnosticCode
from .template_shared import docs_url


class _RuntimeFunctionErrorTemplateMixin:
    """ErrorTemplate methods for function calls and format helpers."""

    @staticmethod
    def function_not_found(function_name: str) -> Diagnostic:
        """Function not found in registry."""
        msg = f"Function '{function_name}' not found"
        return Diagnostic(
            code=DiagnosticCode.FUNCTION_NOT_FOUND,
            message=msg,
            span=None,
            hint="Built-in functions: NUMBER, DATETIME, CURRENCY. Check spelling.",
            help_url=docs_url("functions.html"),
        )

    @staticmethod
    def function_failed(function_name: str, error_detail: str | None = None) -> Diagnostic:
        """Function execution failed.

        Premise:
            Custom functions may wrap downstream systems and secrets.

        Reason:
            The public diagnostic names the failing function and failure class
            without echoing exception payloads into logs or API responses.
        """
        detail = error_detail if error_detail is not None else "custom function execution failed"
        msg = f"Function '{function_name}' failed: {detail}"
        return Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message=msg,
            span=None,
            hint="Check the function arguments and their types",
            help_url=docs_url("functions.html"),
            function_name=function_name,
        )

    @staticmethod
    def formatting_failed(
        function_name: str,
        value: object,
        error_reason: object,
        *,
        safe_reason: str | None = None,
    ) -> Diagnostic:
        """Locale-aware formatting failed.

        Premise:
            Formatting helpers sit on the same trust boundary as parsing and
            custom-function execution, so raw values and downstream exception
            messages may contain user data or operational secrets.

        Reason:
            The diagnostic surfaces stable fingerprints rather than the raw
            payloads, preserving correlation value without turning error
            reporting into an exfiltration path. A caller may optionally attach
            one vetted high-level reason string when that improves usability
            without disclosing user input.
        """
        value_summary = fingerprint_text(value, label="format_value")
        reason_summary = fingerprint_text(error_reason, label="detail")
        reason_prefix = f"{safe_reason} " if safe_reason is not None else ""
        msg = (
            f"{function_name}() formatting failed for {value_summary}: "
            f"{reason_prefix}{reason_summary}"
        )
        return Diagnostic(
            code=DiagnosticCode.FORMATTING_FAILED,
            message=msg,
            span=None,
            hint="Check that the value is valid for the specified format options",
            help_url=docs_url("functions.html"),
            function_name=function_name,
        )

    @staticmethod
    def function_arity_mismatch(
        function_name: str,
        expected: int,
        received: int,
    ) -> Diagnostic:
        """Function called with wrong number of positional arguments."""
        msg = f"Function '{function_name}' expects {expected} argument(s), got {received}"
        return Diagnostic(
            code=DiagnosticCode.FUNCTION_ARITY_MISMATCH,
            message=msg,
            span=None,
            hint=f"Pass exactly {expected} value(s) to {function_name}()",
            help_url=docs_url("functions.html"),
            function_name=function_name,
        )

    @staticmethod
    def type_mismatch(
        function_name: str,
        argument_name: str,
        expected_type: str,
        received_type: str,
        *,
        ftl_location: str | None = None,
    ) -> Diagnostic:
        """Type mismatch in function argument."""
        msg = f"Type mismatch in {function_name}(): expected {expected_type}, got {received_type}"
        hint = f"Convert '{argument_name}' to {expected_type} before passing to {function_name}()"
        return Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message=msg,
            span=None,
            hint=hint,
            help_url=docs_url("functions.html"),
            function_name=function_name,
            argument_name=argument_name,
            expected_type=expected_type,
            received_type=received_type,
            ftl_location=ftl_location,
        )

    @staticmethod
    def invalid_argument(
        function_name: str,
        argument_name: str,
        reason: str,
        *,
        ftl_location: str | None = None,
    ) -> Diagnostic:
        """Invalid argument value."""
        msg = f"Invalid argument '{argument_name}' in {function_name}(): {reason}"
        return Diagnostic(
            code=DiagnosticCode.INVALID_ARGUMENT,
            message=msg,
            span=None,
            hint=f"Check the value of '{argument_name}' argument",
            help_url=docs_url("functions.html"),
            function_name=function_name,
            argument_name=argument_name,
            ftl_location=ftl_location,
        )

    @staticmethod
    def argument_required(
        function_name: str,
        argument_name: str,
        *,
        ftl_location: str | None = None,
    ) -> Diagnostic:
        """Required argument not provided."""
        msg = f"Required argument '{argument_name}' not provided for {function_name}()"
        return Diagnostic(
            code=DiagnosticCode.ARGUMENT_REQUIRED,
            message=msg,
            span=None,
            hint=f"Add '{argument_name}' argument to {function_name}() call",
            help_url=docs_url("functions.html"),
            function_name=function_name,
            argument_name=argument_name,
            ftl_location=ftl_location,
        )

    @staticmethod
    def pattern_invalid(
        function_name: str,
        pattern: str,
        reason: str,
        *,
        ftl_location: str | None = None,
    ) -> Diagnostic:
        """Invalid format pattern."""
        msg = f"Invalid pattern in {function_name}(): {reason}"
        return Diagnostic(
            code=DiagnosticCode.PATTERN_INVALID,
            message=msg,
            span=None,
            hint=f"Check pattern syntax: '{pattern}'",
            help_url=docs_url("functions.html"),
            function_name=function_name,
            argument_name="pattern",
            ftl_location=ftl_location,
            severity="error",
        )
