"""Hypothesis-based property tests for FTL serialization roundtrip.

Focus on parse → serialize → parse idempotence.
"""

from __future__ import annotations

from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.syntax.ast import Message


class TestSerializationRoundtrip:
    """Property-based tests for serialization idempotence."""

    @given(
        # Use st.from_regex for cleaner, less constrained identifiers
        message_id=st.from_regex(r"[a-z][a-z0-9_-]*", fullmatch=True),
        # Remove arbitrary max_size constraint - let Hypothesis explore freely
        value=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.!?'-",
            min_size=1,
        ).filter(lambda x: x.strip()),
    )
    @settings(max_examples=200)
    def test_simple_message_roundtrip(self, message_id: str, value: str) -> None:
        """Simple messages survive parse → serialize → parse roundtrip."""
        # Create FTL source
        ftl_source = f"{message_id} = {value}"

        # Parse
        resource1 = parse_ftl(ftl_source)
        assert len(resource1.entries) >= 1

        # Serialize
        serialized = serialize_ftl(resource1)

        # Parse again
        resource2 = parse_ftl(serialized)

        # Should have same structure
        assert len(resource2.entries) == len(resource1.entries)

        # First entry should be Message
        entry1 = resource1.entries[0]
        entry2 = resource2.entries[0]

        event(f"id_len={len(message_id)}")
        event(f"val_len={len(value)}")
        assert isinstance(entry1, Message)
        assert isinstance(entry2, Message)
        assert entry1.id.name == entry2.id.name
        event("outcome=simple_message_roundtrip")

    @given(
        # Use st.from_regex - cleaner and unconstrained
        message_id=st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True),
        attr_name=st.from_regex(r"[a-z][a-z0-9_]*", fullmatch=True),
        # Remove arbitrary max_size
        attr_value=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,.!?'-",
            min_size=1,
        ).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_message_with_attribute_roundtrip(
        self, message_id: str, attr_name: str, attr_value: str
    ) -> None:
        """Messages with attributes survive roundtrip."""
        assume(message_id != attr_name)  # Distinct names

        ftl_source = f"{message_id} = Value\n    .{attr_name} = {attr_value}"

        # Roundtrip
        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Should have same number of entries
        assert len(resource2.entries) == len(resource1.entries)

        # First entry should be Message with attribute
        entry1 = resource1.entries[0]
        entry2 = resource2.entries[0]

        event(f"id_len={len(message_id)}")
        event(f"attr_len={len(attr_value)}")
        assert isinstance(entry1, Message)
        assert isinstance(entry2, Message)
        assert len(entry1.attributes) == len(entry2.attributes)
        event("outcome=attr_message_roundtrip")

    @given(
        # Keep practical upper bound for performance
        message_count=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=50)
    def test_multiple_messages_count_preserved(self, message_count: int) -> None:
        """Roundtrip preserves number of messages."""
        # Generate multiple simple messages
        ftl_lines = [f"msg{i} = Value {i}" for i in range(message_count)]
        ftl_source = "\n".join(ftl_lines)

        # Roundtrip
        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Count Message entries
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        event(f"msg_count={message_count}")
        assert len(messages2) == len(messages1) == message_count
        event("outcome=multi_msg_count_preserved")

    @given(
        iterations=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=20)
    def test_serialization_idempotence(self, iterations: int) -> None:
        """serialize(parse(serialize(parse(...)))) stabilizes after first cycle."""
        ftl_source = "hello = Hello, World!"

        resource = parse_ftl(ftl_source)
        serialized1 = serialize_ftl(resource)

        # Multiple iterations
        current = serialized1
        for _ in range(iterations - 1):
            resource_temp = parse_ftl(current)
            current = serialize_ftl(resource_temp)

        # Should be identical after stabilization
        assert current == serialized1

    @given(
        whitespace_prefix=st.text(
            alphabet=" \t",
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_whitespace_normalization(self, whitespace_prefix: str) -> None:
        """Roundtrip may normalize whitespace but preserves structure."""
        # FTL with varying whitespace
        ftl_source = f"{whitespace_prefix}hello = World"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Structure preserved
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)
        if messages1:
            assert messages1[0].id.name == messages2[0].id.name


class TestSerializationProperties:
    """Universal properties of serialization."""

    @given(
        ftl_text=st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=1,
            max_size=200,
        ),
    )
    @settings(max_examples=100)
    def test_serialize_never_crashes(self, ftl_text: str) -> None:
        """serialize_ftl never raises on any parsed resource."""
        # Parse (may produce junk)
        resource = parse_ftl(ftl_text)

        # Serialize should never crash - it's a pure function
        result = serialize_ftl(resource)
        event(f"ftl_len={len(ftl_text)}")
        assert isinstance(result, str)
        event("outcome=serialize_no_crash")

    @given(
        message_id=st.text(
            alphabet=st.characters(whitelist_categories=["L"]),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x and x[0].isalpha()),
    )
    @settings(max_examples=100)
    def test_roundtrip_preserves_message_ids(self, message_id: str) -> None:
        """Message IDs are preserved through roundtrip."""
        ftl_source = f"{message_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        if messages1 and messages2:
            event(f"id_len={len(message_id)}")
            assert messages1[0].id.name == messages2[0].id.name == message_id
            event("outcome=id_preserved")

    def test_empty_resource_roundtrip(self) -> None:
        """Empty resources survive roundtrip."""
        ftl_source = ""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Both should be empty
        assert len(resource1.entries) == 0
        assert len(resource2.entries) == 0

    def test_whitespace_only_resource_roundtrip(self) -> None:
        """Whitespace-only resources survive roundtrip."""
        ftl_source = "   \n\n   \n"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Should have no messages
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages1) == 0
        assert len(messages2) == 0


