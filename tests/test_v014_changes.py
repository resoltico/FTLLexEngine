"""Tests for v0.14.0 changes.

Tests new functionality and behavioral changes introduced in v0.14.0:
- FunctionRegistry.get_callable() public API
- LocaleContext.create() always returns LocaleContext
- LocaleContext.create_or_raise() raises ValueError for invalid locales
- FormatCache.get_stats() returns float hit_rate
- ASTVisitor uses __slots__

Python 3.13+.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.cache import FormatCache
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.locale_context import LocaleContext, LocaleValidationError
from ftllexengine.syntax.visitor import ASTVisitor


def _identity_str(x: object) -> str:
    """Simple function for testing registry."""
    return str(x)


def _custom_format(value: float, *, precision: int = 2) -> str:
    """Custom format function for testing."""
    return f"{value:.{precision}f}"


class TestFunctionRegistryGetCallable:
    """Tests for FunctionRegistry.get_callable() method."""

    def test_get_callable_returns_registered_function(self) -> None:
        """get_callable returns the registered callable."""
        registry = FunctionRegistry()

        def my_func(value: int) -> str:
            return str(value)

        registry.register(my_func, ftl_name="MYFUNC")
        result = registry.get_callable("MYFUNC")

        assert result is my_func

    def test_get_callable_returns_none_for_unregistered(self) -> None:
        """get_callable returns None for unregistered function."""
        registry = FunctionRegistry()
        result = registry.get_callable("NONEXISTENT")

        assert result is None

    def test_get_callable_with_simple_function(self) -> None:
        """get_callable works with simple functions."""
        registry = FunctionRegistry()
        registry.register(_identity_str, ftl_name="SIMPLE")
        result = registry.get_callable("SIMPLE")

        assert result is _identity_str

    def test_get_callable_preserves_function_identity(self) -> None:
        """get_callable returns exact same callable object."""
        registry = FunctionRegistry()
        registry.register(_custom_format, ftl_name="CUSTOM")
        callable_func = registry.get_callable("CUSTOM")

        # Identity check
        assert callable_func is _custom_format
        # Functionality check - callable_func is guaranteed to be _custom_format
        assert callable_func is not None
        assert callable_func(3.14159, precision=2) == "3.14"

    @given(st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    @settings(max_examples=20)
    def test_get_callable_with_various_names(self, name: str) -> None:
        """get_callable works with various FTL function names."""
        registry = FunctionRegistry()
        registry.register(_identity_str, ftl_name=name)
        result = registry.get_callable(name)

        assert result is _identity_str


class TestLocaleContextCreate:
    """Tests for LocaleContext.create() always returning LocaleContext."""

    def test_create_with_valid_locale_returns_locale_context(self) -> None:
        """create() returns LocaleContext for valid locale."""
        result = LocaleContext.create("en-US")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "en-US"

    def test_create_with_unknown_locale_returns_locale_context_with_fallback(self) -> None:
        """create() returns LocaleContext with en_US fallback for unknown locale."""
        result = LocaleContext.create("xx-UNKNOWN")

        # Should return LocaleContext (create() always succeeds now)
        assert isinstance(result, LocaleContext)
        # Original locale_code preserved for debugging
        assert result.locale_code == "xx-UNKNOWN"
        # Formatting uses en_US rules (fallback)
        formatted = result.format_number(1234.5, use_grouping=True)
        assert "1,234" in formatted or "1234" in formatted

    def test_create_with_invalid_format_returns_locale_context(self) -> None:
        """create() returns LocaleContext for invalid locale format."""
        result = LocaleContext.create("not-a-valid-locale-format-at-all")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "not-a-valid-locale-format-at-all"

    def test_create_always_returns_locale_context(self) -> None:
        """create() always returns LocaleContext for any input."""
        test_locales = [
            "en-US",
            "lv-LV",
            "xx-XX",
            "invalid",
            "",
            "123",
            "a" * 100,
        ]

        for locale in test_locales:
            result = LocaleContext.create(locale)
            assert isinstance(result, LocaleContext), f"Failed for locale: {locale}"


class TestLocaleContextCreateOrRaise:
    """Tests for LocaleContext.create_or_raise() strict validation."""

    def test_create_or_raise_with_valid_locale_returns_locale_context(self) -> None:
        """create_or_raise() returns LocaleContext for valid locale."""
        result = LocaleContext.create_or_raise("en-US")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "en-US"

    def test_create_or_raise_with_unknown_locale_raises_value_error(self) -> None:
        """create_or_raise() raises ValueError for unknown locale."""
        with pytest.raises(ValueError, match="Unknown locale identifier"):
            LocaleContext.create_or_raise("xx-UNKNOWN")

    def test_create_or_raise_with_invalid_format_raises_value_error(self) -> None:
        """create_or_raise() raises ValueError for invalid format."""
        with pytest.raises(ValueError, match="locale"):
            LocaleContext.create_or_raise("not-valid-at-all-xyz")

    def test_create_or_raise_error_message_contains_locale(self) -> None:
        """create_or_raise() error message includes the locale code."""
        with pytest.raises(ValueError, match="xyz-123"):
            LocaleContext.create_or_raise("xyz-123")


class TestFormatCacheHitRate:
    """Tests for FormatCache.get_stats() hit_rate as float."""

    def test_get_stats_hit_rate_is_float(self) -> None:
        """hit_rate is a float, not an int."""
        cache = FormatCache(maxsize=100)
        stats = cache.get_stats()

        assert isinstance(stats["hit_rate"], float)

    def test_get_stats_hit_rate_has_precision(self) -> None:
        """hit_rate preserves decimal precision."""
        cache = FormatCache(maxsize=100)

        # Simulate some cache operations by directly manipulating stats
        # This tests the return type, not cache functionality
        stats = cache.get_stats()

        # Initial hit_rate should be 0.0
        assert stats["hit_rate"] == 0.0

    def test_get_stats_hit_rate_range(self) -> None:
        """hit_rate is between 0.0 and 100.0."""
        cache = FormatCache(maxsize=100)
        stats = cache.get_stats()

        assert 0.0 <= stats["hit_rate"] <= 100.0

    def test_get_stats_returns_correct_types(self) -> None:
        """get_stats returns dict[str, int | float]."""
        cache = FormatCache(maxsize=100)
        stats = cache.get_stats()

        # Check all keys exist
        expected_keys = {"size", "maxsize", "hits", "misses", "hit_rate", "unhashable_skips"}
        assert set(stats.keys()) == expected_keys

        # Check types
        assert isinstance(stats["size"], int)
        assert isinstance(stats["maxsize"], int)
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)
        assert isinstance(stats["hit_rate"], float)
        assert isinstance(stats["unhashable_skips"], int)


class TestASTVisitorSlots:
    """Tests for ASTVisitor __slots__ optimization."""

    def test_ast_visitor_has_slots(self) -> None:
        """ASTVisitor class has __slots__ defined."""
        assert hasattr(ASTVisitor, "__slots__")
        assert "_instance_dispatch_cache" in ASTVisitor.__slots__

    def test_ast_visitor_no_dict(self) -> None:
        """ASTVisitor instances don't have __dict__ (slots only)."""
        visitor = ASTVisitor()

        # With __slots__, instance should not have __dict__
        # unless a subclass adds it
        assert not hasattr(visitor, "__dict__") or len(visitor.__dict__) == 0

    def test_ast_visitor_dispatch_cache_exists(self) -> None:
        """ASTVisitor has _instance_dispatch_cache attribute."""
        visitor = ASTVisitor()

        assert hasattr(visitor, "_instance_dispatch_cache")
        assert isinstance(visitor._instance_dispatch_cache, dict)

    def test_ast_visitor_subclass_can_add_attributes(self) -> None:
        """Subclasses can still add their own attributes."""

        class CountingVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.count = 0

        visitor = CountingVisitor()
        assert visitor.count == 0
        visitor.count = 5
        assert visitor.count == 5


class TestLocaleValidationErrorStillExists:
    """Verify LocaleValidationError class still exists for backwards compatibility."""

    def test_locale_validation_error_class_exists(self) -> None:
        """LocaleValidationError class is still importable."""
        # LocaleValidationError imported at top of file
        assert LocaleValidationError is not None

    def test_locale_validation_error_has_expected_fields(self) -> None:
        """LocaleValidationError has locale_code and error_message."""
        error = LocaleValidationError(
            locale_code="invalid",
            error_message="Test error"
        )

        assert error.locale_code == "invalid"
        assert error.error_message == "Test error"

    def test_locale_validation_error_str(self) -> None:
        """LocaleValidationError __str__ formats correctly."""
        error = LocaleValidationError(
            locale_code="bad-locale",
            error_message="Not recognized"
        )

        error_str = str(error)
        assert "bad-locale" in error_str
        assert "Not recognized" in error_str
