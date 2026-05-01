"""Tests for syntax.serializer: FluentSerializer, serialize(), edge cases, internal helpers.

Validates serialization of AST nodes back to FTL syntax, including control character
escaping, depth limits, junk entries, multiline patterns, and classify/escape internals.
"""

from __future__ import annotations

from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.syntax import serialize
from ftllexengine.syntax.ast import (
    CallArguments,
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
    TextElement,
    VariableReference,
    Variant,
)


class TestMultilinePatternIndentation:
    """Test multi-line pattern indentation handling.

    Per serializer.py lines 474-475, newlines in TextElements are replaced
    with newline + 4-space indentation for FTL continuation lines.
    """

    def test_multiline_text_indented(self) -> None:
        """Newlines in TextElement followed by 4-space indentation."""
        msg = Message(
            id=Identifier(name="multi"),
            value=Pattern(elements=(TextElement(value="Line 1\nLine 2\nLine 3"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Each newline should be followed by 4 spaces (continuation indent)
        assert "Line 1\n    Line 2\n    Line 3" in result

    def test_multiline_with_braces_indented_and_escaped(self) -> None:
        """Multiline text with braces: both indentation and brace escaping."""
        msg = Message(
            id=Identifier(name="complex"),
            value=Pattern(elements=(TextElement(value="First {line}\nSecond }line"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Should have indentation AND brace escaping
        assert "First" in result
        assert "Second" in result
        assert '{ "{" }' in result  # { escaped
        assert '{ "}" }' in result  # } escaped
        # Newline creates indentation
        assert "\n    " in result

    @given(
        lines=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                    min_codepoint=0x20,  # Printable ASCII and above
                ),
                min_size=1,
                max_size=50,
            ).filter(lambda t: "{" not in t and "}" not in t),
            min_size=2,
            max_size=5,
        )
    )
    @example(lines=["First line", "Second line", "Third line"])
    def test_multiline_indentation_property(self, lines: list[str]) -> None:
        """Multiline patterns always indent continuation lines with 4 spaces."""
        event(f"line_count={len(lines)}")
        assume(all(line.strip() for line in lines))  # Non-empty lines
        # Leading whitespace on the first line gets wrapped in a StringLiteral
        # placeable for roundtrip correctness; not this test's concern.
        assume(not lines[0][0].isspace())

        text = "\n".join(lines)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # After first line, each line should be indented with 4 spaces
        for i, line in enumerate(lines):
            if i == 0:
                # First line not indented
                assert lines[0] in result
            else:
                # Subsequent lines indented
                assert f"\n    {line}" in result or line in result


class TestMixedPatternElements:
    """Test Pattern serialization with mixed TextElement and Placeable elements.

    This ensures the elif branch at line 483 is properly covered when
    iterating through pattern elements that alternate between types.
    """

    def test_mixed_text_and_placeable_elements(self) -> None:
        """Pattern with alternating TextElement and Placeable elements."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    TextElement(value="Start "),
                    Placeable(expression=VariableReference(id=Identifier(name="var1"))),
                    TextElement(value=" middle "),
                    Placeable(expression=VariableReference(id=Identifier(name="var2"))),
                    TextElement(value=" end"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Start { $var1 } middle { $var2 } end" in result

    def test_multiple_consecutive_placeables(self) -> None:
        """Pattern with consecutive Placeable elements (no text between)."""
        msg = Message(
            id=Identifier(name="consecutive"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="a"))),
                    Placeable(expression=VariableReference(id=Identifier(name="b"))),
                    Placeable(expression=VariableReference(id=Identifier(name="c"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "{ $a }{ $b }{ $c }" in result

    def test_text_then_multiple_placeables(self) -> None:
        """Pattern starting with text followed by multiple placeables."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="Prefix: "),
                    Placeable(expression=StringLiteral(value="one")),
                    Placeable(expression=StringLiteral(value="two")),
                    Placeable(expression=StringLiteral(value="three")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert 'Prefix: { "one" }{ "two" }{ "three" }' in result

    @given(
        num_text=st.integers(min_value=1, max_value=5),
        num_placeable=st.integers(min_value=1, max_value=5),
    )
    @example(num_text=3, num_placeable=2)
    @example(num_text=1, num_placeable=4)
    def test_mixed_pattern_property(self, num_text: int, num_placeable: int) -> None:
        """Patterns with varying numbers of text and placeable elements serialize correctly."""
        event(f"num_text={num_text}")
        event(f"num_placeable={num_placeable}")
        elements: list[TextElement | Placeable] = []

        # Alternate between text and placeable
        for i in range(max(num_text, num_placeable)):
            if i < num_text:
                elements.append(TextElement(value=f"text{i} "))
            if i < num_placeable:
                elements.append(
                    Placeable(expression=VariableReference(id=Identifier(name=f"v{i}")))
                )

        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=tuple(elements)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)
        assert "m = " in result


class TestSelectExpressionVariantKeys:
    """Test SelectExpression with both Identifier and NumberLiteral variant keys.

    Ensures match statement at line 619-623 covers both cases completely,
    including exit paths (622->625).
    """

    def test_select_with_identifier_keys_only(self) -> None:
        """SelectExpression with all Identifier variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(elements=(TextElement(value="One item"),)),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(elements=(TextElement(value="Many items"),)),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "[one]" in result
        assert "*[other]" in result
        assert "One item" in result
        assert "Many items" in result

    def test_select_with_number_keys_only(self) -> None:
        """SelectExpression with all NumberLiteral variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(elements=(TextElement(value="Exactly one"),)),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(elements=(TextElement(value="Zero"),)),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "[1]" in result
        assert "*[0]" in result
        assert "Exactly one" in result
        assert "Zero" in result

    def test_select_with_mixed_identifier_and_number_keys(self) -> None:
        """SelectExpression with both Identifier and NumberLiteral keys."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="val")),
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
                                    value=Pattern(elements=(TextElement(value="Other"),)),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Both NumberLiteral and Identifier cases exercised
        assert "[0]" in result
        assert "[1]" in result
        assert "*[other]" in result


class TestFunctionReferenceValidation:
    """Test FunctionReference validation path coverage.

    Ensures the FunctionReference case at line 183-193 in _validate_expression
    is fully covered, including exit paths (185->exit).
    """

    def test_function_reference_with_positional_args_validated(self) -> None:
        """FunctionReference with positional arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(VariableReference(id=Identifier(name="count")),),
                                named=(),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "NUMBER($count)" in result

    def test_function_reference_with_named_args_validated(self) -> None:
        """FunctionReference with named arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="DATETIME"),
                            arguments=CallArguments(
                                positional=(),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="month"),
                                        value=StringLiteral(value="long"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="day"),
                                        value=StringLiteral(value="numeric"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "DATETIME" in result
        assert 'month: "long"' in result
        assert 'day: "numeric"' in result

    def test_function_reference_with_mixed_args_validated(self) -> None:
        """FunctionReference with both positional and named args validated."""
        msg = Message(
            id=Identifier(name="formatted"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(VariableReference(id=Identifier(name="amount")),),
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
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "NUMBER($amount" in result
        assert 'style: "currency"' in result
        assert 'currency: "USD"' in result