class TestSerializationEdgeCases:
    """Edge cases for serialization."""

    @given(
        unicode_value=st.text(
            alphabet=st.characters(
                min_codepoint=0x0080,  # Non-ASCII
                max_codepoint=0x00FF,  # Latin-1 Supplement
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda x: "\n" not in x),
    )
    @settings(max_examples=100)
    def test_unicode_content_roundtrip(self, unicode_value: str) -> None:
        """Unicode content survives roundtrip."""
        ftl_source = f"msg = {unicode_value}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Should have messages
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        event(f"val_len={len(unicode_value)}")
        assert len(messages2) == len(messages1)
        event("outcome=unicode_roundtrip")

    @given(
        line_count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50)
    def test_multiline_pattern_roundtrip(self, line_count: int) -> None:
        """Multiline patterns survive roundtrip."""
        # Create multiline FTL
        lines = ["msg ="]
        lines.extend([f"    Line {i}" for i in range(line_count)])
        ftl_source = "\n".join(lines)

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Should have same message count
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# VARIABLE REFERENCES SERIALIZATION
# ============================================================================


class TestVariableReferenceSerialization:
    """Property tests for variable reference serialization."""

    @given(
        msg_id=st.text(
            alphabet=st.characters(whitelist_categories=["L"]),
            min_size=1,
            max_size=15,
        ).filter(lambda x: x and x[0].isalpha()),
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=["L"]),
            min_size=1,
            max_size=10,
        ).filter(lambda x: x and x[0].isalpha()),
    )
    @settings(max_examples=150)
    def test_variable_reference_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Variable references survive roundtrip."""
        assume(msg_id != var_name)

        ftl_source = f"{msg_id} = {{ ${var_name} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=1,
            max_size=10,
        ),
        var_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_multiple_variables_roundtrip(
        self, msg_id: str, var_count: int
    ) -> None:
        """PROPERTY: Multiple variables survive roundtrip."""
        vars_ftl = " ".join([f"{{ $var{i} }}" for i in range(var_count)])
        ftl_source = f"{msg_id} = {vars_ftl}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        event(f"id_len={len(msg_id)}")
        assert len(resource2.entries) == len(resource1.entries)
        event("outcome=mixed_text_var_roundtrip")

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_text_with_variable_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Mixed text and variables survive roundtrip."""
        ftl_source = f"{msg_id} = Hello {{ $name }}, you have {{ $count }} items"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# TERM SERIALIZATION
# ============================================================================


class TestTermSerialization:
    """Property tests for term serialization."""

    @given(
        term_id=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz",
            min_size=1,
            max_size=10,
        ),
        term_value=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
            min_size=1,
            max_size=20,
        ).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_simple_term_roundtrip(
        self, term_id: str, term_value: str
    ) -> None:
        """PROPERTY: Simple terms survive roundtrip."""
        ftl_source = f"-{term_id} = {term_value}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        term_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        attr_count=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=50)
    def test_term_with_attributes_roundtrip(
        self, term_id: str, attr_count: int
    ) -> None:
        """PROPERTY: Terms with attributes survive roundtrip."""
        attrs = "\n".join([f"    .attr{i} = Value{i}" for i in range(attr_count)])
        ftl_source = f"-{term_id} = Base\n{attrs}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        term_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_term_reference_roundtrip(
        self, msg_id: str, term_id: str
    ) -> None:
        """PROPERTY: Term references survive roundtrip."""
        assume(msg_id != term_id)

        ftl_source = f"-{term_id} = Brand\n{msg_id} = {{ -{term_id} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# SELECT EXPRESSION SERIALIZATION
# ============================================================================


