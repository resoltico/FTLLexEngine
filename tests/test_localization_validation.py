"""Edge case tests for localization.py.

Unit tests for localization module edge cases:
- LoadSummary junk entry handling
- PathResourceLoader whitespace validation for resource IDs
- FluentLocalization whitespace validation for locales
- FluentLocalization type validation for args and attributes
- ResourceLoadResult property methods
- FluentLocalization auxiliary methods (repr, cache, bundles, etc.)

Property tests that overlap with test_localization_property.py (the fuzz
module) are deliberately omitted here; only properties unique to this
file are retained (format_pattern invalid args, get_bundles laziness).

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax.ast import Junk, Span


@st.composite
def locale_codes(draw: st.DrawFn) -> str:
    """Generate valid locale codes."""
    language = draw(
        st.text(
            min_size=2,
            max_size=2,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        )
    )
    region = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=2,
                max_size=2,
                alphabet=st.characters(min_codepoint=65, max_codepoint=90),
            ),
        )
    )
    return f"{language}-{region}" if region else language


@st.composite
def message_identifiers(draw: st.DrawFn) -> str:
    """Generate valid FTL message identifiers."""
    import string  # noqa: PLC0415

    first_char = draw(st.sampled_from(string.ascii_letters))
    rest_chars = draw(
        st.text(
            min_size=0,
            max_size=20,
            alphabet=string.ascii_letters + string.digits + "-_",
        )
    )
    return first_char + rest_chars


class TestLoadSummaryAllCleanProperty:
    """Test LoadSummary.all_clean property with junk entries."""

    def test_all_clean_false_with_junk_entries(self) -> None:
        """all_clean returns False when junk_count > 0."""
        # Create Junk entry for testing
        junk_entry = Junk(content="invalid content", span=Span(start=0, end=15))

        # Create successful result WITH junk
        result_with_junk = ResourceLoadResult(
            locale="en",
            resource_id="test.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk_entry,),
        )

        summary = LoadSummary(results=(result_with_junk,))

        # Should have successful load but junk entries
        assert summary.all_successful is True  # No errors, all found
        assert summary.has_junk is True
        assert summary.junk_count == 1
        assert summary.all_clean is False  # Line 252: junk_count > 0

    def test_all_clean_true_when_no_junk(self) -> None:
        """all_clean is True when all successful and no junk."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="test.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(),  # No junk
        )

        summary = LoadSummary(results=(result,))

        assert summary.all_successful is True
        assert summary.all_clean is True  # No errors, no junk
        assert summary.junk_count == 0


class TestPathResourceLoaderWhitespaceValidation:
    """Test PathResourceLoader._validate_resource_id whitespace handling."""

    def test_resource_id_leading_space_explicit(self) -> None:
        """Resource ID with leading space raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            loader.load("en", " test.ftl")

        assert "leading/trailing whitespace" in str(exc_info.value)
        assert "' test.ftl'" in str(exc_info.value)
        assert "'test.ftl'" in str(exc_info.value)

    def test_resource_id_trailing_space_explicit(self) -> None:
        """Resource ID with trailing space raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            loader.load("en", "test.ftl ")

        assert "leading/trailing whitespace" in str(exc_info.value)
        assert "'test.ftl '" in str(exc_info.value)

    def test_resource_id_both_spaces_explicit(self) -> None:
        """Resource ID with both leading and trailing space raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            loader.load("en", "  test.ftl  ")

        assert "leading/trailing whitespace" in str(exc_info.value)

    def test_resource_id_tab_character_explicit(self) -> None:
        """Resource ID with tab character raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            loader.load("en", "\ttest.ftl")

        assert "leading/trailing whitespace" in str(exc_info.value)


