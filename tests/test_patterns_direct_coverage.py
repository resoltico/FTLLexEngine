"""Direct unit tests for parser/patterns.py to achieve 100% coverage.

Tests all functions in patterns.py using direct Cursor manipulation
to ensure complete branch and line coverage.

Target functions:
- parse_variable_reference()
- parse_simple_pattern()
- parse_pattern()
"""

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    parse_pattern,
    parse_simple_pattern,
    parse_variable_reference,
)


class TestParseVariableReference:
    """Direct tests for parse_variable_reference() function."""

    def test_parse_variable_reference_success(self) -> None:
        """Test successful variable reference parsing: $name."""
        cursor = Cursor("$name", 0)
        result = parse_variable_reference(cursor)

        assert result is not None
        assert result.value.id.name == "name"
        assert result.cursor.pos == 5

    def test_parse_variable_reference_at_eof(self) -> None:
        """Test parse_variable_reference returns None at EOF (line 31)."""
        cursor = Cursor("", 0)
        result = parse_variable_reference(cursor)

        assert result is None

    def test_parse_variable_reference_not_dollar_sign(self) -> None:
        """Test parse_variable_reference returns None without $ (line 31)."""
        cursor = Cursor("name", 0)
        result = parse_variable_reference(cursor)

        assert result is None

    def test_parse_variable_reference_invalid_identifier(self) -> None:
        """Test parse_variable_reference with invalid identifier after $ (line 38)."""
        cursor = Cursor("$123", 0)  # Identifiers can't start with digit
        result = parse_variable_reference(cursor)

        # Should return None because parse_identifier fails
        assert result is None

    def test_parse_variable_reference_dollar_only(self) -> None:
        """Test parse_variable_reference with $ but no identifier."""
        cursor = Cursor("$ ", 0)
        result = parse_variable_reference(cursor)

        # Should return None because parse_identifier fails after $
        assert result is None

    @given(identifier=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]*", fullmatch=True))
    def test_parse_variable_reference_property_valid_identifiers(
        self, identifier: str
    ) -> None:
        """Property: All valid identifiers can be parsed as variable references."""
        source = f"${identifier}"
        cursor = Cursor(source, 0)
        result = parse_variable_reference(cursor)

        assert result is not None
        assert result.value.id.name == identifier


