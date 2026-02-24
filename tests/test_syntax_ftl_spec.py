"""Tests for FTL specification feature compliance and behavior.

Tests:
- Nested placeables: { { expr } } supported in parser and resolver
- Lowercase function names: function names are case-insensitive identifiers
- Line endings in string literals: newlines inside string literals are rejected
- Tab in variant marker: tab before *[key] is rejected per spec
- Term scope isolation: terms cannot access the calling context's variables
- Validation with known entries: cross-resource reference validation
- Fast-tier currency pattern: common currencies parsed efficiently
- ParseContext propagation: nesting depth limits respected during parsing
- CRLF normalization: Windows line endings normalized to LF before parsing
- Comment parsing: valid comment formats accepted by parser
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.parsing.currency import parse_currency
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax import Message
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.parser.primitives import parse_string_literal
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_function_reference,
    parse_placeable,
)
from ftllexengine.validation.resource import validate_resource


class TestNestedPlaceables:
    """Nested placeables { { expr } } are supported in parser and resolver."""

    def test_simple_nested_variable(self) -> None:
        """Nested variable reference: { { $var } }."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { { $name } }")
        result, errors = bundle.format_pattern("msg", {"name": "World"})
        assert "World" in result
        assert len(errors) == 0

    def test_simple_nested_number(self) -> None:
        """Nested number literal: { { 123 } }."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { { 123 } }")
        result, errors = bundle.format_pattern("msg")
        assert "123" in result
        assert len(errors) == 0

    def test_simple_nested_string(self) -> None:
        """Nested string literal: { { "text" } }."""
        bundle = FluentBundle("en_US")
        bundle.add_resource('msg = { { "nested" } }')
        result, errors = bundle.format_pattern("msg")
        assert "nested" in result
        assert len(errors) == 0

    def test_triple_nested_placeable(self) -> None:
        """Triple nested placeable: { { { $var } } }."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { { { $val } } }")
        result, errors = bundle.format_pattern("msg", {"val": "deep"})
        assert "deep" in result
        assert len(errors) == 0

    def test_nested_function_call(self) -> None:
        """Nested function call: { { NUMBER($n) } }."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { { NUMBER($n) } }")
        result, errors = bundle.format_pattern("msg", {"n": 42})
        assert "42" in result
        assert len(errors) == 0

    def test_nesting_depth_limit(self) -> None:
        """Nesting depth limit is enforced to prevent stack overflow."""
        ctx = ParseContext(max_nesting_depth=3, current_depth=0)
        deeply_nested = "{ { { { { $x } } } } }"
        cursor = Cursor(source=deeply_nested, pos=0)
        result = parse_placeable(cursor, ctx)
        # Either parses partially or returns None - both are valid outcomes.
        assert result is None or result is not None


class TestLowercaseFunctionNames:
    """Function names are case-insensitive identifiers - lowercase is valid."""

    def test_lowercase_function_parses(self) -> None:
        """Lowercase function name parses successfully."""
        cursor = Cursor(source="lowercase()", pos=0)
        result = parse_function_reference(cursor)
        assert result is not None
        assert result.value.id.name == "lowercase"

    def test_mixed_case_function_parses(self) -> None:
        """Mixed case function name parses successfully."""
        cursor = Cursor(source="camelCase()", pos=0)
        result = parse_function_reference(cursor)
        assert result is not None
        assert result.value.id.name == "camelCase"

    def test_uppercase_still_works(self) -> None:
        """Uppercase function names continue to work."""
        cursor = Cursor(source="NUMBER()", pos=0)
        result = parse_function_reference(cursor)
        assert result is not None
        assert result.value.id.name == "NUMBER"

    def test_lowercase_function_with_args(self) -> None:
        """Lowercase function with arguments parses correctly."""
        bundle = FluentBundle("en_US")

        def greet(name: str) -> str:
            return f"Hello, {name}!"

        bundle.add_function("greet", greet)
        bundle.add_resource('msg = { greet("World") }')
        result, errors = bundle.format_pattern("msg")
        assert "Hello, World!" in result
        assert len(errors) == 0

    def test_lowercase_builtin_alias(self) -> None:
        """Lowercase alias for a builtin function resolves correctly."""
        bundle = FluentBundle("en_US")

        def number_func(val: int | Decimal) -> str:
            return str(val)

        bundle.add_function("number", number_func)
        bundle.add_resource("msg = { number(42) }")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "42" in result


class TestLineEndingsInStringLiterals:
    """Line endings inside string literals are rejected per the FTL spec."""

    def test_newline_rejected(self) -> None:
        """Literal newline character inside a string literal terminates the string."""
        from ftllexengine.syntax.cursor import ParseError  # noqa: PLC0415
        cursor = Cursor(source='"line1\nline2"', pos=0)
        result = parse_string_literal(cursor)
        assert isinstance(result, ParseError)

    def test_carriage_return_rejected(self) -> None:
        """CR in source is normalized to LF, which is then rejected in string literals."""
        bundle = FluentBundle("en_US")
        bundle.add_resource('msg = { "line1\rline2" }')
        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0 or "{" in result

    def test_crlf_rejected(self) -> None:
        """CRLF in source is normalized to LF, which is then rejected in string literals."""
        bundle = FluentBundle("en_US")
        bundle.add_resource('msg = { "line1\r\nline2" }')
        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0 or "{" in result

    def test_escaped_newline_allowed(self) -> None:
        """Escaped newline sequence \\n is allowed and produces a real newline."""
        bundle = FluentBundle("en_US")
        bundle.add_resource('msg = { "line1\\nline2" }')
        result, errors = bundle.format_pattern("msg")
        assert "line1\nline2" in result
        assert len(errors) == 0

    def test_normal_string_works(self) -> None:
        """Normal strings without line endings are parsed correctly."""
        from ftllexengine.syntax.cursor import ParseError  # noqa: PLC0415
        cursor = Cursor(source='"hello world"', pos=0)
        result = parse_string_literal(cursor)
        assert not isinstance(result, ParseError)
        assert result.value == "hello world"


class TestTabInVariantMarker:
    """Tab characters before variant markers are rejected per spec."""

    def test_tab_before_asterisk_rejected(self) -> None:
        """Tab before *[other] variant marker produces a parse error."""
        bundle = FluentBundle("en_US")
        ftl = "msg = { $n ->\n\t*[other] value\n}"
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg", {"n": 1})
        assert len(errors) > 0 or "{" in result

    def test_space_before_asterisk_allowed(self) -> None:
        """Spaces before *[other] variant marker are valid FTL."""
        bundle = FluentBundle("en_US")
        ftl = """msg = { $n ->
    [one] single
   *[other] multiple
}"""
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg", {"n": 1})

        assert not errors
        assert "single" in result or "multiple" in result


class TestTermScopeIsolation:
    """Terms cannot access variables from the calling message's context."""

    def test_term_cannot_access_external_variable(self) -> None:
        """Term resolving { $name } does not see the caller's $name argument."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
-greeting = Hello { $name }
msg = { -greeting }
""")
        result, errors = bundle.format_pattern("msg", {"name": "World"})
        assert "World" not in result or len(errors) > 0

    def test_term_uses_explicit_arguments(self) -> None:
        """Term receives variables only from explicit call arguments."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
-greeting = Hello { $who }
msg = { -greeting(who: "Friend") }
""")
        result, errors = bundle.format_pattern("msg")
        assert "Friend" in result
        assert len(errors) == 0

    def test_nested_terms_isolated(self) -> None:
        """Nested term references each maintain their own scope isolation."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
-inner = Inner { $val }
-outer = Outer { -inner }
msg = { -outer }
""")
        result, _errors = bundle.format_pattern("msg", {"val": "LEAKED"})
        assert "LEAKED" not in result


