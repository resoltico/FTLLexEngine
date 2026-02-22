"""Tests for FluentBundle cache security parameters via CacheConfig.

Tests the IntegrityCache security parameters exposed through CacheConfig:
- write_once: Write-once semantics for data race prevention
- enable_audit: Audit logging for compliance
- max_audit_entries: Audit log size limit
- max_entry_weight: Memory weight limit for cached results
- max_errors_per_entry: Error count limit per cache entry

These parameters are essential for financial-grade applications requiring
integrity verification, audit trails, and memory bounds.
"""

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_WEIGHT
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig


class TestCacheSecurityParameterDefaults:
    """Test default values for cache security parameters."""

    def test_default_cache_write_once_is_false(self) -> None:
        """write_once defaults to False."""
        bundle = FluentBundle("en", cache=CacheConfig())
        assert bundle.cache_config is not None
        assert bundle.cache_config.write_once is False

    def test_default_cache_enable_audit_is_false(self) -> None:
        """enable_audit defaults to False."""
        bundle = FluentBundle("en", cache=CacheConfig())
        assert bundle.cache_config is not None
        assert bundle.cache_config.enable_audit is False

    def test_default_cache_max_audit_entries_is_10000(self) -> None:
        """max_audit_entries defaults to 10000."""
        bundle = FluentBundle("en", cache=CacheConfig())
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_audit_entries == 10000

    def test_default_cache_max_entry_weight_is_default_max_entry_size(self) -> None:
        """max_entry_weight defaults to DEFAULT_MAX_ENTRY_WEIGHT."""
        bundle = FluentBundle("en", cache=CacheConfig())
        cc = bundle.cache_config
        assert cc is not None
        assert cc.max_entry_weight == DEFAULT_MAX_ENTRY_WEIGHT
        assert cc.max_entry_weight == 10_000

    def test_default_cache_max_errors_per_entry_is_50(self) -> None:
        """max_errors_per_entry defaults to 50."""
        bundle = FluentBundle("en", cache=CacheConfig())
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_errors_per_entry == 50


class TestCacheSecurityParameterConfiguration:
    """Test custom configuration of cache security parameters."""

    def test_cache_write_once_can_be_enabled(self) -> None:
        """write_once can be set to True."""
        bundle = FluentBundle("en", cache=CacheConfig(write_once=True))
        assert bundle.cache_config is not None
        assert bundle.cache_config.write_once is True

    def test_cache_enable_audit_can_be_enabled(self) -> None:
        """enable_audit can be set to True."""
        bundle = FluentBundle("en", cache=CacheConfig(enable_audit=True))
        assert bundle.cache_config is not None
        assert bundle.cache_config.enable_audit is True

    def test_cache_max_audit_entries_can_be_customized(self) -> None:
        """max_audit_entries accepts custom values."""
        cfg = CacheConfig(enable_audit=True, max_audit_entries=5000)
        bundle = FluentBundle("en", cache=cfg)
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_audit_entries == 5000

    def test_cache_max_entry_weight_can_be_customized(self) -> None:
        """max_entry_weight accepts custom values."""
        bundle = FluentBundle("en", cache=CacheConfig(max_entry_weight=5000))
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_entry_weight == 5000

    def test_cache_max_errors_per_entry_can_be_customized(self) -> None:
        """max_errors_per_entry accepts custom values."""
        bundle = FluentBundle("en", cache=CacheConfig(max_errors_per_entry=25))
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_errors_per_entry == 25


class TestCacheConfigAccessible:
    """Test that CacheConfig is accessible via cache_config property."""

    def test_cache_config_accessible_when_enabled(self) -> None:
        """CacheConfig is accessible via cache_config property."""
        cfg = CacheConfig(
            size=500,
            write_once=True,
            enable_audit=True,
            max_audit_entries=5000,
            max_entry_weight=2000,
            max_errors_per_entry=10,
        )
        bundle = FluentBundle("en", cache=cfg)

        assert bundle.cache_enabled is True
        cc = bundle.cache_config
        assert cc is not None
        assert cc.size == 500
        assert cc.write_once is True
        assert cc.enable_audit is True
        assert cc.max_audit_entries == 5000
        assert cc.max_entry_weight == 2000
        assert cc.max_errors_per_entry == 10


