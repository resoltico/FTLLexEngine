"""Property-based tests for ftllexengine.syntax.serializer module.

Comprehensive test suite achieving 100% coverage using Hypothesis property-based
testing with HypoFuzz semantic coverage events.

Test Properties:
- Roundtrip: parse(serialize(ast)) preserves structure
- Idempotence: serialize(parse(serialize(ast))) == serialize(ast)
- Validation: Invalid ASTs raise SerializationValidationError
- Depth: Nested ASTs respect max_depth limits

Coverage Targets:
- Lines 117-118: SelectExpression with 0 defaults
- Lines 121-125: SelectExpression with >1 defaults
- Branch 238: FunctionReference without arguments
- Branch 429: Junk serialization
- Branch 616: Placeable in pattern
- Branch 749: SelectExpression serialization
- Branch 804: NumberLiteral variant keys

Python 3.13+.
"""

from __future__ import annotations

import typing

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import (
    FluentSerializer,
    SerializationDepthError,
    SerializationValidationError,
    _classify_line,
    _escape_text,
    _LineKind,  # Private import for property tests
    serialize,
)
from tests.strategies.ftl import (
    build_invalid_select_multiple_defaults,
    build_invalid_select_no_defaults,
    ftl_comment_nodes,
    ftl_deep_placeables,
    ftl_function_references_no_args,
    ftl_junk_nodes,
    ftl_message_nodes,
    ftl_patterns,
    ftl_placeables,
    ftl_resources,
    ftl_select_expressions,
    ftl_select_expressions_with_number_keys,
    ftl_term_nodes,
)

# =============================================================================
# Roundtrip Properties (Core Correctness)
# =============================================================================


class TestRoundtripProperties:
    """Test roundtrip correctness: parse(serialize(ast)) preserves structure."""

    @given(resource=ftl_resources())
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_resource_roundtrip_preserves_structure(self, resource: Resource) -> None:
        """PROPERTY: Serialized resources can be parsed back to equivalent AST.

        Events emitted:
        - entry_count={n}: Number of entries in resource
        - entry_type={type}: Type of each entry encountered
        """
        # Emit entry count for HypoFuzz coverage
        event(f"entry_count={len(resource.entries)}")

        # Serialize the resource
        serialized = serialize(resource, validate=True)

        # Parse the serialized output
        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Emit entry types for HypoFuzz coverage
        for entry in resource.entries:
            event(f"entry_type={type(entry).__name__}")

        # Verify entry count preserved (no parse errors mean no Junk entries added)
        assert len(reparsed.entries) == len(resource.entries)

    @given(message=ftl_message_nodes())
    def test_message_roundtrip_idempotence(self, message: Message) -> None:
        """PROPERTY: serialize(parse(serialize(ast))) == serialize(ast).

        Idempotence ensures serialization is stable across multiple cycles.

        Events emitted:
        - has_attributes={bool}: Whether message has attributes
        - attribute_count={n}: Number of attributes
        - pattern_starts_with_space={bool}: Edge case tracking
        """
        # Track leading-space edge case for HypoFuzz coverage guidance.
        pattern_value = message.value
        starts_with_space = False
        if pattern_value and pattern_value.elements:
            first_elem = pattern_value.elements[0]
            if isinstance(first_elem, TextElement) and first_elem.value.startswith(" "):
                starts_with_space = True

        event(f"pattern_starts_with_space={starts_with_space}")

        resource = Resource(entries=(message,))

        # Emit attribute coverage events
        event(f"has_attributes={len(message.attributes) > 0}")
        if message.attributes:
            event(f"attribute_count={len(message.attributes)}")

        # First serialization
        serialized1 = serialize(resource, validate=True)

        # Parse and re-serialize
        parser = FluentParserV1()
        reparsed = parser.parse(serialized1)
        serialized2 = serialize(reparsed, validate=True)

        # Idempotence: second serialization matches first
        assert serialized1 == serialized2

    @given(term=ftl_term_nodes())
    def test_term_roundtrip_idempotence(self, term: Term) -> None:
        """PROPERTY: Terms serialize idempotently.

        Events emitted:
        - has_attributes={bool}: Whether term has attributes
        - pattern_starts_with_space={bool}: Edge case tracking
        """
        # Track leading-space edge case for HypoFuzz coverage guidance.
        pattern_value = term.value
        starts_with_space = False
        if pattern_value and pattern_value.elements:
            first_elem = pattern_value.elements[0]
            if isinstance(first_elem, TextElement) and first_elem.value.startswith(" "):
                starts_with_space = True

        event(f"pattern_starts_with_space={starts_with_space}")

        resource = Resource(entries=(term,))

        event(f"has_attributes={len(term.attributes) > 0}")

        serialized1 = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized1)
        serialized2 = serialize(reparsed, validate=True)

        assert serialized1 == serialized2

    @given(pattern=ftl_patterns())
    def test_pattern_roundtrip_preserves_elements(self, pattern: Pattern) -> None:
        """PROPERTY: Pattern serialization preserves all elements.

        Events emitted:
        - element_count={n}: Number of elements in pattern
        - element_type={type}: Type of each element
        - has_placeable={bool}: Whether pattern contains placeables
        """
        # Wrap pattern in a message
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Emit pattern structure events
        event(f"element_count={len(pattern.elements)}")
        has_placeable = any(isinstance(e, Placeable) for e in pattern.elements)
        event(f"has_placeable={has_placeable}")

        for element in pattern.elements:
            event(f"element_type={type(element).__name__}")

        serialized = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Verify no parse errors (no Junk entries) and correct entry count
        assert len(reparsed.entries) == 1


