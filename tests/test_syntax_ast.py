"""Comprehensive property-based tests for syntax.ast module.

Tests all AST node classes for immutability, construction, and type guards.

"""

from decimal import Decimal

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Span,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)


class TestSpanDataclass:
    """Property-based tests for Span dataclass."""

    def test_span_frozen(self) -> None:
        """Property: Span instances are immutable (frozen)."""
        span = Span(start=0, end=10)

        with pytest.raises((AttributeError, TypeError)):
            span.start = 5  # type: ignore[misc]

    @given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
    def test_span_valid_construction(self, start: int, end: int) -> None:
        """Property: Span accepts valid start/end values."""
        span_len = end - start if end >= start else 0
        event(f"span_len={span_len}")
        if end >= start:
            span = Span(start=start, end=end)
            assert span.start == start
            assert span.end == end

    def test_span_negative_start_raises(self) -> None:
        """Verify Span raises ValueError for negative start."""
        with pytest.raises(ValueError, match="start must be >= 0"):
            Span(start=-1, end=10)

    def test_span_end_before_start_raises(self) -> None:
        """Verify Span raises ValueError when end < start."""
        with pytest.raises(ValueError, match=r"end.*must be >= start"):
            Span(start=10, end=5)

    def test_span_zero_length_valid(self) -> None:
        """Verify Span allows zero-length spans (start == end)."""
        span = Span(start=5, end=5)
        assert span.start == 5
        assert span.end == 5


class TestAnnotationDataclass:
    """Property-based tests for Annotation dataclass."""

    def test_annotation_frozen(self) -> None:
        """Property: Annotation instances are immutable (frozen)."""
        ann = Annotation(code="E001", message="Test error")

        with pytest.raises((AttributeError, TypeError)):
            ann.code = "E002"  # type: ignore[misc]

    @given(st.text(min_size=1), st.text(min_size=1))
    def test_annotation_construction_required_only(self, code: str, message: str) -> None:
        """Property: Annotation can be constructed with required fields only."""
        ann = Annotation(code=code, message=message)
        assert ann.code == code
        assert ann.message == message
        assert ann.arguments is None
        assert ann.span is None

    def test_annotation_with_all_fields(self) -> None:
        """Verify Annotation accepts all optional fields."""
        span = Span(start=0, end=10)
        ann = Annotation(
            code="E001",
            message="Test",
            arguments=(("key", "value"),),
            span=span,
        )
        assert ann.code == "E001"
        assert ann.arguments == (("key", "value"),)
        assert ann.span is span


class TestIdentifierDataclass:
    """Property-based tests for Identifier dataclass."""

    def test_identifier_frozen(self) -> None:
        """Property: Identifier instances are immutable (frozen)."""
        ident = Identifier(name="test")

        with pytest.raises((AttributeError, TypeError)):
            ident.name = "changed"  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_identifier_construction(self, name: str) -> None:
        """Property: Identifier can be constructed with any name."""
        ident = Identifier(name=name)
        assert ident.name == name

    def test_identifier_guard_true(self) -> None:
        """Verify Identifier.guard returns True for Identifier instances."""
        ident = Identifier(name="test")
        assert Identifier.guard(ident) is True

    @given(st.text())
    def test_identifier_guard_false(self, not_identifier: str) -> None:
        """Property: Identifier.guard returns False for non-Identifier objects."""
        assert Identifier.guard(not_identifier) is False


class TestResourceDataclass:
    """Property-based tests for Resource dataclass."""

    def test_resource_frozen(self) -> None:
        """Property: Resource instances are immutable (frozen)."""
        resource = Resource(entries=())

        with pytest.raises((AttributeError, TypeError)):
            resource.entries = (  # type: ignore[misc]
                Message(id=Identifier(name="x"), value=Pattern(elements=()), attributes=()),
            )

    def test_resource_empty_entries(self) -> None:
        """Verify Resource accepts empty entries tuple."""
        resource = Resource(entries=())
        assert resource.entries == ()

    def test_resource_with_entries(self) -> None:
        """Verify Resource can hold multiple entries."""
        msg1 = Message(id=Identifier(name="msg1"), value=Pattern(elements=()), attributes=())
        msg2 = Message(id=Identifier(name="msg2"), value=Pattern(elements=()), attributes=())
        resource = Resource(entries=(msg1, msg2))
        assert len(resource.entries) == 2
        assert resource.entries[0] is msg1
        assert resource.entries[1] is msg2


