"""Hypothesis property-based tests for FluentLocalization.

Tests universal properties and invariants using property-based testing.
Validates fallback chain behavior, resource loading, and error handling.

Python 3.13+.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.localization import FluentLocalization, PathResourceLoader


# Strategies for generating test data
@st.composite
def locale_codes(draw: st.DrawFn) -> str:
    """Generate valid locale codes."""
    # Simple locale codes: 2-letter language + optional 2-letter region
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
    """Generate valid FTL message identifiers.

    Per Fluent spec, identifiers must be ASCII only: [a-zA-Z][a-zA-Z0-9_-]*
    Unicode letters are NOT valid per Fluent specification.
    """
    import string  # noqa: PLC0415 - Isolated import for Hypothesis strategy

    first_char = draw(st.sampled_from(string.ascii_letters))
    rest_chars = draw(
        st.text(
            min_size=0,
            max_size=20,
            alphabet=string.ascii_letters + string.digits + "-_",
        )
    )
    return first_char + rest_chars


class TestLocalizationUniversalProperties:
    """Test universal properties that must hold for all inputs."""

    @given(locales=st.lists(locale_codes(), min_size=1, max_size=5))
    def test_initialization_preserves_locale_order(self, locales: list[str]) -> None:
        """Locale deduplication preserves first-occurrence order (universal property)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        # Deduplication uses dict.fromkeys() to preserve insertion order
        expected = tuple(dict.fromkeys(locales))
        assert l10n.locales == expected

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3),
        message_id=message_identifiers(),
        message_value=st.text(min_size=1, max_size=100),
    )
    def test_format_value_never_crashes(
        self, locales: list[str], message_id: str, message_value: str
    ) -> None:
        """format_value never crashes (robustness property)."""
        event(f"locale_count={len(locales)}")
        event(f"value_len={len(message_value)}")
        l10n = FluentLocalization(locales)

        # Add message to first locale
        ftl_source = f"{message_id} = {message_value}"
        l10n.add_resource(locales[0], ftl_source)

        # Should never crash - always returns tuple
        result, errors = l10n.format_value(message_id)

        assert isinstance(result, str)
        assert isinstance(errors, tuple)

    @given(
        locales=st.lists(locale_codes(), min_size=2, max_size=4, unique=True),
        message_id=message_identifiers(),
    )
    def test_fallback_never_uses_later_locale_when_message_in_earlier(
        self, locales: list[str], message_id: str
    ) -> None:
        """Earlier locale takes precedence (precedence property)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        # Add unique messages to each locale
        for idx, locale in enumerate(locales):
            ftl_source = f"{message_id} = Value from locale {idx}"
            l10n.add_resource(locale, ftl_source)

        result, errors = l10n.format_value(message_id)

        assert not errors

        # Should always use first locale (index 0)
        assert result == "Value from locale 0"

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        message_id=message_identifiers(),
    )
    def test_has_message_iff_format_value_succeeds(
        self, locales: list[str], message_id: str
    ) -> None:
        """has_message() returns True iff format_value() finds message (consistency property)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        # Add message to random locale
        l10n.add_resource(locales[0], f"{message_id} = Test value")

        has_msg = l10n.has_message(message_id)
        _result, errors = l10n.format_value(message_id)

        # If has_message is True, format_value should succeed (no missing-message error)
        if has_msg:
            assert not any("not found in any locale" in str(e) for e in errors)
        else:
            # If has_message is False, format_value should fail
            assert any("not found in any locale" in str(e) for e in errors)


