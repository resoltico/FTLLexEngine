"""End-to-end tests for parse->format workflow integration.

Tests the complete pipeline from FTL source to formatted output:
- Parse FTL source with parse_ftl()
- Add to FluentBundle via add_resource()
- Format with format_pattern()
- Verify round-trip produces expected results

These tests validate that parsing and formatting work together correctly
as an integrated system, not just as isolated components.

Note: "Bidirectional" refers to the two-way workflow (parse->format), not
bidirectional text handling or currency/number parsing from strings.

Structure:
    - TestParseFormatBasic: Essential round-trip tests (run in every CI build)
    - TestParseFormatWithVariables: Variable interpolation round-trips
    - TestParseFormatSelectExpressions: Select expression round-trips
    - TestParseFormatReferences: Message/term reference round-trips
    - TestParseFormatEdgeCases: Edge cases and unicode handling
    - TestParseFormatWithFunctions: Built-in function integration
    - TestParseFormatErrorHandling: Error paths in integration
    - TestParseFormatIntrospection: Introspection API integration
    - TestParseFormatValidation: Validation API integration
    - TestParseFormatWithCache: Caching behavior integration
    - TestParseFormatIsolation: Unicode isolation mark behavior
    - TestSerializeParseRoundtrip: AST serialization round-trips
    - TestMultiModuleIntegration: parse->validate->serialize->introspect pipeline
    - TestValidationRuntimeConsistency: validation warnings predict runtime failures
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ftllexengine import (
    FluentBundle,
    parse_ftl,
    serialize_ftl,
)
from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.introspection import introspect_message
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax.ast import Junk, Message, NumberLiteral, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from ftllexengine.validation.resource import validate_resource

# =============================================================================
# Essential Parse->Format Tests (Run in every CI build)
# =============================================================================


class TestParseFormatBasic:
    """Essential tests for parse->format round-trip."""

    def test_simple_message_roundtrip(self) -> None:
        """Simple message parses and formats correctly."""
        ftl_source = "hello = Hello, World!"

        # Verify parsing produces valid AST
        resource = parse_ftl(ftl_source)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

        # Verify formatting produces expected output
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("hello")
        assert result == "Hello, World!"
        assert len(errors) == 0

    def test_multiple_messages_roundtrip(self) -> None:
        """Multiple messages parse and format correctly."""
        ftl_source = """
msg1 = First message
msg2 = Second message
msg3 = Third message
"""
        # Verify parsing
        resource = parse_ftl(ftl_source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 3

        # Verify formatting
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result1, _ = bundle.format_pattern("msg1")
        result2, _ = bundle.format_pattern("msg2")
        result3, _ = bundle.format_pattern("msg3")

        assert result1 == "First message"
        assert result2 == "Second message"
        assert result3 == "Third message"

    def test_multiline_pattern_roundtrip(self) -> None:
        """Multiline patterns parse and format correctly."""
        ftl_source = """
multi = First line
    Second line
    Third line
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("multi")
        assert "First line" in result
        assert "Second line" in result
        assert "Third line" in result
        assert len(errors) == 0

    def test_message_with_attribute_roundtrip(self) -> None:
        """Messages with attributes parse and format correctly."""
        ftl_source = """
button = Click here
    .accesskey = C
    .title = Submit form
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        # Format main value
        result, _ = bundle.format_pattern("button")
        assert result == "Click here"

        # Format attributes using the attribute parameter
        accesskey, _ = bundle.format_pattern("button", attribute="accesskey")
        title, _ = bundle.format_pattern("button", attribute="title")

        assert accesskey == "C"
        assert title == "Submit form"

    def test_term_roundtrip(self) -> None:
        """Terms parse and format correctly."""
        ftl_source = """
