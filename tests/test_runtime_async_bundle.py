"""Tests for AsyncFluentBundle — async-native wrapper around FluentBundle.

Covers:
- Async context manager protocol (__aenter__ / __aexit__)
- add_resource / add_resource_stream (async; offloads to thread pool)
- format_pattern (async; offloads to thread pool)
- add_function (async)
- Sync read operations (has_message, has_attribute, get_message_ids,
  get_message, get_term, introspect_message)
- Properties (locale, strict, use_isolating, cache_enabled, cache_config)
- for_system_locale classmethod (patched to avoid env dependency)
- Strict-mode error propagation
- Concurrent format operations (multiple tasks)
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from ftllexengine import AsyncFluentBundle
from ftllexengine.integrity import FormattingIntegrityError, SyntaxIntegrityError
from ftllexengine.runtime import CacheConfig
from ftllexengine.syntax.ast import Message, Term

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_FTL = "greeting = Hello, { $name }!\nfarewell = Goodbye!"

_MULTI_LINE_FTL = [
    "greeting = Hello, { $name }!",
    "",
    "farewell = Goodbye!",
    "",
]


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------


class TestAsyncContextManager:
    """AsyncFluentBundle supports the async context manager protocol."""

    def test_aenter_returns_self(self) -> None:
        """__aenter__ returns the bundle instance itself."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US")
            result = await bundle.__aenter__()
            assert result is bundle

        asyncio.run(run())

    def test_async_with_block(self) -> None:
        """async with block yields the bundle and exits cleanly."""

        async def run() -> AsyncFluentBundle:
            async with AsyncFluentBundle("en_US") as bundle:
                return bundle

        bundle = asyncio.run(run())
        assert isinstance(bundle, AsyncFluentBundle)

    def test_aexit_on_no_exception(self) -> None:
        """__aexit__ with no exception is a no-op (returns None implicitly)."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US")
            await bundle.__aexit__(None, None, None)  # must not raise

        asyncio.run(run())

    def test_aexit_propagates_exception(self) -> None:
        """Exceptions inside async with block propagate normally."""
        _sentinel = "sentinel"

        async def run() -> None:
            with pytest.raises(ValueError, match=_sentinel):
                async with AsyncFluentBundle("en_US"):
                    raise ValueError(_sentinel)

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    """Sync properties mirror the underlying FluentBundle."""

    def test_locale(self) -> None:
        """locale property returns the normalized locale code."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.locale == "en_us"

    def test_strict_default_true(self) -> None:
        """strict is True by default."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.strict is True

    def test_strict_false(self) -> None:
        """strict=False is reflected in the property."""
        bundle = AsyncFluentBundle("en_US", strict=False)
        assert bundle.strict is False

    def test_use_isolating_default_true(self) -> None:
        """use_isolating is True by default."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.use_isolating is True

    def test_use_isolating_false(self) -> None:
        """use_isolating=False is reflected in the property."""
        bundle = AsyncFluentBundle("en_US", use_isolating=False)
        assert bundle.use_isolating is False

    def test_cache_enabled_default_false(self) -> None:
        """cache_enabled is False when no CacheConfig is provided."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.cache_enabled is False

    def test_cache_enabled_with_config(self) -> None:
        """cache_enabled is True when a CacheConfig is provided."""
        bundle = AsyncFluentBundle("en_US", cache=CacheConfig())
        assert bundle.cache_enabled is True

    def test_cache_config_none_by_default(self) -> None:
        """cache_config is None when caching is not configured."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.cache_config is None

    def test_cache_config_present(self) -> None:
        """cache_config returns the CacheConfig when provided."""
        cfg = CacheConfig()
        bundle = AsyncFluentBundle("en_US", cache=cfg)
        assert bundle.cache_config is cfg

    def test_repr(self) -> None:
        """__repr__ includes locale and strict."""
        bundle = AsyncFluentBundle("en_US")
        r = repr(bundle)
        assert "AsyncFluentBundle" in r
        assert "en_us" in r
        assert "strict=True" in r


# ---------------------------------------------------------------------------
# add_resource
# ---------------------------------------------------------------------------


