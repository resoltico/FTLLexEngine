"""Hypothesis strategies for currency parsing property-based testing.

Provides strategies for generating locale-formatted currency strings,
ambiguous/unambiguous symbol inputs, and edge-case currency values
for property-based testing of ftllexengine.parsing.currency.

Usage:
    from tests.strategies.currency import currency_inputs, ambiguous_currency_inputs

Event-Emitting Strategies (HypoFuzz-Optimized):
    - currency_inputs: Generates (value_str, locale, expected_code) tuples
    - ambiguous_currency_inputs: Generates ambiguous symbol scenarios
    - currency_amount_strings: Generates amount strings with currency symbols

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import composite

if TYPE_CHECKING:
    pass

# Unambiguous symbols that always resolve to one currency
_UNAMBIGUOUS_SYMBOLS: dict[str, str] = {
    "\u20ac": "EUR",
    "\u20b9": "INR",
    "\u20a9": "KRW",
    "\u20ab": "VND",
    "\u20ba": "TRY",
    "\u20bd": "RUB",
    "\u20aa": "ILS",
    "\u20b4": "UAH",
    "\u20a6": "NGN",
    "\u20b5": "GHS",
}

# Ambiguous symbols requiring locale or default_currency
_AMBIGUOUS_SYMBOLS: list[str] = [
    "$", "kr", "\u00a5", "\u00a3", "R", "R$", "S/",
]

# Locale -> expected currency for locale inference tests
_LOCALE_CURRENCY_PAIRS: list[tuple[str, str]] = [
    ("en_US", "USD"),
    ("en_CA", "CAD"),
    ("en_AU", "AUD"),
    ("en_GB", "GBP"),
    ("de_DE", "EUR"),
    ("ja_JP", "JPY"),
    ("zh_CN", "CNY"),
    ("es_MX", "MXN"),
    ("pt_BR", "BRL"),
    ("sv_SE", "SEK"),
    ("ko_KR", "KRW"),
    ("hi_IN", "INR"),
    ("lv_LV", "EUR"),
]

# ISO codes for direct code-based parsing
_COMMON_ISO_CODES: list[str] = [
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD",
    "INR", "BRL", "MXN", "SEK", "NOK", "DKK", "PLN", "CZK",
]

# Locales with distinct number formatting
_FORMATTING_LOCALES: list[str] = [
    "en_US", "de_DE", "fr_FR", "lv_LV", "ja_JP", "zh_CN",
]


@composite
def currency_amounts(draw: st.DrawFn) -> Decimal:
    """Generate realistic currency amounts.

    Events emitted:
    - currency_amount_magnitude={micro|small|medium|large|huge}
    """
    category = draw(st.sampled_from([
        "micro", "small", "medium", "large", "huge",
    ]))

    match category:
        case "micro":
            amount = draw(st.decimals(
                min_value=Decimal("0.01"), max_value=Decimal("0.99"),
                places=2,
            ))
        case "small":
            amount = draw(st.decimals(
                min_value=Decimal("1.00"), max_value=Decimal("99.99"),
                places=2,
            ))
        case "medium":
            amount = draw(st.decimals(
                min_value=Decimal("100.00"), max_value=Decimal("9999.99"),
                places=2,
            ))
        case "large":
            amount = draw(st.decimals(
                min_value=Decimal("10000.00"), max_value=Decimal("999999.99"),
                places=2,
            ))
        case _:  # huge
            amount = draw(st.decimals(
                min_value=Decimal("1000000.00"),
                max_value=Decimal("99999999.99"),
                places=2,
            ))

    event(f"currency_amount_magnitude={category}")
    return amount


@composite
def unambiguous_currency_inputs(
    draw: st.DrawFn,
) -> tuple[str, str, str]:
    """Generate unambiguous currency inputs (symbol + formatted amount).

    Events emitted:
    - currency_input_type=unambiguous_symbol
    - currency_input_format={prefix|suffix|iso_prefix|iso_suffix}

    Returns:
        Tuple of (value_str, locale, expected_currency_code).
    """
    symbol, code = draw(st.sampled_from(list(_UNAMBIGUOUS_SYMBOLS.items())))
    locale = draw(st.sampled_from(_FORMATTING_LOCALES))
    amount = draw(currency_amounts())

    fmt = draw(st.sampled_from([
        "prefix", "suffix", "iso_prefix", "iso_suffix",
    ]))

    match fmt:
        case "prefix":
            value = f"{symbol}{amount}"
        case "suffix":
            value = f"{amount} {symbol}"
        case "iso_prefix":
            value = f"{code} {amount}"
        case _:  # iso_suffix
            value = f"{amount} {code}"

    event("currency_input_type=unambiguous_symbol")
    event(f"currency_input_format={fmt}")
    return (value, locale, code)


@composite
def ambiguous_currency_inputs(
    draw: st.DrawFn,
) -> tuple[str, str, str, str]:
    """Generate ambiguous currency inputs requiring resolution.

    Events emitted:
    - currency_input_type=ambiguous_symbol
    - currency_ambiguous_symbol={dollar|yen|pound|krona|other}

    Returns:
        Tuple of (value_str, locale, default_currency, expected_code).
    """
    locale, expected = draw(st.sampled_from(_LOCALE_CURRENCY_PAIRS))
    amount = draw(currency_amounts())

    # Pick symbol appropriate for the locale's currency
    symbol = "$"
    symbol_cat = "dollar"
    if expected in {"JPY", "CNY"}:
        symbol = "\u00a5"
        symbol_cat = "yen"
    elif expected == "GBP":
        symbol = "\u00a3"
        symbol_cat = "pound"
    elif expected == "SEK":
        symbol = "kr"
        symbol_cat = "krona"
    elif expected in {"INR", "KRW"}:
        # Use ISO code for these (their symbols are unambiguous)
        symbol = expected
        symbol_cat = "other"

    value = f"{symbol}{amount}"

    event("currency_input_type=ambiguous_symbol")
    event(f"currency_ambiguous_symbol={symbol_cat}")
    return (value, locale, expected, expected)


@composite
def iso_code_currency_inputs(
    draw: st.DrawFn,
) -> tuple[str, str, str]:
    """Generate ISO-code-based currency inputs.

    Events emitted:
    - currency_input_type=iso_code
    - currency_iso_position={prefix|suffix}

    Returns:
        Tuple of (value_str, locale, expected_code).
    """
    code = draw(st.sampled_from(_COMMON_ISO_CODES))
    locale = draw(st.sampled_from(_FORMATTING_LOCALES))
    amount = draw(currency_amounts())
    position = draw(st.sampled_from(["prefix", "suffix"]))

    match position:
        case "prefix":
            value = f"{code} {amount}"
        case _:
            value = f"{amount} {code}"

    event("currency_input_type=iso_code")
    event(f"currency_iso_position={position}")
    return (value, locale, code)


@composite
def invalid_currency_inputs(
    draw: st.DrawFn,
) -> tuple[str, str]:
    """Generate invalid currency inputs that should fail parsing.

    Events emitted:
    - currency_input_type=invalid
    - currency_invalid_reason={no_symbol|no_digits|empty|garbage|bad_iso}

    Returns:
        Tuple of (value_str, locale).
    """
    reason = draw(st.sampled_from([
        "no_symbol", "no_digits", "empty", "garbage", "bad_iso",
    ]))
    locale = draw(st.sampled_from(_FORMATTING_LOCALES))

    match reason:
        case "no_symbol":
            value = draw(st.from_regex(r"[0-9]{1,6}\.[0-9]{2}", fullmatch=True))
        case "no_digits":
            value = draw(st.sampled_from([
                "\u20ac", "$", "USD", "hello", "abc def",
            ]))
        case "empty":
            value = ""
        case "garbage":
            value = draw(st.text(
                alphabet=st.characters(
                    blacklist_categories=["Cs"],
                    blacklist_characters=list("0123456789"),
                ),
                min_size=1, max_size=20,
            ))
        case _:  # bad_iso
            # 3-letter uppercase not in ISO 4217 (XXX is valid - "no currency")
            value = draw(st.from_regex(
                r"(ZZZ|QQQ|AAA|YYY) [0-9]{1,4}", fullmatch=True,
            ))

    event("currency_input_type=invalid")
    event(f"currency_invalid_reason={reason}")
    return (value, locale)