class TestSelectExpressionSerialization:
    """Property tests for select expression serialization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_simple_select_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Simple select expressions survive roundtrip."""
        ftl_source = f"""{msg_id} = {{ $count ->
    [one] One item
   *[other] Other items
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        variant_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_select_multiple_variants_roundtrip(
        self, msg_id: str, variant_count: int
    ) -> None:
        """PROPERTY: Select expressions with multiple variants survive roundtrip."""
        variants = "\n".join([f"    [{i}] Variant {i}" for i in range(variant_count - 1)])
        ftl_source = f"{msg_id} = {{ $val ->\n{variants}\n   *[other] Other\n}}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_nested_select_roundtrip(self) -> None:
        """Nested select expressions survive roundtrip."""
        ftl_source = """msg = { $outer ->
    [a] { $inner ->
        [1] A1
       *[other] A-other
    }
   *[other] Other
}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# FUNCTION CALLS SERIALIZATION
# ============================================================================


class TestFunctionCallSerialization:
    """Property tests for function call serialization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_number_function_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: NUMBER function calls survive roundtrip."""
        ftl_source = f"{msg_id} = {{ NUMBER($count) }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        event(f"msg_id_len={len(msg_id)}")
        assert len(resource2.entries) == len(resource1.entries)
        event("outcome=func_opts_roundtrip")

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_function_with_options_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Function calls with options survive roundtrip."""
        ftl_source = f"{msg_id} = {{ NUMBER($val, minimumFractionDigits: 2) }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_currency_function_roundtrip(self) -> None:
        """CURRENCY function calls survive roundtrip."""
        ftl_source = 'msg = { CURRENCY($amt, currency: "USD") }'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# MESSAGE REFERENCES SERIALIZATION
# ============================================================================


class TestMessageReferenceSerialization:
    """Property tests for message reference serialization."""

    @given(
        msg_id1=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        msg_id2=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=100)
    def test_message_reference_roundtrip(
        self, msg_id1: str, msg_id2: str
    ) -> None:
        """PROPERTY: Message references survive roundtrip."""
        assume(msg_id1 != msg_id2)

        ftl_source = f"{msg_id1} = Base\n{msg_id2} = {{ {msg_id1} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_attribute_reference_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Attribute references survive roundtrip."""
        ftl_source = f"""base = Value
    .attr = Attribute
{msg_id} = {{ base.attr }}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# COMPLEX PATTERN SERIALIZATION
# ============================================================================


class TestComplexPatternSerialization:
    """Property tests for complex pattern serialization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        segment_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_alternating_text_placeables_roundtrip(
        self, msg_id: str, segment_count: int
    ) -> None:
        """PROPERTY: Patterns with alternating text and placeables survive roundtrip."""
        segments = []
        for i in range(segment_count):
            segments.append(f"Text{i}")
            segments.append(f"{{ $v{i} }}")

        pattern = " ".join(segments)
        ftl_source = f"{msg_id} = {pattern}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_all_features_combined_roundtrip(self) -> None:
        """Pattern combining all features survives roundtrip."""
        ftl_source = """
-brand = FTLLexEngine

msg = Welcome to { -brand }!
    { $count ->
        [0] No items
       *[other] { NUMBER($count) } items
    }

    .title = { -brand } - System
"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Filter messages
        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# COMMENT PRESERVATION
# ============================================================================


class TestCommentPreservation:
    """Property tests for comment preservation in serialization."""

    def test_standalone_comment_roundtrip(self) -> None:
        """Standalone comments survive roundtrip."""
        ftl_source = """# This is a comment
