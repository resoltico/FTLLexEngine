"""Primitive parsing utilities for Fluent FTL parser.

This module provides low-level parsers for identifiers, numbers,
and string literals per the Fluent specification.

Error Context:
    Functions store error context on failure via _set_parse_error().
    Retrieve with get_last_parse_error() for detailed diagnostics.

Thread-Local State (Architectural Decision):
    This module uses thread-local storage for parse error context rather than
    explicit parameter passing. This design choice prioritizes performance for
    high-frequency operations:

    Performance Rationale:
    - Primitive functions (parse_identifier, parse_number, parse_string_literal)
      are called 100+ times per parse operation
    - Explicit context threading would require ~10 signature changes and
      200+ call site updates throughout the parser
    - Parameter marshaling overhead on the hot path degrades microsecond-scale
      primitive operations
    - Thread-local approach reduces 200-line primitives from growing to 300+ lines

    Trade-off Analysis:
    - Parser operations are synchronous and single-threaded per parse call
    - Error context only needed for the most recent primitive failure
    - Each thread maintains independent state (no cross-thread conflicts)
    - Context lifetime is scoped to single parse operation
    - Caller controls cleanup via clear_parse_error() before each parse

    Thread Safety:
    For async frameworks that reuse threads across parse operations, the caller
    MUST call clear_parse_error() before each parse to prevent error context
    leakage between operations.

    This is a permanent architectural pattern where performance benefits of
    implicit state outweigh the cost of reduced explicitness for this specific
    high-frequency primitive layer.
"""

from dataclasses import dataclass
from threading import local as thread_local

from ftllexengine.constants import (
    _MAX_IDENTIFIER_LENGTH,
    _MAX_NUMBER_LENGTH,
    _MAX_STRING_LITERAL_LENGTH,
)
from ftllexengine.core.identifier_validation import (
    is_identifier_char,
    is_identifier_start,
)
from ftllexengine.syntax.cursor import Cursor, ParseResult

__all__ = [
    "_ASCII_DIGITS",
    "clear_parse_error",
    "get_last_parse_error",
    "is_identifier_char",
    "is_identifier_start",
    "parse_identifier",
    "parse_number",
    "parse_number_value",
    "parse_string_literal",
]

# Unicode escape sequence constants per Unicode Standard.
# \uXXXX = 4 hex digits (BMP characters U+0000 to U+FFFF)
_UNICODE_ESCAPE_LEN_SHORT: int = 4

# \UXXXXXX = 6 hex digits (full Unicode range U+0000 to U+10FFFF)
_UNICODE_ESCAPE_LEN_LONG: int = 6

# Maximum valid Unicode code point per Unicode Standard.
# Code points above U+10FFFF are invalid in UTF-8/UTF-16/UTF-32.
_MAX_UNICODE_CODE_POINT: int = 0x10FFFF

# UTF-16 surrogate code point range (D800-DFFF).
# These are invalid in isolation and must be rejected in UTF-8/32.
_SURROGATE_RANGE_START: int = 0xD800
_SURROGATE_RANGE_END: int = 0xDFFF

# Valid hexadecimal digit characters for Unicode escape parsing.
_HEX_DIGITS: str = "0123456789abcdefABCDEF"

# ASCII digits only - FTL spec requires 0-9, not Unicode digits like ² or ³.
# str.isdigit() returns True for Unicode digits which causes int() to fail.
_ASCII_DIGITS: str = "0123456789"

# Token length limits imported from ftllexengine.constants:
# _MAX_IDENTIFIER_LENGTH, _MAX_NUMBER_LENGTH, _MAX_STRING_LITERAL_LENGTH
# See constants.py for documentation on these DoS prevention limits.

# Identifier validation functions imported from ftllexengine.core.identifier_validation:
# is_identifier_start, is_identifier_char
# See identifier_validation.py for the unified source of truth for FTL identifier grammar.

# Thread-local storage for parse error context
_error_thread_local = thread_local()