class TestMessageDataclass:
    """Property-based tests for Message dataclass."""

    def test_message_frozen(self) -> None:
        """Property: Message instances are immutable (frozen)."""
        msg = Message(id=Identifier(name="test"), value=Pattern(elements=()), attributes=())

        with pytest.raises((AttributeError, TypeError)):
            msg.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_message_construction_minimal(self, name: str) -> None:
        """Property: Message can be constructed with minimal fields."""
        msg = Message(id=Identifier(name=name), value=Pattern(elements=()), attributes=())
        assert msg.id.name == name
        assert msg.value == Pattern(elements=())
        assert msg.attributes == ()
        assert msg.comment is None
        assert msg.span is None

    def test_message_guard_true(self) -> None:
        """Verify Message.guard returns True for Message instances."""
        msg = Message(id=Identifier(name="test"), value=Pattern(elements=()), attributes=())
        assert Message.guard(msg) is True

    def test_message_guard_false(self) -> None:
        """Verify Message.guard returns False for non-Message objects."""
        term = Term(
            id=Identifier(name="test"),
            value=Pattern(elements=()),
            attributes=(),
        )
        assert Message.guard(term) is False


class TestTermDataclass:
    """Property-based tests for Term dataclass."""

    def test_term_frozen(self) -> None:
        """Property: Term instances are immutable (frozen)."""
        term = Term(
            id=Identifier(name="test"),
            value=Pattern(elements=()),
            attributes=(),
        )

        with pytest.raises((AttributeError, TypeError)):
            term.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_term_construction_minimal(self, name: str) -> None:
        """Property: Term can be constructed with minimal fields."""
        term = Term(
            id=Identifier(name=name),
            value=Pattern(elements=()),
            attributes=(),
        )
        assert term.id.name == name
        assert term.value.elements == ()
        assert term.attributes == ()

    def test_term_guard_true(self) -> None:
        """Verify Term.guard returns True for Term instances."""
        term = Term(
            id=Identifier(name="test"),
            value=Pattern(elements=()),
            attributes=(),
        )
        assert Term.guard(term) is True

    def test_term_guard_false(self) -> None:
        """Verify Term.guard returns False for non-Term objects."""
        msg = Message(id=Identifier(name="test"), value=Pattern(elements=()), attributes=())
        assert Term.guard(msg) is False


class TestAttributeDataclass:
    """Property-based tests for Attribute dataclass."""

    def test_attribute_frozen(self) -> None:
        """Property: Attribute instances are immutable (frozen)."""
        attr = Attribute(
            id=Identifier(name="test"),
            value=Pattern(elements=()),
        )

        with pytest.raises((AttributeError, TypeError)):
            attr.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_attribute_construction(self, name: str) -> None:
        """Property: Attribute can be constructed with any name."""
        attr = Attribute(
            id=Identifier(name=name),
            value=Pattern(elements=()),
        )
        assert attr.id.name == name
        assert attr.value.elements == ()


class TestCommentDataclass:
    """Property-based tests for Comment dataclass."""

    def test_comment_frozen(self) -> None:
        """Property: Comment instances are immutable (frozen)."""
        comment = Comment(content="test", type=CommentType.COMMENT)

        with pytest.raises((AttributeError, TypeError)):
            comment.content = "changed"  # type: ignore[misc]

    @given(st.text(), st.sampled_from(CommentType))
    def test_comment_construction(self, content: str, comment_type: CommentType) -> None:
        """Property: Comment can be constructed with any content and type."""
        comment = Comment(content=content, type=comment_type)
        assert comment.content == content
        assert comment.type is comment_type
        assert comment.span is None

    def test_comment_guard_true(self) -> None:
        """Verify Comment.guard returns True for Comment instances."""
        comment = Comment(content="test", type=CommentType.COMMENT)
        assert Comment.guard(comment) is True

    def test_comment_guard_false(self) -> None:
        """Verify Comment.guard returns False for non-Comment objects."""
        msg = Message(id=Identifier(name="test"), value=Pattern(elements=()), attributes=())
        assert Comment.guard(msg) is False


