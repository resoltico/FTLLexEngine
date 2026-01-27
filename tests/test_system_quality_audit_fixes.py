"""Tests for system quality audit fixes.

Tests for:
- AUDIT-009: ASCII-only locale validation
- AUDIT-011: Chain depth validation
- AUDIT-012: Overwrite warning in add_resource
- AUDIT-013: Cache max_entry_weight parameter
"""

from __future__ import annotations

import logging

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.constants import DEFAULT_MAX_ENTRY_SIZE, MAX_DEPTH
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.validation import validate_resource

# ============================================================================
# AUDIT-009: ASCII-only locale validation
# ============================================================================


class TestLocaleValidationAsciiOnly:
    """Test ASCII-only locale code validation (AUDIT-009).

    Locale codes must contain only ASCII alphanumeric characters with
    underscore or hyphen separators. Non-ASCII characters (e.g., accented
    letters) are rejected to ensure BCP 47 compliance.
    """

    def test_valid_ascii_locales_accepted(self) -> None:
        """Valid ASCII locale codes are accepted."""
        valid_locales = [
            "en",
            "en_US",
            "en-US",
            "de_DE",
            "lv_LV",
            "zh_Hans_CN",
            "pt_BR",
            "ja_JP",
            "ar_EG",
        ]
        for locale in valid_locales:
            bundle = FluentBundle(locale)
            assert bundle.locale == locale

    def test_unicode_locale_rejected(self) -> None:
        """Locale codes with non-ASCII characters are rejected."""
        invalid_locales = [
            "\xe9_FR",  # e with acute accent (e_FR with accented e)
            "\u65e5\u672c\u8a9e",  # Japanese characters
            "en_\xfc",  # u with umlaut
            "\xe4\xf6\xfc",  # German umlauts
        ]
        for locale in invalid_locales:
            with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
                FluentBundle(locale)

    def test_empty_locale_rejected(self) -> None:
        """Empty locale code is rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FluentBundle("")

    def test_invalid_format_rejected(self) -> None:
        """Invalid locale code formats are rejected."""
        invalid_formats = [
            "_en",  # Leading separator
            "en_",  # Trailing separator
            "en__US",  # Double separator
            "en US",  # Space separator
            "en.US",  # Dot separator
            "en@US",  # At sign
        ]
        for locale in invalid_formats:
            with pytest.raises(ValueError, match="Invalid locale code format"):
                FluentBundle(locale)

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_ascii_alphanumeric_accepted(self, locale: str) -> None:
        """PROPERTY: Pure ASCII alphanumeric strings are valid locales."""
        bundle = FluentBundle(locale)
        assert bundle.locale == locale


# ============================================================================
# AUDIT-011: Chain depth validation
# ============================================================================


class TestValidationChainDepth:
    """Test reference chain depth validation (AUDIT-011).

    Validation now detects reference chains that exceed MAX_DEPTH and would
    fail at runtime with MAX_DEPTH_EXCEEDED.
    """

    def test_short_chain_no_warning(self) -> None:
        """Short reference chains produce no warning."""
        # Chain of 5 messages
        messages = [
            "msg-0 = Base value",
            "msg-1 = { msg-0 }",
            "msg-2 = { msg-1 }",
            "msg-3 = { msg-2 }",
            "msg-4 = { msg-3 }",
        ]
        ftl_source = "\n".join(messages)

        result = validate_resource(ftl_source)
        chain_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0

    def test_chain_at_max_depth_no_warning(self) -> None:
        """Chain exactly at MAX_DEPTH produces no warning."""
        # Build chain of exactly MAX_DEPTH messages
        messages = ["msg-0 = Base value"]
        for i in range(1, MAX_DEPTH):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        result = validate_resource(ftl_source)
        chain_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        assert len(chain_warnings) == 0

    def test_chain_exceeding_max_depth_warning(self) -> None:
        """Chain exceeding MAX_DEPTH produces warning."""
        # Build chain of MAX_DEPTH + 10 messages
        chain_length = MAX_DEPTH + 10
        messages = ["msg-0 = Base value"]
        for i in range(1, chain_length):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        result = validate_resource(ftl_source)
        chain_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        assert len(chain_warnings) >= 1
        assert "exceeds maximum" in chain_warnings[0].message
        assert "MAX_DEPTH_EXCEEDED" in chain_warnings[0].message

    def test_chain_warning_runtime_confirmation(self) -> None:
        """Chains that produce warnings actually fail at runtime."""
        # Build chain exceeding MAX_DEPTH
        chain_length = MAX_DEPTH + 50
        messages = ["msg-0 = Base value"]
        for i in range(1, chain_length):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        # Validation warns
        result = validate_resource(ftl_source)
        chain_warnings = [
            w for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
        ]
        # VAL-REDUNDANT-REPORTS-001: Reports ALL chains exceeding max_depth
        assert len(chain_warnings) >= 1

        # Runtime fails
        bundle = FluentBundle("en")
        bundle.add_resource(ftl_source)
        _, errors = bundle.format_value(f"msg-{chain_length - 1}")
        depth_errors = [
            e for e in errors
            if "MAX_DEPTH_EXCEEDED" in str(e)
        ]
        assert len(depth_errors) > 0


# ============================================================================
# AUDIT-012: Overwrite warning in add_resource
# ============================================================================


class TestBundleOverwriteWarning:
    """Test overwrite warning in add_resource (AUDIT-012).

    When a message or term is overwritten by a later definition,
    a WARNING-level log is emitted for observability.
    """

    def test_message_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a message logs a warning."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("greeting = Goodbye")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing message 'greeting'" in msg for msg in warning_messages)

    def test_term_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a term logs a warning."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("-brand = Acme")
            bundle.add_resource("-brand = NewCorp")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing term '-brand'" in msg for msg in warning_messages)

    def test_no_warning_for_new_entries(self, caplog: pytest.LogCaptureFixture) -> None:
        """No overwrite warning for new entries."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("farewell = Goodbye")

        overwrite_warnings = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING and "Overwriting" in record.message
        ]
        assert len(overwrite_warnings) == 0

    def test_last_write_wins_behavior_preserved(self) -> None:
        """Last Write Wins behavior is preserved despite warning."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = First")
        bundle.add_resource("greeting = Second")
        bundle.add_resource("greeting = Third")

        result, _ = bundle.format_value("greeting")
        assert result == "Third"


# ============================================================================
# AUDIT-013: Cache max_entry_weight parameter
# ============================================================================


class TestCacheEntrySizeLimit:
    """Test cache max_entry_weight parameter (AUDIT-013).

    The FormatCache now supports a max_entry_weight parameter that prevents
    caching of very large formatted results to avoid memory exhaustion.
    """

    def test_default_max_entry_weight(self) -> None:
        """Default max_entry_weight is 10_000 characters."""
        cache = IntegrityCache(strict=False, )
        assert cache.max_entry_weight == DEFAULT_MAX_ENTRY_SIZE
        assert cache.max_entry_weight == 10_000

    def test_custom_max_entry_weight(self) -> None:
        """Custom max_entry_weight is respected."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)
        assert cache.max_entry_weight == 1000

    def test_invalid_max_entry_weight_rejected(self) -> None:
        """Invalid max_entry_weight values are rejected."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=0)

        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=-1)

    def test_small_entries_cached(self) -> None:
        """Entries below max_entry_weight are cached."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)

        # Small result (100 chars)
        cache.put("msg", None, None, "en", True, "x" * 100, ())

        assert cache.size == 1
        assert cache.oversize_skips == 0

        # Retrieve
        cached = cache.get("msg", None, None, "en", True)
        assert cached is not None
        assert cached.to_tuple() == ("x" * 100, ())

    def test_large_entries_not_cached(self) -> None:
        """Entries exceeding max_entry_weight are not cached."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        # Large result (200 chars)
        cache.put("msg", None, None, "en", True, "x" * 200, ())

        assert cache.size == 0
        assert cache.oversize_skips == 1

        # Cannot retrieve (not cached)
        cached = cache.get("msg", None, None, "en", True)
        assert cached is None

    def test_boundary_entry_size(self) -> None:
        """Entry exactly at max_entry_weight is cached."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        # Entry exactly at limit
        cache.put("msg", None, None, "en", True, "x" * 100, ())

        assert cache.size == 1
        assert cache.oversize_skips == 0

    def test_get_stats_includes_oversize_skips(self) -> None:
        """get_stats() includes oversize_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        # Add some large entries
        for i in range(5):
            cache.put(f"msg-{i}", None, None, "en", True, "x" * 100, ())

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 5
        assert stats["max_entry_weight"] == 50
        assert stats["size"] == 0

    def test_clear_resets_oversize_skips(self) -> None:
        """clear() resets oversize_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        cache.put("msg", None, None, "en", True, "x" * 100, ())
        assert cache.oversize_skips == 1

        cache.clear()
        assert cache.oversize_skips == 0

    def test_bundle_cache_uses_default_max_entry_weight(self) -> None:
        """FluentBundle's internal cache uses default max_entry_weight."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = { $data }")

        # Format with small data
        small_data = "x" * 100
        bundle.format_value("msg", {"data": small_data})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

    @given(st.integers(min_value=1, max_value=1000))
    @settings(max_examples=20)
    def test_max_entry_weight_property(self, size: int) -> None:
        """PROPERTY: max_entry_weight is correctly stored and returned."""
        cache = IntegrityCache(strict=False, max_entry_weight=size)
        assert cache.max_entry_weight == size


# ============================================================================
# Integration Tests
# ============================================================================


class TestAuditFixesIntegration:
    """Integration tests combining multiple audit fixes."""

    def test_validation_and_runtime_consistency(self) -> None:
        """Validation warnings predict runtime failures."""
        # Create a chain just over MAX_DEPTH
        chain_length = MAX_DEPTH + 5
        messages = ["msg-0 = Base"]
        for i in range(1, chain_length):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        # Validation catches the issue
        result = validate_resource(ftl_source)
        has_chain_warning = any(
            w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name
            for w in result.warnings
        )
        assert has_chain_warning

        # Runtime confirms the issue
        bundle = FluentBundle("en")
        bundle.add_resource(ftl_source)
        _, errors = bundle.format_value(f"msg-{chain_length - 1}")
        has_depth_error = any("MAX_DEPTH_EXCEEDED" in str(e) for e in errors)
        assert has_depth_error

    def test_locale_validation_before_resource_loading(self) -> None:
        """Locale validation happens before resource loading."""
        with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
            FluentBundle("\xe9_FR")
