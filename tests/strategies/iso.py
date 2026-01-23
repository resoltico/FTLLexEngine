"""Hypothesis strategies for ISO standards introspection testing.

Provides strategies for generating valid ISO 3166 territory codes,
ISO 4217 currency codes, and locale identifiers for property-based testing.

Usage:
    from hypothesis import given
    from tests.strategies.iso import territory_codes, currency_codes

    @given(code=territory_codes)
    def test_territory_lookup(code):
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypothesis import strategies as st

if TYPE_CHECKING:
    from hypothesis.strategies import SearchStrategy

# ============================================================================
# ISO 3166-1 TERRITORY CODES
# ============================================================================

# Representative sample of ISO 3166-1 alpha-2 country codes.
# Includes major economies, various regions, and edge cases.
# Full validation uses Babel's locale database at runtime.
_SAMPLE_TERRITORY_CODES = [
    # G7 + major economies
    "US", "CA", "GB", "DE", "FR", "IT", "JP",
    # BRICS
    "BR", "RU", "IN", "CN", "ZA",
    # Other major economies
    "AU", "KR", "MX", "ES", "NL", "CH", "SE",
    # Baltic states (for multi-currency region testing)
    "LV", "LT", "EE",
    # Middle East (for 3-decimal currency testing)
    "KW", "BH", "OM", "JO", "IQ",
    # Africa (for 0-decimal currency testing)
    "UG", "RW", "DJ", "GN", "BI",
    # Pacific (for CFP franc testing)
    "NC", "PF", "WF",
    # Edge cases: small territories
    "VA", "MC", "SM", "LI", "AD",
]

territory_codes: SearchStrategy[str] = st.sampled_from(_SAMPLE_TERRITORY_CODES)

# All valid uppercase 2-letter codes (for fuzzing invalid codes)
all_alpha2_codes: SearchStrategy[str] = st.from_regex(r"[A-Z]{2}", fullmatch=True)


# ============================================================================
# ISO 4217 CURRENCY CODES
# ============================================================================

# Representative sample of ISO 4217 currency codes.
# Includes major currencies, various decimal configurations, and edge cases.
_SAMPLE_CURRENCY_CODES = [
    # Major currencies (2 decimals)
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "AUD", "CAD",
    # Zero decimal currencies
    "KRW", "VND", "ISK", "CLP", "PYG", "UGX", "RWF",
    "XAF", "XOF", "XPF",  # CFA/CFP francs
    # Three decimal currencies
    "KWD", "BHD", "OMR", "JOD", "IQD", "TND", "LYD",
    # Four decimal currencies (accounting units)
    "CLF", "UYW",
    # Regional currencies
    "INR", "BRL", "MXN", "ZAR", "RUB", "TRY", "PLN", "CZK",
    # Crypto-adjacent (but ISO-standard)
    "XAU", "XAG", "XPT", "XPD",  # Precious metals
]

currency_codes: SearchStrategy[str] = st.sampled_from(_SAMPLE_CURRENCY_CODES)

# All valid uppercase 3-letter codes (for fuzzing invalid codes)
all_alpha3_codes: SearchStrategy[str] = st.from_regex(r"[A-Z]{3}", fullmatch=True)

# Currencies by decimal places (for targeted testing)
zero_decimal_currencies: SearchStrategy[str] = st.sampled_from([
    "JPY", "KRW", "VND", "ISK", "CLP", "PYG", "UGX", "RWF",
    "BIF", "DJF", "GNF", "KMF", "VUV", "XAF", "XOF", "XPF",
])

three_decimal_currencies: SearchStrategy[str] = st.sampled_from([
    "BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND",
])


# ============================================================================
# LOCALE STRATEGIES
# ============================================================================

# Common locale codes for localized name/symbol retrieval.
# Supports both language-only (e.g., "en") and language_territory (e.g., "en_US").
_SAMPLE_LOCALE_CODES = [
    "en", "en_US", "en_GB", "en_AU",
    "de", "de_DE", "de_AT", "de_CH",
    "fr", "fr_FR", "fr_CA", "fr_BE",
    "es", "es_ES", "es_MX", "es_AR",
    "ja", "ja_JP",
    "zh", "zh_CN", "zh_TW", "zh_HK",
    "ko", "ko_KR",
    "ru", "ru_RU",
    "ar", "ar_SA", "ar_EG",
    "pt", "pt_BR", "pt_PT",
    "it", "it_IT",
    "nl", "nl_NL", "nl_BE",
    "lv", "lv_LV",  # Latvian (for project context)
    "lt", "lt_LT",  # Lithuanian
    "et", "et_EE",  # Estonian
]

locale_codes: SearchStrategy[str] = st.sampled_from(_SAMPLE_LOCALE_CODES)

# Language-only codes
language_codes: SearchStrategy[str] = st.sampled_from([
    "en", "de", "fr", "es", "ja", "zh", "ko", "ru", "ar", "pt", "it", "nl",
])

# Malformed locale codes (for error handling tests)
malformed_locales: SearchStrategy[str] = st.one_of(
    st.just(""),
    st.just("x"),
    st.just("xxx_YYY"),
    st.from_regex(r"[a-z]{1,8}_[A-Z]{3,}", fullmatch=True),  # Invalid territory length
)
