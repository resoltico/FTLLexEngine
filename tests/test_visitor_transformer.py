"""Coverage tests for visitor.py Transformer class.

Targets uncovered lines in visitor.py (lines 303, 315, 321, 324, 330, 336, 343, 345, 351, 353, 382):
- Term transformation (line 303)
- SelectExpression transformation (line 315)
- Variant transformation (line 321)
- FunctionReference transformation (line 324)
- MessageReference transformation (line 330)
- TermReference transformation (line 336)
- VariableReference transformation (line 343)
- CallArguments transformation (line 345)
- NamedArgument transformation (line 351)
- Attribute transformation (line 353)
- _transform_list edge cases (line 382)
"""

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.visitor import ASTTransformer


class UppercaseIdentifierTransformer(ASTTransformer):
    """Test transformer that uppercases all identifiers."""

    def visit_Identifier(self, node: Identifier) -> Identifier:
        """Uppercase identifier names."""
        return Identifier(name=node.name.upper())


class TestTermTransformation:
    """Test Term node transformation (line 303)."""

    def test_transform_term_with_value(self) -> None:
        """Transform a Term with value and attributes."""
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Acme Corp"),)),
            attributes=(
                Attribute(
                    id=Identifier(name="legal"),
                    value=Pattern(elements=(TextElement(value="Acme Corporation"),)),
                ),
            ),
            comment=None,
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(term)

        # Should transform all identifiers to uppercase
        assert isinstance(result, Term)
        assert result.id.name == "BRAND"
        assert result.attributes[0].id.name == "LEGAL"


