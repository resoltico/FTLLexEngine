"""Reference and resolution error template mixins."""

from __future__ import annotations

from .codes import Diagnostic, DiagnosticCode
from .template_shared import docs_url


class _ReferenceErrorTemplateMixin:
    """ErrorTemplate methods for lookup, reference, and traversal failures."""

    @staticmethod
    def message_not_found(message_id: str) -> Diagnostic:
        """Message reference not found in bundle."""
        msg = f"Message '{message_id}' not found"
        return Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=msg,
            span=None,
            hint="Check that the message is defined in the loaded resources",
            help_url=docs_url("messages.html"),
        )

    @staticmethod
    def attribute_not_found(attribute: str, message_id: str) -> Diagnostic:
        """Message attribute not found."""
        msg = f"Attribute '{attribute}' not found in message '{message_id}'"
        return Diagnostic(
            code=DiagnosticCode.ATTRIBUTE_NOT_FOUND,
            message=msg,
            span=None,
            hint=f"Check that message '{message_id}' has an attribute '.{attribute}'",
            help_url=docs_url("attributes.html"),
        )

    @staticmethod
    def term_not_found(term_id: str) -> Diagnostic:
        """Term reference not found."""
        msg = f"Term '-{term_id}' not found"
        return Diagnostic(
            code=DiagnosticCode.TERM_NOT_FOUND,
            message=msg,
            span=None,
            hint="Terms must be defined before they are referenced",
            help_url=docs_url("terms.html"),
        )

    @staticmethod
    def term_attribute_not_found(attribute: str, term_id: str) -> Diagnostic:
        """Term attribute not found."""
        msg = f"Attribute '{attribute}' not found in term '-{term_id}'"
        return Diagnostic(
            code=DiagnosticCode.TERM_ATTRIBUTE_NOT_FOUND,
            message=msg,
            span=None,
            hint=f"Check that term '-{term_id}' has an attribute '.{attribute}'",
            help_url=docs_url("terms.html"),
        )

    @staticmethod
    def term_positional_args_ignored(term_name: str, count: int) -> Diagnostic:
        """Term positional arguments ignored."""
        plural = "argument" if count == 1 else "arguments"
        msg = (
            f"Term '-{term_name}' does not accept positional arguments "
            f"(got {count}). Use named arguments: -term(key: value)"
        )
        return Diagnostic(
            code=DiagnosticCode.TERM_POSITIONAL_ARGS_IGNORED,
            message=msg,
            span=None,
            hint=f"Remove the {count} positional {plural} and use named arguments instead",
            help_url=docs_url("terms.html"),
        )

    @staticmethod
    def plural_support_unavailable() -> Diagnostic:
        """Plural variant matching unavailable due to missing Babel dependency."""
        msg = (
            "Plural variant matching unavailable (Babel not installed). "
            "Install with: pip install ftllexengine[babel]"
        )
        return Diagnostic(
            code=DiagnosticCode.PLURAL_SUPPORT_UNAVAILABLE,
            message=msg,
            span=None,
            hint="Install Babel for CLDR-based plural category matching",
            help_url=docs_url("selectors.html"),
        )

    @staticmethod
    def variable_not_provided(
        variable_name: str,
        *,
        resolution_path: tuple[str, ...] | None = None,
    ) -> Diagnostic:
        """Variable not provided in arguments."""
        msg = f"Variable '${variable_name}' not provided"
        return Diagnostic(
            code=DiagnosticCode.VARIABLE_NOT_PROVIDED,
            message=msg,
            span=None,
            hint=f"Pass '{variable_name}' in the arguments dictionary",
            help_url=docs_url("variables.html"),
            resolution_path=resolution_path,
        )

    @staticmethod
    def message_no_value(message_id: str) -> Diagnostic:
        """Message has no value (only attributes)."""
        msg = f"Message '{message_id}' has no value"
        return Diagnostic(
            code=DiagnosticCode.MESSAGE_NO_VALUE,
            message=msg,
            span=None,
            hint="Message has only attributes; specify which attribute to format",
            help_url=docs_url("messages.html"),
        )

    @staticmethod
    def cyclic_reference(resolution_path: list[str]) -> Diagnostic:
        """Circular reference detected."""
        cycle_chain = " -> ".join(resolution_path)
        msg = f"Circular reference detected: {cycle_chain}"
        return Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message=msg,
            span=None,
            hint="Break the circular dependency by removing one of the references",
            help_url=docs_url("references.html"),
        )

    @staticmethod
    def max_depth_exceeded(message_id: str, max_depth: int) -> Diagnostic:
        """Maximum resolution depth exceeded."""
        msg = f"Maximum resolution depth ({max_depth}) exceeded while resolving '{message_id}'"
        return Diagnostic(
            code=DiagnosticCode.MAX_DEPTH_EXCEEDED,
            message=msg,
            span=None,
            hint="Reduce message reference chain depth or refactor to avoid deep nesting",
            help_url=docs_url("references.html"),
        )

    @staticmethod
    def depth_exceeded(max_depth: int) -> Diagnostic:
        """Maximum nesting depth exceeded."""
        msg = f"Maximum nesting depth ({max_depth}) exceeded"
        return Diagnostic(
            code=DiagnosticCode.MAX_DEPTH_EXCEEDED,
            message=msg,
            span=None,
            hint="Reduce nesting depth or check for malformed AST construction",
            help_url=docs_url("references.html"),
        )

    @staticmethod
    def expansion_budget_exceeded(total_chars: int, max_chars: int) -> Diagnostic:
        """Expansion budget exceeded during resolution."""
        msg = (
            f"Expansion budget exceeded: {total_chars} characters produced "
            f"(limit: {max_chars})"
        )
        return Diagnostic(
            code=DiagnosticCode.EXPANSION_BUDGET_EXCEEDED,
            message=msg,
            span=None,
            hint="Check for exponentially expanding message references (Billion Laughs pattern)",
            help_url=docs_url("references.html"),
        )

    @staticmethod
    def no_variants() -> Diagnostic:
        """Select expression has no variants."""
        msg = "No variants in select expression"
        return Diagnostic(
            code=DiagnosticCode.NO_VARIANTS,
            message=msg,
            span=None,
            hint="Select expressions must have at least one variant",
            help_url=docs_url("selectors.html"),
        )
