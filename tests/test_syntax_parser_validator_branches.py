"""Targeted branch coverage for rules.py and validator.py.

Addresses specific uncovered lines and branches:
- rules.py line 885: parse_term_reference returning None in parse_argument_expression
- NumberLiteral.__post_init__: invariant enforcement for raw/value consistency
- validator.py branches 157->exit, 246->exit: Match case exits for Junk and TextElement

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Annotation,
    Comment,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Resource,
    Span,
    Term,
    TextElement,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_argument_expression,
)
from ftllexengine.syntax.validator import SemanticValidator, validate


class TestRulesLine885TermReferenceFailure:
    """Test rules.py line 885: parse_term_reference returning None.

    Line 885 is triggered when parse_term_reference fails after we've
    already verified the character after '-' is an identifier start.
    This happens when the term reference has invalid attribute syntax.
    """

    def test_term_reference_with_invalid_attribute_name(self) -> None:
        """Term reference with dot but invalid attribute triggers line 885.

        Input: -brand.123
        - '-' followed by 'b' (identifier start) -> tries parse_term_reference
        - parse_term_reference parses '-brand', sees '.', tries attribute
        - Attribute identifier fails (starts with digit) -> returns None
        - Back in parse_argument_expression, line 885 returns None
        """
        cursor = Cursor("-brand.123", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)

        # Should fail because attribute identifier is invalid
        assert result is None

    def test_term_reference_with_dot_at_eof(self) -> None:
        """Term reference with trailing dot at EOF triggers line 885.

        Input: -brand.
        - parse_term_reference tries to parse attribute after '.'
        - No identifier after '.' (EOF) -> returns None
        """
        cursor = Cursor("-brand.", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)

        # Should fail because no attribute identifier after dot
        assert result is None

    def test_term_reference_with_dot_followed_by_space(self) -> None:
        """Term reference with dot followed by space triggers line 885.

        Input: -brand. x
        - parse_term_reference sees '.', tries to parse attribute
        - Space is not identifier start -> returns None
        """
        cursor = Cursor("-brand. ", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)

        # Should fail because space is not valid identifier start
        assert result is None

    def test_term_reference_with_dot_followed_by_special_char(self) -> None:
        """Term reference with dot followed by special char triggers line 885."""
        cursor = Cursor("-brand.@", 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)

        # Should fail because '@' is not valid identifier start
        assert result is None

    @given(
        term_name=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=1,
            max_size=10,
        ),
        invalid_char=st.sampled_from(["0", "1", "9", "@", "#", " ", "!", "-"]),
    )
    @settings(max_examples=20)
    def test_term_reference_invalid_attribute_property(
        self, term_name: str, invalid_char: str
    ) -> None:
        """Property: Term reference with invalid attribute char after dot fails."""
        event(f"invalid_char={invalid_char!r}")
        # Construct: -termname.X where X is not a valid identifier start
        input_str = f"-{term_name}.{invalid_char}"
        cursor = Cursor(input_str, 0)
        context = ParseContext()
        result = parse_argument_expression(cursor, context)

        # Should fail because invalid_char is not a valid identifier start
        assert result is None


class TestNumberLiteralInvariantPreventsInvalidConstruction:
    """NumberLiteral.__post_init__ prevents construction of malformed AST nodes.

    Previously, the validator's _variant_key_to_string had a try/except handler
    for Decimal conversion failures caused by programmatic NumberLiteral construction
    with invalid raw strings or non-int/Decimal value types. NumberLiteral now
    enforces the raw/value invariant at construction time, making those exception
    handlers unreachable via the normal API.
    """

    def test_invalid_raw_string_rejected(self) -> None:
        """NumberLiteral rejects raw strings that do not parse as numbers."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=1, raw="invalid")

    def test_unparseable_raw_brackets_rejected(self) -> None:
        """NumberLiteral rejects raw strings containing bracket syntax."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=Decimal("0"), raw="[1,2,3]")

    def test_empty_raw_string_rejected(self) -> None:
        """NumberLiteral rejects empty raw strings."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=1, raw="")


