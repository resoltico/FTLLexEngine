# mypy: ignore-errors
from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle, parse_ftl
from ftllexengine.enums import ReferenceKind, VariableContext
from ftllexengine.introspection import (
    VariableInfo,
    introspect_message,
)
from ftllexengine.introspection.message import (
    IntrospectionVisitor,
    ReferenceExtractor,
)
from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Junk,
    Message,
    Pattern,
    Placeable,
    Term,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1

# ===========================================================================
# HELPERS
# ===========================================================================


def _parse_message(ftl: str) -> Message:
    """Parse FTL source and return first Message entry."""
    resource = FluentParserV1().parse(ftl)
    entry = resource.entries[0]
    assert isinstance(entry, Message)
    return entry


def _parse_term(ftl: str) -> Term:
    """Parse FTL source and return first Term entry."""
    resource = FluentParserV1().parse(ftl)
    entry = resource.entries[0]
    assert isinstance(entry, Term)
    return entry


def _make_message(
    name: str,
    *,
    value: Pattern | None = None,
    attributes: tuple[Attribute, ...] = (),
) -> Message:
    """Construct a Message programmatically (bypasses parser)."""
    return Message(id=Identifier(name=name), value=value, attributes=attributes)


def _make_pattern(*elements: TextElement | Placeable) -> Pattern:
    """Construct a Pattern from elements."""
    return Pattern(elements=elements)


# ===========================================================================
# VARIABLE EXTRACTION
# ===========================================================================



class TestIntrospectMessageNoneValue:
    """introspect_message with Message(value=None) - covers line 609->613."""

    def test_introspect_message_value_none_no_crash(self) -> None:
        """Message with value=None is introspected without error.

        Covers line 609->613: False branch of ``if message.value is not None:``
        """
        attr = Attribute(
            id=Identifier(name="label"),
            value=_make_pattern(Placeable(expression=VariableReference(id=Identifier("x")))),
        )
        msg = _make_message("test", value=None, attributes=(attr,))
        result = introspect_message(msg, use_cache=False)
        assert result.message_id == "test"
        assert "x" in result.get_variable_names()

    def test_introspect_message_value_none_only_attributes(self) -> None:
        """Attribute variables are still extracted when value is None."""
        attr1 = Attribute(
            id=Identifier(name="formal"),
            value=_make_pattern(Placeable(expression=VariableReference(id=Identifier("name")))),
        )
        attr2 = Attribute(
            id=Identifier(name="casual"),
            value=_make_pattern(TextElement(value="Hi there")),
        )
        msg = _make_message("greet", value=None, attributes=(attr1, attr2))
        result = introspect_message(msg, use_cache=False)
        assert "name" in result.get_variable_names()
        assert result.message_id == "greet"