class TestFallbackChainProperties:
    """Test properties specific to fallback chain behavior."""

    @given(
        locales=st.lists(locale_codes(), min_size=2, max_size=5, unique=True),
        message_id=message_identifiers(),
        target_locale_idx=st.integers(min_value=0, max_value=4),
    )
    def test_fallback_uses_first_available_locale(
        self, locales: list[str], message_id: str, target_locale_idx: int
    ) -> None:
        """Fallback uses first locale in chain that has message (fallback property)."""
        # Adjust target index if it exceeds locale list
        target_locale_idx = min(target_locale_idx, len(locales) - 1)

        l10n = FluentLocalization(locales)

        # Add message ONLY to target locale (skip earlier locales)
        target_locale = locales[target_locale_idx]
        l10n.add_resource(target_locale, f"{message_id} = From {target_locale}")

        result, errors = l10n.format_value(message_id)

        # Should use target locale (first available)
        assert f"From {target_locale}" in result
        # Should not have missing-message error
        assert not any("not found in any locale" in str(e) for e in errors)

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        num_messages=st.integers(min_value=1, max_value=10),
    )
    def test_partial_translations_use_correct_fallback(
        self, locales: list[str], num_messages: int
    ) -> None:
        """Partial translations correctly fall back per message (independence property)."""
        l10n = FluentLocalization(locales)

        # Create messages: msg-0, msg-1, msg-2, ...
        message_ids = [f"msg-{i}" for i in range(num_messages)]

        # Add odd-indexed messages to first locale
        first_locale_messages = [msg for idx, msg in enumerate(message_ids) if idx % 2 == 0]
        if first_locale_messages:
            ftl_first = "\n".join(f"{msg} = First locale" for msg in first_locale_messages)
            l10n.add_resource(locales[0], ftl_first)

        # Add even-indexed messages to last locale
        if len(locales) > 1:
            last_locale_messages = [msg for idx, msg in enumerate(message_ids) if idx % 2 == 1]
            if last_locale_messages:
                ftl_last = "\n".join(f"{msg} = Last locale" for msg in last_locale_messages)
                l10n.add_resource(locales[-1], ftl_last)

        # Each message should resolve independently
        for idx, msg_id in enumerate(message_ids):
            result, errors = l10n.format_value(msg_id)

            if idx % 2 == 0:
                # Even index - should use first locale
                missing = any("not found in any locale" in str(e) for e in errors)
                assert "First locale" in result or missing
            elif len(locales) > 1:
                # Odd index - should use last locale (fallback)
                missing = any("not found in any locale" in str(e) for e in errors)
                assert "Last locale" in result or missing


class TestResourceLoaderProperties:
    """Test properties of PathResourceLoader."""

    @given(
        locale=locale_codes(),
        resource_content=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_path_loader_roundtrip(
        self, tmp_path: Path, locale: str, resource_content: str
    ) -> None:
        """PathResourceLoader roundtrip preserves content (roundtrip property)."""
        # Create locale directory
        locales_dir = tmp_path / "locales"
        locale_dir = locales_dir / locale
        locale_dir.mkdir(parents=True, exist_ok=True)

        # Write FTL content
        ftl_file = locale_dir / "test.ftl"
        ftl_file.write_text(resource_content, encoding="utf-8")

        # Load via PathResourceLoader
        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        loaded_content = loader.load(locale, "test.ftl")

        # Content should be identical
        assert loaded_content == resource_content

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        message_id=message_identifiers(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_loader_integration_deterministic(
        self, tmp_path: Path, locales: list[str], message_id: str
    ) -> None:
        """Loader integration produces deterministic results (determinism property)."""
        # Create FTL files for each locale
        locales_dir = tmp_path / "locales"
        for idx, locale in enumerate(locales):
            locale_dir = locales_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "main.ftl").write_text(
                f"{message_id} = Value {idx}", encoding="utf-8"
            )

        # Load twice - should get same result
        loader = PathResourceLoader(str(locales_dir / "{locale}"))

        l10n1 = FluentLocalization(locales, ["main.ftl"], loader)
        result1, _ = l10n1.format_value(message_id)

        l10n2 = FluentLocalization(locales, ["main.ftl"], loader)
        result2, _ = l10n2.format_value(message_id)

        assert result1 == result2  # Deterministic


class TestErrorHandlingProperties:
    """Test error handling properties."""

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        message_id=st.one_of(st.just(""), st.text(max_size=0)),
    )
    def test_empty_message_id_always_returns_fallback(
        self, locales: list[str], message_id: str
    ) -> None:
        """Empty message ID always returns fallback (error handling property)."""
        l10n = FluentLocalization(locales)

        result, errors = l10n.format_value(message_id)

        assert result == "{???}"
        assert len(errors) > 0
        assert "Empty or invalid message ID" in str(errors[0])

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        message_id=message_identifiers(),
    )
    def test_missing_message_returns_braced_id(
        self, locales: list[str], message_id: str
    ) -> None:
        """Missing message returns {message_id} (graceful degradation property)."""
        l10n = FluentLocalization(locales)
        # Don't add any resources - all messages missing

        result, errors = l10n.format_value(message_id)

        assert result == f"{{{message_id}}}"
        assert "not found in any locale" in str(errors[0])


