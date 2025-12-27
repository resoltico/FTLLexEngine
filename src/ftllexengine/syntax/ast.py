"""Fluent AST (Abstract Syntax Tree) node definitions.

Complete implementation of Fluent 1.0 AST spec.
Includes type guards as static methods (eliminates circular imports).

Python 3.13+. Zero external dependencies.
"""

from dataclasses import dataclass
from typing import TypeIs

from ftllexengine.enums import CommentType

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Base types
    "Span",
    "Annotation",
    "Identifier",
    # Resource structure
    "Resource",
    "Message",
    "Term",
    "Attribute",
    "Comment",
    "Junk",
    # Pattern elements
    "Pattern",
    "TextElement",
    "Placeable",
    # Expressions
    "SelectExpression",
    "Variant",
    "StringLiteral",
    "NumberLiteral",
    "VariableReference",
    "MessageReference",
    "TermReference",
    "FunctionReference",
    "CallArguments",
    "NamedArgument",
    # Type aliases
    "Entry",
    "PatternElement",
    "Expression",
    "InlineExpression",
    "VariantKey",
    "ASTNode",
]

# ============================================================================
# BASE TYPES
# ============================================================================

# ASTNode type alias is defined at the end of this file after all classes
# This is necessary because it references all the AST node classes


@dataclass(frozen=True, slots=True)
class Span:
    """Source position span per Fluent spec.

    Tracks byte offsets in source text for error reporting and tooling.

    Attributes:
        start: Starting byte offset (inclusive)
        end: Ending byte offset (exclusive)

    Example:
        Source: "hello = world"
        Message span: Span(start=0, end=13)
        Identifier "hello" span: Span(start=0, end=5)
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        """Validate span invariants."""
        if self.start < 0:
            msg = f"Span start must be >= 0, got {self.start}"
            raise ValueError(msg)
        if self.end < self.start:
            msg = f"Span end ({self.end}) must be >= start ({self.start})"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Annotation:
    """Parse error annotation per Fluent spec.

    Attached to Junk nodes to provide structured error information.

    Attributes:
        code: Error code (e.g., "E0001", "expected-token")
        message: Human-readable error message
        arguments: Additional error context (optional)
        span: Location of the error (optional)

    Example:
        Annotation(
            code="expected-token",
            message="Expected '}' but found EOF",
            span=Span(start=10, end=10)
        )
    """

    code: str
    message: str
    arguments: dict[str, str] | None = None
    span: Span | None = None


@dataclass(frozen=True, slots=True)
class Identifier:
    """Identifier: [a-zA-Z][a-zA-Z0-9_-]*"""

    name: str

    @staticmethod
    def guard(key: object) -> TypeIs["Identifier"]:
        """Type guard for Identifier (used in variant keys)."""
        return isinstance(key, Identifier)


# ============================================================================
# TOP-LEVEL ENTRIES
# ============================================================================


@dataclass(frozen=True, slots=True)
class Resource:
    """Root AST node containing all entries."""

    entries: tuple["Entry", ...]


@dataclass(frozen=True, slots=True)
class Message:
    """Message definition.

    Examples:
        hello = Hello, world!
        welcome = Welcome, { $name }!
        button = Save
            .tooltip = Click to save
    """

    id: Identifier
    value: "Pattern | None"
    attributes: tuple["Attribute", ...]
    comment: "Comment | None" = None
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs["Message"]:
        """Type guard for Message (used in entry filtering)."""
        return isinstance(entry, Message)


@dataclass(frozen=True, slots=True)
class Term:
    """Term definition (private, prefixed with -).

    Example:
        -brand = Firefox
    """

    id: Identifier
    value: "Pattern"
    attributes: tuple["Attribute", ...]
    comment: "Comment | None" = None
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs["Term"]:
        """Type guard for Term (used in entry filtering)."""
        return isinstance(entry, Term)


@dataclass(frozen=True, slots=True)
class Attribute:
    """Message or term attribute.


    Example:
        login = Sign In
            .tooltip = Click here to sign in  ← attribute
    """

    id: Identifier
    value: "Pattern"


@dataclass(frozen=True, slots=True)
class Comment:
    """Comment (# single, ## group, ### resource).

    """

    content: str
    type: CommentType
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs["Comment"]:
        """Type guard for Comment (used in entry filtering)."""
        return isinstance(entry, Comment)


@dataclass(frozen=True, slots=True)
class Junk:
    """Unparseable content (syntax error recovery).

    Per Fluent spec, Junk nodes wrap unparseable content and include
    structured error annotations for tooling support.

    Attributes:
        content: The unparseable source text
        annotations: Parse errors with positions and messages
        span: Location of junk content in source

    Example:
        Junk(
            content="invalid { syntax",
            annotations=(
                Annotation(
                    code="expected-token",
                    message="Expected '}' but found EOF",
                    span=Span(start=9, end=16)
                ),
            ),
            span=Span(start=0, end=16)
        )
    """

    content: str
    annotations: tuple[Annotation, ...] = ()
    span: Span | None = None

    @staticmethod
    def guard(entry: object) -> TypeIs["Junk"]:
        """Type guard for Junk (used in entry filtering)."""
        return isinstance(entry, Junk)


# ============================================================================
# PATTERNS
# ============================================================================


@dataclass(frozen=True, slots=True)
class Pattern:
    """Text pattern with optional placeables."""

    elements: tuple["PatternElement", ...]


@dataclass(frozen=True, slots=True)
class TextElement:
    """Plain text segment."""

    value: str

    @staticmethod
    def guard(elem: object) -> TypeIs["TextElement"]:
        """Type guard for TextElement.

        Enables type-safe narrowing without circular imports.

        Args:
            elem: Object to check

        Returns:
            True if elem is TextElement

        Example:
            if TextElement.guard(elem):
                elem.value  # Type-safe! mypy knows elem is TextElement
        """
        return isinstance(elem, TextElement)


@dataclass(frozen=True, slots=True)
class Placeable:
    """Dynamic content: { expression }"""

    expression: "Expression"

    @staticmethod
    def guard(elem: object) -> TypeIs["Placeable"]:
        """Type guard for Placeable."""
        return isinstance(elem, Placeable)


# ============================================================================
# EXPRESSIONS
# ============================================================================


@dataclass(frozen=True, slots=True)
class SelectExpression:
    """Conditional expression with variants.


    Example:
        { $count ->
            [one] 1 item
           *[other] { $count } items
        }
    """

    selector: "InlineExpression"
    variants: tuple["Variant", ...]

    @staticmethod
    def guard(expr: object) -> TypeIs["SelectExpression"]:
        """Type guard for SelectExpression."""
        return isinstance(expr, SelectExpression)


@dataclass(frozen=True, slots=True)
class Variant:
    """Single variant in select expression.

    """

    key: "VariantKey"
    value: "Pattern"
    default: bool = False


# ============================================================================
# LITERALS
# ============================================================================


@dataclass(frozen=True, slots=True)
class StringLiteral:
    """String literal: "text"

    Supports escape sequences:
        \\" → "
        \\\\ → \\
        \\u0000 → Unicode
    """

    value: str


@dataclass(frozen=True, slots=True)
class NumberLiteral:
    """Number literal: 42 or 3.14

    The raw field preserves original source for serialization.

    Invariant:
        AST transformers creating new NumberLiteral nodes must ensure
        raw correctly represents value. Parser guarantees consistency
        at construction time. Divergence between these fields indicates
        a transformer bug, not a library issue.
    """

    value: int | float
    """Parsed numeric value."""

    raw: str
    """Original source representation (for serialization)."""

    @staticmethod
    def guard(key: object) -> TypeIs["NumberLiteral"]:
        """Type guard for NumberLiteral (used in variant keys)."""
        return isinstance(key, NumberLiteral)


# ============================================================================
# REFERENCES
# ============================================================================


@dataclass(frozen=True, slots=True)
class VariableReference:
    """Variable reference: $variable"""

    id: Identifier

    @staticmethod
    def guard(expr: object) -> TypeIs["VariableReference"]:
        """Type guard for VariableReference."""
        return isinstance(expr, VariableReference)


@dataclass(frozen=True, slots=True)
class MessageReference:
    """Message reference: message-id or message-id.attribute"""

    id: Identifier
    attribute: Identifier | None = None

    @staticmethod
    def guard(expr: object) -> TypeIs["MessageReference"]:
        """Type guard for MessageReference."""
        return isinstance(expr, MessageReference)


@dataclass(frozen=True, slots=True)
class TermReference:
    """Term reference: -term-id or -term-id.attribute"""

    id: Identifier
    attribute: Identifier | None = None
    arguments: "CallArguments | None" = None

    @staticmethod
    def guard(expr: object) -> TypeIs["TermReference"]:
        """Type guard for TermReference."""
        return isinstance(expr, TermReference)


@dataclass(frozen=True, slots=True)
class FunctionReference:
    """Function call: FUNCTION(arg1, key: value)"""

    id: Identifier
    arguments: "CallArguments"

    @staticmethod
    def guard(expr: object) -> TypeIs["FunctionReference"]:
        """Type guard for FunctionReference."""
        return isinstance(expr, FunctionReference)


@dataclass(frozen=True, slots=True)
class CallArguments:
    """Function call arguments."""

    positional: tuple["InlineExpression", ...]
    named: tuple["NamedArgument", ...]


@dataclass(frozen=True, slots=True)
class NamedArgument:
    """Named argument: name: value"""

    name: Identifier
    value: "InlineExpression"


# ============================================================================
# TYPE ALIASES
# ============================================================================

type Entry = Message | Term | Comment | Junk
type PatternElement = TextElement | Placeable
type Expression = SelectExpression | InlineExpression
type InlineExpression = (
    StringLiteral
    | NumberLiteral
    | VariableReference
    | MessageReference
    | TermReference
    | FunctionReference
    | Placeable
)
type VariantKey = Identifier | NumberLiteral

# Complete ASTNode type - union of all AST node types
# This replaces the forward declaration at the top of the file
type ASTNode = (
    Resource
    | Message
    | Term
    | Attribute
    | Comment
    | Junk
    | Pattern
    | TextElement
    | Placeable
    | SelectExpression
    | Variant
    | StringLiteral
    | NumberLiteral
    | VariableReference
    | MessageReference
    | TermReference
    | FunctionReference
    | CallArguments
    | NamedArgument
    | Identifier
    | Annotation
    | Span
)
