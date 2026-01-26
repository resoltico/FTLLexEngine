"""Comprehensive tests for FluentBundle to achieve 100% coverage.

This module provides complete coverage for all remaining uncovered lines in
src/ftllexengine/runtime/bundle.py. Each test class targets specific uncovered
code paths identified through coverage analysis.

Coverage targets:
- Property accessors (locale, use_isolating, strict, cache_*, max_*)
- Classmethod for_system_locale
- Special methods (__repr__, __enter__, __exit__)
- Type validation for add_resource/validate_resource/format_pattern
- Strict mode error handling
- Introspection methods (get_message_variables, introspect_message, introspect_term)
- Cache management (add_function, clear_cache, get_cache_stats)
- format_value alias
- has_attribute method
- get_babel_locale method

Tests use Hypothesis for property-based testing where applicable, and unit tests
for deterministic API boundaries.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT
from ftllexengine.integrity import FormattingIntegrityError, SyntaxIntegrityError
from ftllexengine.runtime.bundle import FluentBundle

# =============================================================================
# Property Accessors Coverage
# =============================================================================


class TestBundlePropertyAccessors:
    """Test all property accessors for complete coverage."""

    def test_locale_property_returns_configured_locale(self) -> None:
        """locale property returns the configured locale code."""
        bundle = FluentBundle("lv_LV")
        assert bundle.locale == "lv_LV"

        bundle_ar = FluentBundle("ar_EG")
        assert bundle_ar.locale == "ar_EG"

    def test_use_isolating_property_returns_configured_value(self) -> None:
        """use_isolating property returns the configured boolean."""
        bundle_enabled = FluentBundle("en", use_isolating=True)
        assert bundle_enabled.use_isolating is True

        bundle_disabled = FluentBundle("en", use_isolating=False)
        assert bundle_disabled.use_isolating is False

    def test_strict_property_returns_configured_value(self) -> None:
        """strict property returns the strict mode boolean."""
        bundle_strict = FluentBundle("en", strict=True)
        assert bundle_strict.strict is True

        bundle_normal = FluentBundle("en", strict=False)
        assert bundle_normal.strict is False

        bundle_default = FluentBundle("en")
        assert bundle_default.strict is False

    def test_cache_enabled_property_with_enabled_cache(self) -> None:
        """cache_enabled property returns True when cache is enabled."""
        bundle = FluentBundle("en", enable_cache=True)
        assert bundle.cache_enabled is True

    def test_cache_enabled_property_with_disabled_cache(self) -> None:
        """cache_enabled property returns False when cache is disabled."""
        bundle = FluentBundle("en", enable_cache=False)
        assert bundle.cache_enabled is False

        bundle_default = FluentBundle("en")
        assert bundle_default.cache_enabled is False

    def test_cache_size_property_returns_configured_size(self) -> None:
        """cache_size property returns configured maximum cache size."""
        bundle = FluentBundle("en", enable_cache=True, cache_size=500)
        assert bundle.cache_size == 500

        bundle_no_cache = FluentBundle("en", enable_cache=False, cache_size=200)
        assert bundle_no_cache.cache_size == 200

    def test_cache_usage_property_returns_current_size(self) -> None:
        """cache_usage property returns current number of cached entries."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg1 = Hello\nmsg2 = World")

        assert bundle.cache_usage == 0
        bundle.format_pattern("msg1")
        assert bundle.cache_usage == 1
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2

    def test_cache_usage_property_returns_zero_when_disabled(self) -> None:
        """cache_usage property returns 0 when cache is disabled."""
        bundle = FluentBundle("en", enable_cache=False)
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 0

    def test_cache_write_once_property_returns_configured_value(self) -> None:
        """cache_write_once property returns configured boolean."""
        bundle_enabled = FluentBundle("en", enable_cache=True, cache_write_once=True)
        assert bundle_enabled.cache_write_once is True

        bundle_disabled = FluentBundle("en", enable_cache=True, cache_write_once=False)
        assert bundle_disabled.cache_write_once is False

    def test_cache_enable_audit_property_returns_configured_value(self) -> None:
        """cache_enable_audit property returns configured boolean."""
        bundle_enabled = FluentBundle("en", enable_cache=True, cache_enable_audit=True)
        assert bundle_enabled.cache_enable_audit is True

        bundle_disabled = FluentBundle("en", enable_cache=True, cache_enable_audit=False)
        assert bundle_disabled.cache_enable_audit is False

    def test_cache_max_audit_entries_property_returns_configured_value(self) -> None:
        """cache_max_audit_entries property returns configured maximum."""
        bundle = FluentBundle("en", enable_cache=True, cache_max_audit_entries=5000)
        assert bundle.cache_max_audit_entries == 5000

    def test_cache_max_entry_weight_property_returns_configured_value(self) -> None:
        """cache_max_entry_weight property returns configured maximum."""
        bundle = FluentBundle("en", enable_cache=True, cache_max_entry_weight=8000)
        assert bundle.cache_max_entry_weight == 8000

    def test_cache_max_errors_per_entry_property_returns_configured_value(self) -> None:
        """cache_max_errors_per_entry property returns configured maximum."""
        bundle = FluentBundle("en", enable_cache=True, cache_max_errors_per_entry=25)
        assert bundle.cache_max_errors_per_entry == 25

    def test_max_source_size_property_returns_configured_value(self) -> None:
        """max_source_size property returns configured maximum."""
        bundle = FluentBundle("en", max_source_size=1_000_000)
        assert bundle.max_source_size == 1_000_000

    def test_max_nesting_depth_property_returns_configured_value(self) -> None:
        """max_nesting_depth property returns configured maximum."""
        bundle = FluentBundle("en", max_nesting_depth=50)
        assert bundle.max_nesting_depth == 50


