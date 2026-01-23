"""Performance benchmarks for FluentLocalization fallback chains.

Measures fallback chain traversal to detect multi-locale performance issues.

Python 3.13+.
"""

from __future__ import annotations

from typing import Any

import pytest

from ftllexengine import FluentLocalization


class TestLocalizationBenchmarks:
    """Benchmark FluentLocalization fallback performance."""

    @pytest.fixture
    def l10n_two_locales(self) -> FluentLocalization:
        """Create localization with two-locale fallback chain."""
        l10n = FluentLocalization(["lv", "en"])
        l10n.add_resource("lv", "home = Mājas")
        l10n.add_resource("en", "home = Home\nabout = About")
        return l10n

    @pytest.fixture
    def l10n_three_locales(self) -> FluentLocalization:
        """Create localization with three-locale fallback chain."""
        l10n = FluentLocalization(["lv", "en", "lt"])
        l10n.add_resource("lv", "home = Mājas")
        l10n.add_resource("en", "about = About")
        l10n.add_resource("lt", "contact = Kontaktai")
        return l10n

    def test_format_first_locale_no_fallback(
        self, benchmark: Any, l10n_two_locales: FluentLocalization
    ) -> None:
        """Benchmark formatting from first locale (no fallback)."""
        result, errors = benchmark(l10n_two_locales.format_value, "home")

        assert result == "Mājas"
        assert errors == ()

    def test_format_second_locale_fallback(
        self, benchmark: Any, l10n_two_locales: FluentLocalization
    ) -> None:
        """Benchmark formatting with fallback to second locale."""
        result, errors = benchmark(l10n_two_locales.format_value, "about")

        assert result == "About"
        assert errors == ()

    def test_format_three_locale_chain(
        self, benchmark: Any, l10n_three_locales: FluentLocalization
    ) -> None:
        """Benchmark formatting through three-locale fallback chain."""
        result, errors = benchmark(l10n_three_locales.format_value, "contact")

        assert result == "Kontaktai"
        assert errors == ()
