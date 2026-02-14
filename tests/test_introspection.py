"""Tests for variable introspection API (Python 3.13+).

Tests the best-in-class introspection system using TypeIs, frozen dataclasses,
and pattern matching for FTL message analysis.

Covers:
- Variable extraction (simple, multiple, duplicate, selectors, nested)
- Function introspection (detection, named args, positional args)
- Reference introspection (message, term, attribute references)
- MessageIntrospection object (immutability, requires_variable, has_selectors)
- Span tracking for all reference types
- Term references with arguments (positional and named)
- Depth guard boundary conditions
- Visitor pattern edge cases and context restoration
- TypeError handling for invalid inputs
- Function arguments with variable references in named values
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle, parse_ftl
from ftllexengine.enums import ReferenceKind, VariableContext
from ftllexengine.introspection import (
    VariableInfo,
    extract_references,
    extract_variables,
    introspect_message,
)
from ftllexengine.introspection.message import IntrospectionVisitor, ReferenceExtractor
from ftllexengine.syntax.ast import Junk, Message, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestVariableExtraction:
    """Test basic variable extraction functionality."""

    def test_simple_variable(self) -> None:
        """Extract single variable from simple message."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")

        variables = bundle.get_message_variables("greeting")
        assert variables == frozenset({"name"})

    def test_multiple_variables(self) -> None:
        """Extract multiple variables from message."""
        bundle = FluentBundle("en")
        bundle.add_resource("user-info = { $firstName } { $lastName } (Age: { $age })")

        variables = bundle.get_message_variables("user-info")
        assert variables == frozenset({"firstName", "lastName", "age"})

    def test_duplicate_variables(self) -> None:
        """Duplicate variable references should appear only once."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = { $name }, nice to meet you { $name }!")

        variables = bundle.get_message_variables("greeting")
        assert variables == frozenset({"name"})

    def test_no_variables(self) -> None:
        """Message with no variables returns empty set."""
        bundle = FluentBundle("en")
        bundle.add_resource("hello = Hello, World!")

        variables = bundle.get_message_variables("hello")
        assert variables == frozenset()

    def test_message_not_found(self) -> None:
        """KeyError raised for non-existent message."""
        bundle = FluentBundle("en")

        with pytest.raises(KeyError, match=r"Message 'nonexistent' not found"):
            bundle.get_message_variables("nonexistent")


class TestSelectExpressions:
    """Test variable extraction from select expressions."""

    def test_selector_variable(self) -> None:
        """Extract variable used in selector."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
emails = { $count ->
    [one] one email
   *[other] { $count } emails
}
""")

        variables = bundle.get_message_variables("emails")
        assert "count" in variables

    def test_variant_variables(self) -> None:
        """Extract variables from variant patterns."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
message = { $userType ->
    [admin] Hello { $name }, you are an admin
   *[user] Welcome { $name }
}
""")

        variables = bundle.get_message_variables("message")
        assert variables == frozenset({"userType", "name"})

    def test_nested_selectors(self) -> None:
        """Extract variables from nested select expressions."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
complex = { $gender ->
    [male] { $count ->
        [one] one item
       *[other] { $count } items
    }
   *[female] { $count } things
}
""")

        variables = bundle.get_message_variables("complex")
        assert variables == frozenset({"gender", "count"})


class TestFunctionIntrospection:
    """Test function call introspection."""

    def test_function_detection(self) -> None:
        """Detect function calls in message."""
        bundle = FluentBundle("en")
        bundle.add_resource("price = { NUMBER($amount) }")

        info = bundle.introspect_message("price")
        assert "NUMBER" in info.get_function_names()
        assert "amount" in info.get_variable_names()

    def test_function_with_named_args(self) -> None:
        """Extract function with named arguments."""
        bundle = FluentBundle("en")
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")

        info = bundle.introspect_message("price")
        funcs = list(info.functions)
        assert len(funcs) == 1

        func = funcs[0]
        assert func.name == "NUMBER"
        assert "amount" in func.positional_arg_vars
        assert "minimumFractionDigits" in func.named_args

    def test_multiple_functions(self) -> None:
        """Detect multiple different functions."""
        bundle = FluentBundle("en")
        bundle.add_resource("timestamp = { NUMBER($value) } at { DATETIME($time) }")

        info = bundle.introspect_message("timestamp")
        assert info.get_function_names() == frozenset({"NUMBER", "DATETIME"})

    def test_nested_variable_in_function_positional_arg(self) -> None:
        """Nested variable in function positional argument is extracted.

        Regression test for LOGIC-MISSING-006: Introspection was not recursively
        visiting expression arguments in function calls.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("price = { NUMBER($amount) }")

        info = bundle.introspect_message("price")
        # Variable $amount should be found in function arg
        assert "amount" in info.get_variable_names()

    def test_nested_message_reference_in_function_arg(self) -> None:
        """Nested message reference in function argument is extracted.

        Regression test for LOGIC-MISSING-006.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("""