class TestAddResource:
    """add_resource loads FTL source and registers messages."""

    def test_add_resource_basic(self) -> None:
        """Messages registered via add_resource become has_message-visible."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US")
            junk = await bundle.add_resource("greeting = Hello!")
            assert junk == ()
            assert bundle.has_message("greeting")

        asyncio.run(run())

    def test_add_resource_returns_empty_junk_on_success(self) -> None:
        """add_resource returns empty tuple when there are no parse errors."""

        async def run() -> tuple[Any, ...]:
            bundle = AsyncFluentBundle("en_US")
            return await bundle.add_resource(_SIMPLE_FTL)

        junk = asyncio.run(run())
        assert junk == ()

    def test_add_resource_strict_raises_on_junk(self) -> None:
        """In strict mode, junk entries raise SyntaxIntegrityError."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US", strict=True)
            with pytest.raises(SyntaxIntegrityError):
                await bundle.add_resource("= this is not valid FTL")

        asyncio.run(run())

    def test_add_resource_non_strict_returns_junk(self) -> None:
        """In non-strict mode, junk entries are returned, not raised."""

        async def run() -> tuple[Any, ...]:
            bundle = AsyncFluentBundle("en_US", strict=False)
            return await bundle.add_resource("= this is not valid FTL")

        junk = asyncio.run(run())
        assert len(junk) > 0

    def test_add_resource_type_error_on_bytes(self) -> None:
        """add_resource raises TypeError when bytes are passed instead of str."""
        _bad_input: str = b"greeting = Hi!"  # type: ignore[assignment]

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US")
            with pytest.raises(TypeError):
                await bundle.add_resource(_bad_input)

        asyncio.run(run())

    def test_add_resource_with_source_path(self) -> None:
        """source_path does not affect parse outcome; only used for error messages."""

        async def run() -> tuple[Any, ...]:
            bundle = AsyncFluentBundle("en_US")
            return await bundle.add_resource("msg = Text", source_path="test.ftl")

        junk = asyncio.run(run())
        assert junk == ()


# ---------------------------------------------------------------------------
# add_resource_stream
# ---------------------------------------------------------------------------


class TestAddResourceStream:
    """add_resource_stream loads FTL from a line iterator."""

    def test_stream_registers_messages(self) -> None:
        """Messages from a line iterator become has_message-visible."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US")
            junk = await bundle.add_resource_stream(_MULTI_LINE_FTL)
            assert junk == ()
            assert bundle.has_message("greeting")
            assert bundle.has_message("farewell")

        asyncio.run(run())

    def test_stream_from_list_of_lines(self) -> None:
        """A plain list of strings is accepted as the iterable source."""

        async def run() -> tuple[Any, ...]:
            bundle = AsyncFluentBundle("en_US")
            return await bundle.add_resource_stream(["msg = Hello!"])

        junk = asyncio.run(run())
        assert junk == ()

    def test_stream_strict_raises_on_junk(self) -> None:
        """Junk entries in the stream raise SyntaxIntegrityError in strict mode."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US", strict=True)
            with pytest.raises(SyntaxIntegrityError):
                await bundle.add_resource_stream(["= invalid"])

        asyncio.run(run())

    def test_stream_with_source_path(self) -> None:
        """source_path kwarg is forwarded to the underlying bundle."""

        async def run() -> tuple[Any, ...]:
            bundle = AsyncFluentBundle("en_US")
            return await bundle.add_resource_stream(
                ["msg = Text"], source_path="locales/en.ftl"
            )

        junk = asyncio.run(run())
        assert junk == ()


# ---------------------------------------------------------------------------
# format_pattern
# ---------------------------------------------------------------------------


