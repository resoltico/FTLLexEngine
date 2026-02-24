"""Tests for FTL message introspection API.

Covers variable extraction, function introspection, reference tracking,
MessageIntrospection object contracts, span tracking, depth limits,
exhaustiveness guards, and caching. All branches in message.py are exercised.
"""

from __future__ import annotations

import threading

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle, parse_ftl
from ftllexengine.enums import ReferenceKind, VariableContext
from ftllexengine.introspection import (
    VariableInfo,
    clear_introspection_cache,
    extract_references,
    extract_references_by_attribute,
    extract_variables,
    introspect_message,
)
from ftllexengine.introspection.message import (
    IntrospectionVisitor,
    ReferenceExtractor,
    _introspection_cache,
    _introspection_cache_lock,
)
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Term,
    TermReference,
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


class TestVariableExtraction:
    """Variable extraction from various message patterns."""

    def test_simple_variable(self) -> None:
        """Extract single variable from simple message."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")
        assert bundle.get_message_variables("greeting") == frozenset({"name"})

    def test_multiple_variables(self) -> None:
        """Extract multiple variables from message."""
        bundle = FluentBundle("en")
        bundle.add_resource("user-info = { $firstName } { $lastName } (Age: { $age })")
        assert bundle.get_message_variables("user-info") == frozenset(
            {"firstName", "lastName", "age"}
        )

    def test_duplicate_variables(self) -> None:
        """Duplicate variable references appear once (frozenset deduplication)."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = { $name }, nice to meet you { $name }!")
        assert bundle.get_message_variables("greeting") == frozenset({"name"})

    def test_no_variables(self) -> None:
        """Message with no variables returns empty frozenset."""
        bundle = FluentBundle("en")
        bundle.add_resource("hello = Hello, World!")
        assert bundle.get_message_variables("hello") == frozenset()

    def test_message_not_found(self) -> None:
        """KeyError raised for non-existent message."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match=r"Message 'nonexistent' not found"):
            bundle.get_message_variables("nonexistent")

    def test_plain_text_pattern_has_no_variables(self) -> None:
        """TextElement branch: patterns with only text extract nothing."""
        msg = _parse_message("msg = Plain text without any placeables")
        result = introspect_message(msg)
        assert len(result.get_variable_names()) == 0
        assert len(result.get_function_names()) == 0
        assert not result.has_selectors

    def test_text_element_branch_in_visitor(self) -> None:
        """TextElement case in _visit_pattern_element executes without effect."""
        msg = _parse_message("msg = just text")
        visitor = IntrospectionVisitor()
        assert msg.value is not None
        visitor.visit(msg.value)
        assert visitor.variables == set()

    def test_extract_variables_direct_api(self) -> None:
        """extract_variables() convenience function delegates correctly."""
        msg = _parse_message("greeting = Hello, { $name }!")
        assert extract_variables(msg) == frozenset({"name"})

    def test_extract_variables_from_select_with_variants(self) -> None:
        """All variant-local variables are captured."""
        msg = _parse_message(
            "msg = { $count ->\n"
            "    [one] You have { $count } item from { $source }\n"
            "    [few] You have { $count } items from { $source }\n"
            "   *[other] You have { $count } items from { $source }\n"
            "}"
        )
        vars_ = extract_variables(msg)
        assert "count" in vars_
        assert "source" in vars_


# ===========================================================================
# SELECT EXPRESSIONS
# ===========================================================================


class TestSelectExpressions:
    """Variable extraction from select expressions."""

    def test_selector_variable(self) -> None:
        """Variable used in selector is extracted."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "emails = { $count ->\n    [one] one email\n   *[other] { $count } emails\n}\n"
        )
        assert "count" in bundle.get_message_variables("emails")

    def test_variant_variables(self) -> None:
        """Variables in variants are all extracted."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "message = { $userType ->\n"
            "    [admin] Hello { $name }, you are an admin\n"
            "   *[user] Welcome { $name }\n"
            "}\n"
        )
        assert bundle.get_message_variables("message") == frozenset({"userType", "name"})

    def test_nested_selectors(self) -> None:
        """Nested select expressions extract all variables."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "complex = { $gender ->\n"
            "    [male] { $count ->\n"
            "        [one] one item\n"
            "       *[other] { $count } items\n"
            "    }\n"
            "   *[female] { $count } things\n"
            "}\n"
        )
        assert bundle.get_message_variables("complex") == frozenset({"gender", "count"})

    def test_has_selectors_flag_set(self) -> None:
        """MessageIntrospection.has_selectors is True for select expressions."""
        msg = _parse_message(
            "msg = { $count ->\n    [0] No items\n    [1] One item\n   *[other] Many items\n}\n"
        )
        result = introspect_message(msg)
        assert result.has_selectors is True
        assert "count" in result.get_variable_names()

    def test_has_selectors_flag_false_for_plain(self) -> None:
        """has_selectors is False for messages without select expressions."""
        msg = _parse_message("simple = Hello")
        assert not introspect_message(msg).has_selectors