@dataclass(frozen=True, slots=True)
class ParseErrorContext:
    """Context information for parse failures.

    Provides detailed error information when primitive parsing fails.
    Retrieve via get_last_parse_error() after a parser returns None.

    Attributes:
        message: Human-readable error description
        position: Character position in source where error occurred
        expected: What the parser expected to find (optional)
    """

    message: str
    position: int
    expected: tuple[str, ...] = ()


def _set_parse_error(
    message: str, position: int, expected: tuple[str, ...] = ()
) -> None:
    """Store parse error context for later retrieval."""
    _error_thread_local.last_error = ParseErrorContext(
        message=message, position=position, expected=expected
    )


def get_last_parse_error() -> ParseErrorContext | None:
    """Get the last parse error context (if any).

    Returns:
        ParseErrorContext with details, or None if no error recorded

    Example:
        >>> result = parse_identifier(cursor)
        >>> if result is None:
        ...     error = get_last_parse_error()
        ...     print(f"Error at position {error.position}: {error.message}")
    """
    return getattr(_error_thread_local, "last_error", None)


def clear_parse_error() -> None:
    """Clear the last parse error context."""
    _error_thread_local.last_error = None


def parse_identifier(cursor: Cursor) -> ParseResult[str] | None:
    """Parse identifier: [a-zA-Z][a-zA-Z0-9_-]*

    Fluent identifiers start with an ASCII letter and continue with ASCII
    letters, ASCII digits, hyphens, or underscores. Per Fluent specification,
    only ASCII characters are valid in identifiers for cross-implementation
    compatibility.

    Examples:
        hello → "hello"
        brand-name → "brand-name"
        file_name → "file_name"

    Note:
        Unicode letters (é, ñ, µ) are rejected to maintain compatibility
        with JavaScript and Rust Fluent implementations.

    Args:
        cursor: Current position in source

    Returns:
        Success(ParseResult(identifier, new_cursor)) on success
        Failure(ParseError(...)) if not an identifier
    """
    # Clear any stale error context from previous parse attempts
    clear_parse_error()

    # Check first character is ASCII alpha (a-z, A-Z only)
    if cursor.is_eof or not is_identifier_start(cursor.current):
        _set_parse_error(
            "Expected identifier (must start with ASCII letter a-z or A-Z)",
            cursor.pos,
            ("a-z", "A-Z"),
        )
        return None

    # Save start position
    start_pos = cursor.pos
    cursor = cursor.advance()  # Skip first character

    # Continue with ASCII alphanumeric, -, _
    # Limit length to prevent DoS via extremely long identifiers
    while not cursor.is_eof:
        ch = cursor.current
        if is_identifier_char(ch):
            cursor = cursor.advance()
            # Check length limit after consuming character
            current_length = cursor.pos - start_pos
            if current_length > _MAX_IDENTIFIER_LENGTH:
                _set_parse_error(
                    f"Identifier exceeds maximum length ({_MAX_IDENTIFIER_LENGTH} chars)",
                    cursor.pos,
                )
                return None
        else:
            break

    # Extract identifier
    identifier = Cursor(cursor.source, start_pos).slice_to(cursor.pos)
    return ParseResult(identifier, cursor)


def parse_number_value(num_str: str) -> int | float:
    """Parse number string to int or float.


    Args:
        num_str: Number string from parse_number

    Returns:
        int if no decimal point, float otherwise
    """
    return int(num_str) if "." not in num_str else float(num_str)


