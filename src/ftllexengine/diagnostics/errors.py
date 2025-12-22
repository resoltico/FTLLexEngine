"""Fluent exception hierarchy with structured diagnostics.

Integrates with diagnostic codes for Rust/Elm-inspired error messages.
All exceptions store Diagnostic objects for rich error information.

Python 3.13+. Zero external dependencies.
"""

from .codes import Diagnostic


class FluentError(Exception):
    """Base exception for all Fluent errors.

    Attributes:
        diagnostic: Structured diagnostic information (optional)
    """

    def __init__(self, message: str | Diagnostic) -> None:
        """Initialize FluentError.

        Args:
            message: Error message string OR Diagnostic object
        """
        if isinstance(message, Diagnostic):
            self.diagnostic: Diagnostic | None = message
            super().__init__(message.format_error())
        else:
            self.diagnostic = None
            super().__init__(message)


class FluentSyntaxError(FluentError):
    """FTL syntax error during parsing.

    Parser continues after syntax errors (robustness principle).
    Errors become Junk entries in AST.
    """


class FluentReferenceError(FluentError):
    """Unknown message or term reference.

    Raised when resolving a message that references non-existent ID.
    Fallback: return message ID as string.
    """


class FluentResolutionError(FluentError):
    """Runtime error during message resolution.

    Examples:
    - Division by zero in expression
    - Type mismatch
    - Invalid function arguments

    Fallback: return partial result up to error point.
    """


class FluentCyclicReferenceError(FluentReferenceError):
    """Cyclic reference detected (message references itself).

    Example:
        hello = { hello }  ← Infinite loop!

    Fallback: return message ID.
    """


class FluentParseError(FluentError):
    """Error during bi-directional localization parsing.

    Raised when parsing locale-formatted strings (numbers, dates, currency)
    fails. Part of the unified error handling model aligned with format_*() API.

    instead of raising exceptions, consistent with formatting API.

    Attributes:
        input_value: The string that failed to parse
        locale_code: The locale used for parsing
        parse_type: Type of parsing attempted ('number', 'decimal', 'date', 'datetime', 'currency')

    Example:
        >>> result, errors = parse_number("invalid", "en_US")
        >>> if errors:
        ...     for error in errors:
        ...         print(f"Parse failed: {error.input_value} ({error.parse_type})")
    """

    def __init__(
        self,
        message: str | Diagnostic,
        *,
        input_value: str = "",
        locale_code: str = "",
        parse_type: str = "",
    ) -> None:
        """Initialize FluentParseError.

        Args:
            message: Error message string OR Diagnostic object
            input_value: The string that failed to parse
            locale_code: The locale used for parsing
            parse_type: Type of parsing ('number', 'decimal', 'date', 'datetime', 'currency')
        """
        super().__init__(message)
        self.input_value = input_value
        self.locale_code = locale_code
        self.parse_type = parse_type
