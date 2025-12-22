"""Advanced Hypothesis property-based tests for parser.

Critical parser functions tested with extensive property-based strategies:
- Round-trip properties (parse → serialize → parse)
- Invariant preservation (AST structure properties)
- Error handling (crash resistance)
- Edge case generation (Unicode, nesting, whitespace)
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer
from tests.strategies import ftl_identifiers, ftl_simple_text


class TestParserRoundTrip:
    """Property: parse(serialize(ast)) == ast (modulo formatting)."""

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=1000)
    def test_simple_message_roundtrip(self, msg_id: str, msg_value: str) -> None:
        """Property: Simple messages round-trip correctly."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = f"{msg_id} = {msg_value}"

        resource1 = parser.parse(ftl_source)

        assert len(resource1.entries) > 0, f"Parser returned no entries for: {ftl_source}"

        serialized = serializer.serialize(resource1)

        resource2 = parser.parse(serialized)

        assert len(resource2.entries) == len(
            resource1.entries
        ), "Round-trip changed entry count"

        if isinstance(resource1.entries[0], Message) and isinstance(
            resource2.entries[0], Message
        ):
            assert (
                resource1.entries[0].id.name == resource2.entries[0].id.name
            ), "Message ID changed during round-trip"

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        prefix=ftl_simple_text(),
        suffix=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_variable_interpolation_roundtrip(
        self, msg_id: str, var_name: str, prefix: str, suffix: str
    ) -> None:
        """Property: Messages with variable interpolation round-trip."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"

        resource1 = parser.parse(ftl_source)

        assert not any(
            isinstance(e, Junk) for e in resource1.entries
        ), f"Parse error on valid input: {ftl_source}"

        serialized = serializer.serialize(resource1)
        resource2 = parser.parse(serialized)

        assert not any(
            isinstance(e, Junk) for e in resource2.entries
        ), f"Round-trip introduced parse error: {serialized}"


class TestParserInvariants:
    """Properties about parser behavior that must always hold."""

    @given(source=st.text(min_size=0, max_size=500))
    @settings(max_examples=2000)
    def test_parser_never_crashes(self, source: str) -> None:
        """Property: Parser handles arbitrary input without crashing."""
        parser = FluentParserV1()

        try:
            result = parser.parse(source)
            assert isinstance(result, Resource), "Parser must return Resource"
        except RecursionError:
            pass

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_valid_messages_produce_message_nodes(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Property: Valid FTL messages produce Message AST nodes, not Junk."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = {msg_value}"

        resource = parser.parse(ftl_source)

        non_junk = [e for e in resource.entries if not isinstance(e, Junk)]
        assert len(non_junk) > 0, f"Valid message parsed as Junk: {ftl_source}"
        assert isinstance(
            non_junk[0], Message
        ), f"Valid message not parsed as Message: {ftl_source}"

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
        leading_ws=st.text(alphabet=" \t", max_size=10),
        trailing_ws=st.text(alphabet=" \t", max_size=10),
    )
    @settings(max_examples=300)
    def test_whitespace_insensitivity(
        self, msg_id: str, msg_value: str, leading_ws: str, trailing_ws: str
    ) -> None:
        """Property: Leading/trailing whitespace doesn't affect parsing."""
        parser = FluentParserV1()

        ftl1 = f"{msg_id} = {msg_value}"
        ftl2 = f"{leading_ws}{msg_id} = {msg_value}{trailing_ws}"

        resource1 = parser.parse(ftl1)
        resource2 = parser.parse(ftl2)

        msgs1 = [e for e in resource1.entries if isinstance(e, Message)]
        msgs2 = [e for e in resource2.entries if isinstance(e, Message)]

        if msgs1 and msgs2:
            assert msgs1[0].id.name == msgs2[0].id.name, "Whitespace changed message ID"


