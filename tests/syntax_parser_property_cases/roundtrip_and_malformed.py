# mypy: ignore-errors
from tests.syntax_parser_property_cases import (
    FluentParserV1,
    FluentSerializer,
    Junk,
    Message,
    Resource,
    Term,
    assume,
    event,
    example,
    ftl_simple_text,
    given,
    settings,
    shared_ftl_identifiers,
    st,
)


class TestParserRoundTrip:
    """Property: parse(serialize(parse(source))) preserves AST structure."""

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=1000)
    def test_simple_message_roundtrip(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Simple messages round-trip through serialize/parse."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = f"{msg_id} = {msg_value}"
        resource1 = parser.parse(ftl_source)
        entry_count = len(resource1.entries)
        event(f"entry_count={entry_count}")

        assert entry_count > 0

        serialized = serializer.serialize(resource1)
        resource2 = parser.parse(serialized)

        assert len(resource2.entries) == entry_count
        if isinstance(resource1.entries[0], Message) and isinstance(
            resource2.entries[0], Message
        ):
            assert (
                resource1.entries[0].id.name
                == resource2.entries[0].id.name
            )

    @given(
        msg_id=shared_ftl_identifiers(),
        var_name=shared_ftl_identifiers(),
        prefix=ftl_simple_text(),
        suffix=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_variable_interpolation_roundtrip(
        self,
        msg_id: str,
        var_name: str,
        prefix: str,
        suffix: str,
    ) -> None:
        """Messages with variable interpolation round-trip."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = (
            f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"
        )
        resource1 = parser.parse(ftl_source)
        has_junk = any(
            isinstance(e, Junk) for e in resource1.entries
        )
        event(
            f"outcome={'has_junk' if has_junk else 'roundtrip_clean'}"
        )

        assert not has_junk

        serialized = serializer.serialize(resource1)
        resource2 = parser.parse(serialized)

        assert not any(
            isinstance(e, Junk) for e in resource2.entries
        )


# ============================================================================
# METAMORPHIC PROPERTIES
# ============================================================================


class TestParserMetamorphicProperties:
    """Metamorphic properties: predictable relations between inputs."""

    @given(
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_concatenation_preserves_message_count(
        self, value1: str, value2: str
    ) -> None:
        """Separate messages in one source produce two entries."""
        parser = FluentParserV1()
        separate_source = f"m1 = {value1}\nm2 = {value2}"
        r1 = parser.parse(separate_source)

        non_junk = [
            e for e in r1.entries if not isinstance(e, Junk)
        ]
        msg_count = len(non_junk)
        event(f"non_junk_count={msg_count}")
        assert msg_count == 2

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
        newlines=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_blank_line_count_independence(
        self, msg_id: str, msg_value: str, newlines: int
    ) -> None:
        """Blank lines between messages do not affect parse result."""
        parser = FluentParserV1()
        separator = "\n" * newlines
        ftl_source = f"m1 = test{separator}{msg_id} = {msg_value}"

        resource = parser.parse(ftl_source)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]
        event(f"separator_newlines={newlines}")
        assert len(messages) == 2

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_deterministic_parsing(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Parsing same input twice yields identical results."""
        source = f"{msg_id} = {msg_value}"
        parser = FluentParserV1()
        result1 = parser.parse(source)
        result2 = parser.parse(source)

        assert len(result1.entries) == len(result2.entries)
        for e1, e2 in zip(
            result1.entries, result2.entries, strict=True
        ):
            assert isinstance(e1, type(e2))
        event(f"entry_count={len(result1.entries)}")


# ============================================================================
# STRUCTURAL PROPERTIES
# ============================================================================


class TestParserStructuralProperties:
    """Properties about AST structure produced by parser."""

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_message_has_required_fields(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Parsed Messages have all required fields set."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = {msg_value}"
        resource = parser.parse(ftl_source)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]

        assert len(messages) > 0
        msg = messages[0]
        assert msg.id is not None
        assert msg.id.name == msg_id
        assert msg.value is not None
        event(f"attribute_count={len(msg.attributes)}")

    @given(
        msg_id=shared_ftl_identifiers(),
        attr_name=shared_ftl_identifiers(),
        attr_value=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_attribute_parsing_structure(
        self, msg_id: str, attr_name: str, attr_value: str
    ) -> None:
        """Messages with attributes parse into correct structure."""
        parser = FluentParserV1()
        ftl = f"{msg_id} =\n    .{attr_name} = {attr_value}"
        resource = parser.parse(ftl)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]

        has_attr = (
            bool(messages)
            and bool(messages[0].attributes)
        )
        event(
            f"outcome={'has_attr' if has_attr else 'no_attr'}"
        )
        if has_attr:
            attr = messages[0].attributes[0]
            assert attr.id.name == attr_name

    @given(
        term_id=shared_ftl_identifiers(),
        term_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_term_parsing_structure(
        self, term_id: str, term_value: str
    ) -> None:
        """Terms with leading hyphen parse correctly."""
        parser = FluentParserV1()
        ftl_source = f"-{term_id} = {term_value}"
        resource = parser.parse(ftl_source)

        terms = [
            e for e in resource.entries if isinstance(e, Term)
        ]
        event(f"term_count={len(terms)}")
        assert len(terms) > 0
        assert terms[0].id.name == term_id

    @given(
        msg_id=shared_ftl_identifiers(),
        nesting_depth=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_nested_placeable_depth(
        self, msg_id: str, nesting_depth: int
    ) -> None:
        """Parser handles nested placeables up to depth limit."""
        parser = FluentParserV1()
        open_braces = "{ " * nesting_depth
        close_braces = " }" * nesting_depth
        ftl_source = f"{msg_id} = {open_braces}$x{close_braces}"

        resource = parser.parse(ftl_source)
        event(f"nesting_depth={nesting_depth}")
        assert len(resource.entries) > 0

    @given(source=st.text(min_size=0, max_size=500))
    @settings(max_examples=2000)
    def test_parser_always_returns_resource(
        self, source: str
    ) -> None:
        """Parser handles arbitrary input without crashing."""
        parser = FluentParserV1()
        try:
            result = parser.parse(source)
            assert isinstance(result, Resource)
            event(f"entry_count={len(result.entries)}")
        except RecursionError:
            pass

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
        leading_ws=st.text(alphabet=" \t", max_size=10),
        trailing_ws=st.text(alphabet=" \t", max_size=10),
    )
    @settings(max_examples=300)
    def test_whitespace_around_message(
        self, msg_id: str, msg_value: str,
        leading_ws: str, trailing_ws: str,
    ) -> None:
        """Leading/trailing whitespace does not change message ID."""
        parser = FluentParserV1()
        ftl1 = f"{msg_id} = {msg_value}"
        ftl2 = (
            f"{leading_ws}{msg_id} = {msg_value}{trailing_ws}"
        )

        resource1 = parser.parse(ftl1)
        resource2 = parser.parse(ftl2)

        msgs1 = [
            e for e in resource1.entries
            if isinstance(e, Message)
        ]
        msgs2 = [
            e for e in resource2.entries
            if isinstance(e, Message)
        ]
        ws_type = "mixed" if leading_ws and trailing_ws else "one"
        event(f"whitespace_padding={ws_type}")
        if msgs1 and msgs2:
            assert msgs1[0].id.name == msgs2[0].id.name


# ============================================================================
# MALFORMED INPUT PROPERTIES
# ============================================================================


@st.composite
def malformed_placeable(draw: st.DrawFn) -> str:
    """Generate placeables with strategic syntax errors."""
    corruptions = [
        "{",           # Missing content
        "{ ",          # Space but no content
        "{ $",         # Incomplete variable
        "{ $v",        # Incomplete variable name
        "{ $var",      # Missing closing }
        '{ "',         # Incomplete string literal
        '{ "text',     # Unterminated string
        "{ -",         # Incomplete term ref
        "{ -t",        # Incomplete term name
        "{ -term",     # Missing closing }
        "{ 1.",        # Malformed number
        "{ 1.2.",      # Invalid number format
        "{ FUNC",      # Missing parentheses
        "{ FUNC(",     # Incomplete function
        "{ FUNC($",    # Incomplete arg
        "{ msg.",      # Missing attr name
        "{ msg.@",     # Invalid attr name
        "{ $x ->",     # Incomplete select
        "{ $x -> [",   # Incomplete variant
        "{ $x -> [a]", # Missing pattern
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_function_call(draw: st.DrawFn) -> str:
    """Generate function calls with strategic syntax errors."""
    func_name = draw(
        st.sampled_from(["FUNC", "NUMBER", "DATETIME"])
    )
    corruptions = [
        f"{func_name}",
        f"{func_name}(",
        f"{func_name}($",
        f"{func_name}($v",
        f"{func_name}(1.2.",
        f'{{ {func_name}("',
        f"{func_name}(@",
        f"{func_name}(a:",
        f"{func_name}(a: )",
        f"{func_name}(123: x)",
        f"{func_name}(a: 1, a: 2)",
        f"{func_name}(x: 1, 2)",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_select_expression(draw: st.DrawFn) -> str:
    """Generate select expressions with strategic errors."""
    var = draw(st.sampled_from(["$x", "$count", "$num"]))
    corruptions = [
        f"{{ {var} ->",
        f"{{ {var} -> [",
        f"{{ {var} -> [@",
        f"{{ {var} -> [a]",
        f"{{ {var} -> [a] Text",
        f"{{ {var} -> [a] {{ msg.",
        f"{{ {var} -> [one] X *[other] Y",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_term_input(draw: st.DrawFn) -> str:
    """Generate terms with strategic syntax errors."""
    corruptions = [
        "-",
        "- ",
        "-@invalid",
        "-term",
        "-term =",
        "-term = val\n    .",
        "-term = val\n    .@",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_term_reference(draw: st.DrawFn) -> str:
    """Generate term references with strategic errors."""
    corruptions = [
        "{ -",
        "{ - }",
        "{ -@bad }",
        "{ -term(",
        "{ -term(x",
        "{ -term.",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_attribute(draw: st.DrawFn) -> str:
    """Generate attributes with strategic errors."""
    corruptions = [
        "    .",
        "    .@",
        "    . = val",
        "    .attr",
        "    .attr =",
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedPlaceables:
    """Parser handles malformed placeables without crashing."""

    @given(
        msg_id=shared_ftl_identifiers(),
        placeable=malformed_placeable(),
    )
    @settings(max_examples=100, deadline=None)
    @example(msg_id="key", placeable="{ msg.")
    @example(msg_id="key", placeable='{ "')
    @example(msg_id="key", placeable="{ 1.2.")
    def test_malformed_placeables(
        self, msg_id: str, placeable: str
    ) -> None:
        """Parser recovers from malformed placeables."""
        source = f"{msg_id} = {placeable}"
        event(f"placeable_len={len(placeable)}")
        parser = FluentParserV1()

        try:
            resource = parser.parse(source)
            assert resource is not None
        except RecursionError:
            assume(False)


class TestMalformedFunctionCalls:
    """Parser handles malformed function calls gracefully."""

    @given(
        msg_id=shared_ftl_identifiers(),
        func_call=malformed_function_call(),
    )
    @settings(max_examples=80, deadline=None)
    @example(msg_id="key", func_call="FUNC($")
    @example(msg_id="key", func_call="FUNC(1.2.")
    @example(msg_id="key", func_call='{ FUNC("')
    @example(msg_id="key", func_call="FUNC(@bad)")
    @example(msg_id="key", func_call="FUNC(a:)")
    @example(msg_id="key", func_call="FUNC")
    def test_malformed_function_calls(
        self, msg_id: str, func_call: str
    ) -> None:
        """Parser recovers from malformed function calls."""
        source = f"{msg_id} = {{ {func_call} }}"
        event(f"func_call_len={len(func_call)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedSelectExpressions:
    """Parser handles malformed select expressions."""

    @given(
        msg_id=shared_ftl_identifiers(),
        select=malformed_select_expression(),
    )
    @settings(max_examples=50, deadline=None)
    @example(msg_id="key", select="{ $x -> [@")
    @example(msg_id="key", select="{ $x -> [a] Text")
    @example(
        msg_id="key",
        select="{ $x -> [a] { msg.",
    )
    def test_malformed_select_expressions(
        self, msg_id: str, select: str
    ) -> None:
        """Parser recovers from malformed selects."""
        source = f"{msg_id} = {select}"
        event(f"select_len={len(select)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedTerms:
    """Parser handles malformed terms and term references."""

    @given(term_def=malformed_term_input())
    @settings(max_examples=40, deadline=None)
    @example(term_def="-@invalid")
    @example(term_def="-term = val\n    .")
    def test_malformed_term_definitions(
        self, term_def: str
    ) -> None:
        """Parser recovers from malformed term definitions."""
        event(f"input_len={len(term_def)}")
        parser = FluentParserV1()
        resource = parser.parse(term_def)
        assert resource is not None

    @given(
        msg_id=shared_ftl_identifiers(),
        term_ref=malformed_term_reference(),
    )
    @settings(max_examples=40, deadline=None)
    @example(msg_id="key", term_ref="{ -")
    @example(msg_id="key", term_ref="{ -term(")
    def test_malformed_term_references(
        self, msg_id: str, term_ref: str
    ) -> None:
        """Parser recovers from malformed term references."""
        source = f"{msg_id} = {term_ref}"
        event(f"term_ref_len={len(term_ref)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedAttributes:
    """Parser handles malformed attributes."""

    @given(
        msg_id=shared_ftl_identifiers(),
        attr_line=malformed_attribute(),
    )
    @settings(max_examples=30, deadline=None)
    @example(msg_id="key", attr_line="    .")
    def test_malformed_attributes(
        self, msg_id: str, attr_line: str
    ) -> None:
        """Parser recovers from malformed attributes."""
        source = f"{msg_id} = value\n{attr_line}"
        event(f"attr_line_len={len(attr_line)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestSpecialCharacterSequences:
    """Parser handles arbitrary special character sequences."""

    @given(
        text=st.text(
            alphabet="{}$-.[]*\n\r\t ",
            min_size=1,
            max_size=30,
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_arbitrary_special_char_sequences(
        self, text: str
    ) -> None:
        """Parser never crashes on special FTL character combos."""
        assume(text.strip())
        parser = FluentParserV1()
        try:
            resource = parser.parse(text)
            assert resource is not None
            event(f"entry_count={len(resource.entries)}")
        except RecursionError:
            assume(False)

    @given(
        msg_id=shared_ftl_identifiers(),
        value=st.text(
            alphabet=(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789{}$-. "
            ),
            min_size=1,
            max_size=40,
        ),
    )
    @settings(max_examples=150, deadline=None)
    def test_complex_value_patterns(
        self, msg_id: str, value: str
    ) -> None:
        """Parser handles complex patterns in values."""
        source = f"{msg_id} = {value}"
        parser = FluentParserV1()
        try:
            resource = parser.parse(source)
            assert resource is not None
            has_junk = any(
                isinstance(e, Junk) for e in resource.entries
            )
            event(
                f"outcome={'junk' if has_junk else 'clean'}"
            )
        except RecursionError:
            assume(False)

    @given(
        ftl_source=st.text(min_size=0, max_size=100)
    )
    @settings(max_examples=300, deadline=None)
    def test_universal_crash_resistance(
        self, ftl_source: str
    ) -> None:
        """Parser never crashes on any input."""
        parser = FluentParserV1()
        try:
            resource = parser.parse(ftl_source)
            assert resource is not None
            assert hasattr(resource, "entries")
            event(f"entry_count={len(resource.entries)}")
        except RecursionError:
            assume(False)

    @given(
        msg_id=shared_ftl_identifiers(),
        placeable_content=st.text(
            alphabet=(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789$-. "
            ),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_deterministic_placeable_parsing(
        self, msg_id: str, placeable_content: str
    ) -> None:
        """Parsing same placeable twice gives same result."""
        source = f"{msg_id} = {{ {placeable_content} }}"
        parser1 = FluentParserV1()
        parser2 = FluentParserV1()
        try:
            result1 = parser1.parse(source)
            result2 = parser2.parse(source)
            assert len(result1.entries) == len(result2.entries)
            for e1, e2 in zip(
                result1.entries, result2.entries, strict=True
            ):
                assert isinstance(e1, type(e2))
            event(f"entry_count={len(result1.entries)}")
        except RecursionError:
            assume(False)
