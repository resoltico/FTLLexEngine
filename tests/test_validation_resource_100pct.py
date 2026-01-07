"""Tests for 100% coverage of validation/resource.py.

Tests edge cases in validation error handling and cycle detection.
"""

from ftllexengine.syntax.ast import Annotation, Junk, Resource, Span, Term
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _detect_circular_references,
    _extract_syntax_errors,
)


class TestExtractSyntaxErrors:
    """Test _extract_syntax_errors with edge cases."""

    def test_junk_with_annotation_no_span_but_entry_has_span(self) -> None:
        """Junk entry with annotation that has no span, but entry has span.

        This tests lines 96-97 in validation/resource.py.
        """
        source = "invalid syntax here"
        line_cache = LineOffsetCache(source)

        # Create Junk with annotation that has no span, but entry has span
        junk = Junk(
            content="invalid syntax here",
            annotations=(
                Annotation(
                    code="PARSE_ERROR",
                    message="Test error",
                    arguments=None,
                    span=None,  # No span on annotation
                ),
            ),
            span=Span(start=0, end=19),  # But entry has span
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should extract error using entry span as fallback
        assert len(errors) == 1
        assert errors[0].code == "PARSE_ERROR"
        assert errors[0].line == 1
        assert errors[0].column == 1

    def test_junk_without_annotations(self) -> None:
        """Junk entry without annotations (shouldn't happen normally).

        This tests line 113 in validation/resource.py - the fallback
        for Junk without annotations.
        """
        source = "invalid"
        line_cache = LineOffsetCache(source)

        # Create Junk with no annotations (unusual but handled)
        junk = Junk(
            content="invalid",
            annotations=(),  # Empty tuple
            span=Span(start=0, end=7),
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should create generic parse error
        assert len(errors) == 1
        assert errors[0].code == "VALIDATION_PARSE_ERROR"
        assert errors[0].message == "Failed to parse FTL content"
        assert errors[0].line == 1

    def test_junk_without_annotations_or_span(self) -> None:
        """Junk entry without annotations AND without span."""
        source = "test"
        line_cache = LineOffsetCache(source)

        # Junk with neither annotations nor span
        junk = Junk(
            content="test",
            annotations=(),
            span=None,
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should create error with no position info
        assert len(errors) == 1
        assert errors[0].line is None
        assert errors[0].column is None


class TestCircularReferences:
    """Test circular reference detection edge cases."""

    def test_term_referencing_message_creates_cross_type_dependency(self) -> None:
        """Term references an existing message.

        This tests line 345 in validation/resource.py - when a term
        references a message, it creates a cross-type dependency.
        """
        ftl_source = """
msg = Message value
-term = { msg }
"""
        result = validate_resource(ftl_source)

        # No circular references, but the term->message dependency is tracked
        assert result.is_valid
        assert len(result.warnings) == 0

    def test_circular_cross_reference_message_term_message(self) -> None:
        """Circular reference crossing message and term boundaries.

        This tests line 374 in validation/resource.py - detecting
        cross-type circular references.
        """
        ftl_source = """
msg1 = { -term1 }
-term1 = { msg1 }
"""
        result = validate_resource(ftl_source)

        # Circular references are warnings, not errors
        # So is_valid is True, but warnings are present
        assert result.is_valid  # No syntax errors
        assert len(result.warnings) > 0
        # Find the circular reference warning
        circular_warnings = [
            w for w in result.warnings
            if "Circular cross-reference" in w.message
        ]
        assert len(circular_warnings) > 0

    def test_complex_cross_type_cycle(self) -> None:
        """Complex cycle involving multiple messages and terms."""
        ftl_source = """
msg1 = { -term1 }
-term1 = { msg2 }
msg2 = { -term2 }
-term2 = { msg1 }
"""
        result = validate_resource(ftl_source)

        # Should detect the circular cross-reference (as warning)
        assert result.is_valid  # No syntax errors
        circular_warnings = [
            w for w in result.warnings
            if "circular" in w.message.lower()
        ]
        assert len(circular_warnings) > 0


class TestDetectCircularReferencesUnitTest:
    """Direct unit tests for _detect_circular_references."""

    def test_term_only_cycle(self) -> None:
        """Cycle involving only terms."""
        parser = FluentParserV1()
        resource = parser.parse("""
-term1 = { -term2 }
-term2 = { -term1 }
""")

        # Extract terms
        terms_dict: dict[str, Term] = {}
        for entry in resource.entries:
            if isinstance(entry, Term):
                terms_dict[entry.id.name] = entry

        # Build dependency graph
        graph = _build_dependency_graph({}, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect term-only cycle
        assert len(warnings) > 0
        term_warnings = [
            w for w in warnings
            if "Circular term reference" in w.message
        ]
        assert len(term_warnings) > 0