# ===========================================================================
# FUNCTION INTROSPECTION
# ===========================================================================


class TestFunctionIntrospection:
    """Function call detection and metadata extraction."""

    def test_function_detection(self) -> None:
        """Function calls are detected and named correctly."""
        info = introspect_message(_parse_message("price = { NUMBER($amount) }"))
        assert "NUMBER" in info.get_function_names()
        assert "amount" in info.get_variable_names()

    def test_function_with_named_args(self) -> None:
        """Named argument keys are captured in FunctionCallInfo."""
        info = introspect_message(
            _parse_message("price = { NUMBER($amount, minimumFractionDigits: 2) }")
        )
        funcs = list(info.functions)
        assert len(funcs) == 1
        assert funcs[0].name == "NUMBER"
        assert "amount" in funcs[0].positional_arg_vars
        assert "minimumFractionDigits" in funcs[0].named_args

    def test_multiple_functions(self) -> None:
        """Multiple distinct function calls are all detected."""
        info = introspect_message(
            _parse_message("ts = { NUMBER($value) } at { DATETIME($time) }")
        )
        assert info.get_function_names() == frozenset({"NUMBER", "DATETIME"})

    def test_function_without_arguments(self) -> None:
        """Function with empty argument list (FUNC()) is detected."""
        msg = _parse_message("msg = Result: { BUILTIN() }")
        result = introspect_message(msg)
        assert "BUILTIN" in result.get_function_names()

    def test_function_with_empty_arguments(self) -> None:
        """FunctionReference with empty CallArguments is detected and has no variables.

        Verifies that a function call with no positional or named arguments
        produces a FunctionCallInfo with empty variable sets.
        """
        func_ref = FunctionReference(
            id=Identifier(name="NOOP"),
            arguments=CallArguments(positional=(), named=()),
        )
        msg = _make_message(
            "test", value=_make_pattern(Placeable(expression=func_ref))
        )
        info = introspect_message(msg, use_cache=False)
        assert "NOOP" in info.get_function_names()
        assert len(info.get_variable_names()) == 0

    def test_function_multiple_positional_args(self) -> None:
        """Multiple positional arguments are all extracted."""
        msg = _parse_message("msg = { FUNC($a, $b, $c) }")
        result = introspect_message(msg)
        assert result.get_variable_names() == frozenset({"a", "b", "c"})

    def test_function_variable_in_named_arg_value(self) -> None:
        """Variable references in named argument values are extracted."""
        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="x")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt"),
                        value=VariableReference(id=Identifier(name="y")),
                    ),
                ),
            ),
        )
        msg = _make_message("test", value=_make_pattern(Placeable(expression=func_ref)))
        info = introspect_message(msg, use_cache=False)
        assert info.get_variable_names() == frozenset({"x", "y"})

    def test_function_all_named_args_with_variables(self) -> None:
        """All named argument variable references are extracted."""
        func_ref = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="val")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="a"),
                        value=VariableReference(id=Identifier(name="x")),
                    ),
                    NamedArgument(
                        name=Identifier(name="b"),
                        value=VariableReference(id=Identifier(name="y")),
                    ),
                    NamedArgument(
                        name=Identifier(name="literal"),
                        value=NumberLiteral(value=42, raw="42"),
                    ),
                ),
            ),
        )
        msg = _make_message("test", value=_make_pattern(Placeable(expression=func_ref)))
        info = introspect_message(msg, use_cache=False)
        assert info.get_variable_names() == frozenset({"val", "x", "y"})
        assert "FUNC" in info.get_function_names()

    def test_nested_message_reference_in_function_arg(self) -> None:
        """MessageReference in function positional arg is extracted."""
        bundle = FluentBundle("en")
        bundle.add_resource("base-value = 42\nformatted = { NUMBER(base-value) }\n")
        info = bundle.introspect_message("formatted")
        assert any(r.id == "base-value" for r in info.references)

    def test_variable_in_complex_nested_expression(self) -> None:
        """Variables in function inside select expression are captured."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "complex = { $type ->\n"
            "    [currency] { NUMBER($amount, minimumFractionDigits: 2) }\n"
            "   *[plain] { $amount }\n"
            "}\n"
        )
        info = bundle.introspect_message("complex")
        assert "type" in info.get_variable_names()
        assert "amount" in info.get_variable_names()


# ===========================================================================
# REFERENCE INTROSPECTION
# ===========================================================================


class TestReferenceIntrospection:
    """Message and term reference tracking."""

    def test_message_reference(self) -> None:
        """MessageReference is captured in ReferenceInfo."""
        bundle = FluentBundle("en")
        bundle.add_resource("brand = FTLLexEngine\ngreeting = Welcome to { brand }\n")
        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].kind == ReferenceKind.MESSAGE
        assert refs[0].attribute is None

    def test_term_reference(self) -> None:
        """TermReference is captured in ReferenceInfo."""
        bundle = FluentBundle("en")
        bundle.add_resource("-brand = FTLLexEngine\ngreeting = Welcome to { -brand }\n")
        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].kind == ReferenceKind.TERM

    def test_attribute_message_reference(self) -> None:
        """MessageReference with attribute is captured correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "message = Message\n    .tooltip = Tooltip\ngreeting = Hover for { message.tooltip }\n"
        )
        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "message"
        assert refs[0].attribute == "tooltip"