class TestValidatorBranch157JunkEntry:
    """Test validator.py branch 157->exit: Junk entry case.

    Ensures the Junk case in _validate_entry match statement is exercised.
    """

    def test_junk_entry_validation_single_junk(self) -> None:
        """Single Junk entry triggers case Junk(): pass branch."""
        junk = Junk(content="invalid syntax here", annotations=())
        resource = Resource(entries=(junk,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Junk doesn't add validation errors
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_junk_entry_with_annotations(self) -> None:
        """Junk entry with annotations still passes through validator."""
        ann = Annotation(
            code="PARSE_ERROR",
            message="Syntax error",
            arguments=None,
            span=Span(start=0, end=10),
        )
        junk = Junk(content="broken", annotations=(ann,))
        resource = Resource(entries=(junk,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Validator doesn't add errors for junk
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_multiple_junk_entries(self) -> None:
        """Multiple Junk entries all pass through validation."""
        junks = tuple(
            Junk(content=f"junk{i}", annotations=())
            for i in range(5)
        )
        resource = Resource(entries=junks)

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid
        assert len(result.annotations) == 0

    def test_mixed_entries_with_junk(self) -> None:
        """Mixed entries including Junk are all validated."""
        entries = (
            Message(
                id=Identifier(name="valid_msg"),
                value=Pattern(elements=(TextElement(value="Hello"),)),
                attributes=(),
            ),
            Junk(content="invalid", annotations=()),
            Comment(content="A comment", type=CommentType.COMMENT),
        )
        resource = Resource(entries=entries)

        validator = SemanticValidator()
        result = validator.validate(resource)

        # All entries pass validation
        assert result.is_valid


class TestValidatorBranch246TextElement:
    """Test validator.py branch 246->exit: TextElement case.

    Ensures the TextElement case in _validate_pattern_element is exercised.
    """

    def test_text_element_only_pattern(self) -> None:
        """Pattern with only TextElement triggers case TextElement(): pass."""
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Plain text only"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid
        assert len(result.annotations) == 0

    def test_multiple_text_elements(self) -> None:
        """Multiple TextElements in pattern all pass through validator."""
        elements = tuple(
            TextElement(value=f"Text segment {i}")
            for i in range(3)
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=elements),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_text_element_with_special_characters(self) -> None:
        """TextElement with special characters passes validation."""
        special_chars = 'Hello, world! @#$%^&*()_+-={}[]|\\:";<>?,./'
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value=special_chars),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_text_element_with_unicode(self) -> None:
        """TextElement with Unicode characters passes validation."""
        unicode_text = "Hello \u4e16\u754c \ud83c\udf0d"  # Chinese + Earth emoji
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value=unicode_text),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_empty_text_element(self) -> None:
        """Empty TextElement passes validation."""
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value=""),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid


class TestValidatorCommentEntry:
    """Comprehensive tests for Comment entry validation (line 156)."""

    def test_single_line_comment(self) -> None:
        """Single-line comment passes validation."""
        comment = Comment(content="This is a comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_group_comment(self) -> None:
        """Group comment passes validation."""
        comment = Comment(content="Group comment", type=CommentType.GROUP)
        resource = Resource(entries=(comment,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_resource_comment(self) -> None:
        """Resource comment passes validation."""
        comment = Comment(content="Resource comment", type=CommentType.RESOURCE)
        resource = Resource(entries=(comment,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_multiple_comments(self) -> None:
        """Multiple comments of different types pass validation."""
        comments = (
            Comment(content="Comment 1", type=CommentType.COMMENT),
            Comment(content="Group 1", type=CommentType.GROUP),
            Comment(content="Resource 1", type=CommentType.RESOURCE),
        )
        resource = Resource(entries=comments)

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid


class TestValidatorIntegrationCombined:
    """Integration tests combining multiple entry types for full coverage."""

    def test_full_resource_all_entry_types(self) -> None:
        """Resource with all entry types exercises all match cases."""
        # Message with text elements
        msg = Message(
            id=Identifier(name="greeting"),
            value=Pattern(elements=(TextElement(value="Hello, world!"),)),
            attributes=(),
        )

        # Term with pattern
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
            span=Span(start=0, end=20),
        )

        # Comment
        comment = Comment(content="A comment", type=CommentType.COMMENT)

        # Junk
        junk = Junk(content="invalid", annotations=())

        resource = Resource(entries=(msg, term, comment, junk))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # All entries should validate (junk and comments just pass through)
        assert result.is_valid

    def test_parser_output_exercises_text_elements(self) -> None:
        """Parsed FTL with text-only messages exercises TextElement branch."""
        parser = FluentParserV1()
        ftl_source = """
msg1 = Hello world
msg2 = Another message
msg3 = Third message with special chars: @#$%
"""
        resource = parser.parse(ftl_source)
        result = validate(resource)

        assert result.is_valid

    def test_parser_output_with_comments(self) -> None:
        """Parsed FTL with comments exercises Comment branch."""
        parser = FluentParserV1()
        ftl_source = """
# Single-line comment
## Group comment
### Resource comment

msg = Value
"""
        resource = parser.parse(ftl_source)
        result = validate(resource)

        assert result.is_valid


class TestVariantKeyToStringEdgeCases:
    """Additional tests for _variant_key_to_string edge cases."""

    def test_identifier_key_returns_name(self) -> None:
        """Identifier key returns its name directly."""
        validator = SemanticValidator()

        id_key = Identifier(name="other")
        result = validator._variant_key_to_string(id_key)

        assert result == "other"

    def test_integer_number_literal_normalizes(self) -> None:
        """Integer NumberLiteral normalizes via Decimal."""
        validator = SemanticValidator()

        num_key = NumberLiteral(value=42, raw="42")
        result = validator._variant_key_to_string(num_key)
        assert result == "42"

    def test_float_number_literal_normalizes(self) -> None:
        """Float NumberLiteral normalizes via Decimal."""
        validator = SemanticValidator()

        from decimal import Decimal  # noqa: PLC0415
        num_key = NumberLiteral(value=Decimal("1.0"), raw="1.0")
        result = validator._variant_key_to_string(num_key)
        # Decimal conversion and normalization handles float
        assert result == "1"

    def test_negative_number_literal(self) -> None:
        """Negative NumberLiteral normalizes correctly."""
        validator = SemanticValidator()

        num_key = NumberLiteral(value=-5, raw="-5")
        result = validator._variant_key_to_string(num_key)
        assert result == "-5"