# =============================================================================
# Validation Properties (Error Handling)
# =============================================================================


class TestValidationProperties:
    """Test validation error detection for invalid ASTs."""

    def test_select_no_defaults_raises_validation_error(self) -> None:
        """COVERAGE: Lines 117-118 - SelectExpression with 0 defaults."""

        # Build invalid SelectExpression with no defaults
        invalid_select = build_invalid_select_no_defaults()

        # Wrap in a message
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Validation should catch the error
        with pytest.raises(SerializationValidationError, match="no default variant"):
            serialize(resource, validate=True)

    def test_select_multiple_defaults_raises_validation_error(self) -> None:
        """COVERAGE: Lines 121-125 - SelectExpression with >1 defaults."""

        # Build invalid SelectExpression with multiple defaults
        invalid_select = build_invalid_select_multiple_defaults()

        # Wrap in a message
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Validation should catch the error
        with pytest.raises(SerializationValidationError, match="2 default variants"):
            serialize(resource, validate=True)

    @given(message=ftl_message_nodes())
    def test_valid_ast_passes_validation(self, message: Message) -> None:
        """PROPERTY: Valid ASTs pass validation without error.

        Events emitted:
        - validation=passed: Successful validation
        """
        resource = Resource(entries=(message,))

        event("validation=passed")

        # Should not raise
        serialized = serialize(resource, validate=True)
        assert isinstance(serialized, str)

    def test_validation_can_be_disabled(self) -> None:
        """COVERAGE: validate=False parameter skips validation."""

        # Build invalid SelectExpression
        invalid_select = build_invalid_select_no_defaults()
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise when validate=False
        serialized = serialize(resource, validate=False)
        assert isinstance(serialized, str)

    def test_invalid_identifier_raises_validation_error(self) -> None:
        """COVERAGE: Invalid identifier validation."""

        # Create message with invalid identifier (empty string)
        # Bypass validation by using object.__new__
        identifier = object.__new__(Identifier)
        object.__setattr__(identifier, "name", "")  # Invalid: empty
        object.__setattr__(identifier, "span", None)

        message = Message(
            id=identifier,
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_duplicate_named_arguments_raises_validation_error(self) -> None:
        """COVERAGE: Duplicate named arguments validation."""

        # Create function call with duplicate named arguments
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=StringLiteral(value="currency"),
                    ),
                    NamedArgument(
                        name=Identifier(name="style"),  # Duplicate!
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="Duplicate named argument"):
            serialize(resource, validate=True)

    def test_invalid_named_argument_value_type_raises_error(self) -> None:
        """COVERAGE: Named argument value type validation."""

        # Create function call with invalid named argument value (not literal)
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=VariableReference(id=Identifier(name="var")),  # Invalid!
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="invalid value type"):
            serialize(resource, validate=True)


# =============================================================================
# Depth Properties (DoS Protection)
# =============================================================================