class TestNestedPlaceableExpression:
    """Nested Placeable inside Placeable (lines 363-364 branch coverage)."""

    def test_nested_placeable_extracts_inner_variable(self) -> None:
        """Placeable wrapping another Placeable extracts the inner variable.

        Covers lines 363-364: ``elif Placeable.guard(expr):`` branch in
        _visit_expression when the expression is itself a Placeable node.
        """
        inner_var = VariableReference(id=Identifier(name="inner"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)
        msg = _make_message("test", value=_make_pattern(outer_placeable))

        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        names = {v.name for v in visitor.variables}
        assert "inner" in names

    def test_nested_placeable_via_introspect_message(self) -> None:
        """introspect_message handles doubly-nested Placeable."""
        inner_var = VariableReference(id=Identifier(name="deep"))
        msg = _make_message(
            "test",
            value=_make_pattern(Placeable(expression=Placeable(expression=inner_var))),
        )
        result = introspect_message(msg, use_cache=False)
        assert "deep" in result.get_variable_names()

class TestPatternElementExhaustiveness:
    """_visit_pattern_element assert_never guard for unexpected element types."""

    def test_unknown_pattern_element_raises_assertion_error(self) -> None:
        """assert_never raises AssertionError for non-TextElement non-Placeable.

        Covers the ``case _ as unreachable: assert_never(unreachable)`` branch.
        """
        visitor = IntrospectionVisitor()
        # Pass an object that is neither TextElement nor Placeable
        sentinel = object()
        with pytest.raises(AssertionError):
            visitor._visit_pattern_element(sentinel)  # type: ignore[arg-type]

class TestMessageIntrospectionContracts:
    """MessageIntrospection immutability, accessor, and consistency contracts."""

    def test_frozen_immutability(self) -> None:
        """MessageIntrospection cannot be mutated."""
        info = introspect_message(_parse_message("test = { $var }"))
        with pytest.raises(AttributeError):
            info.message_id = "modified"  # type: ignore[misc]

    def test_variable_info_immutability(self) -> None:
        """VariableInfo is frozen."""
        var_info = VariableInfo(name="test", context=VariableContext.PATTERN)
        with pytest.raises(AttributeError):
            var_info.name = "modified"  # type: ignore[misc]

    def test_requires_variable_true(self) -> None:
        """requires_variable returns True for present variable."""
        info = introspect_message(_parse_message("greeting = Hello, { $name }!"))
        assert info.requires_variable("name")

    def test_requires_variable_false(self) -> None:
        """requires_variable returns False for absent variable."""
        info = introspect_message(_parse_message("greeting = Hello, { $name }!"))
        assert not info.requires_variable("age")

    def test_get_variable_names_returns_frozenset(self) -> None:
        """get_variable_names returns frozenset."""
        info = introspect_message(_parse_message("msg = { $x }"))
        assert isinstance(info.get_variable_names(), frozenset)

    def test_get_function_names_returns_frozenset(self) -> None:
        """get_function_names returns frozenset."""
        info = introspect_message(_parse_message("msg = { NUMBER($x) }"))
        assert isinstance(info.get_function_names(), frozenset)

    def test_variables_field_is_frozenset(self) -> None:
        """variables field is a frozenset of VariableInfo."""
        info = introspect_message(_parse_message("msg = { $x }"))
        assert isinstance(info.variables, frozenset)

    def test_message_id_preserved(self) -> None:
        """introspect_message preserves message_id."""
        msg = _parse_message("greet-user = Hello")
        assert introspect_message(msg).message_id == "greet-user"

class TestAttributeIntrospection:
    """Variables in message attributes are extracted."""

    def test_attribute_variable_extracted(self) -> None:
        """Variable in attribute is extracted from message."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "login-button = Sign In\n    .title = Click to sign in as { $username }\n"
        )
        info = bundle.introspect_message("login-button")
        assert "username" in info.get_variable_names()

    def test_multiple_attributes_all_extracted(self) -> None:
        """Variables from all attributes are collected."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "button = Action\n"
            "    .tooltip = { $action } for { $user }\n"
            "    .aria-label = { $role }\n"
        )
        info = bundle.introspect_message("button")
        assert info.get_variable_names() == frozenset({"action", "user", "role"})

    def test_attribute_only_message(self) -> None:
        """Message with no value but attributes is introspected."""
        resource = FluentParserV1().parse("msg =\n    .attr1 = Value 1\n    .attr2 = Value 2\n")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        result = introspect_message(msg)
        assert result.message_id == "msg"

    def test_attribute_only_message_with_variables(self) -> None:
        """Variables in attributes of value-less message are extracted."""
        resource = FluentParserV1().parse(
            "msg =\n    .formal = Hello { $name }\n    .casual = Hi { $name }\n"
        )
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert "name" in introspect_message(msg).get_variable_names()