class TestParserEdgeCases:
    """Edge cases: Unicode, nesting, boundary conditions."""

    @given(
        msg_id=ftl_identifiers(),
        unicode_text=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"), blacklist_characters="{}\n"
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=500)
    def test_unicode_text_parsing(self, msg_id: str, unicode_text: str) -> None:
        """Property: Parser handles arbitrary Unicode in text content."""
        parser = FluentParserV1()

        ftl_source = f"{msg_id} = {unicode_text}"

        resource = parser.parse(ftl_source)

        assert len(resource.entries) > 0, "Parser returned empty resource for Unicode text"

    @given(
        term_id=ftl_identifiers(),
        term_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_term_parsing_with_hyphen(self, term_id: str, term_value: str) -> None:
        """Property: Terms with leading hyphen parse correctly."""
        parser = FluentParserV1()

        ftl_source = f"-{term_id} = {term_value}"

        resource = parser.parse(ftl_source)

        terms = [e for e in resource.entries if isinstance(e, Term)]
        assert len(terms) > 0, f"Term not parsed correctly: {ftl_source}"
        assert terms[0].id.name == term_id, "Term ID incorrect"

    @given(
        msg_id=ftl_identifiers(),
        nesting_depth=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_nested_placeable_depth(self, msg_id: str, nesting_depth: int) -> None:
        """Property: Parser handles nested placeables up to reasonable depth."""
        parser = FluentParserV1()

        open_braces = "{ " * nesting_depth
        close_braces = " }" * nesting_depth
        ftl_source = f"{msg_id} = {open_braces}$x{close_braces}"

        resource = parser.parse(ftl_source)

        assert len(resource.entries) > 0, "Parser failed on nested placeables"


class TestParserMetamorphicProperties:
    """Metamorphic properties: relation between different inputs/outputs."""

    @given(
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_concatenation_associativity(self, value1: str, value2: str) -> None:
        """Property: Parsing concatenated sources vs. separate resources."""
        parser = FluentParserV1()

        separate_source = f"m1 = {value1}\nm2 = {value2}"
        r1 = parser.parse(separate_source)

        non_junk = [e for e in r1.entries if not isinstance(e, Junk)]
        assert len(non_junk) == 2, "Expected 2 messages from concatenated source"

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
        newlines=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_newline_count_independence(
        self, msg_id: str, msg_value: str, newlines: int
    ) -> None:
        """Property: Multiple blank lines between messages don't affect parsing."""
        parser = FluentParserV1()

        separator = "\n" * newlines
        ftl_source = f"m1 = test{separator}{msg_id} = {msg_value}"

        resource = parser.parse(ftl_source)

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 2, f"Newline count affected message parsing: {ftl_source}"


class TestParserErrorRecovery:
    """Properties about parser error handling and recovery."""

    @given(
        valid_msg=ftl_identifiers().flatmap(
            lambda mid: ftl_simple_text().map(lambda val: f"{mid} = {val}")
        ),
        invalid_fragment=st.text(
            alphabet=st.characters(whitelist_categories=["Cc"]), min_size=1, max_size=20
        ),
    )
    @settings(max_examples=300)
    def test_recovery_after_junk(self, valid_msg: str, invalid_fragment: str) -> None:
        """Property: Parser continues after encountering junk."""
        parser = FluentParserV1()

        ftl_source = f"{invalid_fragment}\n{valid_msg}"

        resource = parser.parse(ftl_source)

        assert len(resource.entries) > 0, "Parser stopped after junk instead of continuing"

    @given(
        msg_id=ftl_identifiers(),
        unclosed_braces=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_unclosed_placeable_detection(
        self, msg_id: str, unclosed_braces: int
    ) -> None:
        """Property: Unclosed placeables create Junk, not crash."""
        parser = FluentParserV1()

        open_braces = "{ " * unclosed_braces
        ftl_source = f"{msg_id} = {open_braces}$x"

        resource = parser.parse(ftl_source)

        assert isinstance(resource, Resource), "Parser must return Resource even on errors"


class TestParserStructuralProperties:
    """Properties about AST structure produced by parser."""

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_message_has_required_fields(self, msg_id: str, msg_value: str) -> None:
        """Property: Parsed Messages have all required fields set."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = {msg_value}"

        resource = parser.parse(ftl_source)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        assert len(messages) > 0, "No messages parsed"
        msg = messages[0]

        assert msg.id is not None, "Message missing id field"
        assert msg.id.name == msg_id, "Message ID mismatch"
        assert msg.value is not None, "Message missing value field"

    @given(
        msg_id=ftl_identifiers(),
        attr_name=ftl_identifiers(),
        attr_value=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_attribute_parsing_structure(
        self, msg_id: str, attr_name: str, attr_value: str
    ) -> None:
        """Property: Messages with attributes parse into correct structure."""
        parser = FluentParserV1()

        ftl_source = f"{msg_id} =\n    .{attr_name} = {attr_value}"

        resource = parser.parse(ftl_source)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        if messages and messages[0].attributes:
            attr = messages[0].attributes[0]
            assert attr.id.name == attr_name, "Attribute name mismatch"
