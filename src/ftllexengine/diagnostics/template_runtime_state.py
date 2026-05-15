"""Runtime diagnostics for resolver and runtime-state failures."""

from __future__ import annotations

from .codes import Diagnostic, DiagnosticCode
from .template_shared import docs_url


class _RuntimeStateErrorTemplateMixin:
    """ErrorTemplate methods for runtime-state and resolver failures."""

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

    @staticmethod
    def reentrant_formatting_blocked() -> Diagnostic:
        """Cross-thread bundle re-entry from a custom function was rejected."""
        msg = "Cross-thread format_pattern() re-entry from a custom function is blocked"
        return Diagnostic(
            code=DiagnosticCode.REENTRANT_FORMATTING_BLOCKED,
            message=msg,
            span=None,
            hint=(
                "Resolve nested formatting in the current call stack or return data "
                "to the caller instead of invoking the bundle from a new thread"
            ),
            help_url=docs_url("functions.html"),
        )
