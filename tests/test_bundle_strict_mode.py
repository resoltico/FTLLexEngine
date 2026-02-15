"""FluentBundle strict mode tests.

Tests fail-fast behavior:
- strict=True raises FormattingIntegrityError on ANY error
- Exception carries original errors, fallback value, message ID
- All error paths in format_pattern raise in strict mode
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.integrity import FormattingIntegrityError
from ftllexengine.runtime.cache_config import CacheConfig

# ============================================================================
# STRICT MODE BASIC BEHAVIOR TESTS
# ============================================================================


class TestStrictModeProperty:
    """Test strict property reflects initialization state."""

    def test_strict_mode_disabled_by_default(self) -> None:
        """Default bundle has strict=False."""
        bundle = FluentBundle("en")
        assert bundle.strict is False

    def test_strict_mode_enabled_when_requested(self) -> None:
        """Bundle with strict=True has strict property True."""
        bundle = FluentBundle("en", strict=True)
        assert bundle.strict is True

    def test_strict_mode_disabled_explicitly(self) -> None:
        """Bundle with strict=False has strict property False."""
        bundle = FluentBundle("en", strict=False)
        assert bundle.strict is False


class TestStrictModeSuccessfulFormatting:
    """Test strict mode allows successful formatting."""

    def test_strict_mode_returns_result_on_success(self) -> None:
        """Successful formatting returns normally in strict mode."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("hello = Hello, World!")

        result, errors = bundle.format_pattern("hello")

        assert result == "Hello, World!"
        assert errors == ()

    def test_strict_mode_returns_result_with_args(self) -> None:
        """Successful formatting with args returns normally in strict mode."""
        bundle = FluentBundle("en", strict=True, use_isolating=False)
        bundle.add_resource("welcome = Welcome, { $name }!")

        result, errors = bundle.format_pattern("welcome", {"name": "Alice"})

        assert result == "Welcome, Alice!"
        assert errors == ()

    def test_strict_mode_returns_attribute(self) -> None:
        """Successful attribute access returns normally in strict mode."""
        bundle = FluentBundle("en", strict=True, use_isolating=False)
        bundle.add_resource("""
button = Click me
    .tooltip = Save your work
""")

        result, errors = bundle.format_pattern("button", attribute="tooltip")

        assert result == "Save your work"
        assert errors == ()


# ============================================================================
# STRICT MODE ERROR RAISING TESTS
# ============================================================================


