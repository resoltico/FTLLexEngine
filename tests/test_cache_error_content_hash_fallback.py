"""Test IntegrityCache error content_hash fallback for 100% coverage.

Covers the fallback path in _compute_checksum and _compute_content_hash
when error objects lack a proper content_hash bytes attribute.

Target: Lines 246-251 and 326-328 in cache.py
"""

from __future__ import annotations

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry


class ErrorWithoutContentHash:
    """Mock error object without content_hash attribute."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.diagnostic = None
        self.context = None

    def __str__(self) -> str:
        return self.message


class ErrorWithNonBytesContentHash:
    """Mock error object with content_hash attribute that's not bytes."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.content_hash = "not-bytes-string"  # Wrong type
        self.diagnostic = None
        self.context = None

    def __str__(self) -> str:
        return self.message


class ErrorWithNoneContentHash:
    """Mock error object with content_hash=None."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.content_hash = None
        self.diagnostic = None
        self.context = None

    def __str__(self) -> str:
        return self.message


class TestErrorContentHashFallback:
    """Test fallback path for errors without proper content_hash attribute."""

    def test_entry_create_with_error_without_content_hash(self) -> None:
        """IntegrityCacheEntry.create() handles errors without content_hash.

        Covers _compute_checksum lines 246-251 fallback path.
        """
        error = ErrorWithoutContentHash("Test error")
        errors = (error,)

        # Should not raise, falls back to str(error) encoding
        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        assert entry.formatted == "formatted"
        assert entry.errors == errors  # type: ignore[comparison-overlap]
        assert len(entry.checksum) == 16  # BLAKE2b-128

    def test_entry_create_with_error_non_bytes_content_hash(self) -> None:
        """IntegrityCacheEntry.create() handles non-bytes content_hash.

        Covers _compute_checksum lines 246-251 fallback path.
        """
        error = ErrorWithNonBytesContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        assert entry.formatted == "formatted"
        assert entry.errors == errors  # type: ignore[comparison-overlap]
        assert len(entry.checksum) == 16

    def test_entry_create_with_error_none_content_hash(self) -> None:
        """IntegrityCacheEntry.create() handles content_hash=None."""
        error = ErrorWithNoneContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        assert entry.formatted == "formatted"
        assert len(entry.checksum) == 16

    def test_content_hash_property_with_error_without_content_hash(self) -> None:
        """content_hash property handles errors without content_hash attribute.

        Covers _compute_content_hash lines 326-328 fallback path.
        """
        error = ErrorWithoutContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        # Access content_hash property to trigger _compute_content_hash
        content_hash = entry.content_hash

        assert content_hash is not None
        assert len(content_hash) == 16  # BLAKE2b-128

    def test_content_hash_property_with_non_bytes_content_hash(self) -> None:
        """content_hash property handles non-bytes content_hash.

        Covers _compute_content_hash lines 326-328 fallback path.
        """
        error = ErrorWithNonBytesContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )
        content_hash = entry.content_hash

        assert content_hash is not None
        assert len(content_hash) == 16

    def test_content_hash_property_with_none_content_hash(self) -> None:
        """content_hash property handles content_hash=None."""
        error = ErrorWithNoneContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )
        content_hash = entry.content_hash

        assert content_hash is not None
        assert len(content_hash) == 16

    def test_cache_roundtrip_with_error_without_content_hash(self) -> None:
        """Cache roundtrip works with errors lacking content_hash."""
        cache = IntegrityCache(strict=False)

        error = ErrorWithoutContentHash("Test error")
        errors = (error,)

        # Put entry with non-standard error
        cache.put("msg", None, None, "en", True, "formatted", errors)  # type: ignore[arg-type]

        # Get entry back
        entry = cache.get("msg", None, None, "en", True)

        assert entry is not None
        assert entry.formatted == "formatted"
        assert entry.verify()  # Checksum should verify correctly

    def test_different_errors_produce_different_checksums(self) -> None:
        """Errors without content_hash produce different checksums."""
        error1 = ErrorWithoutContentHash("Error 1")
        error2 = ErrorWithoutContentHash("Error 2")

        entry1 = IntegrityCacheEntry.create(
            "formatted", (error1,), sequence=1  # type: ignore[arg-type]
        )
        entry2 = IntegrityCacheEntry.create(
            "formatted", (error2,), sequence=1  # type: ignore[arg-type]
        )

        # Checksums differ because error str() differs
        assert entry1.checksum != entry2.checksum
        assert entry1.content_hash != entry2.content_hash

    def test_same_error_str_produces_same_content_hash(self) -> None:
        """Errors with same str() produce same content_hash."""
        error1 = ErrorWithoutContentHash("Same message")
        error2 = ErrorWithoutContentHash("Same message")

        entry1 = IntegrityCacheEntry.create(
            "formatted", (error1,), sequence=1  # type: ignore[arg-type]
        )
        entry2 = IntegrityCacheEntry.create(
            "formatted", (error2,), sequence=2  # type: ignore[arg-type]
        )

        # Content hashes are identical (same content)
        assert entry1.content_hash == entry2.content_hash

        # Full checksums differ (different sequence)
        assert entry1.checksum != entry2.checksum

    def test_verify_with_error_without_content_hash_no_verify_method(self) -> None:
        """verify() handles errors without verify_integrity method."""
        # ErrorWithoutContentHash has no verify_integrity method
        error = ErrorWithoutContentHash("Test error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        # verify() should still work (skips recursive verification)
        assert entry.verify() is True

    def test_verify_with_error_with_failing_verification(self) -> None:
        """verify() returns False when error.verify_integrity() returns False."""

        class ErrorWithFailingVerify:
            """Error object with verify_integrity that returns False."""

            def __init__(self, message: str) -> None:
                self.message = message
                self.diagnostic = None
                self.context = None

            def __str__(self) -> str:
                return self.message

            def verify_integrity(self) -> bool:
                """Always fails verification."""
                return False

        error = ErrorWithFailingVerify("Failing error")
        errors = (error,)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        # verify() should return False because error verification failed
        assert entry.verify() is False

    def test_mixed_error_types_all_covered(self) -> None:
        """Mix of standard and non-standard errors all work correctly."""
        standard_error = FrozenFluentError("Standard", ErrorCategory.REFERENCE)
        no_hash_error = ErrorWithoutContentHash("No hash")
        wrong_type_error = ErrorWithNonBytesContentHash("Wrong type")

        errors = (standard_error, no_hash_error, wrong_type_error)

        entry = IntegrityCacheEntry.create(
            "formatted", errors, sequence=1  # type: ignore[arg-type]
        )

        assert entry.formatted == "formatted"
        assert len(entry.checksum) == 16
        assert len(entry.content_hash) == 16
        assert entry.verify() is True