# ===========================================================================
# REFERENCE EXTRACTOR
# ===========================================================================


class TestReferenceExtractor:
    """ReferenceExtractor specialized visitor for dependency analysis."""

    def test_message_reference_collected(self) -> None:
        """MessageReference is added to message_refs without attribute."""
        msg = _parse_message("msg = { other-message }")
        extractor = ReferenceExtractor()
        assert msg.value is not None
        extractor.visit(msg.value)
        assert "other-message" in extractor.message_refs

    def test_message_reference_with_attribute(self) -> None:
        """MessageReference with attribute uses qualified form."""
        msg = _parse_message("msg = { other.attr }")
        extractor = ReferenceExtractor()
        assert msg.value is not None
        extractor.visit(msg.value)
        assert "other.attr" in extractor.message_refs

    def test_term_reference_no_attribute(self) -> None:
        """TermReference without attribute uses unqualified form."""
        msg = _parse_message("msg = { -brand }")
        extractor = ReferenceExtractor()
        assert msg.value is not None
        extractor.visit(msg.value)
        assert "brand" in extractor.term_refs

    def test_term_reference_with_attribute(self) -> None:
        """TermReference with attribute uses qualified form (line 482 branch)."""
        msg = _parse_message("msg = { -brand.short }")
        extractor = ReferenceExtractor()
        assert msg.value is not None
        extractor.visit(msg.value)
        # Covers line 482: self.term_refs.add(f"{node.id.name}.{node.attribute.name}")
        assert "brand.short" in extractor.term_refs

    def test_nested_term_references_via_arguments(self) -> None:
        """Nested term arguments are traversed by generic_visit."""
        msg = _parse_message("msg = { -outer(-inner($var)) }")
        assert isinstance(msg, (Message, Term))
        _msg_refs, term_refs = extract_references(msg)
        assert "outer" in term_refs
        assert "inner" in term_refs

    def test_depth_guard_in_deeply_nested_terms(self) -> None:
        """ReferenceExtractor respects max_depth."""
        msg = _parse_message("msg = { -term1(-term2(-term3)) }")
        extractor = ReferenceExtractor(max_depth=100)
        assert msg.value is not None
        extractor.visit(msg.value)
        assert "term1" in extractor.term_refs
        assert "term2" in extractor.term_refs
        assert "term3" in extractor.term_refs


