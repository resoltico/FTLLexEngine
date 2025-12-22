"""Type-safe assertion helpers for AST testing.

Provides reusable functions that perform isinstance() checks and return
narrowed types, making test code both type-safe and readable.

These helpers solve the common pattern of:
    entry = resource.entries[0]
    assert isinstance(entry, Message)
    assert entry.id.name == "hello"

Becoming:
    msg = assert_is_message(resource.entries[0])
    assert msg.id.name == "hello"
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import (
        Comment,
        Entry,
        Identifier,
        Junk,
        Message,
        NumberLiteral,
        Pattern,
        PatternElement,
        Placeable,
        SelectExpression,
        Term,
        TextElement,
    )


def assert_is_message(entry: Entry) -> Message:
    """Assert entry is Message and return with narrowed type.

    Args:
        entry: Entry union (Message | Term | Comment | Junk)

    Returns:
        The entry with type narrowed to Message

    Raises:
        AssertionError: If entry is not a Message
    """
    from ftllexengine.syntax.ast import Message

    assert isinstance(entry, Message), (
        f"Expected Message, got {type(entry).__name__}"
    )
    return entry


def assert_is_term(entry: Entry) -> Term:
    """Assert entry is Term and return with narrowed type.

    Args:
        entry: Entry union (Message | Term | Comment | Junk)

    Returns:
        The entry with type narrowed to Term

    Raises:
        AssertionError: If entry is not a Term
    """
    from ftllexengine.syntax.ast import Term

    assert isinstance(entry, Term), (
        f"Expected Term, got {type(entry).__name__}"
    )
    return entry


def assert_is_comment(entry: Entry) -> Comment:
    """Assert entry is Comment and return with narrowed type.

    Args:
        entry: Entry union (Message | Term | Comment | Junk)

    Returns:
        The entry with type narrowed to Comment

    Raises:
        AssertionError: If entry is not a Comment
    """
    from ftllexengine.syntax.ast import Comment

    assert isinstance(entry, Comment), (
        f"Expected Comment, got {type(entry).__name__}"
    )
    return entry


def assert_is_junk(entry: Entry) -> Junk:
    """Assert entry is Junk and return with narrowed type.

    Args:
        entry: Entry union (Message | Term | Comment | Junk)

    Returns:
        The entry with type narrowed to Junk

    Raises:
        AssertionError: If entry is not Junk
    """
    from ftllexengine.syntax.ast import Junk

    assert isinstance(entry, Junk), (
        f"Expected Junk, got {type(entry).__name__}"
    )
    return entry


def assert_is_text_element(elem: PatternElement) -> TextElement:
    """Assert element is TextElement and return with narrowed type.

    Args:
        elem: PatternElement union (TextElement | Placeable)

    Returns:
        The element with type narrowed to TextElement

    Raises:
        AssertionError: If element is not a TextElement
    """
    from ftllexengine.syntax.ast import TextElement

    assert isinstance(elem, TextElement), (
        f"Expected TextElement, got {type(elem).__name__}"
    )
    return elem


def assert_is_placeable(elem: PatternElement) -> Placeable:
    """Assert element is Placeable and return with narrowed type.

    Args:
        elem: PatternElement union (TextElement | Placeable)

    Returns:
        The element with type narrowed to Placeable

    Raises:
        AssertionError: If element is not a Placeable
    """
    from ftllexengine.syntax.ast import Placeable

    assert isinstance(elem, Placeable), (
        f"Expected Placeable, got {type(elem).__name__}"
    )
    return elem


def assert_is_select_expression(expr: object) -> SelectExpression:
    """Assert expression is SelectExpression and return with narrowed type.

    Args:
        expr: Expression object

    Returns:
        The expression with type narrowed to SelectExpression

    Raises:
        AssertionError: If expression is not a SelectExpression
    """
    from ftllexengine.syntax.ast import SelectExpression

    assert isinstance(expr, SelectExpression), (
        f"Expected SelectExpression, got {type(expr).__name__}"
    )
    return expr


def assert_is_identifier(key: object) -> Identifier:
    """Assert key is Identifier and return with narrowed type.

    Args:
        key: Variant key union (Identifier | NumberLiteral)

    Returns:
        The key with type narrowed to Identifier

    Raises:
        AssertionError: If key is not an Identifier
    """
    from ftllexengine.syntax.ast import Identifier

    assert isinstance(key, Identifier), (
        f"Expected Identifier, got {type(key).__name__}"
    )
    return key


def assert_is_number_literal(key: object) -> NumberLiteral:
    """Assert key is NumberLiteral and return with narrowed type.

    Args:
        key: Variant key union (Identifier | NumberLiteral)

    Returns:
        The key with type narrowed to NumberLiteral

    Raises:
        AssertionError: If key is not a NumberLiteral
    """
    from ftllexengine.syntax.ast import NumberLiteral

    assert isinstance(key, NumberLiteral), (
        f"Expected NumberLiteral, got {type(key).__name__}"
    )
    return key


def assert_has_pattern(entry: Entry) -> Pattern:
    """Assert entry has a value pattern and return it.

    Args:
        entry: Entry that should have a value (Message or Term)

    Returns:
        The entry's value pattern

    Raises:
        AssertionError: If entry doesn't have a value or value is None
    """
    from ftllexengine.syntax.ast import Message, Term

    assert isinstance(entry, (Message, Term)), (
        f"Expected Message or Term, got {type(entry).__name__}"
    )
    assert entry.value is not None, f"{type(entry).__name__} has no value"
    return entry.value


__all__ = [
    "assert_has_pattern",
    "assert_is_comment",
    "assert_is_identifier",
    "assert_is_junk",
    "assert_is_message",
    "assert_is_number_literal",
    "assert_is_placeable",
    "assert_is_select_expression",
    "assert_is_term",
    "assert_is_text_element",
]
