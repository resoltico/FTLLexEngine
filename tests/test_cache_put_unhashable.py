"""Test coverage for cache.py put() with unhashable args (lines 135-137)."""

from ftllexengine.runtime.cache import IntegrityCache


class TestCachePutUnhashable:
    """Test put() method with unhashable arguments."""

    def test_put_with_circular_reference_increments_skip_counter(self) -> None:
        """Test put() with circular reference increments unhashable_skips (lines 135-137)."""
        cache = IntegrityCache(strict=False, maxsize=100)

        # Create circular reference that causes RecursionError
        circular: dict[str, object] = {}
        circular["self"] = circular  # Circular reference

        # Initial state
        assert cache.unhashable_skips == 0

        # Try to put with circular reference
        cache.put(
            message_id="test",
            args=circular,  # type: ignore[arg-type]
            attribute=None,
            locale_code="en",
            use_isolating=True,
            formatted="output",
            errors=(),
        )

        # Should have incremented unhashable_skips counter
        assert cache.unhashable_skips == 1

        # Cache should still be empty (nothing was stored)
        assert len(cache) == 0

    def test_put_with_nested_circular_reference(self) -> None:
        """Test put() returns early when args contain nested circular references."""
        cache = IntegrityCache(strict=False, maxsize=50)

        # Nested circular reference
        nested: dict[str, object] = {"level1": {}}
        nested["level1"]["back"] = nested  # type: ignore[index]

        initial_skips = cache.unhashable_skips

        cache.put(
            message_id="nested_test",
            args=nested,  # type: ignore[arg-type]
            attribute=None,
            locale_code="lv",
            use_isolating=True,
            formatted="result",
            errors=(),
        )

        # Should increment skip counter
        assert cache.unhashable_skips == initial_skips + 1

        # Cache should remain empty
        assert len(cache) == 0

    def test_put_with_custom_unhashable_object(self) -> None:
        """Test put() with custom unhashable object in args."""
        cache = IntegrityCache(strict=False, maxsize=100)

        class UnhashableObject:
            """Custom unhashable class."""

            __hash__ = None  # type: ignore[assignment]

        unhashable_args = {"obj": UnhashableObject()}

        initial_skips = cache.unhashable_skips

        # Test passing unhashable args to verify graceful handling
        cache.put(
            message_id="custom_obj",
            args=unhashable_args,  # type: ignore[arg-type]
            attribute="attr",
            locale_code="en_US",
            use_isolating=True,
            formatted="value",
            errors=(),
        )

        # Should increment skip counter
        assert cache.unhashable_skips == initial_skips + 1
        assert len(cache) == 0
