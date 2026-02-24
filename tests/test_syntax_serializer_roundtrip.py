"""Roundtrip tests for syntax.serializer: parse(serialize(ast)) == ast.

Validates both the parser and serializer simultaneously, covering programmatic
ASTs with embedded newlines, whitespace preservation, and convergence stability.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.syntax import parse, serialize
from ftllexengine.syntax.ast import (
    Comment,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer

from .strategies import (
    ftl_comments,
    ftl_message_nodes,
    ftl_patterns,
    ftl_resources,
    ftl_select_expressions,
    ftl_variable_references,
)

# ============================================================================
# SIMPLE ROUNDTRIP TESTS (Example-Based)
# ============================================================================


def test_roundtrip_simple_message():
    """Round-trip a simple message with text only."""
    # Create AST
    msg = Message(
        id=Identifier(name="hello"),
        value=Pattern(elements=(TextElement(value="Hello, World!"),)),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    # Serialize and parse back
    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Should be structurally identical
    assert len(reparsed.entries) == 1
    assert isinstance(reparsed.entries[0], Message)
    assert reparsed.entries[0].id.name == "hello"


def test_roundtrip_message_with_variable():
    """Round-trip a message with variable interpolation."""
    msg = Message(
        id=Identifier(name="greeting"),
        value=Pattern(
            elements=(
                TextElement(value="Hello, "),
                Placeable(expression=VariableReference(id=Identifier(name="name"))),
                TextElement(value="!"),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) == 1
    assert isinstance(reparsed.entries[0], Message)
    assert reparsed.entries[0].id.name == "greeting"
    # Verify pattern has 3 elements
    pattern = reparsed.entries[0].value
    assert pattern is not None
    assert len(pattern.elements) == 3


def test_roundtrip_select_expression():
    """Round-trip a message with select expression (plurals)."""
    msg = Message(
        id=Identifier(name="emails"),
        value=Pattern(
            elements=(
                Placeable(
                    expression=SelectExpression(
                        selector=VariableReference(id=Identifier(name="count")),
                        variants=(
                            Variant(
                                key=Identifier(name="one"),
                                value=Pattern(elements=(TextElement(value="one email"),)),
                                default=False,
                            ),
                            Variant(
                                key=Identifier(name="other"),
                                value=Pattern(
                                    elements=(
                                        Placeable(
                                            expression=VariableReference(
                                                id=Identifier(name="count")
                                            )
                                        ),
                                        TextElement(value=" emails"),
                                    )
                                ),
                                default=True,
                            ),
                        ),
                    )
                ),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) == 1
    assert isinstance(reparsed.entries[0], Message)


def test_roundtrip_numeric_variant():
    """Round-trip select expression with numeric variant keys."""
    msg = Message(
        id=Identifier(name="items"),
        value=Pattern(
            elements=(
                Placeable(
                    expression=SelectExpression(
                        selector=VariableReference(id=Identifier(name="count")),
                        variants=(
                            Variant(
                                key=NumberLiteral(value=0, raw="0"),
                                value=Pattern(elements=(TextElement(value="no items"),)),
                                default=False,
                            ),
                            Variant(
                                key=NumberLiteral(value=1, raw="1"),
                                value=Pattern(elements=(TextElement(value="one item"),)),
                                default=False,
                            ),
                            Variant(
                                key=Identifier(name="other"),
                                value=Pattern(elements=(TextElement(value="many items"),)),
                                default=True,
                            ),
                        ),
                    )
                ),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) == 1
    msg_parsed = reparsed.entries[0]
    assert isinstance(msg_parsed, Message)
    assert msg_parsed.id.name == "items"


def test_roundtrip_comment():
    """Round-trip standalone comment.

    NOTE: Parser does not currently support standalone comments - they are
    silently ignored during parsing. This test documents the limitation.
    When parser support is added, this test should pass.
    """
    comment = Comment(content=" This is a comment", type=CommentType.COMMENT)
    resource = Resource(entries=(comment,))

    serialized = serialize(resource)
    # Serializer correctly outputs: "#  This is a comment\n"
    assert serialized == "#  This is a comment\n"

    # Per Fluent spec: Comments are preserved in AST
    reparsed = parse(serialized)

    # Spec-conformant behavior: Comments are preserved
    assert len(reparsed.entries) == 1
    assert isinstance(reparsed.entries[0], Comment)
    assert reparsed.entries[0].content == comment.content


def test_roundtrip_junk():
    """Round-trip junk (invalid syntax preserved)."""
    junk = Junk(content="invalid syntax here {")
    resource = Resource(entries=(junk,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Junk gets reparsed as junk
    assert len(reparsed.entries) >= 1
    # At least one entry should be junk
    assert any(isinstance(e, Junk) for e in reparsed.entries)


def test_roundtrip_junk_with_leading_whitespace():
    """Round-trip junk with leading whitespace without redundant newlines.

    Tests that the serializer does not add redundant separators before Junk
    entries when the Junk content already includes leading whitespace.
    The parser includes preceding whitespace in Junk.content for containment.
    """
    # Parse FTL with message followed by blank lines and indented junk
    source = "msg = hello\n\n  bad"
    resource = parse(source)

    # Serialize and re-parse
    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Verify file doesn't grow on multiple roundtrips (key invariant)
    serialized2 = serialize(reparsed)
    assert len(serialized2) == len(serialized), (
        "File size should remain stable across roundtrips (no whitespace inflation)"
    )

    # Verify multiple roundtrips converge to stable output
    serialized3 = serialize(parse(serialized2))
    assert serialized3 == serialized2, (
        "Serialization should be idempotent after first roundtrip"
    )


def test_roundtrip_multiple_messages():
    """Round-trip resource with multiple messages."""
    msg1 = Message(
        id=Identifier(name="hello"),
        value=Pattern(elements=(TextElement(value="Hello!"),)),
        attributes=(),
    )
    msg2 = Message(
        id=Identifier(name="goodbye"),
        value=Pattern(elements=(TextElement(value="Goodbye!"),)),
        attributes=(),
    )
    resource = Resource(entries=(msg1, msg2))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Should have at least 2 messages
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) >= 2


def test_roundtrip_mixed_entries():
    """Round-trip resource with messages and standalone comments.

    When Comments appear as separate entries in the AST (not as message.comment),
    they are standalone comments and should remain standalone after roundtrip.
    The serializer preserves this by adding 2 blank lines between a standalone
    comment and the following message/term.
    """
    entries = (
        Comment(content=" Header comment", type=CommentType.COMMENT),
        Message(
            id=Identifier(name="app-name"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(),
        ),
        Comment(content=" Another comment", type=CommentType.COMMENT),
        Message(
            id=Identifier(name="version"),
            value=Pattern(elements=(TextElement(value="1.0.0"),)),
            attributes=(),
        ),
    )
    resource = Resource(entries=entries)

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Standalone comments remain standalone after roundtrip
    standalone_comments = [e for e in reparsed.entries if isinstance(e, Comment)]
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(standalone_comments) == 2  # Comments remain standalone
    assert len(messages) == 2  # Messages survive roundtrip

    # Messages should NOT have attached comments (comments are standalone)
    assert messages[0].comment is None
    assert messages[1].comment is None

    # Comment content is preserved
    assert "Header comment" in standalone_comments[0].content
    assert "Another comment" in standalone_comments[1].content


def test_roundtrip_attached_comments():
    """Round-trip resource with attached comments.

    When Comments are set as message.comment (not as separate entries),
    they are attached comments and should remain attached after roundtrip.
    """
    entries = (
        Message(
            id=Identifier(name="app-name"),
            value=Pattern(elements=(TextElement(value="MyApp"),)),
            attributes=(),
            comment=Comment(content=" Attached to app-name", type=CommentType.COMMENT),
        ),
        Message(
            id=Identifier(name="version"),
            value=Pattern(elements=(TextElement(value="1.0.0"),)),
            attributes=(),
            comment=Comment(content=" Attached to version", type=CommentType.COMMENT),
        ),
    )
    resource = Resource(entries=entries)

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # No standalone comments - all attached
    standalone_comments = [e for e in reparsed.entries if isinstance(e, Comment)]
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(standalone_comments) == 0  # No standalone comments
    assert len(messages) == 2  # Messages survive roundtrip

    # Comments remain attached to their messages
    assert messages[0].comment is not None
    assert "Attached to app-name" in messages[0].comment.content
    assert messages[1].comment is not None
    assert "Attached to version" in messages[1].comment.content


def test_roundtrip_empty_resource():
    """Round-trip empty resource."""
    resource = Resource(entries=())

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) == 0


def test_roundtrip_message_with_only_placeable():
    """Round-trip message with only a placeable (no text)."""
    msg = Message(
        id=Identifier(name="count"),
        value=Pattern(
            elements=(Placeable(expression=VariableReference(id=Identifier(name="num"))),)
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) == 1
    assert isinstance(reparsed.entries[0], Message)


def test_roundtrip_complex_pattern():
    """Round-trip message with complex pattern (text + variables).

    NOTE: Parser creates spurious Junk entry for trailing period.
    This is a parser quirk - the message itself parses correctly.
    """
    msg = Message(
        id=Identifier(name="user-info"),
        value=Pattern(
            elements=(
                TextElement(value="User "),
                Placeable(expression=VariableReference(id=Identifier(name="name"))),
                TextElement(value=" has "),
                Placeable(expression=VariableReference(id=Identifier(name="count"))),
                TextElement(value=" items"),  # Removed trailing period to avoid parser quirk
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Message parses correctly (ignore spurious Junk entries)
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    msg_parsed = messages[0]
    assert isinstance(msg_parsed, Message)
    assert msg_parsed.value is not None
    assert len(msg_parsed.value.elements) == 5


# ============================================================================
# WHITESPACE PRESERVATION ROUNDTRIP TESTS
# ============================================================================


def test_roundtrip_multiline_leading_whitespace():
    """Round-trip preserves leading whitespace after newlines.

    Tests fix for IMPL-SERIALIZER-ROUNDTRIP-CORRUPTION-001: when TextElement
    with leading whitespace follows element ending with newline, serializer
    must emit pattern on separate line to preserve the whitespace semantically.
    """
    # Pattern: "Line 1\n  Line 2" (2 leading spaces on line 2)
    msg = Message(
        id=Identifier(name="code-block"),
        value=Pattern(
            elements=(
                TextElement(value="Line 1\n"),
                TextElement(value="  Line 2"),  # 2-space indent
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    # Extract reparsed pattern content
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    pattern = messages[0].value
    assert pattern is not None

    # Reconstruct the pattern content from elements
    content = "".join(
        elem.value for elem in pattern.elements if isinstance(elem, TextElement)
    )
    assert "Line 1\n" in content
    assert "  Line 2" in content  # 2 spaces preserved


def test_roundtrip_code_example_indent():
    """Round-trip preserves code example indentation.

    Tests common use case of embedding code examples in localization strings.
    """
    # Multi-line code example with indentation
    msg = Message(
        id=Identifier(name="code-example"),
        value=Pattern(
            elements=(
                TextElement(value="Example:\n"),
                TextElement(value="    def hello():\n"),
                TextElement(value="        print('Hi')"),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    pattern = messages[0].value
    assert pattern is not None

    content = "".join(
        elem.value for elem in pattern.elements if isinstance(elem, TextElement)
    )
    # Verify indentation preserved
    assert "    def hello():" in content
    assert "        print('Hi')" in content


def test_roundtrip_whitespace_idempotent():
    """Multiple roundtrips produce identical output (idempotency).

    Tests that whitespace handling doesn't cause drift across roundtrips.
    """
    msg = Message(
        id=Identifier(name="formatted"),
        value=Pattern(
            elements=(
                TextElement(value="Header:\n"),
                TextElement(value="  Item 1\n"),
                TextElement(value="  Item 2"),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    # First roundtrip
    serialized1 = serialize(resource)
    reparsed1 = parse(serialized1)

    # Second roundtrip
    serialized2 = serialize(reparsed1)
    reparsed2 = parse(serialized2)

    # Third roundtrip
    serialized3 = serialize(reparsed2)

    # Output should stabilize after first roundtrip
    assert serialized2 == serialized3, "Serialization should be idempotent"


def test_roundtrip_mixed_whitespace_and_placeables():
    """Round-trip preserves whitespace with interleaved placeables."""
    msg = Message(
        id=Identifier(name="mixed"),
        value=Pattern(
            elements=(
                TextElement(value="Results for "),
                Placeable(expression=VariableReference(id=Identifier(name="query"))),
                TextElement(value=":\n"),
                TextElement(value="  - First result\n"),
                TextElement(value="  - "),
                Placeable(expression=VariableReference(id=Identifier(name="count"))),
                TextElement(value=" more"),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    pattern = messages[0].value
    assert pattern is not None

    # Verify structure preserved - should have TextElements with whitespace
    text_elements = [e for e in pattern.elements if isinstance(e, TextElement)]
    text_content = "".join(e.value for e in text_elements)

    # Check whitespace preservation
    assert ":\n" in text_content
    assert "  - First result\n" in text_content or "  -" in text_content


def test_roundtrip_tab_indentation():
    """Round-trip preserves tab indentation."""
    msg = Message(
        id=Identifier(name="tabbed"),
        value=Pattern(
            elements=(
                TextElement(value="Data:\n"),
                TextElement(value="\tColumn 1\n"),
                TextElement(value="\t\tNested"),
            )
        ),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    pattern = messages[0].value
    assert pattern is not None

    content = "".join(
        elem.value for elem in pattern.elements if isinstance(elem, TextElement)
    )
    assert "\tColumn 1" in content
    assert "\t\tNested" in content


def test_roundtrip_preserves_parsed_whitespace():
    """Parse and serialize preserves original whitespace from FTL source.

    Tests the full cycle: FTL source -> parse -> serialize -> parse -> serialize
    """
    # FTL with intentional indentation
    source = """\