# =============================================================================
# for_system_locale Classmethod Coverage
# =============================================================================


class TestForSystemLocaleClassmethod:
    """Test for_system_locale classmethod."""

    def test_for_system_locale_creates_bundle_with_detected_locale(self) -> None:
        """for_system_locale creates bundle with system locale."""
        with patch("ftllexengine.runtime.bundle.get_system_locale", return_value="en_US"):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "en_US"

    def test_for_system_locale_passes_configuration_parameters(self) -> None:
        """for_system_locale passes all configuration parameters."""
        with patch("ftllexengine.runtime.bundle.get_system_locale", return_value="de_DE"):
            bundle = FluentBundle.for_system_locale(
                use_isolating=False,
                enable_cache=True,
                cache_size=2000,
                strict=True,
                max_source_size=500_000,
            )

            assert bundle.locale == "de_DE"
            assert bundle.use_isolating is False
            assert bundle.cache_enabled is True
            assert bundle.cache_size == 2000
            assert bundle.strict is True
            assert bundle.max_source_size == 500_000

    def test_for_system_locale_raises_when_system_locale_unavailable(self) -> None:
        """for_system_locale raises RuntimeError when system locale cannot be determined."""
        with patch(
            "ftllexengine.runtime.bundle.get_system_locale",
            side_effect=RuntimeError("Cannot determine system locale"),
        ), pytest.raises(RuntimeError, match="Cannot determine system locale"):
            FluentBundle.for_system_locale()


# =============================================================================
# Special Methods Coverage (__repr__, __enter__, __exit__)
# =============================================================================


