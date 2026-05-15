# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 8: ERROR BLOAT PROTECTION
# ============================================================================


class TestIntegrityCacheErrorBloatProtection:
    """Test IntegrityCache error collection memory bounding.

    Prevents unbounded memory use when a single message generates many errors.
    Two limits: max_errors_per_entry (count) and max_entry_payload_bytes (bytes).
    """

    def test_put_rejects_excessive_error_count(self) -> None:
        """put() skips caching when error count exceeds max_errors_per_entry."""
        cache = IntegrityCache(max_errors_per_entry=10)
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE) for i in range(15)
        )
        cache.put("msg", None, None, "en", use_isolating=True, formatted="formatted text", errors=errors)
        assert cache.size == 0
        assert cache.get_stats()["error_bloat_skips"] == 1
        assert cache.get("msg", None, None, "en", use_isolating=True) is None

    def test_put_rejects_excessive_error_payload(self) -> None:
        """put() skips caching when retained payload bytes exceed the budget."""
        cache = IntegrityCache(max_entry_payload_bytes=1000, max_errors_per_entry=50)
        errors = tuple(
            FrozenFluentError("E" * 100, ErrorCategory.REFERENCE) for _ in range(10)
        )
        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=errors)
        assert cache.size == 0
        # 10 errors pass the count check (10 <= 50), but the retained payload
        # (100 formatted bytes + 10 * 108 error bytes) exceeds the 1000-byte budget.
        assert cache.get_stats()["combined_payload_skips"] == 1
        assert cache.get_stats()["error_bloat_skips"] == 0

    def test_put_accepts_reasonable_error_collections(self) -> None:
        """put() caches results with error counts and weights within limits."""
        cache = IntegrityCache(max_entry_payload_bytes=15000, max_errors_per_entry=50)
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE) for i in range(10)
        )
        cache.put("msg", None, None, "en", use_isolating=True, formatted="formatted text", errors=errors)
        assert cache.size == 1
        assert cache.get_stats()["error_bloat_skips"] == 0
        cached = cache.get("msg", None, None, "en", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted text", errors)