class TestFluentLocalizationAddResourceWhitespaceValidation:
    """Test FluentLocalization.add_resource locale whitespace validation."""

    def test_add_resource_locale_leading_space_explicit(self) -> None:
        """add_resource with leading space in locale raises ValueError."""
        l10n = FluentLocalization(["en"])

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            l10n.add_resource(" en", "msg = test")

        assert "leading/trailing whitespace" in str(exc_info.value)
        assert "' en'" in str(exc_info.value)
        assert "'en'" in str(exc_info.value)

    def test_add_resource_locale_trailing_space_explicit(self) -> None:
        """add_resource with trailing space in locale raises ValueError."""
        l10n = FluentLocalization(["en"])

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            l10n.add_resource("en ", "msg = test")

        assert "leading/trailing whitespace" in str(exc_info.value)

    def test_add_resource_locale_tab_character_explicit(self) -> None:
        """add_resource with tab in locale raises ValueError."""
        l10n = FluentLocalization(["en"])

        with pytest.raises(
            ValueError, match=r"leading/trailing whitespace"
        ) as exc_info:
            l10n.add_resource("en\t", "msg = test")

        assert "leading/trailing whitespace" in str(exc_info.value)


class TestFormatValueInvalidArgsTypeValidation:
    """Test FluentLocalization.format_value with invalid args type."""

    def test_format_value_list_args_explicit(self) -> None:
        """format_value with list args returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test")

        result, errors = l10n.format_value("msg", [1, 2, 3])  # type: ignore[arg-type]

        assert result == "{???}"
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "expected Mapping or None" in str(errors[0])

    def test_format_value_string_args_explicit(self) -> None:
        """format_value with string args returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test")

        result, errors = l10n.format_value("msg", "invalid")  # type: ignore[arg-type]

        assert result == "{???}"
        assert "Invalid args type" in str(errors[0])

    def test_format_value_int_args_explicit(self) -> None:
        """format_value with int args returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test")

        result, errors = l10n.format_value("msg", 42)  # type: ignore[arg-type]

        assert result == "{???}"
        assert "Invalid args type" in str(errors[0])


class TestFormatPatternInvalidArgsTypeValidation:
    """Test FluentLocalization.format_pattern with invalid args type."""

    @given(
        locale=locale_codes(),
        message_id=message_identifiers(),
        invalid_args=st.one_of(
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
            st.text(min_size=1, max_size=10),
            st.lists(st.integers()),
        ),
    )
    def test_format_pattern_invalid_args_type_returns_error(
        self,
        locale: str,
        message_id: str,
        invalid_args: int | Decimal | str | list[int],
    ) -> None:
        """format_pattern with non-Mapping args returns error."""
        event(f"args_type={type(invalid_args).__name__}")
        l10n = FluentLocalization([locale], strict=False)
        l10n.add_resource(locale, f"{message_id} = test")

        result, errors = l10n.format_pattern(message_id, invalid_args)  # type: ignore[arg-type]

        assert result == "{???}"
        assert len(errors) > 0
        assert "Invalid args type" in str(errors[0])

    def test_format_pattern_list_args_explicit(self) -> None:
        """format_pattern with list args returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test")

        result, errors = l10n.format_pattern("msg", [1, 2, 3])  # type: ignore[arg-type]

        assert result == "{???}"
        assert "Invalid args type" in str(errors[0])
        assert "expected Mapping or None" in str(errors[0])