def parse_number(cursor: Cursor) -> ParseResult[str] | None:
    """Parse number literal: -?[0-9]+(.[0-9]+)?

    Returns the raw string representation. Use parse_number_value()
    to convert to int or float for NumberLiteral construction.

    Examples:
        42 → "42"
        -3.14 → "-3.14"
        0.001 → "0.001"

    Args:
        cursor: Current position in source

    Returns:
        Success(ParseResult(number_str, new_cursor)) on success
        Failure(ParseError(...)) if not a number
    """
    # Clear any stale error context from previous parse attempts
    clear_parse_error()

    start_pos = cursor.pos

    # Optional minus sign
    if not cursor.is_eof and cursor.current == "-":
        cursor = cursor.advance()

    # Must have at least one ASCII digit (0-9, not Unicode digits like ²)
    if cursor.is_eof or cursor.current not in _ASCII_DIGITS:
        _set_parse_error("Expected number", cursor.pos, ("0-9",))
        return None

    # Integer part - with length limit to prevent DoS
    while not cursor.is_eof and cursor.current in _ASCII_DIGITS:
        cursor = cursor.advance()
        # Check length limit after consuming digit
        if cursor.pos - start_pos > _MAX_NUMBER_LENGTH:
            _set_parse_error(
                f"Number exceeds maximum length ({_MAX_NUMBER_LENGTH} chars)",
                cursor.pos,
            )
            return None

    # Optional decimal part
    if not cursor.is_eof and cursor.current == ".":
        cursor = cursor.advance()

        # Must have digit after decimal
        if cursor.is_eof or cursor.current not in _ASCII_DIGITS:
            _set_parse_error("Expected digit after decimal point", cursor.pos, ("0-9",))
            return None

        # Decimal digits - continue length check
        while not cursor.is_eof and cursor.current in _ASCII_DIGITS:
            cursor = cursor.advance()
            if cursor.pos - start_pos > _MAX_NUMBER_LENGTH:
                _set_parse_error(
                    f"Number exceeds maximum length ({_MAX_NUMBER_LENGTH} chars)",
                    cursor.pos,
                )
                return None

    # Extract number string
    number_str = Cursor(cursor.source, start_pos).slice_to(cursor.pos)
    return ParseResult(number_str, cursor)


def parse_escape_sequence(cursor: Cursor) -> tuple[str, Cursor] | None:  # noqa: PLR0911
    """Parse escape sequence after backslash in string.

    Helper method extracted from parse_string_literal to reduce complexity.

    Supported escape sequences:
        \\" → "
        \\\\ → \\
        \\n → newline
        \\t → tab
        \\uXXXX → Unicode character (4 hex digits)
        \\UXXXXXX → Unicode character (6 hex digits)

    Note: PLR0911 (too many returns) is acceptable for parser grammar methods.
    Each return represents a successfully parsed grammar alternative.

    Args:
        cursor: Position AFTER the backslash

    Returns:
        Success((escaped_char, new_cursor)) on success
        Failure(ParseError(...)) on invalid escape
    """
    if cursor.is_eof:
        _set_parse_error("Unexpected EOF in escape sequence", cursor.pos)
        return None

    escape_ch = cursor.current

    if escape_ch == '"':
        return ('"', cursor.advance())
    if escape_ch == "\\":
        return ("\\", cursor.advance())
    if escape_ch == "n":
        return ("\n", cursor.advance())
    if escape_ch == "t":
        return ("\t", cursor.advance())

    if escape_ch == "u":
        # Unicode escape: \uXXXX (4 hex digits for BMP)
        cursor = cursor.advance()
        # Use slice_ahead for O(1) extraction instead of character-by-character loop
        hex_digits = cursor.slice_ahead(_UNICODE_ESCAPE_LEN_SHORT)
        if len(hex_digits) < _UNICODE_ESCAPE_LEN_SHORT or not all(
            c in _HEX_DIGITS for c in hex_digits
        ):
            _set_parse_error(
                f"Invalid Unicode escape (expected {_UNICODE_ESCAPE_LEN_SHORT} hex digits)",
                cursor.pos,
                ("0-9", "a-f", "A-F"),
            )
            return None
        cursor = cursor.advance(_UNICODE_ESCAPE_LEN_SHORT)

        # Convert to character
        code_point = int(hex_digits, 16)
        # Reject UTF-16 surrogate code points (invalid in UTF-8)
        # Per Unicode Standard: D800-DFFF are surrogates, invalid in isolation
        if _SURROGATE_RANGE_START <= code_point <= _SURROGATE_RANGE_END:
            _set_parse_error(
                f"Invalid surrogate code point: U+{hex_digits} (surrogates not allowed)",
                cursor.pos,
            )
            return None
        return (chr(code_point), cursor)

    if escape_ch == "U":
        # Unicode escape: \UXXXXXX (6 hex digits for full Unicode range)
        cursor = cursor.advance()
        # Use slice_ahead for O(1) extraction instead of character-by-character loop
        hex_digits = cursor.slice_ahead(_UNICODE_ESCAPE_LEN_LONG)
        if len(hex_digits) < _UNICODE_ESCAPE_LEN_LONG or not all(
            c in _HEX_DIGITS for c in hex_digits
        ):
            _set_parse_error(
                f"Invalid Unicode escape (expected {_UNICODE_ESCAPE_LEN_LONG} hex digits)",
                cursor.pos,
                ("0-9", "a-f", "A-F"),
            )
            return None
        cursor = cursor.advance(_UNICODE_ESCAPE_LEN_LONG)

        # Convert to character
        code_point = int(hex_digits, 16)
        # Validate Unicode code point range
        if code_point > _MAX_UNICODE_CODE_POINT:
            _set_parse_error(
                f"Invalid Unicode code point: U+{hex_digits} (max U+10FFFF)",
                cursor.pos,
            )
            return None
        # Reject UTF-16 surrogate code points (invalid in UTF-8)
        if _SURROGATE_RANGE_START <= code_point <= _SURROGATE_RANGE_END:
            _set_parse_error(
                f"Invalid surrogate code point: U+{hex_digits} (surrogates not allowed)",
                cursor.pos,
            )
            return None
        return (chr(code_point), cursor)

    _set_parse_error(f"Invalid escape sequence: \\{escape_ch}", cursor.pos)
    return None


