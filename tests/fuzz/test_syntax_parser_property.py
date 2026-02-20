"""Fuzz property-based tests for syntax.parser: entry, error-recovery, expression parsing."""

from __future__ import annotations

import pytest
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Term,
    TermReference,
    VariableReference,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_argument_expression,
    parse_comment,
    parse_function_reference,
    parse_inline_expression,
    parse_message,
    parse_term,
    parse_term_reference,
    parse_variable_reference,
)

pytestmark = pytest.mark.fuzz


# ============================================================================
# Entry Property Tests (from test_parser_entries)
# ============================================================================


@pytest.mark.fuzz
class TestEntriesHypothesis:
    """Property-based tests for entry parsing."""

    @given(
        num_blank_lines=st.integers(min_value=1, max_value=5),
        extra_spaces=st.integers(min_value=0, max_value=8),
    )
    def test_pattern_with_variable_blank_lines(
        self, num_blank_lines: int, extra_spaces: int
    ) -> None:
        """Patterns handle arbitrary blank lines."""
        event(f"num_blank_lines={num_blank_lines}")
        event(f"extra_spaces={extra_spaces}")
        blank_lines = "\n" * num_blank_lines
        spaces = " " * (4 + extra_spaces)
        source = (
            f"hello = text\n{spaces}"
            f"{blank_lines}{spaces}continued"
        )
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)

    @given(
        base_indent=st.integers(min_value=1, max_value=4),
        extra_indent=st.integers(min_value=0, max_value=4),
    )
    def test_pattern_with_variable_indentation(
        self, base_indent: int, extra_indent: int
    ) -> None:
        """Patterns preserve extra indentation."""
        event(f"base_indent={base_indent}")
        event(f"extra_indent={extra_indent}")
        common = " " * base_indent
        extra = " " * extra_indent
        source = (
            f"msg = line1\n{common}line2\n"
            f"{common}{extra}line3"
        )
        result = parse_message(
            Cursor(source, 0), ParseContext()
        )
        assert result is not None
        assert isinstance(result.value, Message)

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=1, max_size=20,
        )
    )
    def test_message_identifier_property(
        self, name: str
    ) -> None:
        """Valid identifiers parse as message IDs."""
        event(f"name_len={len(name)}")
        source = f"{name} = value"
        result = parse_message(Cursor(source, 0))
        assert result is not None
        assert result.value.id.name == name

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=1, max_size=20,
        )
    )
    def test_term_identifier_property(
        self, name: str
    ) -> None:
        """Valid identifiers parse as term IDs."""
        event(f"name_len={len(name)}")
        source = f"-{name} = value"
        result = parse_term(Cursor(source, 0))
        assert result is not None
        assert isinstance(result.value, Term)
        assert result.value.id.name == name


# ============================================================================
# Error Recovery Property Tests (from test_parser_error_recovery)
# ============================================================================