class TestBundleSpecialMethods:
    """Test special methods for complete coverage."""

    def test_repr_shows_locale_and_counts(self) -> None:
        """__repr__ returns string with locale and message/term counts."""
        bundle = FluentBundle("lv_LV")
        repr_str = repr(bundle)

        assert "FluentBundle" in repr_str
        assert "lv_LV" in repr_str
        assert "messages=0" in repr_str
        assert "terms=0" in repr_str

    def test_repr_shows_accurate_counts_after_adding_resources(self) -> None:
        """__repr__ reflects accurate counts after adding resources."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg1 = Hello\nmsg2 = World\n-brand = Firefox")

        repr_str = repr(bundle)
        assert "messages=2" in repr_str
        assert "terms=1" in repr_str

    def test_context_manager_enter_returns_self(self) -> None:
        """__enter__ returns the bundle instance."""
        bundle = FluentBundle("en")
        with bundle as ctx_bundle:
            assert ctx_bundle is bundle

    def test_context_manager_exit_clears_cache_when_modified(self) -> None:
        """__exit__ clears cache when bundle was modified during context."""
        bundle = FluentBundle("en", enable_cache=True)

        with bundle:
            bundle.add_resource("msg = Hello")
            bundle.format_pattern("msg")
            assert bundle.cache_usage == 1

        assert bundle.cache_usage == 0

    def test_context_manager_exit_preserves_cache_when_not_modified(self) -> None:
        """__exit__ preserves cache when bundle was not modified during context."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 1

        with bundle:
            bundle.format_pattern("msg")

        assert bundle.cache_usage == 1

    def test_context_manager_exit_resets_modification_flag(self) -> None:
        """__exit__ resets modification flag for next context."""
        bundle = FluentBundle("en", enable_cache=True)

        with bundle:
            bundle.add_resource("msg1 = Hello")

        assert bundle.cache_usage == 0

        bundle.add_resource("msg2 = World")
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 1

        with bundle:
            bundle.format_pattern("msg2")

        assert bundle.cache_usage == 1


# =============================================================================
# get_babel_locale Method Coverage
# =============================================================================


class TestGetBabelLocaleMethod:
    """Test get_babel_locale introspection method."""

    def test_get_babel_locale_returns_babel_locale_identifier(self) -> None:
        """get_babel_locale returns Babel locale identifier."""
        bundle = FluentBundle("lv")
        babel_locale = bundle.get_babel_locale()
        assert babel_locale == "lv"

    def test_get_babel_locale_with_underscore_locale(self) -> None:
        """get_babel_locale handles underscore-separated locales."""
        bundle = FluentBundle("en_US")
        babel_locale = bundle.get_babel_locale()
        assert babel_locale == "en_US"

    def test_get_babel_locale_with_hyphen_locale(self) -> None:
        """get_babel_locale handles hyphen-separated locales."""
        bundle = FluentBundle("en-GB")
        babel_locale = bundle.get_babel_locale()
        assert "en" in babel_locale


# =============================================================================
# Type Validation Coverage (add_resource, validate_resource)
# =============================================================================


class TestTypeValidationInAddResource:
    """Test type validation in add_resource method."""

    def test_add_resource_rejects_bytes_with_typeerror(self) -> None:
        """add_resource raises TypeError when bytes are passed instead of str."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_add_resource_error_message_suggests_decode(self) -> None:
        """add_resource TypeError suggests decoding bytes to str."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError, match=r"source.decode\('utf-8'\)"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_add_resource_rejects_int_with_typeerror(self) -> None:
        """add_resource raises TypeError for non-string types."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError, match=r"source must be str"):
            bundle.add_resource(42)  # type: ignore[arg-type]


class TestTypeValidationInValidateResource:
    """Test type validation in validate_resource method."""

    def test_validate_resource_rejects_bytes_with_typeerror(self) -> None:
        """validate_resource raises TypeError when bytes are passed."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.validate_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_validate_resource_error_message_suggests_decode(self) -> None:
        """validate_resource TypeError suggests decoding bytes."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError, match=r"source.decode\('utf-8'\)"):
            bundle.validate_resource(b"msg = Hello")  # type: ignore[arg-type]


# =============================================================================
# Strict Mode Syntax Error Handling Coverage
# =============================================================================


class TestStrictModeSyntaxErrorHandling:
    """Test strict mode syntax error handling in _register_resource."""

    def test_strict_mode_raises_syntax_integrity_error_on_junk(self) -> None:
        """Strict mode raises SyntaxIntegrityError when parsing produces junk."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError, match=r"Strict mode: .* syntax error"):
            bundle.add_resource("msg = \n!!invalid!!")

    def test_strict_mode_error_includes_source_path(self) -> None:
        """Strict mode error includes source_path when provided."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(
            SyntaxIntegrityError, match=r"locales/en/messages.ftl"
        ) as exc_info:
            bundle.add_resource("msg = \n!!invalid!!", source_path="locales/en/messages.ftl")

        assert exc_info.value.source_path == "locales/en/messages.ftl"

    def test_strict_mode_error_truncates_long_error_summary(self) -> None:
        """Strict mode error summary truncates to first 3 junk entries."""
        bundle = FluentBundle("en", strict=True)

        invalid_ftl = """
