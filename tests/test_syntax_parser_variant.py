"""Tests for FTL-GRAMMAR-003: Fix variant marker blank handling per Fluent EBNF.

Tests that variant keys with spaces after opening bracket [ parse correctly
according to Fluent EBNF: VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"
"""

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Identifier, Junk, Message, Placeable, SelectExpression
from ftllexengine.syntax.parser import FluentParserV1


class TestVariantMarkerBlankHandling:
    """Test variant marker parsing with blanks per Fluent EBNF."""

    def test_variant_key_with_space_after_opening_bracket(self) -> None:
        """Variant keys with space after [ should parse correctly."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [ one] Item
   *[other] Items
}
"""
        resource = parser.parse(ftl)

        # Should parse without junk
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.id.name == "msg"
        assert msg.value is not None

        # Check that pattern contains SelectExpression
        assert len(msg.value.elements) == 1
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)

        select = placeable.expression
        assert isinstance(select, SelectExpression)
        assert len(select.variants) == 2

        # Check variant keys (filter out NumberLiteral keys)
        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert "one" in keys
        assert "other" in keys

    def test_variant_key_with_multiple_spaces_after_opening_bracket(self) -> None:
        """Variant keys with multiple spaces after [ should parse correctly."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [  one] Item
   *[   other] Items
}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)

        # Verify variant keys parsed correctly despite multiple spaces
        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert "one" in keys
        assert "other" in keys

    def test_variant_key_numeric_with_space_after_bracket(self) -> None:
        """Numeric variant keys with space after [ should parse correctly."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [ 1] One
    [ 2] Two
   *[other] Many
}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)
        assert len(select.variants) == 3

    def test_variant_key_no_space_still_works(self) -> None:
        """Variant keys without space after [ should still work (backwards compat)."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [one] Item
   *[other] Items
}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

    def test_literal_bracket_text_not_confused_with_variant(self) -> None:
        """Literal bracket in text should not be confused with variant marker."""
        parser = FluentParserV1()
        ftl = "msg = Text with [ bracket not variant"

        resource = parser.parse(ftl)

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        msg = messages[0]
        # Should parse as simple text, not as failed variant
        assert msg.value is not None

    def test_variant_key_with_space_before_bracket_close(self) -> None:
        """Spaces before closing ] should be allowed per EBNF."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [one ] Item
   *[other ] Items
}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)

        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert "one" in keys
        assert "other" in keys

    def test_variant_key_with_spaces_both_sides(self) -> None:
        """Spaces on both sides of key should be allowed per EBNF."""
        parser = FluentParserV1()
        ftl = """
msg = { $count ->
    [ one ] Item
   *[ other ] Items
}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)

        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert "one" in keys
        assert "other" in keys


# =============================================================================
# Property-Based Tests (HypoFuzz-Discoverable)
# =============================================================================


@pytest.mark.hypothesis
@given(
    spaces_after_open=st.integers(min_value=0, max_value=10),
    spaces_before_close=st.integers(min_value=0, max_value=10),
)
def test_variant_keys_with_arbitrary_blank_count(
    spaces_after_open: int, spaces_before_close: int
) -> None:
    """Variant keys should parse with arbitrary number of spaces.

    Property: For any valid number of spaces (0-10) before/after variant key,
    the parser should successfully parse the variant without producing Junk.
    """
    event(f"spaces_after={spaces_after_open}")
    parser = FluentParserV1()

    # Create FTL with specified number of spaces
    space_after = " " * spaces_after_open
    space_before = " " * spaces_before_close
    ftl = f"""
msg = {{ $count ->
    [{space_after}one{space_before}] Item
   *[other] Items
}}
"""
    resource = parser.parse(ftl)

    # Should parse successfully
    junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
    messages = [e for e in resource.entries if isinstance(e, Message)]
    assert len(junk_entries) == 0
    assert len(messages) == 1

    msg = messages[0]
    assert msg.value is not None
    placeable = msg.value.elements[0]
    assert isinstance(placeable, Placeable)
    select = placeable.expression
    assert isinstance(select, SelectExpression)

    # Verify "one" variant was parsed
    keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
    assert "one" in keys


class TestLongIdentifierVariantKeys:
    """Tests for variant keys with long identifiers (v0.89.0 fix).

    Prior to v0.89.0, MAX_LOOKAHEAD_CHARS (128) was smaller than
    _MAX_IDENTIFIER_LENGTH (256), causing variant keys with 129-256 char
    identifiers to be misparsed as literal text.
    """

    def test_variant_key_with_max_length_identifier(self) -> None:
        """Variant key with maximum length identifier (256 chars) parses correctly."""
        parser = FluentParserV1()
        long_id = "a" * 256  # Maximum allowed identifier length
        ftl = f"""
msg = {{ $type ->
    [{long_id}] Long variant
   *[other] Default
}}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]

        assert len(junk_entries) == 0, "Should not produce junk"
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)

        # Verify long identifier variant was parsed
        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert long_id in keys

    def test_variant_key_with_200_char_identifier(self) -> None:
        """Variant key with 200 char identifier parses correctly.

        This tests the previously broken range (129-256 chars).
        """
        parser = FluentParserV1()
        medium_id = "x" * 200
        ftl = f"""
selector = {{ $option ->
    [{medium_id}] Medium long option
   *[default] Fallback
}}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]

        assert len(junk_entries) == 0
        assert len(messages) == 1

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)

        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert medium_id in keys

    def test_variant_key_with_129_char_identifier(self) -> None:
        """Variant key with 129 char identifier parses correctly.

        This is the boundary case - previously 128 was the limit.
        """
        parser = FluentParserV1()
        boundary_id = "b" * 129
        ftl = f"""
edge = {{ $case ->
    [{boundary_id}] Boundary case
   *[other] Other
}}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]

        assert len(junk_entries) == 0
        assert len(messages) == 1

        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)
        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert boundary_id in keys

    def test_variant_key_with_spaces_and_long_identifier(self) -> None:
        """Variant key with spaces and long identifier parses correctly.

        Tests combined space handling and long identifier support.
        """
        parser = FluentParserV1()
        long_id = "identifier_" * 20  # 220 chars
        ftl = f"""
combined = {{ $value ->
    [ {long_id} ] With spaces
   *[short] Short key
}}
"""
        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]

        assert len(junk_entries) == 0
        assert len(messages) == 1

        from ftllexengine.syntax.ast import Identifier  # noqa: PLC0415

        msg = messages[0]
        assert msg.value is not None
        placeable = msg.value.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)
        keys = [v.key.name for v in select.variants if isinstance(v.key, Identifier)]
        assert long_id in keys
