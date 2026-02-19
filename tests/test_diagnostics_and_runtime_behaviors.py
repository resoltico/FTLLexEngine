"""Edge case tests for diagnostics, localization, parsing, and runtime modules.

Tests:
- ValidationError.format() with line/column combinations
- ValidationResult.format() with errors, warnings, and annotations
- PathResourceLoader._resolved_root cwd fallback
- _extract_datetime_separator for None formats, reversed order, and adjacent placeholders
- _tokenize_babel_pattern for escaped quotes and unclosed quoted sections
- is_builtin_with_locale_requirement attribute checks
- LocaleContext cache double-check locking behavior
- LocaleContext datetime formatting
- _is_variant_marker at various cursor positions
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


class TestValidationErrorFormat:
    """ValidationError.format() with varying location information."""

    def test_format_with_line_but_no_column(self) -> None:
        """Format with line number but no column omits 'column' from output."""
        error = ValidationError(
            code="parse-error",
            message="Unexpected token",
            content="broken content",
            line=42,
            column=None,
        )
        result = error.format()
        assert "at line 42" in result
        assert "column" not in result
        assert "[parse-error]" in result

    def test_format_with_line_and_column(self) -> None:
        """Format with both line and column includes both in output."""
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
        """Format without any location omits the 'at line' phrase."""
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
    """ValidationResult.format() with errors, warnings, and annotations."""

    def test_format_with_errors_only(self) -> None:
        """Errors section appears in formatted output with correct count."""
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
        """Long annotation messages are truncated when sanitize=True."""
        long_message = "A" * 150
        annotation = Annotation(code="junk", message=long_message)
        result = ValidationResult(errors=(), warnings=(), annotations=(annotation,))
        output = result.format(sanitize=True)
        assert "Annotations (1):" in output
        assert "..." in output

    def test_format_with_annotations_not_sanitized(self) -> None:
        """Short annotation messages are not truncated when sanitize=False."""
        message = "Short message"
        annotation = Annotation(code="junk", message=message)
        result = ValidationResult(errors=(), warnings=(), annotations=(annotation,))
        output = result.format(sanitize=False)
        assert "Annotations (1):" in output
        assert message in output
        assert "..." not in output

    def test_format_with_warnings(self) -> None:
        """Warnings section appears with context when include_warnings=True."""
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
        """Warning without context does not include empty parentheses."""
        warning = ValidationWarning(
            code="unused",
            message="Unused message",
            context=None,
        )
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        output = result.format(include_warnings=True)
        assert "Warnings (1):" in output
        assert "()" not in output

    def test_format_exclude_warnings(self) -> None:
        """Warnings section is omitted when include_warnings=False."""
        warning = ValidationWarning(code="warn", message="Warning", context=None)
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        output = result.format(include_warnings=False)
        assert "Warnings" not in output

    def test_format_valid_result(self) -> None:
        """Valid result formats as a single success message."""
        result = ValidationResult.valid()
        output = result.format()
        assert output == "Validation passed: no errors or warnings"


class TestPathResourceLoaderResolvedRoot:
    """PathResourceLoader._resolved_root falls back to cwd when no static prefix."""

    def test_resolved_root_fallback_to_cwd(self) -> None:
        """Pattern with no static path prefix resolves root to current working directory."""
        loader = PathResourceLoader("{locale}")
        expected = Path.cwd().resolve()
        assert loader._resolved_root == expected  # pylint: disable=protected-access


class TestExtractDatetimeSeparator:
    """_extract_datetime_separator handles None formats, reversed order, and empty separators."""

    def test_none_datetime_format(self) -> None:
        """None datetime_format falls back to default separator ' ' with date-first order."""
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        mock_locale.datetime_formats.get.return_value = None

        separator, is_time_first = _extract_datetime_separator(mock_locale, "short")
        assert separator == " "
        assert is_time_first is False

    def test_reversed_order_time_first(self) -> None:
        """Pattern {0} before {1} indicates time-first ordering."""
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{0} at {1}"

        separator, is_time_first = _extract_datetime_separator(mock_locale, "short")
        assert separator == " at "
        assert is_time_first is True

    def test_no_separator_between_placeholders(self) -> None:
        """Adjacent placeholders {1}{0} produce fallback separator ' '."""
        mock_locale = MagicMock(spec=Locale)
        mock_locale.datetime_formats = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{1}{0}"

        separator, is_time_first = _extract_datetime_separator(mock_locale, "short")
        assert separator == " "
        assert is_time_first is False


class TestTokenizeBabelPattern:
    """_tokenize_babel_pattern handles quoted literals and edge cases."""

    def test_quoted_section_with_escaped_quote(self) -> None:
        """Escaped quote '' inside a quoted literal is unescaped to a single quote."""
        pattern = "'It''s a test'"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("It's a test" in t for t in tokens)

    def test_unclosed_quoted_section(self) -> None:
        """Unclosed quoted literal collects remaining characters."""
        pattern = "'unclosed"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("unclosed" in t for t in tokens)


class TestIsBuiltinWithLocaleRequirement:
    """is_builtin_with_locale_requirement checks the _ftl_requires_locale attribute."""

    def test_false_when_attribute_not_set(self) -> None:
        """Returns False for functions that lack the _ftl_requires_locale attribute."""

        def plain_function() -> str:
            return "test"

        assert is_builtin_with_locale_requirement(plain_function) is False

    def test_false_when_attribute_is_false(self) -> None:
        """Returns False when _ftl_requires_locale is explicitly False."""

        def func_with_false() -> str:
            return "test"

        func_with_false._ftl_requires_locale = False  # type: ignore[attr-defined]
        assert is_builtin_with_locale_requirement(func_with_false) is False

    def test_false_when_attribute_is_truthy_but_not_true(self) -> None:
        """Returns False when _ftl_requires_locale is truthy but not exactly True."""

        def func_with_truthy() -> str:
            return "test"

        func_with_truthy._ftl_requires_locale = 1  # type: ignore[attr-defined]
        assert is_builtin_with_locale_requirement(func_with_truthy) is False


class TestLocaleContextCacheRaceCondition:
    """LocaleContext cache handles the double-check locking pattern."""

    def test_cache_hit_in_double_check_pattern(self) -> None:
        """Cache hit during the inner lock check returns the cached instance."""
        LocaleContext.clear_cache()

        locale_code = "en_US"
        ctx = LocaleContext.create(locale_code)

        cache_key = locale_code.lower().replace("-", "_")
        with LocaleContext._cache_lock:  # pylint: disable=protected-access
            LocaleContext._cache.clear()  # pylint: disable=protected-access
            LocaleContext._cache[cache_key] = ctx  # pylint: disable=protected-access

        result = LocaleContext.create(locale_code)
        assert result is ctx

        LocaleContext.clear_cache()


class TestLocaleContextDatetimePattern:
    """LocaleContext formats datetime values using the locale's pattern."""

    def test_datetime_pattern_without_format_method(self) -> None:
        """format_datetime uses str.format() path when pattern is a plain string."""
        LocaleContext.clear_cache()

        ctx = LocaleContext.create("en_US")
        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)

        result = ctx.format_datetime(dt, date_style="short", time_style="short")
        assert result is not None
        assert len(result) > 0

        LocaleContext.clear_cache()


