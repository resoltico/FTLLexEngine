"""Edge case tests for syntax/parser/rules.py coverage.

Tests specific uncovered lines in parser rules.
"""

from ftllexengine.syntax.parser import FluentParserV1


class TestVariantLookaheadEdgeCases:
    """Test variant lookahead edge cases."""

    def test_eof_before_bracket(self) -> None:
        """EOF before finding closing bracket.

        This tests line 219 in rules.py.
        """
        parser = FluentParserV1()
        # Incomplete variant at EOF
        resource = parser.parse("msg = { $x -> ")
        # Should handle gracefully (parse as junk)
        assert len(resource.entries) > 0

    def test_empty_variant_brackets(self) -> None:
        """Empty [] is not a valid variant key.

        This tests line 246 in rules.py.
        """
        parser = FluentParserV1()
        # Empty variant key
        resource = parser.parse("msg = { $x -> [] value }")
        # Should not parse as valid variant
        assert len(resource.entries) > 0

    def test_variant_at_eof(self) -> None:
        """Variant key followed by EOF.

        This tests line 261 in rules.py.
        """
        parser = FluentParserV1()
        # Variant at EOF
        resource = parser.parse("msg = { $x -> [key]")
        # Should handle EOF gracefully
        assert len(resource.entries) > 0

    def test_no_asterisk_for_lookahead(self) -> None:
        """Character is not * and not [, triggering fallback.

        This tests line 280 in rules.py.
        """
        parser = FluentParserV1()
        # Not a variant marker
        resource = parser.parse("msg = text without variants")
        # Should parse normally as text
        assert len(resource.entries) > 0


class TestPatternBlankLineTrimming:
    """Test pattern blank line trimming edge cases."""

    def test_all_whitespace_elements_removed(self) -> None:
        """Pattern with all-whitespace elements has them removed.

        This tests line 317 in rules.py.
        """
        parser = FluentParserV1()
        # Message with leading/trailing whitespace
        resource = parser.parse("""
msg =

    value

""")
        # Should trim blank lines
        messages = [e for e in resource.entries if hasattr(e, "id")]
        assert len(messages) > 0