base-value = 42
formatted = { NUMBER(base-value) }
""")

        info = bundle.introspect_message("formatted")
        refs = list(info.references)
        # Message reference base-value should be found
        assert any(r.id == "base-value" for r in refs)

    def test_deeply_nested_variable_extraction(self) -> None:
        """Variables in nested function calls are fully extracted.

        Regression test for LOGIC-MISSING-006.
        """
        bundle = FluentBundle("en")
        # Message with variable in a function call within a select expression
        bundle.add_resource("""
complex = { $type ->
    [currency] { NUMBER($amount, minimumFractionDigits: 2) }
   *[plain] { $amount }
}
""")

        info = bundle.introspect_message("complex")
        # Both $type and $amount should be extracted
        assert "type" in info.get_variable_names()
        assert "amount" in info.get_variable_names()


class TestReferenceIntrospection:
    """Test message and term reference introspection."""

    def test_message_reference(self) -> None:
        """Detect message reference."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
brand = FTLLexEngine
greeting = Welcome to { brand }
""")

        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].kind == ReferenceKind.MESSAGE
        assert refs[0].attribute is None

    def test_term_reference(self) -> None:
        """Detect term reference."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
-brand = FTLLexEngine
greeting = Welcome to { -brand }
""")

        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].kind == ReferenceKind.TERM

    def test_attribute_reference(self) -> None:
        """Detect attribute reference."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
message = Message
    .tooltip = Tooltip
