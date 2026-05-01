"""Tests for syntax.serializer: FluentSerializer, serialize(), edge cases, internal helpers.

Validates serialization of AST nodes back to FTL syntax, including control character
escaping, depth limits, junk entries, multiline patterns, and classify/escape internals.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.enums import CommentType
from ftllexengine.syntax import serialize
from ftllexengine.syntax.ast import (
    Annotation,
    Attribute,
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
    StringLiteral,
    Term,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import (
    SerializationDepthError,
    _validate_resource,
)

# =============================================================================
# Defensive re-raise tests (covers lines 286, 449)
# =============================================================================


class TestDefensiveReRaises:
    """Test defensive re-raise paths for non-RESOLUTION FrozenFluentError."""

    def test_validate_resource_non_resolution_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-RESOLUTION FrozenFluentError re-raised from validation (line 286)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="hello"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        def fake_validate_pattern(
            _pattern: Pattern,
            _context: str,
            _depth_guard: object,
        ) -> None:
            raise FrozenFluentError(
                message="Test non-resolution error",
                category=ErrorCategory.PARSE,
            )

        monkeypatch.setattr(
            "ftllexengine.syntax.serializer._validate_pattern",
            fake_validate_pattern,
        )

        with pytest.raises(FrozenFluentError, match="non-resolution"):
            _validate_resource(resource)

    def test_serialize_non_resolution_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-RESOLUTION FrozenFluentError re-raised from serialization (line 449)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="hello"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        def fake_serialize_resource(
            _self: object,
            _node: Resource,
            _output: list[str],
            _depth_guard: object,
        ) -> None:
            raise FrozenFluentError(
                message="Test serialize non-resolution",
                category=ErrorCategory.PARSE,
            )

        monkeypatch.setattr(
            "ftllexengine.syntax.serializer.FluentSerializer._serialize_resource",
            fake_serialize_resource,
        )

        with pytest.raises(FrozenFluentError, match="serialize non-resolution"):
            serialize(resource, validate=False)


class TestSerializerSelectorDepthGuard:
    """Serializer wraps SelectExpression selector in depth guard.

    A well-formed SelectExpression with a variable selector serializes normally.
    A malformed AST where SelectExpression is nested as its own selector (impossible
    in parsed FTL, but constructible via the API) must raise SerializationDepthError
    before triggering a RecursionError.
    """

    def test_valid_select_expression_serializes(self) -> None:
        """SelectExpression with variable selector serializes to valid FTL."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415 - import inside function

        select = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=NumberLiteral(raw="1", value=1),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert "msg" in result
        assert "$x ->" in result

    def test_deeply_nested_selector_raises_depth_error(self) -> None:
        """Malformed deeply-nested SelectExpression selector raises SerializationDepthError."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415 - import inside function

        def make_nested_select(depth: int) -> SelectExpression:
            if depth == 0:
                return SelectExpression(
                    selector=VariableReference(id=Identifier("x")),
                    variants=(
                        Variant(
                            key=Identifier("a"),
                            value=Pattern(elements=(TextElement("A"),)),
                            default=False,
                        ),
                        Variant(
                            key=Identifier("other"),
                            value=Pattern(elements=(TextElement("B"),)),
                            default=True,
                        ),
                    ),
                )
            inner = make_nested_select(depth - 1)
            # Intentionally malformed: SelectExpression as its own selector
            return SelectExpression(
                selector=inner,  # type: ignore[arg-type]
                variants=(
                    Variant(
                        key=Identifier("a"),
                        value=Pattern(elements=(TextElement("A"),)),
                        default=False,
                    ),
                    Variant(
                        key=Identifier("other"),
                        value=Pattern(elements=(TextElement("B"),)),
                        default=True,
                    ),
                ),
            )

        nested = make_nested_select(150)
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=nested),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource, max_depth=50)


# ============================================================================
# SERIALIZER BRANCH COVERAGE
# ============================================================================


class TestSerializerBranchCoverage:
    """Test serializer branch coverage."""

    def test_serialize_junk_entry(self) -> None:
        """Junk entry without annotations is serialized as its raw content."""
        junk = Junk(content="invalid content here")
        resource = Resource(entries=(junk,))

        result = serialize(resource)

        assert "invalid content here" in result

    def test_serialize_text_without_braces(self) -> None:
        """Message with plain text content serializes correctly."""
        message = Message(
            id=Identifier("simple"),
            value=Pattern(elements=(TextElement("Plain text without braces"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "simple = Plain text without braces" in result

    def test_serialize_text_with_braces(self) -> None:
        """Text with literal braces serializes via StringLiteral placeables."""
        message = Message(
            id=Identifier("braced"),
            value=Pattern(
                elements=(
                    TextElement("a"),
                    Placeable(expression=StringLiteral(value="{")),
                    TextElement("b"),
                    Placeable(expression=StringLiteral(value="}")),
                    TextElement("c"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "braced" in result

    def test_serialize_select_expression(self) -> None:
        """SelectExpression with default variant serializes with *[other]."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("one"),
                    value=Pattern(elements=(TextElement("One item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Many items"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("plural"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "plural" in result
        assert "*[other]" in result

    def test_serialize_number_literal_variant_key(self) -> None:
        """Variant with NumberLiteral key serializes as [1]."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("numkey"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[1]" in result
        assert "*[other]" in result

    def test_serialize_nested_placeable(self) -> None:
        """Nested Placeable (Placeable inside Placeable) serializes with double braces."""
        inner = Placeable(expression=VariableReference(id=Identifier("inner")))
        outer = Placeable(expression=inner)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "{ { $inner } }" in result


class TestSerializerBranchCoverageExtended:
    """Extended serializer branch coverage tests."""

    def test_serialize_message_with_comment(self) -> None:
        """Message with attached comment serializes comment on separate line."""
        comment = Comment(content="Message comment", type=CommentType.COMMENT)
        message = Message(
            id=Identifier("commented"),
            value=Pattern(elements=(TextElement("Value"),)),
            attributes=(),
            comment=comment,
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "# Message comment" in result
        assert "commented = Value" in result

    def test_serialize_term_with_attributes(self) -> None:
        """Term with attributes serializes term and all attributes."""
        term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier("gender"),
                    value=Pattern(elements=(TextElement("masculine"),)),
                ),
            ),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert "-brand = Firefox" in result
        assert ".gender = masculine" in result

    def test_serialize_function_with_named_args(self) -> None:
        """Function call with named arguments serializes with correct syntax."""
        func_ref = FunctionReference(
            id=Identifier("NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier("count")),),
                named=(
                    NamedArgument(
                        name=Identifier("style"),
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier("percent"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "NUMBER" in result
        assert "style" in result


class TestSerializerJunkCoverage:
    """Junk entry with annotations serializes raw content."""

    def test_serialize_junk_entry_with_annotations(self) -> None:
        """Junk entry with annotations is serialized as its raw content."""
        junk = Junk(
            content="this is not valid FTL",
            annotations=(Annotation(code="E0003", message="Expected token: ="),),
        )
        resource = Resource(entries=(junk,))

        ftl = serialize(resource)

        assert "this is not valid FTL" in ftl


class TestSerializerPlaceableCoverage:
    """Placeable serialization branch coverage."""

    def test_serialize_placeable_in_pattern(self) -> None:
        """Placeable in pattern serializes with correct brace syntax."""
        placeable = Placeable(expression=VariableReference(id=Identifier(name="name")))
        pattern = Pattern(elements=(TextElement(value="Hello "), placeable))
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "{ $name }" in ftl


class TestSerializerNumberLiteralVariantKeyCoverage:
    """NumberLiteral variant key serialization."""

    def test_serialize_select_with_number_literal_key(self) -> None:
        """Variant with NumberLiteral keys serializes as [1], [2], *[other]."""
        variant1 = Variant(
            key=NumberLiteral(value=1, raw="1"),
            value=Pattern(elements=(TextElement(value="one item"),)),
            default=False,
        )
        variant2 = Variant(
            key=NumberLiteral(value=2, raw="2"),
            value=Pattern(elements=(TextElement(value="two items"),)),
            default=False,
        )
        variant_other = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="many items"),)),
            default=True,
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(variant1, variant2, variant_other),
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="items"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "[1]" in ftl
        assert "[2]" in ftl
        assert "*[other]" in ftl


class TestSerializerStringLiteralEscapesCoverage:
    """Control character escaping in StringLiteral values."""

    def test_serialize_string_literal_with_tab(self) -> None:
        """Tab character in StringLiteral is escaped as \\u0009."""
        expr = StringLiteral(value="Hello\tWorld")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="tabbed"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u0009" in ftl

    def test_serialize_string_literal_with_newline(self) -> None:
        """Newline character in StringLiteral is escaped as \\u000A."""
        expr = StringLiteral(value="Line1\nLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="multiline"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u000A" in ftl

    def test_serialize_string_literal_with_carriage_return(self) -> None:
        """Carriage return in StringLiteral is escaped as \\u000D."""
        expr = StringLiteral(value="Line1\rLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="crlf"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u000D" in ftl


class TestSerializerBranchExhaustive:
    """Exhaustive branch coverage for serializer dispatch."""

    def test_serialize_empty_pattern(self) -> None:
        """Pattern with no elements serializes as empty value line."""
        pattern = Pattern(elements=())
        message = Message(
            id=Identifier(name="empty"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "empty = \n" in ftl

    def test_serialize_text_only_pattern(self) -> None:
        """Pattern with multiple TextElements concatenates them."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
                TextElement(value="!"),
            )
        )
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "greeting = Hello World!\n" in ftl

    def test_serialize_multiple_junk_entries(self) -> None:
        """Multiple Junk entries all serialize as their raw content."""
        junk1 = Junk(content="bad syntax 1")
        junk2 = Junk(content="bad syntax 2")
        resource = Resource(entries=(junk1, junk2))

        ftl = serialize(resource)
        assert "bad syntax 1" in ftl
        assert "bad syntax 2" in ftl

    def test_serialize_select_number_only_variants(self) -> None:
        """Select with only NumberLiteral keys serializes correctly."""
        variants = (
            Variant(
                key=NumberLiteral(value=0, raw="0"),
                value=Pattern(elements=(TextElement(value="zero"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="one"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="n")),
            variants=variants,
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="count"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "[0] zero" in ftl
        assert "*[1] one" in ftl


class TestSerializerVariantCountProperty:
    """Property-based test for serializer with varying variant counts."""

    @given(
        st.integers(min_value=1, max_value=10),
    )
    def test_serializer_handles_multiple_variants(self, variant_count: int) -> None:
        """Serializer handles select expressions with varying variant counts."""
        event(f"variant_count={variant_count}")
        variants = [
            Variant(
                key=Identifier(f"key{i}"),
                value=Pattern(elements=(TextElement(f"Value {i}"),)),
                default=(i == variant_count - 1),
            )
            for i in range(variant_count)
        ]

        select = SelectExpression(
            selector=VariableReference(id=Identifier("sel")),
            variants=tuple(variants),
        )

        message = Message(
            id=Identifier("multi"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        for i in range(variant_count):
            assert f"key{i}" in result
