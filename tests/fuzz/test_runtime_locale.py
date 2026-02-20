"""Locale and localization fuzzing tests.

Property-based tests for locale-dependent functionality:
- Plural rule selection
- Number formatting
- Locale fallback chains
- Locale context handling

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.plural_rules import select_plural_category
from tests.strategies import ftl_financial_numbers

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# Known locales that Babel supports
COMMON_LOCALES = [
    "en-US",
    "en-GB",
    "de-DE",
    "de-AT",
    "fr-FR",
    "fr-CA",
    "es-ES",
    "es-MX",
    "it-IT",
    "pt-BR",
    "pt-PT",
    "nl-NL",
    "pl-PL",
    "ru-RU",
    "uk-UA",
    "ja-JP",
    "ko-KR",
    "zh-CN",
    "zh-TW",
    "ar-SA",
    "he-IL",
    "tr-TR",
    "lv-LV",
    "lt-LT",
    "et-EE",
]

# Plural categories per CLDR
PLURAL_CATEGORIES = ["zero", "one", "two", "few", "many", "other"]


# -----------------------------------------------------------------------------
# Property Tests: Plural Rules
# -----------------------------------------------------------------------------


class TestPluralRuleProperties:
    """Property tests for plural rule selection."""

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.integers(min_value=0, max_value=1000000),
    )
    @settings(max_examples=500, deadline=None)
    def test_plural_category_valid(self, locale: str, n: int) -> None:
        """Property: Plural category is always a valid CLDR category."""
        # Emit semantic events for HypoFuzz guidance
        lang = locale.split("-", maxsplit=1)[0]
        event(f"locale_lang={lang}")
        if n == 0:
            event("n=zero")
        elif n == 1:
            event("n=one")
        elif n == 2:
            event("n=two")
        elif n <= 10:
            event("n=small")
        elif n <= 100:
            event("n=medium")
        else:
            event("n=large")

        category = select_plural_category(n, locale)

        assert isinstance(category, str)
        assert category in PLURAL_CATEGORIES
        event(f"category={category}")

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300, deadline=None)
    def test_plural_category_float(self, locale: str, n: float) -> None:
        """Property: Plural category works for floats."""
        category = select_plural_category(n, locale)

        assert isinstance(category, str)
        assert category in PLURAL_CATEGORIES
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")
        event(f"category={category}")

    @given(st.sampled_from(COMMON_LOCALES))
    @settings(max_examples=50, deadline=None)
    def test_plural_edge_values(self, locale: str) -> None:
        """Property: Plural works for edge values (0, 1, 2)."""
        for n in [0, 1, 2]:
            category = select_plural_category(n, locale)
            assert category in PLURAL_CATEGORIES
            event(f"edge_{n}={category}")

    @given(st.integers(min_value=-1000, max_value=-1))
    @settings(max_examples=100, deadline=None)
    def test_plural_negative_numbers(self, n: int) -> None:
        """Property: Negative numbers don't crash plural rules."""
        # Negative numbers typically use absolute value for plural rules
        category = select_plural_category(n, "en-US")
        assert category in PLURAL_CATEGORIES
        event(f"category={category}")


class TestPluralIntegrationProperties:
    """Property tests for plural rules in message formatting."""

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=200, deadline=None)
    def test_plural_select_in_message(self, locale: str, count: int) -> None:
        """Property: Plural selection works in messages."""
        bundle = FluentBundle(locale)
        bundle.add_resource(
            """
items = { $count ->
    [zero] No items
    [one] One item
    [two] Two items
    [few] A few items
    [many] Many items
   *[other] { $count } items
}
"""
        )

        result, _ = bundle.format_pattern("items", {"count": count})

        assert isinstance(result, str)
        assert "item" in result.lower()
        # Should not have the raw selector
        assert "->" not in result
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")
        branch = "zero" if "No" in result else "one" if "One" in result else "other"
        event(f"plural_branch={branch}")


# -----------------------------------------------------------------------------
# Property Tests: Number Formatting
# -----------------------------------------------------------------------------


class TestNumberFormattingProperties:
    """Property tests for NUMBER function."""

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.integers(min_value=-1000000, max_value=1000000),
    )
    @settings(max_examples=300, deadline=None)
    def test_integer_formatting(self, locale: str, n: int) -> None:
        """Property: INTEGER formatting never crashes."""
        bundle = FluentBundle(locale)
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {"n": n})

        assert isinstance(result, str)
        # Result should contain digits
        assert any(c.isdigit() or c in "-,." for c in result)
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")
        event(f"sign={'negative' if n < 0 else 'zero' if n == 0 else 'positive'}")

    @given(
        st.sampled_from(COMMON_LOCALES),
        ftl_financial_numbers(),
    )
    @settings(max_examples=300, deadline=None)
    def test_financial_number_formatting(
        self, locale: str, n: int | float
    ) -> None:
        """Property: Financial numbers (ISO 4217 magnitudes) format correctly."""
        bundle = FluentBundle(locale)
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {"n": n})
        assert isinstance(result, str)
        assert any(c.isdigit() or c in "-,." for c in result)
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.floats(
            min_value=-1000000,
            max_value=1000000,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=300, deadline=None)
    def test_float_formatting(self, locale: str, n: float) -> None:
        """Property: FLOAT formatting never crashes."""
        bundle = FluentBundle(locale)
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {"n": n})

        assert isinstance(result, str)
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")

    @given(st.sampled_from(COMMON_LOCALES))
    @settings(max_examples=50, deadline=None)
    def test_large_number_formatting(self, locale: str) -> None:
        """Property: Very large numbers format without crash."""
        bundle = FluentBundle(locale)
        bundle.add_resource("num = { NUMBER($n) }")

        large_numbers = [
            1e10,
            1e15,
            1e20,
            -1e10,
            0.000001,
            0.0000001,
        ]

        for n in large_numbers:
            result, _ = bundle.format_pattern("num", {"n": n})
            assert isinstance(result, str)
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")


