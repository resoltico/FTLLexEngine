"""Runtime and function error template mixins."""

from __future__ import annotations

from .codes import Diagnostic, DiagnosticCode
from .template_shared import docs_url


class _RuntimeErrorTemplateMixin:
    """ErrorTemplate methods for runtime evaluation and function failures."""

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
    def function_failed(function_name: str, error_msg: str) -> Diagnostic:
        """Function execution failed."""
        msg = f"Function '{function_name}' failed: {error_msg}"
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
        value: str,
        error_reason: str,
    ) -> Diagnostic:
        """Locale-aware formatting failed."""
        msg = f"{function_name}() formatting failed for value '{value}': {error_reason}"
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
        msg = (
            f"Function '{function_name}' expects {expected} argument(s), "
            f"got {received}"
        )
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

    @staticmethod
    def unknown_expression(expr_type: str) -> Diagnostic:
        """Unknown expression type encountered."""
        msg = f"Unknown expression type: {expr_type}"
        return Diagnostic(
            code=DiagnosticCode.UNKNOWN_EXPRESSION,
            message=msg,
            span=None,
            hint="This is likely a bug in the parser or resolver",
        )

    @staticmethod
    def unexpected_eof(position: int) -> Diagnostic:
        """Unexpected end of file."""
        msg = f"Unexpected EOF at position {position}"
        return Diagnostic(
            code=DiagnosticCode.UNEXPECTED_EOF,
            message=msg,
            span=None,
            hint="Check for unclosed braces or incomplete syntax",
        )
