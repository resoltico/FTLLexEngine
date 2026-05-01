# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# MESSAGE REFERENCE WITH ATTRIBUTES
# ============================================================================


class TestMessageReferenceWithAttribute:
    """Coverage for lowercase message references with .attribute syntax."""

    def test_msg_dot_attr_inline(self) -> None:
        """Parse { msg.attr } in inline expression."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.attr }")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        p = msg.value.elements[0]
        assert isinstance(p, Placeable)
        ref = p.expression
        assert isinstance(ref, MessageReference)
        assert ref.id.name == "msg"
        assert ref.attribute is not None
        assert ref.attribute.name == "attr"

    def test_msg_dot_attr_in_attribute_value(self) -> None:
        """Parse { msg.help } in message attribute value."""
        parser = FluentParserV1()
        res = parser.parse(
            "key = Value\n    .tooltip = { msg.help }\n"
        )
        msg = res.entries[0]
        assert isinstance(msg, Message)
        attr = msg.attributes[0]
        assert isinstance(attr, Attribute)
        p = attr.value.elements[0]
        assert isinstance(p, Placeable)
        ref = p.expression
        assert isinstance(ref, MessageReference)
        assert ref.attribute is not None
        assert ref.attribute.name == "help"

    def test_msg_dot_missing_attr_name(self) -> None:
        """{ msg. } with missing attribute name."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg. }")
        assert len(res.entries) >= 1

    def test_msg_dot_invalid_attr(self) -> None:
        """{ msg.@ } with invalid attribute."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.@ }")
        assert res is not None

    def test_msg_dot_hash_attr(self) -> None:
        """{ msg.# } with invalid attribute."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.# }")
        assert len(res.entries) >= 1

    def test_mixed_identifiers_with_attributes(self) -> None:
        """Various identifier cases with attributes."""
        parser = FluentParserV1()
        cases = [
            ("key = { foo.bar }", "foo", "bar"),
            ("key = { a.b }", "a", "b"),
            ("key = { msg123.attr456 }", "msg123", "attr456"),
        ]
        for source, exp_msg, exp_attr in cases:
            res = parser.parse(source)
            msg = res.entries[0]
            assert isinstance(msg, Message), f"Failed: {source}"
            assert msg.value is not None
            p = msg.value.elements[0]
            assert isinstance(p, Placeable)
            ref = p.expression
            assert isinstance(ref, MessageReference)
            assert ref.id.name == exp_msg
            assert ref.attribute is not None
            assert ref.attribute.name == exp_attr
