"""Targeted tests to achieve 100% coverage in specific modules.

Target Modules:
    - diagnostics/templates.py (lines 584-585)
    - parsing/currency.py (lines 383-392)
    - runtime/locale_context.py (lines 150, 292-295, 449, 495, 518-521)
    - syntax/serializer.py (lines 97, 173, 220-222, 266)

Property-Based Testing: Uses Hypothesis where applicable.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from babel import numbers as babel_numbers

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.parsing import parse_currency
from ftllexengine.parsing.currency import _get_currency_maps, _get_currency_pattern
from ftllexengine.runtime.locale_context import (
    _MAX_LOCALE_CACHE_SIZE,
    LocaleContext,
    _clear_locale_context_cache,
    _get_locale_context_cache_size,
)
from ftllexengine.syntax.ast import (
    Annotation,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import serialize


class TestDiagnosticsTemplatesCoverage:
    """Cover diagnostics/templates.py lines 584-585."""

    def test_parse_currency_symbol_unknown_template(self) -> None:
        """Line 584-585: ErrorTemplate.parse_currency_symbol_unknown().

        This template is used when a symbol is in the regex but not in the map.
        """
        diagnostic = ErrorTemplate.parse_currency_symbol_unknown("XYZ", "XYZ100.50")

        assert diagnostic.code == DiagnosticCode.PARSE_CURRENCY_SYMBOL_UNKNOWN
        assert "Unknown currency symbol" in diagnostic.message
        assert "XYZ" in diagnostic.message
        assert diagnostic.hint is not None


class TestParsingCurrencyCoverage:
    """Cover parsing/currency.py lines 383-392.

    The path where mapped_currency is None (symbol in regex but not in symbol_map).
    """

    def test_symbol_in_regex_but_not_in_symbol_map(self) -> None:
        """Lines 383-392: Defensive code when symbol is not in map.

        Strategy:
        1. First, ensure the pattern is built with original maps (includes €)
        2. Then patch _get_currency_maps to return maps WITHOUT €
        3. Don't rebuild the pattern - it still has € in regex
        4. When parse_currency runs, regex matches €, but map lookup fails
        """
        # Clear caches to start fresh
        _get_currency_maps.cache_clear()
        _get_currency_pattern.cache_clear()

        # Get the original maps and force pattern to be built with them
        original_symbol_map, original_ambiguous, original_locale_map, original_valid_codes = (
            _get_currency_maps()
        )

        # Build the regex pattern with original maps (includes €)
        _ = _get_currency_pattern()

        # Now create modified maps that DON'T include €
        modified_map = {k: v for k, v in original_symbol_map.items() if k != "€"}

        # Patch _get_currency_maps to return modified maps
        # BUT don't clear the pattern cache - pattern still has € in regex
        mock_return = (modified_map, original_ambiguous, original_locale_map, original_valid_codes)
        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=mock_return,
        ):
            # Now € is in the regex (built earlier) but NOT in the map (patched)
            result, errors = parse_currency("€100.50", "en_US")

            # Should return error since symbol is in regex but not in map
            assert len(errors) > 0
            assert result is None
            # Error should mention unknown symbol
            assert any("unknown" in str(e).lower() or "symbol" in str(e).lower()
                       for e in errors)

        # Clean up - restore caches
        _get_currency_maps.cache_clear()
        _get_currency_pattern.cache_clear()


class TestLocaleContextCacheLimitCoverage:
    """Cover runtime/locale_context.py line 150."""

    def test_cache_at_limit_prevents_new_entries(self) -> None:
        """Line 163-164: Cache limit LRU eviction.

        When cache size reaches _MAX_LOCALE_CACHE_SIZE, LRU entry is evicted.
        """
        # Clear cache first
        _clear_locale_context_cache()

        # Fill cache to just under limit with unique locale strings
        locales_to_fill = [f"en_TEST{i:04d}" for i in range(_MAX_LOCALE_CACHE_SIZE)]

        for locale_code in locales_to_fill:
            # These will fallback but still create entries in cache
            ctx = LocaleContext.create(locale_code)
            # Force cache population if not already done
            assert ctx is not None

        # Now cache should be at limit
        cache_size = _get_locale_context_cache_size()
        assert cache_size >= _MAX_LOCALE_CACHE_SIZE

        # Track cache size
        size_before = cache_size

        # Create one more locale - should evict LRU and add new
        ctx = LocaleContext.create("de_TESTOVERFLOW")
        assert ctx is not None

        # Cache size should not exceed maxsize
        cache_size_after = _get_locale_context_cache_size()
        assert cache_size_after <= _MAX_LOCALE_CACHE_SIZE
        # Size may stay the same or decrease slightly due to LRU eviction
        assert cache_size_after <= size_before + 1

        # Cleanup
        _clear_locale_context_cache()


class TestLocaleContextUnexpectedErrorPropagation:
    """Verify unexpected errors propagate instead of being silently caught.

    v0.28.0: Removed broad RuntimeError catches. Unexpected errors now propagate
    for debugging instead of being swallowed with a warning log.
    """

    def test_format_number_unexpected_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify RuntimeError in format_number propagates (v0.28.0 behavior)."""
        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_decimal(*_args: object, **_kwargs: object) -> str:
            msg = "Mocked RuntimeError for testing"
            raise RuntimeError(msg)

        monkeypatch.setattr(babel_numbers, "format_decimal", mock_format_decimal)

        # v0.28.0: RuntimeError now propagates instead of being caught
        with pytest.raises(RuntimeError, match="Mocked RuntimeError"):
            ctx.format_number(123.45)

    def test_format_currency_unexpected_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify RuntimeError in format_currency propagates (v0.28.0 behavior)."""
        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_currency(*_args: object, **_kwargs: object) -> str:
            msg = "Mocked RuntimeError for testing"
            raise RuntimeError(msg)

        monkeypatch.setattr(babel_numbers, "format_currency", mock_format_currency)

        # v0.28.0: RuntimeError now propagates instead of being caught
        with pytest.raises(RuntimeError, match="Mocked RuntimeError"):
            ctx.format_currency(100.0, currency="USD")


class TestLocaleContextCustomPatternCoverage:
    """Cover runtime/locale_context.py lines 449 and 495."""

    def test_format_currency_with_custom_pattern(self) -> None:
        """Line 449: Custom pattern in format_currency."""
        ctx = LocaleContext.create_or_raise("en_US")

        # Use a custom pattern that differs from default
        result = ctx.format_currency(1234.56, currency="USD", pattern="#,##0.00 \xa4")

        assert isinstance(result, str)
        # Pattern should have been applied
        assert "1,234.56" in result or "1234.56" in result

    def test_format_currency_code_display_fallback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Line 495: Fallback when pattern lacks currency placeholder.

        This covers the branch where the pattern lacks the currency placeholder
        character (U+00A4). We test this by creating a LocaleContext with a
        mock Babel locale that has a pattern without the placeholder.
        """
        # Create a mock locale with currency_formats that lacks the placeholder
        mock_locale = MagicMock()
        mock_pattern = MagicMock()
        mock_pattern.pattern = "#,##0.00"  # No currency placeholder (missing \xa4)
        mock_locale.currency_formats = {"standard": mock_pattern}

        # Create LocaleContext and bypass frozen restriction
        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale

        # Use object.__setattr__ to bypass frozen dataclass
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            with caplog.at_level(logging.DEBUG):
                result = ctx.format_currency(100.0, currency="USD", currency_display="code")

            # Should return a valid string (fallback to standard format)
            assert isinstance(result, str)

            # Should have logged debug message about missing placeholder
            assert any(
                "lacks placeholder" in record.message
                for record in caplog.records
            )
        finally:
            # Restore original
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)