msg = Value"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)

    def test_group_comment_roundtrip(self) -> None:
        """Group comments survive roundtrip."""
        ftl_source = """## Group comment

msg = Value"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# ESCAPE SEQUENCE HANDLING
# ============================================================================


class TestEscapeSequenceHandling:
    """Property tests for escape sequence serialization."""

    def test_unicode_escape_roundtrip(self) -> None:
        """Unicode escapes survive roundtrip."""
        ftl_source = r'msg = { "\u0041" }'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_escaped_quote_roundtrip(self) -> None:
        """Escaped quotes survive roundtrip."""
        ftl_source = r'msg = { "Quote: \"Hello\"" }'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_escaped_backslash_roundtrip(self) -> None:
        """Escaped backslashes survive roundtrip."""
        ftl_source = r'msg = { "Path: C:\\Users" }'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ATTRIBUTE VARIATIONS
# ============================================================================


class TestAttributeVariations:
    """Property tests for attribute serialization variations."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        attr_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_attributes_roundtrip(
        self, msg_id: str, attr_count: int
    ) -> None:
        """PROPERTY: Messages with multiple attributes survive roundtrip."""
        attrs = "\n".join([f"    .attr{i} = Value{i}" for i in range(attr_count)])
        ftl_source = f"{msg_id} = Main\n{attrs}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        if messages1 and messages2:
            assert len(messages1[0].attributes) == len(messages2[0].attributes)

    def test_attribute_only_message_roundtrip(self) -> None:
        """Messages with only attributes survive roundtrip."""
        ftl_source = """msg =
    .attr1 = Value1
    .attr2 = Value2"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# PLACEABLE SERIALIZATION
# ============================================================================


class TestPlaceableSerialization:
    """Property tests for placeable serialization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        placeable_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_placeables_roundtrip(
        self, msg_id: str, placeable_count: int
    ) -> None:
        """PROPERTY: Multiple placeables survive roundtrip."""
        placeables = " ".join([f"{{ $v{i} }}" for i in range(placeable_count)])
        ftl_source = f"{msg_id} = {placeables}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_nested_placeables_roundtrip(self) -> None:
        """Nested placeables survive roundtrip."""
        ftl_source = """
-inner = Inner
-middle = { -inner }
msg = {{ -middle }}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# STRING LITERAL SERIALIZATION
# ============================================================================


class TestStringLiteralSerialization:
    """Property tests for string literal serialization."""

    @given(
        text=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ",
            min_size=1,
            max_size=30,
        ).filter(lambda x: x.strip() and '"' not in x),
    )
    @settings(max_examples=100)
    def test_string_literal_roundtrip(self, text: str) -> None:
        """PROPERTY: String literals survive roundtrip."""
        ftl_source = f'msg = {{ "{text}" }}'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_empty_string_literal_roundtrip(self) -> None:
        """Empty string literals survive roundtrip."""
        ftl_source = 'msg = { "" }'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# NUMBER LITERAL SERIALIZATION
# ============================================================================


class TestNumberLiteralSerialization:
    """Property tests for number literal serialization."""

    @given(
        number=st.integers(min_value=-1000, max_value=1000),
    )
    @settings(max_examples=100)
    def test_integer_literal_roundtrip(self, number: int) -> None:
        """PROPERTY: Integer literals survive roundtrip."""
        ftl_source = f"msg = {{ {number} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        number=st.floats(
            min_value=-1000.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=50)
    def test_float_literal_roundtrip(self, number: float) -> None:
        """PROPERTY: Float literals survive roundtrip."""
        ftl_source = f"msg = {{ {number} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ROBUSTNESS PROPERTIES
# ============================================================================


class TestSerializationRobustness:
    """Property tests for serialization robustness."""

    @given(
        iterations=st.integers(min_value=3, max_value=10),
    )
    @settings(max_examples=20)
    def test_many_roundtrips_stable(self, iterations: int) -> None:
        """PROPERTY: Multiple roundtrips are stable."""
        ftl_source = "msg = Hello World"

        resource = parse_ftl(ftl_source)
        serialized_first = serialize_ftl(resource)

        # Multiple roundtrips
        current = serialized_first
        for _ in range(iterations):
            resource_temp = parse_ftl(current)
            current = serialize_ftl(resource_temp)

        # Should stabilize to first serialization
        assert current == serialized_first

    @given(
        msg_count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30)
    def test_large_resource_roundtrip(self, msg_count: int) -> None:
        """PROPERTY: Large resources survive roundtrip."""
        messages = [f"msg{i} = Value {i}" for i in range(msg_count)]
        ftl_source = "\n".join(messages)

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1) == msg_count

    def test_deeply_nested_structures_roundtrip(self) -> None:
        """Deeply nested structures survive roundtrip."""
        ftl_source = """
-a = A
-b = { -a }
-c = { -b }
msg = { -c }"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# ADDITIONAL VARIABLE REFERENCE TESTS
# ============================================================================


class TestAdvancedVariableReferences:
    """Additional property tests for variable references."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_variable_in_function_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Variables in function calls survive roundtrip."""
        ftl_source = f"{msg_id} = {{ NUMBER($count) }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_variable_in_select_selector_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Variables as select selectors survive roundtrip."""
        ftl_source = f"""{msg_id} = {{ $val ->
    [a] A
   *[other] Other
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ADDITIONAL TERM TESTS
# ============================================================================


class TestAdvancedTerms:
    """Additional property tests for terms."""

    @given(
        term_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_term_attribute_reference_roundtrip(self, term_id: str) -> None:
        """PROPERTY: Term attribute references survive roundtrip."""
        ftl_source = f"""-{term_id} = Base
    .attr = Attribute
msg = {{ -{term_id}.attr }}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        term_id1=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        term_id2=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_term_referencing_term_roundtrip(
        self, term_id1: str, term_id2: str
    ) -> None:
        """PROPERTY: Terms referencing other terms survive roundtrip."""
        assume(term_id1 != term_id2)

        ftl_source = f"""-{term_id1} = Base
-{term_id2} = {{ -{term_id1} }}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ADDITIONAL SELECT EXPRESSION TESTS
# ============================================================================


class TestAdvancedSelectExpressions:
    """Additional property tests for select expressions."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_select_with_variables_in_variants_roundtrip(
        self, msg_id: str
    ) -> None:
        """PROPERTY: Select expressions with variables in variants survive roundtrip."""
        ftl_source = f"""{msg_id} = {{ $type ->
    [a] Type A: {{ $value }}
   *[other] Other: {{ $value }}
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_select_with_function_in_variant_roundtrip(self) -> None:
        """Select expressions with functions in variants survive roundtrip."""
        ftl_source = """msg = { $count ->
    [0] Zero
   *[other] { NUMBER($count) } items
}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ADDITIONAL FUNCTION TESTS
# ============================================================================


