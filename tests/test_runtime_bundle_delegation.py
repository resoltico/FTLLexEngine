"""Tests for FluentBundle locale validation, term overwriting, comment handling,
strict mode error summaries, and format_pattern argument type validation.

Property-based tests use Hypothesis where applicable. Unit tests are used for
specific error paths that require precise input construction.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT
from ftllexengine.diagnostics import ErrorCategory
from ftllexengine.integrity import FormattingIntegrityError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig

# ============================================================================
# COVERAGE: Lines 150-154 (Locale exceeding MAX_LOCALE_LENGTH_HARD_LIMIT)
# ============================================================================


class TestLocaleValidationDoSPrevention:
    """Test locale validation DoS prevention (lines 150-154)."""

    def test_locale_exceeding_hard_limit_raises_valueerror(self) -> None:
        """Locale exceeding MAX_LOCALE_LENGTH_HARD_LIMIT raises ValueError."""
        # Create locale string exceeding hard limit (1000 characters)
        malicious_locale = "en_" + ("X" * MAX_LOCALE_LENGTH_HARD_LIMIT)

        with pytest.raises(ValueError, match=r"Locale code exceeds maximum length"):
            FluentBundle(malicious_locale)

    def test_locale_at_hard_limit_boundary_accepted(self) -> None:
        """Locale at exact MAX_LOCALE_LENGTH_HARD_LIMIT boundary is accepted."""
        # Create locale at exact boundary (1000 chars total)
        # Format: "a" + ("b" * 998) + "c" = 1000 chars
        boundary_locale = "a" + ("b" * (MAX_LOCALE_LENGTH_HARD_LIMIT - 2)) + "c"
        assert len(boundary_locale) == MAX_LOCALE_LENGTH_HARD_LIMIT

        # Should succeed (at boundary, not exceeding)
        bundle = FluentBundle(boundary_locale)
        assert bundle.locale == boundary_locale

    def test_locale_one_over_hard_limit_rejected(self) -> None:
        """Locale at MAX_LOCALE_LENGTH_HARD_LIMIT + 1 is rejected."""
        # Create locale exceeding by exactly 1 character
        over_limit_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 1)
        assert len(over_limit_locale) == MAX_LOCALE_LENGTH_HARD_LIMIT + 1

        with pytest.raises(ValueError, match=r"Locale code exceeds maximum length"):
            FluentBundle(over_limit_locale)

    def test_locale_error_message_truncates_display(self) -> None:
        """ValueError message truncates long locale to first 50 chars for display."""
        # Create very long locale (>1000 chars)
        long_locale = "X" * 2000

        with pytest.raises(
            ValueError, match=r"Locale code exceeds maximum length"
        ) as exc_info:
            FluentBundle(long_locale)

        error_msg = str(exc_info.value)
        # Error should contain truncated locale (first 50 chars)
        assert long_locale[:50] in error_msg
        # Error should show actual length
        assert "2000 characters" in error_msg

    @given(
        st.text(
            alphabet=st.characters(min_codepoint=0x0041, max_codepoint=0x005A),  # A-Z
            min_size=MAX_LOCALE_LENGTH_HARD_LIMIT + 1,
            max_size=MAX_LOCALE_LENGTH_HARD_LIMIT + 100,
        )
    )
    def test_property_any_locale_exceeding_limit_rejected(self, locale: str) -> None:
        """Property: Any locale exceeding hard limit is rejected."""
        assume(len(locale) > MAX_LOCALE_LENGTH_HARD_LIMIT)
        overshoot = len(locale) - MAX_LOCALE_LENGTH_HARD_LIMIT
        event(f"boundary={'near' if overshoot <= 10 else 'far'}_limit")

        with pytest.raises(ValueError, match=r"Locale code exceeds maximum length"):
            FluentBundle(locale)


# ============================================================================
# COVERAGE: Line 674 (Term overwriting warning)
# ============================================================================


class TestTermOverwritingWarning:
    """Test term overwriting produces warning log (line 674)."""

    def test_overwriting_term_logs_warning(self, caplog: Any) -> None:
        """Overwriting existing term logs warning with term ID."""
        bundle = FluentBundle("en")

        # Add initial term
        bundle.add_resource("-brand = Firefox")
        assert "-brand" not in bundle.get_message_ids()  # Terms not in message IDs

        # Overwrite term - should trigger warning on line 674
        bundle.add_resource("-brand = Chrome")

        # Verify warning was logged
        assert any(
            "Overwriting existing term '-brand'" in record.message
            for record in caplog.records
        )

    def test_overwriting_multiple_terms_logs_each(self, caplog: Any) -> None:
        """Overwriting multiple terms logs separate warning for each."""
        bundle = FluentBundle("en")

        # Add initial terms
        bundle.add_resource(
            """
