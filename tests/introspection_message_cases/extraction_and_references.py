# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine import FluentBundle
from ftllexengine.enums import ReferenceKind
from ftllexengine.introspection import (
    extract_references,
    extract_references_by_attribute,
    extract_variables,
    introspect_message,
)
from ftllexengine.introspection.message import (
    IntrospectionVisitor,
    ReferenceExtractor,
)
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    StringLiteral,
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

    def test_function_variable_in_positional_arg_with_literal_named_arg(self) -> None:
        """Variable reference in positional arg is extracted; named arg literals are not.

        Per FTL spec, named argument values are constrained to StringLiteral or
        NumberLiteral. They cannot be VariableReferences. Only positional arguments
        contribute variable names when they contain VariableReference nodes.
        """
        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="x")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt"),
                        value=StringLiteral(value="opt_value"),
                    ),
                ),
            ),
        )
        msg = _make_message("test", value=_make_pattern(Placeable(expression=func_ref)))
        info = introspect_message(msg, use_cache=False)
        # Only "x" from positional arg; named arg literal value contributes nothing
        assert info.get_variable_names() == frozenset({"x"})

    def test_function_named_args_with_literals_do_not_contribute_variable_names(
        self,
    ) -> None:
        """Named argument literal values do not contribute to variable_names.

        Per FTL spec, named argument values are always literals (StringLiteral or
        NumberLiteral), never VariableReferences. Variables from positional args
        are extracted; named arg literal values are not variable references.
        """
        func_ref = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="val")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="a"),
                        value=StringLiteral(value="first"),
                    ),
                    NamedArgument(
                        name=Identifier(name="b"),
                        value=StringLiteral(value="second"),
                    ),
                    NamedArgument(
                        name=Identifier(name="n"),
                        value=NumberLiteral(value=42, raw="42"),
                    ),
                ),
            ),
        )
        msg = _make_message("test", value=_make_pattern(Placeable(expression=func_ref)))
        info = introspect_message(msg, use_cache=False)
        # Only "val" from positional arg; named arg literal values contribute nothing
        assert info.get_variable_names() == frozenset({"val"})
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