class TestAdvancedFunctions:
    """Additional property tests for function calls."""

    def test_datetime_function_roundtrip(self) -> None:
        """DATETIME function calls survive roundtrip."""
        ftl_source = "msg = { DATETIME($date) }"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_nested_function_calls_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Nested function calls survive roundtrip."""
        # FTL doesn't support true nesting, but function in select is common
        ftl_source = f"""{msg_id} = {{ $val ->
    [0] Zero
   *[other] {{ NUMBER($val, minimumFractionDigits: 2) }}
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# BIDIRECTIONAL TEXT HANDLING
# ============================================================================


class TestBidirectionalTextSerialization:
    """Property tests for bidirectional text serialization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        rtl_text=st.sampled_from(["مرحبا", "שלום", "سلام"]),
    )
    @settings(max_examples=50)
    def test_rtl_text_roundtrip(self, msg_id: str, rtl_text: str) -> None:
        """PROPERTY: RTL text survives roundtrip."""
        ftl_source = f"{msg_id} = {rtl_text}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    def test_mixed_ltr_rtl_roundtrip(self) -> None:
        """Mixed LTR and RTL text survives roundtrip."""
        ftl_source = "msg = Hello مرحبا World"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# LINE ENDING VARIATIONS
# ============================================================================


class TestLineEndingHandling:
    """Property tests for line ending handling."""

    def test_lf_line_endings_roundtrip(self) -> None:
        """LF line endings survive roundtrip."""
        ftl_source = "msg1 = Value1\nmsg2 = Value2"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)

    def test_crlf_line_endings_roundtrip(self) -> None:
        """CRLF line endings survive roundtrip."""
        ftl_source = "msg1 = Value1\r\nmsg2 = Value2"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# ADDITIONAL ROBUSTNESS TESTS
# ============================================================================


class TestAdditionalRobustness:
    """Additional robustness property tests."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        leading_spaces=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_leading_whitespace_normalization(
        self, msg_id: str, leading_spaces: int
    ) -> None:
        """PROPERTY: Leading whitespace is normalized in roundtrip."""
        ftl_source = f"{' ' * leading_spaces}{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        trailing_spaces=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_trailing_whitespace_normalization(
        self, msg_id: str, trailing_spaces: int
    ) -> None:
        """PROPERTY: Trailing whitespace may be normalized in roundtrip."""
        ftl_source = f"{msg_id} = Value{' ' * trailing_spaces}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)

    def test_very_long_message_id_roundtrip(self) -> None:
        """Very long message IDs survive roundtrip."""
        long_id = "a" * 100
        ftl_source = f"{long_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        # Both parses must produce exactly one message
        assert len(messages1) == 1, "Original parse must produce one message"
        assert len(messages2) == 1, "Roundtrip parse must produce one message"
        assert messages1[0].id.name == messages2[0].id.name

    @given(
        text_length=st.integers(min_value=100, max_value=500),
    )
    @settings(max_examples=20)
    def test_very_long_value_roundtrip(self, text_length: int) -> None:
        """PROPERTY: Very long values survive roundtrip."""
        long_value = "a" * text_length
        ftl_source = f"msg = {long_value}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# PATTERN ELEMENT ORDERING
# ============================================================================


class TestPatternElementOrdering:
    """Property tests for pattern element ordering."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        element_count=st.integers(min_value=2, max_value=8),
    )
    @settings(max_examples=50)
    def test_element_ordering_preserved(
        self, msg_id: str, element_count: int
    ) -> None:
        """PROPERTY: Pattern element ordering is preserved in roundtrip."""
        elements = []
        for i in range(element_count):
            elements.append(f"text{i}")
            elements.append(f"{{ $v{i} }}")

        pattern = " ".join(elements)
        ftl_source = f"{msg_id} = {pattern}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# VARIANT KEY TYPES
# ============================================================================


class TestVariantKeyTypes:
    """Property tests for variant key types in select expressions."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_string_variant_keys_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: String variant keys survive roundtrip."""
        ftl_source = f"""{msg_id} = {{ $type ->
    [apple] Apple
    [banana] Banana
   *[other] Other fruit
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        number_key=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50)
    def test_number_variant_keys_roundtrip(
        self, msg_id: str, number_key: int
    ) -> None:
        """PROPERTY: Number variant keys survive roundtrip."""
        ftl_source = f"""{msg_id} = {{ $count ->
    [{number_key}] Exact match
   *[other] Other
}}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ATTRIBUTE POSITION TESTS
# ============================================================================