class TestTermIntrospection:
    """Introspection of Term AST nodes."""

    def test_introspect_term_direct(self) -> None:
        """introspect_message accepts Term nodes."""
        term = _parse_term("-brand = { $companyName }")
        info = introspect_message(term)
        assert info.message_id == "brand"
        assert "companyName" in info.get_variable_names()

    def test_introspect_term_via_bundle(self) -> None:
        """FluentBundle.introspect_term() introspects a term."""
        bundle = FluentBundle("en")
        bundle.add_resource("-brand = { $companyName }")
        info = bundle.introspect_term("brand")
        assert info.message_id == "brand"
        assert "companyName" in info.get_variable_names()

    def test_introspect_term_not_found(self) -> None:
        """KeyError raised for non-existent term."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match=r"Term 'nonexistent' not found"):
            bundle.introspect_term("nonexistent")

    def test_term_reference_positional_args(self) -> None:
        """Term reference with positional arguments extracts nested variables."""
        msg = _parse_message("greeting = { -brand($platform) }")
        assert isinstance(msg, (Message, Term))
        info = introspect_message(msg)
        assert "platform" in info.get_variable_names()

    def test_term_reference_named_args(self) -> None:
        """Term reference with named arguments extracts variable values."""
        msg = _parse_message('app-name = { -brand($userCase, case: "nominative") }')
        assert isinstance(msg, (Message, Term))
        info = introspect_message(msg)
        assert "userCase" in info.get_variable_names()

    def test_term_reference_both_arg_types(self) -> None:
        """Term reference with positional and named arguments captures all variables."""
        msg = _parse_message('msg = { -term($pos1, $pos2, style: "formal") }')
        assert isinstance(msg, (Message, Term))
        info = introspect_message(msg)
        assert "pos1" in info.get_variable_names()
        assert "pos2" in info.get_variable_names()

class TestVariableContexts:
    """Variable context tracking in IntrospectionVisitor."""

    def test_function_arg_context(self) -> None:
        """Variables in function arguments have FUNCTION_ARG context."""
        msg = _parse_message("msg = { NUMBER($value, minimumFractionDigits: 2) }")
        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        value_vars = [v for v in visitor.variables if v.name == "value"]
        assert len(value_vars) == 1
        assert value_vars[0].context == VariableContext.FUNCTION_ARG

    def test_selector_context(self) -> None:
        """Variables in selectors have SELECTOR context."""
        msg = _parse_message("msg = { $count -> [one] one *[other] many }")
        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        count_vars = [v for v in visitor.variables if v.name == "count"]
        selector_contexts = [v for v in count_vars if v.context == VariableContext.SELECTOR]
        assert len(selector_contexts) >= 1

    def test_variant_context(self) -> None:
        """Variables in variant values have VARIANT context."""
        msg = _parse_message("msg = { $sel -> [key] Value is { $value } *[other] none }")
        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        value_vars = [v for v in visitor.variables if v.name == "value"]
        variant_contexts = [v for v in value_vars if v.context == VariableContext.VARIANT]
        assert len(variant_contexts) >= 1

    def test_context_restored_after_selector(self) -> None:
        """Variable context is correctly restored after visiting selector."""
        msg = _parse_message(
            "emails = { $count ->\n"
            "    [one] { $name } has one email\n"
            "   *[other] { $name } has { $count } emails\n"
            "}"
        )
        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        var_contexts = {v.name: v.context for v in visitor.variables}
        assert "count" in var_contexts
        assert "name" in var_contexts

class TestSpanTracking:
    """Source position spans are attached to introspection results."""

    def test_variable_reference_span(self) -> None:
        """Variable references include correct source spans."""
        msg = _parse_message("greeting = Hello, { $name }!")
        info = introspect_message(msg)
        assert len(info.variables) == 1
        var_info = next(iter(info.variables))
        assert var_info.name == "name"
        assert var_info.span is not None
        assert var_info.span.start == 20
        assert var_info.span.end == 25

    def test_function_reference_span(self) -> None:
        """Function references include correct source spans."""
        msg = _parse_message("price = { NUMBER($amount) }")
        info = introspect_message(msg)
        assert len(info.functions) == 1
        func_info = next(iter(info.functions))
        assert func_info.name == "NUMBER"
        assert func_info.span is not None
        assert func_info.span.start == 10
        assert func_info.span.end == 25

    def test_message_reference_span(self) -> None:
        """Message references include correct source spans."""
        msg = _parse_message("ref = { other-msg }")
        info = introspect_message(msg)
        refs = [r for r in info.references if r.kind == ReferenceKind.MESSAGE]
        assert len(refs) == 1
        assert refs[0].id == "other-msg"
        assert refs[0].span is not None
        assert refs[0].span.start == 8
        assert refs[0].span.end == 17

    def test_term_reference_span(self) -> None:
        """Term references include correct source spans."""
        msg = _parse_message("msg = { -brand }")
        info = introspect_message(msg)
        refs = [r for r in info.references if r.kind == ReferenceKind.TERM]
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].span is not None
        assert refs[0].span.start == 8
        assert refs[0].span.end == 15

    def test_term_reference_with_attribute_span(self) -> None:
        """Term references with attributes have correct spans."""
        msg = _parse_message("msg = { -brand.short }")
        info = introspect_message(msg)
        refs = [r for r in info.references if r.kind == ReferenceKind.TERM]
        assert len(refs) == 1
        assert refs[0].attribute == "short"
        assert refs[0].span is not None
        assert refs[0].span.start == 8
        assert refs[0].span.end == 21

    def test_multiple_variables_distinct_spans(self) -> None:
        """Multiple variables each have distinct spans."""
        msg = _parse_message("msg = { $first } and { $second }")
        info = introspect_message(msg)
        assert len(info.variables) == 2
        vars_by_name = {v.name: v for v in info.variables}
        assert vars_by_name["first"].span is not None
        assert vars_by_name["first"].span.start == 8
        assert vars_by_name["second"].span is not None
        assert vars_by_name["second"].span.start == 23

    def test_message_reference_with_attribute_span(self) -> None:
        """Message references with attributes have correct spans."""
        msg = _parse_message("msg = { other.attr }")
        info = introspect_message(msg)
        refs = [r for r in info.references if r.kind == ReferenceKind.MESSAGE]
        assert len(refs) == 1
        assert refs[0].attribute == "attr"
        assert refs[0].span is not None
        assert refs[0].span.start == 8
        assert refs[0].span.end == 18

class TestDepthLimits:
    """Depth guard prevents stack overflow on deeply nested ASTs."""

    def test_introspection_visitor_depth_limit(self) -> None:
        """IntrospectionVisitor respects max_depth configuration."""
        msg = _parse_message(
            "msg = { $a -> [x] { $b -> [y] { $c -> [z] value *[o] v } *[o] v } *[o] v }"
        )
        visitor = IntrospectionVisitor(max_depth=100)
        assert msg.value is not None
        visitor.visit(msg.value)
        names = {v.name for v in visitor.variables}
        assert "a" in names
        assert "b" in names
        assert "c" in names

    def test_reference_extractor_depth_limit(self) -> None:
        """ReferenceExtractor respects max_depth configuration."""
        msg = _parse_message("msg = { -term1(-term2(-term3)) }")
        extractor = ReferenceExtractor(max_depth=100)
        assert msg.value is not None
        extractor.visit(msg.value)
        assert "term1" in extractor.term_refs
        assert "term2" in extractor.term_refs
        assert "term3" in extractor.term_refs

class TestIntrospectMessageTypeErrors:
    """introspect_message raises TypeError for non-Message/Term inputs."""

    def test_raises_for_junk(self) -> None:
        """Junk entry raises TypeError."""
        resource = parse_ftl("invalid syntax here !!!")
        assert resource.entries
        junk = resource.entries[0]
        assert isinstance(junk, Junk)
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(junk)  # type: ignore[arg-type]

    def test_raises_for_string(self) -> None:
        """String input raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message("not a message")  # type: ignore[arg-type]

    def test_raises_for_none(self) -> None:
        """None input raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(None)  # type: ignore[arg-type]

    def test_raises_for_dict(self) -> None:
        """Dict input raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message({"not": "a message"})  # type: ignore[arg-type]

    @given(
        st.one_of(
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.lists(st.text()),
        )
    )
    @settings(max_examples=30)
    def test_raises_for_arbitrary_types(self, invalid_input: object) -> None:
        """Arbitrary non-Message types raise TypeError."""
        event(f"input_type={type(invalid_input).__name__}")
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(invalid_input)  # type: ignore[arg-type]