def parse_string_literal(cursor: Cursor) -> ParseResult[str] | None:
    """Parse string literal: "text"

    Per Fluent EBNF:
        StringLiteral ::= '"' quoted_char* '"'
        quoted_char ::= (any_char - special_quoted_char - line_end) | escape
        line_end ::= CRLF | LF | EOF

    Line endings (LF, CRLF) are forbidden in string literals per spec.
    Use escape sequences (\\n) for newlines in strings.

    Supports escape sequences:
        \\" → "
        \\\\ → \\
        \\n → newline
        \\t → tab
        \\uXXXX → Unicode character (4 hex digits)
        \\UXXXXXX → Unicode character (6 hex digits)

    Examples:
        "hello" → "hello"
        "with \\"quotes\\"" → 'with "quotes"'
        "unicode: \\u00E4" → "unicode: ä"
        "emoji: \\U01F600" → Unicode emoji character

    Args:
        cursor: Current position in source

    Returns:
        Success(ParseResult(string_value, new_cursor)) on success
        Failure(ParseError(...)) if invalid string
    """
    # Clear any stale error context from previous parse attempts
    clear_parse_error()

    # Expect opening quote
    if cursor.is_eof or cursor.current != '"':
        _set_parse_error("Expected opening quote", cursor.pos, ('"',))
        return None

    cursor = cursor.advance()  # Skip opening "
    # Use list accumulation to avoid O(N^2) string concatenation
    chars: list[str] = []

    while not cursor.is_eof:
        # Check length limit before processing more characters (DoS prevention)
        if len(chars) > _MAX_STRING_LITERAL_LENGTH:
            _set_parse_error(
                f"String literal exceeds maximum length ({_MAX_STRING_LITERAL_LENGTH} chars)",
                cursor.pos,
            )
            return None

        ch = cursor.current

        if ch == '"':
            # Closing quote - done!
            cursor = cursor.advance()
            return ParseResult("".join(chars), cursor)

        # Per Fluent spec: line endings are forbidden in string literals
        # quoted_char ::= (any_char - special_quoted_char - line_end)
        # Note: Line endings normalized to LF at parser entry point
        if ch == "\n":
            _set_parse_error(
                "Line endings not allowed in string literals (use \\n escape)",
                cursor.pos,
            )
            return None

        if ch == "\\":
            # Escape sequence - use extracted helper
            cursor = cursor.advance()
            escape_result = parse_escape_sequence(cursor)
            if escape_result is None:
                return escape_result

            escaped_char, cursor = escape_result
            chars.append(escaped_char)

        else:
            # Regular character (control chars except line endings are allowed per spec)
            chars.append(ch)
            cursor = cursor.advance()

    # EOF without closing quote
    _set_parse_error("Unterminated string literal", cursor.pos, ('"',))
    return None