class TestJunkDataclass:
    """Property-based tests for Junk dataclass."""

    def test_junk_frozen(self) -> None:
        """Property: Junk instances are immutable (frozen)."""
        junk = Junk(content="invalid")

        with pytest.raises((AttributeError, TypeError)):
            junk.content = "changed"  # type: ignore[misc]

    @given(st.text())
    def test_junk_construction_minimal(self, content: str) -> None:
        """Property: Junk can be constructed with content only."""
        junk = Junk(content=content)
        assert junk.content == content
        assert junk.annotations == ()
        assert junk.span is None

    def test_junk_with_annotations(self) -> None:
        """Verify Junk can hold multiple annotations."""
        ann1 = Annotation(code="E001", message="Error 1")
        ann2 = Annotation(code="E002", message="Error 2")
        junk = Junk(content="bad", annotations=(ann1, ann2))
        assert len(junk.annotations) == 2
        assert junk.annotations[0] is ann1
        assert junk.annotations[1] is ann2

    def test_junk_guard_true(self) -> None:
        """Verify Junk.guard returns True for Junk instances."""
        junk = Junk(content="test")
        assert Junk.guard(junk) is True

    def test_junk_guard_false(self) -> None:
        """Verify Junk.guard returns False for non-Junk objects."""
        msg = Message(id=Identifier(name="test"), value=Pattern(elements=()), attributes=())
        assert Junk.guard(msg) is False


class TestPatternDataclass:
    """Property-based tests for Pattern dataclass."""

    def test_pattern_frozen(self) -> None:
        """Property: Pattern instances are immutable (frozen)."""
        pattern = Pattern(elements=())

        with pytest.raises((AttributeError, TypeError)):
            pattern.elements = (TextElement(value="changed"),)  # type: ignore[misc]

    def test_pattern_empty_elements(self) -> None:
        """Verify Pattern accepts empty elements tuple."""
        pattern = Pattern(elements=())
        assert pattern.elements == ()

    def test_pattern_with_text_elements(self) -> None:
        """Verify Pattern can hold text elements."""
        elem1 = TextElement(value="hello")
        elem2 = TextElement(value=" world")
        pattern = Pattern(elements=(elem1, elem2))
        assert len(pattern.elements) == 2
        assert pattern.elements[0] is elem1


class TestTextElementDataclass:
    """Property-based tests for TextElement dataclass."""

    def test_text_element_frozen(self) -> None:
        """Property: TextElement instances are immutable (frozen)."""
        elem = TextElement(value="test")

        with pytest.raises((AttributeError, TypeError)):
            elem.value = "changed"  # type: ignore[misc]

    @given(st.text())
    def test_text_element_construction(self, value: str) -> None:
        """Property: TextElement can be constructed with any text."""
        elem = TextElement(value=value)
        assert elem.value == value

    def test_text_element_guard_true(self) -> None:
        """Verify TextElement.guard returns True for TextElement instances."""
        elem = TextElement(value="test")
        assert TextElement.guard(elem) is True

    def test_text_element_guard_false(self) -> None:
        """Verify TextElement.guard returns False for non-TextElement objects."""
        placeable = Placeable(expression=StringLiteral(value="test"))
        assert TextElement.guard(placeable) is False


class TestPlaceableDataclass:
    """Property-based tests for Placeable dataclass."""

    def test_placeable_frozen(self) -> None:
        """Property: Placeable instances are immutable (frozen)."""
        placeable = Placeable(expression=StringLiteral(value="test"))

        with pytest.raises((AttributeError, TypeError)):
            placeable.expression = StringLiteral(value="changed")  # type: ignore[misc]

    def test_placeable_construction(self) -> None:
        """Verify Placeable can be constructed with any expression."""
        expr = StringLiteral(value="test")
        placeable = Placeable(expression=expr)
        assert placeable.expression is expr

    def test_placeable_guard_true(self) -> None:
        """Verify Placeable.guard returns True for Placeable instances."""
        placeable = Placeable(expression=StringLiteral(value="test"))
        assert Placeable.guard(placeable) is True

    def test_placeable_guard_false(self) -> None:
        """Verify Placeable.guard returns False for non-Placeable objects."""
        elem = TextElement(value="test")
        assert Placeable.guard(elem) is False


