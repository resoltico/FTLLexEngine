"""Regression tests for cache key collision prevention, frozenset handling,
type marker disambiguation in hash composition, and FrozenFluentError
section markers.
"""

from __future__ import annotations

from collections import ChainMap
from decimal import Decimal
from typing import Any

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode, FrozenErrorContext
from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry

# ============================================================================
# SEC-CACHE-COLLISION-001: dict/ChainMap TYPE-TAGGING TESTS
# ============================================================================


class TestDictChainMapCollisionPrevention:
    """Test that dict and ChainMap produce distinct cache keys.

    Issue: SEC-CACHE-COLLISION-001
    Previous: dict and Mapping ABC (ChainMap) produced identical cache keys
    Fix: Added "__dict__" and "__mapping__" type-tags to distinguish them
    """

    def test_dict_vs_chainmap_different_cache_keys(self) -> None:
        """dict and ChainMap with same content produce different cache keys."""
        data = {"a": 1, "b": 2}
        dict_key = IntegrityCache._make_hashable(dict(data))
        chainmap_key = IntegrityCache._make_hashable(ChainMap(data))

        # Keys must be different since str(dict) != str(ChainMap)
        assert dict_key != chainmap_key, (
            "dict and ChainMap should produce different cache keys"
        )

    def test_dict_has_type_tag(self) -> None:
        """dict produces cache key with __dict__ type tag."""
        result = IntegrityCache._make_hashable({"a": 1})
        assert isinstance(result, tuple)
        assert result[0] == "__dict__", f"Expected __dict__ tag, got {result[0]}"

    def test_chainmap_has_type_tag(self) -> None:
        """ChainMap produces cache key with __mapping__ type tag."""
        result = IntegrityCache._make_hashable(ChainMap({"a": 1}))
        assert isinstance(result, tuple)
        assert result[0] == "__mapping__", f"Expected __mapping__ tag, got {result[0]}"

    def test_dict_cache_hit_not_shared_with_chainmap(self) -> None:
        """Caching dict does not produce hit for ChainMap lookup."""
        cache = IntegrityCache(maxsize=10)
        data: dict[str, Any] = {"x": 1}

        # Put with dict args
        cache.put("msg", {"arg": dict(data)}, None, "en", True, "dict result", ())

        # Get with ChainMap args should miss (different cache key)
        result = cache.get("msg", {"arg": ChainMap(data)}, None, "en", True)
        assert result is None, "ChainMap should not hit dict cache entry"

    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers()))
    @settings(max_examples=20)
    def test_dict_chainmap_always_differ(self, data: dict[str, int]) -> None:
        """PROPERTY: dict and ChainMap always produce different keys."""
        event(f"dict_size={len(data)}")
        if not data:  # Skip empty dicts
            return
        dict_key = IntegrityCache._make_hashable(dict(data))
        chainmap_key = IntegrityCache._make_hashable(ChainMap(data))
        assert dict_key != chainmap_key


# ============================================================================
# TYPE-CACHE-FROZENSET-001: FROZENSET CACHE KEY TESTS
# ============================================================================


