"""Tests for plural_rules.py - CLDR plural category selection using Babel.

Comprehensive property-based tests ensuring plural rule correctness across all locales
and number ranges. Critical for multilingual applications with proper pluralization.

Property-Based Testing Strategy:
    Uses Hypothesis to verify mathematical properties and CLDR compliance across
    locale families (Germanic, Slavic, Romance, Semitic, etc.).

Coverage:
    - All CLDR plural categories (zero, one, two, few, many, other)
    - 30+ representative locales across language families
    - Edge cases (unknown locales, large numbers, decimals)
    - Babel ImportError path for parser-only installations
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import patch

import pytest
from babel.core import UnknownLocaleError
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

import ftllexengine.core.babel_compat as _bc
from ftllexengine.runtime.plural_rules import select_plural_category

# ============================================================================
# Hypothesis Strategies
# ============================================================================

# Valid locale codes across language families
LOCALE_CODES = st.sampled_from([
    "en", "en_US", "en_GB",
    "lv", "lv_LV",
    "de", "de_DE",
    "pl", "pl_PL",
    "ru", "ru_RU",
    "ar", "ar_SA",
    "fr", "fr_FR",
    "es", "es_ES",
    "it", "it_IT",
    "pt", "pt_PT", "pt_BR",
    "zh", "zh_CN",
    "ja", "ja_JP",
    "ko", "ko_KR",
    "hi", "hi_IN",
    "bn", "bn_BD",
    "vi", "vi_VN",
    "tr", "tr_TR",
    "th", "th_TH",
    "uk", "uk_UA",
])

# Numbers strategy (integers and decimals)
NUMBERS = st.one_of(
    st.integers(min_value=0, max_value=1000000),
    st.decimals(
        min_value=Decimal(0), max_value=Decimal(1000000),
        allow_nan=False, allow_infinity=False,
    ),
)

__all__ = [
    "LOCALE_CODES",
    "NUMBERS",
    "Decimal",
    "UnknownLocaleError",
    "_bc",
    "assume",
    "event",
    "example",
    "given",
    "patch",
    "pytest",
    "select_plural_category",
    "st",
    "sys",
]
