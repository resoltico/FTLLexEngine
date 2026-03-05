"""Property-based tests for LocaleContext with HypoFuzz event emission.

Comprehensive Hypothesis tests designed for coverage-guided fuzzing.
Emits semantic coverage events for HypoFuzz guidance.

Python 3.13+.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_FORMAT_DIGITS
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.locale_context import LocaleContext

# Locale samples for property testing
COMMON_LOCALES = [
    "en-US", "de-DE", "fr-FR", "es-ES", "ja-JP",
    "zh-CN", "ar-SA", "ru-RU", "it-IT", "pt-BR",
]

# Locales where ROUND_HALF_UP oracle comparison is feasible: all ASCII-digit
# locales. ar-SA uses Arabic-Indic digits (U+0660..U+0669) which cannot be
# compared against str(Decimal), so it is excluded from oracle parameterization.
ORACLE_LOCALES = [loc for loc in COMMON_LOCALES if loc != "ar-SA"]


def _oracle_extract_digits(result: str, locale: str) -> str | None:
    """Extract absolute numeric digits from a formatted string for oracle comparison.

    Uses Babel locale-specific decimal and grouping separators to normalize
    the formatted string to a plain ASCII digit sequence, enabling comparison
    against str(Decimal) oracle values across all ASCII-digit locales.

    Returns None when extraction is not possible (non-ASCII digits in result,
    ambiguous separators, or unknown locale).

    Normalization steps:
    1. Skip if any digit character is non-ASCII (e.g., ar-SA Arabic-Indic U+0660+).
    2. Look up decimal and group symbols via Babel.
    3. Remove group separators first — critical for de-DE where group sep is
       '.' (without this step, '1.234,56' → '1.234.56', two dots, wrong).
    4. Replace decimal separator with ASCII '.'.
    5. Strip all remaining non-digit, non-dot characters (currency codes,
       whitespace, signs). Whitespace-variant group separators (fr-FR
       thin-space, lv-LV narrow no-break space) are handled by this step.
    """
    if any(c.isdigit() and not c.isascii() for c in result):
        return None
    try:
        from babel.numbers import get_decimal_symbol, get_group_symbol  # noqa: PLC0415
        # Babel expects underscore-separated locale IDs ('en_US', 'de_DE');
        # ftllexengine uses BCP 47 hyphen-separated codes ('en-US', 'de-DE').
        babel_locale = locale.replace("-", "_")
        decimal_sym = get_decimal_symbol(babel_locale)
        group_sym = get_group_symbol(babel_locale)
    except ValueError:
        return None
    if decimal_sym == group_sym:
        return None
    normalized = result.replace(group_sym, "").replace(decimal_sym, ".")
    digits = re.sub(r"[^\d.]", "", normalized)
    return digits if digits else None


class TestLocaleContextCreateProperties:
    """Property-based tests for LocaleContext.create() robustness."""

    @given(
        locale_code=st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs"],
                blacklist_characters="\x00",
            ),
            min_size=0,
            max_size=100,
        ),
    )
    @example(locale_code="")
    @example(locale_code="en-US")
    @example(locale_code="not-a-locale!!!")
    def test_create_never_crashes(self, locale_code: str) -> None:
        """create() never raises an unhandled exception (property: robustness).

        Property: For all strings S, create(S) returns a LocaleContext
        instance (with en_US fallback for invalid locales).

        Events emitted:
        - outcome={result}: Whether locale was valid or fell back
        - input_length={range}: Length category of input
        """
        result = LocaleContext.create(locale_code)

        assert isinstance(result, LocaleContext)
        if result.is_fallback:
            event("outcome=fallback")
        else:
            event("outcome=exact_match")

        length = len(locale_code)
        if length == 0:
            event("input_length=empty")
        elif length <= 5:
            event("input_length=short")
        elif length <= 20:
            event("input_length=medium")
        else:
            event("input_length=long")


class TestLocaleContextCacheProperties:
    """Property-based tests for cache behavior."""

    @given(
        locale=st.sampled_from(
            [*COMMON_LOCALES, "lv-LV", "ko-KR", "nl-NL"]
        )
    )
    @example(locale="en-US")
    @example(locale="de-DE")
    def test_cache_identity_property(self, locale: str) -> None:
        """Cache returns same instance for same locale (property: identity).

        Property: For all locales L, create(L) is create(L).

        Events emitted:
        - locale={locale_category}: Locale category for diversity
        """
        if locale.startswith("en"):
            event("locale=english")
        elif locale.startswith("de"):
            event("locale=german")
        elif locale.startswith("ja"):
            event("locale=japanese")
        elif locale.startswith("ar"):
            event("locale=arabic")
        else:
            event("locale=other")

        ctx1 = LocaleContext.create(locale)
        ctx2 = LocaleContext.create(locale)

        assert ctx1 is ctx2

    @given(
        count=st.integers(min_value=1, max_value=10)
    )
    @example(count=1)
    @example(count=5)
    def test_cache_size_monotonic_property(self, count: int) -> None:
        """Cache size increases monotonically until max (property: monotonicity).

        Property: cache_size() <= previous cache_size() + new unique locales.

        Events emitted:
        - cache_count={range}: Number of locales created
        """
        LocaleContext.clear_cache()

        if count <= 2:
            event("cache_count=low")
        elif count <= 5:
            event("cache_count=medium")
        else:
            event("cache_count=high")

        initial_size = LocaleContext.cache_size()
        assert initial_size == 0

        for i in range(count):
            LocaleContext.create(
                COMMON_LOCALES[i % len(COMMON_LOCALES)]
            )

        final_size = LocaleContext.cache_size()
        assert 0 < final_size <= count


class TestFormatNumberProperties:
    """Property-based tests for number formatting."""

    @given(
        value=st.one_of(
            st.integers(
                min_value=-1_000_000_000,
                max_value=1_000_000_000,
            ),
            st.decimals(
                min_value=Decimal("-1000000000"),
                max_value=Decimal("1000000000"),
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        locale=st.sampled_from(COMMON_LOCALES),
    )
    @example(value=0, locale="en-US")
    @example(value=Decimal("1234.5"), locale="de-DE")
    @example(value=Decimal("999.99"), locale="fr-FR")
    def test_format_number_type_safety(
        self, value: int | Decimal, locale: str
    ) -> None:
        """format_number() always returns non-empty string (property: type safety).

        Property: For all numbers n and locales L,
        format_number(n) returns a non-empty string.

        Events emitted:
        - value_type={type}: Input value type
        - value_sign={sign}: Sign of value
        - locale={category}: Locale category
        """
        if isinstance(value, int):
            event("value_type=int")
        else:
            event("value_type=Decimal")

        if value == 0:
            event("value_sign=zero")
        elif value > 0:
            event("value_sign=positive")
        else:
            event("value_sign=negative")

        if "US" in locale or "GB" in locale:
            event("locale=english")
        elif "DE" in locale:
            event("locale=german")
        elif "JP" in locale:
            event("locale=japanese")
        else:
            event("locale=other")

        ctx = LocaleContext.create(locale)
        result = ctx.format_number(value)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        value=st.one_of(
            st.decimals(
                min_value=Decimal("-1e10"),
                max_value=Decimal("1e10"),
                allow_nan=False,
                allow_infinity=False,
            ),
            st.just(Decimal("Infinity")),
            st.just(Decimal("-Infinity")),
            st.just(Decimal("NaN")),
        )
    )
    @example(value=Decimal("Infinity"))
    @example(value=Decimal("-Infinity"))
    @example(value=Decimal("NaN"))
    def test_format_number_special_values_property(
        self, value: Decimal
    ) -> None:
        """format_number() handles special Decimal values (property: robustness).

        Property: For all special values v in {Infinity, -Infinity, NaN, normal},
        format_number(v) returns non-empty string without exception.

        Events emitted:
        - special_value={type}: Special value type
        """
        if value.is_nan():
            event("special_value=nan")
        elif value.is_infinite():
            if value > 0:
                event("special_value=positive_infinity")
            else:
                event("special_value=negative_infinity")
        else:
            event("special_value=normal")

        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(value)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        minimum=st.integers(min_value=0, max_value=10),
        maximum=st.integers(min_value=0, max_value=10),
    )
    @example(minimum=0, maximum=0)
    @example(minimum=2, maximum=2)
    @example(minimum=0, maximum=3)
    def test_format_number_fraction_digits_valid_range(
        self, minimum: int, maximum: int
    ) -> None:
        """format_number() respects fraction digit constraints (property: validity).

        Property: When 0 <= minimum <= maximum <= 10, formatting succeeds.

        Events emitted:
        - fraction_relation={relation}: Relationship between min/max
        - decimal_count={range}: Decimal place count
        """
        if minimum > maximum:
            event("fraction_relation=invalid")
            return  # Skip invalid combinations
        if minimum == maximum:
            event("fraction_relation=fixed")
        else:
            event("fraction_relation=variable")

        if maximum == 0:
            event("decimal_count=none")
        elif maximum <= 2:
            event("decimal_count=low")
        elif maximum <= 5:
            event("decimal_count=medium")
        else:
            event("decimal_count=high")

        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            Decimal("123.456789"),
            minimum_fraction_digits=minimum,
            maximum_fraction_digits=maximum,
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        minimum=st.integers(max_value=-1),
    )
    @example(minimum=-1)
    @example(minimum=-100)
    def test_format_number_negative_minimum_raises(
        self, minimum: int
    ) -> None:
        """format_number() raises for negative minimum_fraction_digits.

        Property: For all n < 0,
        format_number(..., minimum_fraction_digits=n) raises ValueError.

        Events emitted:
        - error=ValueError_minimum_negative: Error path
        """
        event("error=ValueError_minimum_negative")

        ctx = LocaleContext.create("en-US")

        with pytest.raises(
            ValueError, match=r"minimum_fraction_digits"
        ):
            ctx.format_number(
                Decimal("123.45"), minimum_fraction_digits=minimum
            )

    @given(
        maximum=st.integers(max_value=-1),
    )
    @example(maximum=-1)
    @example(maximum=-50)
    def test_format_number_negative_maximum_raises(
        self, maximum: int
    ) -> None:
        """format_number() raises for negative maximum_fraction_digits.

        Property: For all n < 0,
        format_number(..., maximum_fraction_digits=n) raises ValueError.

        Events emitted:
        - error=ValueError_maximum_negative: Error path
        """
        event("error=ValueError_maximum_negative")

        ctx = LocaleContext.create("en-US")

        with pytest.raises(
            ValueError, match=r"maximum_fraction_digits"
        ):
            ctx.format_number(
                Decimal("123.45"), maximum_fraction_digits=maximum
            )

    @given(
        value=st.integers(
            min_value=MAX_FORMAT_DIGITS + 1,
            max_value=MAX_FORMAT_DIGITS + 1000,
        ),
    )
    @example(value=MAX_FORMAT_DIGITS + 1)
    @example(value=MAX_FORMAT_DIGITS + 500)
    def test_minimum_fraction_digits_exceeds_max_property(
        self, value: int
    ) -> None:
        """format_number() raises when minimum_fraction_digits > MAX_FORMAT_DIGITS.

        Property: For all n > MAX_FORMAT_DIGITS,
        format_number(..., minimum_fraction_digits=n) raises ValueError.

        Events emitted:
        - error=ValueError_minimum_exceeds_max: Error path
        - boundary={range}: How far above the limit
        """
        event("error=ValueError_minimum_exceeds_max")

        overshoot = value - MAX_FORMAT_DIGITS
        if overshoot <= 10:
            event("boundary=near")
        elif overshoot <= 100:
            event("boundary=moderate")
        else:
            event("boundary=far")

        ctx = LocaleContext.create("en-US")

        with pytest.raises(
            ValueError, match=r"minimum_fraction_digits"
        ):
            ctx.format_number(
                Decimal("42"), minimum_fraction_digits=value
            )

    @given(
        value=st.integers(
            min_value=MAX_FORMAT_DIGITS + 1,
            max_value=MAX_FORMAT_DIGITS + 1000,
        ),
    )
    @example(value=MAX_FORMAT_DIGITS + 1)
    @example(value=MAX_FORMAT_DIGITS + 500)
    def test_maximum_fraction_digits_exceeds_max_property(
        self, value: int
    ) -> None:
        """format_number() raises when maximum_fraction_digits > MAX_FORMAT_DIGITS.

        Property: For all n > MAX_FORMAT_DIGITS,
        format_number(..., maximum_fraction_digits=n) raises ValueError.

        Events emitted:
        - error=ValueError_maximum_exceeds_max: Error path
        - boundary={range}: How far above the limit
        """
        event("error=ValueError_maximum_exceeds_max")

        overshoot = value - MAX_FORMAT_DIGITS
        if overshoot <= 10:
            event("boundary=near")
        elif overshoot <= 100:
            event("boundary=moderate")
        else:
            event("boundary=far")

        ctx = LocaleContext.create("en-US")

        with pytest.raises(
            ValueError, match=r"maximum_fraction_digits"
        ):
            ctx.format_number(
                Decimal("42"), maximum_fraction_digits=value
            )


class TestFormatNumberRoundHalfUp:
    """Oracle-based property tests verifying ROUND_HALF_UP rounding semantics.

    These tests compare format_number() output against a manually-computed
    expected value (the oracle) to catch Babel rounding mode regressions.
    The oracle: quantize to exact display precision with ROUND_HALF_UP, then
    extract the numeric portion and compare.

    Why these tests are necessary:
    - Babel's format_decimal() uses ROUND_HALF_EVEN (banker's rounding) by default.
    - Midpoint values (exactly halfway between two representable values) differ
      between ROUND_HALF_UP and ROUND_HALF_EVEN: Decimal("1.225") with max=2
      rounds to "1.22" (HALF_EVEN) vs "1.23" (HALF_UP).
    - Structural invariant tests (output is a string) cannot detect this.
    - Only oracle tests that compute the expected rounded value catch the bug.
    """

    @given(
        # Generate "midpoint" decimals: values whose last relevant digit is 5,
        # which is where ROUND_HALF_UP and ROUND_HALF_EVEN diverge.
        integer_part=st.integers(min_value=0, max_value=9999),
        decimal_digits=st.integers(min_value=0, max_value=99),
        precision=st.integers(min_value=1, max_value=4),
        locale=st.sampled_from(ORACLE_LOCALES),
    )
    @example(integer_part=1, decimal_digits=225, precision=2, locale="en-US")
    @example(integer_part=1, decimal_digits=235, precision=2, locale="en-US")
    @example(integer_part=0, decimal_digits=5, precision=0, locale="en-US")
    @example(integer_part=9, decimal_digits=995, precision=2, locale="en-US")
    @example(integer_part=1, decimal_digits=225, precision=2, locale="de-DE")
    @example(integer_part=9, decimal_digits=995, precision=2, locale="fr-FR")
    def test_format_number_round_half_up_oracle(
        self,
        integer_part: int,
        decimal_digits: int,
        precision: int,
        locale: str,
    ) -> None:
        """format_number() uses ROUND_HALF_UP for all midpoint values across locales.

        Oracle: Manually quantize with ROUND_HALF_UP and verify the formatted
        output reflects the correctly-rounded value, not ROUND_HALF_EVEN.
        Covers all ASCII-digit locales in ORACLE_LOCALES; _oracle_extract_digits
        handles locale-specific decimal and group separators.

        Events emitted:
        - outcome=midpoint: Value is an exact midpoint for the precision
        - outcome=non_midpoint: Value is not a midpoint
        - precision={n}: Decimal places in the precision
        - locale={code}: Locale under test
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415 - test-local import

        # Construct value as "integer_part.decimal_digits" at the given digit count
        # Normalize decimal_digits to at most (precision + 1) significant digits
        digit_count = precision + 1
        decimal_str = str(decimal_digits).zfill(digit_count)[:digit_count]
        raw = Decimal(f"{integer_part}.{decimal_str}")

        event(f"precision={precision}")
        event(f"locale={locale}")

        # Determine if this is a midpoint: last digit at display precision is 5
        quantizer = Decimal(10) ** -precision
        # The digit at position (precision + 1) determines rounding
        # Midpoint means the digit immediately past the display precision is 5
        scale_str = str(decimal_digits).zfill(digit_count)
        is_midpoint = len(scale_str) > precision and scale_str[precision] == "5"
        if is_midpoint:
            event("outcome=midpoint")
        else:
            event("outcome=non_midpoint")

        # Oracle: expected rounded value via explicit ROUND_HALF_UP
        expected_value = raw.quantize(quantizer, rounding=ROUND_HALF_UP)

        ctx = LocaleContext.create(locale)
        result = ctx.format_number(
            raw,
            minimum_fraction_digits=precision,
            maximum_fraction_digits=precision,
        )

        # Extract numeric portion via locale-aware separator normalization.
        # result.replace(",", "") would corrupt de-DE output: "1,23" → "123"
        # (comma is the decimal separator in de-DE, not the group separator).
        normalized_result = _oracle_extract_digits(result, locale)
        assert normalized_result is not None, (
            f"Oracle digit extraction failed for locale={locale}, result={result!r}"
        )
        assert normalized_result == str(expected_value), (
            f"ROUND_HALF_UP oracle failed for {raw} (locale={locale}): "
            f"expected {expected_value}, got {result!r}"
        )

    @given(
        # Test that custom patterns also use ROUND_HALF_UP
        integer_part=st.integers(min_value=0, max_value=999),
        decimal_digits=st.integers(min_value=0, max_value=99),
        locale=st.sampled_from(ORACLE_LOCALES),
    )
    @example(integer_part=1, decimal_digits=25, locale="en-US")
    @example(integer_part=0, decimal_digits=15, locale="en-US")
    @example(integer_part=99, decimal_digits=95, locale="en-US")
    @example(integer_part=1, decimal_digits=25, locale="de-DE")
    @example(integer_part=99, decimal_digits=95, locale="fr-FR")
    def test_format_number_custom_pattern_round_half_up_oracle(
        self,
        integer_part: int,
        decimal_digits: int,
        locale: str,
    ) -> None:
        """Custom pattern path also uses ROUND_HALF_UP across locales.

        Before v0.145.0, the custom pattern fast-path in format_number bypassed
        ROUND_HALF_UP quantization. This oracle test would have caught that bug.
        Covers all ASCII-digit locales in ORACLE_LOCALES.

        Events emitted:
        - outcome=midpoint: Value is an exact midpoint for 2 decimal places
        - outcome=non_midpoint: Value is not a midpoint
        - locale={code}: Locale under test
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415 - test-local import

        decimal_str = str(decimal_digits).zfill(3)[:3]
        raw = Decimal(f"{integer_part}.{decimal_str}")

        event(f"locale={locale}")
        is_midpoint = len(decimal_str) >= 3 and decimal_str[2] == "5"
        if is_midpoint:
            event("outcome=midpoint")
        else:
            event("outcome=non_midpoint")

        # Oracle: expected value via explicit ROUND_HALF_UP to 2 places
        expected_value = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        ctx = LocaleContext.create(locale)
        result = ctx.format_number(raw, pattern="#,##0.00")

        # Locale-aware extraction: result.replace(",", "") would corrupt de-DE
        # output ("1,23" → "123") since comma is the decimal separator there.
        normalized_result = _oracle_extract_digits(result, locale)
        assert normalized_result is not None, (
            f"Oracle digit extraction failed for locale={locale}, result={result!r}"
        )
        assert normalized_result == str(expected_value), (
            f"Custom pattern ROUND_HALF_UP oracle failed for {raw} (locale={locale}): "
            f"expected {expected_value}, got {result!r}"
        )

    @given(
        min_d=st.integers(min_value=0, max_value=6),
        max_d=st.integers(min_value=0, max_value=6),
        integer_part=st.integers(min_value=0, max_value=99),
    )
    @example(min_d=4, max_d=3, integer_part=1)
    @example(min_d=3, max_d=2, integer_part=5)
    @example(min_d=0, max_d=0, integer_part=10)
    def test_format_number_min_max_clamping_never_truncates(
        self,
        min_d: int,
        max_d: int,
        integer_part: int,
    ) -> None:
        """When min > max, output has at least min decimal places (clamping, not error).

        Pre-v0.145.0: min=3, max=2 would quantize to 2 places but format with
        3 required digits, producing "1.230" — wrong and incoherent.
        Post-v0.145.0: max is clamped to max(min, max), output is consistent.

        Events emitted:
        - relation=min_gt_max: min > max (clamping applies)
        - relation=min_le_max: min <= max (normal path)
        """

        event(f"relation={'min_gt_max' if min_d > max_d else 'min_le_max'}")

        effective_max = max(min_d, max_d)
        # Use a value that has many decimal places
        value = Decimal(f"{integer_part}.123456789")
        effective_min = max(min_d, max_d) if min_d > 0 else min_d

        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            value,
            minimum_fraction_digits=min_d,
            maximum_fraction_digits=max_d,
        )

        # Decimal count in result must be at least effective min places
        decimal_places_in_result = (
            len(result.split(".")[-1]) if "." in result else 0
        )
        assert decimal_places_in_result >= min(min_d, effective_min), (
            f"min/max clamping: result {result!r} has {decimal_places_in_result} "
            f"decimal places, expected >= {min_d} (min_d={min_d}, max_d={max_d})"
        )
        # And result must never exceed effective max places
        assert decimal_places_in_result <= effective_max, (
            f"min/max clamping: result {result!r} has {decimal_places_in_result} "
            f"decimal places, expected <= {effective_max} (min_d={min_d}, max_d={max_d})"
        )


class TestFormatCurrencyRoundHalfUp:
    """Oracle-based property tests verifying ROUND_HALF_UP for currency formatting.

    Before v0.145.0, format_currency() used Babel's default ROUND_HALF_EVEN,
    causing midpoint values to round incorrectly. These oracle tests compare
    against manually-computed ROUND_HALF_UP results.
    """

    @given(
        integer_part=st.integers(min_value=0, max_value=9999),
        decimal_digits=st.integers(min_value=0, max_value=99),
        currency=st.sampled_from(["USD", "EUR", "GBP", "AUD", "CAD"]),
        locale=st.sampled_from(ORACLE_LOCALES),
    )
    @example(integer_part=123, decimal_digits=44, currency="USD", locale="en-US")
    @example(integer_part=123, decimal_digits=45, currency="USD", locale="en-US")
    @example(integer_part=0, decimal_digits=5, currency="EUR", locale="en-US")
    @example(integer_part=999, decimal_digits=99, currency="GBP", locale="en-US")
    @example(integer_part=0, decimal_digits=0, currency="AUD", locale="en-US")
    @example(integer_part=123, decimal_digits=45, currency="USD", locale="de-DE")
    @example(integer_part=0, decimal_digits=5, currency="EUR", locale="fr-FR")
    def test_format_currency_round_half_up_oracle(
        self,
        integer_part: int,
        decimal_digits: int,
        currency: str,
        locale: str,
    ) -> None:
        """format_currency() uses ROUND_HALF_UP for midpoint values across locales.

        Oracle: Pre-quantize with ROUND_HALF_UP to CLDR currency precision,
        compare against the formatted output's numeric component using
        locale-aware separator normalization. Covers all ASCII-digit locales
        in ORACLE_LOCALES.

        Events emitted:
        - currency={code}: Currency being tested
        - outcome=midpoint: Value is a midpoint at currency precision
        - outcome=non_midpoint: Value is not a midpoint
        - locale={code}: Locale under test
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415 - test-local import

        from babel.numbers import get_currency_precision  # noqa: PLC0415 - Babel optional

        event(f"currency={currency}")
        event(f"locale={locale}")

        prec = get_currency_precision(currency)
        digit_count = prec + 1
        decimal_str = str(decimal_digits).zfill(digit_count)[:digit_count]
        raw = Decimal(f"{integer_part}.{decimal_str}")

        # Determine midpoint: the first truncated digit is 5
        is_midpoint = len(decimal_str) > prec and decimal_str[prec] == "5"
        if is_midpoint:
            event("outcome=midpoint")
        else:
            event("outcome=non_midpoint")

        quantizer = Decimal(10) ** -prec
        expected_value = raw.quantize(quantizer, rounding=ROUND_HALF_UP)

        ctx = LocaleContext.create(locale)
        result = ctx.format_currency(raw, currency=currency)

        # Locale-aware extraction: re.sub(r"[^\d.]", "", result) would corrupt
        # de-DE output ("1,23 USD" → "123") since comma is the decimal separator.
        digits_only = _oracle_extract_digits(result, locale)
        assert digits_only is not None, (
            f"Oracle digit extraction failed for locale={locale}, result={result!r}"
        )
        assert digits_only == str(expected_value), (
            f"ROUND_HALF_UP oracle failed for {raw} {currency} (locale={locale}): "
            f"expected {expected_value}, got {result!r}"
        )

    @given(
        integer_part=st.integers(min_value=0, max_value=9999),
        decimal_digits=st.integers(min_value=0, max_value=99),
        currency=st.sampled_from(["USD", "EUR", "GBP"]),
        locale=st.sampled_from(ORACLE_LOCALES),
    )
    @example(integer_part=100, decimal_digits=50, currency="USD", locale="en-US")
    @example(integer_part=0, decimal_digits=5, currency="EUR", locale="en-US")
    @example(integer_part=100, decimal_digits=50, currency="USD", locale="de-DE")
    @example(integer_part=0, decimal_digits=5, currency="EUR", locale="fr-FR")
    def test_format_currency_custom_pattern_round_half_up_oracle(
        self,
        integer_part: int,
        decimal_digits: int,
        currency: str,
        locale: str,
    ) -> None:
        """Custom pattern currency also uses ROUND_HALF_UP across locales.

        Covers all ASCII-digit locales in ORACLE_LOCALES.

        Events emitted:
        - currency={code}: Currency being tested
        - outcome=midpoint: Value is a midpoint at 2 decimal places
        - outcome=non_midpoint: Not a midpoint
        - locale={code}: Locale under test
        """
        from decimal import ROUND_HALF_UP  # noqa: PLC0415 - test-local import

        event(f"currency={currency}")
        event(f"locale={locale}")

        decimal_str = str(decimal_digits).zfill(3)[:3]
        raw = Decimal(f"{integer_part}.{decimal_str}")

        is_midpoint = len(decimal_str) >= 3 and decimal_str[2] == "5"
        if is_midpoint:
            event("outcome=midpoint")
        else:
            event("outcome=non_midpoint")

        expected_value = raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        ctx = LocaleContext.create(locale)
        result = ctx.format_currency(raw, currency=currency, pattern="#,##0.00 ¤")

        # Locale-aware extraction: re.sub(r"[^\d.]", "", result) would corrupt
        # de-DE output ("1,23 USD" → "123") since comma is the decimal separator.
        digits_only = _oracle_extract_digits(result, locale)
        assert digits_only is not None, (
            f"Oracle digit extraction failed for locale={locale}, result={result!r}"
        )
        assert digits_only == str(expected_value), (
            f"Custom pattern ROUND_HALF_UP oracle failed for {raw} {currency} (locale={locale}): "
            f"expected {expected_value}, got {result!r}"
        )