-brand = Firefox
-version = 120.0
about = { -brand } v{ -version }
"""
        resource = parse_ftl(ftl_source)
        terms = [e for e in resource.entries if isinstance(e, Term)]
        assert len(terms) == 2

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("about")
        assert result == "Firefox v120.0"


class TestParseFormatWithVariables:
    """Tests for parse->format with variable interpolation."""

    def test_single_variable_roundtrip(self) -> None:
        """Single variable interpolation works correctly."""
        ftl_source = "greeting = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("greeting", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert len(errors) == 0

    def test_multiple_variables_roundtrip(self) -> None:
        """Multiple variables interpolate correctly."""
        ftl_source = "user = { $firstName } { $lastName } ({ $role })"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern(
            "user",
            {"firstName": "John", "lastName": "Doe", "role": "Admin"},
        )
        assert result == "John Doe (Admin)"

    def test_number_variable_roundtrip(self) -> None:
        """Number variables format correctly."""
        ftl_source = "count = You have { $n } items."

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("count", {"n": 42})
        assert "42" in result

    def test_decimal_variable_roundtrip(self) -> None:
        """Decimal variables format correctly."""
        ftl_source = "price = Total: { $amount }"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("price", {"amount": Decimal("19.99")})
        assert "19.99" in result

    def test_missing_variable_fallback(self) -> None:
        """Missing variables produce fallback with error."""
        ftl_source = "greeting = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("greeting")
        assert "Hello" in result
        assert len(errors) > 0  # Should report missing variable


class TestParseFormatSelectExpressions:
    """Tests for parse->format with select expressions."""

    def test_simple_select_roundtrip(self) -> None:
        """Simple select expression resolves correctly."""
        ftl_source = """
items = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result_one, _ = bundle.format_pattern("items", {"count": 1})
        result_many, _ = bundle.format_pattern("items", {"count": 5})

        assert result_one == "One item"
        assert "5" in result_many
        assert "items" in result_many

    def test_string_selector_roundtrip(self) -> None:
        """String selector in select expression works correctly."""
        ftl_source = """
status = { $state ->
    [active] Currently active
    [inactive] Not active
   *[unknown] Status unknown
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        active, _ = bundle.format_pattern("status", {"state": "active"})
        inactive, _ = bundle.format_pattern("status", {"state": "inactive"})
        other, _ = bundle.format_pattern("status", {"state": "foo"})

        assert active == "Currently active"
        assert inactive == "Not active"
        assert other == "Status unknown"

    def test_nested_select_roundtrip(self) -> None:
        """Nested select expressions resolve correctly."""
        ftl_source = """