# ===========================================================================
# EXTRACT_REFERENCES API
# ===========================================================================


class TestExtractReferences:
    """Tests for extract_references() public function."""

    def test_extract_message_and_term_refs(self) -> None:
        """extract_references returns both message and term ref sets."""
        msg = _parse_message("msg = { welcome } uses { -brand }")
        msg_refs, term_refs = extract_references(msg)
        assert "welcome" in msg_refs
        assert "brand" in term_refs

    def test_term_reference_with_args_tracked(self) -> None:
        """Term references in arguments are captured."""
        msg = _parse_message('msg = { -brand($var, case: "nominative") }')
        assert isinstance(msg, (Message, Term))
        _msg_refs, term_refs = extract_references(msg)
        assert "brand" in term_refs

    def test_extract_references_message_with_no_value(self) -> None:
        """extract_references handles Message(value=None) correctly.

        Covers line 518->522: False branch of ``if entry.value is not None:``
        when message has only attributes (no value pattern).
        """
        attr = Attribute(
            id=Identifier(name="attr"),
            value=_make_pattern(Placeable(expression=TermReference(id=Identifier("brand")))),
        )
        msg = _make_message("test", value=None, attributes=(attr,))
        msg_refs, term_refs = extract_references(msg)
        # Value is None so no refs from value; attribute has term ref
        assert "brand" in term_refs
        assert len(msg_refs) == 0

    def test_extract_references_message_with_empty_value_no_attrs(self) -> None:
        """extract_references with empty pattern value returns empty sets."""
        msg = _make_message("test", value=_make_pattern())
        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset()
        assert term_refs == frozenset()


# ===========================================================================
# EXTRACT_REFERENCES_BY_ATTRIBUTE API
# ===========================================================================


class TestExtractReferencesByAttribute:
    """Tests for extract_references_by_attribute() public function.

    This function was previously untested (0% coverage). Tests cover all
    branches: value pattern, per-attribute patterns, and None-value messages.
    """

    def test_value_pattern_refs_under_none_key(self) -> None:
        """Value pattern references are stored under key None."""
        msg = _parse_message("msg = { welcome } uses { -brand }")
        result = extract_references_by_attribute(msg)
        assert None in result
        msg_refs, term_refs = result[None]
        assert "welcome" in msg_refs
        assert "brand" in term_refs

    def test_attribute_refs_under_attribute_name_key(self) -> None:
        """Attribute references are stored under the attribute name key."""
        msg = _parse_message(
            "msg = Base text\n    .tooltip = { -brand }\n    .label = { other }\n"
        )
        result = extract_references_by_attribute(msg)
        assert "tooltip" in result
        assert "label" in result
        _m, term_refs = result["tooltip"]
        assert "brand" in term_refs
        msg_refs2, _t = result["label"]
        assert "other" in msg_refs2

    def test_value_and_attributes_separated(self) -> None:
        """Value and attribute references are separate entries."""
        msg = _parse_message(
            "msg = { value-ref }\n    .attr = { -term-ref }\n"
        )
        result = extract_references_by_attribute(msg)
        assert None in result
        assert "attr" in result
        # Value has message ref
        assert "value-ref" in result[None][0]
        # Attr has term ref
        assert "term-ref" in result["attr"][1]

    def test_message_with_no_value(self) -> None:
        """Message with value=None has no None key in result."""
        attr = Attribute(
            id=Identifier(name="tooltip"),
            value=_make_pattern(Placeable(expression=TermReference(id=Identifier("brand")))),
        )
        msg = _make_message("btn", value=None, attributes=(attr,))
        result = extract_references_by_attribute(msg)
        # No None key (no value pattern)
        assert None not in result
        assert "tooltip" in result
        assert "brand" in result["tooltip"][1]

    def test_message_with_only_value(self) -> None:
        """Message with value but no attributes returns single entry."""
        msg = _parse_message("msg = { other }")
        result = extract_references_by_attribute(msg)
        assert set(result.keys()) == {None}
        assert "other" in result[None][0]

    def test_empty_message_no_refs(self) -> None:
        """Message with empty value and no attributes returns empty result."""
        msg = _make_message("test", value=_make_pattern())
        result = extract_references_by_attribute(msg)
        # Empty Pattern creates a None key with empty sets
        assert None in result
        msg_refs, term_refs = result[None]
        assert msg_refs == frozenset()
        assert term_refs == frozenset()

    def test_multiple_attributes_all_present(self) -> None:
        """All attributes appear as separate keys."""
        msg = _parse_message(
            "btn = Base\n    .a1 = { -t1 }\n    .a2 = { -t2 }\n    .a3 = { -t3 }\n"
        )
        result = extract_references_by_attribute(msg)
        assert "a1" in result
        assert "a2" in result
        assert "a3" in result
        assert "t1" in result["a1"][1]
        assert "t2" in result["a2"][1]
        assert "t3" in result["a3"][1]