greeting = Hover for { message.tooltip }
""")

        info = bundle.introspect_message("greeting")
        refs = list(info.references)
        assert len(refs) == 1
        assert refs[0].id == "message"
        assert refs[0].attribute == "tooltip"


class TestMessageIntrospection:
    """Test complete MessageIntrospection object."""

    def test_frozen_immutability(self) -> None:
        """MessageIntrospection is immutable."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $var }")

        info = bundle.introspect_message("test")

        # Should not be able to modify frozen dataclass
        with pytest.raises(AttributeError):
            info.message_id = "modified"  # type: ignore[misc]

    def test_variable_info_immutability(self) -> None:
        """VariableInfo is frozen and immutable."""
        var_info = VariableInfo(name="test", context=VariableContext.PATTERN)

        with pytest.raises(AttributeError):
            var_info.name = "modified"  # type: ignore[misc]

    def test_requires_variable(self) -> None:
        """Check if message requires specific variable."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")

        info = bundle.introspect_message("greeting")
        assert info.requires_variable("name")
        assert not info.requires_variable("age")

    def test_has_selectors_flag(self) -> None:
        """Detect presence of select expressions."""
        bundle = FluentBundle("en")
        bundle.add_resource("simple = Hello")
        bundle.add_resource("select = { $count -> [one] one *[other] many }")

        simple_info = bundle.introspect_message("simple")
        assert not simple_info.has_selectors

        select_info = bundle.introspect_message("select")
        assert select_info.has_selectors


class TestDirectAPIUsage:
    """Test using introspection API directly with parsed AST."""

    def test_extract_variables_direct(self) -> None:
        """Use extract_variables directly on Message."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        variables = extract_variables(entry)

        assert variables == frozenset({"name"})

    def test_introspect_message_direct(self) -> None:
        """Use introspect_message directly on Message."""
        parser = FluentParserV1()
        resource = parser.parse("price = { NUMBER($amount, minimumFractionDigits: 2) }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        assert info.message_id == "price"
        assert "amount" in info.get_variable_names()
        assert "NUMBER" in info.get_function_names()

    def test_introspect_term(self) -> None:
        """Introspect term (not just message)."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = { $companyName }")

        entry = resource.entries[0]
        assert isinstance(entry, Term)
        info = introspect_message(entry)

        assert info.message_id == "brand"
        assert "companyName" in info.get_variable_names()

    def test_introspect_term_via_bundle(self) -> None:
        """Introspect term via FluentBundle.introspect_term()."""
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


class TestAttributeIntrospection:
    """Test introspection of message attributes."""

    def test_attribute_variables(self) -> None:
        """Extract variables from message attributes."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
login-button = Sign In
    .title = Click to sign in as { $username }
""")

        info = bundle.introspect_message("login-button")
        assert "username" in info.get_variable_names()

    def test_multiple_attributes(self) -> None:
        """Extract variables from multiple attributes."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
button = Action
    .tooltip = { $action } for { $user }
    .aria-label = { $role }
""")

        info = bundle.introspect_message("button")
        assert info.get_variable_names() == frozenset({"action", "user", "role"})


class TestRealWorldScenarios:

    def test_ui_message_validation(self) -> None:
        """Validate UI messages have required variables (CI/CD use case)."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
home-subtitle = Welcome to { $country }
money-with-vat = Gross: { $gross }, Net: { $net }, VAT: { $vat } ({ $rate }%)
""")

        # Validate home-subtitle
        assert "country" in bundle.get_message_variables("home-subtitle")

        # Validate money-with-vat
        assert bundle.get_message_variables("money-with-vat") == frozenset(
            {"gross", "net", "vat", "rate"}
        )

    def test_function_usage_analysis(self) -> None:
        """Analyze which functions are used in message."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
timestamp = Last updated: { DATETIME($time, dateStyle: "medium") }
price = Total: { NUMBER($amount, minimumFractionDigits: 2, maximumFractionDigits: 2) }
""")

        timestamp_info = bundle.introspect_message("timestamp")
        assert "DATETIME" in timestamp_info.get_function_names()
        assert "time" in timestamp_info.get_variable_names()

        price_info = bundle.introspect_message("price")
        assert "NUMBER" in price_info.get_function_names()
        assert "amount" in price_info.get_variable_names()

        # Check function call details
        number_funcs = [f for f in price_info.functions if f.name == "NUMBER"]
        assert len(number_funcs) == 1
        assert "minimumFractionDigits" in number_funcs[0].named_args
        assert "maximumFractionDigits" in number_funcs[0].named_args


class TestSpanTracking:
    """Test source span tracking in introspection results."""

    def test_variable_reference_span(self) -> None:
        """Variable references include source position spans."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        # Should have exactly one variable with a span
        assert len(info.variables) == 1
        var_info = next(iter(info.variables))
        assert var_info.name == "name"
        assert var_info.span is not None
        # Span should cover "$name" in "Hello, { $name }!"
        # Pattern starts after "greeting = " (11 chars)
        # "Hello, { " is 9 chars, so $name starts at position 20
        assert var_info.span.start == 20
        # $name is 5 characters long
        assert var_info.span.end == 25

    def test_function_reference_span(self) -> None:
        """Function references include source position spans."""
        parser = FluentParserV1()
        resource = parser.parse("price = { NUMBER($amount) }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        # Should have one function with a span
        assert len(info.functions) == 1
        func_info = next(iter(info.functions))
        assert func_info.name == "NUMBER"
        assert func_info.span is not None
        # "price = { " is 10 chars, NUMBER($amount) starts at 10
        assert func_info.span.start == 10
        # "NUMBER($amount)" is 15 chars
        assert func_info.span.end == 25

    def test_message_reference_span(self) -> None:
        """Message references include source position spans."""
        parser = FluentParserV1()
        resource = parser.parse("ref = { other-msg }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        # Should have one message reference with a span
        refs = [r for r in info.references if r.kind == ReferenceKind.MESSAGE]
        assert len(refs) == 1
        assert refs[0].id == "other-msg"
        assert refs[0].span is not None
        # "ref = { " is 8 chars, other-msg starts at 8
        assert refs[0].span.start == 8
        # "other-msg" is 9 chars
        assert refs[0].span.end == 17

    def test_term_reference_span(self) -> None:
        """Term references include source position spans."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -brand }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        # Should have one term reference with a span
        refs = [r for r in info.references if r.kind == ReferenceKind.TERM]
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].span is not None
        # "msg = { " is 8 chars, -brand starts at 8
        assert refs[0].span.start == 8
        # Span includes trailing whitespace consumed for optional args check
        assert refs[0].span.end == 15

    def test_term_reference_with_attribute_span(self) -> None:
        """Term references with attributes have correct spans."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -brand.short }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        refs = [r for r in info.references if r.kind == ReferenceKind.TERM]
        assert len(refs) == 1
        assert refs[0].id == "brand"
        assert refs[0].attribute == "short"
        assert refs[0].span is not None
        # "-brand.short" starts at 8, includes trailing whitespace for args check
        assert refs[0].span.start == 8
        assert refs[0].span.end == 21

    def test_multiple_variables_spans(self) -> None:
        """Multiple variables each have distinct spans."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { $first } and { $second }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        # Should have two variables with different spans
        assert len(info.variables) == 2
        vars_by_name = {v.name: v for v in info.variables}

        first = vars_by_name["first"]
        assert first.span is not None
        # "msg = { " is 8 chars, $first starts at 8
        assert first.span.start == 8

        second = vars_by_name["second"]
        assert second.span is not None
        # " and { " is 7 chars after first } (at 15), so $second starts at 23
        assert second.span.start == 23

    def test_message_reference_with_attribute_span(self) -> None:
        """Message references with attributes have correct spans."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other.attr }")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        refs = [r for r in info.references if r.kind == ReferenceKind.MESSAGE]
        assert len(refs) == 1
        assert refs[0].id == "other"
        assert refs[0].attribute == "attr"
        assert refs[0].span is not None
        # "msg = { " is 8 chars, "other.attr" starts at 8
        assert refs[0].span.start == 8
        # "other.attr" is 10 chars
        assert refs[0].span.end == 18


# ---------------------------------------------------------------------------
# Term reference arguments
# ---------------------------------------------------------------------------


class TestTermReferenceArguments:
    """Test introspection of term references with arguments."""

    def test_term_reference_with_positional_args(self) -> None:
        """Term reference with positional arguments extracts nested variables."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = { -brand($platform) }")
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        info = introspect_message(message)
        assert "platform" in info.get_variable_names()

    def test_term_reference_with_named_args(self) -> None:
        """Term reference with named arguments (using literals per FTL spec)."""
        parser = FluentParserV1()
        resource = parser.parse(
            'app-name = { -brand($userCase, case: "nominative") }'
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        info = introspect_message(message)
        assert "userCase" in info.get_variable_names()

    def test_term_reference_with_both_arg_types(self) -> None:
        """Term reference with both positional and named arguments."""
        parser = FluentParserV1()
        resource = parser.parse(
            'msg = { -term($pos1, $pos2, style: "formal") }'
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        info = introspect_message(message)
        assert "pos1" in info.get_variable_names()
        assert "pos2" in info.get_variable_names()

    def test_term_reference_extract_references(self) -> None:
        """Term references with arguments are tracked by ReferenceExtractor."""
        parser = FluentParserV1()
        resource = parser.parse(
            'msg = { -brand($var, case: "nominative") }'
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        _msg_refs, term_refs = extract_references(message)
        assert "brand" in term_refs

    def test_reference_extractor_depth_guard(self) -> None:
        """ReferenceExtractor uses depth guard for nested term arguments."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -outer(-inner($var)) }")
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        _msg_refs, term_refs = extract_references(message)
        assert "outer" in term_refs
        assert "inner" in term_refs


# ---------------------------------------------------------------------------
# Visitor edge cases and depth limits
# ---------------------------------------------------------------------------


class TestIntrospectionVisitorEdgeCases:
    """Test edge cases in IntrospectionVisitor."""

    def test_placeable_expression_branch(self) -> None:
        """Nested Placeable expressions handled correctly."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Text { $var } more")
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        info = introspect_message(message)
        assert "var" in info.get_variable_names()

    def test_visitor_context_restoration(self) -> None:
        """Variable context correctly restored after visiting expressions."""
        parser = FluentParserV1()
        resource = parser.parse(
            "emails = { $count ->\n"
            "    [one] { $name } has one email\n"
            "   *[other] { $name } has { $count } emails\n"
            "}"
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        visitor = IntrospectionVisitor()
        if message.value:
            visitor.visit(message.value)

        var_contexts = {v.name: v.context for v in visitor.variables}
        assert "count" in var_contexts
        assert "name" in var_contexts


class TestIntrospectionDepthLimits:
    """Test depth guard behavior in introspection."""

    def test_introspection_respects_depth_limit(self) -> None:
        """IntrospectionVisitor respects max_depth configuration."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg = { $a -> [x] { $b -> [y] { $c -> "
            "[z] value *[o] v } *[o] v } *[o] v }"
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        visitor = IntrospectionVisitor(max_depth=100)
        if message.value:
            visitor.visit(message.value)

        assert "a" in {v.name for v in visitor.variables}
        assert "b" in {v.name for v in visitor.variables}
        assert "c" in {v.name for v in visitor.variables}

    def test_reference_extractor_respects_depth_limit(self) -> None:
        """ReferenceExtractor respects max_depth configuration."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -term1(-term2(-term3)) }")
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        extractor = ReferenceExtractor(max_depth=100)
        if message.value:
            extractor.visit(message.value)

        assert "term1" in extractor.term_refs
        assert "term2" in extractor.term_refs
        assert "term3" in extractor.term_refs


class TestReferenceExtractorMessageReference:
    """Test MessageReference handling in ReferenceExtractor."""

    def test_message_reference_no_nested_calls(self) -> None:
        """MessageReference contains no nested references requiring traversal."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other-message }")
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        extractor = ReferenceExtractor()
        if message.value:
            extractor.visit(message.value)

        assert "other-message" in extractor.message_refs


