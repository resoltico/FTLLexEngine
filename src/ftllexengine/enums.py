"""Enumerations for FTLLexEngine type-safe constants.

Uses StrEnum (Python 3.11+) for automatic string conversion.
StrEnum members are strings themselves, eliminating boilerplate __str__ methods.

Python 3.13+.
"""

from enum import StrEnum


class CommentType(StrEnum):
    """Type of FTL comment.

    StrEnum provides automatic string conversion: str(CommentType.COMMENT) == "comment"
    """

    COMMENT = "comment"
    """Standalone comment: # This is a comment"""

    GROUP = "group"
    """Group comment: ## Group Title"""

    RESOURCE = "resource"
    """Resource comment: ### Resource Description"""


class VariableContext(StrEnum):
    """Context where a variable reference appears.

    StrEnum provides automatic string conversion: str(VariableContext.PATTERN) == "pattern"
    """

    PATTERN = "pattern"
    """Variable in message pattern: msg = Hello { $name }"""

    SELECTOR = "selector"
    """Variable in select expression selector: { $count -> }"""

    VARIANT = "variant"
    """Variable in select variant: [one] { $count } item"""

    FUNCTION_ARG = "function_arg"
    """Variable in function argument: { NUMBER($value) }"""


class ReferenceKind(StrEnum):
    """Kind of reference (message or term).

    StrEnum provides automatic string conversion: str(ReferenceKind.MESSAGE) == "message"
    """

    MESSAGE = "message"
    """Reference to a message: { message-id }"""

    TERM = "term"
    """Reference to a term: { -term-id }"""


__all__ = [
    "CommentType",
    "ReferenceKind",
    "VariableContext",
]