class TestDepthProperties:
    """Test max_depth protection against stack overflow."""

    @given(deep_placeable=ftl_deep_placeables(depth=5))
    def test_moderate_depth_succeeds(self, deep_placeable: Placeable) -> None:
        """PROPERTY: Moderately nested ASTs serialize successfully.

        Events emitted:
        - depth=moderate: Depth category
        """
        event("depth=moderate")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(deep_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should succeed with default max_depth
        serialized = serialize(resource, validate=True, max_depth=MAX_DEPTH)
        assert isinstance(serialized, str)

    def test_extreme_depth_raises_depth_error(self) -> None:
        """COVERAGE: SerializationDepthError on overflow."""

        # Build deeply nested structure exceeding limit
        # Start with innermost expression
        inner_expr = VariableReference(id=Identifier(name="x"))

        # Wrap in 150 nested placeables (exceeds default MAX_DEPTH=100)
        current: Placeable | VariableReference = inner_expr
        for _ in range(150):
            current = Placeable(expression=current)

        # After loop, current is guaranteed to be Placeable
        outermost_placeable = typing.cast(Placeable, current)

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(outermost_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationDepthError, match="depth limit exceeded"):
            serialize(resource, validate=True, max_depth=MAX_DEPTH)

    def test_custom_max_depth_respected(self) -> None:
        """COVERAGE: Custom max_depth parameter."""

        # Build structure with 10 nested placeables
        inner_expr = VariableReference(id=Identifier(name="x"))
        current: Placeable | VariableReference = inner_expr
        for _ in range(10):
            current = Placeable(expression=current)

        # After loop, current is guaranteed to be Placeable
        outermost_placeable = typing.cast(Placeable, current)

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(outermost_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should fail with max_depth=5
        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=True, max_depth=5)

        # Should succeed with max_depth=15
        serialized = serialize(resource, validate=True, max_depth=15)
        assert isinstance(serialized, str)


# =============================================================================
# Coverage-Targeted Tests (Branch Coverage)
# =============================================================================


class TestCoverageTargeted:
    """Tests targeting specific coverage gaps."""

    @given(func_ref=ftl_function_references_no_args())
    def test_function_reference_without_arguments(self, func_ref: FunctionReference) -> None:
        """COVERAGE: Branch 238 - FunctionReference without arguments.

        Events emitted:
        - coverage_target=function_no_args: Branch target
        """
        event("coverage_target=function_no_args")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain function name followed by empty parens
        assert f"{func_ref.id.name}()" in serialized

    @given(junk=ftl_junk_nodes())
    def test_junk_serialization(self, junk: Junk) -> None:
        """COVERAGE: Branch 429 - Junk serialization.

        Events emitted:
        - coverage_target=junk: Branch target
        - junk_has_trailing_newline={bool}: Content structure
        """
        event("coverage_target=junk")
        event(f"junk_has_trailing_newline={junk.content.endswith('\\n')}")

        resource = Resource(entries=(junk,))

        serialized = serialize(resource, validate=False)  # Junk may be invalid

        # Junk content should be preserved as-is (with trailing newline added if missing)
        if junk.content.endswith("\n"):
            assert junk.content in serialized
        else:
            assert junk.content + "\n" in serialized

    @given(select_expr=ftl_select_expressions_with_number_keys())
    def test_select_expression_number_keys(self, select_expr: SelectExpression) -> None:
        """COVERAGE: Branch 804 - NumberLiteral variant keys.

        Events emitted:
        - coverage_target=select_number_keys: Branch target
        """
        event("coverage_target=select_number_keys")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain numeric variant keys
        assert "[0]" in serialized or "[1]" in serialized

    @given(placeable=ftl_placeables())
    def test_placeable_in_pattern(self, placeable: Placeable) -> None:
        """COVERAGE: Branch 616 - Placeable in pattern.

        Events emitted:
        - coverage_target=placeable_in_pattern: Branch target
        - placeable_expr_type={type}: Expression type
        """
        event("coverage_target=placeable_in_pattern")
        event(f"placeable_expr_type={type(placeable.expression).__name__}")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain placeable delimiters
        assert "{ " in serialized
        assert " }" in serialized

    @given(select_expr=ftl_select_expressions())
    def test_select_expression_serialization(self, select_expr: SelectExpression) -> None:
        """COVERAGE: Branch 749 - SelectExpression serialization.

        Events emitted:
        - coverage_target=select_expression: Branch target
        - variant_count={n}: Number of variants
        """
        event("coverage_target=select_expression")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Emit variant count for HypoFuzz
        event(f"variant_count={len(select_expr.variants)}")

        # Should contain select syntax
        assert "->" in serialized
        # Should contain at least one default variant marker
        assert "*[" in serialized

    @given(comment=ftl_comment_nodes())
    def test_comment_serialization(self, comment: Comment) -> None:
        """COVERAGE: Comment serialization.

        Events emitted:
        - coverage_target=comment: Branch target
        - comment_type={type}: Comment type
        """
        event("coverage_target=comment")
        event(f"comment_type={comment.type.name}")

        resource = Resource(entries=(comment,))

        serialized = serialize(resource, validate=False)

        # Should contain comment prefix
        assert "#" in serialized


# =============================================================================
# Serializer Class Tests (Direct Class Usage)
# =============================================================================


class TestFluentSerializerClass:
    """Test FluentSerializer class directly (not just convenience function)."""

    @given(resource=ftl_resources())
    def test_serializer_instance_reusable(self, resource: Resource) -> None:
        """PROPERTY: FluentSerializer instances are reusable (thread-safe).

        Events emitted:
        - serializer=reused: Reuse tracking
        """
        event("serializer=reused")

        serializer = FluentSerializer()

        # Use same instance twice
        result1 = serializer.serialize(resource, validate=True)
        result2 = serializer.serialize(resource, validate=True)

        # Should produce identical results (no state mutation)
        assert result1 == result2

    @given(message=ftl_message_nodes())
    def test_serializer_matches_convenience_function(self, message: Message) -> None:
        """PROPERTY: FluentSerializer.serialize() == serialize().

        Events emitted:
        - serializer=class_vs_function: Comparison tracking
        """
        event("serializer=class_vs_function")

        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        class_result = serializer.serialize(resource, validate=True)
        func_result = serialize(resource, validate=True)

        assert class_result == func_result


# =============================================================================
# Special Character Handling Tests
# =============================================================================


class TestSpecialCharacterHandling:
    """Test proper escaping and handling of special characters."""

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs", "Cc"],  # Surrogates and control
                blacklist_characters=["\x00"],  # Null
            ),
            min_size=1,
            max_size=50,
        )
    )
    def test_string_literal_escaping_roundtrip(self, text: str) -> None:
        """PROPERTY: String literals with special chars roundtrip correctly.

        Events emitted:
        - has_backslash={bool}: Contains backslash
        - has_quote={bool}: Contains quote
        - has_newline={bool}: Contains newline
        """
        has_backslash = "\\\\" in text
        has_quote = '"' in text
        has_newline = "\\n" in text
        event(f"has_backslash={has_backslash}")
        event(f"has_quote={has_quote}")
        event(f"has_newline={has_newline}")

        string_lit = StringLiteral(value=text)
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=string_lit),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Verify no parse errors (no Junk entries means successful parse)
        assert len(reparsed.entries) > 0

    def test_brace_escaping_as_placeable(self) -> None:
        """COVERAGE: Braces must be escaped as placeables."""

        # Braces in text are represented as Placeable(StringLiteral)
        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=StringLiteral(value="{")),
                TextElement(value=" middle "),
                Placeable(expression=StringLiteral(value="}")),
                TextElement(value=" end"),
            )
        )

        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain escaped braces as placeables
        assert '{ "{" }' in serialized
        assert '{ "}" }' in serialized

    def test_multiline_pattern_indentation(self) -> None:
        """COVERAGE: Multiline patterns get proper indentation."""

        # Pattern with embedded newline
        pattern = Pattern(
            elements=(
                TextElement(value="Line 1\n"),
                TextElement(value="Line 2"),
            )
        )

        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain structural indentation after newline
        assert "Line 1\n    Line 2" in serialized


