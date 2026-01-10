"""Tests for Junk entry and annotation handling in validation.

Covers edge cases in syntax error extraction:
- Junk entries with and without annotations
- Junk entries with and without span information
- Annotation span fallback to Junk span
- Multiple annotations on single Junk entry

Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax import (
    Annotation,
    Identifier,
    Junk,
    Pattern,
    Resource,
    Span,
    Term,
    TextElement,
)
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.validation.resource import _extract_syntax_errors, validate_resource

# ============================================================================
# Junk Without Annotations
# ============================================================================


class TestJunkWithoutAnnotations:
    """Test Junk entries without annotations (unusual but handled)."""

    def test_junk_without_annotations_creates_generic_error(self) -> None:
        """Junk without annotations produces generic parse error."""
        source = "invalid"
        line_cache = LineOffsetCache(source)

        junk = Junk(
            content="invalid",
            annotations=(),  # Empty tuple
            span=Span(start=0, end=7),
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.VALIDATION_PARSE_ERROR.name
        assert errors[0].message == "Failed to parse FTL content"
        assert errors[0].line == 1

    def test_junk_without_annotations_or_span(self) -> None:
        """Junk without annotations AND without span has no position info."""
        source = "test"
        line_cache = LineOffsetCache(source)

        junk = Junk(
            content="test",
            annotations=(),
            span=None,
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.VALIDATION_PARSE_ERROR.name
        assert errors[0].line is None
        assert errors[0].column is None


# ============================================================================
# Annotation Span Fallback
# ============================================================================


class TestAnnotationSpanFallback:
    """Test annotation span fallback to Junk span."""

    def test_annotation_with_span_uses_annotation_span(self) -> None:
        """Annotation with span uses its own span for position."""
        source = "hello = world\ninvalid syntax\ngoodbye = world"
        line_cache = LineOffsetCache(source)

        # Annotation has its own span
        annotation = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=Span(start=20, end=25),  # Points to specific position
        )
        junk = Junk(
            content="invalid syntax",
            annotations=(annotation,),
            span=Span(start=14, end=28),  # Junk span is broader
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        # Should use annotation's span
        assert errors[0].line == 2
        assert errors[0].column is not None

    def test_annotation_without_span_uses_junk_span(self) -> None:
        """Annotation without span falls back to Junk span."""
        source = "hello = world\ninvalid syntax\ngoodbye = world"
        line_cache = LineOffsetCache(source)

        # Annotation has no span
        annotation = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=None,
        )
        junk = Junk(
            content="invalid syntax",
            annotations=(annotation,),
            span=Span(start=14, end=28),  # Junk has span
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        # Should use Junk's span as fallback
        assert errors[0].line is not None
        assert errors[0].column is not None

    def test_annotation_and_junk_both_without_span(self) -> None:
        """Annotation and Junk both without span results in no position."""
        source = "invalid syntax"
        line_cache = LineOffsetCache(source)

        annotation = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=None,
        )
        junk = Junk(
            content="invalid syntax",
            annotations=(annotation,),
            span=None,
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        assert errors[0].line is None
        assert errors[0].column is None


# ============================================================================
# Multiple Annotations
# ============================================================================


class TestMultipleAnnotations:
    """Test Junk entries with multiple annotations."""

    def test_junk_with_multiple_annotations_creates_multiple_errors(self) -> None:
        """Junk with multiple annotations produces error for each annotation."""
        source = "invalid content here"
        line_cache = LineOffsetCache(source)

        # Create Junk with two annotations
        annotation1 = Annotation(
            code=DiagnosticCode.INVALID_CHARACTER.name,
            message="Invalid character",
            span=Span(start=0, end=7),
        )
        annotation2 = Annotation(
            code=DiagnosticCode.EXPECTED_TOKEN.name,
            message="Expected token",
            span=Span(start=8, end=15),
        )
        junk = Junk(
            content="invalid content here",
            annotations=(annotation1, annotation2),
            span=Span(start=0, end=20),
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should have two errors (one per annotation)
        assert len(errors) == 2
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        assert errors[1].code == DiagnosticCode.EXPECTED_TOKEN.name

    def test_multiple_junk_entries_create_separate_errors(self) -> None:
        """Multiple Junk entries each produce their own errors."""
        source = "first invalid\nsecond invalid"
        line_cache = LineOffsetCache(source)

        junk1 = Junk(
            content="first invalid",
            annotations=(
                Annotation(
                    code=DiagnosticCode.INVALID_CHARACTER.name,
                    message="First error",
                    span=Span(start=0, end=13),
                ),
            ),
            span=Span(start=0, end=13),
        )
        junk2 = Junk(
            content="second invalid",
            annotations=(
                Annotation(
                    code=DiagnosticCode.EXPECTED_TOKEN.name,
                    message="Second error",
                    span=Span(start=14, end=28),
                ),
            ),
            span=Span(start=14, end=28),
        )

        resource = Resource(entries=(junk1, junk2))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should have two errors (one per Junk)
        assert len(errors) == 2
        assert errors[0].code == DiagnosticCode.INVALID_CHARACTER.name
        assert errors[1].code == DiagnosticCode.EXPECTED_TOKEN.name


# ============================================================================
# Integration Tests
# ============================================================================


class TestJunkHandlingIntegration:
    """Integration tests using validate_resource with real FTL syntax errors."""

    def test_validate_resource_with_syntax_error(self) -> None:
        """validate_resource handles FTL with syntax errors."""
        source = """