class TestSelectExpressionDataclass:
    """Property-based tests for SelectExpression dataclass."""

    def test_select_expression_frozen(self) -> None:
        """Property: SelectExpression instances are immutable (frozen)."""
        selector = VariableReference(id=Identifier(name="count"))
        default_variant = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="items"),)),
            default=True,
        )
        select = SelectExpression(selector=selector, variants=(default_variant,))

        with pytest.raises((AttributeError, TypeError)):
            select.selector = VariableReference(id=Identifier(name="other"))  # type: ignore[misc]

    def test_select_expression_construction(self) -> None:
        """Verify SelectExpression can be constructed with variants."""
        selector = VariableReference(id=Identifier(name="count"))
        variant = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="items"),)),
            default=True,
        )
        select = SelectExpression(selector=selector, variants=(variant,))
        assert select.selector is selector
        assert len(select.variants) == 1

    def test_select_expression_guard_true(self) -> None:
        """Verify SelectExpression.guard returns True for SelectExpression instances."""
        selector = VariableReference(id=Identifier(name="x"))
        default_variant = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=()),
            default=True,
        )
        select = SelectExpression(selector=selector, variants=(default_variant,))
        assert SelectExpression.guard(select) is True

    def test_select_expression_guard_false(self) -> None:
        """Verify SelectExpression.guard returns False for non-SelectExpression objects."""
        lit = StringLiteral(value="test")
        assert SelectExpression.guard(lit) is False


class TestVariantDataclass:
    """Property-based tests for Variant dataclass."""

    def test_variant_frozen(self) -> None:
        """Property: Variant instances are immutable (frozen)."""
        variant = Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=()),
            default=False,
        )

        with pytest.raises((AttributeError, TypeError)):
            variant.default = True  # type: ignore[misc]

    @given(st.booleans())
    def test_variant_construction(self, default: bool) -> None:
        """Property: Variant default field accepts any boolean."""
        variant = Variant(
            key=Identifier(name="test"),
            value=Pattern(elements=()),
            default=default,
        )
        assert variant.default is default


class TestStringLiteralDataclass:
    """Property-based tests for StringLiteral dataclass."""

    def test_string_literal_frozen(self) -> None:
        """Property: StringLiteral instances are immutable (frozen)."""
        lit = StringLiteral(value="test")

        with pytest.raises((AttributeError, TypeError)):
            lit.value = "changed"  # type: ignore[misc]

    @given(st.text())
    def test_string_literal_construction(self, value: str) -> None:
        """Property: StringLiteral can be constructed with any string."""
        lit = StringLiteral(value=value)
        assert lit.value == value


class TestNumberLiteralDataclass:
    """Property-based tests for NumberLiteral dataclass."""

    def test_number_literal_frozen(self) -> None:
        """Property: NumberLiteral instances are immutable (frozen)."""
        lit = NumberLiteral(value=42, raw="42")

        with pytest.raises((AttributeError, TypeError)):
            lit.value = 43  # type: ignore[misc]

    @given(st.integers())
    def test_number_literal_int_construction(self, value: int) -> None:
        """Property: NumberLiteral accepts integer values."""
        raw = str(value)
        lit = NumberLiteral(value=value, raw=raw)
        assert lit.value == value
        assert lit.raw == raw

    @given(st.decimals(allow_nan=False, allow_infinity=False))
    def test_number_literal_decimal_construction(self, value: Decimal) -> None:
        """Property: NumberLiteral accepts Decimal values."""
        raw = format(value, "f")
        lit = NumberLiteral(value=value, raw=raw)
        assert lit.value == value
        assert lit.raw == raw

    def test_number_literal_guard_true(self) -> None:
        """Verify NumberLiteral.guard returns True for NumberLiteral instances."""
        lit = NumberLiteral(value=42, raw="42")
        assert NumberLiteral.guard(lit) is True

    def test_number_literal_guard_false(self) -> None:
        """Verify NumberLiteral.guard returns False for non-NumberLiteral objects."""
        ident = Identifier(name="test")
        assert NumberLiteral.guard(ident) is False

    def test_bool_true_value_rejected(self) -> None:
        """NumberLiteral rejects bool True for value (bool is a subclass of int)."""
        with pytest.raises(TypeError, match="not bool"):
            NumberLiteral(value=True, raw="1")

    def test_bool_false_value_rejected(self) -> None:
        """NumberLiteral rejects bool False for value (bool is a subclass of int)."""
        with pytest.raises(TypeError, match="not bool"):
            NumberLiteral(value=False, raw="0")

    def test_unparseable_raw_raises_value_error(self) -> None:
        """NumberLiteral rejects raw strings that are not parseable as numbers."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=1, raw="not-a-number")

    def test_empty_raw_raises_value_error(self) -> None:
        """NumberLiteral rejects empty raw string."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=1, raw="")

    def test_raw_value_divergence_raises_value_error(self) -> None:
        """NumberLiteral rejects raw that parses to a different value than value field."""
        with pytest.raises(ValueError, match="parses to"):
            NumberLiteral(value=Decimal("1.5"), raw="9.9")

    def test_int_raw_value_divergence_raises_value_error(self) -> None:
        """NumberLiteral rejects int raw that parses to a different integer than value."""
        with pytest.raises(ValueError, match="parses to"):
            NumberLiteral(value=42, raw="99")

    def test_non_finite_decimal_raw_raises_value_error(self) -> None:
        """NumberLiteral rejects raw that produces a non-finite Decimal (Infinity)."""
        with pytest.raises(ValueError, match="not a finite number"):
            NumberLiteral(value=Decimal("Infinity"), raw="Infinity")

    def test_nan_raw_raises_value_error(self) -> None:
        """NumberLiteral rejects raw that produces NaN."""
        with pytest.raises(ValueError, match="not a finite number"):
            NumberLiteral(value=Decimal("NaN"), raw="NaN")