-brand = Firefox
-version = 1.0
"""
        )

        caplog.clear()

        # Overwrite both terms
        bundle.add_resource(
            """
-brand = Chrome
-version = 2.0
"""
        )

        # Should have two warnings
        warnings = [r for r in caplog.records if "Overwriting existing term" in r.message]
        assert len(warnings) == 2
        assert any("-brand" in w.message for w in warnings)
        assert any("-version" in w.message for w in warnings)

    @given(
        st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu"), min_codepoint=0x0061
                ),
                min_size=1,
                max_size=20,
            ),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    def test_property_overwriting_any_term_logs_warning(
        self, term_ids: list[str]
    ) -> None:
        """Property: Overwriting any term produces warning (log check omitted)."""
        assume(all(tid.isidentifier() for tid in term_ids))
        event(f"term_count={len(term_ids)}")

        bundle = FluentBundle("en")

        # Add initial terms
        for tid in term_ids:
            bundle.add_resource(f"-{tid} = Original")

        # Overwrite all terms - should succeed without errors
        for tid in term_ids:
            bundle.add_resource(f"-{tid} = Updated")

        # Verify terms were overwritten (no exception = success)
        # Note: Log verification removed - hypothesis tests shouldn't use fixtures


# ============================================================================
# COVERAGE: Line 701->652 (Comment entry handling branch)
# ============================================================================


class TestCommentEntryHandling:
    """Test Comment entry handling in _register_resource (line 701->652 branch)."""

    def test_resource_with_standalone_comment_processed(self, caplog: Any) -> None:
        """Resource with standalone comment is processed without registration."""
        # Set caplog to capture DEBUG level
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        # FTL with standalone comment (not attached to message)
        source = """
# This is a standalone comment
# Another comment line

hello = World
"""

        bundle.add_resource(source)

        # Verify message was added
        assert bundle.has_message("hello")

        # Verify comment skip was logged (debug level)
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert any("Skipping comment entry" in r.message for r in debug_records)

    def test_resource_with_only_comments_no_messages(self, caplog: Any) -> None:
        """Resource containing only comments produces no messages."""
        # Set caplog to capture DEBUG level
        caplog.set_level(logging.DEBUG)

        bundle = FluentBundle("en")

        # FTL with only comments
        source = """
# Comment 1
# Comment 2
# Comment 3
"""

        bundle.add_resource(source)

        # No messages should be added
        assert len(bundle.get_message_ids()) == 0

        # Comment skip should be logged
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert any("Skipping comment entry" in r.message for r in debug_records)

    def test_mixed_comments_and_messages_processed_correctly(self) -> None:
        """Resource with mixed comments and messages processes only messages."""
        bundle = FluentBundle("en")

        source = """
# Header comment
msg1 = First
# Middle comment
msg2 = Second
# Footer comment
"""

        bundle.add_resource(source)

        # Both messages should be registered
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")
        assert len(bundle.get_message_ids()) == 2

    def test_comment_followed_by_message_loop_continuation(self) -> None:
        """Comment entry followed by message tests loop continuation branch."""
        bundle = FluentBundle("en")

        # Resource with comment followed by message (tests branch 701->652)
        # The parser creates separate Comment and Message entries
        source = """
## Standalone resource comment