class TestSerializerJunkCoverage:
    """Cover syntax/serializer.py line 97."""

    def test_serialize_junk_entry(self) -> None:
        """Line 97: Junk case branch in _serialize_entry."""
        junk = Junk(
            content="this is not valid FTL",
            annotations=(
                Annotation(code="E0003", message="Expected token: ="),
            ),
        )
        resource = Resource(entries=(junk,))

        ftl = serialize(resource)

        assert "this is not valid FTL" in ftl


class TestSerializerPlaceableCoverage:
    """Cover syntax/serializer.py lines 173 and 220-222."""

    def test_serialize_placeable_in_pattern(self) -> None:
        """Line 173: elif isinstance(element, Placeable) in _serialize_pattern.

        This is the standard path for placeables in patterns.
        """
        placeable = Placeable(expression=VariableReference(id=Identifier(name="name")))
        pattern = Pattern(elements=(TextElement(value="Hello "), placeable))
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "{ $name }" in ftl

    def test_serialize_nested_placeable(self) -> None:
        """Lines 220-222: Nested Placeable case in _serialize_expression.

        FTL spec allows { { $var } } as a nested placeable.
        """
        inner_placeable = Placeable(
            expression=VariableReference(id=Identifier(name="inner"))
        )
        outer_placeable = Placeable(expression=inner_placeable)
        pattern = Pattern(elements=(outer_placeable,))
        message = Message(
            id=Identifier(name="nested"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Should have nested braces
        assert "{ { $inner } }" in ftl


class TestSerializerNumberLiteralVariantKeyCoverage:
    """Cover syntax/serializer.py line 266."""

    def test_serialize_select_with_number_literal_key(self) -> None:
        """Line 266: NumberLiteral case in variant key serialization."""
        variant1 = Variant(
            key=NumberLiteral(value=1, raw="1"),
            value=Pattern(elements=(TextElement(value="one item"),)),
            default=False,
        )
        variant2 = Variant(
            key=NumberLiteral(value=2, raw="2"),
            value=Pattern(elements=(TextElement(value="two items"),)),
            default=False,
        )
        variant_other = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="many items"),)),
            default=True,
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(variant1, variant2, variant_other),
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="items"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Should have numeric variant keys
        assert "[1]" in ftl
        assert "[2]" in ftl
        assert "*[other]" in ftl