msg1 =
!!error1!!
msg2 =
!!error2!!
msg3 =
!!error3!!
msg4 =
!!error4!!
"""

        with pytest.raises(SyntaxIntegrityError, match=r"and \d+ more") as exc_info:
            bundle.add_resource(invalid_ftl)

        assert "syntax error" in str(exc_info.value).lower()

    def test_strict_mode_does_not_mutate_bundle_on_error(self) -> None:
        """Strict mode does not partially populate bundle on syntax error."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg1 = Hello")
        assert len(bundle.get_message_ids()) == 1

        with pytest.raises(SyntaxIntegrityError):
            bundle.add_resource("msg2 = World\n!!invalid!!")

        assert len(bundle.get_message_ids()) == 1


# =============================================================================
# _raise_strict_error Helper Coverage
# =============================================================================


class TestRaiseStrictErrorHelper:
    """Test _raise_strict_error helper method."""

    def test_raise_strict_error_raises_formatting_integrity_error(self) -> None:
        """_raise_strict_error raises FormattingIntegrityError in strict mode."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello { $name }")

        with pytest.raises(FormattingIntegrityError, match=r"Strict mode"):
            bundle.format_pattern("msg", {})

    def test_strict_mode_error_includes_message_id(self) -> None:
        """Strict mode formatting error includes message ID."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("greeting = Hello { $name }")

        with pytest.raises(FormattingIntegrityError, match=r"greeting") as exc_info:
            bundle.format_pattern("greeting", {})

        assert exc_info.value.message_id == "greeting"

    def test_strict_mode_error_truncates_multiple_errors(self) -> None:
        """Strict mode error summary truncates to first 3 errors."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $a } { $b } { $c } { $d }")

        with pytest.raises(FormattingIntegrityError, match=r"and \d+ more"):
            bundle.format_pattern("msg", {})


# =============================================================================
# format_pattern Type Validation Coverage
# =============================================================================


class TestFormatPatternTypeValidation:
    """Test type validation in format_pattern method."""

    def test_format_pattern_with_empty_message_id_returns_error(self) -> None:
        """format_pattern with empty message ID returns fallback and error."""
        bundle = FluentBundle("en")

        result, errors = bundle.format_pattern("")
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_with_invalid_args_type_returns_error(self) -> None:
        """format_pattern with non-Mapping args returns fallback and error."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg", [])  # type: ignore[arg-type]
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_with_invalid_attribute_type_returns_error(self) -> None:
        """format_pattern with non-string attribute returns fallback and error."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg", {}, attribute=123)  # type: ignore[arg-type]
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_strict_mode_raises_on_empty_message_id(self) -> None:
        """format_pattern in strict mode raises on empty message ID."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("")

    def test_format_pattern_strict_mode_raises_on_invalid_args_type(self) -> None:
        """format_pattern in strict mode raises on invalid args type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")

        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", [])  # type: ignore[arg-type]

    def test_format_pattern_strict_mode_raises_on_invalid_attribute_type(self) -> None:
        """format_pattern in strict mode raises on invalid attribute type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")

        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", {}, attribute=123)  # type: ignore[arg-type]


# =============================================================================
# format_value Method Coverage
# =============================================================================


class TestFormatValueMethod:
    """Test format_value alias method."""

    def test_format_value_formats_message_without_attribute(self) -> None:
        """format_value formats message without attribute access."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("welcome = Hello, { $name }!")

        result, errors = bundle.format_value("welcome", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert errors == ()

    def test_format_value_is_alias_for_format_pattern(self) -> None:
        """format_value is functionally equivalent to format_pattern without attribute."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Test message")

        result1, errors1 = bundle.format_value("msg")
        result2, errors2 = bundle.format_pattern("msg", attribute=None)

        assert result1 == result2
        assert errors1 == errors2


# =============================================================================
# has_attribute Method Coverage
# =============================================================================


