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
from tests.strategies.localization import locale_chains, message_ids


class TestLocalizationUniversalProperties:
    """Test universal properties that must hold for all inputs."""

    @given(locales=locale_chains(min_size=1, max_size=5))
    def test_initialization_preserves_locale_order(
        self, locales: list[str],
    ) -> None:
        """Locale deduplication preserves first-occurrence order."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        expected = tuple(dict.fromkeys(locales))
        assert l10n.locales == expected

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
        message_value=st.text(min_size=1, max_size=100),
    )
    def test_format_value_never_crashes(
        self,
        locales: list[str],
        message_id: str,
        message_value: str,
    ) -> None:
        """format_value never crashes (robustness property)."""
        event(f"locale_count={len(locales)}")
        val_class = (
            "short" if len(message_value) <= 10
            else "medium" if len(message_value) <= 50
            else "long"
        )
        event(f"value_len={val_class}")
        l10n = FluentLocalization(locales)

        ftl_source = f"{message_id} = {message_value}"
        l10n.add_resource(locales[0], ftl_source)

        result, errors = l10n.format_value(message_id)
        assert isinstance(result, str)
        assert isinstance(errors, tuple)

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        message_id=message_ids(),
    )
    def test_fallback_never_uses_later_locale_when_earlier_has_msg(
        self, locales: list[str], message_id: str,
    ) -> None:
        """Earlier locale takes precedence (precedence property)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        for idx, locale in enumerate(locales):
            ftl_source = f"{message_id} = Value from locale {idx}"
            l10n.add_resource(locale, ftl_source)

        result, errors = l10n.format_value(message_id)
        assert not errors
        assert result == "Value from locale 0"

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
    )
    def test_has_message_iff_format_value_succeeds(
        self, locales: list[str], message_id: str,
    ) -> None:
        """has_message True iff format_value finds message."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{message_id} = Test value")

        has_msg = l10n.has_message(message_id)
        _result, errors = l10n.format_value(message_id)

        if has_msg:
            not_found = any(
                "not found in any locale" in str(e) for e in errors
            )
            assert not not_found
        else:
            found = any(
                "not found in any locale" in str(e) for e in errors
            )
            assert found


class TestFallbackChainProperties:
    """Test properties specific to fallback chain behavior."""

    @given(
        locales=locale_chains(min_size=2, max_size=5),
        message_id=message_ids(),
        target_locale_idx=st.integers(min_value=0, max_value=4),
    )
    def test_fallback_uses_first_available_locale(
        self,
        locales: list[str],
        message_id: str,
        target_locale_idx: int,
    ) -> None:
        """Fallback uses first locale in chain that has message."""
        target_locale_idx = min(target_locale_idx, len(locales) - 1)
        event(f"target_idx={target_locale_idx}")

        l10n = FluentLocalization(locales)
        target_locale = locales[target_locale_idx]
        l10n.add_resource(
            target_locale, f"{message_id} = From {target_locale}",
        )

        result, errors = l10n.format_value(message_id)
        assert f"From {target_locale}" in result
        not_found = any(
            "not found in any locale" in str(e) for e in errors
        )
        assert not not_found

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        num_messages=st.integers(min_value=1, max_value=10),
    )
    def test_partial_translations_use_correct_fallback(
        self, locales: list[str], num_messages: int,
    ) -> None:
        """Partial translations correctly fall back per message."""
        event(f"num_messages={num_messages}")
        has_fallback = len(locales) > 1
        event(f"has_fallback={has_fallback}")
        l10n = FluentLocalization(locales)

        message_ids_list = [f"msg-{i}" for i in range(num_messages)]

        first_locale_msgs = [
            msg for idx, msg in enumerate(message_ids_list) if idx % 2 == 0
        ]
        if first_locale_msgs:
            ftl = "\n".join(
                f"{msg} = First locale" for msg in first_locale_msgs
            )
            l10n.add_resource(locales[0], ftl)

        if has_fallback:
            last_locale_msgs = [
                msg for idx, msg in enumerate(message_ids_list)
                if idx % 2 == 1
            ]
            if last_locale_msgs:
                ftl = "\n".join(
                    f"{msg} = Last locale" for msg in last_locale_msgs
                )
                l10n.add_resource(locales[-1], ftl)

        for idx, msg_id in enumerate(message_ids_list):
            result, errors = l10n.format_value(msg_id)
            missing = any(
                "not found in any locale" in str(e) for e in errors
            )
            if idx % 2 == 0:
                assert "First locale" in result or missing
            elif has_fallback:
                assert "Last locale" in result or missing


class TestResourceLoaderProperties:
    """Test properties of PathResourceLoader."""

    @given(
        locale=st.sampled_from(["en", "de", "fr", "es", "ja"]),
        resource_content=st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_path_loader_roundtrip(
        self,
        tmp_path: Path,
        locale: str,
        resource_content: str,
    ) -> None:
        """PathResourceLoader roundtrip preserves content."""
        event(f"locale={locale}")
        content_len = (
            "short" if len(resource_content) <= 20
            else "medium" if len(resource_content) <= 100
            else "long"
        )
        event(f"content_len={content_len}")

        locales_dir = tmp_path / "locales"
        locale_dir = locales_dir / locale
        locale_dir.mkdir(parents=True, exist_ok=True)

        ftl_file = locale_dir / "test.ftl"
        ftl_file.write_text(resource_content, encoding="utf-8")

        loader = PathResourceLoader(str(locales_dir / "{locale}"))
        loaded = loader.load(locale, "test.ftl")
        assert loaded == resource_content

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_loader_integration_deterministic(
        self,
        tmp_path: Path,
        locales: list[str],
        message_id: str,
    ) -> None:
        """Loader integration produces deterministic results."""
        event(f"locale_count={len(locales)}")

        locales_dir = tmp_path / "locales"
        for idx, locale in enumerate(locales):
            locale_dir = locales_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "main.ftl").write_text(
                f"{message_id} = Value {idx}", encoding="utf-8",
            )

        loader = PathResourceLoader(str(locales_dir / "{locale}"))

        l10n1 = FluentLocalization(locales, ["main.ftl"], loader)
        result1, _ = l10n1.format_value(message_id)

        l10n2 = FluentLocalization(locales, ["main.ftl"], loader)
        result2, _ = l10n2.format_value(message_id)

        assert result1 == result2


class TestErrorHandlingProperties:
    """Test error handling properties."""

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=st.just(""),
    )
    def test_empty_message_id_always_returns_fallback(
        self, locales: list[str], message_id: str,
    ) -> None:
        """Empty message ID always returns fallback."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        result, errors = l10n.format_value(message_id)
        assert result == "{???}"
        assert len(errors) > 0
        assert "Empty or invalid message ID" in str(errors[0])

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
    )
    def test_missing_message_returns_braced_id(
        self, locales: list[str], message_id: str,
    ) -> None:
        """Missing message returns {message_id} (graceful degradation)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        result, errors = l10n.format_value(message_id)
        assert result == f"{{{message_id}}}"
        assert "not found in any locale" in str(errors[0])


class TestImmutabilityProperties:
    """Test immutability properties."""

    @given(
        locales=locale_chains(min_size=1, max_size=5),
    )
    def test_locales_property_returns_same_tuple(
        self, locales: list[str],
    ) -> None:
        """locales property always returns same tuple instance."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)

        locales1 = l10n.locales
        locales2 = l10n.locales
        assert locales1 is locales2

    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
    )
    def test_format_value_does_not_modify_state(
        self, locales: list[str], message_id: str,
    ) -> None:
        """format_value does not modify localization state (purity)."""
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(locales)
        l10n.add_resource(locales[0], f"{message_id} = Test")

        result1, _ = l10n.format_value(message_id)
        result2, _ = l10n.format_value(message_id)
        result3, _ = l10n.format_value(message_id)

        assert result1 == result2 == result3