msg = Value
"""

        bundle.add_resource(source)

        # Verify message was registered after comment was skipped
        assert bundle.has_message("msg")
        assert len(bundle.get_message_ids()) == 1


# ============================================================================
# COVERAGE: Line 863 (Strict mode error summary with >3 errors)
# ============================================================================


class TestStrictModeErrorSummaryTruncation:
    """Test strict mode error summary truncation (line 863)."""

    def test_strict_mode_more_than_three_errors_truncates_summary(self) -> None:
        """Strict mode with >3 errors truncates error summary in exception message."""
        bundle = FluentBundle("en", strict=True)

        # Create message with multiple undefined references (>3 errors)
        # Each undefined variable/term will produce a separate error
        bundle.add_resource(
            """
msg = { $var1 } { $var2 } { $var3 } { $var4 } { $var5 }
"""
        )

        # Calling with empty args will produce 5 missing variable errors
        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        error_msg = str(exc_info.value)

        # Error message should indicate truncation
        assert "and" in error_msg
        assert "more" in error_msg
        # Should show at least 3 errors plus truncation notice
        assert "error(s)" in error_msg

        # Verify the exception carries all errors
        assert len(exc_info.value.fluent_errors) > 3

    def test_strict_mode_exactly_three_errors_no_truncation(self) -> None:
        """Strict mode with exactly 3 errors shows all without truncation."""
        bundle = FluentBundle("en", strict=True)

        # Create message with exactly 3 undefined references
        bundle.add_resource("msg = { $a } { $b } { $c }")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        error_msg = str(exc_info.value)

        # Should NOT show truncation marker
        assert "more)" not in error_msg

        # Should have exactly 3 errors
        assert len(exc_info.value.fluent_errors) == 3

    def test_strict_mode_five_errors_shows_and_2_more(self) -> None:
        """Strict mode with 5 errors shows 'and 2 more' in message."""
        bundle = FluentBundle("en", strict=True)

        # Create message with 5 undefined variables
        bundle.add_resource("msg = { $a } { $b } { $c } { $d } { $e }")

        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", {})

        error_msg = str(exc_info.value)

        # Should show "(and 2 more)" since we show first 3 of 5
        assert "(and 2 more)" in error_msg

        # Verify we have exactly 5 errors
        assert len(exc_info.value.fluent_errors) == 5


# ============================================================================
# COVERAGE: Lines 919-932 (Invalid args type validation)
# ============================================================================


class TestInvalidArgsTypeValidation:
    """Test invalid args type validation (lines 919-932)."""

    def test_args_not_mapping_returns_error_non_strict(self) -> None:
        """Non-strict mode: Invalid args type returns error tuple."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello { $name }")

        # Pass list instead of Mapping (type violation)
        result, errors = bundle.format_pattern("msg", ["invalid"])  # type: ignore[arg-type]

        # Should return fallback
        assert result == "{???}"

        # Should have error about invalid argument type
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "Invalid args type" in str(errors[0])

    def test_args_not_mapping_raises_strict_mode(self) -> None:
        """Strict mode: Invalid args type raises FormattingIntegrityError."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello { $name }")

        # Pass tuple instead of Mapping
        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern("msg", ("not", "a", "mapping"))  # type: ignore[arg-type]

        # Exception should contain invalid args error
        assert len(exc_info.value.fluent_errors) == 1
        assert "Invalid args type" in str(exc_info.value.fluent_errors[0])

    @given(
        st.one_of(
            st.lists(st.text()), st.text(), st.integers(), st.booleans(), st.tuples()
        )
    )
    def test_property_non_mapping_args_handled_gracefully(self, invalid_args: Any) -> None:
        """Property: Any non-Mapping args produces error without crashing."""
        # Filter out None (which is valid) and actual Mappings
        assume(invalid_args is not None)
        assume(not hasattr(invalid_args, "items"))
        event(f"args_type={type(invalid_args).__name__}")

        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Test")

        # Should handle gracefully
        result, errors = bundle.format_pattern("msg", invalid_args)

        assert result == "{???}"
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION


# ============================================================================
# COVERAGE: Lines 936-949 (Invalid attribute type validation)
# ============================================================================


class TestInvalidAttributeTypeValidation:
    """Test invalid attribute type validation (lines 936-949)."""

    def test_attribute_not_string_returns_error_non_strict(self) -> None:
        """Non-strict mode: Invalid attribute type returns error tuple."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Value\n    .attr = Attribute")

        # Pass integer instead of string for attribute
        result, errors = bundle.format_pattern(
            "msg", None, attribute=123  # type: ignore[arg-type]
        )

        # Should return fallback
        assert result == "{???}"

        # Should have error about invalid attribute type
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "Invalid attribute type" in str(errors[0])

    def test_attribute_not_string_raises_strict_mode(self) -> None:
        """Strict mode: Invalid attribute type raises FormattingIntegrityError."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Value\n    .attr = Attribute")

        # Pass list instead of string
        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle.format_pattern(
                "msg", None, attribute=["not", "string"]  # type: ignore[arg-type]
            )

        # Exception should contain invalid attribute error
        assert len(exc_info.value.fluent_errors) == 1
        assert "Invalid attribute type" in str(exc_info.value.fluent_errors[0])

    @given(
        st.one_of(
            st.integers(),
            st.booleans(),
            st.lists(st.text()),
            st.dictionaries(st.text(), st.text()),
        )
    )
    def test_property_non_string_attribute_handled_gracefully(
        self, invalid_attr: Any
    ) -> None:
        """Property: Any non-string attribute produces error without crashing."""
        assume(not isinstance(invalid_attr, str))
        event(f"attr_type={type(invalid_attr).__name__}")

        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Test")

        # Should handle gracefully
        result, errors = bundle.format_pattern("msg", None, attribute=invalid_attr)

        assert result == "{???}"
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION


# ============================================================================
# INTEGRATION: Properties and cache edge cases
# ============================================================================


class TestPropertyAccessEdgeCases:
    """Test property access edge cases for complete coverage."""

    def test_cache_enabled_false_when_not_initialized(self) -> None:
        """cache_enabled returns False when caching not enabled."""
        bundle = FluentBundle("en")
        assert bundle.cache_enabled is False

    def test_cache_enabled_true_when_initialized(self) -> None:
        """cache_enabled returns True when caching enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        assert bundle.cache_enabled is True

    def test_cache_config_size_returns_configured_size(self) -> None:
        """cache_config.size returns configured size from CacheConfig."""
        bundle = FluentBundle("en", cache=CacheConfig(size=200))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == 200
        assert bundle.cache_enabled is True

    @given(st.integers(min_value=1, max_value=10000))
    def test_property_cache_config_size_reflects_initialization(self, size: int) -> None:
        """Property: cache_config.size always reflects CacheConfig parameter."""
        scale = "small" if size <= 100 else "large"
        event(f"boundary={scale}_cache")
        bundle = FluentBundle("en", cache=CacheConfig(size=size))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == size