class TestFormatPattern:
    """format_pattern resolves messages with locale-aware formatting."""

    def test_format_pattern_simple(self) -> None:
        """Simple message formats without variables."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US")
            await bundle.add_resource("farewell = Goodbye!")
            return await bundle.format_pattern("farewell")

        result, errors = asyncio.run(run())
        assert result == "Goodbye!"
        assert errors == ()

    def test_format_pattern_with_variable(self) -> None:
        """Variable interpolation works with bidi isolation marks."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US", use_isolating=False)
            await bundle.add_resource("greeting = Hello, { $name }!")
            return await bundle.format_pattern("greeting", {"name": "Alice"})

        result, errors = asyncio.run(run())
        assert result == "Hello, Alice!"
        assert errors == ()

    def test_format_pattern_currency(self) -> None:
        """CURRENCY function formats Decimal with locale-aware symbol."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US")
            await bundle.add_resource(
                'price = Total: { CURRENCY($amount, currency: "USD") }'
            )
            return await bundle.format_pattern("price", {"amount": Decimal("99.99")})

        result, errors = asyncio.run(run())
        assert errors == ()
        assert "$99.99" in result

    def test_format_pattern_strict_raises_on_missing_message(self) -> None:
        """In strict mode, missing message raises FormattingIntegrityError."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US", strict=True)
            await bundle.add_resource("greeting = Hello!")
            with pytest.raises(FormattingIntegrityError):
                await bundle.format_pattern("nonexistent")

        asyncio.run(run())

    def test_format_pattern_non_strict_missing_message(self) -> None:
        """In non-strict mode, missing message returns fallback and an error."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US", strict=False)
            await bundle.add_resource("greeting = Hello!")
            return await bundle.format_pattern("nonexistent")

        result, errors = asyncio.run(run())
        assert len(errors) > 0
        assert "nonexistent" in result

    def test_format_pattern_with_attribute(self) -> None:
        """Attribute access via the attribute= keyword."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US")
            await bundle.add_resource("button = Click\n    .tooltip = Save the file")
            return await bundle.format_pattern("button", attribute="tooltip")

        result, errors = asyncio.run(run())
        assert result == "Save the file"
        assert errors == ()

    def test_format_pattern_concurrent(self) -> None:
        """Multiple concurrent format_pattern calls complete without data races."""

        async def run() -> list[str]:
            bundle = AsyncFluentBundle("en_US", use_isolating=False)
            await bundle.add_resource("counter = Count: { $n }")
            tasks = [
                asyncio.create_task(
                    bundle.format_pattern("counter", {"n": i})
                )
                for i in range(20)
            ]
            results = await asyncio.gather(*tasks)
            return [r for r, _ in results]

        results = asyncio.run(run())
        assert len(results) == 20
        for i, result in enumerate(results):
            assert f"Count: {i}" == result


# ---------------------------------------------------------------------------
# add_function
# ---------------------------------------------------------------------------


class TestAddFunction:
    """add_function registers custom Fluent functions."""

    def test_add_function_callable(self) -> None:
        """Custom function is invoked during format_pattern."""

        async def run() -> tuple[str, tuple[Any, ...]]:
            bundle = AsyncFluentBundle("en_US", use_isolating=False)
            await bundle.add_function("SHOUT", lambda val, **_: str(val).upper())
            await bundle.add_resource("shout = { SHOUT($word) }")
            return await bundle.format_pattern("shout", {"word": "hello"})

        result, errors = asyncio.run(run())
        assert result == "HELLO"
        assert errors == ()


# ---------------------------------------------------------------------------
# Sync read operations
# ---------------------------------------------------------------------------