class TestFormatDatetimeProperties:
    """Property-based tests for datetime formatting."""

    @given(
        year=st.integers(min_value=1900, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        locale=st.sampled_from(COMMON_LOCALES),
        date_style=st.sampled_from(
            ["short", "medium", "long", "full"]
        ),
    )
    @example(
        year=2025, month=10, day=27,
        locale="en-US", date_style="short",
    )
    @example(
        year=2000, month=1, day=1,
        locale="ja-JP", date_style="full",
    )
    def test_format_datetime_type_safety(
        self,
        year: int,
        month: int,
        day: int,
        locale: str,
        date_style: str,
    ) -> None:
        """format_datetime() always returns non-empty string (property: type safety).

        Property: For all valid dates D, locales L, and styles S,
        format_datetime(D, style=S) returns non-empty string.

        Events emitted:
        - date_style={style}: Style parameter
        - locale={category}: Locale category
        """
        event(f"date_style={date_style}")

        if "US" in locale:
            event("locale=us")
        elif "DE" in locale:
            event("locale=german")
        elif "JP" in locale:
            event("locale=japanese")
        elif "CN" in locale:
            event("locale=chinese")
        else:
            event("locale=other")

        dt = datetime(year, month, day, tzinfo=UTC)
        ctx = LocaleContext.create(locale)

        result = ctx.format_datetime(
            dt, date_style=date_style  # type: ignore[arg-type]
        )

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        invalid_string=st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs"]
            ),
            min_size=1,
            max_size=50,
        ).filter(lambda s: not _is_valid_iso_date(s))
    )
    @example(invalid_string="not-a-date")
    @example(invalid_string="2025-13-45")
    def test_format_datetime_invalid_string_raises(
        self, invalid_string: str
    ) -> None:
        """format_datetime() raises for invalid ISO strings (property: validation).

        Property: For all invalid ISO strings S,
        format_datetime(S) raises FrozenFluentError with FORMATTING category.

        Events emitted:
        - error=FrozenFluentError_invalid_datetime: Error path
        """
        event("error=FrozenFluentError_invalid_datetime")

        ctx = LocaleContext.create("en-US")

        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_datetime(invalid_string)

        assert exc_info.value.category == ErrorCategory.FORMATTING


