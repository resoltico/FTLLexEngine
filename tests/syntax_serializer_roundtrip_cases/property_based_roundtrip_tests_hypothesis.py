# mypy: ignore-errors
"""Split test cases from tests/test_syntax_serializer_roundtrip.py."""

from tests.syntax_serializer_roundtrip_cases import *  # noqa: F403 - shared split test support

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
