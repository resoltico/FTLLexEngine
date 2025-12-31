"""Tests for 100% coverage of runtime/bundle.py.

Tests edge cases and less-commonly-used features to achieve complete coverage.
"""

import pytest

from ftllexengine.runtime.bundle import FluentBundle


class TestBundleCacheUsageProperty:
    """Test cache_usage property with cache disabled."""

    def test_cache_usage_returns_zero_when_cache_disabled(self) -> None:
        """cache_usage returns 0 when caching is disabled.

        This tests lines 312-314 in bundle.py.
        """
        bundle = FluentBundle("en", enable_cache=False)
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")

        # cache_usage should return 0 when cache is disabled
        assert bundle.cache_usage == 0

    def test_cache_usage_with_cache_enabled(self) -> None:
        """cache_usage reflects actual cache size when enabled."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg1 = Hello\nmsg2 = World")

        # Before any formatting
        assert bundle.cache_usage == 0

        # After formatting one message
        bundle.format_pattern("msg1")
        assert bundle.cache_usage == 1

        # After formatting two messages
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2


class TestBundleCommentHandling:
    """Test that comments in FTL source are handled correctly."""

    def test_add_resource_with_comments(self) -> None:
        """Comments are parsed but not registered.

        This tests line 553 (the Comment case) in bundle.py.
        """
        bundle = FluentBundle("en")

        # Add resource with various comment types
        ftl_source = """
# Standalone comment
msg1 = Hello

## Section comment
## Multi-line section comment

msg2 = World

### Resource comment
# Another standalone comment
"""
        junk = bundle.add_resource(ftl_source)

        # No junk entries (comments parse successfully)
        assert len(junk) == 0

        # Messages are registered
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")

        # Comments don't create messages
        assert len(bundle.get_message_ids()) == 2

    def test_standalone_comment_only_resource(self) -> None:
        """Resource containing only comments is valid."""
        bundle = FluentBundle("en")

        ftl_source = """
# This is a comment
## This is another comment
### Resource-level comment
"""
        junk = bundle.add_resource(ftl_source)

        # No errors (comments are valid)
        assert len(junk) == 0

        # No messages registered
        assert len(bundle.get_message_ids()) == 0

    def test_comment_followed_by_comment(self) -> None:
        """Multiple consecutive comments hit the Comment->loop branch.

        This ensures the branch 553->532 is covered (Comment case continuing
        to next loop iteration).

        Note: Only section comments (##) and resource comments (###) are
        parsed as Comment AST nodes. Standalone comments (#) are ignored.
        """
        bundle = FluentBundle("en")

        # Multiple section/resource comments in sequence
        ftl_source = """
## Section comment 1
## Section comment 2

### Resource comment

## Another section

msg = Value
"""
        junk = bundle.add_resource(ftl_source)

        # No junk, one message
        assert len(junk) == 0
        assert bundle.has_message("msg")


class TestBundleIntrospectTerm:
    """Test introspect_term method."""

    def test_introspect_term_not_found_raises_key_error(self) -> None:
        """introspect_term raises KeyError for non-existent term.

        This tests lines 928-933 in bundle.py.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        # Accessing non-existent term raises KeyError
        with pytest.raises(KeyError, match="Term 'nonexistent' not found"):
            bundle.introspect_term("nonexistent")

    def test_introspect_term_success(self) -> None:
        """introspect_term returns metadata for existing term."""
        bundle = FluentBundle("en")
        bundle.add_resource("-brand = Firefox\n    .gender = masculine")

        # Should return introspection data
        info = bundle.introspect_term("brand")

        # Verify it's a valid introspection object
        assert info is not None
        # Can access term info
        assert len(info.get_variable_names()) >= 0  # May or may not have variables

    def test_introspect_term_with_variables(self) -> None:
        """introspect_term extracts variables from term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = { $case -> \n    [nominative] Firefox\n    *[other] Firefox\n}"
        )

        info = bundle.introspect_term("brand")

        # Should detect the $case variable
        variables = info.get_variable_names()
        assert "case" in variables