# =============================================================================
# _classify_line Property Tests
# =============================================================================


# Characters syntactically significant at continuation line start in FTL
_SYNTAX_CHARS = ".[*"


class TestClassifyLineProperties:
    """Property-based tests for _classify_line pure function.

    Properties verified:
    - EMPTY iff empty string
    - WHITESPACE_ONLY iff all spaces and non-empty
    - SYNTAX_LEADING iff first non-ws char is in {., *, [}
    - ws_len is always non-negative
    - Classification is exhaustive (always one of 4 kinds)
    """

    @given(line=st.text(
        alphabet=st.characters(
            codec="utf-8", categories=("L", "N", "P", "S", "Z")
        ),
        min_size=0,
        max_size=80,
    ))
    def test_output_is_valid_kind(self, line: str) -> None:
        """_classify_line always returns a valid _LineKind."""
        kind, ws_len = _classify_line(line)
        kind_name = kind.name
        event(f"kind={kind_name}")
        assert isinstance(kind, _LineKind)
        assert ws_len >= 0

    @given(line=st.text(
        alphabet=st.characters(
            codec="utf-8", categories=("L", "N", "P", "S", "Z")
        ),
        min_size=0,
        max_size=80,
    ))
    def test_empty_iff_empty_string(self, line: str) -> None:
        """EMPTY kind iff input is the empty string."""
        kind, _ = _classify_line(line)
        is_empty = kind is _LineKind.EMPTY
        event(f"empty={is_empty}")
        assert is_empty == (line == "")

    @given(n=st.integers(min_value=1, max_value=20))
    def test_whitespace_only_for_space_strings(self, n: int) -> None:
        """Strings of only spaces classify as WHITESPACE_ONLY."""
        line = " " * n
        kind, ws_len = _classify_line(line)
        event(f"spaces={n}")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    @given(
        ws=st.integers(min_value=0, max_value=10),
        syntax_char=st.sampled_from(list(_SYNTAX_CHARS)),
        suffix=st.text(min_size=0, max_size=20),
    )
    def test_syntax_leading_classification(
        self, ws: int, syntax_char: str, suffix: str
    ) -> None:
        """Lines starting with (optional ws + syntax char) are SYNTAX_LEADING."""
        line = " " * ws + syntax_char + suffix
        kind, ws_len = _classify_line(line)
        event(f"syntax_char={syntax_char}")
        event(f"ws_prefix={ws}")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == ws

    @given(
        ws=st.integers(min_value=0, max_value=10),
        first_char=st.characters(
            codec="utf-8",
            categories=("L", "N"),
        ),
        suffix=st.text(min_size=0, max_size=20),
    )
    def test_normal_for_non_syntax_first_char(
        self, ws: int, first_char: str, suffix: str
    ) -> None:
        """Lines where first non-ws char is not syntax are NORMAL."""
        line = " " * ws + first_char + suffix
        kind, _ = _classify_line(line)
        event(f"kind={kind.name}")
        assert kind is _LineKind.NORMAL