class TestStrictModeMissingMessage:
    """Test strict mode raises on missing message."""

    def test_raises_on_missing_message(self) -> None:
        """Missing message raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("nonexistent")

        assert exc_info.value.message_id == "nonexistent"
        assert len(exc_info.value.fluent_errors) == 1
        error = exc_info.value.fluent_errors[0]
        assert isinstance(error, FrozenFluentError)
        assert error.category == ErrorCategory.REFERENCE

    def test_non_strict_returns_fallback_for_missing(self) -> None:
        """Non-strict mode returns fallback for missing message."""
        bundle = FluentBundle("en", strict=False)

        result, errors = bundle.format_pattern("nonexistent")

        assert "{nonexistent}" in result
        assert len(errors) == 1


class TestStrictModeMissingVariable:
    """Test strict mode raises on missing variable."""

    def test_raises_on_missing_variable(self) -> None:
        """Missing variable raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello, { $name }!")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        assert exc_info.value.message_id == "msg"
        assert len(exc_info.value.fluent_errors) >= 1

    def test_non_strict_returns_fallback_for_missing_variable(self) -> None:
        """Non-strict mode returns fallback for missing variable."""
        bundle = FluentBundle("en", strict=False, use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        result, errors = bundle.format_pattern("msg", {})

        assert "{$name}" in result
        assert len(errors) >= 1


class TestStrictModeMissingTerm:
    """Test strict mode raises on missing term reference."""

    def test_raises_on_missing_term(self) -> None:
        """Missing term reference raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Welcome to { -brand }!")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg")

        assert exc_info.value.message_id == "msg"
        assert len(exc_info.value.fluent_errors) >= 1

    def test_non_strict_returns_fallback_for_missing_term(self) -> None:
        """Non-strict mode returns fallback for missing term."""
        bundle = FluentBundle("en", strict=False, use_isolating=False)
        bundle.add_resource("msg = Welcome to { -brand }!")

        result, errors = bundle.format_pattern("msg")

        assert "{-brand}" in result
        assert len(errors) >= 1


class TestStrictModeMissingAttribute:
    """Test strict mode raises on missing attribute."""

    def test_raises_on_missing_attribute(self) -> None:
        """Missing attribute raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("button = Click me")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("button", attribute="nonexistent")

        assert exc_info.value.message_id == "button"
        assert len(exc_info.value.fluent_errors) >= 1


# ============================================================================
# EXCEPTION CONTENT TESTS
# ============================================================================


class TestFormattingIntegrityErrorContent:
    """Test FormattingIntegrityError carries correct information."""

    def test_exception_has_message_id(self) -> None:
        """Exception carries the message ID that failed."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("missing_message")

        assert exc_info.value.message_id == "missing_message"

    def test_exception_has_fluent_errors(self) -> None:
        """Exception carries the original Fluent errors."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $a } { $b } { $c }")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        assert len(exc_info.value.fluent_errors) >= 3
        for error in exc_info.value.fluent_errors:
            assert isinstance(error, FrozenFluentError)

    def test_exception_has_fallback_value(self) -> None:
        """Exception carries the fallback value that would have been returned."""
        bundle = FluentBundle("en", strict=True, use_isolating=False)
        bundle.add_resource("msg = Hello { $name }!")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        # The fallback would contain {$name} placeholder
        assert "{$name}" in exc_info.value.fallback_value

    def test_exception_has_context(self) -> None:
        """Exception carries IntegrityContext for diagnosis."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("missing")

        assert exc_info.value.context is not None
        assert exc_info.value.context.component == "bundle"
        assert exc_info.value.context.operation == "format_pattern"
        assert exc_info.value.context.key == "missing"

    def test_exception_message_describes_errors(self) -> None:
        """Exception message includes error count and summary."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("missing")

        message = str(exc_info.value)
        assert "missing" in message
        assert "error" in message.lower()


# ============================================================================
# FORMAT_VALUE STRICT MODE TESTS
# ============================================================================


class TestFormatValueStrictMode:
    """Test format_value() respects strict mode."""

    def test_format_value_raises_in_strict_mode(self) -> None:
        """format_value() raises in strict mode on error."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $name }")

        with pytest.raises(FormattingIntegrityError):
            bundle.format_value("msg", {})

    def test_format_value_returns_in_non_strict_mode(self) -> None:
        """format_value() returns fallback in non-strict mode."""
        bundle = FluentBundle("en", strict=False, use_isolating=False)
        bundle.add_resource("msg = { $name }")

        result, errors = bundle.format_value("msg", {})

        assert "{$name}" in result
        assert len(errors) >= 1


# ============================================================================
# EDGE CASES AND INVALID INPUT TESTS
# ============================================================================


class TestStrictModeInvalidInput:
    """Test strict mode with invalid inputs."""

    def test_raises_on_empty_message_id(self) -> None:
        """Empty message ID raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("")

        assert exc_info.value.message_id == "<empty>"


# ============================================================================
# CACHING WITH STRICT MODE TESTS
# ============================================================================


class TestStrictModeWithCaching:
    """Test strict mode interaction with caching."""

    def test_successful_format_is_cached(self) -> None:
        """Successful formatting in strict mode is cached."""
        bundle = FluentBundle("en", strict=True, cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        # First call - cache miss
        result1, _ = bundle.format_pattern("msg", {"name": "Alice"})

        # Second call - should be cache hit
        result2, _ = bundle.format_pattern("msg", {"name": "Alice"})

        assert result1 == result2 == "Hello, Alice!"

        # Verify cache was used
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] >= 1

    def test_errors_cached_before_strict_raise(self) -> None:
        """Errors are cached before strict mode raises, enabling cache hits on retry."""
        bundle = FluentBundle("en", strict=True, cache=CacheConfig())
        bundle.add_resource("msg = { $name }")

        # First call: resolves with error, caches result, then raises
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", {})

        # Cache should contain the error result (cache-before-raise pattern)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1


