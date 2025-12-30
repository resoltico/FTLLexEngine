"""Comprehensive coverage tests for runtime/locale_context.py.

Targets coverage for LocaleContext.create() and create_or_raise() methods.
"""

from __future__ import annotations

import pytest

from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# LocaleContext.create_or_raise() ValueError Path
# ============================================================================


class TestLocaleContextCreateOrRaiseErrorPath:
    """Test LocaleContext.create_or_raise() error handling (lines 165-170).

    Since v0.14.0, create_or_raise() does its own validation and raises
    ValueError directly for invalid locales.
    """

    def test_create_or_raise_with_unknown_locale_raises(self) -> None:
        """Test create_or_raise() raises ValueError for unknown locale."""
        with pytest.raises(ValueError, match=r"Unknown locale identifier"):
            LocaleContext.create_or_raise("xx-INVALID")

    def test_create_or_raise_with_malformed_locale_raises(self) -> None:
        """Test create_or_raise() raises ValueError for malformed locale."""
        with pytest.raises(ValueError, match=r"locale"):
            LocaleContext.create_or_raise("not-a-valid-locale-at-all")

    def test_create_or_raise_error_contains_locale_code(self) -> None:
        """Test create_or_raise() error message includes locale code."""
        test_locales = [
            "bad-locale",
            "xyz-123",
        ]

        for locale_code in test_locales:
            with pytest.raises(ValueError, match="locale") as exc_info:
                LocaleContext.create_or_raise(locale_code)

            assert locale_code in str(exc_info.value)

    def test_create_or_raise_success_path_returns_context(self) -> None:
        """Verify create_or_raise() returns LocaleContext on success."""
        # This tests the normal path where LocaleContext is returned
        ctx = LocaleContext.create_or_raise("en_US")

        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en_US"


# ============================================================================
# LocaleContext.create() fallback behavior tests
# ============================================================================


class TestLocaleContextCreateFallback:
    """Test LocaleContext.create() graceful fallback behavior (v0.14.0+).

    Since v0.14.0, create() always returns LocaleContext with en_US fallback
    for invalid locales instead of returning LocaleValidationError.
    """

    def test_create_with_unknown_locale_returns_context(self) -> None:
        """create() returns LocaleContext for unknown locale."""
        result = LocaleContext.create("xx-UNKNOWN")

        assert isinstance(result, LocaleContext)
        # Original locale_code preserved
        assert result.locale_code == "xx-UNKNOWN"

    def test_create_with_invalid_locale_uses_en_us_formatting(self) -> None:
        """create() uses en_US formatting for invalid locales."""
        ctx = LocaleContext.create("invalid-locale-xyz")

        # Should format like en_US (comma grouping)
        formatted = ctx.format_number(1234.5, use_grouping=True)
        assert "1,234" in formatted or "1234" in formatted

    def test_create_never_returns_locale_validation_error(self) -> None:
        """create() never returns LocaleValidationError (v0.14.0+)."""
        test_cases = ["xx-YY", "invalid", "", "123", "not-a-locale"]

        for locale in test_cases:
            result = LocaleContext.create(locale)
            assert isinstance(result, LocaleContext)


class TestLocaleContextBehaviorConsistency:
    """Test that create() and create_or_raise() have consistent validation logic."""

    def test_valid_locale_accepted_by_both(self) -> None:
        """Valid locale accepted by both create() and create_or_raise()."""
        locales = ["en-US", "de-DE", "lv-LV", "fr-FR"]

        for locale in locales:
            # create() should return context
            ctx1 = LocaleContext.create(locale)
            assert isinstance(ctx1, LocaleContext)

            # create_or_raise() should return context
            ctx2 = LocaleContext.create_or_raise(locale)
            assert isinstance(ctx2, LocaleContext)

    def test_invalid_locale_handled_differently(self) -> None:
        """Invalid locale: create() falls back, create_or_raise() raises."""
        locale = "xx-INVALID"

        # create() should return context with fallback
        ctx = LocaleContext.create(locale)
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == locale

        # create_or_raise() should raise
        with pytest.raises(ValueError, match="locale"):
            LocaleContext.create_or_raise(locale)


# ============================================================================
# CACHING TESTS (v0.20.0+)
# ============================================================================


class TestLocaleContextCaching:
    """Test LocaleContext.create() caching behavior (v0.20.0+).

    create() uses LRU cache to avoid repeated Babel.Locale.parse() calls.
    """

    def test_create_returns_same_instance_for_same_locale(self) -> None:
        """create() returns cached instance for same locale code."""
        ctx1 = LocaleContext.create("en-US")
        ctx2 = LocaleContext.create("en-US")

        # Should be the same object (cached)
        assert ctx1 is ctx2

    def test_create_returns_different_instances_for_different_locales(self) -> None:
        """create() returns different instances for different locale codes."""
        ctx_en = LocaleContext.create("en-US")
        ctx_de = LocaleContext.create("de-DE")

        # Should be different objects
        assert ctx_en is not ctx_de
        assert ctx_en.locale_code != ctx_de.locale_code

    def test_create_caching_with_invalid_locale(self) -> None:
        """create() caches invalid locales consistently."""
        ctx1 = LocaleContext.create("xx-INVALID")
        ctx2 = LocaleContext.create("xx-INVALID")

        # Should be the same object (cached)
        assert ctx1 is ctx2
        # Both should use en_US fallback
        assert ctx1.locale_code == "xx-INVALID"

    def test_create_caching_is_case_insensitive(self) -> None:
        """create() cache treats locale codes as case-insensitive (normalized)."""
        ctx1 = LocaleContext.create("en-US")
        ctx2 = LocaleContext.create("en-us")
        ctx3 = LocaleContext.create("EN-US")

        # These all normalize to the same cache key (en_us)
        # and return the same cached instance
        assert ctx1 is ctx2
        assert ctx1 is ctx3
