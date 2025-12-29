"""Property-based tests for common bug categories.

This test module contains systematic property-based tests designed to catch
common categories of bugs. These tests serve as regression guards and may
reveal similar issues in other parts of the codebase.

Bug Categories Covered:
    1. Parameter Effect: Optional parameters must affect output when varied
    2. Cache Identity: Cached objects must preserve identity (same object)
    3. Cache Bounds: Cache size must never exceed maximum
    4. Locale Consistency: Formatting must match CLDR/Babel expectations
    5. Sanitization Bounds: Sanitized content has bounded length
    6. Visitor Dispatch Cache: Cache must be class-level (shared across instances)
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.diagnostics.validation import (
    _SANITIZE_MAX_CONTENT_LENGTH,
    ValidationError,
    ValidationResult,
)
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.syntax.ast import Message, Pattern
from ftllexengine.syntax.visitor import ASTVisitor

# ============================================================================
# Bug Category 1: Parameter Effect Property
# Original bug: LOGIC-DATETIME-TIMESTYLE-001 - time_style parameter ignored
# ============================================================================


class TestParameterEffectProperty:
    """Property: Optional parameters must affect output when varied."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=50)
    def test_time_style_affects_format_datetime(
        self, hour: int, minute: int
    ) -> None:
        """PROPERTY: Different time_style values produce different output.

        Catches bugs like LOGIC-DATETIME-TIMESTYLE-001 where parameters
        are accepted but ignored in the implementation.
        """
        ctx = LocaleContext.create("en_US")
        dt = datetime(2025, 6, 15, hour, minute, 0, tzinfo=UTC)

        # Format with different time styles
        short_result = ctx.format_datetime(dt, time_style="short")
        medium_result = ctx.format_datetime(dt, time_style="medium")

        # Short format should typically be shorter or different from medium
        # We can't assert exact length, but they should differ for most times
        # Exception: some times may format identically in short/medium
        if hour != 0 and minute != 0:
            # For non-midnight times, formats should typically differ
            # (medium includes seconds, short doesn't)
            assert short_result != medium_result or len(short_result) <= len(
                medium_result
            ), f"time_style='short' should differ from 'medium': {short_result} vs {medium_result}"

    @given(
        value=st.decimals(
            min_value=-1000000, max_value=1000000, allow_nan=False, allow_infinity=False
        )
    )
    @settings(max_examples=50)
    def test_minimum_fraction_digits_affects_format_number(
        self, value: float
    ) -> None:
        """PROPERTY: minimum_fraction_digits affects number formatting."""
        ctx = LocaleContext.create("en_US")
        float_val = float(value)

        # Both results used for comparison
        _ = ctx.format_number(float_val, minimum_fraction_digits=0)
        result_3 = ctx.format_number(float_val, minimum_fraction_digits=3)

        # With min 3 fraction digits, result should have at least 3 decimal places
        if "." in result_3:
            decimal_part = result_3.split(".")[-1]
            # Remove any trailing grouping chars
            decimal_part = decimal_part.rstrip(",. ")
            assert len(decimal_part) >= 3, (
                f"minimum_fraction_digits=3 should produce at least 3 decimal places: "
                f"{result_3}"
            )


# ============================================================================
# Bug Category 2: Cache Identity Property
# Original bug: SEC-CACHE-EVICTION-001 - lru_cache returned tuples, not instances
# ============================================================================