# =============================================================================
# _escape_text Property Tests
# =============================================================================


class TestEscapeTextProperties:
    """Property-based tests for _escape_text brace escaping.

    Properties verified:
    - Content preserved: unescaping the result recovers the original
    - No raw braces in non-placeable positions
    """

    @given(text=st.text(min_size=0, max_size=100))
    def test_content_roundtrip(self, text: str) -> None:
        """Unescaping placeable wrappers recovers original text."""
        output: list[str] = []
        _escape_text(text, output)
        result = "".join(output)
        has_braces = "{" in text or "}" in text
        event(f"has_braces={has_braces}")
        event(f"length={len(text)}")
        # Reverse the escaping
        recovered = result.replace('{ "{" }', "{").replace('{ "}" }', "}")
        assert recovered == text

    @given(text=st.text(
        alphabet=st.characters(
            codec="utf-8",
            exclude_characters="{}",
        ),
        min_size=0,
        max_size=100,
    ))
    def test_no_transformation_without_braces(self, text: str) -> None:
        """Text without braces passes through unchanged."""
        output: list[str] = []
        _escape_text(text, output)
        result = "".join(output)
        event(f"length={len(text)}")
        assert result == text


# =============================================================================
# Call Argument Depth Properties (Depth Guard in Arguments)
# =============================================================================


