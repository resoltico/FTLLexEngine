# mypy: ignore-errors
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from babel import Locale, UnknownLocaleError

from ftllexengine.runtime.locale_context import (
    _UNKNOWN_LOCALE_WARNING_LIMIT,
    LocaleContext,
)


class TestLocaleContextFallbackBehavior:
    """Regression coverage for fallback-locale resolution paths."""

    def test_create_accepts_babel_language_alias_locale(self) -> None:
        """Alias locales accepted by Babel remain valid."""
        LocaleContext.clear_cache()

        ctx = LocaleContext.create("iw")

        assert ctx.is_fallback is False
        assert ctx.babel_locale.language == "he"

    def test_create_or_raise_rejects_cached_fallback_locale(self) -> None:
        """Strict creation never reuses a fallback cache entry as valid."""
        LocaleContext.clear_cache()
        LocaleContext.create("xx-INVALID")

        with pytest.raises(ValueError, match="Unknown locale identifier 'xx_invalid'"):
            LocaleContext.create_or_raise("xx-INVALID")

    def test_create_unknown_locale_flood_suppresses_extra_warnings(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Repeated fallback locales emit bounded warnings."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            for i in range(_UNKNOWN_LOCALE_WARNING_LIMIT + 5):
                LocaleContext.create(f"xx-TEST{i:04d}")

        unknown_messages = [
            record.message
            for record in caplog.records
            if "Unknown locale" in record.message
        ]
        suppression_messages = [
            record.message
            for record in caplog.records
            if "suppressed after" in record.message
        ]

        assert len(unknown_messages) == _UNKNOWN_LOCALE_WARNING_LIMIT
        assert suppression_messages == [
            "Additional locale fallback warnings suppressed after "
            f"{_UNKNOWN_LOCALE_WARNING_LIMIT} events; most recent locale was "
            "'xx_test0008'."
        ]

    def test_create_skips_unknown_parse_for_impossible_language(self) -> None:
        """Impossible language tags fall back without parsing the unknown code."""
        LocaleContext.clear_cache()
        parse_calls: list[str] = []

        class FakeLocaleClass:
            @staticmethod
            def parse(code: str) -> Locale:
                parse_calls.append(code)
                return Locale.parse("en_US")

        with (
            patch(
                "ftllexengine.runtime.locale_resolution.get_locale_identifiers_func",
                return_value=lambda: ("en_US", "de_DE"),
            ),
            patch(
                "ftllexengine.runtime.locale_resolution.get_babel_global_func",
                return_value=lambda name: {"iw": "he"}
                if name == "language_aliases"
                else {},
            ),
            patch(
                "ftllexengine.runtime.locale_context.get_locale_class",
                return_value=FakeLocaleClass,
            ),
        ):
            ctx = LocaleContext.create("xx-TEST0000")

        assert ctx.is_fallback is True
        assert parse_calls == ["en_US"]

    def test_create_uses_unknown_locale_error_fallback_path(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Known-language unknown locales fall back through Babel's error path."""
        LocaleContext.clear_cache()

        class FakeLocaleClass:
            @staticmethod
            def parse(code: str) -> Locale:
                if code == "en_test":
                    raise UnknownLocaleError(code)
                return Locale.parse("en_US")

        with (
            patch(
                "ftllexengine.runtime.locale_context.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.runtime.locale_context.get_unknown_locale_error_class",
                return_value=UnknownLocaleError,
            ),
            patch(
                "ftllexengine.runtime.locale_context.is_definitely_unknown_locale",
                return_value=False,
            ),
            caplog.at_level(logging.WARNING),
        ):
            ctx = LocaleContext.create("en-TEST")

        assert ctx.is_fallback is True
        assert any("Unknown locale 'en_test'" in record.message for record in caplog.records)

    def test_create_or_raise_uses_unknown_locale_error_branch(self) -> None:
        """Strict creation raises when Babel rejects a known-language locale."""
        LocaleContext.clear_cache()

        class FakeLocaleClass:
            @staticmethod
            def parse(code: str) -> Locale:
                raise UnknownLocaleError(code)

        with (
            patch(
                "ftllexengine.runtime.locale_context.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.runtime.locale_context.get_unknown_locale_error_class",
                return_value=UnknownLocaleError,
            ),
            patch(
                "ftllexengine.runtime.locale_context.is_definitely_unknown_locale",
                return_value=False,
            ),
            pytest.raises(ValueError, match="Unknown locale identifier 'en_test'"),
        ):
            LocaleContext.create_or_raise("en-TEST")

    def test_create_or_raise_uses_invalid_locale_format_branch(self) -> None:
        """Strict creation surfaces Babel ValueError messages unchanged."""
        LocaleContext.clear_cache()

        class FakeLocaleClass:
            @staticmethod
            def parse(code: str) -> Locale:
                msg = f"synthetic parse failure for {code}"
                raise ValueError(msg)

        with (
            patch(
                "ftllexengine.runtime.locale_context.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.runtime.locale_context.is_definitely_unknown_locale",
                return_value=False,
            ),
            pytest.raises(
                ValueError,
                match="Invalid locale format 'en_test': synthetic parse failure for en_test",
            ),
        ):
            LocaleContext.create_or_raise("en-TEST")