class TestFormatCurrencyProperties:
    """Property-based tests for currency formatting."""

    @given(
        value=st.one_of(
            st.integers(min_value=0, max_value=1_000_000),
            st.decimals(
                min_value=Decimal("0"),
                max_value=Decimal("1000000"),
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        currency=st.sampled_from(
            ["USD", "EUR", "GBP", "JPY", "CNY"]
        ),
        locale=st.sampled_from(COMMON_LOCALES[:5]),
    )
    @example(value=0, currency="USD", locale="en-US")
    @example(value=Decimal("123.45"), currency="EUR", locale="de-DE")
    @example(
        value=Decimal("999.99"),
        currency="JPY", locale="ja-JP",
    )
    def test_format_currency_type_safety(
        self,
        value: int | Decimal,
        currency: str,
        locale: str,
    ) -> None:
        """format_currency() always returns non-empty string (property: type safety).

        Property: For all amounts A, currencies C, and locales L,
        format_currency(A, currency=C) returns non-empty string.

        Events emitted:
        - value_type={type}: Input value type
        - currency={code}: Currency code
        - locale={category}: Locale category
        """
        if isinstance(value, int):
            event("value_type=int")
        else:
            event("value_type=Decimal")

        event(f"currency={currency}")

        if "US" in locale:
            event("locale=us")
        elif "DE" in locale:
            event("locale=german")
        elif "JP" in locale:
            event("locale=japanese")
        else:
            event("locale=other")

        ctx = LocaleContext.create(locale)
        result = ctx.format_currency(value, currency=currency)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        display=st.sampled_from(["symbol", "code", "name"]),
    )
    @example(display="symbol")
    @example(display="code")
    @example(display="name")
    def test_format_currency_display_modes(
        self, display: str
    ) -> None:
        """format_currency() supports all display modes (property: completeness).

        Property: For all display modes D in {symbol, code, name},
        format_currency(..., currency_display=D) succeeds.

        Events emitted:
        - currency_display={mode}: Display mode
        """
        event(f"currency_display={display}")

        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("100.00"),
            currency="USD",
            currency_display=display,  # type: ignore[arg-type]
        )

        assert isinstance(result, str)
        assert len(result) > 0


def _is_valid_iso_date(s: str) -> bool:
    """Check if string is valid ISO 8601 date format."""
    try:
        datetime.fromisoformat(s)
        return True
    except (ValueError, TypeError):
        return False