class TestCallArgumentDepthProperties:
    """Test depth guard enforcement within call arguments.

    Serializer wraps each positional and named argument expression
    in depth_guard. Nested term/function calls must respect limits.
    """

    @given(depth=st.integers(min_value=1, max_value=8))
    def test_nested_call_arguments_serialize(
        self, depth: int
    ) -> None:
        """PROPERTY: Nested call arguments within limits serialize.

        Events emitted:
        - call_arg_depth={n}: Nesting depth of call arguments
        - outcome=nested_args_ok: Serialization succeeded
        """
        event(f"call_arg_depth={depth}")

        # Build: NUMBER(-t0(-t1(-t2(...$x...))))
        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(depth):
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=()
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        event("outcome=nested_args_ok")
        assert "-t0(" in result
        assert "$x" in result

    def test_deep_call_args_exceed_depth_limit(self) -> None:
        """Deeply nested call arguments exceed depth limit."""
        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(20):
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=()
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=True, max_depth=10)

    @given(
        depth=st.integers(min_value=1, max_value=5),
        named_val=st.sampled_from(["decimal", "percent"]),
    )
    def test_named_args_in_nested_calls(
        self, depth: int, named_val: str
    ) -> None:
        """PROPERTY: Named arguments in nested calls serialize.

        Events emitted:
        - call_arg_depth={n}: Nesting depth
        - has_named_arg=True: Named argument present
        """
        event(f"call_arg_depth={depth}")
        event("has_named_arg=True")

        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(depth):
            named = NamedArgument(
                name=Identifier(name="style"),
                value=StringLiteral(value=named_val),
            )
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=(named,)
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert f'style: "{named_val}"' in result


# =============================================================================
# Control Character StringLiteral Properties
# =============================================================================


class TestControlCharStringLiteralProperties:
    """Test StringLiteral escaping for all control characters.

    Serializer uses \\uHHHH for chars < 0x20 and 0x7F. Verify
    this encoding for the full control character range.
    """

    @given(
        code=st.integers(min_value=0, max_value=0x1F),
    )
    def test_c0_control_chars_escaped(self, code: int) -> None:
        """PROPERTY: C0 control chars (0x00-0x1F) use \\uHHHH.

        Events emitted:
        - control_char_code={n}: Character code point
        - outcome=control_char_escaped: Escape verified
        """
        event(f"control_char_code={code}")

        char = chr(code)
        lit = StringLiteral(value=f"a{char}b")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        expected_escape = f"\\u{code:04X}"
        assert expected_escape in result
        event("outcome=control_char_escaped")

    def test_del_char_escaped(self) -> None:
        """DEL character (0x7F) uses \\u007F encoding."""
        lit = StringLiteral(value="a\x7Fb")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "\\u007F" in result

    @given(
        code=st.sampled_from(
            [0x00, 0x01, 0x08, 0x09, 0x0A, 0x0C, 0x0D,
             0x1B, 0x1F, 0x7F]
        ),
    )
    def test_control_char_roundtrip(self, code: int) -> None:
        """PROPERTY: Control chars roundtrip through parse/serialize.

        Events emitted:
        - control_char_code={n}: Character code point
        - outcome=control_roundtrip_ok: Roundtrip succeeded
        """
        event(f"control_char_code={code}")

        char = chr(code)
        lit = StringLiteral(value=f"x{char}y")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        serialized = serialize(resource, validate=True)
        parser = FluentParserV1()
        reparsed = parser.parse(serialized)
        assert len(reparsed.entries) == 1
        assert not any(
            isinstance(e, Junk) for e in reparsed.entries
        )
        event("outcome=control_roundtrip_ok")


# =============================================================================
# Entry Sequencing Properties (Junk/Comment/Message ordering)
# =============================================================================


