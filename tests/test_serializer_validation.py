"""Validation tests for ftllexengine.syntax.serializer module.

Tests validation logic in serializer:
- SelectExpression validation (no default, multiple defaults)
- Pattern validation with placeables
- Expression validation (nested structures)
- Resource validation
- validate=True parameter behavior
- Nested Placeable serialization
- NumberLiteral variant key handling

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import (
    SerializationValidationError,
    serialize,
)

# ============================================================================
# Validation Tests - Lines 61-72, 77-79, 84-93, 107-121, 165
# ============================================================================


class TestValidateSelectExpression:
    """Test _validate_select_expression (lines 61-72)."""

    def test_no_default_variant_raises_error(self) -> None:
        """COVERAGE: Lines 63-65 - No default variant."""
        # SelectExpression with no default variant
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="Other"),)),
                    default=False,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "no default variant" in str(exc_info.value).lower()

    def test_multiple_default_variants_raises_error(self) -> None:
        """COVERAGE: Lines 67-72 - Multiple default variants."""
        # SelectExpression with multiple default variants
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=True,  # First default
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="Other"),)),
                    default=True,  # Second default - invalid!
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "2 default variants" in str(exc_info.value)


class TestValidatePattern:
    """Test _validate_pattern (lines 77-79)."""

    def test_validate_pattern_with_placeable(self) -> None:
        """COVERAGE: Lines 77-79 - Pattern containing placeable is validated."""
        # Valid pattern with placeable containing valid select
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="a"),
                    value=Pattern(elements=(TextElement(value="A"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise - valid select with one default
        result = serialize(resource, validate=True)
        assert "msg" in result


class TestValidateExpression:
    """Test _validate_expression (lines 84-93)."""

    def test_validate_nested_select_in_variant(self) -> None:
        """COVERAGE: Lines 88-89 - Validate patterns within variants."""
        # Nested select expression in variant value
        inner_select = SelectExpression(
            selector=VariableReference(id=Identifier(name="inner")),
            variants=(
                Variant(
                    key=Identifier(name="default"),
                    value=Pattern(elements=(TextElement(value="Inner"),)),
                    default=True,
                ),
            ),
        )

        outer_select = SelectExpression(
            selector=VariableReference(id=Identifier(name="outer")),
            variants=(
                Variant(
                    key=Identifier(name="nested"),
                    value=Pattern(elements=(Placeable(expression=inner_select),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=outer_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise - both selects have default variants
        result = serialize(resource, validate=True)
        assert "msg" in result

    def test_validate_nested_placeable(self) -> None:
        """COVERAGE: Lines 90-91 - Validate nested Placeable."""
        # Nested Placeable containing select
        inner_select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="default"),
                    value=Pattern(elements=(TextElement(value="Val"),)),
                    default=True,
                ),
            ),
        )

        nested_placeable = Placeable(expression=Placeable(expression=inner_select))

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(nested_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise - select has default
        result = serialize(resource, validate=True)
        assert "msg" in result

    def test_validate_other_expression_types(self) -> None:
        """COVERAGE: Lines 92-93 - Other expressions pass without validation."""
        # Variable reference doesn't need validation
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(Placeable(expression=VariableReference(id=Identifier(name="x"))),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise - no select expressions to validate
        result = serialize(resource, validate=True)
        assert "$x" in result


class TestValidateResource:
    """Test _validate_resource (lines 107-121)."""

    def test_validate_message_value(self) -> None:
        """COVERAGE: Lines 109-112 - Validate message value."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="d"),
                    value=Pattern(elements=(TextElement(value="D"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=True)
        assert "msg" in result

    def test_validate_message_attributes(self) -> None:
        """COVERAGE: Lines 113-114 - Validate message attributes."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="d"),
                    value=Pattern(elements=(TextElement(value="D"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=None,
            attributes=(
                Attribute(
                    id=Identifier(name="attr"),
                    value=Pattern(elements=(Placeable(expression=select),)),
                ),
            ),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=True)
        assert ".attr" in result

    def test_validate_term(self) -> None:
        """COVERAGE: Lines 115-119 - Validate term value and attributes."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="d"),
                    value=Pattern(elements=(TextElement(value="D"),)),
                    default=True,
                ),
            ),
        )

        term = Term(
            id=Identifier(name="term"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(
                Attribute(
                    id=Identifier(name="attr"),
                    value=Pattern(elements=(TextElement(value="Attr"),)),
                ),
            ),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource, validate=True)
        assert "-term" in result

    def test_validate_comments_and_junk_skip(self) -> None:
        """COVERAGE: Lines 120-121 - Comments don't need validation."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CommentType,
        )

        comment = Comment(type=CommentType.COMMENT, content="A comment")
        resource = Resource(entries=(comment,))

        # Should not raise - comments are skipped
        result = serialize(resource, validate=True)
        assert "# A comment" in result


class TestSerializeWithValidation:
    """Test serialize() with validate=True (line 165)."""

    def test_serialize_with_validation_enabled(self) -> None:
        """COVERAGE: Line 165 - Validation is called when enabled."""
        message = Message(
            id=Identifier(name="simple"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should succeed - simple message with no select
        result = serialize(resource, validate=True)
        assert result == "simple = Hello\n"


# ============================================================================
# Nested Placeable Serialization - Lines 324-326
# ============================================================================


class TestNestedPlaceableSerialization:
    """Test nested Placeable serialization (lines 324-326)."""

    def test_serialize_nested_placeable(self) -> None:
        """COVERAGE: Lines 324-326 - Nested Placeable with braces."""
        # Nested placeable: { { $var } }
        inner = VariableReference(id=Identifier(name="var"))
        outer = Placeable(expression=Placeable(expression=inner))

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # Should produce "msg = { { $var } }"
        assert "{ { $var } }" in result

    def test_serialize_deeply_nested_placeable(self) -> None:
        """COVERAGE: Lines 324-326 - Multiple levels of nesting."""
        # Triple nested: { { { $x } } }
        inner = VariableReference(id=Identifier(name="x"))
        mid = Placeable(expression=Placeable(expression=inner))
        outer = Placeable(expression=mid)

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # Should produce nested structure
        assert "{ { { $x } } }" in result


# ============================================================================
# NumberLiteral in Variant Key - Lines 370-371
# ============================================================================


class TestNumberLiteralVariantKey:
    """Test NumberLiteral as variant key (lines 370-371)."""

    def test_serialize_number_literal_variant_key(self) -> None:
        """COVERAGE: Lines 370-371 - NumberLiteral variant key."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=0, raw="0"),
                    value=Pattern(elements=(TextElement(value="Zero"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="Many"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="items"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[0] Zero" in result
        assert "[1] One" in result
        assert "*[other] Many" in result

    def test_serialize_float_literal_variant_key(self) -> None:
        """COVERAGE: Lines 370-371 - Float NumberLiteral variant key."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="price")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("9.99"), raw="9.99"),
                    value=Pattern(elements=(TextElement(value="Cheap"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="Expensive"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="cost"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[9.99] Cheap" in result
        assert "*[other] Expensive" in result


# ============================================================================
# Additional Edge Cases
# ============================================================================


class TestSerializerEdgeCases:
    """Additional edge cases for complete coverage."""

    def test_serialize_function_with_arguments(self) -> None:
        """Test function reference with mixed arguments."""
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="num")),),
                named=(),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)
        assert "NUMBER($num)" in result

    def test_serialize_string_literal(self) -> None:
        """Test string literal serialization."""
        literal = StringLiteral(value="hello")

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=literal),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)
        assert '"hello"' in result


# ============================================================================
# CallArguments Validation - Duplicate Names and Literal-Only Values
# ============================================================================


class TestCallArgumentsValidation:
    """Test _validate_call_arguments function.

    Per FTL EBNF:
        NamedArgument ::= Identifier blank? ":" blank? (StringLiteral | NumberLiteral)

    The parser enforces these constraints during parsing, but programmatically
    constructed ASTs may violate them. The serializer validation catches these
    errors before producing invalid FTL.
    """

    def test_duplicate_named_arguments_in_function_raises_error(self) -> None:
        """Duplicate named argument names in FunctionReference must raise error."""
        # Create FunctionReference with duplicate named argument "style"
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="count")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=StringLiteral(value="decimal"),
                    ),
                    NamedArgument(
                        name=Identifier(name="style"),  # DUPLICATE!
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "Duplicate named argument 'style'" in str(exc_info.value)
        assert "must be unique" in str(exc_info.value).lower()

    def test_duplicate_named_arguments_in_term_raises_error(self) -> None:
        """Duplicate named argument names in TermReference must raise error."""
        # Create TermReference with duplicate named argument "case"
        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=None,
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="case"),
                        value=StringLiteral(value="upper"),
                    ),
                    NamedArgument(
                        name=Identifier(name="case"),  # DUPLICATE!
                        value=StringLiteral(value="lower"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=term_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "Duplicate named argument 'case'" in str(exc_info.value)

    def test_non_literal_named_argument_value_raises_error(self) -> None:
        """Named argument with VariableReference value must raise error."""
        # Per FTL spec, named argument values must be StringLiteral or NumberLiteral
        # NOT arbitrary expressions like VariableReference
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="count")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=VariableReference(id=Identifier(name="styleVar")),  # INVALID!
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "style" in str(exc_info.value)
        assert "VariableReference" in str(exc_info.value)
        assert "StringLiteral or NumberLiteral" in str(exc_info.value)

    def test_function_reference_named_argument_with_function_raises_error(self) -> None:
        """Named argument with FunctionReference value must raise error."""
        # Nested function call as named argument value is invalid per FTL spec
        inner_func = FunctionReference(
            id=Identifier(name="UPPER"),
            arguments=CallArguments(
                positional=(StringLiteral(value="text"),),
                named=(),
            ),
        )

        func = FunctionReference(
            id=Identifier(name="FORMAT"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="value"),
                        value=inner_func,  # INVALID! Must be literal
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        assert "value" in str(exc_info.value)
        assert "FunctionReference" in str(exc_info.value)

    def test_valid_named_arguments_with_string_literal(self) -> None:
        """Valid named arguments with StringLiteral values should pass."""
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="count")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=StringLiteral(value="currency"),
                    ),
                    NamedArgument(
                        name=Identifier(name="currency"),
                        value=StringLiteral(value="USD"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="price"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should succeed - unique names, literal values
        result = serialize(resource, validate=True)
        assert "NUMBER($count, style: " in result
        assert '"currency"' in result
        assert '"USD"' in result

    def test_valid_named_arguments_with_number_literal(self) -> None:
        """Valid named arguments with NumberLiteral values should pass."""
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="value")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="minimumFractionDigits"),
                        value=NumberLiteral(value=2, raw="2"),
                    ),
                    NamedArgument(
                        name=Identifier(name="maximumFractionDigits"),
                        value=NumberLiteral(value=4, raw="4"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="decimal"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should succeed - unique names, literal values
        result = serialize(resource, validate=True)
        assert "minimumFractionDigits: 2" in result
        assert "maximumFractionDigits: 4" in result

    def test_term_reference_valid_arguments_pass(self) -> None:
        """Valid TermReference with proper named arguments should pass."""
        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="short"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="case"),
                        value=StringLiteral(value="upper"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="title"),
            value=Pattern(elements=(Placeable(expression=term_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=True)
        assert "-brand.short(case: " in result

    def test_validation_skipped_when_disabled(self) -> None:
        """Invalid AST should serialize without validation when validate=False."""
        # This AST has duplicate named arguments - normally invalid
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=StringLiteral(value="a"),
                    ),
                    NamedArgument(
                        name=Identifier(name="style"),  # DUPLICATE!
                        value=StringLiteral(value="b"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # With validate=False, should serialize (producing invalid FTL)
        result = serialize(resource, validate=False)
        # Serialization produces the invalid output
        assert "NUMBER(style: " in result

    def test_triple_duplicate_named_arguments(self) -> None:
        """Three or more duplicate named arguments should raise on first duplicate."""
        func = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(name=Identifier(name="x"), value=StringLiteral(value="1")),
                    NamedArgument(name=Identifier(name="x"), value=StringLiteral(value="2")),
                    NamedArgument(name=Identifier(name="x"), value=StringLiteral(value="3")),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError) as exc_info:
            serialize(resource, validate=True)

        # Should catch the first duplicate
        assert "Duplicate named argument 'x'" in str(exc_info.value)