response = { $gender ->
    [male] { $count ->
        [one] He has one item
       *[other] He has { $count } items
    }
   *[other] { $count ->
        [one] They have one item
       *[other] They have { $count } items
    }
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("response", {"gender": "male", "count": 1})
        assert "He has one item" in result

    def test_number_literal_variant_roundtrip(self) -> None:
        """Number literal variants in select expressions work correctly."""
        ftl_source = """
rating = { $stars ->
    [1] Poor
    [2] Fair
    [3] Good
    [4] Great
    [5] Excellent
   *[other] Unknown
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("rating", {"stars": 5})
        assert result == "Excellent"


class TestParseFormatReferences:
    """Tests for parse->format with message and term references."""

    def test_message_reference_roundtrip(self) -> None:
        """Message references resolve correctly."""
        ftl_source = """
base = World
greeting = Hello, { base }!
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("greeting")
        assert result == "Hello, World!"
        assert len(errors) == 0

    def test_chained_reference_roundtrip(self) -> None:
        """Chained message references resolve correctly."""
        ftl_source = """
level1 = Core
level2 = { level1 } Extended
level3 = { level2 } Final
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("level3")
        assert result == "Core Extended Final"

    def test_term_reference_roundtrip(self) -> None:
        """Term references resolve correctly."""
        ftl_source = """
-brand = Firefox
download = Download { -brand } now!
about = About { -brand }
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        download, _ = bundle.format_pattern("download")
        about, _ = bundle.format_pattern("about")

        assert "Firefox" in download
        assert "Firefox" in about

    def test_term_attribute_reference_roundtrip(self) -> None:
        """Term attribute references resolve correctly."""
        ftl_source = """
-brand = Firefox
    .short = Fx
full = { -brand }
short = { -brand.short }
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        full, _ = bundle.format_pattern("full")
        short, _ = bundle.format_pattern("short")

        assert full == "Firefox"
        assert short == "Fx"

    def test_term_with_arguments_roundtrip(self) -> None:
        """Term references with arguments resolve correctly."""
        ftl_source = """
-brand = { $case ->
    [nominative] Firefox
    [genitive] Firefoxu
   *[other] Firefox
}
download = Download { -brand(case: "nominative") }
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("download")
        assert "Firefox" in result


class TestParseFormatEdgeCases:
    """Tests for edge cases and unicode handling."""

    def test_unicode_content_roundtrip(self) -> None:
        """Unicode content parses and formats correctly."""
        ftl_source = "greeting = Sveiki, pasaule!"

        bundle = FluentBundle("lv-LV", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("greeting")
        assert result == "Sveiki, pasaule!"

    def test_emoji_content_roundtrip(self) -> None:
        """Emoji content parses and formats correctly."""
        ftl_source = "welcome = Welcome! \U0001F44B"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("welcome")
        assert "\U0001F44B" in result

    def test_cjk_content_roundtrip(self) -> None:
        """CJK (Japanese) content in pattern values parses and formats correctly."""
        ftl_source = "hello = \u3053\u3093\u306b\u3061\u306f\u4e16\u754c"

        bundle = FluentBundle("ja-JP", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("hello")
        assert "\u3053\u3093\u306b\u3061\u306f" in result

    def test_arabic_content_roundtrip(self) -> None:
        """Arabic RTL script in pattern values parses and formats correctly."""
        ftl_source = "greeting = \u0645\u0631\u062d\u0628\u0627"

        bundle = FluentBundle("ar-SA", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("greeting")
        assert "\u0645\u0631\u062d\u0628\u0627" in result

    def test_hebrew_content_roundtrip(self) -> None:
        """Hebrew RTL script in pattern values parses and formats correctly."""
        ftl_source = "greeting = \u05e9\u05b8\u05dc\u05d5\u05b9\u05dd"

        bundle = FluentBundle("he-IL", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("greeting")
        assert "\u05e9\u05b8\u05dc\u05d5\u05b9\u05dd" in result

    def test_backslash_in_text_roundtrip(self) -> None:
        """Backslash in text (not StringLiteral) is preserved as-is per Fluent spec."""
        ftl_source = r"path = C:\Users\file.txt"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("path")
        assert "\\" in result
        assert "Users" in result

    def test_literal_brace_via_string_literal(self) -> None:
        """Literal braces via StringLiteral placeable."""
        ftl_source = 'json = { "{" }key{ "}" }'

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("json")
        assert "{" in result
        assert "}" in result

    def test_empty_pattern_roundtrip(self) -> None:
        """Empty pattern value handled correctly."""
        ftl_source = """
msg =
    .attr = Has attribute
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        # Main value is empty
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert isinstance(result, str)

        # Attribute should work
        attr, _ = bundle.format_pattern("msg", attribute="attr")
        assert attr == "Has attribute"

    def test_whitespace_preservation_roundtrip(self) -> None:
        """Significant whitespace in patterns is preserved."""
        ftl_source = "spaced = Hello   World"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("spaced")
        assert "   " in result


class TestParseFormatWithFunctions:
    """Tests for parse->format with built-in functions."""

    def test_number_function_roundtrip(self) -> None:
        """NUMBER function formats correctly."""
        ftl_source = "amount = { NUMBER($value, minimumFractionDigits: 2) }"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("amount", {"value": Decimal("19.99")})
        assert "19.99" in result or "19,99" in result

    def test_datetime_function_roundtrip(self) -> None:
        """DATETIME function formats correctly."""
        ftl_source = 'date = Date: { DATETIME($when, dateStyle: "short") }'

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern(
            "date", {"when": datetime(2024, 1, 15, tzinfo=UTC)}
        )
        assert "1" in result or "2024" in result

    def test_custom_function_roundtrip(self) -> None:
        """Custom functions work in parse->format workflow."""
        ftl_source = "msg = Result: { DOUBLE($n) }"

        bundle = FluentBundle("en-US", use_isolating=False)

        def double_func(n: int | Decimal) -> str:
            return str(n * 2)

        bundle.add_function("DOUBLE", double_func)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("msg", {"n": 21})
        assert "42" in result


class TestParseFormatErrorHandling:
    """Tests for error handling in parse->format workflow."""

    def test_missing_message_returns_fallback(self) -> None:
        """Missing message returns fallback string with error."""
        ftl_source = "hello = Hello!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("nonexistent")
        assert "{nonexistent}" in result
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

    def test_missing_attribute_returns_fallback(self) -> None:
        """Missing attribute returns fallback string with error."""
        ftl_source = """
button = Click
    .title = Button title
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        _, errors = bundle.format_pattern("button", attribute="nonexistent")
        assert len(errors) == 1

    def test_invalid_ftl_produces_junk(self) -> None:
        """Invalid FTL syntax produces Junk entry."""
        ftl_source = "invalid = { unclosed"

        resource = parse_ftl(ftl_source)
        assert any(isinstance(e, Junk) for e in resource.entries)

    def test_resolution_error_propagates(self) -> None:
        """Resolution errors are captured and returned."""
        ftl_source = """
msg = { missing-ref }
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        _, errors = bundle.format_pattern("msg")
        assert len(errors) > 0


class TestParseFormatIntrospection:
    """Tests for introspection API in parse->format workflow."""

    def test_has_message_after_parse(self) -> None:
        """has_message() works correctly after parsing."""
        ftl_source = """
hello = Hello
world = World
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        assert bundle.has_message("hello") is True
        assert bundle.has_message("world") is True
        assert bundle.has_message("nonexistent") is False

    def test_has_attribute_after_parse(self) -> None:
        """has_attribute() works correctly after parsing."""
        ftl_source = """
button = Click
    .title = Title
    .accesskey = A
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        assert bundle.has_attribute("button", "title") is True
        assert bundle.has_attribute("button", "accesskey") is True
        assert bundle.has_attribute("button", "nonexistent") is False

    def test_get_message_ids_after_parse(self) -> None:
        """get_message_ids() returns all parsed message IDs."""
        ftl_source = """
msg1 = First
msg2 = Second
msg3 = Third
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        ids = bundle.get_message_ids()
        assert "msg1" in ids
        assert "msg2" in ids
        assert "msg3" in ids
        assert len(ids) == 3

    def test_get_message_variables_after_parse(self) -> None:
        """get_message_variables() extracts variables from parsed message."""
        ftl_source = "greeting = Hello, { $name }! You have { $count } items."

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        variables = bundle.get_message_variables("greeting")
        assert "name" in variables
        assert "count" in variables
        assert len(variables) == 2

    def test_introspect_message_after_parse(self) -> None:
        """introspect_message() provides detailed info after parsing."""
        ftl_source = """
msg = Hello, { $name }!
select-msg = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        # Introspect simple message
        info = bundle.introspect_message("msg")
        assert info.message_id == "msg"
        assert "name" in info.get_variable_names()
        assert info.has_selectors is False

        # Introspect message with select expression
        select_info = bundle.introspect_message("select-msg")
        assert select_info.message_id == "select-msg"
        assert "count" in select_info.get_variable_names()
        assert select_info.has_selectors is True


class TestParseFormatValidation:
    """Tests for validation API in parse->format workflow."""

    def test_validate_resource_valid_ftl(self) -> None:
        """validate_resource() accepts valid FTL."""
        ftl_source = """
hello = Hello, World!
greeting = Hello, { $name }!
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        result = bundle.validate_resource(ftl_source)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_resource_invalid_ftl(self) -> None:
        """validate_resource() rejects invalid FTL."""
        ftl_source = "invalid = { unclosed"

        bundle = FluentBundle("en-US", use_isolating=False)
        result = bundle.validate_resource(ftl_source)

        assert result.is_valid is False
        assert len(result.errors) > 0


class TestParseFormatWithCache:
    """Tests for caching behavior in parse->format workflow."""

    def test_cache_enabled_improves_repeated_calls(self) -> None:
        """Cache improves performance on repeated format calls."""
        ftl_source = "msg = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=False, cache=CacheConfig())
        bundle.add_resource(ftl_source)

        # First call - cache miss
        result1, _ = bundle.format_pattern("msg", {"name": "Alice"})

        # Second call with same args - cache hit
        result2, _ = bundle.format_pattern("msg", {"name": "Alice"})

        assert result1 == result2

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] >= 1

    def test_cache_stats_available_when_enabled(self) -> None:
        """Cache statistics are available when caching enabled."""
        ftl_source = "msg = Hello!"

        bundle = FluentBundle("en-US", use_isolating=False, cache=CacheConfig())
        bundle.add_resource(ftl_source)

        bundle.format_pattern("msg")

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert "hits" in stats
        assert "misses" in stats

    def test_cache_stats_none_when_disabled(self) -> None:
        """Cache statistics are None when caching disabled."""
        ftl_source = "msg = Hello!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        bundle.format_pattern("msg")

        stats = bundle.get_cache_stats()
        assert stats is None

    def test_clear_cache_preserves_stats(self) -> None:
        """clear_cache() clears entries but metrics are cumulative (not reset)."""
        ftl_source = "msg = Hello!"

        bundle = FluentBundle("en-US", use_isolating=False, cache=CacheConfig())
        bundle.add_resource(ftl_source)

        bundle.format_pattern("msg")   # miss
        bundle.format_pattern("msg")   # hit

        bundle.clear_cache()
        bundle.format_pattern("msg")   # miss (entries cleared, not metrics)

        stats = bundle.get_cache_stats()
        assert stats is not None
        # 1 pre-clear miss + 1 post-clear miss = 2 cumulative misses
        assert stats["misses"] == 2


class TestParseFormatIsolation:
    """Tests for Unicode bidi isolation in parse->format workflow."""

    def test_use_isolating_true_adds_marks(self) -> None:
        """use_isolating=True wraps placeables in bidi isolation marks."""
        ftl_source = "msg = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=True)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("msg", {"name": "World"})

        # Should contain FSI (First Strong Isolate) and PDI (Pop Directional Isolate)
        assert "\u2068" in result
        assert "\u2069" in result

    def test_use_isolating_false_no_marks(self) -> None:
        """use_isolating=False does not add bidi isolation marks."""
        ftl_source = "msg = Hello, { $name }!"

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        result, _ = bundle.format_pattern("msg", {"name": "World"})

        # Should NOT contain isolation marks
        assert "\u2068" not in result
        assert "\u2069" not in result


class TestCommentPreservation:
    """Tests for comment handling in parse->format."""

    def test_comments_dont_affect_formatting(self) -> None:
        """Comments in FTL don't affect message formatting."""
        ftl_source = """
# This is a comment
## Group comment
### Resource comment
hello = Hello!
# Another comment
world = World!
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl_source)

        hello, _ = bundle.format_pattern("hello")
        world, _ = bundle.format_pattern("world")

        assert hello == "Hello!"
        assert world == "World!"


# =============================================================================
# Intensive Round-trip Tests (Fuzz-marked, run with pytest -m fuzz)
# =============================================================================


class TestSerializeParseRoundtrip:
    """Example-based tests for AST serialization round-trips."""

    def test_serialize_parse_simple_message(self) -> None:
        """Serialize->parse round-trip preserves simple messages."""
        ftl_source = "hello = Hello, World!"

        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)
        resource2 = parse_ftl(serialized)

        assert len(resource.entries) == len(resource2.entries)

    def test_serialize_parse_with_variables(self) -> None:
        """Serialize->parse round-trip preserves variables."""
        ftl_source = "greeting = Hello, { $name }!"

        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle1 = FluentBundle("en-US", use_isolating=False)
        bundle1.add_resource(ftl_source)

        bundle2 = FluentBundle("en-US", use_isolating=False)
        bundle2.add_resource(serialized)

        result1, _ = bundle1.format_pattern("greeting", {"name": "Test"})
        result2, _ = bundle2.format_pattern("greeting", {"name": "Test"})

        assert result1 == result2

    def test_serialize_preserves_select_expressions(self) -> None:
        """Serialize->parse preserves select expression structure."""
        ftl_source = """
count = { $n ->
    [one] One
   *[other] Many
}
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        one, _ = bundle.format_pattern("count", {"n": 1})
        many, _ = bundle.format_pattern("count", {"n": 5})

        assert "One" in one
        assert "Many" in many

    def test_serialize_preserves_term_attributes(self) -> None:
        """Serialize->parse preserves term attributes."""
        ftl_source = """
-brand = Firefox
    .short = Fx
    .full = Mozilla Firefox
msg = { -brand.short }
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        result, _ = bundle.format_pattern("msg")
        assert "Fx" in result

    def test_serialize_preserves_message_attributes(self) -> None:
        """Serialize->parse preserves message attributes."""
        ftl_source = """
button = Click me
    .accesskey = C
    .title = Submit
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        accesskey, _ = bundle.format_pattern("button", attribute="accesskey")
        title, _ = bundle.format_pattern("button", attribute="title")

        assert accesskey == "C"
        assert title == "Submit"


# =============================================================================
# Multi-Module Pipeline Tests
# =============================================================================


class TestMultiModuleIntegration:
    """Integration tests exercising parse->validate->serialize->introspect pipeline."""

    def test_parse_validate_serialize_roundtrip(self) -> None:
        """Complete roundtrip: parse -> validate -> serialize -> re-parse preserves structure."""
        ftl = """
msg = Hello { $name }
    .title = Title

-brand = Firefox

plural = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        result = validate_resource(ftl)
        assert result.is_valid

        serialized = serialize(resource)
        resource2 = parser.parse(serialized)

        assert len(resource2.entries) == len(resource.entries)

    def test_introspect_complex_message(self) -> None:
        """Introspect message with select expression, term reference, and function call."""
        ftl = """
complex = { NUMBER($count) ->
    [one] { -brand } has { $count } item
   *[other] { -brand } has { NUMBER($count) } items
}
    .hint = { $hint }
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        info = introspect_message(msg)

        var_names = {v.name for v in info.variables}
        func_names = {f.name for f in info.functions}
        assert "count" in var_names
        assert "hint" in var_names
        assert info.has_selectors
        assert "NUMBER" in func_names


class TestValidationRuntimeConsistency:
    """Validation warnings predict runtime resolution failures."""

    def test_chain_depth_warning_matches_runtime_error(self) -> None:
        """VALIDATION_CHAIN_DEPTH_EXCEEDED warning implies MAX_DEPTH_EXCEEDED at runtime."""
        chain_length = MAX_DEPTH + 5
        messages = ["msg-0 = Base"]
        for i in range(1, chain_length):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        result = validate_resource(ftl_source)
        has_chain_warning = any(
            w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED
            for w in result.warnings
        )
        assert has_chain_warning

        bundle = FluentBundle("en")
        bundle.add_resource(ftl_source)
        _, errors = bundle.format_pattern(f"msg-{chain_length - 1}")
        has_depth_error = any(
            e.diagnostic is not None
            and e.diagnostic.code.name == "MAX_DEPTH_EXCEEDED"
            for e in errors
        )
        assert has_depth_error


# =============================================================================
# NumberLiteral Invariant and Roundtrip
# =============================================================================


class TestNumberLiteralInvariant:
    """NumberLiteral enforces raw/value consistency and rejects bool."""

    def test_bool_value_rejected(self) -> None:
        """NumberLiteral rejects bool for value (bool is int subclass, not a number literal)."""
        with pytest.raises(TypeError, match="must be int or Decimal, not bool"):
            NumberLiteral(value=True, raw="1")

    def test_raw_value_inconsistency_rejected(self) -> None:
        """NumberLiteral rejects raw that parses to a different value than the value field."""
        with pytest.raises(ValueError, match=r"parses to.*but value is"):
            NumberLiteral(value=Decimal("1.5"), raw="9.9")

    def test_integer_variant_key_exact_match_roundtrip(self) -> None:
        """Integer number variant keys select the correct variant."""
        ftl = """
rating = { $stars ->
    [1] Poor
    [3] Good
    [5] Excellent
   *[other] Unknown
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl)

        poor, err1 = bundle.format_pattern("rating", {"stars": 1})
        excellent, err2 = bundle.format_pattern("rating", {"stars": 5})
        fallback, err3 = bundle.format_pattern("rating", {"stars": 99})

        assert not err1
        assert not err2
        assert not err3
        assert poor == "Poor"
        assert excellent == "Excellent"
        assert fallback == "Unknown"

    def test_decimal_variant_key_roundtrip(self) -> None:
        """Decimal number variant keys in serialized FTL survive parse->format roundtrip."""
        ftl = """
precision = { $level ->
    [0.5] Half
    [1.0] Full
   *[other] Custom
}
"""
        resource = parse_ftl(ftl)
        serialized = serialize_ftl(resource)
        resource2 = parse_ftl(serialized)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialize_ftl(resource2))

        # Default variant (string selector won't match numeric keys)
        result, _ = bundle.format_pattern("precision", {"level": "other"})
        assert result == "Custom"


# =============================================================================
# Locale Code Validation
# =============================================================================


class TestLocaleCodeValidation:
    """FluentBundle validates locale codes against BCP 47 format."""

    def test_posix_locale_with_charset_rejected(self) -> None:
        """POSIX locale string with charset suffix is rejected with BCP 47 guidance."""
        with pytest.raises(ValueError, match="Strip charset suffixes"):
            FluentBundle("en_US.UTF-8")

    def test_valid_bcp47_locales_accepted(self) -> None:
        """Valid BCP 47 locale codes are accepted by FluentBundle."""
        for locale in ("en-US", "de-DE", "zh-Hans-CN"):
            bundle = FluentBundle(locale, use_isolating=False)
            bundle.add_resource("hello = Hello")
            result, _ = bundle.format_pattern("hello")
            assert result == "Hello"