class TestSyncReadOperations:
    """Sync read methods (has_message, get_message, etc.) delegate to the bundle."""

    def setup_method(self) -> None:
        """Load a shared bundle for read tests."""

        async def build() -> AsyncFluentBundle:
            bundle = AsyncFluentBundle("en_US")
            await bundle.add_resource(
                "greeting = Hello!\n"
                "farewell = Goodbye!\n"
                "button = Click\n"
                "    .tooltip = Save\n"
                "-brand = Firefox"
            )
            return bundle

        self.bundle = asyncio.run(build())

    def test_has_message_true(self) -> None:
        """has_message returns True for a registered message."""
        assert self.bundle.has_message("greeting") is True

    def test_has_message_false(self) -> None:
        """has_message returns False for an absent message."""
        assert self.bundle.has_message("nonexistent") is False

    def test_has_attribute_true(self) -> None:
        """has_attribute returns True for an existing attribute."""
        assert self.bundle.has_attribute("button", "tooltip") is True

    def test_has_attribute_false_missing_attr(self) -> None:
        """has_attribute returns False for a missing attribute."""
        assert self.bundle.has_attribute("button", "missing") is False

    def test_has_attribute_false_missing_message(self) -> None:
        """has_attribute returns False when the message itself is absent."""
        assert self.bundle.has_attribute("nonexistent", "tooltip") is False

    def test_get_message_ids(self) -> None:
        """get_message_ids returns all registered message IDs."""
        ids = self.bundle.get_message_ids()
        assert "greeting" in ids
        assert "farewell" in ids
        assert "button" in ids

    def test_get_message_found(self) -> None:
        """get_message returns the AST node for a known message."""
        msg = self.bundle.get_message("greeting")
        assert isinstance(msg, Message)
        assert msg.id.name == "greeting"

    def test_get_message_not_found(self) -> None:
        """get_message returns None for an absent message."""
        assert self.bundle.get_message("nonexistent") is None

    def test_get_term_found(self) -> None:
        """get_term returns the AST node for a registered term."""
        term = self.bundle.get_term("brand")
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_get_term_not_found(self) -> None:
        """get_term returns None for an absent term."""
        assert self.bundle.get_term("nonexistent") is None

    def test_introspect_message(self) -> None:
        """introspect_message returns variable and function metadata."""

        async def build() -> AsyncFluentBundle:
            bundle = AsyncFluentBundle("en_US")
            await bundle.add_resource("price = { NUMBER($amount) }")
            return bundle

        bundle = asyncio.run(build())
        info = bundle.introspect_message("price")
        assert "amount" in info.get_variable_names()
        assert "NUMBER" in info.get_function_names()

    def test_introspect_message_key_error(self) -> None:
        """introspect_message raises KeyError for an absent message."""
        with pytest.raises(KeyError, match="nonexistent"):
            self.bundle.introspect_message("nonexistent")


# ---------------------------------------------------------------------------
# Cache operations
# ---------------------------------------------------------------------------


class TestCacheOperations:
    """Cache stats and audit log delegate correctly."""

    def test_get_cache_stats_none_when_disabled(self) -> None:
        """get_cache_stats returns None when caching is not configured."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.get_cache_stats() is None

    def test_get_cache_stats_present_when_enabled(self) -> None:
        """get_cache_stats returns a CacheStats instance when caching is on."""

        async def run() -> None:
            bundle = AsyncFluentBundle("en_US", cache=CacheConfig())
            await bundle.add_resource("msg = Hello!")
            await bundle.format_pattern("msg")
            stats = bundle.get_cache_stats()
            assert stats is not None

        asyncio.run(run())

    def test_clear_cache_noop_when_disabled(self) -> None:
        """clear_cache is a no-op when caching is not configured."""
        bundle = AsyncFluentBundle("en_US")
        bundle.clear_cache()  # must not raise

    def test_get_cache_audit_log_none_when_disabled(self) -> None:
        """get_cache_audit_log returns None when caching is disabled."""
        bundle = AsyncFluentBundle("en_US")
        assert bundle.get_cache_audit_log() is None


# ---------------------------------------------------------------------------
# for_system_locale classmethod
# ---------------------------------------------------------------------------


class TestForSystemLocale:
    """for_system_locale detects system locale from environment."""

    def test_for_system_locale_returns_async_bundle(self) -> None:
        """for_system_locale returns an AsyncFluentBundle instance."""
        with patch(
            "ftllexengine.runtime.async_bundle.get_system_locale",
            return_value="en_us",
        ):
            bundle = AsyncFluentBundle.for_system_locale()
        assert isinstance(bundle, AsyncFluentBundle)
        assert bundle.locale == "en_us"

    def test_for_system_locale_raises_on_no_locale(self) -> None:
        """for_system_locale raises RuntimeError when locale cannot be detected."""
        with (
            patch(
                "ftllexengine.runtime.async_bundle.get_system_locale",
                side_effect=RuntimeError("no locale"),
            ),
            pytest.raises(RuntimeError, match="no locale"),
        ):
            AsyncFluentBundle.for_system_locale()