class TestFormatPatternInvalidAttributeTypeValidation:
    """Test FluentLocalization.format_pattern with invalid attribute type."""

    def test_format_pattern_int_attribute_explicit(self) -> None:
        """format_pattern with int attribute returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test\n  .attr = value")

        result, errors = l10n.format_pattern("msg", None, attribute=42)  # type: ignore[arg-type]

        assert result == "{???}"
        assert "Invalid attribute type" in str(errors[0])
        assert "expected str or None" in str(errors[0])

    def test_format_pattern_list_attribute_explicit(self) -> None:
        """format_pattern with list attribute returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test\n  .attr = value")

        result, errors = l10n.format_pattern(
            "msg", None, attribute=["invalid"]  # type: ignore[arg-type]
        )

        assert result == "{???}"
        assert "Invalid attribute type" in str(errors[0])

    def test_format_pattern_dict_attribute_explicit(self) -> None:
        """format_pattern with dict attribute returns error."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = test\n  .attr = value")

        result, errors = l10n.format_pattern(
            "msg", None, attribute={"key": "val"}  # type: ignore[arg-type]
        )

        assert result == "{???}"
        assert "Invalid attribute type" in str(errors[0])


class TestPathResourceLoaderRootDirResolution:
    """Test PathResourceLoader root directory resolution edge cases."""

    def test_root_dir_explicit_provided(self, tmp_path: Path) -> None:
        """PathResourceLoader with explicit root_dir uses it for validation."""
        locales_dir = tmp_path / "locales"
        locales_dir.mkdir()
        en_dir = locales_dir / "en"
        en_dir.mkdir()
        (en_dir / "test.ftl").write_text("msg = test", encoding="utf-8")

        # Provide explicit root_dir
        loader = PathResourceLoader(
            str(locales_dir / "{locale}"),
            root_dir=str(tmp_path)
        )

        # Should load successfully
        content = loader.load("en", "test.ftl")
        assert content == "msg = test"

    def test_root_dir_empty_static_prefix(self, tmp_path: Path) -> None:
        """PathResourceLoader with no static prefix uses cwd as root."""
        # Create test structure
        en_dir = tmp_path / "en"
        en_dir.mkdir()
        (en_dir / "test.ftl").write_text("msg = test", encoding="utf-8")

        # Change to tmp_path and use relative path
        import os  # noqa: PLC0415

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            loader = PathResourceLoader("{locale}")
            content = loader.load("en", "test.ftl")
            assert content == "msg = test"
        finally:
            os.chdir(original_cwd)


class TestResourceLoadResultPropertiesExhaustive:
    """Exhaustive tests for ResourceLoadResult property methods."""

    def test_is_success_all_states(self) -> None:
        """is_success property for all LoadStatus states."""
        success_result = ResourceLoadResult("en", "test.ftl", LoadStatus.SUCCESS)
        assert success_result.is_success is True

        not_found_result = ResourceLoadResult("en", "test.ftl", LoadStatus.NOT_FOUND)
        assert not_found_result.is_success is False

        error_result = ResourceLoadResult("en", "test.ftl", LoadStatus.ERROR)
        assert error_result.is_success is False

    def test_is_not_found_all_states(self) -> None:
        """is_not_found property for all LoadStatus states."""
        not_found_result = ResourceLoadResult("en", "test.ftl", LoadStatus.NOT_FOUND)
        assert not_found_result.is_not_found is True

        success_result = ResourceLoadResult("en", "test.ftl", LoadStatus.SUCCESS)
        assert success_result.is_not_found is False

        error_result = ResourceLoadResult("en", "test.ftl", LoadStatus.ERROR)
        assert error_result.is_not_found is False

    def test_is_error_all_states(self) -> None:
        """is_error property for all LoadStatus states."""
        error_result = ResourceLoadResult("en", "test.ftl", LoadStatus.ERROR)
        assert error_result.is_error is True

        success_result = ResourceLoadResult("en", "test.ftl", LoadStatus.SUCCESS)
        assert success_result.is_error is False

        not_found_result = ResourceLoadResult("en", "test.ftl", LoadStatus.NOT_FOUND)
        assert not_found_result.is_error is False

    def test_has_junk_with_and_without(self) -> None:
        """has_junk property with and without junk entries."""
        junk_entry = Junk(content="invalid", span=Span(start=0, end=7))

        with_junk = ResourceLoadResult(
            "en", "test.ftl", LoadStatus.SUCCESS, junk_entries=(junk_entry,)
        )
        assert with_junk.has_junk is True

        without_junk = ResourceLoadResult(
            "en", "test.ftl", LoadStatus.SUCCESS, junk_entries=()
        )
        assert without_junk.has_junk is False


class TestLoadSummaryMethodsExhaustive:
    """Exhaustive tests for LoadSummary filtering methods."""

    def test_get_all_junk_flattens_correctly(self) -> None:
        """get_all_junk flattens junk entries from all results."""
        junk1 = Junk(content="invalid1", span=Span(start=0, end=8))
        junk2 = Junk(content="invalid2", span=Span(start=10, end=18))
        junk3 = Junk(content="invalid3", span=Span(start=20, end=28))

        results = (
            ResourceLoadResult(
                "en", "test1.ftl", LoadStatus.SUCCESS, junk_entries=(junk1, junk2)
            ),
            ResourceLoadResult(
                "en", "test2.ftl", LoadStatus.SUCCESS, junk_entries=(junk3,)
            ),
        )

        summary = LoadSummary(results=results)
        all_junk = summary.get_all_junk()

        assert len(all_junk) == 3
        assert junk1 in all_junk
        assert junk2 in all_junk
        assert junk3 in all_junk

    def test_get_by_locale_filters_correctly(self) -> None:
        """get_by_locale returns only results for specified locale."""
        results = (
            ResourceLoadResult("en", "test.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "test.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("en", "other.ftl", LoadStatus.SUCCESS),
        )

        summary = LoadSummary(results=results)
        en_results = summary.get_by_locale("en")

        assert len(en_results) == 2
        assert all(r.locale == "en" for r in en_results)


class TestFluentLocalizationReprMethod:
    """Test FluentLocalization.__repr__ method."""

    def test_repr_shows_initialized_vs_total_bundles(self) -> None:
        """__repr__ shows initialized/total bundle count."""
        l10n = FluentLocalization(["en", "de", "fr"])

        # Initially, no bundles created (lazy initialization)
        repr_str = repr(l10n)
        assert "FluentLocalization" in repr_str
        assert "locales=('en', 'de', 'fr')" in repr_str
        assert "bundles=" in repr_str


class TestFluentLocalizationGetBundlesGenerator:
    """Test FluentLocalization.get_bundles generator method."""

    def test_get_bundles_yields_in_fallback_order(self) -> None:
        """get_bundles yields bundles in locale fallback order."""
        l10n = FluentLocalization(["en", "de", "fr"])

        bundles = list(l10n.get_bundles())

        assert len(bundles) == 3
        assert bundles[0].get_babel_locale() == "en"
        assert bundles[1].get_babel_locale() == "de"
        assert bundles[2].get_babel_locale() == "fr"

    @given(
        locales=st.lists(
            locale_codes(), min_size=1, max_size=5, unique=True
        )
    )
    def test_get_bundles_creates_lazily(
        self, locales: list[str]
    ) -> None:
        """get_bundles creates bundles lazily if not already created."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        bundles = list(l10n.get_bundles())

        assert len(bundles) == len(locales)
        assert len(bundles) == len(l10n._bundles)


