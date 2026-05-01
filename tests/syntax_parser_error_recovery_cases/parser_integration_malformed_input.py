# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSER INTEGRATION - MALFORMED INPUT
# ============================================================================


class TestParserMalformedInput:
    """FluentParserV1 integration for error recovery on malformed FTL."""

    def test_four_hash_comment_recovery(self) -> None:
        """Invalid >3 hash comment is recovered as junk."""
        parser = FluentParserV1()
        res = parser.parse(
            "#### Invalid\nkey = value"
        )
        assert any(
            hasattr(e, "id") and e.id.name == "key"
            for e in res.entries
        )

    def test_multiple_junk_entries(self) -> None:
        """Multiple malformed entries create multiple junk entries."""
        parser = FluentParserV1()
        res = parser.parse(
            "!!!invalid1\n!!!invalid2\nkey = value\n"
        )
        assert any(
            hasattr(e, "id") and e.id.name == "key"
            for e in res.entries
        )

    def test_junk_with_unicode(self) -> None:
        """Junk entries with non-ASCII characters."""
        parser = FluentParserV1()
        res = parser.parse("¡¡¡ invalid\nkey = value\n")
        assert len(res.entries) >= 1

    def test_empty_variant_key(self) -> None:
        """Empty variant key []."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c -> [] x *[o] O }\n"
        )
        assert len(res.entries) >= 1

    def test_unclosed_variant_bracket(self) -> None:
        """Unclosed variant bracket."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c -> [unclosed X *[o] O }\n"
        )
        assert len(res.entries) >= 1

    def test_select_missing_arrow(self) -> None:
        """Select expression without '->'."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $val\n   [one] One\n  *[other] Other\n}\n"
        )
        junk = [e for e in res.entries if isinstance(e, Junk)]
        assert len(junk) >= 1

    def test_unclosed_placeable(self) -> None:
        """Unclosed placeable creates junk."""
        parser = FluentParserV1()
        res = parser.parse("msg = { $value")
        assert isinstance(res.entries[0], Junk)

    def test_invalid_variant_syntax(self) -> None:
        """Invalid variant syntax (missing '[')."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c ->\n   one] One\n  *[other] O\n}\n"
        )
        junk = [e for e in res.entries if isinstance(e, Junk)]
        assert len(junk) >= 1

    def test_empty_placeable(self) -> None:
        """Empty placeable { }."""
        parser = FluentParserV1()
        res = parser.parse("key = { }")
        assert res is not None

    def test_standalone_attribute(self) -> None:
        """Attribute without Message/Term creates junk."""
        parser = FluentParserV1()
        res = parser.parse("    .attr = Value")
        assert isinstance(res.entries[0], Junk)

    def test_invalid_term_name(self) -> None:
        """Term '-' without valid identifier."""
        parser = FluentParserV1()
        res = parser.parse("- = Invalid")
        assert len(res.entries) >= 1

    def test_message_without_equals(self) -> None:
        """Message identifier without '=' creates junk."""
        parser = FluentParserV1()
        res = parser.parse("test Hello")
        assert isinstance(res.entries[0], Junk)

    def test_identifier_starting_with_number(self) -> None:
        """Identifier starting with number creates junk."""
        parser = FluentParserV1()
        res = parser.parse("123invalid = Value")
        assert isinstance(res.entries[0], Junk)

    def test_eof_after_equals(self) -> None:
        """EOF after '=' sign."""
        parser = FluentParserV1()
        res = parser.parse("msg =")
        assert len(res.entries) > 0

    def test_eof_after_identifier(self) -> None:
        """File ends right after message ID."""
        parser = FluentParserV1()
        res = parser.parse("msg")
        assert len(res.entries) > 0

    def test_multiple_errors_creates_multiple_junk(self) -> None:
        """Multiple errors create junk interleaved with valid entries."""
        parser = FluentParserV1()
        res = parser.parse(
            "invalid1 Missing\nvalid = Good\n"
            "invalid2 Also\nanother = OK\n"
        )
        assert len(res.entries) == 4
        junk_count = sum(
            1 for e in res.entries if isinstance(e, Junk)
        )
        assert junk_count == 2


class TestParserMalformedExpressions:
    """FluentParserV1 integration for malformed expressions."""

    def test_invalid_selector_variable(self) -> None:
        """$ followed by invalid character in selector."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $-invalid -> *[key] Value }"
        )
        assert any(isinstance(e, Junk) for e in res.entries)

    def test_unclosed_string_literal_in_selector(self) -> None:
        """Unclosed string literal in selector."""
        parser = FluentParserV1()
        res = parser.parse(
            'msg = { "unclosed -> *[key] Value }'
        )
        assert any(isinstance(e, Junk) for e in res.entries)

    def test_function_no_parens(self) -> None:
        """UPPERCASE without parens is MessageReference."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC }")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        p = msg.value.elements[0]
        assert isinstance(p, Placeable)
        assert isinstance(p.expression, MessageReference)

    def test_function_missing_argument(self) -> None:
        """Function with incomplete arguments."""
        parser = FluentParserV1()
        res = parser.parse("key = { UPPERCASE( }")
        assert res is not None

    def test_function_invalid_argument(self) -> None:
        """Function with @invalid argument."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(@invalid) }")
        assert res is not None

    def test_term_ref_invalid_identifier(self) -> None:
        """Term reference '-#' with invalid identifier."""
        parser = FluentParserV1()
        res = parser.parse("key = { -# }")
        assert len(res.entries) >= 1

    def test_lowercase_function_call(self) -> None:
        """Lowercase identifier with () is now valid per spec."""
        parser = FluentParserV1()
        res = parser.parse("key = { lowercase() }")
        assert len(res.entries) >= 1

    def test_nested_malformed(self) -> None:
        """Deeply malformed nested structures."""
        parser = FluentParserV1()
        res = parser.parse(
            "key1 = { $v -> [a] { FUNC( *[b] X }\nkey2 = ok\n"
        )
        assert len(res.entries) >= 1

    def test_term_reference_arguments_unclosed(self) -> None:
        """Term arguments without closing ')'."""
        parser = FluentParserV1()
        res = parser.parse("key = { -term(arg ")
        assert res is not None

    def test_named_argument_number_as_name(self) -> None:
        """Number as named argument name."""
        parser = FluentParserV1()
        res = parser.parse('key = { FUNC(123: "value") }')
        assert res is not None

    def test_duplicate_named_argument_via_parser(self) -> None:
        """Duplicate named argument names via parser."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(foo: 1, foo: 2) }")
        assert res is not None

    def test_positional_after_named_via_parser(self) -> None:
        """Positional after named argument."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(name: 1, 2) }")
        assert res is not None

    def test_named_arg_missing_value_via_parser(self) -> None:
        """Named argument missing value."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(name:) }")
        assert res is not None

    def test_incomplete_number_at_eof(self) -> None:
        """Number literal at EOF without closing brace."""
        parser = FluentParserV1()
        res = parser.parse("msg = { 42")
        assert len(res.entries) > 0

    def test_number_multiple_decimal_points(self) -> None:
        """Number with multiple decimal points."""
        parser = FluentParserV1()
        res = parser.parse("msg = { 1.2.3 }")
        assert len(res.entries) >= 1

    def test_select_with_empty_variant_value(self) -> None:
        """Select expression with empty variant value."""
        parser = FluentParserV1()
        res = parser.parse(
            "test = { $c ->\n   [one]\n  *[other] O\n}\n"
        )
        assert len(res.entries) >= 1
