"""Hypothesis property-based tests for serializer.py to achieve 100% coverage.

Targets missing branches:
- Line 136->133: Placeable case in _visit_pattern
- Line 171->exit: SelectExpression case in _visit_expression
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize

# ============================================================================
# COVERAGE TARGET: Line 136->133 (Placeable in Pattern)
# ============================================================================


class TestPlaceablePatternCoverage:
    """Test Placeable branch in _visit_pattern (line 136->133)."""

    def test_pattern_with_placeable_variable(self) -> None:
        """COVERAGE: Line 136->133 - Pattern with placeable variable."""
        parser = FluentParserV1()
        ftl_source = "msg = Hello { $name }!"

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        assert "{ $name }" in serialized
        assert "msg" in serialized

    def test_pattern_with_multiple_placeables(self) -> None:
        """COVERAGE: Line 136->133 - Pattern with multiple placeables."""
        parser = FluentParserV1()
        ftl_source = "msg = { $a } and { $b } and { $c }"

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        assert "{ $a }" in serialized
        assert "{ $b }" in serialized
        assert "{ $c }" in serialized

    def test_pattern_with_placeable_function(self) -> None:
        """COVERAGE: Line 136->133 - Pattern with function placeable."""
        parser = FluentParserV1()
        ftl_source = "msg = Price: { NUMBER($amount) }"

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        assert "NUMBER" in serialized
        assert "$amount" in serialized

    @given(var_name=st.from_regex(r"[a-z]+", fullmatch=True))
    def test_placeable_pattern_property(self, var_name: str) -> None:
        """PROPERTY: Placeable serialization roundtrips correctly."""
        parser = FluentParserV1()
        ftl_source = f"msg = Value: {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Should contain the variable reference
        assert f"${var_name}" in serialized


# ============================================================================
# COVERAGE TARGET: Line 171->exit (SelectExpression)
# ============================================================================


class TestSelectExpressionCoverage:
    """Test SelectExpression branch in _visit_expression (line 171->exit)."""

    def test_select_expression_basic(self) -> None:
        """COVERAGE: Line 171->exit - Basic select expression."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $count ->
    [one] One item
   *[other] Many items
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        assert "->" in serialized
        assert "[one]" in serialized
        assert "[other]" in serialized

    def test_select_expression_with_number_key(self) -> None:
        """COVERAGE: Line 171->exit - Select with number keys."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $value ->
    [0] Zero
    [1] One
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        assert "[0]" in serialized
        assert "[1]" in serialized
        assert "*[other]" in serialized

    def test_select_expression_nested(self) -> None:
        """COVERAGE: Line 171->exit - Nested select expressions."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $x ->
    [a] { $y ->
        [1] A1
       *[other] A-other
    }
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Both select expressions should be serialized
        assert "->" in serialized
        assert "[a]" in serialized
        assert "[1]" in serialized

    def test_select_with_placeable_in_variant(self) -> None:
        """COVERAGE: Lines 136->133 AND 171->exit together."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $count ->
    [1] One { $item }
   *[other] Many { $item }s
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Select expression
        assert "->" in serialized
        # Placeables in variants
        assert "{ $item }" in serialized or "$item" in serialized

    @given(
        key1=st.from_regex(r"[a-z]+", fullmatch=True),
        key2=st.from_regex(r"[a-z]+", fullmatch=True),
    )
    def test_select_expression_property(self, key1: str, key2: str) -> None:
        """PROPERTY: Select expressions serialize correctly."""
        from hypothesis import assume  # noqa: PLC0415

        assume(key1 != key2)

        parser = FluentParserV1()
        ftl_source = f"""
msg = {{ $value ->
    [{key1}] First
   *[{key2}] Second
}}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Should contain both variant keys
        assert f"[{key1}]" in serialized
        assert f"[{key2}]" in serialized


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestSerializerIntegration:
    """Integration tests combining multiple branches."""

    def test_complex_message_all_features(self) -> None:
        """Integration: Message with placeables, select, and attributes."""
        parser = FluentParserV1()
        ftl_source = """
greeting = Hello { $name }!
    .formal = Dear { $name },

status = { $count ->
    [0] No items
    [1] One item: { $item }
   *[other] { $count } items
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Placeables
        assert "$name" in serialized
        assert "$item" in serialized
        assert "$count" in serialized

        # Select expression
        assert "->" in serialized
        assert "[0]" in serialized
        assert "[1]" in serialized

        # Attributes
        assert ".formal" in serialized