message = valid

# Invalid syntax that creates Junk
@@@invalid

another = valid
"""

        result = validate_resource(source)

        # Should have errors from Junk
        assert len(result.errors) > 0
        assert not result.is_valid

    def test_validate_resource_extracts_all_junk_errors(self) -> None:
        """validate_resource extracts errors from all Junk entries."""
        source = """
valid = message
@@@first-invalid
@@@second-invalid
another-valid = message
"""

        result = validate_resource(source)

        # Parser may combine consecutive invalid lines into single Junk
        # Should have at least 1 error for the invalid syntax
        assert len(result.errors) >= 1

    def test_validate_resource_with_mixed_valid_and_junk(self) -> None:
        """validate_resource processes both valid entries and Junk."""
        source = """
valid1 = This is valid
@@@invalid
valid2 = This is also valid
"""

        result = validate_resource(source)

        # Should have errors from Junk
        assert len(result.errors) > 0
        # But should still process valid messages (check warnings for other issues)
        # Valid messages shouldn't produce errors
        assert not result.is_valid  # Due to parse errors


# ============================================================================
# Edge Cases
# ============================================================================


class TestJunkEdgeCases:
    """Edge cases in Junk handling."""

    def test_empty_junk_content(self) -> None:
        """Junk with empty content is handled."""
        source = ""
        line_cache = LineOffsetCache(source)

        junk = Junk(
            content="",
            annotations=(),
            span=None,
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should create generic error
        assert len(errors) == 1
        assert errors[0].code == DiagnosticCode.VALIDATION_PARSE_ERROR.name

    def test_junk_with_whitespace_only_content(self) -> None:
        """Junk with whitespace-only content is handled."""
        source = "   \n  \t  "
        line_cache = LineOffsetCache(source)

        junk = Junk(
            content="   \n  \t  ",
            annotations=(),
            span=Span(start=0, end=9),
        )

        resource = Resource(entries=(junk,))
        errors = _extract_syntax_errors(resource, line_cache)

        assert len(errors) == 1
        assert errors[0].content == "   \n  \t  "

    def test_resource_with_only_junk_entries(self) -> None:
        """Resource containing only Junk entries is handled."""
        source = "@@@invalid1\n@@@invalid2"
        line_cache = LineOffsetCache(source)

        junk1 = Junk(
            content="@@@invalid1",
            annotations=(
                Annotation(
                    code=DiagnosticCode.INVALID_CHARACTER.name,
                    message="Error 1",
                    span=Span(start=0, end=11),
                ),
            ),
            span=Span(start=0, end=11),
        )
        junk2 = Junk(
            content="@@@invalid2",
            annotations=(
                Annotation(
                    code=DiagnosticCode.INVALID_CHARACTER.name,
                    message="Error 2",
                    span=Span(start=12, end=23),
                ),
            ),
            span=Span(start=12, end=23),
        )

        resource = Resource(entries=(junk1, junk2))
        errors = _extract_syntax_errors(resource, line_cache)

        # Should have errors for all Junk entries
        assert len(errors) == 2

    def test_resource_with_no_junk_entries(self) -> None:
        """Resource with no Junk entries produces no syntax errors."""
        # Create valid term (not Junk)
        term = Term(
            id=Identifier("valid-term"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )

        resource = Resource(entries=(term,))
        source = "-valid-term = value"
        line_cache = LineOffsetCache(source)

        errors = _extract_syntax_errors(resource, line_cache)

        # No Junk entries, no syntax errors
        assert len(errors) == 0
