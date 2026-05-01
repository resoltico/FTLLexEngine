# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor_transformer.py."""

from tests.syntax_visitor_transformer_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TESTS FOR _TRANSFORM_LIST EDGE CASES
# ============================================================================


class TestTransformListNodeManagement:
    """Test edge cases in _transform_list (line 552 and match branches)."""

    def test_transform_list_with_none_removal(self) -> None:
        """_transform_list handles None results (node removal)."""

        class RemoveFirstElementTransformer(ASTTransformer):
            """Remove first element from pattern."""

            def __init__(self) -> None:
                """Initialize transformer."""
                super().__init__()
                self.first_text_seen = False

            def visit_TextElement(self, node: TextElement) -> TextElement | None:
                """Remove first text element."""
                if not self.first_text_seen:
                    self.first_text_seen = True
                    return None
                return node

        pattern = Pattern(
            elements=(
                TextElement(value="First"),
                TextElement(value="Second"),
                TextElement(value="Third"),
            )
        )

        transformer = RemoveFirstElementTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert len(result.elements) == 2
        assert result.elements[0].value == "Second"  # type: ignore[union-attr]
        assert result.elements[1].value == "Third"  # type: ignore[union-attr]

    def test_transform_list_with_expansion(self) -> None:
        """_transform_list handles list results (node expansion)."""

        class DuplicateTextElementTransformer(ASTTransformer):
            """Duplicate text elements."""

            def visit_TextElement(self, node: TextElement) -> list[TextElement]:
                """Duplicate each text element."""
                return [node, TextElement(value=f"{node.value}_copy")]

        pattern = Pattern(
            elements=(
                TextElement(value="Hello"),
                TextElement(value="World"),
            )
        )

        transformer = DuplicateTextElementTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert len(result.elements) == 4
        assert result.elements[0].value == "Hello"  # type: ignore[union-attr]
        assert result.elements[1].value == "Hello_copy"  # type: ignore[union-attr]
        assert result.elements[2].value == "World"  # type: ignore[union-attr]
        assert result.elements[3].value == "World_copy"  # type: ignore[union-attr]

    def test_transform_list_with_single_replacement(self) -> None:
        """_transform_list handles single ASTNode results (replacement, line 552)."""

        class UppercaseTextTransformer(ASTTransformer):
            """Uppercase text elements."""

            def visit_TextElement(self, node: TextElement) -> TextElement:
                """Uppercase text."""
                return TextElement(value=node.value.upper())

        pattern = Pattern(
            elements=(
                TextElement(value="hello"),
                TextElement(value="world"),
            )
        )

        transformer = UppercaseTextTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert len(result.elements) == 2
        assert result.elements[0].value == "HELLO"  # type: ignore[union-attr]
        assert result.elements[1].value == "WORLD"  # type: ignore[union-attr]

    def test_transform_list_mixed_operations(self) -> None:
        """_transform_list handles mix of None, list, and single node returns."""

        class MixedTransformer(ASTTransformer):
            """Transform with mixed return types."""

            def __init__(self) -> None:
                """Initialize transformer."""
                super().__init__()
                self.element_count = 0

            def visit_TextElement(
                self, node: TextElement
            ) -> TextElement | None | list[TextElement]:
                """Return different types based on position."""
                self.element_count += 1

                match self.element_count:
                    case 1:
                        # Remove first element
                        return None
                    case 2:
                        # Expand second element
                        return [
                            TextElement(value=f"{node.value}_a"),
                            TextElement(value=f"{node.value}_b"),
                        ]
                    case _:
                        # Keep remaining elements (single node)
                        return node

        pattern = Pattern(
            elements=(
                TextElement(value="first"),
                TextElement(value="second"),
                TextElement(value="third"),
            )
        )

        transformer = MixedTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        # First removed, second expanded to 2, third kept = 3 elements
        assert len(result.elements) == 3
        assert result.elements[0].value == "second_a"  # type: ignore[union-attr]
        assert result.elements[1].value == "second_b"  # type: ignore[union-attr]
        assert result.elements[2].value == "third"  # type: ignore[union-attr]
