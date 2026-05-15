# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 1: INITIALIZATION VALIDATION
# ============================================================================


class TestIntegrityCacheInitValidation:
    """Test IntegrityCache.__init__ parameter validation."""

    def test_maxsize_zero_rejected(self) -> None:
        """IntegrityCache rejects maxsize=0."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            IntegrityCache(maxsize=0)

    def test_maxsize_negative_rejected(self) -> None:
        """IntegrityCache rejects negative maxsize."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            IntegrityCache(maxsize=-1)

    def test_max_entry_payload_bytes_zero_rejected(self) -> None:
        """IntegrityCache rejects max_entry_payload_bytes=0."""
        with pytest.raises(ValueError, match="max_entry_payload_bytes must be positive"):
            IntegrityCache(max_entry_payload_bytes=0)

    def test_max_entry_payload_bytes_negative_rejected(self) -> None:
        """IntegrityCache rejects negative max_entry_payload_bytes."""
        with pytest.raises(ValueError, match="max_entry_payload_bytes must be positive"):
            IntegrityCache(max_entry_payload_bytes=-1)

    def test_max_errors_per_entry_zero_rejected(self) -> None:
        """IntegrityCache rejects max_errors_per_entry=0."""
        with pytest.raises(ValueError, match="max_errors_per_entry must be positive"):
            IntegrityCache(max_errors_per_entry=0)

    def test_max_errors_per_entry_negative_rejected(self) -> None:
        """IntegrityCache rejects negative max_errors_per_entry."""
        with pytest.raises(ValueError, match="max_errors_per_entry must be positive"):
            IntegrityCache(max_errors_per_entry=-1)
