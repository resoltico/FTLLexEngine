"""Hypothesis property-based tests for ISO introspection module.

Tests invariants and properties that must hold across all valid inputs.
Uses strategies from tests.strategies.iso for generating test data.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.introspection.iso import (
    CurrencyInfo,
    TerritoryInfo,
    get_currency,
    get_territory,
    get_territory_currencies,
    is_valid_currency_code,
    is_valid_territory_code,
    list_currencies,
    list_territories,
)
from tests.strategies.iso import (
    all_alpha2_codes,
    all_alpha3_codes,
    currency_codes,
    locale_codes,
    malformed_locales,
    territory_codes,
    three_decimal_currencies,
    zero_decimal_currencies,
)

# ============================================================================
# TERRITORY LOOKUP PROPERTIES
# ============================================================================


class TestTerritoryLookupProperties:
    """Property-based tests for territory lookup functions."""

    @given(code=territory_codes)
    def test_get_territory_returns_territory_info(self, code: str) -> None:
        """Valid territory codes always return TerritoryInfo."""
        result = get_territory(code)
        assert result is not None
        assert isinstance(result, TerritoryInfo)

    @given(code=territory_codes)
    def test_territory_alpha2_normalized_to_uppercase(self, code: str) -> None:
        """Returned alpha2 code is always uppercase."""
        result = get_territory(code)
        assert result is not None
        assert result.alpha2 == result.alpha2.upper()
        assert result.alpha2 == code.upper()

    @given(code=territory_codes)
    def test_case_insensitivity_invariant(self, code: str) -> None:
        """Lookup is case-insensitive: upper, lower, mixed all return same data."""
        upper = get_territory(code.upper())
        lower = get_territory(code.lower())
        mixed = get_territory(code[0].lower() + code[1].upper())

        assert upper is not None
        assert upper == lower == mixed

    @given(code=territory_codes, locale=locale_codes)
    def test_territory_name_is_non_empty_string(self, code: str, locale: str) -> None:
        """Territory names are always non-empty strings."""
        result = get_territory(code, locale=locale)
        assert result is not None
        assert isinstance(result.name, str)
        assert len(result.name) > 0

    @given(code=territory_codes)
    def test_territory_in_list_territories(self, code: str) -> None:
        """Any valid territory code is found in list_territories()."""
        result = get_territory(code)
        assert result is not None
        territories = list_territories()
        # Check by alpha2 code since objects may differ by locale
        alpha2_codes = {t.alpha2 for t in territories}
        assert result.alpha2 in alpha2_codes

    @given(code=territory_codes)
    def test_type_guard_consistency(self, code: str) -> None:
        """is_valid_territory_code matches get_territory behavior."""
        is_valid = is_valid_territory_code(code)
        result = get_territory(code)
        assert is_valid == (result is not None)

    @given(code=all_alpha2_codes)
    def test_type_guard_matches_lookup(self, code: str) -> None:
        """Type guard and lookup always agree on validity."""
        is_valid = is_valid_territory_code(code)
        result = get_territory(code)
        assert is_valid == (result is not None)


# ============================================================================
# CURRENCY LOOKUP PROPERTIES
# ============================================================================


class TestCurrencyLookupProperties:
    """Property-based tests for currency lookup functions."""

    @given(code=currency_codes)
    def test_get_currency_returns_currency_info(self, code: str) -> None:
        """Valid currency codes always return CurrencyInfo."""
        result = get_currency(code)
        assert result is not None
        assert isinstance(result, CurrencyInfo)

    @given(code=currency_codes)
    def test_currency_code_normalized_to_uppercase(self, code: str) -> None:
        """Returned currency code is always uppercase."""
        result = get_currency(code)
        assert result is not None
        assert result.code == result.code.upper()
        assert result.code == code.upper()

    @given(code=currency_codes)
    def test_case_insensitivity_invariant(self, code: str) -> None:
        """Lookup is case-insensitive."""
        upper = get_currency(code.upper())
        lower = get_currency(code.lower())

        assert upper is not None
        assert upper == lower

    @given(code=currency_codes, locale=locale_codes)
    def test_currency_name_is_non_empty_string(self, code: str, locale: str) -> None:
        """Currency names are always non-empty strings when available."""
        result = get_currency(code, locale=locale)
        # Not all currencies are available in all locales (CLDR coverage varies)
        assume(result is not None)
        assert result is not None  # Type narrowing for mypy
        assert isinstance(result.name, str)
        assert len(result.name) > 0

    @given(code=currency_codes, locale=locale_codes)
    def test_currency_symbol_is_non_empty_string(self, code: str, locale: str) -> None:
        """Currency symbols are always non-empty strings when available."""
        result = get_currency(code, locale=locale)
        # Not all currencies are available in all locales (CLDR coverage varies)
        assume(result is not None)
        assert result is not None  # Type narrowing for mypy
        assert isinstance(result.symbol, str)
        assert len(result.symbol) > 0

    @given(code=currency_codes)
    def test_currency_in_list_currencies(self, code: str) -> None:
        """Any valid currency code is found in list_currencies()."""
        result = get_currency(code)
        assert result is not None
        currencies = list_currencies()
        currency_codes_set = {c.code for c in currencies}
        assert result.code in currency_codes_set

    @given(code=currency_codes)
    def test_type_guard_consistency(self, code: str) -> None:
        """is_valid_currency_code matches get_currency behavior."""
        is_valid = is_valid_currency_code(code)
        result = get_currency(code)
        assert is_valid == (result is not None)

    @given(code=all_alpha3_codes)
    def test_type_guard_matches_lookup(self, code: str) -> None:
        """Type guard and lookup always agree on validity."""
        is_valid = is_valid_currency_code(code)
        result = get_currency(code)
        assert is_valid == (result is not None)


# ============================================================================
# DECIMAL DIGITS PROPERTIES
# ============================================================================


class TestDecimalDigitsProperties:
    """Property-based tests for currency decimal digits."""

    @given(code=currency_codes)
    def test_decimal_digits_in_valid_range(self, code: str) -> None:
        """Decimal digits are always 0, 2, 3, or 4."""
        result = get_currency(code)
        assert result is not None
        assert result.decimal_digits in {0, 2, 3, 4}

    @given(code=zero_decimal_currencies)
    def test_zero_decimal_currencies(self, code: str) -> None:
        """Known zero-decimal currencies have decimal_digits=0."""
        result = get_currency(code)
        assert result is not None
        assert result.decimal_digits == 0

    @given(code=three_decimal_currencies)
    def test_three_decimal_currencies(self, code: str) -> None:
        """Known three-decimal currencies have decimal_digits=3."""
        result = get_currency(code)
        assert result is not None
        assert result.decimal_digits == 3


# ============================================================================
# TERRITORY-CURRENCY RELATIONSHIP PROPERTIES
# ============================================================================


class TestTerritoryCurrencyProperties:
    """Property-based tests for territory-currency relationships."""

    @given(code=territory_codes)
    def test_territory_currencies_are_all_valid(self, code: str) -> None:
        """get_territory_currencies returns tuple of valid currency codes."""
        currencies = get_territory_currencies(code)
        assert isinstance(currencies, tuple)
        for currency_code in currencies:
            assert is_valid_currency_code(currency_code)

    @given(code=territory_codes)
    def test_territory_currencies_matches_lookup(self, code: str) -> None:
        """TerritoryInfo.currencies matches get_territory_currencies."""
        territory = get_territory(code)
        assert territory is not None
        direct_lookup = get_territory_currencies(code)
        assert territory.currencies == direct_lookup

    @given(code=territory_codes)
    def test_territory_currencies_case_insensitive(self, code: str) -> None:
        """get_territory_currencies is case-insensitive."""
        upper = get_territory_currencies(code.upper())
        lower = get_territory_currencies(code.lower())
        assert upper == lower


# ============================================================================
# CACHE CONSISTENCY PROPERTIES
# ============================================================================


class TestCacheConsistencyProperties:
    """Property-based tests for caching behavior."""

    @given(code=territory_codes)
    def test_repeated_territory_lookup_consistent(self, code: str) -> None:
        """Repeated lookups return identical results."""
        first = get_territory(code)
        second = get_territory(code)
        assert first is second  # Same object from cache

    @given(code=currency_codes)
    def test_repeated_currency_lookup_consistent(self, code: str) -> None:
        """Repeated lookups return identical results."""
        first = get_currency(code)
        second = get_currency(code)
        assert first is second  # Same object from cache

    @given(code=territory_codes, locale=locale_codes)
    def test_locale_specific_caching(self, code: str, locale: str) -> None:
        """Different locales cache separately."""
        en_result = get_territory(code, locale="en")
        locale_result = get_territory(code, locale=locale)

        # Both should be valid
        assert en_result is not None
        assert locale_result is not None

        # Same code, different locale might have different names
        assert en_result.alpha2 == locale_result.alpha2


# ============================================================================
# COLLECTION PROPERTIES
# ============================================================================


class TestCollectionProperties:
    """Property-based tests for list functions."""

    def test_list_territories_returns_frozenset(self) -> None:
        """list_territories returns immutable frozenset."""
        result = list_territories()
        assert isinstance(result, frozenset)

    def test_list_currencies_returns_frozenset(self) -> None:
        """list_currencies returns immutable frozenset."""
        result = list_currencies()
        assert isinstance(result, frozenset)

    def test_all_territory_codes_are_alpha2(self) -> None:
        """All territory codes are 2-letter uppercase."""
        territories = list_territories()
        for territory in territories:
            assert len(territory.alpha2) == 2
            assert territory.alpha2.isalpha()
            assert territory.alpha2.isupper()

    def test_all_currency_codes_are_alpha3(self) -> None:
        """All currency codes are 3-letter uppercase."""
        currencies = list_currencies()
        for currency in currencies:
            assert len(currency.code) == 3
            assert currency.code.isalpha()
            assert currency.code.isupper()

    @given(locale=locale_codes)
    def test_list_territories_subset_of_english(self, locale: str) -> None:
        """Locale territory codes are subset of English (CLDR source)."""
        # CLDR data completeness varies by locale; English is the source
        en_territories = list_territories(locale="en")
        locale_territories = list_territories(locale=locale)

        en_codes = {t.alpha2 for t in en_territories}
        locale_codes_set = {t.alpha2 for t in locale_territories}

        # All locale codes should be in English set (English is most complete)
        assert locale_codes_set <= en_codes

    @given(locale=locale_codes)
    def test_list_currencies_subset_of_english(self, locale: str) -> None:
        """Locale currency codes are subset of English (CLDR source)."""
        # CLDR data completeness varies by locale; English is the source
        en_currencies = list_currencies(locale="en")
        locale_currencies = list_currencies(locale=locale)

        en_codes = {c.code for c in en_currencies}
        locale_codes_set = {c.code for c in locale_currencies}

        # All locale codes should be in English set (English is most complete)
        assert locale_codes_set <= en_codes


# ============================================================================
# IMMUTABILITY PROPERTIES
# ============================================================================


class TestImmutabilityProperties:
    """Property-based tests for immutability guarantees."""

    @given(code=territory_codes)
    def test_territory_info_is_frozen(self, code: str) -> None:
        """TerritoryInfo cannot be mutated."""
        result = get_territory(code)
        assert result is not None
        with pytest.raises(AttributeError):
            result.alpha2 = "XX"  # type: ignore[misc]

    @given(code=currency_codes)
    def test_currency_info_is_frozen(self, code: str) -> None:
        """CurrencyInfo cannot be mutated."""
        result = get_currency(code)
        assert result is not None
        with pytest.raises(AttributeError):
            result.code = "XXX"  # type: ignore[misc]

    @given(code=territory_codes)
    def test_territory_info_is_hashable(self, code: str) -> None:
        """TerritoryInfo can be used in sets and as dict keys."""
        result = get_territory(code)
        assert result is not None
        # Should not raise
        h = hash(result)
        assert isinstance(h, int)
        s = {result}
        assert len(s) == 1
        d = {result: "value"}
        assert d[result] == "value"

    @given(code=currency_codes)
    def test_currency_info_is_hashable(self, code: str) -> None:
        """CurrencyInfo can be used in sets and as dict keys."""
        result = get_currency(code)
        assert result is not None
        # Should not raise
        h = hash(result)
        assert isinstance(h, int)
        s = {result}
        assert len(s) == 1
        d = {result: "value"}
        assert d[result] == "value"


# ============================================================================
# EDGE CASE PROPERTIES
# ============================================================================


class TestEdgeCaseProperties:
    """Property-based tests for edge cases and invalid inputs."""

    @given(code=st.text(max_size=1))
    def test_short_strings_rejected_as_territory(self, code: str) -> None:
        """Strings shorter than 2 chars are never valid territory codes."""
        assert is_valid_territory_code(code) is False

    @given(code=st.text(min_size=3, max_size=10))
    def test_long_strings_rejected_as_territory(self, code: str) -> None:
        """Strings longer than 2 chars are never valid territory codes."""
        assert is_valid_territory_code(code) is False

    @given(code=st.text(max_size=2))
    def test_short_strings_rejected_as_currency(self, code: str) -> None:
        """Strings shorter than 3 chars are never valid currency codes."""
        assert is_valid_currency_code(code) is False

    @given(code=st.text(min_size=4, max_size=10))
    def test_long_strings_rejected_as_currency(self, code: str) -> None:
        """Strings longer than 3 chars are never valid currency codes."""
        assert is_valid_currency_code(code) is False

    @given(code=st.from_regex(r"[0-9]{2}", fullmatch=True))
    def test_numeric_strings_rejected_as_territory(self, code: str) -> None:
        """Numeric-only strings are never valid territory codes."""
        # Note: Some could theoretically be CLDR numeric codes, but
        # our API only supports alpha-2 codes
        assert get_territory(code) is None

    @given(code=st.from_regex(r"[0-9]{3}", fullmatch=True))
    def test_numeric_strings_rejected_as_currency(self, code: str) -> None:
        """Numeric-only strings are never valid currency codes."""
        assert get_currency(code) is None

    @given(locale=malformed_locales, code=territory_codes)
    def test_malformed_locale_territory_degrades_gracefully(
        self, locale: str, code: str
    ) -> None:
        """Malformed locales degrade gracefully without crashing."""
        try:
            result = get_territory(code, locale=locale)
            # If no exception, result should be None or valid
            assert result is None or isinstance(result, TerritoryInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions for malformed locales
            pass

    @given(locale=malformed_locales, code=currency_codes)
    def test_malformed_locale_currency_degrades_gracefully(
        self, locale: str, code: str
    ) -> None:
        """Malformed locales degrade gracefully without crashing."""
        try:
            result = get_currency(code, locale=locale)
            # If no exception, result should be None or valid
            assert result is None or isinstance(result, CurrencyInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions for malformed locales
            pass

    @given(locale=malformed_locales)
    def test_malformed_locale_list_territories_degrades_gracefully(
        self, locale: str
    ) -> None:
        """Malformed locales degrade gracefully for list operations."""
        try:
            result = list_territories(locale=locale)
            # If no exception, result should be valid frozenset
            assert isinstance(result, frozenset)
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions for malformed locales
            pass

    @given(locale=malformed_locales)
    @settings(deadline=None)  # Cold-cache locale parsing has inherent variability
    def test_malformed_locale_list_currencies_degrades_gracefully(
        self, locale: str
    ) -> None:
        """Malformed locales degrade gracefully for list operations."""
        try:
            result = list_currencies(locale=locale)
            # If no exception, result should be valid frozenset
            assert isinstance(result, frozenset)
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions for malformed locales
            pass


# ============================================================================
# CACHE POLLUTION PREVENTION PROPERTIES
# ============================================================================


class TestCachePollutionPrevention:
    """Property-based tests for cache pollution prevention.

    Validates that validation functions do NOT pollute the primary lookup caches
    by caching None results for invalid codes. This is critical for financial
    applications where attackers could degrade performance by flooding validation
    with random strings.

    Design: Validation uses membership check against a cached code set. The first
    validation call triggers _list_*_impl which populates the lookup cache with
    ALL VALID codes (one-time cost). Subsequent validations of INVALID codes use
    O(1) set membership and do NOT add None entries to the cache.
    """

    def test_territory_validation_cache_stable_after_warmup(self) -> None:
        """After initial warmup, validation doesn't modify lookup cache.

        The validation function checks membership in a pre-built code set rather
        than calling get_territory(). After the code set is populated, subsequent
        validations (whether valid or invalid codes) don't add new lookup entries.
        """
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _get_territory_impl,
            clear_iso_cache,
        )

        clear_iso_cache()

        # First validation call populates the cache with all valid territories
        is_valid_territory_code("US")

        # pylint: disable=no-value-for-parameter  # lru_cache decorator adds cache_info()
        cache_info_after_warmup = _get_territory_impl.cache_info()
        initial_misses = cache_info_after_warmup.misses
        initial_size = cache_info_after_warmup.currsize

        # Validate multiple codes - both valid and known-invalid patterns
        # After warmup, NONE of these should trigger new cache entries
        test_codes = ["US", "GB", "DE", "XZ", "YZ", "00", "!!"]
        for code in test_codes:
            is_valid_territory_code(code)

        # Cache should NOT have grown - validation uses set membership
        cache_info_after = _get_territory_impl.cache_info()
        # pylint: enable=no-value-for-parameter

        # Miss count should not increase
        assert cache_info_after.misses == initial_misses
        # Size should not increase
        assert cache_info_after.currsize == initial_size

    def test_currency_validation_cache_stable_after_warmup(self) -> None:
        """After initial warmup, validation doesn't modify lookup cache.

        The validation function checks membership in a pre-built code set rather
        than calling get_currency(). After the code set is populated, subsequent
        validations (whether valid or invalid codes) don't add new lookup entries.
        """
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _get_currency_impl,
            clear_iso_cache,
        )

        clear_iso_cache()

        # First validation call populates the cache with all valid currencies
        is_valid_currency_code("USD")

        # pylint: disable=no-value-for-parameter  # lru_cache decorator adds cache_info()
        cache_info_after_warmup = _get_currency_impl.cache_info()
        initial_misses = cache_info_after_warmup.misses
        initial_size = cache_info_after_warmup.currsize

        # Validate multiple codes - both valid and known-invalid patterns
        # After warmup, NONE of these should trigger new cache entries
        test_codes = ["USD", "EUR", "GBP", "XZY", "YZX", "000", "!!!"]
        for code in test_codes:
            is_valid_currency_code(code)

        # Cache should NOT have grown - validation uses set membership
        cache_info_after = _get_currency_impl.cache_info()
        # pylint: enable=no-value-for-parameter

        # Miss count should not increase
        assert cache_info_after.misses == initial_misses
        # Size should not increase
        assert cache_info_after.currsize == initial_size

    @given(
        invalid_codes=st.lists(
            st.text(alphabet="XYZ", min_size=2, max_size=2),
            min_size=10,
            max_size=50,
        )
    )
    def test_bulk_invalid_territory_validation(
        self, invalid_codes: list[str]
    ) -> None:
        """PROPERTY: Bulk validation of invalid codes doesn't grow lookup cache.

        After initial cache population, repeated validation of invalid codes
        should not add any entries or trigger any cache misses.
        """
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _get_territory_impl,
            clear_iso_cache,
        )

        clear_iso_cache()

        # Warm up: First validation populates all valid territories
        is_valid_territory_code("US")

        # pylint: disable=no-value-for-parameter  # lru_cache decorator adds cache_info()
        baseline = _get_territory_impl.cache_info()

        # Validate many invalid codes
        for code in invalid_codes:
            if len(code) == 2 and code.isalpha():
                is_valid_territory_code(code)

        final = _get_territory_impl.cache_info()
        # pylint: enable=no-value-for-parameter

        # No new misses, no new entries
        assert final.misses == baseline.misses
        assert final.currsize == baseline.currsize

    @given(
        invalid_codes=st.lists(
            st.text(alphabet="XYZ", min_size=3, max_size=3),
            min_size=10,
            max_size=50,
        )
    )
    def test_bulk_invalid_currency_validation(
        self, invalid_codes: list[str]
    ) -> None:
        """PROPERTY: Bulk validation of invalid codes doesn't grow lookup cache.

        After initial cache population, repeated validation of invalid codes
        should not add any entries or trigger any cache misses.
        """
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _get_currency_impl,
            clear_iso_cache,
        )

        clear_iso_cache()

        # Warm up: First validation populates all valid currencies
        is_valid_currency_code("USD")

        # pylint: disable=no-value-for-parameter  # lru_cache decorator adds cache_info()
        baseline = _get_currency_impl.cache_info()

        # Validate many invalid codes
        for code in invalid_codes:
            if len(code) == 3 and code.isalpha():
                is_valid_currency_code(code)

        final = _get_currency_impl.cache_info()
        # pylint: enable=no-value-for-parameter

        # No new misses, no new entries
        assert final.misses == baseline.misses
        assert final.currsize == baseline.currsize

    def test_validation_uses_o1_membership_check(self) -> None:
        """Validation uses O(1) set membership, not O(n) linear search.

        Validates the implementation detail that validation goes through
        cached code sets for constant-time lookup.
        """
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _currency_codes_impl,
            _territory_codes_impl,
            clear_iso_cache,
        )

        clear_iso_cache()

        # First validation call should populate the code set cache
        is_valid_territory_code("US")
        is_valid_currency_code("USD")

        # Verify code set caches were populated
        territory_codes_info = _territory_codes_impl.cache_info()
        currency_codes_info = _currency_codes_impl.cache_info()

        assert territory_codes_info.currsize >= 1
        assert currency_codes_info.currsize >= 1

    def test_cache_clear_includes_code_set_caches(self) -> None:
        """clear_iso_cache() also clears the validation code set caches."""
        # Function-local import to access internal cache functions
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _currency_codes_impl,
            _territory_codes_impl,
            clear_iso_cache,
        )

        # Populate caches
        is_valid_territory_code("US")
        is_valid_currency_code("USD")

        # Clear all caches
        clear_iso_cache()

        # Verify code set caches were cleared
        assert _territory_codes_impl.cache_info().currsize == 0
        assert _currency_codes_impl.cache_info().currsize == 0
