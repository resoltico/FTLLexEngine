# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

import logging
import sys
import threading
from typing import Any
from unittest.mock import patch

import pytest
from babel import Locale

import ftllexengine.core.babel_compat as _bc
from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Construction Guard Tests
# ============================================================================



class TestLocaleContextConstructionGuard:
    """Test __post_init__ validation prevents direct construction."""

    def test_direct_construction_without_token_raises(self) -> None:
        """Direct construction without factory token raises TypeError."""
        babel_locale = Locale.parse("en_US")

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "LocaleContext.create_or_raise()" in error_msg
        assert "direct construction" in error_msg

    def test_direct_construction_with_wrong_token_raises(self) -> None:
        """Direct construction with invalid token raises TypeError."""
        babel_locale = Locale.parse("en_US")
        wrong_token = object()

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=wrong_token,
            )

        assert "LocaleContext.create()" in str(exc_info.value)

    def test_direct_construction_with_none_token_raises(self) -> None:
        """Direct construction with None token raises TypeError."""
        babel_locale = Locale.parse("en_US")

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=None,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "direct construction" in error_msg

    def test_factory_methods_bypass_guard(self) -> None:
        """Factory methods bypass __post_init__ guard successfully."""
        ctx1 = LocaleContext.create("en-US")
        assert isinstance(ctx1, LocaleContext)

        ctx2 = LocaleContext.create_or_raise("de-DE")
        assert isinstance(ctx2, LocaleContext)

class TestLocaleContextCacheManagement:
    """Test LocaleContext cache operations."""

    def test_clear_cache_empties_cache(self) -> None:
        """clear_cache() empties the cache."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")
        assert LocaleContext.cache_size() > 0

        LocaleContext.clear_cache()
        assert LocaleContext.cache_size() == 0

    def test_cache_size_returns_count(self) -> None:
        """cache_size() returns number of cached instances."""
        LocaleContext.clear_cache()
        assert LocaleContext.cache_size() == 0

        LocaleContext.create("en-US")
        assert LocaleContext.cache_size() == 1

        LocaleContext.create("de-DE")
        assert LocaleContext.cache_size() == 2

    def test_cache_info_returns_dict(self) -> None:
        """cache_info() returns dictionary with expected keys."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")

        info = LocaleContext.cache_info()

        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info
        assert isinstance(info["locales"], tuple)
        assert info["size"] == 2

    def test_cache_info_after_clear(self) -> None:
        """cache_info() returns empty after clearing."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")

        LocaleContext.clear_cache()
        info = LocaleContext.cache_info()

        assert info["size"] == 0
        assert info["locales"] == ()

    def test_cache_returns_same_instance(self) -> None:
        """Cache returns the same instance for same locale."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("en-US")
        ctx2 = LocaleContext.create("en-US")

        assert ctx1 is ctx2

    def test_cache_double_check_pattern(self) -> None:
        """Cache double-check pattern returns existing instance."""
        from ftllexengine.core.locale_utils import (
            normalize_locale,
        )
        from ftllexengine.runtime.locale_context import (
            _FACTORY_TOKEN,
        )

        LocaleContext.clear_cache()

        cache_key = normalize_locale("en-RACE-TEST")
        pre_inserted_ctx = LocaleContext(
            locale_code="en-RACE-TEST",
            _babel_locale=Locale.parse("en_US"),
            _factory_token=_FACTORY_TOKEN,
        )

        original_parse = Locale.parse

        def parse_with_insertion(
            code: str, *args: Any, **kwargs: Any
        ) -> Locale:
            with LocaleContext._cache_lock:
                if cache_key not in LocaleContext._cache:
                    LocaleContext._cache[cache_key] = (
                        pre_inserted_ctx
                    )
            return original_parse(code, *args, **kwargs)

        with patch.object(
            Locale, "parse", side_effect=parse_with_insertion
        ):
            result = LocaleContext.create("en-RACE-TEST")

        assert result is pre_inserted_ctx

    def test_cache_thread_safety(self) -> None:
        """Cache is thread-safe under concurrent access."""
        LocaleContext.clear_cache()

        results: list[LocaleContext] = []

        def create_context() -> None:
            ctx = LocaleContext.create("en-US")
            results.append(ctx)

        thread1 = threading.Thread(target=create_context)
        thread2 = threading.Thread(target=create_context)

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        assert len(results) == 2
        assert results[0] is results[1]

    def test_cache_eviction_on_max_size(self) -> None:
        """Cache evicts LRU entry when max size reached."""
        LocaleContext.clear_cache()

        locales = ["en-US"] + [
            f"de-DE-x-variant{i}"
            for i in range(MAX_LOCALE_CACHE_SIZE)
        ]

        for locale in locales[:MAX_LOCALE_CACHE_SIZE]:
            LocaleContext.create(locale)

        assert (
            LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE
        )

        LocaleContext.create(locales[MAX_LOCALE_CACHE_SIZE])

        assert (
            LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE
        )

        info = LocaleContext.cache_info()
        locales_tuple = info["locales"]
        assert isinstance(locales_tuple, tuple)
        assert "en_US" not in locales_tuple

    def test_clear_cache_and_recreate(self) -> None:
        """Cache clearing and recreation works correctly."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("fr-FR")
        assert ctx1.locale_code == "fr_fr"

        ctx2 = LocaleContext.create("fr-FR")
        assert ctx1 is ctx2

        LocaleContext.clear_cache()
        ctx3 = LocaleContext.create("fr-FR")
        assert ctx1 is not ctx3

class TestLocaleContextCreate:
    """Test LocaleContext.create() factory with graceful fallback."""

    def test_create_valid_locale(self) -> None:
        """create() returns LocaleContext for valid locale."""
        ctx = LocaleContext.create("en-US")
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en_us"

    def test_create_unknown_locale_returns_context(self) -> None:
        """create() returns LocaleContext for unknown locale."""
        LocaleContext.clear_cache()
        result = LocaleContext.create("xx-UNKNOWN")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "xx_unknown"
        assert result.is_fallback is True

    def test_create_unknown_locale_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """create() logs warning for unknown locale."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            LocaleContext.create("xx_INVALID")

        assert any(
            "Unknown locale" in r.message
            or "xx_INVALID" in r.message
            for r in caplog.records
        )

    def test_create_invalid_format_raises(self) -> None:
        """create() rejects structurally invalid locale boundary values."""
        LocaleContext.clear_cache()

        with pytest.raises(ValueError, match=r"Invalid locale_code: '!!!INVALID@@@'"):
            LocaleContext.create("!!!INVALID@@@")

    def test_create_unknown_locale_uses_en_us(self) -> None:
        """create() uses en_US formatting for unknown locales."""
        ctx = LocaleContext.create("invalid-locale-xyz")
        locale = ctx.babel_locale

        assert locale.language == "en"

