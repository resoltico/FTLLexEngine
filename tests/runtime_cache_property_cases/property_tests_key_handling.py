# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - KEY HANDLING
# ============================================================================


@pytest.mark.fuzz
class TestCacheKeyHandling:
    """Test cache key construction and equality."""

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_same_key_retrieves_same_value(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Same key components retrieve same cached value."""
        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        # Put with specific key
        cache.put(msg_id, None, None, locale, use_isolating=True, formatted=formatted, errors=errors)

        # Get with same key components
        entry = cache.get(msg_id, None, None, locale, use_isolating=True)

        assert entry is not None
        assert entry.as_result() == value
        event(f"locale={locale}")

    @given(
        msg_id=message_ids,
        locale1=locale_codes,
        locale2=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_different_locale_creates_different_key(
        self,
        msg_id: str,
        locale1: str,
        locale2: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Different locales create different cache keys."""
        assume(locale1 != locale2)

        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        # Put with locale1
        cache.put(msg_id, None, None, locale1, use_isolating=True, formatted=formatted, errors=errors)

        # Get with locale2 should miss
        result = cache.get(msg_id, None, None, locale2, use_isolating=True)

        assert result is None
        event(f"locale_pair={locale1}_{locale2}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        attr1=attributes,
        attr2=attributes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_different_attribute_creates_different_key(
        self,
        msg_id: str,
        locale: str,
        attr1: str | None,
        attr2: str | None,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Different attributes create different cache keys."""
        assume(attr1 != attr2)

        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        # Put with attr1
        cache.put(msg_id, None, attr1, locale, use_isolating=True, formatted=formatted, errors=errors)

        # Get with attr2 should miss
        result = cache.get(msg_id, None, attr2, locale, use_isolating=True)

        assert result is None
        has_attr1 = attr1 is not None
        event(f"has_attr={has_attr1}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_args_dict_key_stability(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Equivalent args dicts produce same cache key."""
        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        # Put with args dict
        args = {"x": 1, "y": 2}
        cache.put(msg_id, args, None, locale, use_isolating=True, formatted=formatted, errors=errors)

        # Get with equivalent dict (different order)
        args_reordered = {"y": 2, "x": 1}
        entry = cache.get(msg_id, args_reordered, None, locale, use_isolating=True)

        # Should hit cache (dict key normalized)
        assert entry is not None
        assert entry.as_result() == value
        event(f"locale={locale}")