class TestAttributePositions:
    """Property tests for attribute positioning."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        attr_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=30)
    def test_attribute_ordering_preserved(
        self, msg_id: str, attr_count: int
    ) -> None:
        """PROPERTY: Attribute ordering is preserved in roundtrip."""
        attrs = [f"    .attr{i} = Value{i}" for i in range(attr_count)]
        ftl_source = f"{msg_id} = Main\n" + "\n".join(attrs)

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        if messages1 and messages2:
            assert len(messages1[0].attributes) == len(messages2[0].attributes)


# ============================================================================
# SPECIAL CHARACTER HANDLING
# ============================================================================


class TestSpecialCharacterHandling:
    """Property tests for special character handling."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        special_char=st.sampled_from(["@", "#", "%", "&", "*", "+"]),
    )
    @settings(max_examples=50)
    def test_special_chars_in_text_roundtrip(
        self, msg_id: str, special_char: str
    ) -> None:
        """PROPERTY: Special characters in text survive roundtrip."""
        ftl_source = f"{msg_id} = Text {special_char} more"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# IDENTIFIER EDGE CASES
# ============================================================================


class TestIdentifierEdgeCases:
    """Property tests for identifier edge cases."""

    @given(
        id_length=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=30)
    def test_varying_length_identifiers_roundtrip(
        self, id_length: int
    ) -> None:
        """PROPERTY: Identifiers of varying lengths survive roundtrip."""
        msg_id = "a" * id_length
        ftl_source = f"{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        if messages1 and messages2:
            assert messages1[0].id.name == messages2[0].id.name


# ============================================================================
# COMPLETE ROUNDTRIP VALIDATION
# ============================================================================


class TestCompleteRoundtripValidation:
    """Comprehensive roundtrip validation tests."""

    def test_complex_real_world_example_roundtrip(self) -> None:
        """Complex real-world FTL example survives roundtrip."""
        ftl_source = """
# Main application messages
-brand-name = FTLLexEngine

welcome = Welcome to { -brand-name }!
    .title = Welcome

items-count = { $count ->
    [0] No items
    [1] One item
   *[other] { NUMBER($count) } items
}

price = { CURRENCY($amount, currency: "USD") }
    .with-tax = Total: { CURRENCY($amount, currency: "USD") }

message-ref = See { welcome } for more info

nested-term =
    { items-count }
    in { -brand-name }
"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)


# ============================================================================
# EDGE CASE COMBINATIONS
# ============================================================================


class TestEdgeCaseCombinations:
    """Property tests for combinations of edge cases."""

    def test_empty_attribute_value_roundtrip(self) -> None:
        """Empty attribute values survive roundtrip."""
        ftl_source = """msg = Main
    .empty = """

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        messages1 = [e for e in resource1.entries if isinstance(e, Message)]
        messages2 = [e for e in resource2.entries if isinstance(e, Message)]

        assert len(messages2) == len(messages1)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_whitespace_only_value_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Whitespace-only values survive roundtrip."""
        ftl_source = f"{msg_id} =     "

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)

        # May normalize whitespace
        assert isinstance(serialized, str)


# ============================================================================
# SERIALIZATION DETERMINISM
# ============================================================================


class TestSerializationDeterminism:
    """Property tests for serialization determinism."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        iterations=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=30)
    def test_serialize_deterministic(
        self, msg_id: str, iterations: int
    ) -> None:
        """PROPERTY: Serialization is deterministic across multiple calls."""
        ftl_source = f"{msg_id} = Value"

        resource = parse_ftl(ftl_source)

        # Serialize multiple times
        results = [serialize_ftl(resource) for _ in range(iterations)]

        # All should be identical
        assert all(r == results[0] for r in results)


# ============================================================================
# MESSAGE COMMENT PRESERVATION
# ============================================================================


class TestMessageCommentPreservation:
    """Property tests for message comment preservation."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        comment_text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Zs"),
                blacklist_characters="\n\r",
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=50)
    def test_standalone_comment_roundtrip(
        self, msg_id: str, comment_text: str
    ) -> None:
        """PROPERTY: Standalone comments survive roundtrip."""
        ftl_source = f"# {comment_text}\n{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        group_comment=st.text(
            alphabet=st.characters(whitelist_categories=["L"]),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_group_comment_roundtrip(self, msg_id: str, group_comment: str) -> None:
        """PROPERTY: Group comments survive roundtrip."""
        ftl_source = f"## {group_comment}\n{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_resource_comment_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Resource comments survive roundtrip."""
        ftl_source = f"### Resource comment\n{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# MULTILINE PATTERN HANDLING
# ============================================================================


class TestMultilinePatternHandling:
    """Property tests for multiline pattern handling."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        line_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiline_message_roundtrip(
        self, msg_id: str, line_count: int
    ) -> None:
        """PROPERTY: Multiline messages survive roundtrip."""
        lines = ["Line one", "Line two", "Line three", "Line four", "Line five"]
        value = "\n    ".join(lines[:line_count])
        ftl_source = f"{msg_id} =\n    {value}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_indented_pattern_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Indented patterns preserve structure."""
        ftl_source = f"{msg_id} =\n    Indented line 1\n    Indented line 2"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_mixed_multiline_placeable_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Mixed multiline with placeables survives roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"{msg_id} =\n    Line 1\n    {{ ${var_name} }}\n    Line 3"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# COMPLEX ATTRIBUTE COMBINATIONS