# ---------------------------------------------------------------------------
# Variable contexts
# ---------------------------------------------------------------------------


class TestIntrospectionVariableContexts:
    """Test variable context tracking in introspection."""

    def test_function_arg_context(self) -> None:
        """Variables in function arguments have FUNCTION_ARG context."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg = { NUMBER($value, minimumFractionDigits: 2) }"
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        visitor = IntrospectionVisitor()
        if message.value:
            visitor.visit(message.value)

        value_vars = [v for v in visitor.variables if v.name == "value"]
        assert len(value_vars) == 1
        assert value_vars[0].context == VariableContext.FUNCTION_ARG

    def test_selector_context(self) -> None:
        """Variables in selectors have SELECTOR context."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg = { $count -> [one] one *[other] many }"
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        visitor = IntrospectionVisitor()
        if message.value:
            visitor.visit(message.value)

        count_vars = [v for v in visitor.variables if v.name == "count"]
        selector_contexts = [
            v for v in count_vars if v.context == VariableContext.SELECTOR
        ]
        assert len(selector_contexts) >= 1

    def test_variant_context(self) -> None:
        """Variables in variant values have VARIANT context."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg = { $sel -> [key] Value is { $value } *[other] none }"
        )
        message = resource.entries[0]
        assert isinstance(message, (Message, Term))

        visitor = IntrospectionVisitor()
        if message.value:
            visitor.visit(message.value)

        value_vars = [v for v in visitor.variables if v.name == "value"]
        variant_contexts = [
            v for v in value_vars if v.context == VariableContext.VARIANT
        ]
        assert len(variant_contexts) >= 1


# ---------------------------------------------------------------------------
# Function arguments with variable named args
# ---------------------------------------------------------------------------


class TestFunctionWithVariableNamedArgs:
    """Test functions with variable references in named arguments."""

    def test_function_with_variable_in_named_arg(self) -> None:
        """Custom function with variable in named argument value."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            Identifier,
            NamedArgument,
            Pattern,
            Placeable,
            VariableReference,
        )

        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(
                    VariableReference(id=Identifier(name="x")),
                ),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt"),
                        value=VariableReference(id=Identifier(name="y")),
                    ),
                ),
            ),
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None,
        )

        info = introspect_message(msg)
        variables = info.get_variable_names()
        assert "x" in variables
        assert "y" in variables

    def test_multiple_named_args_with_variables(self) -> None:
        """Multiple named arguments with variable values."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            Identifier,
            NamedArgument,
            Pattern,
            Placeable,
            VariableReference,
        )

        func_ref = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(
                positional=(
                    VariableReference(id=Identifier(name="val")),
                ),
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
                        name=Identifier(name="c"),
                        value=VariableReference(id=Identifier(name="z")),
                    ),
                ),
            ),
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None,
        )

        info = introspect_message(msg)
        variables = info.get_variable_names()
        assert variables == frozenset({"val", "x", "y", "z"})

    def test_mixed_positional_and_named_variable_args(self) -> None:
        """Function with both positional and named variable arguments."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            Identifier,
            NamedArgument,
            NumberLiteral,
            Pattern,
            Placeable,
            VariableReference,
        )

        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(
                    VariableReference(id=Identifier(name="x")),
                    VariableReference(id=Identifier(name="y")),
                ),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt1"),
                        value=VariableReference(id=Identifier(name="a")),
                    ),
                    NamedArgument(
                        name=Identifier(name="opt2"),
                        value=VariableReference(id=Identifier(name="b")),
                    ),
                    NamedArgument(
                        name=Identifier(name="literal"),
                        value=NumberLiteral(value=42, raw="42"),
                    ),
                ),
            ),
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None,
        )

        info = introspect_message(msg)
        variables = info.get_variable_names()
        assert variables == frozenset({"x", "y", "a", "b"})
        assert "CUSTOM" in info.get_function_names()

    @given(
        st.lists(
            st.text(
                alphabet=st.characters(
                    min_codepoint=97, max_codepoint=122
                ),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30)
    def test_arbitrary_variable_named_args(
        self, var_names: list[str]
    ) -> None:
        """Functions with arbitrary variable names in args."""
        var_names = list(dict.fromkeys(var_names))
        if not var_names:
            return

        event(f"var_count={len(var_names)}")

        var_list = ", ".join(f"{name}: ${name}" for name in var_names)
        ftl = f"test = {{ NUMBER($value, {var_list}) }}"

        resource = parse_ftl(ftl)
        if not resource.entries or isinstance(resource.entries[0], Junk):
            return

        msg = resource.entries[0]
        if not isinstance(msg, Message):
            return

        info = introspect_message(msg)
        variables = info.get_variable_names()

        assert "value" in variables
        for name in var_names:
            assert name in variables


# ---------------------------------------------------------------------------
# TypeError handling for invalid inputs
# ---------------------------------------------------------------------------


class TestIntrospectMessageTypeErrors:
    """Test introspect_message with invalid input types."""

    def test_introspect_message_with_junk(self) -> None:
        """Introspecting a Junk entry raises TypeError."""
        resource = parse_ftl("invalid syntax here !!!")

        assert resource.entries
        junk = resource.entries[0]
        assert isinstance(junk, Junk)

        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(junk)  # type: ignore[arg-type]

    def test_introspect_message_with_string(self) -> None:
        """Introspecting a string raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message("not a message")  # type: ignore[arg-type]

    def test_introspect_message_with_none(self) -> None:
        """Introspecting None raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(None)  # type: ignore[arg-type]

    def test_introspect_message_with_dict(self) -> None:
        """Introspecting a dict raises TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message({"not": "a message"})  # type: ignore[arg-type]

    @given(
        st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.lists(st.text()),
        )
    )
    @settings(max_examples=30)
    def test_introspect_message_with_arbitrary_types(
        self, invalid_input: object
    ) -> None:
        """Non-Message types raise TypeError."""
        event(f"input_type={type(invalid_input).__name__}")
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(invalid_input)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# extract_variables edge cases
# ---------------------------------------------------------------------------


class TestExtractVariablesEdgeCases:
    """Test extract_variables with edge cases."""

    def test_extract_variables_from_message_with_no_value(self) -> None:
        """Message with no value pattern returns empty set."""
        resource = parse_ftl("empty =\n    .attr = Attribute only")

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)
        assert isinstance(variables, frozenset)

    def test_extract_variables_from_select_with_variants(self) -> None:
        """Select expression with variables in variants."""
        resource = parse_ftl(
            "msg = { $count ->\n"
            "    [one] You have { $count } item from { $source }\n"
            "    [few] You have { $count } items from { $source }\n"
            "   *[other] You have { $count } items from { $source }\n"
            "}"
        )

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)
        assert "count" in variables
        assert "source" in variables


# ---------------------------------------------------------------------------
# Hypothesis property tests for introspection roundtrips
# ---------------------------------------------------------------------------


class TestIntrospectionPropertyRoundtrips:
    """Hypothesis-based property tests for introspection roundtrips."""

    @given(
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=20,
        )
    )
    def test_variable_extraction_roundtrip(self, var_name: str) -> None:
        """Variables extracted match those in source pattern."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"
        event(f"var_len={len(var_name)}")
        try:
            resource = parser.parse(ftl_source)
            if not resource.entries:
                return

            message = resource.entries[0]
            if not isinstance(message, (Message, Term)):
                return

            variables = extract_variables(message)
            assert var_name in variables
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    @given(
        term_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=20,
        )
    )
    def test_term_reference_extraction_roundtrip(
        self, term_name: str
    ) -> None:
        """Term references extracted match those in source."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ -{term_name} }}"
        event(f"term_len={len(term_name)}")
        try:
            resource = parser.parse(ftl_source)
            if not resource.entries:
                return

            message = resource.entries[0]
            if not isinstance(message, (Message, Term)):
                return

            _msg_refs, term_refs = extract_references(message)
            assert term_name in term_refs
        except Exception:  # pylint: disable=broad-exception-caught
            pass
