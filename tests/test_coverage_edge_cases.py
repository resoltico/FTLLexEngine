"""Edge case tests to achieve 100% coverage in target modules.

Target Modules:
    - diagnostics/validation.py
    - localization.py
    - parsing/dates.py
    - runtime/functions.py
    - runtime/locale_context.py
    - syntax/parser/rules.py

Coverage Focus:
    - Branch conditions not covered by main test suite
    - Error paths and fallback behaviors
    - Edge cases in format/parse logic
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from babel import Locale

from ftllexengine.diagnostics.validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from ftllexengine.localization import PathResourceLoader
from ftllexengine.parsing.dates import (
    _extract_datetime_separator,
    _tokenize_babel_pattern,
)
from ftllexengine.runtime.functions import is_builtin_with_locale_requirement
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.syntax.ast import Annotation
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import _is_variant_marker

# ============================================================================
# diagnostics/validation.py coverage
# ============================================================================


class TestValidationErrorFormat:
    """Test ValidationError.format() edge cases."""

    def test_format_with_line_but_no_column(self) -> None:
        """Line 89-92: Test formatting with line number but no column."""
        error = ValidationError(
            code="parse-error",
            message="Unexpected token",
            content="broken content",
            line=42,
            column=None,  # No column
        )
        result = error.format()
        assert "at line 42" in result
        assert "column" not in result
        assert "[parse-error]" in result

    def test_format_with_line_and_column(self) -> None:
        """Line 91-92: Test formatting with both line and column."""
        error = ValidationError(
            code="syntax-error",
            message="Missing equals",
            content="msg",
            line=10,
            column=5,
        )
        result = error.format()
        assert "at line 10, column 5" in result

    def test_format_without_location(self) -> None:
        """Line 89: Test formatting with no line number."""
        error = ValidationError(
            code="error",
            message="General error",
            content="content",
            line=None,
            column=None,
        )
        result = error.format()
        assert "at line" not in result
        assert "[error]:" in result


class TestValidationResultFormat:
    """Test ValidationResult.format() edge cases."""

    def test_format_with_errors_only(self) -> None:
        """Lines 267-270: Test formatting with errors."""
        error = ValidationError(
            code="err1",
            message="Error message",
            content="bad content",
            line=1,
        )
        result = ValidationResult(errors=(error,), warnings=(), annotations=())
        output = result.format()
        assert "Errors (1):" in output
        assert "[err1]" in output

    def test_format_with_annotations_sanitized(self) -> None:
        """Lines 273-280: Test annotation formatting with sanitization."""
        long_message = "A" * 150  # Longer than _SANITIZE_MAX_CONTENT_LENGTH
        annotation = Annotation(code="junk", message=long_message)
        result = ValidationResult(errors=(), warnings=(), annotations=(annotation,))
        output = result.format(sanitize=True)
        assert "Annotations (1):" in output
        assert "..." in output  # Truncated

    def test_format_with_annotations_not_sanitized(self) -> None:
        """Lines 273-280: Test annotation formatting without sanitization."""
        message = "Short message"
        annotation = Annotation(code="junk", message=message)
        result = ValidationResult(errors=(), warnings=(), annotations=(annotation,))
        output = result.format(sanitize=False)
        assert "Annotations (1):" in output
        assert message in output
        assert "..." not in output

    def test_format_with_warnings(self) -> None:
        """Lines 283-287: Test warning formatting."""
        warning = ValidationWarning(
            code="duplicate-id",
            message="Duplicate message ID",
            context="hello",
        )
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        output = result.format(include_warnings=True)
        assert "Warnings (1):" in output
        assert "[duplicate-id]" in output
        assert "(context: 'hello')" in output

    def test_format_with_warning_no_context(self) -> None:
        """Lines 286-287: Test warning formatting without context."""
        warning = ValidationWarning(
            code="unused",
            message="Unused message",
            context=None,
        )
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        output = result.format(include_warnings=True)
        assert "Warnings (1):" in output
        assert "()" not in output  # No context parens

    def test_format_exclude_warnings(self) -> None:
        """Lines 283: Test excluding warnings from output."""
        warning = ValidationWarning(code="warn", message="Warning", context=None)
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        output = result.format(include_warnings=False)
        assert "Warnings" not in output

    def test_format_valid_result(self) -> None:
        """Line 290: Test formatting a valid result with no issues."""
        result = ValidationResult.valid()
        output = result.format()
        assert output == "Validation passed: no errors or warnings"


# ============================================================================
# localization.py coverage
# ============================================================================


class TestPathResourceLoaderResolvedRoot:
    """Test PathResourceLoader._resolved_root caching."""

    def test_resolved_root_fallback_to_cwd(self) -> None:
        """Test fallback to cwd when no static prefix."""
        # Create loader with no static prefix in path_pattern
        # When base_path is just "{locale}", the static prefix is empty
        loader = PathResourceLoader("{locale}")
        # The _resolved_root is cached at initialization and should be cwd
        expected = Path.cwd().resolve()
        # Access via the internal cached field
        # pylint: disable=protected-access
        assert loader._resolved_root == expected


# ============================================================================
# parsing/dates.py coverage
# ============================================================================


class TestExtractDatetimeSeparator:
    """Test _extract_datetime_separator edge cases."""

    def test_none_datetime_format(self) -> None:
        """Line 293: Test when datetime_format is None."""
        # Create a mock locale with None datetime format
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        mock_locale.datetime_formats.get.return_value = None

        result = _extract_datetime_separator(mock_locale, "short")
        assert result == " "  # Default fallback

    def test_reversed_order_time_first(self) -> None:
        """Lines 316-317: Test reversed order pattern {0}<sep>{1}."""
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        # Pattern with time first: {0} then {1}
        mock_locale.datetime_formats.get.return_value = "{0} at {1}"

        result = _extract_datetime_separator(mock_locale, "short")
        assert result == " at "

    def test_no_separator_between_placeholders(self) -> None:
        """Line 322: Test when sep_start >= sep_end."""
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        # Pattern where placeholders are adjacent or overlapping
        mock_locale.datetime_formats.get.return_value = "{1}{0}"

        result = _extract_datetime_separator(mock_locale, "short")
        # When sep_start >= sep_end, it returns fallback " "
        assert result == " "


class TestTokenizeBabelPattern:
    """Test _tokenize_babel_pattern edge cases."""

    def test_quoted_section_with_escaped_quote(self) -> None:
        """Lines 457-475: Test quoted literal with escaped quotes."""
        # Pattern with 'literal ''quoted'' text'
        pattern = "'It''s a test'"
        tokens = _tokenize_babel_pattern(pattern)
        # Should contain the literal with single quote
        assert any("It's a test" in t for t in tokens)

    def test_unclosed_quoted_section(self) -> None:
        """Lines 457-475: Test unclosed quote (reaches end of pattern)."""
        pattern = "'unclosed"
        tokens = _tokenize_babel_pattern(pattern)
        # Should collect the literal chars even without closing quote
        assert any("unclosed" in t for t in tokens)


# ============================================================================
# runtime/functions.py coverage
# ============================================================================


class TestIsBuiltinWithLocaleRequirement:
    """Test is_builtin_with_locale_requirement function edge cases."""

    def test_false_when_attribute_not_set(self) -> None:
        """Line 259: Test when _ftl_requires_locale attribute is not set."""

        def plain_function() -> str:
            return "test"

        # Function without the attribute
        assert is_builtin_with_locale_requirement(plain_function) is False

    def test_false_when_attribute_is_false(self) -> None:
        """Line 259: Test when attribute is explicitly False."""

        def func_with_false() -> str:
            return "test"

        func_with_false._ftl_requires_locale = False  # type: ignore[attr-defined]
        assert is_builtin_with_locale_requirement(func_with_false) is False

    def test_false_when_attribute_is_truthy_but_not_true(self) -> None:
        """Line 259: Test when attribute is not exactly True."""

        def func_with_truthy() -> str:
            return "test"

        func_with_truthy._ftl_requires_locale = 1  # type: ignore[attr-defined]
        # Should be False because 1 is not True
        assert is_builtin_with_locale_requirement(func_with_truthy) is False


# ============================================================================
# runtime/locale_context.py coverage
# ============================================================================


class TestLocaleContextCacheRaceCondition:
    """Test LocaleContext cache race condition handling."""

    def test_cache_hit_in_double_check_pattern(self) -> None:
        """Line 172: Test cache hit during double-check locking.

        This tests the race condition where another thread populates the cache
        between the initial check and acquiring the lock.
        """
        LocaleContext.clear_cache()

        # First, create a context normally to get a valid instance
        locale_code = "en_US"
        ctx = LocaleContext.create(locale_code)

        # Clear cache and immediately re-add with lock (simulating race)
        # Access class-level cache via LocaleContext._cache and _cache_lock
        # Note: cache key is normalized to lowercase
        cache_key = locale_code.lower().replace("-", "_")
        with LocaleContext._cache_lock:
            LocaleContext._cache.clear()
            LocaleContext._cache[cache_key] = ctx

        # Now call create - should hit the cache in the double-check
        result = LocaleContext.create(locale_code)
        assert result is ctx

        LocaleContext.clear_cache()


class TestLocaleContextDatetimePattern:
    """Test LocaleContext datetime formatting edge cases."""

    def test_datetime_pattern_without_format_method(self) -> None:
        """Line 404: Test when datetime_pattern is a string without format method."""
        LocaleContext.clear_cache()

        # Create context and test formatting
        ctx = LocaleContext.create("en_US")

        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)

        # This should work and use str.format() path
        result = ctx.format_datetime(dt, date_style="short", time_style="short")
        assert result is not None
        assert len(result) > 0

        LocaleContext.clear_cache()


# ============================================================================
# syntax/parser/rules.py coverage
# ============================================================================


class TestIsVariantMarker:
    """Test _is_variant_marker edge cases."""

    def test_eof_cursor(self) -> None:
        """Line 190: Test with EOF cursor."""
        cursor = Cursor("", 0)
        assert _is_variant_marker(cursor) is False

    def test_empty_variant_key(self) -> None:
        """Line 214: Test empty [] is not a variant key."""
        cursor = Cursor("[]", 0)
        assert _is_variant_marker(cursor) is False

    def test_variant_key_followed_by_eof(self) -> None:
        """Line 224: Test variant key at end of input."""
        cursor = Cursor("[other]", 0)
        assert _is_variant_marker(cursor) is True

    def test_not_variant_marker_char(self) -> None:
        """Line 242: Test character that is neither * nor [."""
        cursor = Cursor("hello", 0)
        assert _is_variant_marker(cursor) is False

    def test_asterisk_not_followed_by_bracket(self) -> None:
        """Lines 196-197: Test * not followed by [."""
        cursor = Cursor("*other", 0)
        assert _is_variant_marker(cursor) is False

    def test_asterisk_at_eof(self) -> None:
        """Lines 196-197: Test * at EOF."""
        cursor = Cursor("*", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_invalid_char(self) -> None:
        """Lines 230-232: Test bracket with invalid variant key char."""
        cursor = Cursor("[foo bar]", 0)  # Space is invalid
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_comma(self) -> None:
        """Lines 230-232: Test bracket with comma."""
        cursor = Cursor("[a,b]", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_unclosed_at_eof(self) -> None:
        """Line 240: Test unclosed bracket at EOF."""
        cursor = Cursor("[other", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_followed_by_newline(self) -> None:
        """Line 228: Test bracket followed by newline."""
        cursor = Cursor("[other]\n", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_close_brace(self) -> None:
        """Line 228: Test bracket followed by }."""
        cursor = Cursor("[other]}", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_another_bracket(self) -> None:
        """Line 228: Test bracket followed by [."""
        cursor = Cursor("[one][two]", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_asterisk(self) -> None:
        """Line 228: Test bracket followed by *."""
        cursor = Cursor("[one]*[other]", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_text(self) -> None:
        """Line 228: Test bracket followed by regular text (not variant)."""
        cursor = Cursor("[link]text", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_whitespace_before_newline(self) -> None:
        """Lines 220-221: Test whitespace handling after bracket."""
        cursor = Cursor("[other]  \n", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_with_whitespace_and_text(self) -> None:
        """Lines 220-221: Test whitespace then text (not variant)."""
        cursor = Cursor("[other]  text", 0)
        assert _is_variant_marker(cursor) is False