class TestHasAttributeMethod:
    """Test has_attribute method."""

    def test_has_attribute_returns_true_when_attribute_exists(self) -> None:
        """has_attribute returns True when message has specified attribute."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
button = Click
    .tooltip = Click to save
"""
        )

        assert bundle.has_attribute("button", "tooltip") is True

    def test_has_attribute_returns_false_when_attribute_missing(self) -> None:
        """has_attribute returns False when attribute does not exist."""
        bundle = FluentBundle("en")
        bundle.add_resource("button = Click\n    .tooltip = Save")

        assert bundle.has_attribute("button", "nonexistent") is False

    def test_has_attribute_returns_false_when_message_missing(self) -> None:
        """has_attribute returns False when message does not exist."""
        bundle = FluentBundle("en")

        assert bundle.has_attribute("nonexistent", "tooltip") is False


# =============================================================================
# get_message_variables Method Coverage
# =============================================================================


class TestGetMessageVariablesMethod:
    """Test get_message_variables method."""

    def test_get_message_variables_returns_variable_set(self) -> None:
        """get_message_variables returns frozenset of variable names."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")

        variables = bundle.get_message_variables("greeting")
        assert "name" in variables
        assert isinstance(variables, frozenset)

    def test_get_message_variables_raises_keyerror_when_message_missing(self) -> None:
        """get_message_variables raises KeyError when message does not exist."""
        bundle = FluentBundle("en")

        with pytest.raises(KeyError, match=r"Message 'nonexistent' not found"):
            bundle.get_message_variables("nonexistent")


# =============================================================================
# get_all_message_variables Method Coverage
# =============================================================================


class TestGetAllMessageVariablesMethod:
    """Test get_all_message_variables batch introspection method."""

    def test_get_all_message_variables_returns_dict_of_variable_sets(self) -> None:
        """get_all_message_variables returns dict mapping message IDs to variables."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
greeting = Hello, { $name }!
farewell = Goodbye, { $firstName } { $lastName }!
simple = No variables here
"""
        )

        all_vars = bundle.get_all_message_variables()

        assert all_vars["greeting"] == frozenset({"name"})
        assert all_vars["farewell"] == frozenset({"firstName", "lastName"})
        assert all_vars["simple"] == frozenset()

    def test_get_all_message_variables_returns_empty_dict_for_empty_bundle(self) -> None:
        """get_all_message_variables returns empty dict when no messages exist."""
        bundle = FluentBundle("en")

        all_vars = bundle.get_all_message_variables()
        assert all_vars == {}


# =============================================================================
# introspect_message and introspect_term Methods Coverage
# =============================================================================


class TestIntrospectionMethods:
    """Test introspect_message and introspect_term methods."""

    def test_introspect_message_returns_metadata(self) -> None:
        """introspect_message returns MessageIntrospection with metadata."""
        bundle = FluentBundle("en")
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")

        info = bundle.introspect_message("price")
        assert "amount" in info.get_variable_names()
        assert "NUMBER" in info.get_function_names()

    def test_introspect_message_raises_keyerror_when_message_missing(self) -> None:
        """introspect_message raises KeyError when message does not exist."""
        bundle = FluentBundle("en")

        with pytest.raises(KeyError, match=r"Message 'nonexistent' not found"):
            bundle.introspect_message("nonexistent")

    def test_introspect_term_returns_metadata(self) -> None:
        """introspect_term returns MessageIntrospection for term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-brand = { $case ->
    [nominative] Firefox
    *[other] Firefox
}
"""
        )

        info = bundle.introspect_term("brand")
        assert "case" in info.get_variable_names()

    def test_introspect_term_raises_keyerror_when_term_missing(self) -> None:
        """introspect_term raises KeyError when term does not exist."""
        bundle = FluentBundle("en")

        with pytest.raises(KeyError, match=r"Term 'nonexistent' not found"):
            bundle.introspect_term("nonexistent")


# =============================================================================
# add_function Method Coverage
# =============================================================================


class TestAddFunctionMethod:
    """Test add_function method with copy-on-write semantics."""

    def test_add_function_registers_custom_function(self) -> None:
        """add_function registers custom function successfully."""
        bundle = FluentBundle("en")

        def CUSTOM(value: Any) -> str:  # noqa: N802 - FTL function naming convention
            return str(value).upper()

        bundle.add_function("CUSTOM", CUSTOM)
        bundle.add_resource("msg = { CUSTOM($val) }")

        result, _errors = bundle.format_pattern("msg", {"val": "hello"})
        assert "HELLO" in result

    def test_add_function_clears_cache(self) -> None:
        """add_function clears cache after registration."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 1

        def CUSTOM(value: Any) -> str:  # noqa: N802 - FTL function naming convention
            return str(value)

        bundle.add_function("CUSTOM", CUSTOM)
        assert bundle.cache_usage == 0

    def test_add_function_marks_bundle_as_modified(self) -> None:
        """add_function marks bundle as modified for context manager."""
        bundle = FluentBundle("en", enable_cache=True)

        def CUSTOM(value: Any) -> str:  # noqa: N802 - FTL function naming convention
            return str(value)

        with bundle:
            bundle.add_function("CUSTOM", CUSTOM)

        assert bundle.cache_usage == 0