class TestMetamorphicProperties:
    """Test metamorphic properties (relationships between inputs/outputs)."""

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        message_id=message_ids(),
    )
    def test_locale_order_affects_result(
        self, locales: list[str], message_id: str,
    ) -> None:
        """Changing locale order changes which bundle is used."""
        event(f"locale_count={len(locales)}")

        l10n_forward = FluentLocalization(locales)
        l10n_reversed = FluentLocalization(list(reversed(locales)))

        first_msg = f"{message_id} = From {locales[0]}"
        last_msg = f"{message_id} = From {locales[-1]}"

        l10n_forward.add_resource(locales[0], first_msg)
        l10n_forward.add_resource(locales[-1], last_msg)

        l10n_reversed.add_resource(locales[0], first_msg)
        l10n_reversed.add_resource(locales[-1], last_msg)

        result_forward, _ = l10n_forward.format_value(message_id)
        result_reversed, _ = l10n_reversed.format_value(message_id)

        if len(locales) > 1:
            assert result_forward != result_reversed

    @given(
        locales=locale_chains(min_size=1, max_size=1),
        message_id=message_ids(),
        value1=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1, max_size=50,
        ),
        value2=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1, max_size=50,
        ),
    )
    def test_add_resource_twice_uses_latest(
        self,
        locales: list[str],
        message_id: str,
        value1: str,
        value2: str,
    ) -> None:
        """Adding resource twice uses latest value (override property)."""
        event("outcome=override")
        locale = locales[0]
        l10n = FluentLocalization([locale])

        l10n.add_resource(locale, f"{message_id} = {value1}")
        result1, _ = l10n.format_value(message_id)

        l10n.add_resource(locale, f"{message_id} = {value2}")
        result2, _ = l10n.format_value(message_id)

        assert value1 in result1 or value2 in result1
        assert value2 in result2