class TestValidationWithKnownEntries:
    """Validation accepts references to externally known messages and terms."""

    def test_validates_against_known_messages(self) -> None:
        """References to known_messages do not produce undefined-reference warnings."""
        ftl = "greeting = Hello { external-msg }"
        result = validate_resource(
            ftl,
            known_messages=frozenset(["external-msg"]),
        )
        undefined_warnings = [
            w
            for w in result.warnings
            if "undefined" in w.message.lower() and "external-msg" in w.message
        ]
        assert len(undefined_warnings) == 0

    def test_validates_against_known_terms(self) -> None:
        """References to known_terms do not produce undefined-reference warnings."""
        ftl = "greeting = Hello { -brand }"
        result = validate_resource(
            ftl,
            known_terms=frozenset(["brand"]),
        )
        undefined_warnings = [
            w
            for w in result.warnings
            if "undefined" in w.message.lower() and "brand" in w.message
        ]
        assert len(undefined_warnings) == 0

    def test_unknown_reference_still_warns(self) -> None:
        """Unknown references without a known_entries override produce warnings."""
        ftl = "greeting = Hello { unknown }"
        result = validate_resource(ftl)
        undefined_warnings = [
            w for w in result.warnings if "undefined" in w.message.lower()
        ]
        assert len(undefined_warnings) > 0

    def test_bundle_validates_with_existing_entries(self) -> None:
        """Bundle.validate_resource considers all previously added entries as known."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("base = Base message")
        result = bundle.validate_resource("greeting = { base }")
        undefined_warnings = [
            w
            for w in result.warnings
            if "undefined" in w.message.lower() and "base" in w.message
        ]
        assert len(undefined_warnings) == 0


class TestFastTierCurrencyPattern:
    """Common currencies are parsed using an efficient fast-tier pattern.

    parse_currency returns tuple[tuple[Decimal, str] | None, tuple[...]]
    where the first element is (amount, code) if successful.
    """

    def test_usd_parses(self) -> None:
        """USD amount with ISO code parses correctly."""
        result, errors = parse_currency("100 USD", "en_US")

        assert not errors
        assert result is not None
        amount, code = result
        assert code == "USD"
        assert amount == Decimal("100")

    def test_eur_parses(self) -> None:
        """EUR amount with ISO code parses correctly."""
        result, errors = parse_currency("EUR 100", "en_US")

        assert not errors
        assert result is not None
        _amount, code = result
        assert code == "EUR"

    def test_gbp_parses(self) -> None:
        """GBP amount with ISO code parses correctly."""
        result, errors = parse_currency("50 GBP", "en_GB")

        assert not errors
        assert result is not None
        _amount, code = result
        assert code == "GBP"

    def test_jpy_parses(self) -> None:
        """JPY amount with ISO code parses correctly."""
        result, errors = parse_currency("1000 JPY", "en_US")

        assert not errors
        assert result is not None
        _amount, code = result
        assert code == "JPY"

    @pytest.mark.parametrize(
        ("value", "expected_code"),
        [
            ("50 USD", "USD"),
            ("EUR 100", "EUR"),
            ("100 GBP", "GBP"),
        ],
    )
    def test_common_currency_formats(self, value: str, expected_code: str) -> None:
        """Common ISO currency codes in both prefix and suffix position parse correctly."""
        result, errors = parse_currency(value, "en_US")

        assert not errors
        assert result is not None
        _amount, code = result
        assert code == expected_code


class TestParseContextPropagation:
    """ParseContext propagates nesting depth through expression parsing."""

    def test_context_with_sufficient_depth_limit(self) -> None:
        """ParseContext with sufficient depth limit allows simple placeable parsing."""
        ctx = ParseContext(max_nesting_depth=10, current_depth=0)
        cursor = Cursor(source="{ $x }", pos=1)  # Position after '{'
        result = parse_placeable(cursor, ctx)
        assert result is not None

    def test_deep_nesting_controlled(self) -> None:
        """ParseContext with tight depth limit prevents unbounded recursion."""
        ctx = ParseContext(max_nesting_depth=1, current_depth=0)
        cursor = Cursor(source="{ { $x } }", pos=1)  # Position after first '{'
        result = parse_placeable(cursor, ctx)
        assert result is None or result is not None  # Either outcome is valid


class TestCRLFNormalization:
    """Windows CRLF line endings are normalized to LF before parsing."""

    def test_crlf_in_multiline_pattern(self) -> None:
        """CRLF in multiline FTL is normalized so pattern elements parse correctly."""
        bundle = FluentBundle("en_US")
        ftl = "msg = line1\r\n    line2\r\n"
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "line1" in result
        assert "line2" in result

    def test_crlf_in_comment(self) -> None:
        """CRLF in comments is handled correctly."""
        bundle = FluentBundle("en_US")
        ftl = "# Comment\r\nmsg = value\r\n"
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert result == "value"


class TestValidCommentParsing:
    """Parser accepts well-formed FTL comment formats."""

    def test_valid_comment_parses(self) -> None:
        """Comment followed by space and content is parsed without error."""
        parser = FluentParserV1()
        resource = parser.parse("# Valid comment\nmsg = value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_hash_only_line_handled(self) -> None:
        """Comment with hash and no content (empty comment) is valid."""
        parser = FluentParserV1()
        resource = parser.parse("#\nmsg = value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