# -----------------------------------------------------------------------------
# Property Tests: Locale Context
# -----------------------------------------------------------------------------


class TestLocaleContextProperties:
    """Property tests for locale context handling."""

    @given(st.sampled_from(COMMON_LOCALES))
    @settings(max_examples=50, deadline=None)
    def test_bundle_creation_all_locales(self, locale: str) -> None:
        """Property: Bundle creation works for all common locales."""
        bundle = FluentBundle(locale)
        assert bundle._locale == locale
        event(f"locale={locale}")

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz-_", min_size=2, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_unknown_locale_handling(self, locale: str) -> None:
        """Property: Unknown locales don't crash, fall back gracefully."""
        # Filter to plausible locale-like strings
        assume("-" in locale or "_" in locale or len(locale) == 2)

        try:
            bundle = FluentBundle(locale)
            bundle.add_resource("msg = Hello")
            result, _ = bundle.format_pattern("msg")
            assert result == "Hello"
            event("outcome=locale_accepted")
        except ValueError:
            # Invalid locale format is acceptable
            event("outcome=locale_rejected")

    @given(st.sampled_from(COMMON_LOCALES), st.sampled_from(COMMON_LOCALES))
    @settings(max_examples=100, deadline=None)
    def test_locale_isolation(self, locale1: str, locale2: str) -> None:
        """Property: Different bundles maintain locale isolation."""
        bundle1 = FluentBundle(locale1)
        bundle2 = FluentBundle(locale2)

        bundle1.add_resource("msg = Bundle 1")
        bundle2.add_resource("msg = Bundle 2")

        result1, _ = bundle1.format_pattern("msg")
        result2, _ = bundle2.format_pattern("msg")

        assert result1 == "Bundle 1"
        assert result2 == "Bundle 2"
        event(f"same_locale={locale1 == locale2}")


# -----------------------------------------------------------------------------
# Property Tests: Locale Fallback
# -----------------------------------------------------------------------------


class TestLocaleFallbackProperties:
    """Property tests for locale fallback behavior."""

    @given(st.sampled_from(["en-US", "en-GB", "en-AU", "en-CA"]))
    @settings(max_examples=20, deadline=None)
    def test_english_variant_consistency(self, locale: str) -> None:
        """Property: English variants behave consistently for basic messages."""
        bundle = FluentBundle(locale)
        bundle.add_resource("greeting = Hello, world!")

        result, errors = bundle.format_pattern("greeting")

        assert result == "Hello, world!"
        assert errors == ()
        event(f"locale={locale}")

    @given(
        st.sampled_from(COMMON_LOCALES),
        st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=200, deadline=None)
    def test_plural_consistency_per_locale(self, locale: str, count: int) -> None:
        """Property: Same locale always gives same plural for same count."""
        # Get plural category twice
        cat1 = select_plural_category(count, locale)
        cat2 = select_plural_category(count, locale)

        assert cat1 == cat2
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")
        event(f"category={cat1}")

    def test_russian_plural_rules(self) -> None:
        """Russian has complex plural rules (one, few, many, other)."""
        bundle = FluentBundle("ru-RU", use_isolating=False)
        bundle.add_resource(
            """
items = { $count ->
    [one] { $count } товар
    [few] { $count } товара
    [many] { $count } товаров
   *[other] { $count } товаров
}
"""
        )

        # 1 = one, 2-4 = few, 5-20 = many, 21 = one, etc.
        test_cases = [
            (1, "1 товар"),
            (2, "2 товара"),
            (5, "5 товаров"),
            (21, "21 товар"),
        ]

        for count, expected in test_cases:
            result, _ = bundle.format_pattern("items", {"count": count})
            assert result == expected, f"count={count}: got {result!r}"

    def test_arabic_plural_rules(self) -> None:
        """Arabic has 6 plural forms."""
        category_zero = select_plural_category(0, "ar-SA")
        category_one = select_plural_category(1, "ar-SA")
        category_two = select_plural_category(2, "ar-SA")

        # Arabic should distinguish these
        assert category_zero == "zero"
        assert category_one == "one"
        assert category_two == "two"

    def test_latvian_plural_rules(self) -> None:
        """Latvian has special rules: zero for 0, 11-19, etc; one for 1, 21, 31, etc."""
        bundle = FluentBundle("lv-LV", use_isolating=False)
        bundle.add_resource(
            """
items = { $count ->
    [zero] Nav prieksmetu
    [one] { $count } prieksmets
   *[other] { $count } prieksmeti
}
"""
        )

        # CLDR Latvian rules: zero for n%10=0 or n%100=11..19, one for n%10=1 and n%100!=11
        cat_0 = select_plural_category(0, "lv-LV")
        cat_1 = select_plural_category(1, "lv-LV")
        cat_21 = select_plural_category(21, "lv-LV")
        cat_11 = select_plural_category(11, "lv-LV")

        assert cat_0 == "zero"
        assert cat_1 == "one"
        assert cat_21 == "one"
        assert cat_11 == "zero"  # 11 falls into zero category (n%100=11..19)
