"""Primitive parsing utilities for Fluent FTL parser.

This module provides low-level parsers for identifiers, numbers,
and string literals per the Fluent specification.

Error Handling:
    All parser functions return ``ParseResult[T] | ParseError``.
    Callers check ``isinstance(result, ParseError)`` to detect failure.
    Error details (message, position, expected tokens) are carried in
    the returned ``ParseError`` object — no side-channel state required.

Design:
    - Zero mutable state at module level (no ContextVars, no thread-locals)
    - Failure is a first-class value: ``ParseResult[T] | ParseError``
    - Error details are always co-located with the failure return
    - Safe for concurrent and async use without any per-call cleanup

Python 3.13+.
"""

from decimal import Decimal

from ftllexengine.constants import MAX_IDENTIFIER_LENGTH
from ftllexengine.core.identifier_validation import (
    is_identifier_char,
    is_identifier_start,
)
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult

__all__ = [
    "_ASCII_DIGITS",
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
# frozenset enables O(1) issuperset() check vs O(N) iteration.
_HEX_DIGITS: frozenset[str] = frozenset("0123456789abcdefABCDEF")

# ASCII digits only - FTL spec requires 0-9, not Unicode digits like ² or ³.
# str.isdigit() returns True for Unicode digits which causes int() to fail.
_ASCII_DIGITS: str = "0123456789"

# Token length limits for DoS prevention. MAX_IDENTIFIER_LENGTH is defined in
# constants.py (cross-module: also used by core/identifier_validation.py).
# _MAX_NUMBER_LENGTH and _MAX_STRING_LITERAL_LENGTH are parser-local limits.

# Maximum number literal length (1000 chars including sign and decimal point).
# Covers any practical numeric value (Python's arbitrary precision int/float).
# A 1000-digit number is ~3KB and already beyond practical use.
_MAX_NUMBER_LENGTH: int = 1000

# Maximum string literal length (1 million chars).
# FTL strings may contain long text blocks (e.g., legal disclaimers, terms).
# 1M characters (~2-4MB with Unicode) is generous while preventing abuse.
_MAX_STRING_LITERAL_LENGTH: int = 1_000_000

# Identifier validation functions imported from ftllexengine.core.identifier_validation:
# is_identifier_start, is_identifier_char
# See identifier_validation.py for the unified source of truth for FTL identifier grammar.


def parse_identifier(cursor: Cursor) -> ParseResult[str] | ParseError:
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
        ParseResult(identifier, new_cursor) on success
        ParseError with details on failure
    """
    # Check first character is ASCII alpha (a-z, A-Z only)
    if cursor.is_eof or not is_identifier_start(cursor.current):
        return ParseError(
            "Expected identifier (must start with ASCII letter a-z or A-Z)",
            cursor,
            ("a-z", "A-Z"),
        )

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
            if current_length > MAX_IDENTIFIER_LENGTH:
                return ParseError(
                    f"Identifier exceeds maximum length ({MAX_IDENTIFIER_LENGTH} chars)",
                    cursor,
                )
        else:
            break

    # Extract identifier
    identifier = Cursor(cursor.source, start_pos).slice_to(cursor.pos)
    return ParseResult(identifier, cursor)


def parse_number_value(num_str: str) -> int | Decimal:
    """Parse number string to int or Decimal.

    Uses Decimal for decimal literals to preserve financial-grade precision.
    Uses int for integer literals for memory efficiency.

    Args:
        num_str: Number string from parse_number

    Returns:
        int if no decimal point, Decimal otherwise
    """
    return int(num_str) if "." not in num_str else Decimal(num_str)


def parse_number(cursor: Cursor) -> ParseResult[str] | ParseError:
    """Parse number literal: -?[0-9]+(.[0-9]+)?

    Returns the raw string representation. Use parse_number_value()
    to convert to int or Decimal for NumberLiteral construction.

    Examples:
        42 → "42"
        -3.14 → "-3.14"
        0.001 → "0.001"

    Args:
        cursor: Current position in source

    Returns:
        ParseResult(number_str, new_cursor) on success
        ParseError with details on failure
    """
    start_pos = cursor.pos

    # Optional minus sign
    if not cursor.is_eof and cursor.current == "-":
        cursor = cursor.advance()

    # Must have at least one ASCII digit (0-9, not Unicode digits like ²)
    if cursor.is_eof or cursor.current not in _ASCII_DIGITS:
        return ParseError("Expected number", cursor, ("0-9",))

    # Integer part - with length limit to prevent DoS
    while not cursor.is_eof and cursor.current in _ASCII_DIGITS:
        cursor = cursor.advance()
        # Check length limit after consuming digit
        if cursor.pos - start_pos > _MAX_NUMBER_LENGTH:
            return ParseError(
                f"Number exceeds maximum length ({_MAX_NUMBER_LENGTH} chars)",
                cursor,
            )

    # Optional decimal part
    if not cursor.is_eof and cursor.current == ".":
        cursor = cursor.advance()

        # Must have digit after decimal
        if cursor.is_eof or cursor.current not in _ASCII_DIGITS:
            return ParseError("Expected digit after decimal point", cursor, ("0-9",))

        # Decimal digits - continue length check
        while not cursor.is_eof and cursor.current in _ASCII_DIGITS:
            cursor = cursor.advance()
            if cursor.pos - start_pos > _MAX_NUMBER_LENGTH:
                return ParseError(
                    f"Number exceeds maximum length ({_MAX_NUMBER_LENGTH} chars)",
                    cursor,
                )

    # Extract number string
    number_str = Cursor(cursor.source, start_pos).slice_to(cursor.pos)
    return ParseResult(number_str, cursor)


def parse_escape_sequence(  # noqa: PLR0911 - escape
    cursor: Cursor,
) -> tuple[str, Cursor] | ParseError:
    """Parse escape sequence after backslash in string.

    Helper extracted from parse_string_literal to reduce complexity.

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
        (escaped_char, new_cursor) on success
        ParseError on invalid escape
    """
    if cursor.is_eof:
        return ParseError("Unexpected EOF in escape sequence", cursor)

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
        # frozenset.issuperset() performs O(1) membership test per character
        if len(hex_digits) < _UNICODE_ESCAPE_LEN_SHORT or not _HEX_DIGITS.issuperset(
            hex_digits
        ):
            return ParseError(
                f"Invalid Unicode escape (expected {_UNICODE_ESCAPE_LEN_SHORT} hex digits)",
                cursor,
                ("0-9", "a-f", "A-F"),
            )
        cursor = cursor.advance(_UNICODE_ESCAPE_LEN_SHORT)

        # Convert to character
        code_point = int(hex_digits, 16)
        # Reject UTF-16 surrogate code points (invalid in UTF-8)
        # Per Unicode Standard: D800-DFFF are surrogates, invalid in isolation
        if _SURROGATE_RANGE_START <= code_point <= _SURROGATE_RANGE_END:
            return ParseError(
                f"Invalid surrogate code point: U+{hex_digits} (surrogates not allowed)",
                cursor,
            )
        return (chr(code_point), cursor)

    if escape_ch == "U":
        # Unicode escape: \UXXXXXX (6 hex digits for full Unicode range)
        cursor = cursor.advance()
        # Use slice_ahead for O(1) extraction instead of character-by-character loop
        hex_digits = cursor.slice_ahead(_UNICODE_ESCAPE_LEN_LONG)
        # frozenset.issuperset() performs O(1) membership test per character
        if len(hex_digits) < _UNICODE_ESCAPE_LEN_LONG or not _HEX_DIGITS.issuperset(
            hex_digits
        ):
            return ParseError(
                f"Invalid Unicode escape (expected {_UNICODE_ESCAPE_LEN_LONG} hex digits)",
                cursor,
                ("0-9", "a-f", "A-F"),
            )
        cursor = cursor.advance(_UNICODE_ESCAPE_LEN_LONG)

        # Convert to character
        code_point = int(hex_digits, 16)
        # Validate Unicode code point range
        if code_point > _MAX_UNICODE_CODE_POINT:
            return ParseError(
                f"Invalid Unicode code point: U+{hex_digits} (max U+10FFFF)",
                cursor,
            )
        # Reject UTF-16 surrogate code points (invalid in UTF-8)
        if _SURROGATE_RANGE_START <= code_point <= _SURROGATE_RANGE_END:
            return ParseError(
                f"Invalid surrogate code point: U+{hex_digits} (surrogates not allowed)",
                cursor,
            )
        return (chr(code_point), cursor)

    return ParseError(f"Invalid escape sequence: \\{escape_ch}", cursor)


def parse_string_literal(cursor: Cursor) -> ParseResult[str] | ParseError:
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
        ParseResult(string_value, new_cursor) on success
        ParseError with details on failure
    """
    # Expect opening quote
    if cursor.is_eof or cursor.current != '"':
        return ParseError("Expected opening quote", cursor, ('"',))

    cursor = cursor.advance()  # Skip opening "
    # Use list accumulation to avoid O(N^2) string concatenation
    chars: list[str] = []

    while not cursor.is_eof:
        # Check length limit before processing more characters (DoS prevention)
        if len(chars) > _MAX_STRING_LITERAL_LENGTH:
            return ParseError(
                f"String literal exceeds maximum length ({_MAX_STRING_LITERAL_LENGTH} chars)",
                cursor,
            )

        ch = cursor.current

        if ch == '"':
            # Closing quote - done!
            cursor = cursor.advance()
            return ParseResult("".join(chars), cursor)

        # Per Fluent spec: line endings are forbidden in string literals
        # quoted_char ::= (any_char - special_quoted_char - line_end)
        # Note: Line endings normalized to LF at parser entry point
        if ch == "\n":
            return ParseError(
                "Line endings not allowed in string literals (use \\n escape)",
                cursor,
            )

        if ch == "\\":
            # Escape sequence - use extracted helper
            cursor = cursor.advance()
            escape_result = parse_escape_sequence(cursor)
            if isinstance(escape_result, ParseError):
                return escape_result

            escaped_char, cursor = escape_result
            chars.append(escaped_char)

        else:
            # Regular character (control chars except line endings are allowed per spec)
            chars.append(ch)
            cursor = cursor.advance()

    # EOF without closing quote
    return ParseError("Unterminated string literal", cursor, ('"',))