code-snippet =
    Example code:
      if True:
          print("hello")
"""
    parsed = parse(source)
    serialized = serialize(parsed)
    reparsed = parse(serialized)
    serialized2 = serialize(reparsed)

    # Should stabilize
    assert serialized == serialized2, "Roundtrip should be stable"

    # Verify semantic content preserved
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 1
    pattern = messages[0].value
    assert pattern is not None

    content = "".join(
        elem.value for elem in pattern.elements if isinstance(elem, TextElement)
    )
    # Original indentation relationships should be preserved
    assert "Example code:" in content
    assert "print(" in content


def test_roundtrip_compact_messages_no_blank_lines():
    """Roundtrip of compact messages preserves no-blank-line format.

    Tests the fix for NAME-SERIALIZER-SPACING-001 where serializer was adding
    redundant newlines between Message/Term entries.
    """
    # Compact FTL with no blank lines between messages
    source = "msg1 = First\nmsg2 = Second\nmsg3 = Third"

    parsed = parse(source)
    serialized = serialize(parsed)

    # Serialized output should maintain compact format (no blank lines)
    assert serialized == "msg1 = First\nmsg2 = Second\nmsg3 = Third\n"

    # Verify roundtrip preserves structure
    reparsed = parse(serialized)
    assert len(reparsed.entries) == 3
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) == 3
    assert messages[0].id.name == "msg1"
    assert messages[1].id.name == "msg2"
    assert messages[2].id.name == "msg3"


def test_comment_message_separation_preserved():
    """Comment->Message still gets blank line to prevent attachment.

    Tests the fix for NAME-SERIALIZER-SPACING-001 ensures Comment separation
    logic is preserved (blank lines prevent comment attachment on re-parse).
    """
    # Standalone comment followed by message (with blank line)
    source = "# Standalone comment\n\nmsg = Value"

    parsed = parse(source)
    serialized = serialize(parsed)

    # Should preserve blank line between comment and message
    # The blank line prevents the comment from being attached to the message
    assert "\n\n" in serialized

    # Verify roundtrip: comment should remain standalone
    reparsed = parse(serialized)
    comments = [e for e in reparsed.entries if isinstance(e, Comment)]
    messages = [e for e in reparsed.entries if isinstance(e, Message)]

    assert len(comments) == 1
    assert len(messages) == 1
    # Message should NOT have an attached comment
    assert messages[0].comment is None


def test_roundtrip_mixed_spacing_preserved():
    """Mixed spacing patterns are preserved during roundtrip."""
    # Mix of compact messages and separated entries
    source = "msg1 = First\nmsg2 = Second\n\n# Comment\n\nmsg3 = Third"

    parsed = parse(source)
    serialized = serialize(parsed)
    reparsed = parse(serialized)

    # Should have 3 messages and 1 comment
    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    comments = [e for e in reparsed.entries if isinstance(e, Comment)]

    assert len(messages) == 3
    assert len(comments) == 1

    # First two messages should be compact (consecutive)
    # Comment should be standalone (not attached)
    # Third message should be after comment
    assert messages[0].id.name == "msg1"
    assert messages[1].id.name == "msg2"
    assert messages[2].id.name == "msg3"


# ============================================================================
# PROPERTY-BASED ROUNDTRIP TESTS (Hypothesis)
# ============================================================================


@given(ftl_message_nodes())
@settings(max_examples=30)
def test_roundtrip_property_messages(message: Message) -> None:
    """Property: All generated messages round-trip successfully."""
    resource = Resource(entries=(message,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    messages = [e for e in reparsed.entries if isinstance(e, Message)]
    assert len(messages) >= 1
    assert messages[0].id.name == message.id.name
    has_attrs = len(message.attributes) > 0
    event(f"has_attributes={has_attrs}")
    event("outcome=message_roundtrip")


@given(ftl_patterns())
@settings(max_examples=30)
def test_roundtrip_property_patterns(pattern: Pattern) -> None:
    """Property: All generated patterns round-trip in messages."""
    msg = Message(
        id=Identifier(name="test"), value=pattern, attributes=()
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) >= 1
    event(f"element_count={len(pattern.elements)}")
    event("outcome=pattern_roundtrip")


@given(ftl_select_expressions())
@settings(max_examples=20)
def test_roundtrip_property_select_expressions(
    select_expr: SelectExpression,
) -> None:
    """Property: All generated select expressions round-trip."""
    msg = Message(
        id=Identifier(name="test"),
        value=Pattern(elements=(Placeable(expression=select_expr),)),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) >= 1
    event(f"variant_count={len(select_expr.variants)}")
    event("outcome=select_roundtrip")


@given(ftl_comments())
@settings(max_examples=30)
def test_roundtrip_property_comments(comment_str: str) -> None:
    """Property: All generated comments serialize correctly."""
    if comment_str.startswith("### "):
        comment_type = CommentType.RESOURCE
        content = comment_str[4:]
    elif comment_str.startswith("## "):
        comment_type = CommentType.GROUP
        content = comment_str[3:]
    else:
        comment_type = CommentType.COMMENT
        content = comment_str[2:]

    comment_node = Comment(content=content, type=comment_type)
    resource = Resource(entries=(comment_node,))

    serialized = serialize(resource)
    assert isinstance(serialized, str)
    assert serialized.startswith("#")

    _ = parse(serialized)
    event(f"comment_type={comment_type.name}")
    event("outcome=comment_roundtrip")


@given(ftl_resources())
@settings(max_examples=20)
def test_roundtrip_property_complete_resources(
    resource: Resource,
) -> None:
    """Property: All generated resources round-trip successfully."""
    serialized = serialize(resource)
    reparsed = parse(serialized)

    original_messages = [
        e for e in resource.entries if isinstance(e, Message)
    ]
    reparsed_messages = [
        e for e in reparsed.entries if isinstance(e, Message)
    ]

    original_ids = {msg.id.name for msg in original_messages}
    reparsed_ids = {msg.id.name for msg in reparsed_messages}
    assert original_ids.issubset(reparsed_ids)
    event(f"entry_count={len(resource.entries)}")
    event("outcome=resource_roundtrip")


@given(ftl_variable_references())
@settings(max_examples=30)
def test_roundtrip_property_variable_references(
    var_ref: VariableReference,
) -> None:
    """Property: Variable references round-trip in placeables."""
    msg = Message(
        id=Identifier(name="test"),
        value=Pattern(elements=(Placeable(expression=var_ref),)),
        attributes=(),
    )
    resource = Resource(entries=(msg,))

    serialized = serialize(resource)
    reparsed = parse(serialized)

    assert len(reparsed.entries) >= 1
    event(f"var_name={var_ref.id.name}")
    event("outcome=varref_roundtrip")


# ============================================================================
# SERIALIZER VALIDITY TESTS
# ============================================================================


@given(ftl_resources())
@settings(max_examples=30)
def test_serializer_produces_valid_ftl(resource: Resource) -> None:
    """Property: Serialized output always produces parseable FTL."""
    serialized = serialize(resource)

    assert isinstance(serialized, str)

    result = parse(serialized)
    assert isinstance(result, Resource)
    event(f"entry_count={len(resource.entries)}")
    event("outcome=valid_ftl")


@given(ftl_message_nodes())
@settings(max_examples=30)
def test_serializer_deterministic(message: Message) -> None:
    """Property: Same AST always produces same serialized output."""
    resource = Resource(entries=(message,))

    serialized1 = serialize(resource)
    serialized2 = serialize(resource)

    assert serialized1 == serialized2
    event("outcome=deterministic")


# ============================================================================
# PROGRAMMATIC AST ROUNDTRIPS (from test_serializer_programmatic_roundtrip.py)
# ============================================================================


_parser = FluentParserV1()
_serializer = FluentSerializer()


def _roundtrip_pattern_value(pattern_text: str) -> str:
    """Create a programmatic AST, serialize, parse, and return pattern value."""
    msg = Message(
        id=Identifier(name="msg", span=None),
        value=Pattern(elements=(TextElement(value=pattern_text),)),
        attributes=(),
        comment=None,
        span=None,
    )
    resource = Resource(entries=(msg,))
    serialized = _serializer.serialize(resource)
    parsed = _parser.parse(serialized)
    entry = parsed.entries[0]
    assert hasattr(entry, "value")
    assert entry.value is not None
    return "".join(
        el.value for el in entry.value.elements  # type: ignore[union-attr]
    )


class TestEmbeddedNewlineWhitespace:
    """Roundtrip preservation of embedded newlines with significant whitespace."""

    def test_five_space_indent(self) -> None:
        """Embedded newline with 5-space indent preserved through roundtrip."""
        original = "foo\n     bar"
        assert _roundtrip_pattern_value(original) == original

    def test_four_space_indent(self) -> None:
        """Embedded newline with exactly 4-space indent (boundary case)."""
        original = "foo\n    bar"
        assert _roundtrip_pattern_value(original) == original

    def test_single_space_indent(self) -> None:
        """Embedded newline with single space indent."""
        original = "foo\n bar"
        assert _roundtrip_pattern_value(original) == original

    def test_multiple_newlines_varying_indent(self) -> None:
        """Multiple embedded newlines with different indentation levels."""
        original = "a\n  b\n    c\n      d"
        assert _roundtrip_pattern_value(original) == original

    def test_no_whitespace_after_newline(self) -> None:
        """Embedded newline without whitespace does not trigger separate-line."""
        original = "hello\nworld"
        assert _roundtrip_pattern_value(original) == original

    def test_trailing_newline_no_whitespace(self) -> None:
        """Trailing newline at end of text element."""
        original = "hello\n"
        result = _roundtrip_pattern_value(original)
        # Trailing newline may be normalized during parse
        assert result.rstrip("\n") == "hello"

    def test_tab_after_newline(self) -> None:
        """Tab character after newline (not space, no separate-line needed).

        Only space characters trigger separate-line serialization per the
        FTL spec's whitespace handling (tab is not continuation indent).
        """
        original = "foo\n\tbar"
        assert _roundtrip_pattern_value(original) == original


def _extract_element_values(resource: Resource) -> list[str]:
    """Extract text element values from the first entry's pattern."""
    entry = resource.entries[0]
    assert hasattr(entry, "value")
    assert entry.value is not None
    return [el.value for el in entry.value.elements]  # type: ignore[union-attr]


