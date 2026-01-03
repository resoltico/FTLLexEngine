"""Tests for introspection caching functionality.

Validates WeakKeyDictionary-based caching for introspect_message().
"""

from __future__ import annotations

import gc

from ftllexengine.introspection import (
    clear_introspection_cache,
    introspect_message,
)
from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestIntrospectionCache:
    """Test introspection caching behavior."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_introspection_cache()

    def test_cache_hit_returns_same_object(self) -> None:
        """Repeated introspection of same message returns cached result."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")
        message = resource.entries[0]
        assert isinstance(message, Message)

        result1 = introspect_message(message)
        result2 = introspect_message(message)

        # Same object (cache hit)
        assert result1 is result2

    def test_cache_disabled_returns_new_object(self) -> None:
        """With use_cache=False, new result object is created each time."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")
        message = resource.entries[0]
        assert isinstance(message, Message)

        result1 = introspect_message(message, use_cache=False)
        result2 = introspect_message(message, use_cache=False)

        # Equal but not the same object
        assert result1 == result2
        assert result1 is not result2

    def test_cache_disabled_does_not_populate_cache(self) -> None:
        """With use_cache=False, cache is not populated."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")
        message = resource.entries[0]
        assert isinstance(message, Message)

        # First call with cache disabled
        result1 = introspect_message(message, use_cache=False)

        # Second call with cache enabled should create new result
        result2 = introspect_message(message, use_cache=True)

        # Different objects (cache was not populated by first call)
        assert result1 == result2
        assert result1 is not result2

        # Now cache is populated, third call should return same object
        result3 = introspect_message(message, use_cache=True)
        assert result2 is result3

    def test_different_messages_different_results(self) -> None:
        """Different messages return different cached results."""
        parser = FluentParserV1()
        resource = parser.parse("""
greeting = Hello, { $name }!
farewell = Goodbye, { $name }!
""")
        message1 = resource.entries[0]
        message2 = resource.entries[1]
        assert isinstance(message1, Message)
        assert isinstance(message2, Message)

        result1 = introspect_message(message1)
        result2 = introspect_message(message2)

        # Different results
        assert result1 is not result2
        assert result1.message_id == "greeting"
        assert result2.message_id == "farewell"

    def test_clear_cache_invalidates_entries(self) -> None:
        """clear_introspection_cache() removes all cached entries."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")
        message = resource.entries[0]
        assert isinstance(message, Message)

        result1 = introspect_message(message)

        # Clear the cache
        clear_introspection_cache()

        # New call should create new object
        result2 = introspect_message(message)

        # Equal but not the same object (cache was cleared)
        assert result1 == result2
        assert result1 is not result2

    def test_weak_reference_cleanup(self) -> None:
        """Cache entries are garbage collected when message is deleted."""

        def create_and_introspect() -> int:
            """Create message, introspect it, and return hash of result."""
            parser = FluentParserV1()
            resource = parser.parse("temp = Temporary { $var }")
            message = resource.entries[0]
            assert isinstance(message, Message)
            result = introspect_message(message)
            return id(result)

        # Create and introspect a message
        result_id = create_and_introspect()

        # Force garbage collection
        gc.collect()

        # Create a new message with same content
        parser = FluentParserV1()
        resource = parser.parse("temp = Temporary { $var }")
        message = resource.entries[0]
        assert isinstance(message, Message)

        # This should create a new cache entry (old one was cleaned up)
        result = introspect_message(message)

        # The new result should have a different id
        # (WeakKeyDictionary cleaned up the old entry)
        assert id(result) != result_id

    def test_term_caching(self) -> None:
        """Terms are also cached correctly."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = FTLLexEngine { $version }")
        term = resource.entries[0]
        assert isinstance(term, Term)

        result1 = introspect_message(term)
        result2 = introspect_message(term)

        # Same object (cache hit)
        assert result1 is result2
        assert result1.message_id == "brand"

    def test_cache_preserves_all_metadata(self) -> None:
        """Cached result contains all introspection metadata."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { NUMBER($count) } items for { $user } via { -brand }
""")
        message = resource.entries[0]
        assert isinstance(message, Message)

        result1 = introspect_message(message)
        result2 = introspect_message(message)

        # Verify both have same metadata
        assert result1.get_variable_names() == result2.get_variable_names()
        assert result1.get_function_names() == result2.get_function_names()
        assert result1.references == result2.references
        assert result1.has_selectors == result2.has_selectors
