"""Explicit branch coverage for match/case control flow in resolver.py.

Tests designed to explicitly cover match/case branches that may be
artifacts of coverage.py's branch tracking with Python 3.13 match/case.
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle


class TestMatchCaseBranchCoverage:
    """Test match/case control flow branches in resolver."""

    def test_placeable_followed_by_text_in_pattern(self) -> None:
        """Pattern with Placeable followed by TextElement.

        Tests the 404->400 branch: after successfully processing a Placeable,
        the loop continues to process the next element (TextElement).
        """
        ftl = """msg = { $x } text"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"x": "value"})

        assert result == "value text"

    def test_multiple_placeables_in_pattern(self) -> None:
        """Pattern with multiple Placeables ensures loop continuation.

        Placeable -> Placeable sequence guarantees the 404->400 branch
        (loop continuation after Placeable case) is exercised.
        """
        ftl = """msg = { $a }{ $b }"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"a": "A", "b": "B"})

        assert result == "AB"

    def test_select_with_number_literal_then_identifier_variant(self) -> None:
        """SelectExpression with NumberLiteral followed by Identifier variant.

        When iterating variants in _find_exact_variant, if NumberLiteral
        doesn't match, the loop continues to check Identifier variants.
        This covers the 634->629 branch.
        """
        ftl = """
msg = { $val ->
    [1] one
    [2] two
   *[other] default
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        # Use string value - skips NumberLiteral variants, matches Identifier
        result, _ = bundle.format_pattern("msg", {"val": "other"})

        assert result == "default"

    def test_select_number_literal_no_match_continues_to_next(self) -> None:
        """SelectExpression where first NumberLiteral doesn't match, second does.

        Ensures _find_exact_variant loop continues past non-matching
        NumberLiteral to find the matching one (634->629 branch).
        """
        ftl = """
msg = { $count ->
    [10] ten
    [20] twenty
    [30] thirty
   *[other] default
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        # 20 matches second NumberLiteral after skipping first
        result, _ = bundle.format_pattern("msg", {"count": 20})

        assert result == "twenty"

    def test_select_with_isolating_enabled_exercises_placeable_branch(self) -> None:
        """Pattern with use_isolating=True covers Placeable branch with isolation.

        Tests the 404->400 branch specifically with isolating characters
        enabled, ensuring the if self.use_isolating branch is taken before
        loop continuation.
        """
        ftl = """msg = Prefix { $val } Suffix"""
        bundle = FluentBundle("en", use_isolating=True)  # Isolating enabled
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"val": "middle"})

        # Should contain isolating characters (FSI/PDI)
        assert "Prefix" in result
        assert "middle" in result
        assert "Suffix" in result
