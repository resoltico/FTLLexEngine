"""Unified identifier validation for FTL syntax.

This module provides the single source of truth for FTL identifier grammar rules,
ensuring consistent validation across parser and serializer subsystems.

Fluent Identifier Grammar:
    [a-zA-Z][a-zA-Z0-9_-]*

    - Start: ASCII letter (a-z, A-Z)
    - Continue: ASCII letter, ASCII digit, hyphen, or underscore
    - Length: Maximum 256 characters (DoS prevention)

Rationale:
    Parser and serializer previously duplicated identifier validation logic:
    - Parser used character-by-character functions for streaming validation
    - Serializer used regex for complete-string validation

    This duplication created maintenance burden and consistency risk. The unified
    module provides both validation modes from a single implementation.

Thread Safety:
    All functions in this module are pure functions with no shared state.
    Safe for concurrent use across multiple threads.

Python 3.13+.
"""

from __future__ import annotations

import re

from ftllexengine.constants import MAX_IDENTIFIER_LENGTH

__all__ = [
    "is_identifier_char",
    "is_identifier_start",
    "is_valid_identifier",
]

# Compiled regex for complete identifier validation.
# Pattern: [a-zA-Z][a-zA-Z0-9_-]* matches FTL identifier grammar.
# Compiled once at module load; C-level matching outperforms Python iteration.
_IDENTIFIER_CONTINUATION_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_-]*$")


def is_identifier_start(ch: str) -> bool:
    """Check if character can start an identifier per Fluent spec.

    Fluent identifiers follow the pattern: [a-zA-Z][a-zA-Z0-9_-]*
    Only ASCII letters are allowed as the first character.

    This enforces Fluent specification compliance. Python's str.isalpha()
    accepts Unicode letters (e.g., 'é', 'ñ', 'µ') which would create
    interoperability issues with other Fluent implementations (JavaScript,
    Rust) that enforce ASCII-only identifiers.

    Args:
        ch: Single character to check

    Returns:
        True if character is ASCII letter (a-z, A-Z), False otherwise

    Example:
        >>> is_identifier_start('a')
        True
        >>> is_identifier_start('1')
        False
        >>> is_identifier_start('é')
        False
    """
    return len(ch) == 1 and ch.isascii() and ch.isalpha()


def is_identifier_char(ch: str) -> bool:
    """Check if character can continue an identifier per Fluent spec.

    Fluent identifiers follow the pattern: [a-zA-Z][a-zA-Z0-9_-]*
    Continuation characters must be ASCII alphanumeric, hyphen, or underscore.

    This enforces Fluent specification compliance. Python's str.isalnum()
    accepts Unicode alphanumerics which would create interoperability issues.

    Args:
        ch: Single character to check

    Returns:
        True if character is ASCII letter, ASCII digit, hyphen, or underscore

    Example:
        >>> is_identifier_char('a')
        True
        >>> is_identifier_char('5')
        True
        >>> is_identifier_char('-')
        True
        >>> is_identifier_char('_')
        True
        >>> is_identifier_char('é')
        False
    """
    return len(ch) == 1 and ch.isascii() and (ch.isalnum() or ch in "-_")


def is_valid_identifier(name: str) -> bool:
    """Validate complete identifier per FTL grammar rules.

    Checks both syntax (character validity) and length constraints.
    This is the complete validation function used by serializer and other
    components that need to validate entire identifier strings.

    Args:
        name: Identifier string to validate

    Returns:
        True if identifier is valid per FTL spec, False otherwise

    Validation Rules:
        - Must not be empty
        - First character must be ASCII letter (a-zA-Z)
        - Remaining characters must be ASCII alphanumeric, hyphen, or underscore
        - Length must not exceed MAX_IDENTIFIER_LENGTH (256 characters)

    Example:
        >>> is_valid_identifier("message-id")
        True
        >>> is_valid_identifier("message_id_2")
        True
        >>> is_valid_identifier("1message")
        False
        >>> is_valid_identifier("")
        False
        >>> is_valid_identifier("a" * 300)
        False
    """
    # Empty check
    if not name:
        return False

    # Length check (DoS prevention)
    if len(name) > MAX_IDENTIFIER_LENGTH:
        return False

    # First character must be ASCII letter
    if not is_identifier_start(name[0]):
        return False

    # Remaining characters must be valid continuation characters
    # Compiled regex outperforms Python-level all() iteration
    return _IDENTIFIER_CONTINUATION_PATTERN.match(name[1:]) is not None