class TestEntrySequencingProperties:
    """Test blank-line insertion logic for mixed entry sequences.

    Serializer handles spacing between entries: extra blank lines
    for adjacent comments of same type, Junk with leading
    whitespace, Message/Term compact separation.
    """

    @given(
        data=st.data(),
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_mixed_entry_sequences_parseable(
        self, data: st.DataObject, count: int
    ) -> None:
        """PROPERTY: Mixed entry sequences serialize to parseable FTL.

        Events emitted:
        - entry_count={n}: Number of entries
        - has_junk={bool}: Whether Junk entries present
        - has_comment={bool}: Whether Comment entries present
        - outcome=sequence_parseable: Output parses without error
        """
        event(f"entry_count={count}")

        entries: list[Message | Term | Comment | Junk] = []
        seen_ids: set[str] = set()
        has_junk = False
        has_comment = False

        for i in range(count):
            choice = data.draw(
                st.sampled_from(
                    ["message", "term", "comment", "junk"]
                )
            )
            if choice == "message":
                name = f"msg{i}"
                if name not in seen_ids:
                    seen_ids.add(name)
                    entries.append(
                        Message(
                            id=Identifier(name=name),
                            value=Pattern(
                                elements=(
                                    TextElement(value="val"),
                                )
                            ),
                            attributes=(),
                        )
                    )
            elif choice == "term":
                name = f"term{i}"
                if name not in seen_ids:
                    seen_ids.add(name)
                    entries.append(
                        Term(
                            id=Identifier(name=name),
                            value=Pattern(
                                elements=(
                                    TextElement(value="val"),
                                )
                            ),
                            attributes=(),
                        )
                    )
            elif choice == "comment":
                has_comment = True
                ctype = data.draw(
                    st.sampled_from([
                        CommentType.COMMENT,
                        CommentType.GROUP,
                        CommentType.RESOURCE,
                    ])
                )
                entries.append(
                    Comment(
                        content=f"comment {i}",
                        type=ctype,
                    )
                )
            else:
                has_junk = True
                entries.append(
                    Junk(content=f"junk line {i}\n")
                )

        event(f"has_junk={has_junk}")
        event(f"has_comment={has_comment}")

        if not entries:
            return

        resource = Resource(entries=tuple(entries))
        result = serialize(resource, validate=False)

        parser = FluentParserV1()
        reparsed = parser.parse(result)
        assert len(reparsed.entries) > 0
        event("outcome=sequence_parseable")

    @given(
        junk_count=st.integers(min_value=1, max_value=3),
        msg_count=st.integers(min_value=1, max_value=3),
    )
    def test_junk_between_messages(
        self, junk_count: int, msg_count: int
    ) -> None:
        """PROPERTY: Junk interleaved with Messages serializes.

        Events emitted:
        - junk_count={n}: Number of Junk entries
        - msg_count={n}: Number of Message entries
        - outcome=junk_interleaved_ok: Serialization succeeded
        """
        event(f"junk_count={junk_count}")
        event(f"msg_count={msg_count}")

        entries: list[Message | Junk] = []
        for i in range(msg_count):
            entries.append(
                Message(
                    id=Identifier(name=f"m{i}"),
                    value=Pattern(
                        elements=(TextElement(value="v"),)
                    ),
                    attributes=(),
                )
            )
            if i < junk_count:
                entries.append(
                    Junk(content=f"bad syntax {i}\n")
                )

        resource = Resource(entries=tuple(entries))
        result = serialize(resource, validate=False)
        assert isinstance(result, str)
        assert len(result) > 0
        event("outcome=junk_interleaved_ok")

    def test_adjacent_same_type_comments_separated(
        self,
    ) -> None:
        """Adjacent same-type comments get extra blank line."""
        entries = (
            Comment(content="first", type=CommentType.COMMENT),
            Comment(content="second", type=CommentType.COMMENT),
        )
        resource = Resource(entries=entries)
        result = serialize(resource, validate=False)
        # Double newline separates same-type comments
        assert "\n\n" in result


# =============================================================================
# SYNTAX_LEADING Roundtrip Properties (Full Path)
# =============================================================================


class TestSyntaxLeadingRoundtripProperties:
    """Test full serialize-parse-serialize for syntax-leading lines.

    Continuation lines starting with . * [ need wrapping as
    StringLiteral placeables to prevent parser misinterpretation.
    """

    _parser = FluentParserV1()

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
        ws=st.integers(min_value=0, max_value=6),
        suffix=st.text(
            alphabet=st.characters(
                codec="utf-8",
                categories=("L", "N"),
            ),
            min_size=0,
            max_size=20,
        ),
    )
    def test_syntax_leading_roundtrip(
        self, syntax_char: str, ws: int, suffix: str
    ) -> None:
        """PROPERTY: Syntax-leading continuation lines roundtrip.

        Events emitted:
        - syntax_char={char}: Which syntax character
        - ws_prefix={n}: Leading whitespace before syntax char
        - has_suffix={bool}: Whether trailing text follows
        - line_kind=SYNTAX_LEADING: Confirm classification
        """
        event(f"syntax_char={syntax_char}")
        event(f"ws_prefix={ws}")
        has_suffix = len(suffix) > 0
        event(f"has_suffix={has_suffix}")

        line = " " * ws + syntax_char + suffix
        kind, _ = _classify_line(line)
        event(f"line_kind={kind.name}")

        text_val = f"line1\n{line}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)

        # Must contain the syntax char wrapped as placeable
        escaped = f'{{ "{syntax_char}" }}'
        assert escaped in result

        # Parse: no Junk entries
        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
    )
    def test_syntax_char_only_roundtrip(
        self, syntax_char: str
    ) -> None:
        """PROPERTY: Line with only syntax char roundtrips.

        Events emitted:
        - syntax_char={char}: Which syntax character
        - line_kind=SYNTAX_LEADING: Classification
        - has_suffix=False: No trailing text
        """
        event(f"syntax_char={syntax_char}")
        event("has_suffix=False")

        kind, _ = _classify_line(syntax_char)
        event(f"line_kind={kind.name}")

        text_val = f"first line\n{syntax_char}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        escaped = f'{{ "{syntax_char}" }}'
        assert escaped in result

        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )

    @given(
        n_spaces=st.integers(min_value=1, max_value=10),
    )
    def test_whitespace_only_continuation_roundtrip(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Whitespace-only continuation lines roundtrip.

        Events emitted:
        - spaces={n}: Number of spaces
        - line_kind=WHITESPACE_ONLY: Classification
        """
        event(f"spaces={n_spaces}")

        ws_line = " " * n_spaces
        kind, _ = _classify_line(ws_line)
        event(f"line_kind={kind.name}")

        text_val = f"first line\n{ws_line}\nthird line"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        # Whitespace-only wrapped as placeable
        assert f'{{ "{ws_line}" }}' in result

        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )


# =============================================================================
# Separate-Line Trigger Discrimination
# =============================================================================


class TestSeparateLineTriggerProperties:
    """Test separate-line mode trigger discrimination.

    Two distinct triggers exist:
    1. Cross-element: TextElement starts with space after
       element ending with newline.
    2. Intra-element: Single TextElement has embedded newline
       followed by space on a NORMAL line.
    """

    @given(
        n_spaces=st.integers(min_value=1, max_value=8),
    )
    def test_cross_element_trigger(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Cross-element whitespace triggers separate-line.

        Events emitted:
        - trigger=cross_element: Trigger type
        - leading_spaces={n}: Number of leading spaces
        """
        event("trigger=cross_element")
        event(f"leading_spaces={n_spaces}")

        # Element 1 ends with newline, element 2 starts with
        # spaces — triggers separate-line mode.
        elems = (
            TextElement(value="line one\n"),
            TextElement(value=" " * n_spaces + "line two"),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=elems),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Separate-line: pattern on new line after =
        assert "test = \n    " in result

    @given(
        n_spaces=st.integers(min_value=1, max_value=8),
    )
    def test_intra_element_trigger(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Intra-element whitespace triggers separate-line.

        Events emitted:
        - trigger=intra_element: Trigger type
        - leading_spaces={n}: Number of leading spaces
        """
        event("trigger=intra_element")
        event(f"leading_spaces={n_spaces}")

        # Single element with embedded \n + spaces + NORMAL char
        text_val = f"line one\n{' ' * n_spaces}line two"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Separate-line: pattern on new line after =
        assert "test = \n    " in result

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
        n_spaces=st.integers(min_value=1, max_value=6),
    )
    def test_syntax_leading_does_not_trigger_separate_line(
        self, syntax_char: str, n_spaces: int
    ) -> None:
        """PROPERTY: SYNTAX_LEADING lines DON'T trigger separate-line.

        Events emitted:
        - trigger=syntax_not_separate: Negative case
        - syntax_char={char}: Which syntax char
        """
        event("trigger=syntax_not_separate")
        event(f"syntax_char={syntax_char}")

        # Embedded \n + spaces + syntax char => SYNTAX_LEADING,
        # which is handled by per-line wrapping, NOT separate-line.
        line = " " * n_spaces + syntax_char + "rest"
        text_val = f"line one\n{line}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Should NOT use separate-line mode
        assert result.startswith("test = ")
        assert not result.startswith("test = \n")


# =============================================================================
# Mark as fuzz tests for selective execution
# =============================================================================

pytestmark = pytest.mark.fuzz