class TestStrictModeCachePropagation:
    """Test that bundle strict mode propagates to cache.

    When FluentBundle is created with strict=True and cache=CacheConfig(),
    the internal IntegrityCache must also use strict=True so that cache
    corruption raises CacheCorruptionError rather than silently evicting.
    """

    def test_strict_bundle_has_strict_cache(self) -> None:
        """Bundle with strict=True creates cache with strict=True."""
        bundle = FluentBundle("en", strict=True, cache=CacheConfig())

        # Access internal cache to verify strict mode
        cache = bundle._cache  # pylint: disable=protected-access
        assert cache is not None
        assert cache.strict is True

    def test_non_strict_bundle_has_non_strict_cache(self) -> None:
        """Bundle with strict=False creates cache with strict=False."""
        bundle = FluentBundle("en", strict=False, cache=CacheConfig())

        cache = bundle._cache  # pylint: disable=protected-access
        assert cache is not None
        assert cache.strict is False

    def test_strict_cache_stats_reflects_mode(self) -> None:
        """Cache stats reflect strict mode setting."""
        bundle = FluentBundle("en", strict=True, cache=CacheConfig())

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["strict"] is True

    def test_non_strict_cache_stats_reflects_mode(self) -> None:
        """Non-strict bundle cache stats reflect strict=False."""
        bundle = FluentBundle("en", strict=False, cache=CacheConfig())

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["strict"] is False


# ============================================================================
# PROPERTY-BASED TESTS
# ============================================================================


class TestStrictModeProperties:
    """Property-based tests for strict mode."""

    @given(st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"))
    @settings(max_examples=50)
    def test_missing_message_always_raises(self, message_id: str) -> None:
        """Any missing message raises in strict mode."""
        event("outcome=raised")

        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern(message_id)

        assert exc_info.value.message_id == message_id

    @given(st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]{0,19}", fullmatch=True))
    @settings(max_examples=50)
    def test_missing_variable_always_raises(self, var_name: str) -> None:
        """Any missing variable raises in strict mode."""
        event("outcome=raised")

        bundle = FluentBundle("en", strict=True)
        # Variable names must start with a letter (FTL spec)
        bundle.add_resource(f"msg = Hello {{ ${var_name} }}!")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        assert exc_info.value.message_id == "msg"
        assert len(exc_info.value.fluent_errors) >= 1


# ============================================================================
# THREAD SAFETY TESTS
# ============================================================================


class TestStrictModeThreadSafety:
    """Test strict mode is thread-safe."""

    def test_concurrent_strict_formatting(self) -> None:
        """Strict mode works correctly under concurrent access."""
        bundle = FluentBundle("en", strict=True, cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        errors: list[Exception] = []
        results: list[str] = []
        lock = threading.Lock()

        def format_message(name: str) -> str:
            try:
                result, _ = bundle.format_pattern("msg", {"name": name})
                with lock:
                    results.append(result)
                return result
            except Exception as e:
                with lock:
                    errors.append(e)
                raise

        names = [f"User{i}" for i in range(100)]

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_message, name) for name in names]
            for future in as_completed(futures):
                future.result()  # Re-raise any exceptions

        assert len(errors) == 0
        assert len(results) == 100

    def test_concurrent_strict_errors(self) -> None:
        """Strict mode raises correctly under concurrent error conditions."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $name }")

        error_count = 0
        lock = threading.Lock()

        def try_format() -> None:
            nonlocal error_count
            try:
                bundle.format_pattern("msg", {})
            except FormattingIntegrityError:
                with lock:
                    error_count += 1

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(try_format) for _ in range(100)]
            for future in as_completed(futures):
                future.result()

        # All 100 attempts should have raised
        assert error_count == 100