class TestVariableReferenceDataclass:
    """Property-based tests for VariableReference dataclass."""

    def test_variable_reference_frozen(self) -> None:
        """Property: VariableReference instances are immutable (frozen)."""
        ref = VariableReference(id=Identifier(name="test"))

        with pytest.raises((AttributeError, TypeError)):
            ref.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_variable_reference_construction(self, name: str) -> None:
        """Property: VariableReference can be constructed with any identifier."""
        ref = VariableReference(id=Identifier(name=name))
        assert ref.id.name == name

    def test_variable_reference_guard_true(self) -> None:
        """Verify VariableReference.guard returns True for VariableReference instances."""
        ref = VariableReference(id=Identifier(name="test"))
        assert VariableReference.guard(ref) is True

    def test_variable_reference_guard_false(self) -> None:
        """Verify VariableReference.guard returns False for non-VariableReference objects."""
        lit = StringLiteral(value="test")
        assert VariableReference.guard(lit) is False


class TestMessageReferenceDataclass:
    """Property-based tests for MessageReference dataclass."""

    def test_message_reference_frozen(self) -> None:
        """Property: MessageReference instances are immutable (frozen)."""
        ref = MessageReference(id=Identifier(name="test"))

        with pytest.raises((AttributeError, TypeError)):
            ref.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_message_reference_without_attribute(self, name: str) -> None:
        """Property: MessageReference can be constructed without attribute."""
        ref = MessageReference(id=Identifier(name=name))
        assert ref.id.name == name
        assert ref.attribute is None

    def test_message_reference_with_attribute(self) -> None:
        """Verify MessageReference can be constructed with attribute."""
        ref = MessageReference(
            id=Identifier(name="msg"),
            attribute=Identifier(name="attr"),
        )
        assert ref.id.name == "msg"
        assert ref.attribute is not None
        assert ref.attribute.name == "attr"

    def test_message_reference_guard_true(self) -> None:
        """Verify MessageReference.guard returns True for MessageReference instances."""
        ref = MessageReference(id=Identifier(name="test"))
        assert MessageReference.guard(ref) is True

    def test_message_reference_guard_false(self) -> None:
        """Verify MessageReference.guard returns False for non-MessageReference objects."""
        ref = TermReference(id=Identifier(name="test"))
        assert MessageReference.guard(ref) is False