class TestImmutabilityProperties:
    """Test immutability properties."""

    @given(locales=st.lists(locale_codes(), min_size=1, max_size=5, unique=True))
    def test_locales_property_returns_same_tuple(self, locales: list[str]) -> None:
        """locales property always returns same tuple instance (immutability property)."""
        l10n = FluentLocalization(locales)

        locales1 = l10n.locales
        locales2 = l10n.locales

        # Should be same tuple instance
        assert locales1 is locales2

    @given(
        locales=st.lists(locale_codes(), min_size=1, max_size=3, unique=True),
        message_id=message_identifiers(),
    )
    def test_format_value_does_not_modify_state(
        self, locales: list[str], message_id: str
    ) -> None:
        """format_value does not modify localization state (purity property)."""
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{message_id} = Test")

        # Call format_value multiple times
        result1, _ = l10n.format_value(message_id)
        result2, _ = l10n.format_value(message_id)
        result3, _ = l10n.format_value(message_id)

        # All results should be identical
        assert result1 == result2 == result3


class TestMetamorphicProperties:
    """Test metamorphic properties (relationships between inputs/outputs)."""

    @given(
        locales=st.lists(locale_codes(), min_size=2, max_size=4, unique=True),
        message_id=message_identifiers(),
    )
    def test_locale_order_affects_result(
        self, locales: list[str], message_id: str
    ) -> None:
        """Changing locale order changes which bundle is used (metamorphic property)."""
        # Create two localizations with reversed locale order
        l10n_forward = FluentLocalization(locales)
        l10n_reversed = FluentLocalization(list(reversed(locales)))

        # Add unique messages to first and last locale
        first_locale_msg = f"{message_id} = From {locales[0]}"
        last_locale_msg = f"{message_id} = From {locales[-1]}"

        l10n_forward.add_resource(locales[0], first_locale_msg)
        l10n_forward.add_resource(locales[-1], last_locale_msg)

        l10n_reversed.add_resource(locales[0], first_locale_msg)
        l10n_reversed.add_resource(locales[-1], last_locale_msg)

        result_forward, _ = l10n_forward.format_value(message_id)
        result_reversed, _ = l10n_reversed.format_value(message_id)

        # If locales are different, results should differ
        if len(locales) > 1:
            assert result_forward != result_reversed

    @given(
        locale=locale_codes(),
        message_id=message_identifiers(),
        value1=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=50,
        ),
        value2=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=50,
        ),
    )
    def test_add_resource_twice_uses_latest(
        self, locale: str, message_id: str, value1: str, value2: str
    ) -> None:
        """Adding resource twice uses latest value (override property)."""
        l10n = FluentLocalization([locale])

        # Add first version
        l10n.add_resource(locale, f"{message_id} = {value1}")
        result1, _ = l10n.format_value(message_id)

        # Add second version (override)
        l10n.add_resource(locale, f"{message_id} = {value2}")
        result2, _ = l10n.format_value(message_id)

        # Second call should use latest value
        # (FluentBundle.add_resource appends, so second definition wins)
        assert value1 in result1 or value2 in result1
        assert value2 in result2
