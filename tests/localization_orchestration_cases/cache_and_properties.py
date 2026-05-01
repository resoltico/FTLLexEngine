# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.localization import (
    CacheAuditLogEntry,
    FluentLocalization,
    PathResourceLoader,
)
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from tests.strategies.localization import locale_chains, message_ids


class TestCacheStatsBranch:
    """Tests for get_cache_stats aggregation branch."""

    def test_aggregates_across_multiple_bundles(self) -> None:
        """get_cache_stats sums metrics across all bundles."""
        l10n = FluentLocalization(
            ["en", "de"], cache=CacheConfig(size=500),
        )
        l10n.add_resource("en", "msg = Hello\n")
        l10n.add_resource("de", "msg = Hallo\n")

        # Format to create cache entries
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == 2
        assert stats["maxsize"] == 1000  # 500 * 2

    def test_empty_bundles_returns_zero_stats(self) -> None:
        """get_cache_stats returns zero stats with no initialized bundles."""
        l10n = FluentLocalization(["en"], cache=CacheConfig())
        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == 0
        assert stats["size"] == 0

    def test_hit_rate_calculated_correctly(self) -> None:
        """Hit rate is hits/(hits+misses)*100."""
        l10n = FluentLocalization(["en"], cache=CacheConfig())
        l10n.add_resource("en", "msg = Hello\n")
        l10n.format_value("msg")  # miss
        l10n.format_value("msg")  # hit
        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 50.0

    def test_skips_bundle_with_no_cache(self) -> None:
        """Bundles returning None from get_cache_stats are skipped."""
        l10n = FluentLocalization(
            ["en", "de"], cache=CacheConfig(size=100),
        )
        # Create cached bundle for "en"
        l10n.add_resource("en", "msg = Hello\n")
        l10n.format_value("msg")

        # Inject a no-cache bundle for "de" directly
        no_cache_bundle = FluentBundle("de")
        no_cache_bundle.add_resource("msg = Hallo\n")
        l10n._bundles["de"] = no_cache_bundle

        stats = l10n.get_cache_stats()
        assert stats is not None
        # Only "en" bundle contributes stats
        assert stats["bundle_count"] == 2
        assert stats["maxsize"] == 100  # Only en's maxsize