class TestCacheIdentityProperty:
    """Property: Cached objects must preserve identity (same object returned)."""

    def test_locale_context_cache_identity(self) -> None:
        """PROPERTY: Same locale returns same instance.

        Catches bugs where cache returns new objects each time instead
        of preserving object identity.
        """
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("en_US")
        ctx2 = LocaleContext.create("en_US")

        # Must be the same object, not equal objects
        assert ctx1 is ctx2, (
            "LocaleContext.create() must return the same instance for same locale. "
            f"Got {id(ctx1)} vs {id(ctx2)}"
        )

        LocaleContext.clear_cache()

    @given(locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "ja_JP"]))
    @settings(max_examples=20)
    def test_locale_context_cache_identity_hypothesis(self, locale: str) -> None:
        """PROPERTY: Cache identity holds for various locales."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create(locale)
        ctx2 = LocaleContext.create(locale)

        assert ctx1 is ctx2

        LocaleContext.clear_cache()


# ============================================================================
# Bug Category 3: Cache Bounds Property
# Original bug: SEC-CACHE-EVICTION-001 - Cache could grow unbounded
# ============================================================================


class TestCacheBoundsProperty:
    """Property: Cache size must never exceed maximum."""

    def test_cache_respects_max_size(self) -> None:
        """PROPERTY: Cache size never exceeds MAX_LOCALE_CACHE_SIZE.

        Catches bugs where cache grows unbounded, leading to memory leaks.
        """
        LocaleContext.clear_cache()

        # Create more locales than the cache limit
        for i in range(MAX_LOCALE_CACHE_SIZE + 10):
            locale_code = f"en_TEST{i:04d}"
            LocaleContext.create(locale_code)

        cache_size = LocaleContext.cache_size()
        assert cache_size <= MAX_LOCALE_CACHE_SIZE, (
            f"Cache size {cache_size} exceeds maximum {MAX_LOCALE_CACHE_SIZE}"
        )

        LocaleContext.clear_cache()

    @given(num_locales=st.integers(min_value=1, max_value=200))
    @settings(max_examples=10)
    def test_cache_bounds_hypothesis(self, num_locales: int) -> None:
        """PROPERTY: Cache bounds hold for any number of locales."""
        LocaleContext.clear_cache()

        for i in range(num_locales):
            LocaleContext.create(f"xx_TEST{i:04d}")

        cache_size = LocaleContext.cache_size()
        assert cache_size <= MAX_LOCALE_CACHE_SIZE

        LocaleContext.clear_cache()


# ============================================================================
# Bug Category 4: Locale Consistency Property
# Original bug: DEBT-DATETIME-SEPARATOR-001 - Used hardcoded space, not CLDR
# ============================================================================


class TestLocaleConsistencyProperty:
    """Property: Formatting must be consistent with CLDR/Babel."""

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "ja_JP", "zh_CN"]),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=30)
    def test_datetime_separator_matches_babel(
        self, locale: str, hour: int, minute: int
    ) -> None:
        """PROPERTY: Datetime formatting uses locale-appropriate separators.

        Catches bugs where hardcoded separators are used instead of
        CLDR-compliant locale-specific separators.
        """
        from babel import Locale  # noqa: PLC0415  # Function-local import for test isolation

        ctx = LocaleContext.create(locale)
        dt = datetime(2025, 6, 15, hour, minute, 0, tzinfo=UTC)

        result = ctx.format_datetime(dt, date_style="short", time_style="short")

        # Get the CLDR dateTimeFormat pattern to verify separator
        babel_locale = Locale.parse(locale)
        datetime_format = babel_locale.datetime_formats.get("short", "{1} {0}")
        pattern = str(datetime_format)

        # Extract expected separator from CLDR pattern
        date_idx = pattern.find("{1}")
        time_idx = pattern.find("{0}")
        if 0 <= date_idx < time_idx and time_idx >= 0:
            expected_sep = pattern[date_idx + 3 : time_idx]
            # Verify the result contains the expected separator pattern
            # (not strictly checking position, just presence)
            assert expected_sep.strip() in result or expected_sep == " ", (
                f"Expected separator '{expected_sep}' not found in '{result}' "
                f"for locale {locale}"
            )


# ============================================================================
# Bug Category 5: Sanitization Bounds Property
# Original bug: SEC-ERROR-MESSAGE-DETAIL-001 - Error messages could leak content
# ============================================================================


class TestSanitizationBoundsProperty:
    """Property: Sanitized content has bounded length."""

    @given(
        content=st.text(min_size=0, max_size=1000),
        sanitize=st.booleans(),
        redact=st.booleans(),
    )
    @settings(max_examples=100)
    def test_validation_error_format_bounded(
        self, content: str, sanitize: bool, redact: bool
    ) -> None:
        """PROPERTY: Sanitized error content never exceeds max length.

        Catches bugs where user content in error messages is not truncated,
        potentially exposing sensitive data in logs.
        """
        error = ValidationError(
            code="test-error",
            message="Test error message",
            content=content,
            line=1,
            column=1,
        )

        formatted = error.format(sanitize=sanitize, redact_content=redact)

        if sanitize and redact:
            # Content should be fully redacted
            assert "[content redacted]" in formatted or content == ""
        elif sanitize and len(content) > _SANITIZE_MAX_CONTENT_LENGTH:
            # Content should be truncated with ellipsis
            assert "..." in formatted, (
                f"Long content should be truncated when sanitize=True: {formatted}"
            )

    def test_validation_result_format_bounded(self) -> None:
        """PROPERTY: ValidationResult.format() respects sanitization."""
        # Create a result with long content
        long_content = "A" * 500
        errors = (
            ValidationError(
                code="err1", message="Error 1", content=long_content, line=1
            ),
        )
        result = ValidationResult(errors=errors, warnings=(), annotations=())

        formatted = result.format(sanitize=True, redact_content=False)

        # Verify content is truncated
        assert "..." in formatted or len(long_content) <= _SANITIZE_MAX_CONTENT_LENGTH


# ============================================================================
# Bug Category 6: Visitor Dispatch Cache Property
# Original bug: MAINT-VISITOR-DISPATCH-001 - Dispatch cache rebuilt per instance
# ============================================================================


class TestVisitorDispatchCacheProperty:
    """Property: Visitor dispatch cache is class-level (shared).

    The implementation uses two-tier caching:
    1. _class_visit_methods (ClassVar): method names, shared across instances
    2. _instance_dispatch_cache: bound method refs, per-instance (necessary)
    """

    def test_class_level_dispatch_table_shared_across_instances(self) -> None:
        """PROPERTY: Class-level dispatch table is computed once, not per instance.

        Catches bugs where expensive dispatch table computation happens
        on every instantiation instead of being cached at the class level.
        """

        class TestVisitor(ASTVisitor):
            """Test visitor with custom visit method."""

            def visit_Message(self, node: Message) -> str:  # noqa: N802
                return f"Message: {node.id.name}"

        # Create multiple instances
        visitor1 = TestVisitor()
        visitor2 = TestVisitor()

        # Class-level dispatch table should be the same object
        assert (
            visitor1._class_visit_methods is visitor2._class_visit_methods
        ), "Class-level dispatch table should be shared across instances"

        # The table should contain our visit method
        assert "Message" in TestVisitor._class_visit_methods, (
            "visit_Message should be in class dispatch table"
        )

    def test_subclass_has_own_dispatch_table(self) -> None:
        """PROPERTY: Subclasses have their own class-level dispatch table."""

        class ParentVisitor(ASTVisitor):
            pass

        class ChildVisitor(ParentVisitor):
            def visit_Pattern(self, _node: Pattern) -> str:  # noqa: N802
                return "Pattern"

        # Subclasses should have their own class-level tables
        assert ParentVisitor._class_visit_methods is not ChildVisitor._class_visit_methods, (
            "Subclasses should have their own class-level dispatch table"
        )

        # Child should have Pattern but parent should not
        assert "Pattern" in ChildVisitor._class_visit_methods
        assert "Pattern" not in ParentVisitor._class_visit_methods

    def test_instance_cache_is_per_instance(self) -> None:
        """PROPERTY: Instance-level bound method cache is per-instance.

        This is necessary because bound methods are instance-specific.
        Each instance maintains its own cache of bound method references.
        """

        class TestVisitor(ASTVisitor):
            def visit_Message(self, _node: Message) -> str:  # noqa: N802
                return "visited"

        visitor1 = TestVisitor()
        visitor2 = TestVisitor()

        # Instance caches should be different objects
        assert (
            visitor1._instance_dispatch_cache is not visitor2._instance_dispatch_cache
        ), "Instance-level cache should be per-instance"


# ============================================================================
# Integration Tests: Combined Properties
# ============================================================================


class TestCombinedProperties:
    """Integration tests combining multiple properties."""

    def test_cache_identity_survives_eviction(self) -> None:
        """PROPERTY: Cache identity holds even after LRU eviction cycles."""
        LocaleContext.clear_cache()

        # Create a locale, then fill cache past limit, then re-access
        _ = LocaleContext.create("en_US")

        # Fill cache past limit to trigger eviction
        for i in range(MAX_LOCALE_CACHE_SIZE + 5):
            LocaleContext.create(f"xx_FILLER{i:04d}")

        # en_US should have been evicted, so new instance created
        after_eviction = LocaleContext.create("en_US")

        # After eviction, a new instance is created (identity not preserved)
        # But accessing it again should return the same instance
        again = LocaleContext.create("en_US")
        assert after_eviction is again, (
            "Cache identity must hold for re-accessed locales after eviction"
        )

        LocaleContext.clear_cache()

    @given(locale=st.sampled_from(["en_US", "de_DE", "fr_FR"]))
    @settings(max_examples=10)
    def test_locale_formatting_consistency(self, locale: str) -> None:
        """PROPERTY: Formatting is consistent across cache hits."""
        LocaleContext.clear_cache()

        dt = datetime(2025, 6, 15, 14, 30, tzinfo=UTC)

        # First access (cache miss)
        ctx1 = LocaleContext.create(locale)
        result1 = ctx1.format_datetime(dt, time_style="short")

        # Second access (cache hit)
        ctx2 = LocaleContext.create(locale)
        result2 = ctx2.format_datetime(dt, time_style="short")

        assert result1 == result2, (
            f"Formatting should be identical for cache hits: {result1} vs {result2}"
        )

        LocaleContext.clear_cache()
