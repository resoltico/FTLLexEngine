"""Diagnostic codes and data structures.

Defines error codes, source spans, and diagnostic messages.
Python 3.13+. Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Literal

__all__ = [
    "Diagnostic",
    "DiagnosticCode",
    "ErrorCategory",
    "FrozenErrorContext",
    "SourceSpan",
]


class ErrorCategory(StrEnum):
    """Error categorization for FrozenFluentError.

    Inherits from ``StrEnum`` so that ``str(category)`` and direct string
    comparisons work without accessing ``.value``; serialization and log
    aggregation receive plain strings (``"reference"``, ``"resolution"``,
    etc.) rather than the ``"ErrorCategory.X"`` repr that a plain ``Enum``
    would produce. The ``.value`` attribute is still the canonical string.

    Categories:
        REFERENCE: Unknown message, term, or variable reference
        RESOLUTION: Runtime resolution failure (type mismatch, function error)
        CYCLIC: Cyclic reference detected in message resolution
        PARSE: Bi-directional parsing failure (number, date, currency parsing)
        FORMATTING: Locale-aware formatting failure (NUMBER, DATETIME, CURRENCY)
    """

    REFERENCE = "reference"
    RESOLUTION = "resolution"
    CYCLIC = "cyclic"
    PARSE = "parse"
    FORMATTING = "formatting"


@dataclass(frozen=True, slots=True)
class FrozenErrorContext:
    """Immutable context for parse/formatting errors.

    Carries additional information about the error context without
    making the error object mutable.

    Attributes:
        input_value: String that failed to parse (empty if not applicable)
        locale_code: Locale used for parsing/formatting (empty if not applicable)
        parse_type: Type of parsing attempted (number, date, currency)
        fallback_value: Value to use in output when formatting fails
    """

    input_value: str = ""
    locale_code: str = ""
    parse_type: str = ""
    fallback_value: str = ""


class DiagnosticCode(Enum):
    """Error codes with unique identifiers.

    Organized by category:
        1000-1999: Reference errors (missing messages, terms, variables)
        2000-2999: Resolution errors (runtime evaluation failures)
        3000-3999: Syntax errors (parser failures)
        4000-4999: Parsing errors (bi-directional localization)
        5000-5099: Validation errors (Fluent spec semantic validation)
        5100-5199: Validation warnings (resource-level structural checks)
    """

    # Reference errors (1000-1999)
    MESSAGE_NOT_FOUND = 1001
    ATTRIBUTE_NOT_FOUND = 1002
    TERM_NOT_FOUND = 1003
    TERM_ATTRIBUTE_NOT_FOUND = 1004
    VARIABLE_NOT_PROVIDED = 1005
    MESSAGE_NO_VALUE = 1006

    # Resolution errors (2000-2999)
    CYCLIC_REFERENCE = 2001
    NO_VARIANTS = 2002
    FUNCTION_NOT_FOUND = 2003
    FUNCTION_FAILED = 2004
    UNKNOWN_EXPRESSION = 2005
    TYPE_MISMATCH = 2006
    INVALID_ARGUMENT = 2007
    ARGUMENT_REQUIRED = 2008
    PATTERN_INVALID = 2009
    MAX_DEPTH_EXCEEDED = 2010
    FUNCTION_ARITY_MISMATCH = 2011
    TERM_POSITIONAL_ARGS_IGNORED = 2012
    PLURAL_SUPPORT_UNAVAILABLE = 2013
    FORMATTING_FAILED = 2014
    EXPANSION_BUDGET_EXCEEDED = 2015

    # Syntax errors (3000-3999)
    # 3001: UNEXPECTED_EOF - parser cursor signals early end of input
    # 3002, 3003: not assigned - character-level and token-level errors
    #             are reported via Annotation codes in the AST, not
    #             DiagnosticCode, because they carry structural arguments
    #             (found/expected token pairs) that do not map to flat codes.
    UNEXPECTED_EOF = 3001
    PARSE_JUNK = 3004      # Generic parse error for Junk AST entries
    PARSE_NESTING_DEPTH_EXCEEDED = 3005  # Nesting depth limit exceeded

    # Parsing errors (4000-4999) - Bi-directional localization
    PARSE_DECIMAL_FAILED = 4002
    PARSE_DATE_FAILED = 4003
    PARSE_DATETIME_FAILED = 4004
    PARSE_CURRENCY_FAILED = 4005
    PARSE_LOCALE_UNKNOWN = 4006
    PARSE_CURRENCY_AMBIGUOUS = 4007
    PARSE_CURRENCY_SYMBOL_UNKNOWN = 4008
    PARSE_AMOUNT_INVALID = 4009
    PARSE_CURRENCY_CODE_INVALID = 4010

    # Validation errors (5000-5099) - Fluent spec semantic validation
    # Codes 5001-5003: E0001 (call-args on attribute reference),
    #     E0002 (positional args on attribute reference),
    #     E0003 (attribute access on term value) - handled by the parser as
    #     parse-time syntax errors (Junk), not as post-parse validation codes.
    # Codes 5008-5009: E0008 (unresolved variable), E0009 (missing default)
    #     are represented at runtime via VARIABLE_NOT_PROVIDED (1005) and
    #     NO_VARIANTS (2002) respectively.
    # Codes 5011-5013: E0011-E0013 are not defined by the Fluent spec
    #     valid.md as of the current implementation revision.
    VALIDATION_TERM_NO_VALUE = 5004
    VALIDATION_SELECT_NO_DEFAULT = 5005
    VALIDATION_SELECT_NO_VARIANTS = 5006
    VALIDATION_VARIANT_DUPLICATE = 5007
    VALIDATION_NAMED_ARG_DUPLICATE = 5010

    # Validation warnings (5100-5199) - Resource-level validation
    # These are structural checks beyond Fluent spec requirements
    VALIDATION_PARSE_ERROR = 5100
    VALIDATION_CRITICAL_PARSE_ERROR = 5101
    VALIDATION_DUPLICATE_ID = 5102
    VALIDATION_NO_VALUE_OR_ATTRS = 5103
    VALIDATION_UNDEFINED_REFERENCE = 5104
    VALIDATION_CIRCULAR_REFERENCE = 5105
    VALIDATION_CHAIN_DEPTH_EXCEEDED = 5106
    VALIDATION_DUPLICATE_ATTRIBUTE = 5107
    VALIDATION_SHADOW_WARNING = 5108
    VALIDATION_TERM_POSITIONAL_ARGS = 5109


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Source code location for error reporting.

    Note:
        Python strings measure positions in characters (Unicode code points),
        not bytes. For multi-byte UTF-8 characters, character offset differs
        from byte offset.

    Attributes:
        start: Starting character offset (0-indexed)
        end: Ending character offset (exclusive)
        line: Line number (1-indexed)
        column: Column number (1-indexed)
    """

    start: int
    end: int
    line: int
    column: int

    def __post_init__(self) -> None:
        """Validate SourceSpan invariants.

        Raises:
            ValueError: If start is negative, end precedes start, line is
                less than 1 (lines are 1-indexed), or column is less than 1
                (columns are 1-indexed).
        """
        if self.start < 0:
            msg = f"SourceSpan.start must be >= 0, got {self.start}"
            raise ValueError(msg)
        if self.end < self.start:
            msg = f"SourceSpan.end ({self.end}) must be >= start ({self.start})"
            raise ValueError(msg)
        if self.line < 1:
            msg = f"SourceSpan.line must be >= 1 (1-indexed), got {self.line}"
            raise ValueError(msg)
        if self.column < 1:
            msg = f"SourceSpan.column must be >= 1 (1-indexed), got {self.column}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Structured diagnostic message.

    Inspired by Rust compiler diagnostics. Provides rich error information
    for both humans and tools (IDEs, LSP servers).

    Attributes:
        code: Unique error code
        message: Human-readable error description
        span: Source location (None for non-syntax errors)
        hint: Suggestion for fixing the error
        help_url: Documentation URL for this error
        function_name: Function name where error occurred (format errors)
        argument_name: Argument name that caused error (format errors)
        expected_type: Expected type for argument (format errors)
        received_type: Actual type received (format errors)
        ftl_location: FTL file location (format errors)
        severity: Error severity level
        resolution_path: Resolution stack at time of error (for debugging nested references)
    """

    code: DiagnosticCode
    message: str
    span: SourceSpan | None = None
    hint: str | None = None
    help_url: str | None = None
    function_name: str | None = None
    argument_name: str | None = None
    expected_type: str | None = None
    received_type: str | None = None
    ftl_location: str | None = None
    severity: Literal["error", "warning"] = "error"
    resolution_path: tuple[str, ...] | None = None

    def __str__(self) -> str:
        """Return human-readable error description."""
        return self.message

    def format_error(self) -> str:
        """Format diagnostic like Rust compiler.

        Delegates to DiagnosticFormatter for consistent output with
        control-character escaping (log injection prevention).

        Example output:
            error[MESSAGE_NOT_FOUND]: Message 'hello' not found
              --> line 5, column 10
              = help: Check that the message is defined in the loaded resources
              = note: see https://projectfluent.org/fluent/guide/messages.html

        Example with format context:
            error[TYPE_MISMATCH]: Invalid argument type for NUMBER() function
              --> ui.ftl:509
              = function: NUMBER
              = argument: value
              = expected: Number
              = received: String
              = help: Convert the string to a number first

        Returns:
            Formatted error message
        """
        from .formatter import DiagnosticFormatter  # noqa: PLC0415 - circular

        return DiagnosticFormatter().format(self)