# =============================================================================
# clear_cache Method Coverage
# =============================================================================


class TestClearCacheMethod:
    """Test clear_cache method."""

    def test_clear_cache_clears_cached_entries(self) -> None:
        """clear_cache removes all cached format results."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg1 = Hello\nmsg2 = World")

        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2

        bundle.clear_cache()
        assert bundle.cache_usage == 0

    def test_clear_cache_marks_bundle_as_modified(self) -> None:
        """clear_cache marks bundle as modified for context manager."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Hello")

        with bundle:
            bundle.clear_cache()

        assert bundle.cache_usage == 0

    def test_clear_cache_on_bundle_without_cache_succeeds(self) -> None:
        """clear_cache succeeds when cache is not enabled."""
        bundle = FluentBundle("en", enable_cache=False)

        bundle.clear_cache()


# =============================================================================
# get_cache_stats Method Coverage
# =============================================================================


class TestGetCacheStatsMethod:
    """Test get_cache_stats method."""

    def test_get_cache_stats_returns_dict_when_cache_enabled(self) -> None:
        """get_cache_stats returns dict with metrics when cache is enabled."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Hello")

        bundle.format_pattern("msg", {})
        bundle.format_pattern("msg", {})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert "hits" in stats
        assert "misses" in stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_get_cache_stats_returns_none_when_cache_disabled(self) -> None:
        """get_cache_stats returns None when caching is disabled."""
        bundle = FluentBundle("en", enable_cache=False)

        stats = bundle.get_cache_stats()
        assert stats is None


# =============================================================================
# Hypothesis Property-Based Tests
# =============================================================================


class TestBundleHypothesisProperties:
    """Property-based tests for FluentBundle using Hypothesis."""

    @given(st.text(alphabet=st.sampled_from(["a", "b", "c", "_", "-"]), min_size=1, max_size=50))
    def test_property_valid_locale_accepted(self, locale: str) -> None:
        """Property: Any valid locale format is accepted by FluentBundle."""
        if not locale or not locale[0].isalnum():
            return

        try:
            bundle = FluentBundle(locale)
            assert bundle.locale == locale
        except ValueError:
            pass

    @given(st.booleans())
    def test_property_use_isolating_preserved(self, use_isolating: bool) -> None:
        """Property: use_isolating configuration is preserved."""
        bundle = FluentBundle("en", use_isolating=use_isolating)
        assert bundle.use_isolating == use_isolating

    @given(st.booleans())
    def test_property_strict_mode_preserved(self, strict: bool) -> None:
        """Property: strict mode configuration is preserved."""
        bundle = FluentBundle("en", strict=strict)
        assert bundle.strict == strict

    @given(st.integers(min_value=1, max_value=10000))
    def test_property_cache_size_preserved(self, cache_size: int) -> None:
        """Property: cache_size configuration is preserved."""
        bundle = FluentBundle("en", cache_size=cache_size)
        assert bundle.cache_size == cache_size


# =============================================================================
# Additional Coverage for Remaining Missing Lines
# =============================================================================


class TestLocaleValidationExceedsMaxLength:
    """Test locale validation for exceeding max length."""

    def test_locale_exceeding_max_length_rejected(self) -> None:
        """Locale exceeding MAX_LOCALE_LENGTH_HARD_LIMIT raises ValueError."""
        # Create locale that exceeds limit
        long_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 1)

        with pytest.raises(ValueError, match=r"Locale code exceeds maximum length"):
            FluentBundle(long_locale)

    def test_locale_exceeding_max_length_shows_truncated_value(self) -> None:
        """Locale exceeding max shows truncated value in error message."""
        long_locale = "X" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 100)

        with pytest.raises(ValueError, match=r"Locale code exceeds maximum length") as exc_info:
            FluentBundle(long_locale)

        error_msg = str(exc_info.value)
        assert long_locale[:50] in error_msg
        assert str(len(long_locale)) in error_msg


class TestLocaleValidationInvalidFormat:
    """Test locale validation for invalid format (non-ASCII characters)."""

    def test_locale_with_non_ascii_characters_rejected(self) -> None:
        """Locale with non-ASCII characters raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale code format"):
            FluentBundle("ën_FR")

    def test_locale_with_special_characters_rejected(self) -> None:
        """Locale with special characters raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale code format"):
            FluentBundle("en@US")

    def test_locale_with_spaces_rejected(self) -> None:
        """Locale with spaces raises ValueError."""
        with pytest.raises(ValueError, match=r"Invalid locale code format"):
            FluentBundle("en US")


class TestTermOverwriteInSameResource:
    """Test term overwrite within same resource."""

    def test_duplicate_terms_in_same_resource_overwrites(self, caplog: Any) -> None:
        """Duplicate term definitions in same resource produces overwrite warning."""
        bundle = FluentBundle("en")

        # Add resource with duplicate term definitions
        ftl_source = """