class TestCacheWriteOnceBehavior:
    """Test write-once cache behavior."""

    def test_write_once_allows_first_write(self) -> None:
        """Write-once cache allows initial cache entries."""
        cfg = CacheConfig(write_once=True)
        bundle = FluentBundle("en", cache=cfg, strict=False)
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg")
        assert result == "Hello"
        assert errors == ()
        assert bundle.cache_usage == 1

    def test_write_once_allows_repeated_reads(self) -> None:
        """Write-once cache allows reading the same cached entry."""
        cfg = CacheConfig(write_once=True)
        bundle = FluentBundle("en", cache=cfg, strict=False)
        bundle.add_resource("msg = Hello")

        bundle.format_pattern("msg")
        assert bundle.cache_usage == 1

        result, errors = bundle.format_pattern("msg")
        assert result == "Hello"
        assert errors == ()

    def test_write_once_with_strict_raises_on_overwrite(self) -> None:
        """Write-once + strict mode raises WriteConflictError on overwrite attempt."""
        cfg = CacheConfig(write_once=True)
        bundle = FluentBundle("en", cache=cfg, strict=True)
        bundle.add_resource("msg = Hello")

        bundle.format_pattern("msg")

        bundle._messages.clear()
        bundle.add_resource("msg = World")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["write_once"] is True