# ===========================================================================
# INTROSPECT_MESSAGE WITH value=None
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


# ===========================================================================
# NESTED PLACEABLE IN _visit_expression
# ===========================================================================


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


# ===========================================================================
# EXHAUSTIVENESS GUARD
# ===========================================================================


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


# ===========================================================================
# MESSAGEINTROSPECTON OBJECT CONTRACTS
# ===========================================================================


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


# ===========================================================================
# ATTRIBUTE INTROSPECTION
# ===========================================================================


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


# ===========================================================================
# TERM INTROSPECTION
# ===========================================================================


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


# ===========================================================================
# VARIABLE CONTEXTS
# ===========================================================================


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


# ===========================================================================
# SPAN TRACKING
# ===========================================================================


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


# ===========================================================================
# DEPTH LIMITS
# ===========================================================================


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


# ===========================================================================
# TYPE ERROR HANDLING
# ===========================================================================


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


# ===========================================================================
# REAL-WORLD SCENARIOS
# ===========================================================================


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


# ===========================================================================
# HYPOTHESIS PROPERTY TESTS  (inline - no external strategy module needed)
# ===========================================================================


_var_names = st.from_regex(r"[a-z]+", fullmatch=True)
_msg_ids = st.from_regex(r"[a-z]+", fullmatch=True)