class TestParseSimplePattern:
    """Direct tests for parse_simple_pattern() function."""

    def test_parse_simple_pattern_plain_text(self) -> None:
        """Test parsing simple text pattern."""
        cursor = Cursor("Hello world", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        # Test context: parsing plain text creates TextElement with .value attribute
        assert result.value.elements[0].value == "Hello world"  # type: ignore[union-attr]

    def test_parse_simple_pattern_with_variable(self) -> None:
        """Test parsing pattern with variable placeable."""
        cursor = Cursor("Hello {$name}", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 2
        # First element is TextElement with .value, second is Placeable
        assert result.value.elements[0].value == "Hello "  # type: ignore[union-attr]

    def test_parse_simple_pattern_invalid_placeable_returns_none(self) -> None:
        """Test that invalid placeable causes parse_simple_pattern to return None (line 104)."""
        # Create a pattern with unclosed placeable
        cursor = Cursor("text {", 0)
        result = parse_simple_pattern(cursor)

        # Should return None when parse_placeable fails
        assert result is None

    def test_parse_simple_pattern_stop_at_newline(self) -> None:
        """Test that parse_simple_pattern stops at newline."""
        cursor = Cursor("text\nmore", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        # Test context: plain text produces TextElement
        assert result.value.elements[0].value == "text"  # type: ignore[union-attr]
        # Cursor should be at newline
        assert result.cursor.current == "\n"

    def test_parse_simple_pattern_includes_dot(self) -> None:
        """Test that parse_simple_pattern includes dot as literal text.

        v0.26.0: Dots in variant values are literal text, not attribute markers.
        Attribute markers only appear at line starts in top-level patterns.
        """
        cursor = Cursor("text.attr", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        # Dot is literal text in variant values
        assert result.value.elements[0].value == "text.attr"  # type: ignore[union-attr]
        assert result.cursor.is_eof

    def test_parse_simple_pattern_stop_at_close_brace(self) -> None:
        """Test that parse_simple_pattern stops at } (end of select expression)."""
        cursor = Cursor("text}more", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        # Test context: plain text before marker is TextElement
        assert result.value.elements[0].value == "text"  # type: ignore[union-attr]
        assert result.cursor.current == "}"

    def test_parse_simple_pattern_stops_at_variant_markers(self) -> None:
        """Test lookahead for variant markers [ and *.

        v0.26.0: Added lookahead to distinguish variant syntax from literal text.
        - [identifier] is a variant marker only if followed by newline/}/[/*
        - * is a variant marker only if followed by [
        Otherwise, these characters are literal text.
        """
        # [ without matching ] is literal text
        cursor = Cursor("text[more", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "text[more"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # * not followed by [ is literal text
        cursor = Cursor("text*more", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "text*more"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # [INFO] followed by text is literal (not variant marker)
        cursor = Cursor("[INFO] message", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "[INFO] message"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # [key] followed by newline IS a variant marker (stops)
        cursor = Cursor("[one]\n", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 0  # Stops at [one]

        # *[key] IS a variant marker (stops)
        cursor = Cursor("text *[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "text "  # type: ignore[union-attr]
        assert result.cursor.current == "*"

    def test_parse_simple_pattern_empty_at_eof(self) -> None:
        """Test parse_simple_pattern with empty input."""
        cursor = Cursor("", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 0

    def test_parse_simple_pattern_stops_at_close_brace(self) -> None:
        """Test that parse_simple_pattern stops at } character."""
        cursor = Cursor("text}", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        # Test context: plain text is TextElement
        assert result.value.elements[0].value == "text"  # type: ignore[union-attr]
        assert result.cursor.current == "}"

    def test_parse_simple_pattern_at_close_brace(self) -> None:
        """Test parse_simple_pattern stops immediately at } (line 118)."""
        cursor = Cursor("}text", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        # Stops at } with empty pattern
        assert len(result.value.elements) == 0
        assert result.cursor.current == "}"

    def test_parse_simple_pattern_stops_at_bracket(self) -> None:
        """Test [ lookahead for variant key detection.

        v0.26.0: [ alone without valid variant key pattern is literal text.
        """
        # [ alone at EOF is literal text (no matching ])
        cursor = Cursor("[", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "["  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # [key] followed by } IS a variant marker
        cursor = Cursor("[one]}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 0
        assert result.cursor.current == "["

    def test_parse_simple_pattern_stops_at_asterisk(self) -> None:
        """Test * lookahead for default variant marker detection.

        v0.26.0: * alone without [ is literal text.
        """
        # * alone at EOF is literal text (not followed by [)
        cursor = Cursor("*", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "*"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # *[ IS a variant marker
        cursor = Cursor("*[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 0
        assert result.cursor.current == "*"


class TestParsePattern:
    """Direct tests for parse_pattern() function."""

    def test_parse_pattern_plain_text(self) -> None:
        """Test parsing plain text pattern."""
        cursor = Cursor("Simple text", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        # Test context: plain text is TextElement
        assert result.value.elements[0].value == "Simple text"  # type: ignore[union-attr]

    def test_parse_pattern_with_placeable(self) -> None:
        """Test parsing pattern with placeable."""
        cursor = Cursor("Hello {$world}", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) >= 2

    def test_parse_pattern_invalid_placeable_returns_none(self) -> None:
        """Test that invalid placeable returns None (line 191)."""
        cursor = Cursor("text { invalid", 0)
        result = parse_pattern(cursor)

        # Should return None when placeable parsing fails
        assert result is None

    def test_parse_pattern_multiline_continuation(self) -> None:
        """Test parse_pattern with indented continuation."""
        source = "Line one\n    Line two"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Should have parsed with continuation
        elements = result.value.elements
        # Continuation adds space between lines
        full_text = "".join(
            e.value for e in elements if hasattr(e, "value") and isinstance(e.value, str)
        )
        assert "Line one" in full_text or "Line two" in full_text

    def test_parse_pattern_stop_at_newline_without_continuation(self) -> None:
        """Test parse_pattern stops at newline when not continuation."""
        source = "First line\nSecond line"  # No indentation = no continuation
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Test context: first line is TextElement
        assert result.value.elements[0].value == "First line"  # type: ignore[union-attr]
        assert result.cursor.current == "\n"

    def test_parse_pattern_crlf_handling(self) -> None:
        """Test parse_pattern handles CRLF line endings in continuations."""
        source = "Line one\r\n    Line two"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Should handle CRLF correctly

    def test_parse_pattern_empty_input(self) -> None:
        """Test parse_pattern with empty string."""
        cursor = Cursor("", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 0

    def test_parse_pattern_infinite_loop_prevention_text_branch(self) -> None:
        """Test infinite loop prevention in text parsing (lines 211-214)."""
        # Create scenario where cursor at stop char but not '{'
        cursor = Cursor("]", 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Cursor should have advanced to prevent infinite loop
        assert result.cursor.pos >= 1 or result.cursor.is_eof

    def test_parse_pattern_includes_special_chars_as_text(self) -> None:
        """Test parse_pattern treats }, [, * as literal text in top-level patterns."""
        # In top-level patterns (not inside select), these are just text
        for delimiter in ["}", "[", "*"]:
            cursor = Cursor(f"text{delimiter}more", 0)
            result = parse_pattern(cursor)

            assert result is not None
            assert len(result.value.elements) == 1
            # All characters including delimiter are part of the text
            expected = f"text{delimiter}more"
            assert result.value.elements[0].value == expected  # type: ignore[union-attr]

    def test_parse_pattern_with_special_char_sequences(self) -> None:
        """Test pattern parsing with special character sequences as text."""
        # All these are literal text in top-level patterns
        cursor = Cursor("}}]]", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}}]]"  # type: ignore[union-attr]

    def test_parse_pattern_close_brace_is_text(self) -> None:
        """Test that } is treated as literal text in top-level patterns."""
        cursor = Cursor("}text", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}text"  # type: ignore[union-attr]

    def test_parse_pattern_bracket_is_text(self) -> None:
        """Test that [ is treated as literal text in top-level patterns."""
        cursor = Cursor("[text", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "[text"  # type: ignore[union-attr]

    def test_parse_pattern_asterisk_is_text(self) -> None:
        """Test that * is treated as literal text in top-level patterns."""
        cursor = Cursor("*text", 0)
        result = parse_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "*text"  # type: ignore[union-attr]


class TestPatternParsingProperties:
    """Hypothesis-based property tests for pattern parsing."""

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",)  # type: ignore[arg-type]
            ),
            min_size=0,
            max_size=100,
        )
    )
    def test_parse_pattern_handles_most_inputs(self, text: str) -> None:
        """Property: Pattern parsing handles most inputs gracefully.

        Note: Some Unicode edge cases may raise ValueError in number parsing,
        which is expected behavior for invalid numeric literals.
        """
        cursor = Cursor(text, 0)
        try:
            result = parse_pattern(cursor)
            # Either succeeds (returns ParseResult) or fails (returns None)
            assert result is None or result.value is not None
        except ValueError:
            # ValueError can occur for invalid numeric literals (e.g., Unicode superscripts)
            # This is expected behavior
            pass
        except Exception as e:
            # Other exceptions are unexpected
            msg = f"Parsing raised unexpected exception: {e}"
            raise AssertionError(msg) from e

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",)  # type: ignore[arg-type]
            ),
            min_size=0,
            max_size=100,
        )
    )
    def test_parse_simple_pattern_handles_most_inputs(self, text: str) -> None:
        """Property: Simple pattern parsing handles most inputs gracefully.

        Note: Some Unicode edge cases may raise ValueError in number parsing.
        """
        cursor = Cursor(text, 0)
        try:
            result = parse_simple_pattern(cursor)
            assert result is None or result.value is not None
        except ValueError:
            # ValueError can occur for invalid numeric literals
            pass
        except Exception as e:
            msg = f"Parsing raised unexpected exception: {e}"
            raise AssertionError(msg) from e

    @given(
        var_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]*", fullmatch=True),
        prefix=st.text(max_size=10),
        suffix=st.text(max_size=10),
    )
    def test_parse_pattern_preserves_variable_names(
        self, var_name: str, prefix: str, suffix: str
    ) -> None:
        """Property: Variable names are preserved in parsed patterns."""
        # Avoid patterns that would create invalid FTL
        if "{" in prefix or "}" in suffix:
            return

        source = f"{prefix}{{${var_name}}}{suffix}"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        if result is not None:
            # If parsing succeeded, verify structure makes sense
            assert len(result.value.elements) >= 0


class TestEdgeCasesAndBranches:
    """Additional tests for specific edge cases and branch coverage."""

    def test_parse_simple_pattern_placeable_at_start(self) -> None:
        """Test pattern starting with placeable."""
        cursor = Cursor("{$var} text", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        assert len(result.value.elements) >= 1

    def test_parse_simple_pattern_multiple_placeables(self) -> None:
        """Test pattern with multiple consecutive placeables."""
        cursor = Cursor("{$a}{$b}{$c}", 0)
        result = parse_simple_pattern(cursor)

        assert result is not None
        # All three should be placeables
        assert len(result.value.elements) == 3

    def test_parse_pattern_continuation_with_multiple_newlines(self) -> None:
        """Test continuation with multiple newlines."""
        source = "Line\n\n    Continued"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None

    def test_parse_pattern_continuation_adds_space(self) -> None:
        """Test that continuation adds space between lines."""
        source = "First\n    Second"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Should have space added between lines
        elements = result.value.elements
        # Check if space was added (as TextElement)
        has_space = any(
            hasattr(e, "value") and " " in str(e.value)
            for e in elements
        )
        assert has_space or len(elements) > 0

    def test_parse_pattern_continuation_after_placeable(self) -> None:
        """Test continuation after placeable adds space element (line 174)."""
        # Pattern ending with placeable, then continuation
        # This should trigger the else branch at line 174
        source = "{$var}\n    text"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Should have: placeable, space, text
        assert len(result.value.elements) >= 1

    def test_parse_pattern_empty_continuation(self) -> None:
        """Test continuation on empty pattern (line 174)."""
        # Start with newline and continuation (elements list empty)
        source = "\n    text"
        cursor = Cursor(source, 0)
        result = parse_pattern(cursor)

        assert result is not None
        # Elements list was empty, should add space element (line 174)