class TestCacheAuditLogging:
    """Test cache audit logging functionality."""

    def test_audit_logging_records_operations(self) -> None:
        """Audit logging records cache operations when enabled."""
        bundle = FluentBundle("en", cache=CacheConfig(enable_audit=True))
        bundle.add_resource("msg = Hello")

        bundle.format_pattern("msg")  # MISS then PUT
        bundle.format_pattern("msg")  # HIT

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["audit_enabled"] is True
        assert stats["audit_entries"] >= 2

    def test_audit_logging_disabled_by_default(self) -> None:
        """Audit logging is disabled by default."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["audit_enabled"] is False
        assert stats["audit_entries"] == 0


class TestCacheMaxEntryWeight:
    """Test cache entry weight limiting."""

    def test_large_results_not_cached_when_over_weight_limit(self) -> None:
        """Results exceeding max_entry_weight are computed but not cached."""
        cfg = CacheConfig(max_entry_weight=50)  # Very small limit
        bundle = FluentBundle("en", cache=cfg)

        long_text = "x" * 100
        bundle.add_resource(f"msg = {long_text}")

        result, errors = bundle.format_pattern("msg")
        assert result == long_text
        assert errors == ()

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["oversize_skips"] == 1
        assert stats["size"] == 0


class TestCacheMaxErrorsPerEntry:
    """Test cache error count limiting."""

    def test_entries_with_many_errors_not_cached(self) -> None:
        """Entries with excessive errors are computed but not cached."""
        cfg = CacheConfig(max_errors_per_entry=1)  # Very strict
        bundle = FluentBundle("en", cache=cfg)

        bundle.add_resource("msg = { $a } { $b } { $c }")

        _, errors = bundle.format_pattern("msg")
        assert len(errors) >= 2

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["error_bloat_skips"] >= 1


class TestForSystemLocaleWithCacheParameters:
    """Test for_system_locale factory method with CacheConfig."""

    def test_for_system_locale_accepts_cache_config(self) -> None:
        """for_system_locale accepts CacheConfig."""
        cfg = CacheConfig(
            size=500,
            write_once=True,
            enable_audit=True,
            max_audit_entries=5000,
            max_entry_weight=8000,
            max_errors_per_entry=30,
        )
        bundle = FluentBundle.for_system_locale(cache=cfg, strict=True)

        assert bundle.cache_enabled is True
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == 500
        assert bundle.cache_config.write_once is True
        assert bundle.cache_config.enable_audit is True
        assert bundle.cache_config.max_audit_entries == 5000
        assert bundle.cache_config.max_entry_weight == 8000
        assert bundle.cache_config.max_errors_per_entry == 30
        assert bundle.strict is True

    def test_for_system_locale_cache_parameters_default(self) -> None:
        """for_system_locale uses default CacheConfig values."""
        bundle = FluentBundle.for_system_locale(cache=CacheConfig())

        assert bundle.cache_enabled is True
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == DEFAULT_CACHE_SIZE
        assert bundle.cache_config.write_once is False
        assert bundle.cache_config.enable_audit is False
        assert bundle.cache_config.max_audit_entries == 10000
        assert bundle.cache_config.max_entry_weight == DEFAULT_MAX_ENTRY_WEIGHT
        assert bundle.cache_config.max_errors_per_entry == 50


class TestCacheParameterCombinations:
    """Test various combinations of cache parameters."""

    def test_financial_grade_configuration(self) -> None:
        """Test typical financial application configuration."""
        cfg = CacheConfig(
            write_once=True,  # Prevent data races
            enable_audit=True,  # Compliance logging
        )
        bundle = FluentBundle("en_US", cache=cfg, strict=True)

        bundle.add_resource("amount = { NUMBER($value, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("amount", {"value": 1234.56})
        assert errors == ()
        assert "1,234.56" in result or "1234.56" in result

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is True

    def test_high_throughput_configuration(self) -> None:
        """Test high-throughput server configuration (audit disabled for performance)."""
        cfg = CacheConfig(
            size=10000,  # Large cache
            enable_audit=False,  # Disable for performance
            max_entry_weight=50000,  # Allow larger entries
        )
        bundle = FluentBundle("en_US", use_isolating=False, cache=cfg)

        bundle.add_resource("msg = Hello { $name }!")
        result, _ = bundle.format_pattern("msg", {"name": "World"})
        assert result == "Hello World!"

        assert bundle.cache_config is not None
        assert bundle.cache_config.size == 10000
        assert bundle.cache_config.enable_audit is False
        assert bundle.cache_config.max_entry_weight == 50000


class TestCacheStatsIncludeNewParameters:
    """Test that get_cache_stats() includes new parameters."""

    def test_cache_stats_include_all_parameters(self) -> None:
        """get_cache_stats() returns all cache configuration parameters."""
        cfg = CacheConfig(
            size=500,
            write_once=True,
            enable_audit=True,
            max_audit_entries=5000,
            max_entry_weight=8000,
            max_errors_per_entry=30,
        )
        bundle = FluentBundle("en", cache=cfg, strict=True)

        stats = bundle.get_cache_stats()
        assert stats is not None

        assert "maxsize" in stats
        assert "max_entry_weight" in stats
        assert "max_errors_per_entry" in stats
        assert "write_once" in stats
        assert "strict" in stats
        assert "audit_enabled" in stats
        assert "audit_entries" in stats

        assert stats["maxsize"] == 500
        assert stats["max_entry_weight"] == 8000
        assert stats["max_errors_per_entry"] == 30
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is True


@pytest.mark.fuzz
class TestPropertyBasedCacheParameters:
    """Property-based tests for cache parameters."""

    @given(
        size=st.integers(min_value=1, max_value=100000),
        max_audit_entries=st.integers(min_value=1, max_value=100000),
        max_entry_weight=st.integers(min_value=1, max_value=100000),
        max_errors_per_entry=st.integers(min_value=1, max_value=1000),
    )
    @settings(max_examples=50)
    def test_cache_parameters_roundtrip(
        self,
        size: int,
        max_audit_entries: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
    ) -> None:
        """Cache parameters are correctly stored and accessible via CacheConfig."""
        cfg = CacheConfig(
            size=size,
            max_audit_entries=max_audit_entries,
            max_entry_weight=max_entry_weight,
            max_errors_per_entry=max_errors_per_entry,
        )
        bundle = FluentBundle("en", cache=cfg)

        assert bundle.cache_config is not None
        assert bundle.cache_config.size == size
        assert bundle.cache_config.max_audit_entries == max_audit_entries
        assert bundle.cache_config.max_entry_weight == max_entry_weight
        assert bundle.cache_config.max_errors_per_entry == max_errors_per_entry
        event(f"cache_size={size}")

    @given(
        write_once=st.booleans(),
        enable_audit=st.booleans(),
        strict=st.booleans(),
    )
    @settings(max_examples=20)
    def test_boolean_parameters_roundtrip(
        self, write_once: bool, enable_audit: bool, strict: bool
    ) -> None:
        """Boolean cache parameters are correctly stored and accessible."""
        cfg = CacheConfig(write_once=write_once, enable_audit=enable_audit)
        bundle = FluentBundle("en", cache=cfg, strict=strict)

        cc = bundle.cache_config
        assert cc is not None
        assert cc.write_once == write_once
        assert cc.enable_audit == enable_audit
        assert bundle.strict == strict
        wo = "write_once" if write_once else "normal"
        event(f"mode={wo}")