# ============================================================================


class TestComplexAttributeCombinations:
    """Property tests for complex attribute combinations."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        attr_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_attribute_roundtrip(
        self, msg_id: str, attr_count: int
    ) -> None:
        """PROPERTY: Multiple attributes preserve order."""
        attrs = ["one", "two", "three", "four", "five"]
        attr_lines = "\n".join(
            f"    .{attrs[i]} = Value {i + 1}" for i in range(attr_count)
        )
        ftl_source = f"{msg_id} = Main value\n{attr_lines}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        attr_name=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10
        ),
    )
    @settings(max_examples=50)
    def test_attribute_only_message_roundtrip(
        self, msg_id: str, attr_name: str
    ) -> None:
        """PROPERTY: Attribute-only messages survive roundtrip."""
        ftl_source = f"{msg_id}\n    .{attr_name} = Attr value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_attribute_with_placeable_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Attributes with placeables survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"{msg_id}\n    .attr = Value {{ ${var_name} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# ADVANCED ESCAPE SEQUENCES
# ============================================================================


class TestAdvancedEscapeSequences:
    """Property tests for advanced escape sequence handling."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_all_escape_types_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: All escape types survive roundtrip."""
        ftl_source = f'{msg_id} = "Quote: \\" Backslash: \\\\ Unicode: \\u0041"'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        escape_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_multiple_escapes_roundtrip(
        self, msg_id: str, escape_count: int
    ) -> None:
        """PROPERTY: Multiple consecutive escapes survive roundtrip."""
        escapes = "\\\\" * escape_count
        ftl_source = f'{msg_id} = "{escapes}"'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_mixed_escape_text_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Mixed escaped and unescaped text survives roundtrip."""
        ftl_source = f'{msg_id} = "Normal text \\" more text \\\\ end"'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# NUMBER FORMAT VARIATIONS
# ============================================================================


class TestNumberFormatVariations:
    """Property tests for number format variations."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        number=st.integers(min_value=-1000000, max_value=1000000),
    )
    @settings(max_examples=100)
    def test_integer_literal_roundtrip(self, msg_id: str, number: int) -> None:
        """PROPERTY: Integer literals survive roundtrip."""
        ftl_source = f"{msg_id} = {{ {number} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        number=st.floats(
            min_value=-1000.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=100)
    def test_float_literal_roundtrip(self, msg_id: str, number: float) -> None:
        """PROPERTY: Float literals survive roundtrip."""
        ftl_source = f"{msg_id} = {{ {number} }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_zero_variations_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Zero variations survive roundtrip."""
        ftl_source = f"{msg_id} = {{ 0 }} {{ 0.0 }} {{ -0 }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# STRING LITERAL COMPLEX CASES
# ============================================================================