class TestSelectExpressionTransformation:
    """Test SelectExpression transformation (line 315)."""

    def test_transform_select_expression(self) -> None:
        """Transform SelectExpression with variants."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="one item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="many items"),)),
                    default=True,
                ),
            ),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(select)

        # Should transform all identifiers
        assert isinstance(result, SelectExpression)
        assert result.selector.id.name == "COUNT"  # type: ignore[union-attr]
        assert result.variants[0].key.name == "ONE"  # type: ignore[union-attr]
        assert result.variants[1].key.name == "OTHER"  # type: ignore[union-attr]


class TestVariantTransformation:
    """Test Variant transformation (line 321)."""

    def test_transform_variant(self) -> None:
        """Transform Variant with key and value."""
        variant = Variant(
            key=Identifier(name="zero"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(id=Identifier(name="count"))
                    ),
                )
            ),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(variant)

        # Should transform identifiers in key and value
        assert isinstance(result, Variant)
        assert result.key.name == "ZERO"  # type: ignore[union-attr]
        assert result.value.elements[0].expression.id.name == "COUNT"  # type: ignore[union-attr]


class TestFunctionReferenceTransformation:
    """Test FunctionReference transformation (line 324)."""

    def test_transform_function_reference(self) -> None:
        """Transform FunctionReference with arguments."""
        func_ref = FunctionReference(
            id=Identifier(name="number"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="amount")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="minimumFractionDigits"),
                        value=NumberLiteral(value=2, raw="2"),
                    ),
                ),
            ),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(func_ref)

        # Should transform all identifiers
        assert isinstance(result, FunctionReference)
        assert result.id.name == "NUMBER"
        assert result.arguments.positional[0].id.name == "AMOUNT"  # type: ignore[union-attr]
        assert result.arguments.named[0].name.name == "MINIMUMFRACTIONDIGITS"


class TestMessageReferenceTransformation:
    """Test MessageReference transformation (line 330)."""

    def test_transform_message_reference_without_attribute(self) -> None:
        """Transform MessageReference without attribute."""
        msg_ref = MessageReference(
            id=Identifier(name="welcome"), attribute=None
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(msg_ref)

        assert isinstance(result, MessageReference)
        assert result.id.name == "WELCOME"
        assert result.attribute is None

    def test_transform_message_reference_with_attribute(self) -> None:
        """Transform MessageReference with attribute."""
        msg_ref = MessageReference(
            id=Identifier(name="welcome"),
            attribute=Identifier(name="tooltip"),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(msg_ref)

        assert isinstance(result, MessageReference)
        assert result.id.name == "WELCOME"
        assert result.attribute.name == "TOOLTIP"  # type: ignore[union-attr]


class TestTermReferenceTransformation:
    """Test TermReference transformation (line 336)."""

    def test_transform_term_reference_simple(self) -> None:
        """Transform TermReference without attribute or arguments."""
        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=None,
            arguments=None,
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(term_ref)

        assert isinstance(result, TermReference)
        assert result.id.name == "BRAND"
        assert result.attribute is None
        assert result.arguments is None

    def test_transform_term_reference_with_attribute_and_arguments(self) -> None:
        """Transform TermReference with attribute and arguments."""
        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="legal"),
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

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(term_ref)

        assert isinstance(result, TermReference)
        assert result.id.name == "BRAND"
        assert result.attribute.name == "LEGAL"  # type: ignore[union-attr]
        assert result.arguments.named[0].name.name == "CASE"  # type: ignore[union-attr]


class TestVariableReferenceTransformation:
    """Test VariableReference transformation (line 343)."""

    def test_transform_variable_reference(self) -> None:
        """Transform VariableReference."""
        var_ref = VariableReference(id=Identifier(name="userName"))

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(var_ref)

        assert isinstance(result, VariableReference)
        assert result.id.name == "USERNAME"


class TestCallArgumentsTransformation:
    """Test CallArguments transformation (line 345)."""

    def test_transform_call_arguments(self) -> None:
        """Transform CallArguments with positional and named arguments."""
        call_args = CallArguments(
            positional=(
                VariableReference(id=Identifier(name="value")),
                NumberLiteral(value=42, raw="42"),
            ),
            named=(
                NamedArgument(
                    name=Identifier(name="option"),
                    value=VariableReference(id=Identifier(name="opt")),
                ),
            ),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(call_args)

        assert isinstance(result, CallArguments)
        assert result.positional[0].id.name == "VALUE"  # type: ignore[union-attr]
        assert result.positional[1].value == 42  # type: ignore[union-attr]
        assert result.named[0].name.name == "OPTION"
        assert result.named[0].value.id.name == "OPT"  # type: ignore[union-attr]


class TestNamedArgumentTransformation:
    """Test NamedArgument transformation (line 351)."""

    def test_transform_named_argument(self) -> None:
        """Transform NamedArgument."""
        named_arg = NamedArgument(
            name=Identifier(name="minimumFractionDigits"),
            value=VariableReference(id=Identifier(name="precision")),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(named_arg)

        assert isinstance(result, NamedArgument)
        assert result.name.name == "MINIMUMFRACTIONDIGITS"
        assert result.value.id.name == "PRECISION"  # type: ignore[union-attr]


class TestAttributeTransformation:
    """Test Attribute transformation (line 353)."""

    def test_transform_attribute(self) -> None:
        """Transform Attribute with id and value."""
        attr = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(id=Identifier(name="text"))
                    ),
                )
            ),
        )

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(attr)

        assert isinstance(result, Attribute)
        assert result.id.name == "TOOLTIP"
        assert result.value.elements[0].expression.id.name == "TEXT"  # type: ignore[union-attr]


class TestTransformListEdgeCases:
    """Test _transform_list method edge cases."""

    def test_transform_empty_tuple(self) -> None:
        """Transform empty tuple."""
        pattern = Pattern(elements=())

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert result.elements == ()

    def test_transform_large_list(self) -> None:
        """Transform large list of elements."""
        elements = tuple(
            Placeable(expression=VariableReference(id=Identifier(name=f"var{i}")))
            for i in range(100)
        )
        pattern = Pattern(elements=elements)

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert len(result.elements) == 100
        # All identifiers should be uppercased
        for i, elem in enumerate(result.elements):
            assert elem.expression.id.name == f"VAR{i}".upper()  # type: ignore[union-attr]


class TestTransformerPropertyBased:
    """Property-based tests for Transformer."""

    @given(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        )
    )
    @settings(max_examples=50)
    def test_identifier_transformation_is_idempotent(self, name: str) -> None:
        """Transforming twice yields same result (idempotency)."""
        identifier = Identifier(name=name)
        transformer = UppercaseIdentifierTransformer()

        result1 = transformer.visit(identifier)
        assert isinstance(result1, Identifier), f"Expected Identifier, got {type(result1)}"
        result2 = transformer.visit(result1)
        assert isinstance(result2, Identifier), f"Expected Identifier, got {type(result2)}"

        event("outcome=idempotent")

        # Uppercasing twice should give same result
        assert result1.name == result2.name
        assert result1.name == name.upper()

    @given(
        st.lists(
            st.text(
                min_size=1,
                max_size=10,
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            ),
            min_size=0,
            max_size=20,
        )
    )
    @settings(max_examples=30)
    def test_transform_pattern_with_variable_count(self, names: list[str]) -> None:
        """Transform pattern with arbitrary number of variables."""
        elements = tuple(
            Placeable(expression=VariableReference(id=Identifier(name=name)))
            for name in names
        )
        pattern = Pattern(elements=elements)

        transformer = UppercaseIdentifierTransformer()
        result = transformer.visit(pattern)
        assert isinstance(result, Pattern), f"Expected Pattern, got {type(result)}"

        event(f"element_count={len(names)}")

        assert len(result.elements) == len(names)
        for i, name in enumerate(names):
            elem = result.elements[i]
            assert isinstance(elem, Placeable), f"Expected Placeable, got {type(elem)}"
            assert isinstance(elem.expression, VariableReference), (
                f"Expected VariableReference, got {type(elem.expression)}"
            )
            assert elem.expression.id.name == name.upper()