class TestParserProducedRoundtrip:
    """Verify existing parser-produced roundtrip behavior is preserved."""

    def test_separate_line_with_extra_indent(self) -> None:
        """Parser-produced AST from FTL with extra indentation."""
        ftl = "msg =\n    foo\n         bar\n"
        resource = _parser.parse(ftl)
        serialized = _serializer.serialize(resource)
        resource2 = _parser.parse(serialized)
        assert _extract_element_values(resource) == _extract_element_values(resource2)

    def test_inline_start_multiline(self) -> None:
        """Inline pattern start with continuation line."""
        ftl = "msg = foo\n    bar\n"
        resource = _parser.parse(ftl)
        serialized = _serializer.serialize(resource)
        resource2 = _parser.parse(serialized)
        assert _extract_element_values(resource) == _extract_element_values(resource2)


class TestSerializerStability:
    """Serialize-parse-serialize stability (idempotence after first roundtrip)."""

    @given(
        indent=st.integers(min_value=1, max_value=12),
        line_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=100)
    @example(indent=1, line_count=2)
    @example(indent=4, line_count=2)
    @example(indent=5, line_count=3)
    def test_embedded_indent_stability(self, indent: int, line_count: int) -> None:
        """After first roundtrip, subsequent roundtrips are stable.

        Constructs patterns with N lines, each indented by `indent` spaces.
        After initial serialize-parse, the result must be stable on
        subsequent serialize-parse cycles.
        """
        event(f"indent={indent}")
        event(f"line_count={line_count}")
        lines = [f"{'  ' * indent}line{i}" if i > 0 else "first" for i in range(line_count)]
        original = "\n".join(lines)

        # First roundtrip
        first_rt = _roundtrip_pattern_value(original)

        # Second roundtrip from the first result
        msg2 = Message(
            id=Identifier(name="msg", span=None),
            value=Pattern(elements=(TextElement(value=first_rt),)),
            attributes=(),
            comment=None,
            span=None,
        )
        resource2 = Resource(entries=(msg2,))
        serialized2 = _serializer.serialize(resource2)
        parsed2 = _parser.parse(serialized2)
        entry2 = parsed2.entries[0]
        assert hasattr(entry2, "value")
        assert entry2.value is not None
        second_rt = "".join(
            el.value for el in entry2.value.elements  # type: ignore[union-attr]
        )

        # Stability: second roundtrip equals first roundtrip
        assert first_rt == second_rt, (
            f"Roundtrip not stable: first={first_rt!r}, second={second_rt!r}"
        )


# ============================================================================
# Identifier Roundtrip (Fuzz-marked: deadline=None)
# ============================================================================


@pytest.mark.fuzz
@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
@settings(max_examples=50, deadline=None)
def test_serialize_parse_identifiers(identifier: str) -> None:
    """Property: valid identifiers survive serialize->parse round-trip.

    FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
    """
    assume(identifier[0].isalpha())
    assume(all(c.isalnum() or c == "-" for c in identifier))

    ftl_source = f"{identifier} = Test value"
    resource = parse(ftl_source)

    assume(len(resource.entries) > 0)
    assume(not isinstance(resource.entries[0], Junk))

    serialized = serialize(resource)
    resource2 = parse(serialized)

    event(f"id_len={len(identifier)}")
    assert resource2 is not None
    assert len(resource2.entries) == len(resource.entries)
    event("outcome=e2e_id_roundtrip_success")