class TestRealWorldScenarios:
    """Integration tests for practical use cases."""

    def test_ui_message_validation(self) -> None:
        """CI/CD variable validation for UI messages."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "home-subtitle = Welcome to { $country }\n"
            "money-with-vat = Gross: { $gross }, Net: { $net }, VAT: { $vat } ({ $rate }%)\n"
        )
        assert "country" in bundle.get_message_variables("home-subtitle")
        assert bundle.get_message_variables("money-with-vat") == frozenset(
            {"gross", "net", "vat", "rate"}
        )

    def test_function_usage_analysis(self) -> None:
        """Analyze function usage in financial messages."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            'timestamp = Last updated: { DATETIME($time, dateStyle: "medium") }\n'
            "price = Total: { NUMBER($amount, minimumFractionDigits: 2,"
            " maximumFractionDigits: 2) }\n"
        )
        ts_info = bundle.introspect_message("timestamp")
        assert "DATETIME" in ts_info.get_function_names()
        assert "time" in ts_info.get_variable_names()

        price_info = bundle.introspect_message("price")
        number_funcs = [f for f in price_info.functions if f.name == "NUMBER"]
        assert len(number_funcs) == 1
        assert "minimumFractionDigits" in number_funcs[0].named_args
        assert "maximumFractionDigits" in number_funcs[0].named_args
