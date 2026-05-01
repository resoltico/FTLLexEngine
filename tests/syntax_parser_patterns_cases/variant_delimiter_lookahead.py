# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VARIANT DELIMITER LOOKAHEAD
# ============================================================================


class TestVariantDelimiterLookahead:
    """Tests for variant delimiter (* and [) in pattern text."""

    def test_asterisk_literal_in_variant(self) -> None:
        """'*' without '[' is treated as literal text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
count = { $n ->
    [one] 1 * item
   *[other] { $n } * items
}
""")
        result, errors = bundle.format_pattern("count", {"n": 1})
        assert "1 * item" in result
        assert not errors

    def test_bracket_not_starting_variant(self) -> None:
        """'[' not followed by valid key is treated as literal."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $type ->
    [info] [INFO] message
   *[other] [?] unknown
}
""")
        result, errors = bundle.format_pattern(
            "msg", {"type": "info"}
        )
        assert "[INFO] message" in result
        assert not errors

    def test_math_expression_in_variant(self) -> None:
        """Math-like expressions with * and [ in variant text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
calc = { $op ->
    [mul] Result: 3 * 5 = 15
    [arr] Array: [1, 2, 3]
   *[other] Unknown operation
}
""")
        result, _ = bundle.format_pattern("calc", {"op": "mul"})
        assert "3 * 5 = 15" in result

        result, _ = bundle.format_pattern("calc", {"op": "arr"})
        assert "[1, 2, 3]" in result

    def test_asterisk_bracket_is_variant(self) -> None:
        """'*[' still correctly marks default variant."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
example = { $x ->
    [a] Value A
   *[b] Default B
}
""")
        result, errors = bundle.format_pattern(
            "example", {"x": "unknown"}
        )
        assert not errors
        assert "Default B" in result

    def test_numeric_variant_key(self) -> None:
        """[123] treated as variant key."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
indexed = { $i ->
    [0] Zero
    [1] One
   *[2] Default
}
""")
        result, errors = bundle.format_pattern("indexed", {"i": 0})
        assert not errors
        assert "Zero" in result

    def test_complex_asterisk_and_brackets(self) -> None:
        """Both * and [] as literals in variant text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
complex = { $mode ->
    [matrix] See [matrix * vector] for details
    [calc] Compute a * b + c
   *[other] No special chars
}
""")
        result, _ = bundle.format_pattern(
            "complex", {"mode": "matrix"}
        )
        assert "[matrix * vector]" in result

    def test_variant_pattern_fails(self) -> None:
        """parse_variant returns None on malformed input."""
        cursor = Cursor("[one] {@", 0)
        assert parse_variant(cursor) is None