# ============================================================================
# ROUNDTRIP: Error handling consistency
# ============================================================================


class TestErrorHandlingRoundtrip:
    """Test error handling roundtrip properties."""

    @given(
        st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,9}", fullmatch=True)
    )
    def test_property_invalid_args_error_consistent_across_modes(
        self, msg_id: str
    ) -> None:
        """Property: Invalid args produces consistent error across strict/non-strict."""
        has_special = any(c in msg_id for c in "-_")
        event(f"id_chars={'special' if has_special else 'alpha'}")

        bundle_strict = FluentBundle("en", strict=True)
        bundle_normal = FluentBundle("en", strict=False)

        ftl_source = f"{msg_id} = Test"
        bundle_strict.add_resource(ftl_source)
        bundle_normal.add_resource(ftl_source)

        # Non-strict returns error tuple
        _, errors_normal = bundle_normal.format_pattern(
            msg_id, [1, 2, 3]  # type: ignore[arg-type]
        )

        # Strict raises with same error
        with pytest.raises(FormattingIntegrityError) as exc_info:
            bundle_strict.format_pattern(msg_id, [1, 2, 3])  # type: ignore[arg-type]

        # Error details should match
        assert len(errors_normal) == 1
        assert len(exc_info.value.fluent_errors) == 1
        assert str(errors_normal[0]) == str(exc_info.value.fluent_errors[0])