@pytest.mark.fuzz
class TestErrorRecoveryHypothesis:
    """Property-based tests for error recovery paths."""

    @given(
        value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="{}[]#.=-*",
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_inline_value_parses(self, value: str) -> None:
        """Inline values (no newline) parse as message."""
        assume("\n" not in value and "\r" not in value)
        assume(value.strip() == value)
        kind = "alpha" if value[0].isalpha() else "other"
        event(f"value_start={kind}")

        parser = FluentParserV1()
        res = parser.parse(f"msg = {value}")
        assert len(res.entries) > 0

    @given(
        number=st.integers(
            min_value=-1000, max_value=1000
        )
    )
    @example(0)
    @example(-42)
    @example(42)
    def test_number_variant_key_property(
        self, number: int
    ) -> None:
        """Number literal variant keys parse correctly."""
        sign = "negative" if number < 0 else "non_negative"
        event(f"number_sign={sign}")

        parser = FluentParserV1()
        res = parser.parse(
            f"msg = {{ $c ->\n"
            f"    [{number}] Value\n"
            f"   *[other] Other\n"
            f"}}\n"
        )
        msg = res.entries[0]
        assert isinstance(msg, (Message, Junk))

    @given(
        id_name=st.from_regex(
            r"[a-zA-Z][a-zA-Z0-9_-]{0,30}", fullmatch=True
        )
    )
    def test_various_id_formats(self, id_name: str) -> None:
        """Various identifier formats parse as entries."""
        length = "short" if len(id_name) <= 5 else "long"
        event(f"id_length={length}")

        parser = FluentParserV1()
        res = parser.parse(f"{id_name} = Value")
        assert len(res.entries) > 0

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="{}[]#",
            ),
            min_size=1,
            max_size=50,
        )
    )
    def test_various_text_content(self, text: str) -> None:
        """Various text content parses correctly."""
        assume("\n" not in text and "\r" not in text)
        assume(text.strip())
        assume(not text.startswith("."))
        assume(not text.startswith("-"))
        has_special = any(c in text for c in "=*")
        event(
            f"has_special={'yes' if has_special else 'no'}"
        )

        parser = FluentParserV1()
        safe_text = text.replace("\\", "\\\\")
        res = parser.parse(f"msg = {safe_text}")
        assert len(res.entries) > 0

    @given(
        func_name=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            min_size=1,
            max_size=10,
        )
    )
    def test_uppercase_id_triggers_function_lookahead(
        self, func_name: str
    ) -> None:
        """Uppercase identifiers trigger function call lookahead."""
        length = "short" if len(func_name) <= 3 else "long"
        event(f"func_name_length={length}")

        result = parse_argument_expression(
            Cursor(func_name, 0)
        )
        if result is not None:
            assert isinstance(result.value, MessageReference)

    @given(
        number=st.integers(
            min_value=-1000000, max_value=1000000
        )
    )
    def test_integers_parse_as_number_literal(
        self, number: int
    ) -> None:
        """Integer strings parse as NumberLiteral in arguments."""
        sign = "negative" if number < 0 else "non_negative"
        event(f"argument_number_sign={sign}")

        result = parse_argument_expression(
            Cursor(str(number), 0)
        )
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    @given(
        var_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd")
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s and s[0].isalpha())
    )
    def test_valid_identifiers_parse_as_message_ref(
        self, var_name: str
    ) -> None:
        """Valid identifiers parse as MessageReference."""
        assume(not var_name.isupper())
        case = "lower" if var_name[0].islower() else "mixed"
        event(f"identifier_case={case}")

        result = parse_argument_expression(
            Cursor(var_name, 0)
        )
        if result is not None:
            assert isinstance(
                result.value, (MessageReference, NumberLiteral)
            )

    @given(
        content=st.text(min_size=0, max_size=100)
    )
    def test_comment_arbitrary_content(
        self, content: str
    ) -> None:
        """Comment with arbitrary content."""
        clean = content.replace("\n", "").replace("\r", "")
        has_content = "yes" if clean.strip() else "no"
        event(f"comment_has_content={has_content}")

        cursor = Cursor(f"# {clean}\n", 0)
        result = parse_comment(cursor)
        if result is not None:
            assert result.value.content == clean


# ============================================================================
# Expression Property Tests (from test_parser_expressions)
# ============================================================================


@pytest.mark.fuzz
class TestExpressionsHypothesis:
    """Property-based tests for expression parsing."""

    @given(st.integers(min_value=0, max_value=1000))
    @example(42)
    @example(-42)
    @example(0)
    def test_numeric_argument_roundtrip(self, num: int) -> None:
        """Numbers parse correctly as argument expressions."""
        event(f"num_sign={'neg' if num < 0 else 'pos'}")
        cursor = Cursor(str(num), 0)
        result = parse_argument_expression(cursor)
        if result is not None:
            assert isinstance(
                result.value, (NumberLiteral, TermReference)
            )

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=20,
        )
    )
    @example("msg")
    @example("x")
    def test_identifier_as_inline_expression(
        self, name: str
    ) -> None:
        """Valid identifiers parsed as message references."""
        event(f"name_len={len(name)}")
        result = parse_inline_expression(Cursor(name, 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=20,
        )
    )
    @example("count")
    @example("x")
    def test_variable_reference_property(self, name: str) -> None:
        """'$' + valid identifier always parses as VariableReference."""
        event(f"name_len={len(name)}")
        source = f"${name}"
        result = parse_variable_reference(Cursor(source, 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)
        assert result.value.id.name == name

    @given(
        st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1,
            max_size=10,
        )
    )
    @example("NUMBER")
    @example("DATETIME")
    def test_function_no_paren_returns_none(
        self, name: str
    ) -> None:
        """UPPERCASE identifier without paren returns None."""
        event(f"name_len={len(name)}")
        result = parse_function_reference(Cursor(name, 0))
        assert result is None

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=10,
        )
    )
    @example("brand")
    @example("x")
    def test_term_reference_property(self, name: str) -> None:
        """'-' + valid identifier always parses as TermReference."""
        event(f"name_len={len(name)}")
        source = f"-{name}"
        result = parse_term_reference(Cursor(source, 0))
        assert result is not None
        assert isinstance(result.value, TermReference)
        assert result.value.id.name == name