class TestIsVariantMarker:
    """_is_variant_marker detects *[key] and [key] patterns at cursor position."""

    def test_eof_cursor(self) -> None:
        """Empty source at position 0 is not a variant marker."""
        cursor = Cursor("", 0)
        assert _is_variant_marker(cursor) is False

    def test_empty_variant_key(self) -> None:
        """[] with no key content is not a variant marker."""
        cursor = Cursor("[]", 0)
        assert _is_variant_marker(cursor) is False

    def test_variant_key_followed_by_eof(self) -> None:
        """[other] at end of input is a valid variant marker."""
        cursor = Cursor("[other]", 0)
        assert _is_variant_marker(cursor) is True

    def test_not_variant_marker_char(self) -> None:
        """Non-bracket, non-asterisk character is not a variant marker."""
        cursor = Cursor("hello", 0)
        assert _is_variant_marker(cursor) is False

    def test_asterisk_not_followed_by_bracket(self) -> None:
        """* not followed by [ is not a variant marker."""
        cursor = Cursor("*other", 0)
        assert _is_variant_marker(cursor) is False

    def test_asterisk_at_eof(self) -> None:
        """* at EOF is not a variant marker."""
        cursor = Cursor("*", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_invalid_char(self) -> None:
        """[key with space] is not a variant marker (space is invalid in key)."""
        cursor = Cursor("[foo bar]", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_comma(self) -> None:
        """[a,b] is not a variant marker (comma is invalid in key)."""
        cursor = Cursor("[a,b]", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_unclosed_at_eof(self) -> None:
        """[other without closing bracket is not a variant marker."""
        cursor = Cursor("[other", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_followed_by_newline(self) -> None:
        """[other] followed by newline is a valid variant marker."""
        cursor = Cursor("[other]\n", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_close_brace(self) -> None:
        """[other] followed by } is a valid variant marker."""
        cursor = Cursor("[other]}", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_another_bracket(self) -> None:
        """[one][two] - first bracket expression is a valid variant marker."""
        cursor = Cursor("[one][two]", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_asterisk(self) -> None:
        """[one]*[other] - bracket expression followed by * is a valid variant marker."""
        cursor = Cursor("[one]*[other]", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_followed_by_text(self) -> None:
        """[link]text - bracket expression followed by regular text is not a variant marker."""
        cursor = Cursor("[link]text", 0)
        assert _is_variant_marker(cursor) is False

    def test_bracket_with_whitespace_before_newline(self) -> None:
        """[other]  \\n - trailing whitespace before newline is accepted."""
        cursor = Cursor("[other]  \n", 0)
        assert _is_variant_marker(cursor) is True

    def test_bracket_with_whitespace_and_text(self) -> None:
        """[other]  text - whitespace then text after bracket is not a variant marker."""
        cursor = Cursor("[other]  text", 0)
        assert _is_variant_marker(cursor) is False