class TestVariableExtractionProperties:
    """Property-based invariants for variable extraction."""

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_simple_variable_always_extracted(self, var_name: str) -> None:
        """{ $var } always extracts var."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        assert var_name in extract_variables(msg)

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_duplicate_variables_deduplicated(self, var_name: str) -> None:
        """{ $var } { $var } extracts var once."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }} {{ ${var_name} }}")
        variables = extract_variables(msg)
        assert var_name in variables
        assert len([v for v in variables if v == var_name]) == 1

    @given(var1=_var_names, var2=_var_names)
    @settings(max_examples=200)
    def test_multiple_variables_all_extracted(self, var1: str, var2: str) -> None:
        """{ $a } { $b } extracts both a and b."""
        event(f"same_vars={var1 == var2}")
        msg = _parse_message(f"msg = Hello {{ ${var1} }} {{ ${var2} }}")
        variables = extract_variables(msg)
        assert var1 in variables
        if var1 != var2:
            assert var2 in variables

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_variables_returns_empty_set(self, msg_id: str) -> None:
        """Message with no variables returns empty frozenset."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello World")
        assert len(extract_variables(msg)) == 0

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_variable_in_function_extracted(self, var_name: str) -> None:
        """NUMBER($var) extracts var."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = {{ NUMBER(${var_name}) }}")
        assert var_name in extract_variables(msg)

    @given(var_name=_var_names, attr_name=st.from_regex(r"[a-z]+", fullmatch=True))
    @settings(max_examples=100)
    def test_attribute_variable_extracted(self, var_name: str, attr_name: str) -> None:
        """Variables in attributes are extracted."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello\n    .{attr_name} = {{ ${var_name} }}")
        assert var_name in introspect_message(msg).get_variable_names()


class TestIntrospectionResultProperties:
    """Properties of MessageIntrospection result objects."""

    @given(msg_id=_msg_ids)
    @settings(max_examples=200)
    def test_message_id_preserved(self, msg_id: str) -> None:
        """introspect_message preserves message ID."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello")
        assert introspect_message(msg).message_id == msg_id

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_get_variable_names_consistent(self, var_name: str) -> None:
        """get_variable_names() and variables field are consistent."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        info = introspect_message(msg)
        var_names = info.get_variable_names()
        assert var_name in var_names
        assert len(info.variables) == len(var_names)

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_requires_variable_matches_extraction(self, var_name: str) -> None:
        """requires_variable(x) iff x in get_variable_names()."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        info = introspect_message(msg)
        if info.requires_variable(var_name):
            assert var_name in info.get_variable_names()
        if var_name in info.get_variable_names():
            assert info.requires_variable(var_name)

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_selectors_for_simple_message(self, msg_id: str) -> None:
        """Simple message has has_selectors=False."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello")
        assert introspect_message(msg).has_selectors is False

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_select_expression_sets_has_selectors(self, var_name: str) -> None:
        """Message with select expression has has_selectors=True."""
        event(f"var_name={var_name}")
        msg = _parse_message(
            f"msg = {{ ${var_name} ->\n    [one] One item\n   *[other] Many items\n}}"
        )
        assert introspect_message(msg).has_selectors is True

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_number_function_detected(self, var_name: str) -> None:
        """NUMBER($var) is detected as a function call."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = {{ NUMBER(${var_name}) }}")
        assert "NUMBER" in introspect_message(msg).get_function_names()

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_functions_returns_empty_set(self, msg_id: str) -> None:
        """Message with no functions returns empty frozenset."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello World")
        assert len(introspect_message(msg).get_function_names()) == 0


class TestIntrospectionIdempotence:
    """Idempotence: repeated calls return same results."""

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_extract_variables_idempotent(self, var_name: str) -> None:
        """Multiple extract_variables() calls return the same result."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        r1 = extract_variables(msg)
        r2 = extract_variables(msg)
        assert r1 == r2

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_introspect_message_idempotent(self, var_name: str) -> None:
        """Multiple introspect_message() calls return equivalent results."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        r1 = introspect_message(msg)
        r2 = introspect_message(msg)
        assert r1.message_id == r2.message_id
        assert r1.variables == r2.variables
        assert r1.functions == r2.functions
        assert r1.references == r2.references
        assert r1.has_selectors == r2.has_selectors

    @given(vars_list=st.lists(_var_names, min_size=1, max_size=10, unique=True))
    @settings(max_examples=50)
    def test_multiple_variables_all_captured(self, vars_list: list[str]) -> None:
        """All variables in message are captured in extract_variables."""
        event(f"var_count={len(vars_list)}")
        placeables = " ".join(f"{{ ${v} }}" for v in vars_list)
        msg = _parse_message(f"msg = {placeables}")
        variables = extract_variables(msg)
        for var in vars_list:
            assert var in variables
        assert len(variables) == len(vars_list)

    @given(
        var_names_list=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30)
    def test_arbitrary_variable_named_args(self, var_names_list: list[str]) -> None:
        """Functions with arbitrary variable names in named args extract all vars."""
        var_names_list = list(dict.fromkeys(var_names_list))
        if not var_names_list:
            return
        event(f"var_count={len(var_names_list)}")
        var_list = ", ".join(f"{name}: ${name}" for name in var_names_list)
        ftl = f"test = {{ NUMBER($value, {var_list}) }}"
        resource = parse_ftl(ftl)
        if not resource.entries or isinstance(resource.entries[0], Junk):
            return
        msg = resource.entries[0]
        if not isinstance(msg, Message):
            return
        info = introspect_message(msg)
        assert "value" in info.get_variable_names()
        for name in var_names_list:
            assert name in info.get_variable_names()


# ============================================================================
# NESTED PLACEABLE COVERAGE
# ============================================================================


class TestIntrospectionNestedPlaceable:
    """Test introspection of nested Placeable expressions."""

    def test_nested_placeable_extraction(self) -> None:
        """Nested Placeable (Placeable containing Placeable) visits inner expression."""
        inner_var = VariableReference(id=Identifier("innerVar"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer_placeable,)),
            attributes=(),
        )

        result = introspect_message(message)

        var_names = {v.name for v in result.variables}
        assert "innerVar" in var_names

    def test_deeply_nested_placeables(self) -> None:
        """Multiple levels of nested Placeables are fully traversed."""
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
        """Message with value=None but with attributes extracts from attributes."""
        attr_pattern = Pattern(
            elements=(Placeable(expression=VariableReference(id=Identifier("attrVar"))),)
        )
        message = Message(
            id=Identifier("attrsOnly"),
            value=None,
            attributes=(Attribute(id=Identifier("hint"), value=attr_pattern),),
        )

        msg_refs, term_refs = extract_references(message)

        assert isinstance(msg_refs, frozenset)
        assert isinstance(term_refs, frozenset)

    def test_introspect_message_without_value(self) -> None:
        """introspect_message extracts from attributes when message.value is None."""
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

        var_names = {v.name for v in result.variables}
        assert "hintVar" in var_names


class TestIntrospectionBranchCoverage:
    """Tests for introspection branch coverage."""

    def test_function_without_arguments(self) -> None:
        """Function reference with empty arguments visits function node correctly."""
        func_ref = FunctionReference(
            id=Identifier("NOARGS"),
            arguments=CallArguments(positional=(), named=()),
        )

        message = Message(
            id=Identifier("noArgsFunc"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        result = introspect_message(message)

        func_names = {f.name for f in result.functions}
        assert "NOARGS" in func_names

    def test_text_element_only_pattern(self) -> None:
        """Pattern with only TextElement yields no variables or functions."""
        message = Message(
            id=Identifier("textOnly"),
            value=Pattern(elements=(TextElement("Just plain text"),)),
            attributes=(),
        )

        result = introspect_message(message)

        assert len(result.variables) == 0
        assert len(result.functions) == 0

    def test_function_with_empty_call_arguments(self) -> None:
        """Function with empty positional and named arguments is still recorded."""
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


# ===========================================================================
# THREAD SAFETY TESTS
# ===========================================================================


class TestIntrospectionThreadSafety:
    """Verify the cache lock prevents data corruption under concurrent access.

    These tests exercise the check-compute-store pattern introduced with the
    threading.Lock that replaced the GIL-reliant lock-free WeakKeyDictionary
    access. They run in CI (no @pytest.mark.fuzz) because the thread counts
    are small and the wall-clock cost is negligible.
    """

    def test_concurrent_introspection_same_message(self) -> None:
        """Concurrent introspection of the same Message yields identical results.

        All threads must see the same MessageIntrospection (equal by content),
        and the cache must contain exactly one entry for the shared message.
        """
        message = Message(
            id=Identifier("sharedMsg"),
            value=Pattern(elements=(
                TextElement("Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )),
            attributes=(),
        )

        # Clear cache to ensure a fresh start for this test.
        with _introspection_cache_lock:
            _introspection_cache.clear()

        results: list[object] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                results.append(introspect_message(message))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 20

        # All results must be equal (same content, immutable).
        first = results[0]
        assert all(r == first for r in results)

    def test_concurrent_clear_and_introspect(self) -> None:
        """Concurrent clear + introspect does not corrupt the cache.

        After all operations complete, any surviving cached entry must be
        a valid MessageIntrospection (no partially-written garbage).
        """
        message = Message(
            id=Identifier("racyMsg"),
            value=Pattern(elements=(TextElement("race"),)),
            attributes=(),
        )

        errors: list[BaseException] = []

        def introspector() -> None:
            try:
                for _ in range(10):
                    introspect_message(message)
            except Exception as exc:
                errors.append(exc)

        def clearer() -> None:
            try:
                for _ in range(5):
                    clear_introspection_cache()
            except Exception as exc:
                errors.append(exc)

        threads = (
            [threading.Thread(target=introspector) for _ in range(8)]
            + [threading.Thread(target=clearer) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        # Final cache state must be consistent: either empty or holding a valid result.
        result = introspect_message(message)
        assert result.message_id == "racyMsg"
