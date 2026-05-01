# mypy: ignore-errors
"""Split test cases from tests/test_syntax_serializer_roundtrip.py."""

from tests.syntax_serializer_roundtrip_cases import *  # noqa: F403 - shared split test support

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