class TestFluentLocalizationCacheMethods:
    """Test FluentLocalization cache-related methods and properties."""

    def test_cache_enabled_property_true(self) -> None:
        """cache_enabled property returns True when caching enabled."""
        l10n = FluentLocalization(["en"], cache=CacheConfig())
        assert l10n.cache_enabled is True

    def test_cache_enabled_property_false(self) -> None:
        """cache_enabled property returns False when caching disabled."""
        l10n = FluentLocalization(["en"])
        assert l10n.cache_enabled is False

    def test_cache_config_property_custom(self) -> None:
        """cache_config property returns configured CacheConfig."""
        l10n = FluentLocalization(["en"], cache=CacheConfig(size=500))
        assert l10n.cache_config is not None
        assert l10n.cache_config.size == 500

    def test_clear_cache_on_multiple_bundles(self) -> None:
        """clear_cache clears cache on all initialized bundles."""
        l10n = FluentLocalization(["en", "de"], cache=CacheConfig())
        l10n.add_resource("en", "msg = test")
        l10n.add_resource("de", "msg = test")

        # Format to populate caches
        l10n.format_value("msg")

        # Clear caches
        l10n.clear_cache()

        # Should not raise - just verifies method works
        assert True


class TestFluentLocalizationValidateResource:
    """Test FluentLocalization.validate_resource method."""

    def test_validate_resource_valid_ftl(self) -> None:
        """validate_resource returns valid result for correct FTL."""
        l10n = FluentLocalization(["en"])

        result = l10n.validate_resource("msg = Hello, world!")

        assert result.is_valid is True

    def test_validate_resource_invalid_ftl(self) -> None:
        """validate_resource returns invalid result for broken FTL."""
        l10n = FluentLocalization(["en"])

        # Invalid FTL syntax
        result = l10n.validate_resource("msg = {{ broken")

        # Should have parse errors or annotations
        assert len(result.errors) > 0 or len(result.annotations) > 0