class TestFrozensetCacheKey:
    """Test that frozenset is properly handled in cache keys.

    Issue: TYPE-CACHE-FROZENSET-001
    Previous: frozenset raised TypeError (not matched by any case)
    Fix: Added explicit frozenset case with __frozenset__ type tag
    """

    def test_frozenset_does_not_raise(self) -> None:
        """frozenset is accepted as cache key component."""
        fs = frozenset({1, 2, 3})
        # Should not raise TypeError
        result = IntegrityCache._make_hashable(fs)
        assert result is not None

    def test_frozenset_has_type_tag(self) -> None:
        """frozenset produces cache key with __frozenset__ type tag."""
        result = IntegrityCache._make_hashable(frozenset({1, 2}))
        assert isinstance(result, tuple)
        assert result[0] == "__frozenset__", f"Expected __frozenset__ tag, got {result[0]}"

    def test_set_has_type_tag(self) -> None:
        """set produces cache key with __set__ type tag."""
        result = IntegrityCache._make_hashable({1, 2})
        assert isinstance(result, tuple)
        assert result[0] == "__set__", f"Expected __set__ tag, got {result[0]}"

    def test_set_vs_frozenset_different_keys(self) -> None:
        """set and frozenset with same content produce different cache keys."""
        data = {1, 2, 3}
        set_key = IntegrityCache._make_hashable(set(data))
        frozenset_key = IntegrityCache._make_hashable(frozenset(data))

        # Keys must be different since str(set) != str(frozenset)
        assert set_key != frozenset_key, (
            "set and frozenset should produce different cache keys"
        )

    def test_frozenset_in_nested_structure(self) -> None:
        """frozenset works in nested dict/list structures."""
        nested = {"keys": frozenset({"a", "b"}), "values": [1, 2]}
        # Should not raise
        result = IntegrityCache._make_hashable(nested)
        assert result is not None

    @given(st.frozensets(st.integers()))
    @settings(max_examples=20)
    def test_frozenset_always_hashable(self, fs: frozenset[int]) -> None:
        """PROPERTY: Any frozenset can be converted to cache key."""
        event(f"frozenset_size={len(fs)}")
        result = IntegrityCache._make_hashable(fs)
        # Result should be a tuple (hashable)
        assert hash(result)  # No exception


# ============================================================================
# SEC-HASH-AMBIGUITY-CACHE-001: TYPE MARKERS IN HASH COMPOSITION
# ============================================================================


class TestHashCompositionTypeMarkers:
    """Test type markers in IntegrityCacheEntry hash composition.

    Issue: SEC-HASH-AMBIGUITY-CACHE-001
    Previous: No type markers between raw hash and length-prefixed string
    Fix: Added b"\\x01" before hash, b"\\x00" before length-prefixed string
    """

    def test_error_with_content_hash_produces_different_checksum(self) -> None:
        """Errors with content_hash property produce different checksums."""
        # FrozenFluentError has content_hash property
        error_with_hash = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry1 = IntegrityCacheEntry.create("Hello", (error_with_hash,), sequence=1)

        # MockError without content_hash (fallback to str encoding)
        # We verify that different errors produce different checksums
        # MockError can't be used since IntegrityCacheEntry expects FrozenFluentError
        error2 = FrozenFluentError("Different error", ErrorCategory.RESOLUTION)
        entry2 = IntegrityCacheEntry.create("Hello", (error2,), sequence=1)

        assert entry1.checksum != entry2.checksum

    def test_content_hash_used_in_checksum(self) -> None:
        """Error content_hash is included in checksum computation."""
        error = FrozenFluentError("Test", ErrorCategory.REFERENCE)
        entry = IntegrityCacheEntry.create("Hello", (error,), sequence=1)

        # Verify entry validates (checksum includes error hash)
        assert entry.verify() is True


# ============================================================================
# SEC-HASH-AMBIGUITY-ERROR-001: SECTION MARKERS IN FROZENFLUENTERROR
# ============================================================================