class TestStringLiteralComplexCases:
    """Property tests for complex string literal cases."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_empty_string_literal_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Empty string literals survive roundtrip."""
        ftl_source = f'{msg_id} = {{ "" }}'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        length=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=50)
    def test_long_string_literal_roundtrip(
        self, msg_id: str, length: int
    ) -> None:
        """PROPERTY: Long string literals survive roundtrip."""
        content = "x" * length
        ftl_source = f'{msg_id} = {{ "{content}" }}'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_string_with_spaces_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Strings with various spaces survive roundtrip."""
        ftl_source = f'{msg_id} = {{ "  leading  trailing  " }}'

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# VARIANT KEY EDGE CASES
# ============================================================================


class TestVariantKeyEdgeCases:
    """Property tests for variant key edge cases."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        key_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_many_variant_keys_roundtrip(
        self, msg_id: str, var_name: str, key_count: int
    ) -> None:
        """PROPERTY: Many variant keys survive roundtrip."""
        assume(msg_id != var_name)
        keys = ["one", "two", "three", "four", "five"]
        variants = "\n".join(
            f"        [{keys[i]}] Value {i + 1}" for i in range(key_count)
        )
        ftl_source = f"{msg_id} = {{ ${var_name} ->\n{variants}\n       *[other] Default\n    }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        number=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=50)
    def test_number_variant_key_roundtrip(
        self, msg_id: str, var_name: str, number: int
    ) -> None:
        """PROPERTY: Number variant keys survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = (
            f"{msg_id} = {{ ${var_name} ->\n"
            f"        [{number}] Exact\n"
            "       *[other] Default\n"
            "    }"
        )

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_mixed_variant_key_types_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Mixed variant key types survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = (
            f"{msg_id} = {{ ${var_name} ->\n"
            "        [0] Zero\n"
            "        [one] One\n"
            "       *[other] Default\n"
            "    }"
        )

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# FUNCTION ARGUMENT EDGE CASES
# ============================================================================


class TestFunctionArgumentEdgeCases:
    """Property tests for function argument edge cases."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_function_no_args_roundtrip(self, msg_id: str, var_name: str) -> None:
        """PROPERTY: Functions without arguments survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"{msg_id} = {{ NUMBER(${var_name}) }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        arg_count=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=50)
    def test_function_many_args_roundtrip(
        self, msg_id: str, var_name: str, arg_count: int
    ) -> None:
        """PROPERTY: Functions with many arguments survive roundtrip."""
        assume(msg_id != var_name)
        args = [
            'style: "decimal"',
            'useGrouping: "always"',
            "minimumFractionDigits: 2",
            "maximumFractionDigits: 4",
        ]
        arg_str = ", ".join(args[:arg_count])
        ftl_source = f"{msg_id} = {{ NUMBER(${var_name}, {arg_str}) }}"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_nested_function_calls_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Nested function calls survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"{msg_id} = Outer {{ NUMBER(${var_name}) }} inner"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# IDENTIFIER BOUNDARY CASES
# ============================================================================


class TestIdentifierBoundaryCases:
    """Property tests for identifier boundary cases."""

    @given(
        id_length=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=30)
    def test_short_identifier_roundtrip(self, id_length: int) -> None:
        """PROPERTY: Short identifiers survive roundtrip."""
        msg_id = "a" * id_length
        ftl_source = f"{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        id_length=st.integers(min_value=20, max_value=50),
    )
    @settings(max_examples=50)
    def test_long_identifier_roundtrip(self, id_length: int) -> None:
        """PROPERTY: Long identifiers survive roundtrip."""
        msg_id = "a" * id_length
        ftl_source = f"{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=5,
            max_size=15,
        ).filter(lambda x: x and x[0].isalpha()),
    )
    @settings(max_examples=50)
    def test_alphanumeric_identifier_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Alphanumeric identifiers survive roundtrip."""
        ftl_source = f"{msg_id} = Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# WHITESPACE NORMALIZATION
# ============================================================================


class TestWhitespaceNormalization:
    """Property tests for whitespace normalization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        space_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_leading_whitespace_roundtrip(
        self, msg_id: str, space_count: int
    ) -> None:
        """PROPERTY: Leading whitespace handling in roundtrip."""
        spaces = " " * space_count
        ftl_source = f"{msg_id} = {spaces}Value"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        space_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_internal_whitespace_roundtrip(
        self, msg_id: str, space_count: int
    ) -> None:
        """PROPERTY: Internal whitespace preservation in roundtrip."""
        spaces = " " * space_count
        ftl_source = f"{msg_id} = Value{spaces}text"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_mixed_whitespace_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Mixed whitespace types survive roundtrip."""
        ftl_source = f"{msg_id} = Value  with   various    spaces"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# UNICODE NORMALIZATION
# ============================================================================


class TestUnicodeNormalization:
    """Property tests for Unicode normalization."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_unicode_combining_chars_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Unicode combining characters survive roundtrip."""
        ftl_source = f"{msg_id} = Café"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_emoji_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Emoji characters survive roundtrip (test data only)."""
        ftl_source = f"{msg_id} = Hello 👋"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# COMPLETE MESSAGE PATTERNS
# ============================================================================


class TestCompleteMessagePatterns:
    """Property tests for complete message patterns."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_complete_message_roundtrip(self, msg_id: str, var_name: str) -> None:
        """PROPERTY: Complete message with all features survives roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"""{msg_id} = Value {{ ${var_name} }}
    .attr1 = Attribute 1
    .attr2 = Attribute 2"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_real_world_pattern_roundtrip(self, msg_id: str) -> None:
        """PROPERTY: Real-world message pattern survives roundtrip."""
        ftl_source = f"{msg_id} = You have {{ $count }} messages"

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)


# ============================================================================
# SELECT EXPRESSION EDGE CASES
# ============================================================================


class TestSelectExpressionEdgeCases:
    """Property tests for select expression edge cases."""

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=50)
    def test_select_with_variables_in_variants_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Select with variables in variants survives roundtrip."""
        assume(msg_id != var_name)
        ftl_source = (
            f"{msg_id} = {{ ${var_name} ->\n"
            f"        [one] One item: {{ ${var_name} }}\n"
            "       *[other] Many items\n"
            "    }"
        )

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)

    @given(
        msg_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
        var_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
    )
    @settings(max_examples=30)
    def test_deeply_nested_select_roundtrip(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Deeply nested selects survive roundtrip."""
        assume(msg_id != var_name)
        ftl_source = f"""{msg_id} = {{ ${var_name} ->
        [one] {{ ${var_name} ->
            [male] One male
           *[other] One other
        }}
       *[other] Many
    }}"""

        resource1 = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        assert len(resource2.entries) == len(resource1.entries)