-brand = Firefox
-brand = Chrome
"""
        bundle.add_resource(ftl_source)

        # Should have overwrite warning
        assert any(
            "Overwriting existing term '-brand'" in record.message
            for record in caplog.records
        )

    def test_multiple_duplicate_terms_in_same_resource(self, caplog: Any) -> None:
        """Multiple duplicate terms in same resource each produce warnings."""
        bundle = FluentBundle("en")

        ftl_source = """
-brand = First
-version = First
-brand = Second
-version = Second
"""
        bundle.add_resource(ftl_source)

        warnings = [r for r in caplog.records if "Overwriting existing term" in r.message]
        assert len(warnings) == 2


class TestCommentHandlingBranch:
    """Test Comment entry handling in register_resource loop."""

    def test_resource_with_comments_processes_correctly(self, caplog: Any) -> None:
        """Resource with comments is processed and comments are skipped."""
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        # Add resource with comments to trigger Comment case branch
        ftl_source = """
# This is a comment
msg1 = Hello

## Section comment
msg2 = World

### Resource comment
-term = Value
"""
        junk = bundle.add_resource(ftl_source)

        assert len(junk) == 0
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")

    def test_standalone_comments_processed(self, caplog: Any) -> None:
        """Resource with only comments is valid and processes correctly."""
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        ftl_source = """
# Comment 1
## Comment 2
### Comment 3
"""
        junk = bundle.add_resource(ftl_source)
        assert len(junk) == 0

    def test_comment_followed_by_term(self, caplog: Any) -> None:
        """Comment followed by term ensures Comment->loop branch is hit."""
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        # Comment followed by term to ensure loop continuation
        ftl_source = """
# Comment before term
-brand = Firefox
"""
        junk = bundle.add_resource(ftl_source)
        assert len(junk) == 0

    def test_multiple_comments_in_sequence(self, caplog: Any) -> None:
        """Multiple consecutive comments to hit Comment->Comment->loop branch."""
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        ftl_source = """
# Comment 1
# Comment 2
# Comment 3
msg = Hello
"""
        junk = bundle.add_resource(ftl_source)
        assert len(junk) == 0
        assert bundle.has_message("msg")