class TestLocaleContextCreateOrRaise:
    """Test create_or_raise() factory with strict validation."""

    def test_create_or_raise_valid_locale(self) -> None:
        """create_or_raise() returns LocaleContext for valid locale."""
        ctx = LocaleContext.create_or_raise("en-US")
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en_us"
        assert ctx.is_fallback is False

    def test_create_or_raise_unknown_locale_raises(self) -> None:
        """create_or_raise() raises ValueError for unknown locale."""
        with pytest.raises(
            ValueError, match=r"Unknown locale identifier"
        ):
            LocaleContext.create_or_raise("xx-INVALID")

    def test_create_or_raise_invalid_format_raises(self) -> None:
        """create_or_raise() raises ValueError for invalid format."""
        with pytest.raises(ValueError, match=r"Invalid locale_code: 'not a valid locale'"):
            LocaleContext.create_or_raise(
                "not a valid locale"
            )

    def test_create_or_raise_error_contains_locale_code(
        self,
    ) -> None:
        """create_or_raise() error message includes locale code."""
        test_locales = ["bad-locale", "xyz-123"]

        for locale_code in test_locales:
            with pytest.raises(
                ValueError, match="locale"
            ) as exc_info:
                LocaleContext.create_or_raise(locale_code)

            assert normalize_locale(locale_code) in str(exc_info.value)

class TestLocaleContextBabelImportErrors:
    """Test ImportError paths when Babel is not installed."""

    def test_create_raises_babel_import_error(self) -> None:
        """create() raises BabelImportError when Babel unavailable."""
        LocaleContext.clear_cache()

        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates_mod = sys.modules.pop("babel.dates", None)
        babel_nums = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import(
                    name: str,
                    globals_dict: (
                        dict[str, object] | None
                    ) = None,
                    locals_dict: (
                        dict[str, object] | None
                    ) = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        err = ModuleNotFoundError("No module named 'babel'")
                        err.name = "babel"
                        raise err
                    return original_import(
                        name,
                        globals_dict,
                        locals_dict,
                        fromlist,
                        level,
                    )

                with patch(
                    "builtins.__import__",
                    side_effect=mock_import,
                ):
                    with pytest.raises(
                        BabelImportError
                    ) as exc_info:
                        LocaleContext.create("en-US")

                    assert "LocaleContext.create" in str(
                        exc_info.value
                    )
        finally:
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates_mod is not None:
                sys.modules["babel.dates"] = babel_dates_mod
            if babel_nums is not None:
                sys.modules["babel.numbers"] = babel_nums
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None
            LocaleContext.clear_cache()

    def test_create_or_raise_raises_babel_import_error(
        self,
    ) -> None:
        """create_or_raise() raises BabelImportError."""
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates_mod = sys.modules.pop("babel.dates", None)
        babel_nums = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import(
                    name: str,
                    globals_dict: (
                        dict[str, object] | None
                    ) = None,
                    locals_dict: (
                        dict[str, object] | None
                    ) = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        err = ModuleNotFoundError("No module named 'babel'")
                        err.name = "babel"
                        raise err
                    return original_import(
                        name,
                        globals_dict,
                        locals_dict,
                        fromlist,
                        level,
                    )

                with patch(
                    "builtins.__import__",
                    side_effect=mock_import,
                ):
                    with pytest.raises(
                        BabelImportError
                    ) as exc_info:
                        LocaleContext.create_or_raise("en-US")

                    assert "create_or_raise" in str(
                        exc_info.value
                    )
        finally:
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates_mod is not None:
                sys.modules["babel.dates"] = babel_dates_mod
            if babel_nums is not None:
                sys.modules["babel.numbers"] = babel_nums
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None