class TestFrozenFluentErrorSectionMarkers:
    """Test section markers in FrozenFluentError hash composition.

    Issue: SEC-HASH-AMBIGUITY-ERROR-001
    Previous: No markers distinguishing diagnostic/context presence
    Fix: Added section markers (DIAG/NODIAG, CTX/NOCTX)
    """

    def test_diagnostic_none_vs_present_different_hash(self) -> None:
        """Errors with/without diagnostic have different content hashes."""
        # Error without diagnostic
        error_no_diag = FrozenFluentError(
            "Test error",
            ErrorCategory.REFERENCE,
            diagnostic=None,
            context=None,
        )

        # Error with diagnostic
        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Diagnostic message",
            span=None,
        )
        error_with_diag = FrozenFluentError(
            "Test error",
            ErrorCategory.REFERENCE,
            diagnostic=diag,
            context=None,
        )

        assert error_no_diag.content_hash != error_with_diag.content_hash

    def test_context_none_vs_present_different_hash(self) -> None:
        """Errors with/without context have different content hashes."""
        # Error without context
        error_no_ctx = FrozenFluentError(
            "Test error",
            ErrorCategory.FORMATTING,
            diagnostic=None,
            context=None,
        )

        # Error with context
        ctx = FrozenErrorContext(
            input_value="test",
            locale_code="en_US",
            parse_type="number",
            fallback_value="0",
        )
        error_with_ctx = FrozenFluentError(
            "Test error",
            ErrorCategory.FORMATTING,
            diagnostic=None,
            context=ctx,
        )

        assert error_no_ctx.content_hash != error_with_ctx.content_hash

    def test_both_sections_produce_unique_hashes(self) -> None:
        """All combinations of diagnostic/context presence produce unique hashes."""
        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Diagnostic",
            span=None,
        )
        ctx = FrozenErrorContext(
            input_value="test",
            locale_code="en_US",
            parse_type="number",
            fallback_value="0",
        )

        # All four combinations
        err_none_none = FrozenFluentError("X", ErrorCategory.REFERENCE)
        err_diag_none = FrozenFluentError("X", ErrorCategory.REFERENCE, diagnostic=diag)
        err_none_ctx = FrozenFluentError("X", ErrorCategory.REFERENCE, context=ctx)
        err_diag_ctx = FrozenFluentError(
            "X", ErrorCategory.REFERENCE, diagnostic=diag, context=ctx
        )

        hashes = {
            err_none_none.content_hash,
            err_diag_none.content_hash,
            err_none_ctx.content_hash,
            err_diag_ctx.content_hash,
        }

        # All hashes must be unique
        assert len(hashes) == 4, "All combinations should produce unique hashes"

    def test_error_verify_integrity_still_works(self) -> None:
        """verify_integrity() returns True for valid errors after section marker changes."""
        diag = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test diagnostic",
            span=None,
        )
        ctx = FrozenErrorContext(
            input_value="123",
            locale_code="en_US",
            parse_type="number",
            fallback_value="0",
        )
        error = FrozenFluentError(
            "Test error",
            ErrorCategory.FORMATTING,
            diagnostic=diag,
            context=ctx,
        )

        assert error.verify_integrity() is True


# ============================================================================
# COMPREHENSIVE TYPE-TAGGING COVERAGE
# ============================================================================


class TestComprehensiveTypeTagging:
    """Ensure all type-tagged values produce distinct cache keys."""

    def test_all_tagged_types_distinct(self) -> None:
        """Each type-tagged value produces unique cache key structure."""
        # Collect cache keys for equivalent "content" in different types
        values: list[tuple[str, Any]] = [
            ("list", [1, 2, 3]),
            ("tuple", (1, 2, 3)),
            ("set", {1, 2, 3}),
            ("frozenset", frozenset({1, 2, 3})),
            ("dict", {"a": 1}),
            ("chainmap", ChainMap({"a": 1})),
        ]

        keys = {}
        for name, value in values:
            key = IntegrityCache._make_hashable(value)
            keys[name] = key

        # All keys should be distinct
        unique_keys = set()
        for name, key in keys.items():
            key_str = str(key)
            assert key_str not in unique_keys, f"{name} collides with another type"
            unique_keys.add(key_str)

    def test_numeric_types_distinct(self) -> None:
        """int, float, bool, Decimal with same value produce different keys."""
        keys = {
            "bool_true": IntegrityCache._make_hashable(True),
            "int_1": IntegrityCache._make_hashable(1),
            "float_1": IntegrityCache._make_hashable(1.0),
            "decimal_1": IntegrityCache._make_hashable(Decimal("1")),
        }

        # All must be different
        for i, (name1, key1) in enumerate(keys.items()):
            for name2, key2 in list(keys.items())[i + 1 :]:
                assert key1 != key2, f"{name1} and {name2} should differ"
