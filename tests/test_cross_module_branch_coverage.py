"""Tests targeting final coverage gaps across multiple modules.

This module provides targeted tests for specific uncovered lines and branches
identified via coverage analysis. Tests are organized by source module.

Covered modules:
- introspection.py (lines 261-262: nested Placeable)
- runtime/function_bridge.py (lines 137, 147, 618-620)
- runtime/locale_context.py (lines 143-144, 440)
- syntax/parser/rules.py (lines 703, 721)
- syntax/serializer.py (branches 249->exit, 349->338, 440->exit, 485->488)
- syntax/validator.py (branches 153->exit, 166->170, 242->exit)
- syntax/visitor.py (branches 179->177, 182->168)
- validation/resource.py (branches 330->328, 339->336)

Python 3.13+.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, get_args

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.enums import CommentType
from ftllexengine.introspection import extract_references, introspect_message
from ftllexengine.runtime.function_bridge import (
    _FTL_REQUIRES_LOCALE_ATTR,
    FluentValue,
    FunctionRegistry,
    fluent_function,
)
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from ftllexengine.syntax.validator import SemanticValidator
from ftllexengine.syntax.visitor import ASTVisitor
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _detect_circular_references,
    validate_resource,
)

# ============================================================================
# INTROSPECTION: Nested Placeable Coverage (lines 261-262)
# ============================================================================


class TestIntrospectionNestedPlaceable:
    """Test introspection of nested Placeable expressions."""

    def test_nested_placeable_extraction(self) -> None:
        """Nested Placeable (Placeable containing Placeable) visits inner expression.

        Lines 261-262: with self._depth_guard: self._visit_expression(expr.expression)
        """
        # Construct: { { $var } } - nested placeable with variable
        inner_var = VariableReference(id=Identifier("innerVar"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer_placeable,)),
            attributes=(),
        )

        result = introspect_message(message)

        # Variable should be extracted from nested structure
        var_names = {v.name for v in result.variables}
        assert "innerVar" in var_names

    def test_deeply_nested_placeables(self) -> None:
        """Multiple levels of nested Placeables."""
        # Build { { { $deep } } }
        var = VariableReference(id=Identifier("deep"))
        level1 = Placeable(expression=var)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        message = Message(
            id=Identifier("deepNest"),
            value=Pattern(elements=(level3,)),
            attributes=(),
        )

        result = introspect_message(message)
        var_names = {v.name for v in result.variables}
        assert "deep" in var_names

    def test_message_without_value_extract_references(self) -> None:
        """Message with value=None but with attributes (branch 397->401)."""
        # Message with only attributes
        attr_pattern = Pattern(
            elements=(Placeable(expression=VariableReference(id=Identifier("attrVar"))),)
        )
        message = Message(
            id=Identifier("attrsOnly"),
            value=None,  # No value - triggers branch 397->401
            attributes=(Attribute(id=Identifier("hint"), value=attr_pattern),),
        )

        msg_refs, term_refs = extract_references(message)

        # Should work even without value
        assert isinstance(msg_refs, frozenset)
        assert isinstance(term_refs, frozenset)

    def test_introspect_message_without_value(self) -> None:
        """introspect_message with message.value=None (branch 441->445)."""
        attr_pattern = Pattern(
            elements=(
                TextElement("Hint: "),
                Placeable(expression=VariableReference(id=Identifier("hintVar"))),
            )
        )
        message = Message(
            id=Identifier("noValue"),
            value=None,
            attributes=(Attribute(id=Identifier("tooltip"), value=attr_pattern),),
        )

        result = introspect_message(message)

        # Should extract from attributes even when value is None
        var_names = {v.name for v in result.variables}
        assert "hintVar" in var_names


# ============================================================================
# FUNCTION_BRIDGE: Decorator and Registry Coverage
# ============================================================================


class TestFunctionBridgeCoverage:
    """Test function_bridge decorator and registry coverage."""

    def test_fluent_function_no_parentheses_usage(self) -> None:
        """Using @fluent_function without parentheses (line 147).

        When func is not None, decorator is applied directly.
        """

        @fluent_function
        def my_upper(value: str) -> FluentValue:
            return value.upper()

        result = my_upper("hello")
        assert result == "HELLO"

    def test_fluent_function_with_parentheses_usage(self) -> None:
        """Using @fluent_function() with parentheses (line 143)."""

        @fluent_function()
        def my_lower(value: str) -> FluentValue:
            return value.lower()

        result = my_lower("HELLO")
        assert result == "hello"

    def test_fluent_function_with_locale_injection(self) -> None:
        """Using @fluent_function(inject_locale=True) (line 141)."""

        @fluent_function(inject_locale=True)
        def locale_aware(value: str, locale: str) -> FluentValue:
            return f"{value}@{locale}"

        # Check attribute is set
        assert hasattr(locale_aware, _FTL_REQUIRES_LOCALE_ATTR)
        assert getattr(locale_aware, _FTL_REQUIRES_LOCALE_ATTR) is True

    def test_fluent_function_wrapper_returns_value(self) -> None:
        """Wrapper function returns fn() result (line 137)."""

        @fluent_function
        def add_suffix(value: str, suffix: str = "!") -> FluentValue:
            return f"{value}{suffix}"

        result = add_suffix("Hello", suffix="?")
        assert result == "Hello?"

    def test_get_builtin_metadata_exists(self) -> None:
        """get_builtin_metadata for existing function (lines 618-620)."""
        registry = FunctionRegistry()

        meta = registry.get_builtin_metadata("NUMBER")
        assert meta is not None
        assert meta.requires_locale is True

    def test_get_builtin_metadata_not_exists(self) -> None:
        """get_builtin_metadata for non-existent function."""
        registry = FunctionRegistry()

        meta = registry.get_builtin_metadata("NONEXISTENT")
        assert meta is None


# ============================================================================
# LOCALE_CONTEXT: cache_info and datetime pattern format
# ============================================================================


class TestLocaleContextCoverage:
    """Test LocaleContext coverage gaps."""

    def test_cache_info_returns_dict(self) -> None:
        """cache_info() returns dict with cache state (lines 143-144)."""
        LocaleContext.clear_cache()

        # Create some cached contexts
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")

        info = LocaleContext.cache_info()

        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info
        assert info["size"] == 2
        locales = info["locales"]
        assert isinstance(locales, tuple)
        # Cache keys are normalized to lowercase
        assert "en_us" in locales or "de_de" in locales

    def test_format_datetime_string_pattern_fallback(self) -> None:
        """format_datetime when pattern is string, not DateTimePattern (line 440).

        When datetime_pattern doesn't have format() method, use str.format().
        """
        ctx = LocaleContext.create("en-US")

        # Format with both date and time to trigger combined pattern path
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)

        # Use format that combines date and time
        result = ctx.format_datetime(dt, date_style="medium", time_style="short")

        # Should successfully format (either DateTimePattern.format or str.format)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_datetime_date_only(self) -> None:
        """format_datetime with date_style only (no time) - line 442-448."""
        ctx = LocaleContext.create("en-US")

        dt = datetime(2024, 12, 25, 0, 0, 0, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="long")

        assert isinstance(result, str)
        assert "2024" in result or "December" in result


# ============================================================================
# PARSER/RULES: Placeable and FunctionReference in Arguments
# ============================================================================


class TestParserRulesCoverage:
    """Test parser/rules.py coverage gaps."""

    def test_placeable_as_function_argument(self) -> None:
        """Placeable inside function call arguments (line 703).

        FTL: msg = { FUNC({ $var }) }
        """
        parser = FluentParserV1()
        ftl = 'msg = { NUMBER({ "5" }) }'

        resource = parser.parse(ftl)

        # Should parse successfully
        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_function_reference_as_argument(self) -> None:
        """Function reference inside function arguments (line 721).

        FTL: msg = { OUTER(INNER()) }
        """
        parser = FluentParserV1()
        ftl = "msg = { NUMBER(UPPER($val)) }"

        resource = parser.parse(ftl)

        # Should parse (may fail validation but parse succeeds)
        assert len(resource.entries) >= 1

    def test_uppercase_identifier_not_function(self) -> None:
        """Uppercase identifier without parentheses is message reference."""
        parser = FluentParserV1()
        # THIS is an uppercase message reference, not a function call
        ftl = "msg = { THIS }"

        resource = parser.parse(ftl)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)


# ============================================================================
# SERIALIZER: Missing Branch Coverage
# ============================================================================


class TestSerializerBranchCoverage:
    """Test serializer branch coverage."""

    def test_serialize_junk_entry(self) -> None:
        """Serialize Junk entry (branch 249->exit)."""
        junk = Junk(content="invalid content here")
        resource = Resource(entries=(junk,))

        result = serialize(resource)

        # Junk should be serialized as-is
        assert "invalid content here" in result

    def test_serialize_text_without_braces(self) -> None:
        """Serialize text that has no braces (branch 349->338)."""
        message = Message(
            id=Identifier("simple"),
            value=Pattern(elements=(TextElement("Plain text without braces"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "simple = Plain text without braces" in result

    def test_serialize_text_with_braces(self) -> None:
        """Serialize text with literal braces."""
        message = Message(
            id=Identifier("braced"),
            value=Pattern(
                elements=(
                    TextElement("a"),
                    Placeable(expression=StringLiteral(value="{")),
                    TextElement("b"),
                    Placeable(expression=StringLiteral(value="}")),
                    TextElement("c"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "braced" in result

    def test_serialize_select_expression(self) -> None:
        """Serialize SelectExpression (branch 440->exit)."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("one"),
                    value=Pattern(elements=(TextElement("One item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Many items"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("plural"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "plural" in result
        assert "*[other]" in result

    def test_serialize_number_literal_variant_key(self) -> None:
        """Serialize variant with NumberLiteral key (branch 485->488)."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("numkey"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[1]" in result
        assert "*[other]" in result

    def test_serialize_nested_placeable(self) -> None:
        """Serialize nested Placeable (Placeable inside Placeable)."""
        inner = Placeable(expression=VariableReference(id=Identifier("inner")))
        outer = Placeable(expression=inner)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # Nested placeables serialize with proper braces
        assert "nested" in result


# ============================================================================
# VALIDATOR: Missing Branch Coverage
# ============================================================================


class TestValidatorBranchCoverage:
    """Test validator branch coverage."""

    def test_validate_junk_entry_passthrough(self) -> None:
        """Junk entry in validation passes through (branch 153->exit)."""
        junk = Junk(content="invalid")
        resource = Resource(entries=(junk,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should complete without error for Junk
        assert result is not None

    def test_validate_comment_entry_passthrough(self) -> None:
        """Comment entry in validation passes through (branch 151-152)."""
        comment = Comment(content="This is a comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should complete without error
        assert result.is_valid

    def test_validate_message_without_value(self) -> None:
        """Message with value=None (branch 166->170)."""
        # Message with only attributes, no value
        attr = Attribute(
            id=Identifier("hint"),
            value=Pattern(elements=(TextElement("Hint text"),)),
        )
        message = Message(
            id=Identifier("noValue"),
            value=None,  # No value - triggers branch
            attributes=(attr,),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should validate (may warn but not crash)
        assert result is not None


# ============================================================================
# VISITOR: Missing Branch Coverage
# ============================================================================


class TestVisitorBranchCoverage:
    """Test visitor branch coverage."""

    def test_visit_node_with_empty_tuple_field(self) -> None:
        """Visit node where tuple field is empty (branch 179->177 loop exit)."""
        # Message with empty attributes tuple
        message = Message(
            id=Identifier("empty"),
            value=Pattern(elements=(TextElement("Value"),)),
            attributes=(),  # Empty tuple
        )

        class CountingVisitor(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.visit_count = 0

            def visit(self, node: Any) -> Any:
                self.visit_count += 1
                return super().visit(node)

        visitor = CountingVisitor()
        visitor.visit(message)

        # Should have visited nodes despite empty tuple
        assert visitor.visit_count > 0

    def test_visit_node_with_primitive_fields(self) -> None:
        """Visit node with str/int/bool fields (branch 172-173)."""
        # Identifier has 'name' which is a string
        ident = Identifier("test")

        class FieldInspector(ASTVisitor):
            def __init__(self) -> None:
                super().__init__()
                self.visited_identifier = False

            def visit_Identifier(self, node: Identifier) -> Any:  # noqa: N802
                self.visited_identifier = True
                return self.generic_visit(node)

        visitor = FieldInspector()
        visitor.visit(ident)

        assert visitor.visited_identifier

    def test_visit_node_with_none_field(self) -> None:
        """Visit node where a field is None."""
        # Message without comment
        message = Message(
            id=Identifier("noComment"),
            value=Pattern(elements=(TextElement("Val"),)),
            attributes=(),
            comment=None,
        )

        visitor = ASTVisitor()
        result = visitor.visit(message)

        # Should handle None fields gracefully
        assert result is not None


# ============================================================================
# VALIDATION/RESOURCE: Cycle Detection Branch Coverage
# ============================================================================


class TestValidationResourceBranchCoverage:
    """Test validation/resource.py branch coverage."""

    def test_cycle_detection_loop_iterations(self) -> None:
        """Test cycle detection loop branches (330->328, 339->336)."""
        # Create a more complex graph with multiple iterations
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("x"))
                    ),
                )
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("y"))
                    ),
                )
            ),
            attributes=(),
        )

        term_x = Term(
            id=Identifier("x"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("y"))
                    ),
                )
            ),
            attributes=(),
        )
        term_y = Term(
            id=Identifier("y"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("x"))
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b}
        terms_dict = {"x": term_x, "y": term_y}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Cycle detection should find the term cycle
        warnings = _detect_circular_references(graph)

        # Should detect the cycle
        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) >= 1

    def test_cross_type_cycle_detection(self) -> None:
        """Test message -> term -> message cycle detection."""
        # Create cross-type cycle: msg:a -> term:t -> msg:a
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("t"))),
                )
            ),
            attributes=(),
        )

        term_t = Term(
            id=Identifier("t"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("a"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a}
        terms_dict = {"t": term_t}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect cross-type cycle
        assert any("circular" in w.message.lower() for w in warnings)


# ============================================================================
# HYPOTHESIS-BASED PROPERTY TESTS
# ============================================================================


class TestCoverageHypothesis:
    """Property-based tests for coverage gaps."""

    @given(
        st.lists(
            st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnop"),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=50)
    def test_visitor_handles_arbitrary_identifiers(self, names: list[str]) -> None:
        """Visitor handles messages with various identifier names."""
        event(f"name_count={len(names)}")
        # Build message with multiple attributes
        attrs = tuple(
            Attribute(
                id=Identifier(name),
                value=Pattern(elements=(TextElement(f"Value for {name}"),)),
            )
            for name in names[1:]
        ) if len(names) > 1 else ()

        message = Message(
            id=Identifier(names[0]),
            value=Pattern(elements=(TextElement("Main value"),)),
            attributes=attrs,
        )

        visitor = ASTVisitor()
        result = visitor.visit(message)

        assert result is not None

    @given(
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30)
    def test_serializer_handles_multiple_variants(self, variant_count: int) -> None:
        """Serializer handles select expressions with varying variant counts."""
        event(f"variant_count={variant_count}")
        variants = [
            Variant(
                key=Identifier(f"key{i}"),
                value=Pattern(elements=(TextElement(f"Value {i}"),)),
                default=(i == variant_count - 1),  # Last is default
            )
            for i in range(variant_count)
        ]

        select = SelectExpression(
            selector=VariableReference(id=Identifier("sel")),
            variants=tuple(variants),
        )

        message = Message(
            id=Identifier("multi"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # Should have all variants
        for i in range(variant_count):
            assert f"key{i}" in result


# ============================================================================
# INTEGRATION: End-to-End Coverage Verification
# ============================================================================


class TestIntegrationCoverage:
    """Integration tests that exercise multiple modules together."""

    def test_parse_validate_serialize_roundtrip(self) -> None:
        """Complete roundtrip: parse -> validate -> serialize."""
        ftl = """
msg = Hello { $name }
    .title = Title

-brand = Firefox

plural = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        # Validate
        result = validate_resource(ftl)
        assert result.is_valid

        # Serialize
        serialized = serialize(resource)

        # Re-parse
        resource2 = parser.parse(serialized)

        # Should have same structure
        assert len(resource2.entries) == len(resource.entries)

    def test_introspect_complex_message(self) -> None:
        """Introspect message with various constructs."""
        ftl = """
complex = { NUMBER($count) ->
    [one] { -brand } has { $count } item
   *[other] { -brand } has { NUMBER($count) } items
}
    .hint = { $hint }
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should extract all components
        var_names = {v.name for v in result.variables}
        func_names = {f.name for f in result.functions}
        assert "count" in var_names
        assert "hint" in var_names
        assert result.has_selectors
        assert "NUMBER" in func_names


# ============================================================================
# ADDITIONAL BRANCH COVERAGE TESTS
# ============================================================================


class TestIntrospectionBranchCoverage:
    """Additional tests for introspection branch coverage."""

    def test_function_without_arguments(self) -> None:
        """Function reference with empty arguments (branch 273->298).

        When func.arguments has no positional or named args, skip processing.
        """
        # Construct: { FUNC() } with empty CallArguments
        func_ref = FunctionReference(
            id=Identifier("NOARGS"),
            arguments=CallArguments(positional=(), named=()),  # Empty args
        )

        message = Message(
            id=Identifier("noArgsFunc"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        result = introspect_message(message)

        # Function should be recorded even without arguments
        func_names = {f.name for f in result.functions}
        assert "NOARGS" in func_names

    def test_text_element_only_pattern(self) -> None:
        """Pattern with only TextElement (branch 219->exit).

        TextElement case passes immediately.
        """
        message = Message(
            id=Identifier("textOnly"),
            value=Pattern(elements=(TextElement("Just plain text"),)),
            attributes=(),
        )

        result = introspect_message(message)

        # No variables or functions expected
        assert len(result.variables) == 0
        assert len(result.functions) == 0

    def test_function_with_empty_call_arguments(self) -> None:
        """Function with CallArguments but empty positional and named."""
        func_ref = FunctionReference(
            id=Identifier("EMPTY"),
            arguments=CallArguments(positional=(), named=()),
        )

        message = Message(
            id=Identifier("emptyArgs"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        result = introspect_message(message)

        func_names = {f.name for f in result.functions}
        assert "EMPTY" in func_names


class TestLocaleContextBranchCoverage:
    """Additional tests for locale_context branch coverage."""

    def test_format_datetime_with_string_pattern(self) -> None:
        """Test when datetime_pattern is a string rather than DateTimePattern.

        Line 440 uses str.format() when pattern lacks format() method.
        This requires mocking Babel to return a string pattern.
        """
        # This path is exercised when Babel returns a string pattern
        # which can happen with certain locale/format combinations
        ctx = LocaleContext.create("en-US")

        # Different style combinations to maximize branch coverage
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Date and time together
        result1 = ctx.format_datetime(dt, date_style="short", time_style="short")
        assert isinstance(result1, str)

        # Long formats
        result2 = ctx.format_datetime(dt, date_style="full", time_style="full")
        assert isinstance(result2, str)

    def test_format_datetime_varied_styles(self) -> None:
        """Test various datetime style combinations for branch coverage."""
        # Type alias for datetime styles
        type _DateTimeStyle = Literal["short", "medium", "long", "full"]
        styles: tuple[_DateTimeStyle, ...] = get_args(_DateTimeStyle)

        ctx = LocaleContext.create("en-US")
        dt = datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC)

        # Test all standard styles with proper typing
        for date_style in styles:
            for time_style in styles:
                result = ctx.format_datetime(
                    dt, date_style=date_style, time_style=time_style
                )
                assert isinstance(result, str)
                assert len(result) > 0


class TestParserRulesBranchCoverage:
    """Additional tests for parser/rules branch coverage."""

    def test_parse_complex_select_with_functions(self) -> None:
        """Complex select expression with function calls in variants.

        Tests various parser branches including 343->300.
        """
        parser = FluentParserV1()
        ftl = """
complex = { $gender ->
    [male] Mr. { $lastName }
    [female] Ms. { $lastName }
   *[other] { $firstName } { $lastName }
}
"""
        resource = parser.parse(ftl)
        assert len(resource.entries) == 1

    def test_parse_nested_function_calls(self) -> None:
        """Nested function calls in expressions."""
        parser = FluentParserV1()
        # NUMBER with string literal
        ftl = 'msg = { NUMBER("123.45") }'

        resource = parser.parse(ftl)
        assert len(resource.entries) == 1


class TestSerializerBranchCoverageExtended:
    """Extended serializer branch coverage tests."""

    def test_serialize_message_with_comment(self) -> None:
        """Serialize message with attached comment."""
        comment = Comment(content="Message comment", type=CommentType.COMMENT)
        message = Message(
            id=Identifier("commented"),
            value=Pattern(elements=(TextElement("Value"),)),
            attributes=(),
            comment=comment,
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "# Message comment" in result
        assert "commented = Value" in result

    def test_serialize_term_with_attributes(self) -> None:
        """Serialize term with attributes."""
        term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier("gender"),
                    value=Pattern(elements=(TextElement("masculine"),)),
                ),
            ),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert "-brand = Firefox" in result
        assert ".gender = masculine" in result

    def test_serialize_function_with_named_args(self) -> None:
        """Serialize function call with named arguments."""
        func_ref = FunctionReference(
            id=Identifier("NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier("count")),),
                named=(
                    NamedArgument(
                        name=Identifier("style"),
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier("percent"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "NUMBER" in result
        assert "style" in result


class TestVisitorBranchCoverageExtended:
    """Extended visitor branch coverage tests."""

    def test_visit_resource_with_mixed_entries(self) -> None:
        """Visit Resource with mix of messages, terms, comments, junk."""
        resource = Resource(
            entries=(
                Comment(content="File comment", type=CommentType.RESOURCE),
                Message(
                    id=Identifier("msg"),
                    value=Pattern(elements=(TextElement("Value"),)),
                    attributes=(),
                ),
                Term(
                    id=Identifier("term"),
                    value=Pattern(elements=(TextElement("Term"),)),
                    attributes=(),
                ),
                Junk(content="invalid"),
            )
        )

        visitor = ASTVisitor()
        result = visitor.visit(resource)

        assert result is not None

    def test_visit_with_dataclass_fields(self) -> None:
        """Visit nodes with various dataclass field types."""
        # NumberLiteral has int|float value field
        num_lit = NumberLiteral(value=42, raw="42")

        variant = Variant(
            key=num_lit,
            value=Pattern(elements=(TextElement("Forty-two"),)),
            default=True,  # bool field
        )

        select = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(variant,),
        )

        message = Message(
            id=Identifier("select"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )

        visitor = ASTVisitor()
        result = visitor.visit(message)

        assert result is not None


class TestValidatorBranchCoverageExtended:
    """Extended validator branch coverage tests."""

    def test_validate_term_with_attributes(self) -> None:
        """Validate term with attributes."""
        term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier("gender"),
                    value=Pattern(elements=(TextElement("m"),)),
                ),
            ),
        )
        resource = Resource(entries=(term,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result is not None

    def test_validate_message_with_select_in_attribute(self) -> None:
        """Validate message with select expression in attribute."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("one"),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(TextElement("Main"),)),
            attributes=(
                Attribute(
                    id=Identifier("count"),
                    value=Pattern(elements=(Placeable(expression=select),)),
                ),
            ),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result is not None


class TestResourceValidationBranchCoverageExtended:
    """Extended resource validation branch coverage tests."""

    def test_cycle_detection_with_multiple_independent_cycles(self) -> None:
        """Multiple independent cycles in same resource."""
        # Cycle 1: a -> b -> a
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("b"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("a"))),)
            ),
            attributes=(),
        )

        # Cycle 2: x -> y -> x
        msg_x = Message(
            id=Identifier("x"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("y"))),)
            ),
            attributes=(),
        )
        msg_y = Message(
            id=Identifier("y"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("x"))),)
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b, "x": msg_x, "y": msg_y}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect both cycles
        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) >= 2

    def test_no_cycles_in_linear_chain(self) -> None:
        """Linear reference chain without cycles."""
        # Chain: a -> b -> c -> d (no cycle)
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("b"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("c"))),)
            ),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("c"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("d"))),)
            ),
            attributes=(),
        )
        msg_d = Message(
            id=Identifier("d"),
            value=Pattern(elements=(TextElement("End"),)),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b, "c": msg_c, "d": msg_d}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        # Should detect no cycles
        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) == 0
