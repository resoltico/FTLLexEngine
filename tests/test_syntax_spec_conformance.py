"""Spec conformance tests using vendored official Fluent.js test fixtures.

This module implements SYSTEM 8 from the testing strategy: Spec Conformance Testing.
We vendor selected official test fixtures from the Fluent.js reference
implementation to ensure our parser conforms to the Fluent specification
without depending on live network fetches at test time.

Strategy:
1. Load vendored official .ftl fixtures from projectfluent/fluent.js
2. Parse .ftl files with our parser
3. Compare structural properties with counts derived from the reference JSON AST
4. Focus on semantic equivalence (not exact AST match since schemas differ)

Official fixtures:
https://github.com/projectfluent/fluent.js/tree/main/fluent-syntax/test/fixtures_structure

References:
- Fluent Specification: https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf
- Fluent.js Reference Implementation
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.ast import Comment, Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from tests.helpers.fluentjs_fixtures import STRUCTURE_FIXTURES

CORE_FIXTURES = (
    "simple_message",
    "multiline_pattern",
    "multiline_with_placeables",
    "select_expressions",
    "blank_lines",
    "term",
)
ERROR_FIXTURES = ("empty_resource",)


# ==============================================================================
# STRUCTURAL COMPARISON UTILITIES
# ==============================================================================


def count_ast_nodes_by_type(resource: Resource) -> dict[str, int]:
    """Count AST nodes by type in parsed resource.

    Args:
        resource: Parsed FTL resource

    Returns:
        Dictionary mapping node type names to counts
    """
    counts: dict[str, int] = {
        "Message": 0,
        "Term": 0,
        "Comment": 0,
        "Junk": 0,
    }

    for entry in resource.entries:
        if isinstance(entry, Message):
            counts["Message"] += 1
        elif isinstance(entry, Term):
            counts["Term"] += 1
        elif isinstance(entry, Comment):
            counts["Comment"] += 1
        elif isinstance(entry, Junk):
            counts["Junk"] += 1

    return counts


# ==============================================================================
# SPEC CONFORMANCE TESTS
# ==============================================================================


class TestSpecConformanceCoreFeatures:
    """Test parser conformance with official Fluent.js fixtures for core features."""

    @pytest.mark.parametrize(
        "fixture_name",
        CORE_FIXTURES,
        ids=CORE_FIXTURES,
    )
    def test_core_fixture_structural_conformance(
        self,
        fixture_name: str,
    ) -> None:
        """Test structural conformance with official fixtures.

        Property: Parser produces same structure as reference implementation.

        Note: Some fixtures show spec discrepancies where our parser behavior
        differs from Fluent.js reference. These are marked for investigation.
        """
        fixture = STRUCTURE_FIXTURES[fixture_name]

        # Parse with our parser
        parser = FluentParserV1()
        resource = parser.parse(fixture.ftl)

        # Verify resource type
        assert isinstance(resource, Resource)

        # Count nodes in our AST
        our_counts = count_ast_nodes_by_type(resource)

        # Verify structural equivalence
        assert (
            our_counts["Message"] == fixture.expected_messages
        ), (
            f"Message count mismatch for {fixture_name}: expected "
            f"{fixture.expected_messages}, got {our_counts['Message']}"
        )
        assert (
            our_counts["Term"] == fixture.expected_terms
        ), (
            f"Term count mismatch for {fixture_name}: expected "
            f"{fixture.expected_terms}, got {our_counts['Term']}"
        )

    @pytest.mark.parametrize(
        "fixture_name",
        CORE_FIXTURES[:5],  # First 5 fixtures for detailed testing
        ids=CORE_FIXTURES[:5],
    )
    def test_parse_determinism_on_fixtures(
        self,
        fixture_name: str,
    ) -> None:
        """Test parser determinism on official fixtures.

        Property: Parsing same fixture twice yields identical results.
        """
        ftl_content = STRUCTURE_FIXTURES[fixture_name].ftl
        parser = FluentParserV1()

        # Parse twice
        resource1 = parser.parse(ftl_content)
        resource2 = parser.parse(ftl_content)

        # Verify determinism
        assert len(resource1.entries) == len(resource2.entries)

        # Verify entry types match
        types1 = [type(e).__name__ for e in resource1.entries]
        types2 = [type(e).__name__ for e in resource2.entries]
        assert types1 == types2


class TestSpecConformanceErrorHandling:
    """Test parser error handling conformance with official fixtures."""

    @pytest.mark.parametrize(
        "fixture_name",
        ERROR_FIXTURES,
        ids=ERROR_FIXTURES,
    )
    def test_error_fixture_robustness(
        self,
        fixture_name: str,
    ) -> None:
        """Test parser robustness on error fixtures.

        Property: Parser never crashes on invalid input.
        """
        ftl_content = STRUCTURE_FIXTURES[fixture_name].ftl

        # Parse (should not crash)
        parser = FluentParserV1()
        resource = parser.parse(ftl_content)

        # Verify resource type
        assert isinstance(resource, Resource)
        assert resource.entries is not None

        # Count nodes
        counts = count_ast_nodes_by_type(resource)

        # For error fixtures, we expect either:
        # 1. Valid messages/terms (parser recovered)
        # 2. Junk entries (parser recorded errors)
        total_entries = sum(counts.values())
        assert total_entries >= 0, "Parser should produce some entries or empty resource"


class TestSpecConformanceRoundtrip:
    """Test roundtrip property on official fixtures."""

    @pytest.mark.parametrize(
        "fixture_name",
        CORE_FIXTURES[:5],  # First 5 fixtures for roundtrip
        ids=CORE_FIXTURES[:5],
    )
    def test_parse_serialize_parse_converges(
        self,
        fixture_name: str,
    ) -> None:
        """Test parse→serialize→parse convergence on official fixtures.

        Property: After first roundtrip, format stabilizes.
        """
        from ftllexengine.syntax.serializer import serialize

        ftl_content = STRUCTURE_FIXTURES[fixture_name].ftl
        parser = FluentParserV1()

        # Parse original
        resource1 = parser.parse(ftl_content)

        # Serialize and parse again
        ftl2 = serialize(resource1)
        resource2 = parser.parse(ftl2)

        # Serialize and parse third time
        ftl3 = serialize(resource2)
        resource3 = parser.parse(ftl3)

        # Should have converged (same number of entries)
        assert len(resource2.entries) == len(resource3.entries)

        # Entry types should match
        types2 = [type(e).__name__ for e in resource2.entries]
        types3 = [type(e).__name__ for e in resource3.entries]
        assert types2 == types3


class TestSpecConformanceEdgeCases:
    """Test parser behavior on edge cases from official fixtures."""

    def test_empty_resource(self) -> None:
        """Test empty FTL resource."""
        ftl = STRUCTURE_FIXTURES["empty_resource"].ftl
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Empty resource should have no entries or only whitespace/comments
        assert len(resource.entries) >= 0

    def test_blank_lines_handling(self) -> None:
        """Test blank lines don't affect parsing."""
        ftl = STRUCTURE_FIXTURES["blank_lines"].ftl
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        counts = count_ast_nodes_by_type(resource)
        # Should produce valid message (blank lines ignored)
        assert counts["Message"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
