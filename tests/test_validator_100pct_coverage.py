"""Tests for 100% coverage of syntax/validator.py.

Tests semantic validation edge cases per Fluent spec.
"""

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Span,
    Term,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import SemanticValidator, validate


class TestValidatorMessageWithoutValue:
    """Test message validation without value."""

    def test_message_without_value_only_attributes(self) -> None:
        """Message with no value, only attributes (valid per spec).

        This tests line 170->174 (the branch when message.value is None).
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
    .attr = Attribute value
""")
        result = validate(resource)

        # Valid - messages can have only attributes
        assert result.is_valid
        assert len(result.annotations) == 0


class TestValidatorTermWithoutValue:
    """Test term validation requirements."""

    def test_term_without_value_is_invalid(self) -> None:
        """Term without value violates Fluent spec.

        This tests lines 188-194 in validator.py.
        Note: The parser might not actually create a term without a value,
        so this tests the defensive check.
        """
        # The FTL spec requires terms to have values, so the parser
        # should enforce this. This test verifies the validator's
        # defensive check exists, even if the parser prevents this case.

        # Manually construct a term without value (parser won't create this)
        term = Term(
            id=Identifier(name="test"),
            value=None,  # type: ignore[arg-type]  # Invalid: terms must have values
            attributes=(),
            span=Span(start=0, end=10),
        )

        resource = Resource(entries=(term,))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should detect missing term value
        assert not result.is_valid
        errors = [a for a in result.annotations if "TERM_NO_VALUE" in a.code]
        assert len(errors) > 0


class TestValidatorPlaceableNesting:
    """Test nested placeable validation."""

    def test_placeable_containing_placeable(self) -> None:
        """Nested placeables are validated recursively.

        This tests lines 293-294 (Placeable case in inline expression validation).
        """
        parser = FluentParserV1()
        # Nested placeables: { { $var } }
        resource = parser.parse("""
msg = { { $var } }
""")
        result = validate(resource)

        # Valid - nested placeables are allowed
        assert result.is_valid


class TestValidatorDuplicateNamedArguments:
    """Test function/term call argument validation."""

    def test_duplicate_named_argument_in_function_call(self) -> None:
        """Function call with duplicate named arguments is invalid.

        This tests line 340 in validator.py.
        """
        # Manually construct function call with duplicate named args
        # (parser might deduplicate them, so we construct manually)
        args = CallArguments(
            positional=(),
            named=(
                NamedArgument(
                    name=Identifier(name="option"),
                    value=NumberLiteral(value=1, raw="1"),
                ),
                NamedArgument(
                    name=Identifier(name="option"),  # Duplicate!
                    value=NumberLiteral(value=2, raw="2"),
                ),
            ),
        )

        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=args,
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should detect duplicate named argument
        assert not result.is_valid
        errors = [a for a in result.annotations if "DUPLICATE" in a.code]
        assert len(errors) > 0


class TestValidatorSelectExpressionEdgeCases:
    """Test select expression validation edge cases."""

    def test_select_expression_without_variants(self) -> None:
        """Select expression must have at least one variant.

        This tests lines 376-377 in validator.py.
        Note: The parser likely prevents this, but the validator checks defensively.
        """
        # Manually construct a select expression without variants
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(),  # Empty - invalid
        )

        pattern = Pattern(elements=(Placeable(expression=select),))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )

        resource = Resource(entries=(message,))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should detect missing variants
        assert not result.is_valid
        errors = [a for a in result.annotations if "NO_VARIANTS" in a.code]
        assert len(errors) > 0


class TestValidatorDecimalNormalization:
    """Test variant key decimal normalization."""

    def test_decimal_conversion_fallback_on_invalid_value(self) -> None:
        """Decimal conversion fallback for invalid number literals.

        This tests lines 423-425 in validator.py - the exception handler
        when Decimal conversion fails.
        """
        # Create a NumberLiteral with NaN which breaks Decimal conversion
        # In practice, the parser creates valid NumberLiterals, but the
        # validator has defensive exception handling
        malformed_key = NumberLiteral(value=float("nan"), raw="nan")

        # Create select expression with this malformed key
        variant = Variant(
            key=malformed_key,
            value=Pattern(elements=()),
            default=True,
        )

        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(variant,),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )

        resource = Resource(entries=(message,))
        validator = SemanticValidator()

        # Should not crash, should use fallback string conversion
        result = validator.validate(resource)

        # The validation should complete (may or may not be valid depending on
        # other aspects, but shouldn't crash)
        assert result is not None


class TestValidatorCommentAndJunkHandling:
    """Test validator handling of Comment and Junk entries."""

    def test_comment_entries_require_no_validation(self) -> None:
        """Comments pass through validation without checks.

        This tests line 156 (Comment case) in validator.py.
        """
        # Create resource with comment
        comment = Comment(content="# Test comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        result = validate(resource)

        # Comments don't cause validation issues
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_junk_entries_require_no_validation(self) -> None:
        """Junk already represents invalid syntax, no further validation.

        This tests line 157 (Junk case) in validator.py.
        """
        # Create resource with junk
        junk = Junk(content="invalid", annotations=())
        resource = Resource(entries=(junk,))

        result = validate(resource)

        # Junk doesn't require validation (it's already marked as invalid)
        # The validator doesn't add more errors for junk
        assert result.is_valid
        assert len(result.annotations) == 0


class TestValidatorTextElementHandling:
    """Test TextElement validation."""

    def test_text_elements_require_no_validation(self) -> None:
        """Plain text elements need no validation.

        This tests line 245 (TextElement case) in validator.py.
        """
        parser = FluentParserV1()
        # Simple message with only text
        resource = parser.parse("msg = Plain text")

        result = validate(resource)

        # Text-only messages are valid
        assert result.is_valid


class TestValidatorPlaceableInInlineExpression:
    """Test Placeable appearing in inline expression context."""

    def test_placeable_as_inline_expression(self) -> None:
        """Placeable can appear as inline expression.

        This tests lines 293-294 (Placeable case in inline expression).
        """
        # Nested placeable: outer placeable contains inner placeable
        inner = Placeable(expression=VariableReference(id=Identifier(name="x")))
        outer = Placeable(expression=inner)

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )

        resource = Resource(entries=(message,))
        result = validate(resource)

        # Nested placeables are valid
        assert result.is_valid
