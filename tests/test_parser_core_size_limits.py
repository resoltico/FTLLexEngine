"""Coverage tests for parser/core.py to reach 100%.

Tests specifically targeting uncovered lines:
- Line 57: max_source_size property getter
- Lines 82-87: ValueError when source size exceeds limit
"""

import pytest

from ftllexengine.constants import MAX_SOURCE_SIZE
from ftllexengine.syntax.parser.core import FluentParserV1


class TestFluentParserV1Properties:
    """Test FluentParserV1 property accessors."""

    def test_max_source_size_property_default(self) -> None:
        """Test max_source_size property returns default value (line 57)."""
        parser = FluentParserV1()

        assert parser.max_source_size == MAX_SOURCE_SIZE

    def test_max_source_size_property_custom(self) -> None:
        """Test max_source_size property returns custom value (line 57)."""
        custom_size = 5000
        parser = FluentParserV1(max_source_size=custom_size)

        assert parser.max_source_size == custom_size

    def test_max_source_size_property_disabled(self) -> None:
        """Test max_source_size property when limit disabled (line 57)."""
        parser = FluentParserV1(max_source_size=0)

        assert parser.max_source_size == 0


class TestFluentParserV1SourceSizeValidation:
    """Test source size validation in parse() method."""

    def test_parse_raises_value_error_on_oversized_source(self) -> None:
        """Test parse() raises ValueError when source exceeds limit (lines 82-87)."""
        parser = FluentParserV1(max_source_size=100)
        oversized_source = "a" * 101  # 101 chars > 100 char limit

        with pytest.raises(
            ValueError, match=r"Source length \(101 characters\) exceeds maximum \(100 characters\)"
        ):
            parser.parse(oversized_source)

    def test_parse_error_message_includes_configuration_hint(self) -> None:
        """Test ValueError includes hint about configuration (lines 82-87)."""
        parser = FluentParserV1(max_source_size=50)
        oversized_source = "x" * 51

        with pytest.raises(
            ValueError, match="Configure max_source_size in FluentParserV1 constructor"
        ):
            parser.parse(oversized_source)

    def test_parse_allows_source_at_exact_limit(self) -> None:
        """Test parse() allows source exactly at size limit."""
        parser = FluentParserV1(max_source_size=100)
        exact_size_source = "msg = value\n" * 8  # Exactly at or under limit

        # Should not raise
        result = parser.parse(exact_size_source[:100])
        assert result is not None

    def test_parse_with_disabled_limit_accepts_large_source(self) -> None:
        """Test parse() with disabled limit (max_source_size=0) accepts large sources."""
        parser = FluentParserV1(max_source_size=0)
        large_source = "msg = " + ("x" * 100000)  # Very large source

        # Should not raise when limit is disabled
        result = parser.parse(large_source)
        assert result is not None

    def test_parse_with_disabled_limit_via_none(self) -> None:
        """Test parse() with disabled limit (max_source_size=None) accepts large sources."""
        parser = FluentParserV1(max_source_size=None)
        large_source = "msg = " + ("y" * 100000)

        result = parser.parse(large_source)
        assert result is not None


class TestFluentParserV1BranchCoverage:
    """Test branch coverage for parser/core.py."""

    def test_parse_handles_failed_term_parsing(self) -> None:
        """Test that parser handles failed term parsing (branch 120->127).

        When line starts with '-' but parse_term fails, the parser should
        try to parse as a message instead of creating junk.
        """
        parser = FluentParserV1()

        # Line starting with '-' but not a valid term
        # This should trigger parse_term to fail (return None)
        # and then fall through to parse_message
        source = "- invalid\n"

        result = parser.parse(source)
        assert result is not None
        # Should create junk entry since neither term nor message parsing succeeded
        assert len(result.entries) > 0