class TestCacheAuditLogBranch:
    """Tests for get_cache_audit_log per-locale audit access."""

    def test_returns_none_when_caching_disabled(self) -> None:
        """get_cache_audit_log() returns None when localization caching is disabled."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello\n")

        assert l10n.get_cache_audit_log() is None

    def test_returns_empty_mapping_when_no_bundles_initialized(self) -> None:
        """get_cache_audit_log() does not create bundles during inspection."""
        l10n = FluentLocalization(["en", "de"], cache=CacheConfig(enable_audit=True))

        audit_logs = l10n.get_cache_audit_log()
        assert audit_logs == {}

    def test_returns_per_locale_write_log_entries(self) -> None:
        """get_cache_audit_log() returns immutable CacheAuditLogEntry tuples per locale."""
        l10n = FluentLocalization(["en", "de"], cache=CacheConfig(enable_audit=True))
        l10n.add_resource("en", "msg = Hello\n")
        l10n.add_resource("de", "msg = Hallo\n")

        l10n.format_value("msg")
        l10n.format_value("msg")

        audit_logs = l10n.get_cache_audit_log()
        assert audit_logs is not None
        assert list(audit_logs) == ["en", "de"]
        assert [entry.operation for entry in audit_logs["en"]] == ["MISS", "PUT", "HIT"]
        assert audit_logs["de"] == ()
        assert all(isinstance(entry, CacheAuditLogEntry) for entry in audit_logs["en"])

    @given(enable_audit=st.booleans(), locales=locale_chains(min_size=1, max_size=3))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_property_audit_log_tracks_initialized_locales(
        self, enable_audit: bool, locales: list[str]
    ) -> None:
        """PROPERTY: get_cache_audit_log() uses canonical locale keys."""
        l10n = FluentLocalization(locales, cache=CacheConfig(enable_audit=enable_audit))
        for locale in locales:
            l10n.add_resource(locale, "msg = Hello\n")

        l10n.format_value("msg")

        audit_logs = l10n.get_cache_audit_log()
        assert audit_logs is not None
        normalized_locales = [normalize_locale(locale) for locale in locales]
        assert list(audit_logs) == normalized_locales

        event(f"audit={'enabled' if enable_audit else 'disabled'}")
        event(f"locale_count={len(locales)}")

        if enable_audit:
            assert len(audit_logs[normalized_locales[0]]) >= 2
            assert all(
                isinstance(entry, CacheAuditLogEntry)
                for entry in audit_logs[normalized_locales[0]]
            )
        else:
            assert all(log == () for log in audit_logs.values())

class TestFormatPattern:
    """Tests for format_pattern fallback chain edge cases."""

    def test_format_pattern_not_found_returns_braced_id(self) -> None:
        """format_pattern returns {message_id} when not found in any locale."""
        l10n = FluentLocalization(["en", "de"], strict=False)
        result, errors = l10n.format_pattern("missing")
        assert result == "{missing}"
        assert len(errors) == 1

    def test_format_pattern_primary_locale_skips_fallback_callback(
        self,
    ) -> None:
        """format_pattern does not invoke on_fallback for primary locale."""
        from ftllexengine.localization import FallbackInfo
        events: list[FallbackInfo] = []
        l10n = FluentLocalization(
            ["en", "de"], on_fallback=events.append,
            use_isolating=False,
        )
        l10n.add_resource("en", "msg = Primary")
        result, errors = l10n.format_pattern("msg")
        assert result == "Primary"
        assert errors == ()
        assert len(events) == 0

class TestRepr:
    """Tests for __repr__ format."""

    def test_includes_locales_and_bundle_count(self) -> None:
        """__repr__ shows locales and initialized/total bundles."""
        l10n = FluentLocalization(["en", "de"])
        r = repr(l10n)
        assert "FluentLocalization" in r
        assert "locales=('en', 'de')" in r
        assert "bundles=0/2" in r

    def test_bundle_count_updates_after_access(self) -> None:
        """__repr__ bundle count reflects initialized bundles."""
        l10n = FluentLocalization(["en", "de"])
        l10n.add_resource("en", "msg = test")
        r = repr(l10n)
        assert "bundles=1/2" in r

class TestOrchestrationProperties:
    """Property-based tests for orchestration invariants.

    Standard @given tests with bounded strategies. Run in CI (no fuzz marker).
    """

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
        """format_value never crashes regardless of input (robustness)."""
        event(f"locale_count={len(locales)}")
        val_class = (
            "short" if len(message_value) <= 10
            else "medium" if len(message_value) <= 50
            else "long"
        )
        event(f"value_len={val_class}")
        l10n = FluentLocalization(locales, strict=False)
        ftl_source = f"{message_id} = {message_value}"
        l10n.add_resource(locales[0], ftl_source)
        result, errors = l10n.format_value(message_id)
        assert isinstance(result, str)
        assert isinstance(errors, tuple)

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
        """Fallback resolves from first locale in chain that has message."""
        idx = min(target_locale_idx, len(locales) - 1)
        event(f"target_idx={idx}")
        l10n = FluentLocalization(locales)
        target_locale = locales[idx]
        l10n.add_resource(
            target_locale, f"{message_id} = From {target_locale}",
        )
        result, errors = l10n.format_value(message_id)
        assert f"From {target_locale}" in result
        assert not any(
            "not found in any locale" in str(e) for e in errors
        )

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
        l10n = FluentLocalization(locales, strict=False)

        msg_ids = [f"msg-{i}" for i in range(num_messages)]

        first_msgs = [m for i, m in enumerate(msg_ids) if i % 2 == 0]
        if first_msgs:
            ftl = "\n".join(f"{m} = First locale" for m in first_msgs)
            l10n.add_resource(locales[0], ftl)

        if has_fallback:
            last_msgs = [
                m for i, m in enumerate(msg_ids) if i % 2 == 1
            ]
            if last_msgs:
                ftl = "\n".join(
                    f"{m} = Last locale" for m in last_msgs
                )
                l10n.add_resource(locales[-1], ftl)

        for idx, mid in enumerate(msg_ids):
            result, errors = l10n.format_value(mid)
            missing = any(
                "not found in any locale" in str(e)
                for e in errors
            )
            if idx % 2 == 0:
                assert "First locale" in result or missing
            elif has_fallback:
                assert "Last locale" in result or missing

    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        locales=locale_chains(min_size=1, max_size=3),
        message_id=message_ids(),
    )
    def test_loader_integration_deterministic(
        self,
        tmp_path: Path,
        locales: list[str],
        message_id: str,
    ) -> None:
        """Loader integration produces identical results across instances."""
        event(f"locale_count={len(locales)}")
        locales_dir = tmp_path / "locales"
        for idx, locale in enumerate(locales):
            locale_dir = locales_dir / normalize_locale(locale)
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

    @given(
        locales=locale_chains(min_size=2, max_size=4),
        message_id=message_ids(),
    )
    def test_locale_order_affects_resolution(
        self, locales: list[str], message_id: str,
    ) -> None:
        """Reversing locale order changes which bundle resolves message."""
        event(f"locale_count={len(locales)}")
        l10n_fwd = FluentLocalization(locales)
        l10n_rev = FluentLocalization(list(reversed(locales)))

        first_msg = f"{message_id} = From {locales[0]}"
        last_msg = f"{message_id} = From {locales[-1]}"

        l10n_fwd.add_resource(locales[0], first_msg)
        l10n_fwd.add_resource(locales[-1], last_msg)

        l10n_rev.add_resource(locales[0], first_msg)
        l10n_rev.add_resource(locales[-1], last_msg)

        result_fwd, _ = l10n_fwd.format_value(message_id)
        result_rev, _ = l10n_rev.format_value(message_id)

        if len(locales) > 1:
            assert result_fwd != result_rev

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
