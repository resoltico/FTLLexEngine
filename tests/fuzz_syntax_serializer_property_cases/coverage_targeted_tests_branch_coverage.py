# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Coverage-Targeted Tests (Branch Coverage)
# =============================================================================


class TestCoverageTargeted:
    """Tests targeting specific coverage gaps."""

    @given(func_ref=ftl_function_references_no_args())
    def test_function_reference_without_arguments(self, func_ref: FunctionReference) -> None:
        """COVERAGE: Branch 238 - FunctionReference without arguments.

        Events emitted:
        - coverage_target=function_no_args: Branch target
        """
        event("coverage_target=function_no_args")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain function name followed by empty parens
        assert f"{func_ref.id.name}()" in serialized

    @given(junk=ftl_junk_nodes())
    def test_junk_serialization(self, junk: Junk) -> None:
        """COVERAGE: Branch 429 - Junk serialization.

        Events emitted:
        - coverage_target=junk: Branch target
        - junk_has_trailing_newline={bool}: Content structure
        """
        event("coverage_target=junk")
        event(f"junk_has_trailing_newline={junk.content.endswith('\\n')}")

        resource = Resource(entries=(junk,))

        serialized = serialize(resource, validate=False)  # Junk may be invalid

        # Junk content should be preserved as-is (with trailing newline added if missing)
        if junk.content.endswith("\n"):
            assert junk.content in serialized
        else:
            assert junk.content + "\n" in serialized

    @given(select_expr=ftl_select_expressions_with_number_keys())
    def test_select_expression_number_keys(self, select_expr: SelectExpression) -> None:
        """COVERAGE: Branch 804 - NumberLiteral variant keys.

        Events emitted:
        - coverage_target=select_number_keys: Branch target
        """
        event("coverage_target=select_number_keys")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain numeric variant keys
        assert "[0]" in serialized or "[1]" in serialized

    @given(placeable=ftl_placeables())
    def test_placeable_in_pattern(self, placeable: Placeable) -> None:
        """COVERAGE: Branch 616 - Placeable in pattern.

        Events emitted:
        - coverage_target=placeable_in_pattern: Branch target
        - placeable_expr_type={type}: Expression type
        """
        event("coverage_target=placeable_in_pattern")
        event(f"placeable_expr_type={type(placeable.expression).__name__}")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain placeable delimiters
        assert "{ " in serialized
        assert " }" in serialized

    @given(select_expr=ftl_select_expressions())
    def test_select_expression_serialization(self, select_expr: SelectExpression) -> None:
        """COVERAGE: Branch 749 - SelectExpression serialization.

        Events emitted:
        - coverage_target=select_expression: Branch target
        - variant_count={n}: Number of variants
        """
        event("coverage_target=select_expression")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Emit variant count for HypoFuzz
        event(f"variant_count={len(select_expr.variants)}")

        # Should contain select syntax
        assert "->" in serialized
        # Should contain at least one default variant marker
        assert "*[" in serialized

    @given(comment=ftl_comment_nodes())
    def test_comment_serialization(self, comment: Comment) -> None:
        """COVERAGE: Comment serialization.

        Events emitted:
        - coverage_target=comment: Branch target
        - comment_type={type}: Comment type
        """
        event("coverage_target=comment")
        event(f"comment_type={comment.type.name}")

        resource = Resource(entries=(comment,))

        serialized = serialize(resource, validate=False)

        # Should contain comment prefix
        assert "#" in serialized