class TestSerializerStringLiteralEscapesCoverage:
    """Additional coverage for escape sequences in serializer."""

    def test_serialize_string_literal_with_tab(self) -> None:
        """Test tab character escaping in StringLiteral."""
        expr = StringLiteral(value="Hello\tWorld")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="tabbed"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Tab should be escaped using Unicode escape per Fluent 1.0 spec
        assert "\\u0009" in ftl

    def test_serialize_string_literal_with_newline(self) -> None:
        """Test newline character escaping in StringLiteral."""
        expr = StringLiteral(value="Line1\nLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="multiline"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Newline should be escaped as \u000A
        assert "\\u000A" in ftl

    def test_serialize_string_literal_with_carriage_return(self) -> None:
        """Test carriage return escaping in StringLiteral."""
        expr = StringLiteral(value="Line1\rLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="crlf"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # CR should be escaped as \u000D
        assert "\\u000D" in ftl


class TestLocaleContextCurrencyCodeFallback:
    """Cover runtime/locale_context.py branch 479->503.

    This branch covers the fallback when:
    1. standard_pattern is None, OR
    2. standard_pattern doesn't have a 'pattern' attribute
    """

    def test_format_currency_code_no_standard_pattern(self) -> None:
        """Branch 479->503: standard_pattern is None."""
        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale

        # Create mock with None standard pattern
        mock_locale = MagicMock()
        mock_locale.currency_formats = {"standard": None}

        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx.format_currency(100.0, currency="USD", currency_display="code")
            # Should fall through to default (line 503)
            assert isinstance(result, str)
        finally:
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)

    def test_format_currency_code_pattern_no_attr(self) -> None:
        """Branch 479->503: standard_pattern lacks 'pattern' attribute."""
        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale

        # Create mock with pattern object that has no 'pattern' attr
        mock_locale = MagicMock()
        mock_pattern = object()  # Plain object with no attributes
        mock_locale.currency_formats = {"standard": mock_pattern}

        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx.format_currency(100.0, currency="USD", currency_display="code")
            # Should fall through to default (line 503)
            assert isinstance(result, str)
        finally:
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)


class TestSerializerBranchExhaustive:
    """Exhaust all serializer branches for complete coverage.

    Targets:
    - 97->exit: Junk entry (match exits after case)
    - 173->170: Pattern loop continues after TextElement
    - 224->exit: SelectExpression (match exits after case)
    - 266->269: NumberLiteral variant key continues to serialize pattern
    """

    def test_serialize_empty_pattern(self) -> None:
        """Pattern with no elements (edge case for 173->170)."""
        pattern = Pattern(elements=())
        message = Message(
            id=Identifier(name="empty"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "empty = \n" in ftl

    def test_serialize_text_only_pattern(self) -> None:
        """Pattern with only TextElements to exercise loop continuation."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
                TextElement(value="!"),
            )
        )
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "greeting = Hello World!\n" in ftl

    def test_serialize_multiple_junk_entries(self) -> None:
        """Multiple Junk entries to fully exercise the case branch."""
        junk1 = Junk(content="bad syntax 1")
        junk2 = Junk(content="bad syntax 2")
        resource = Resource(entries=(junk1, junk2))

        ftl = serialize(resource)
        assert "bad syntax 1" in ftl
        assert "bad syntax 2" in ftl

    def test_serialize_select_number_only_variants(self) -> None:
        """Select with only NumberLiteral keys to exercise 266->269."""
        variants = (
            Variant(
                key=NumberLiteral(value=0, raw="0"),
                value=Pattern(elements=(TextElement(value="zero"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="one"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="n")),
            variants=variants,
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="count"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "[0] zero" in ftl
        assert "*[1] one" in ftl