class TestTermReferenceDataclass:
    """Property-based tests for TermReference dataclass."""

    def test_term_reference_frozen(self) -> None:
        """Property: TermReference instances are immutable (frozen)."""
        ref = TermReference(id=Identifier(name="test"))

        with pytest.raises((AttributeError, TypeError)):
            ref.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_term_reference_minimal(self, name: str) -> None:
        """Property: TermReference can be constructed with minimal fields."""
        ref = TermReference(id=Identifier(name=name))
        assert ref.id.name == name
        assert ref.attribute is None
        assert ref.arguments is None

    def test_term_reference_with_attribute_and_arguments(self) -> None:
        """Verify TermReference can be constructed with all fields."""
        args = CallArguments(positional=(), named=())
        ref = TermReference(
            id=Identifier(name="term"),
            attribute=Identifier(name="attr"),
            arguments=args,
        )
        assert ref.attribute is not None
        assert ref.arguments is args

    def test_term_reference_guard_true(self) -> None:
        """Verify TermReference.guard returns True for TermReference instances."""
        ref = TermReference(id=Identifier(name="test"))
        assert TermReference.guard(ref) is True

    def test_term_reference_guard_false(self) -> None:
        """Verify TermReference.guard returns False for non-TermReference objects."""
        ref = MessageReference(id=Identifier(name="test"))
        assert TermReference.guard(ref) is False


class TestFunctionReferenceDataclass:
    """Property-based tests for FunctionReference dataclass."""

    def test_function_reference_frozen(self) -> None:
        """Property: FunctionReference instances are immutable (frozen)."""
        args = CallArguments(positional=(), named=())
        ref = FunctionReference(id=Identifier(name="TEST"), arguments=args)

        with pytest.raises((AttributeError, TypeError)):
            ref.id = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1))
    def test_function_reference_construction(self, name: str) -> None:
        """Property: FunctionReference can be constructed with any function name."""
        args = CallArguments(positional=(), named=())
        ref = FunctionReference(id=Identifier(name=name), arguments=args)
        assert ref.id.name == name
        assert ref.arguments is args

    def test_function_reference_guard_true(self) -> None:
        """Verify FunctionReference.guard returns True for FunctionReference instances."""
        args = CallArguments(positional=(), named=())
        ref = FunctionReference(id=Identifier(name="TEST"), arguments=args)
        assert FunctionReference.guard(ref) is True

    def test_function_reference_guard_false(self) -> None:
        """Verify FunctionReference.guard returns False for non-FunctionReference objects."""
        ref = VariableReference(id=Identifier(name="test"))
        assert FunctionReference.guard(ref) is False


class TestCallArgumentsDataclass:
    """Property-based tests for CallArguments dataclass."""

    def test_call_arguments_frozen(self) -> None:
        """Property: CallArguments instances are immutable (frozen)."""
        args = CallArguments(positional=(), named=())

        with pytest.raises((AttributeError, TypeError)):
            args.positional = (StringLiteral(value="test"),)  # type: ignore[misc]

    def test_call_arguments_empty(self) -> None:
        """Verify CallArguments accepts empty tuples."""
        args = CallArguments(positional=(), named=())
        assert args.positional == ()
        assert args.named == ()

    def test_call_arguments_with_positional(self) -> None:
        """Verify CallArguments can hold positional arguments."""
        pos1 = StringLiteral(value="arg1")
        pos2 = NumberLiteral(value=42, raw="42")
        args = CallArguments(positional=(pos1, pos2), named=())
        assert len(args.positional) == 2
        assert args.positional[0] is pos1

    def test_call_arguments_with_named(self) -> None:
        """Verify CallArguments can hold named arguments."""
        named1 = NamedArgument(
            name=Identifier(name="key"),
            value=StringLiteral(value="val"),
        )
        args = CallArguments(positional=(), named=(named1,))
        assert len(args.named) == 1
        assert args.named[0] is named1


class TestNamedArgumentDataclass:
    """Property-based tests for NamedArgument dataclass."""

    def test_named_argument_frozen(self) -> None:
        """Property: NamedArgument instances are immutable (frozen)."""
        arg = NamedArgument(
            name=Identifier(name="key"),
            value=StringLiteral(value="val"),
        )

        with pytest.raises((AttributeError, TypeError)):
            arg.name = Identifier(name="changed")  # type: ignore[misc]

    @given(st.text(min_size=1), st.text())
    def test_named_argument_construction(self, name: str, value: str) -> None:
        """Property: NamedArgument can be constructed with any name and value."""
        arg = NamedArgument(
            name=Identifier(name=name),
            value=StringLiteral(value=value),
        )
        assert arg.name.name == name
        assert isinstance(arg.value, StringLiteral)