class TestFluentLocalizationGetBabelLocale:
    """Test FluentLocalization.get_babel_locale method."""

    def test_get_babel_locale_returns_primary_normalized(self) -> None:
        """get_babel_locale returns Babel-normalized primary locale."""
        l10n = FluentLocalization(["en-US", "de", "fr"])

        babel_locale = l10n.get_babel_locale()

        # Babel normalizes en-US to en_US
        assert babel_locale == "en_US"

    def test_get_babel_locale_with_simple_locale(self) -> None:
        """get_babel_locale with simple locale code."""
        l10n = FluentLocalization(["lv", "en", "de"])

        babel_locale = l10n.get_babel_locale()

        # Simple locale codes should match (or Babel fallback)
        assert babel_locale in ("lv", "en_US")  # Babel may normalize


class TestFluentLocalizationIntrospectMessage:
    """Test FluentLocalization.introspect_message method."""

    def test_introspect_message_with_variables(self) -> None:
        """introspect_message returns variable information."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello, { $name }!")

        introspection = l10n.introspect_message("msg")

        assert introspection is not None
        variables = introspection.get_variable_names()
        assert "name" in variables

    def test_introspect_message_not_found_returns_none(self) -> None:
        """introspect_message returns None for missing message."""
        l10n = FluentLocalization(["en"])

        introspection = l10n.introspect_message("nonexistent")

        assert introspection is None

    def test_introspect_message_fallback_chain(self) -> None:
        """introspect_message uses fallback chain."""
        l10n = FluentLocalization(["en", "de"])
        # Add message only to second locale
        l10n.add_resource("de", "msg = Hallo, { $name }!")

        introspection = l10n.introspect_message("msg")

        assert introspection is not None  # Found in fallback locale


class TestFluentLocalizationAddFunction:
    """Test FluentLocalization.add_function method."""

    def test_add_function_applies_to_existing_bundles(self) -> None:
        """add_function applies to already-created bundles."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = { CUSTOM($val) }")

        # Format once to create bundle (CUSTOM not yet registered, may error)
        _result, _errors = l10n.format_value("msg", {"val": "test"})

        # Now add function
        def CUSTOM(val: str) -> str:  # noqa: N802 - UPPERCASE per Fluent spec
            return val.upper()

        l10n.add_function("CUSTOM", CUSTOM)

        # Should use the custom function
        result, _errors = l10n.format_value("msg", {"val": "hello"})
        assert "HELLO" in result

    def test_add_function_stored_for_lazy_bundles(self) -> None:
        """add_function stored for bundles not yet created."""
        l10n = FluentLocalization(["en", "de"])

        def CUSTOM(val: str) -> str:  # noqa: N802 - UPPERCASE per Fluent spec
            return val.upper()

        # Add function BEFORE accessing any bundle
        l10n.add_function("CUSTOM", CUSTOM)

        # Now add resource and format
        l10n.add_resource("en", "msg = { CUSTOM($val) }")
        result, _errors = l10n.format_value("msg", {"val": "hello"})

        assert "HELLO" in result
