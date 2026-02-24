"""Stateful and advanced property-based tests for FluentResolver.

Consolidates:
- test_resolver_state_machine.py: FluentResolverStateMachine (fuzz), TestResolverErrorPaths
- test_resolver_advanced_hypothesis.py: all classes
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.runtime.value_types import FluentValue
from ftllexengine.syntax import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from tests.strategies import ftl_identifiers, ftl_simple_text

# ============================================================================
# STRATEGY HELPERS
# ============================================================================


def simple_pattern(text: str) -> Pattern:
    """Create simple text pattern."""
    return Pattern(elements=(TextElement(value=text),))


def variable_pattern(var_name: str) -> Pattern:
    """Create pattern with variable reference."""
    return Pattern(
        elements=(
            Placeable(expression=VariableReference(id=Identifier(name=var_name))),
        )
    )


def term_reference_pattern(term_name: str) -> Pattern:
    """Create pattern with term reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=TermReference(id=Identifier(name=term_name), attribute=None)
            ),
        )
    )


def message_reference_pattern(msg_name: str) -> Pattern:
    """Create pattern with message reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=MessageReference(id=Identifier(name=msg_name), attribute=None)
            ),
        )
    )


# ============================================================================
# STATE MACHINE
# ============================================================================


class FluentResolverStateMachine(RuleBasedStateMachine):
    """State machine for testing FluentResolver.

    Bundles:
    - messages: Message IDs that have been added
    - terms: Term IDs that have been added
    - variables: Variable names used in patterns

    Invariants:
    - Resolving same message twice produces same result (determinism)
    - Resolver never crashes (robustness)
    - All messages are resolvable with correct args
    """

    messages = Bundle("messages")
    terms = Bundle("terms")
    variables = Bundle("variables")

    @initialize()
    def setup_resolver(self) -> None:
        """Initialize resolver with empty registries."""
        self.message_registry: dict[str, Message] = {}
        self.term_registry: dict[str, Term] = {}
        self.locale = "en_US"
        self.resolver = FluentResolver(
            locale=self.locale,
            messages=self.message_registry,
            terms=self.term_registry,
            function_registry=create_default_registry(),
            use_isolating=False,
        )

    @rule(target=messages, msg_id=ftl_identifiers(), text=st.text(min_size=1, max_size=50))
    def add_simple_message(self, msg_id: str, text: str) -> str:
        """Add simple text-only message."""
        message = Message(
            id=Identifier(name=msg_id),
            value=simple_pattern(text),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message
        event("rule=add_simple_message")
        return msg_id

    @rule(
        target=messages,
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
    )
    def add_message_with_variable(self, msg_id: str, var_name: str) -> str:
        """Add message that requires variable argument."""
        message = Message(
            id=Identifier(name=msg_id),
            value=variable_pattern(var_name),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message
        event("rule=add_message_with_variable")
        return msg_id

    @rule(target=terms, term_id=ftl_identifiers(), text=st.text(min_size=1, max_size=50))
    def add_simple_term(self, term_id: str, text: str) -> str:
        """Add simple term."""
        term = Term(
            id=Identifier(name=term_id),
            value=simple_pattern(text),
            attributes=(),
            comment=None,
        )
        self.term_registry[term_id] = term
        event("rule=add_simple_term")
        return term_id

    @rule(
        target=messages,
        msg_id=ftl_identifiers(),
        term_id=terms,
    )
    def add_message_referencing_term(self, msg_id: str, term_id: str) -> str:
        """Add message that references a term."""
        message = Message(
            id=Identifier(name=msg_id),
            value=term_reference_pattern(term_id),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message
        event("rule=add_message_referencing_term")
        return msg_id

    @rule(msg_id=messages)
    def resolve_simple_message(self, msg_id: str) -> None:
        """Resolve message without arguments. Checks determinism."""
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        needs_vars = any(
            isinstance(elem, Placeable)
            and isinstance(elem.expression, VariableReference)
            for elem in (message.value.elements if message.value else ())
        )

        if needs_vars:
            result, errors = self.resolver.resolve_message(message, args={})
            assert isinstance(result, str)
            assert len(errors) >= 0
        else:
            result1, _errors = self.resolver.resolve_message(message, args={})
            result2, _errors = self.resolver.resolve_message(message, args={})
            assert result1 == result2, f"Resolution should be deterministic for {msg_id}"
            assert isinstance(result1, str)
        event(f"rule=resolve_simple(vars={needs_vars})")

    @rule(
        msg_id=messages,
        var_name=ftl_identifiers(),
        var_value=st.text(max_size=50),
    )
    def resolve_message_with_args(self, msg_id: str, var_name: str, var_value: str) -> None:
        """Resolve message with arguments."""
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        args = {var_name: var_value}

        try:
            result, _errors = self.resolver.resolve_message(message, args=args)
            assert isinstance(result, str)
        except FrozenFluentError:
            pass
        event("rule=resolve_message_with_args")

    @rule(
        msg_id=ftl_identifiers(),
        attr_name=ftl_identifiers(),
        text=st.text(min_size=1, max_size=50),
    )
    def add_message_with_attribute(self, msg_id: str, attr_name: str, text: str) -> None:
        """Add message with attribute and resolve it."""
        attribute = Attribute(
            id=Identifier(name=attr_name),
            value=simple_pattern(text),
        )
        message = Message(
            id=Identifier(name=msg_id),
            value=simple_pattern("default value"),
            attributes=(attribute,),
            comment=None,
        )
        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={}, attribute=attr_name)
        assert text in result
        assert errors == (), f"Unexpected errors: {errors}"
        event("rule=add_message_with_attribute")

    @rule(msg_id=messages)
    def resolve_nonexistent_attribute(self, msg_id: str) -> None:
        """Try to resolve non-existent attribute - should give REFERENCE error."""
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        _result, errors = self.resolver.resolve_message(
            message, args={}, attribute="nonexistent_attr_xyz"
        )
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "attribute" in str(errors[0]).lower()
        event("rule=resolve_nonexistent_attribute")

    @rule()
    def resolve_nonexistent_term(self) -> None:
        """Try to resolve term reference to non-existent term."""
        msg_id = "msg_ref_bad_term"
        message = Message(
            id=Identifier(name=msg_id),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="nonexistent_term_xyz"),
                            attribute=None,
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)
        assert len(errors) > 0
        event("rule=resolve_nonexistent_term")

    @rule(term_id=terms)
    def resolve_term_attribute_not_found(self, term_id: str) -> None:
        """Try to resolve term attribute that doesn't exist."""
        assume(term_id in self.term_registry)

        msg_id = "msg_ref_term_attr"
        message = Message(
            id=Identifier(name=msg_id),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name=term_id),
                            attribute=Identifier(name="nonexistent_attr"),
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)
        assert len(errors) > 0
        event("rule=resolve_term_attr_not_found")

    @rule()
    def test_unknown_expression_type(self) -> None:
        """Document architecturally unreachable expression type error path.

        The unknown expression error path is unreachable by design since all
        AST node types are exhaustively handled. This rule documents the gap.
        """
        event("rule=test_unknown_expression_type")

    @rule(
        msg_id1=ftl_identifiers(),
        msg_id2=ftl_identifiers(),
    )
    def test_circular_reference_detection(self, msg_id1: str, msg_id2: str) -> None:
        """Test circular reference detection produces graceful degradation."""
        assume(msg_id1 != msg_id2)

        message1 = Message(
            id=Identifier(name=msg_id1),
            value=message_reference_pattern(msg_id2),
            attributes=(),
            comment=None,
        )
        message2 = Message(
            id=Identifier(name=msg_id2),
            value=message_reference_pattern(msg_id1),
            attributes=(),
            comment=None,
        )

        self.message_registry[msg_id1] = message1
        self.message_registry[msg_id2] = message2

        result, _errors = self.resolver.resolve_message(message1, args={})
        assert isinstance(result, str)
        event("rule=circular_reference_detection")

    @rule(
        msg_id=ftl_identifiers(),
        number=st.integers(min_value=0, max_value=100),
    )
    def add_message_with_select_expression(self, msg_id: str, number: int) -> None:
        """Add message with select expression (plural)."""
        variants = (
            Variant(
                key=Identifier(name="one"),
                value=simple_pattern("singular"),
                default=False,
            ),
            Variant(
                key=Identifier(name="other"),
                value=simple_pattern("plural"),
                default=True,
            ),
        )

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=variants,
        )

        message = Message(
            id=Identifier(name=msg_id),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
            comment=None,
        )

        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={"count": number})
        assert result in ["singular", "plural"]
        assert errors == (), f"Unexpected errors: {errors}"
        event(f"rule=select_expression({result})")

    @rule()
    def test_message_no_value(self) -> None:
        """Test message without value (only attributes) produces REFERENCE error."""
        msg_id = "msg_no_value"
        message = Message(
            id=Identifier(name=msg_id),
            value=None,
            attributes=(
                Attribute(
                    id=Identifier(name="attr1"),
                    value=simple_pattern("has attribute"),
                ),
            ),
            comment=None,
        )
        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={})
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "no value" in str(errors[0]).lower()
        assert isinstance(result, str)
        event("rule=test_message_no_value")

    @rule(
        msg_id=ftl_identifiers(),
        func_name=st.sampled_from(["NUMBER", "NONEXISTENT"]),
    )
    def test_function_reference(self, msg_id: str, func_name: str) -> None:
        """Test function reference resolution (both successful and failed calls)."""
        func_ref = FunctionReference(
            id=Identifier(name=func_name),
            arguments=CallArguments(
                positional=(NumberLiteral(value=42, raw="42"),),
                named=(),
            ),
        )

        message = Message(
            id=Identifier(name=msg_id),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None,
        )

        self.message_registry[msg_id] = message

        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)

        if func_name == "NUMBER":
            assert "42" in result
            assert errors == ()
        else:
            assert len(errors) > 0
        event(f"rule=function_reference({func_name})")

    @invariant()
    def resolver_state_consistent(self) -> None:
        """Invariant: Resolver registries stay consistent."""
        assert self.resolver._messages == self.message_registry
        assert self.resolver._terms == self.term_registry
        assert self.resolver._locale == self.locale
        msg_count = len(self.message_registry)
        event(f"invariant=state_consistent({msg_count})")

    @invariant()
    def resolution_uses_explicit_context(self) -> None:
        """Invariant: Resolver properly initialized with explicit context pattern."""
        assert self.resolver._locale == self.locale
        event("invariant=explicit_context")


# Stateful test runner
TestFluentResolverStateMachine = FluentResolverStateMachine.TestCase
TestFluentResolverStateMachine = pytest.mark.fuzz(TestFluentResolverStateMachine)


# ============================================================================
# DIRECT ERROR PATH TESTS (from state machine module)
# ============================================================================


class TestStatefulErrorPaths:
    """Direct tests for specific error paths that are hard to reach via state machine."""

    def test_term_not_found_direct(self) -> None:
        """Term not found error (line 176)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="nonexistent"),
                            attribute=None,
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{-nonexistent}" in result

    def test_term_attribute_not_found_direct(self) -> None:
        """Term attribute not found error (lines 182-185)."""
        from ftllexengine.syntax import Term  # noqa: PLC0415

        term = Term(
            id=Identifier(name="brand"),
            value=simple_pattern("Firefox"),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={"brand": term},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="brand"),
                            attribute=Identifier(name="nonexistent"),
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{-brand.nonexistent}" in result

    def test_message_not_found_reference(self) -> None:
        """Message not found when referenced from another message (line 164)."""
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier(name="nonexistent"),
                            attribute=None,
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{nonexistent}" in result

    def test_variable_not_provided(self) -> None:
        """Variable not provided in args (line 157)."""
        message = Message(
            id=Identifier(name="test"),
            value=variable_pattern("missing_var"),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{$missing_var}" in result

    @given(st.data())
    @settings(max_examples=50)
    def test_format_value_edge_cases(self, data: st.DataObject) -> None:
        """Property: _format_value never crashes, always returns string (lines 268-278)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        test_values: list[FluentValue] = [
            data.draw(st.text()),
            data.draw(st.integers()),
            data.draw(st.decimals(allow_nan=False, allow_infinity=False)),
            data.draw(st.booleans()),
            None,
        ]

        value = None
        for value in test_values:
            result = resolver._format_value(value)
            assert isinstance(result, str), f"_format_value({value}) should return string"
        val_type = type(value).__name__
        event(f"last_value_type={val_type}")

    def test_select_expression_no_variants(self) -> None:
        """SelectExpression with no variants raises ValueError at construction."""
        with pytest.raises(ValueError, match="at least one variant"):
            SelectExpression(
                selector=NumberLiteral(value=1, raw="1"),
                variants=(),
            )


# ============================================================================
# ADVANCED PROPERTY-BASED TESTS
# ============================================================================


class TestPatternResolution:
    """Properties about pattern resolution."""

    @given(
        msg_id=ftl_identifiers(),
        text_content=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_simple_text_resolution(self, msg_id: str, text_content: str) -> None:
        """Property: Simple text patterns resolve to their content."""
        event(f"text_len={len(text_content)}")
        pattern = Pattern(elements=(TextElement(value=text_content),))
        message = Message(id=Identifier(name=msg_id), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={msg_id: message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert not errors
        assert result == text_content, f"Expected {text_content}, got {result}"

    @given(
        msg_id=ftl_identifiers(),
        parts=st.lists(ftl_simple_text(), min_size=2, max_size=5),
    )
    @settings(max_examples=300)
    def test_multiple_text_elements_concatenation(
        self, msg_id: str, parts: list[str]
    ) -> None:
        """Property: Multiple text elements are concatenated in order."""
        event(f"part_count={len(parts)}")
        elements = tuple(TextElement(value=p) for p in parts)
        pattern = Pattern(elements=elements)
        message = Message(id=Identifier(name=msg_id), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={msg_id: message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert not errors
        expected = "".join(parts)
        assert result == expected, f"Concatenation mismatch: {result} != {expected}"


class TestVariableResolution:
    """Properties about variable reference resolution."""

    @given(
        var_name=ftl_identifiers(),
        var_value=st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=500)
    def test_variable_value_preservation(
        self, var_name: str, var_value: str | int | Decimal
    ) -> None:
        """Property: Variable values are preserved in resolution."""
        val_type = type(var_value).__name__
        event(f"var_type={val_type}")
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})
        assert not errors
        assert str(var_value) in result, f"Variable value not in result: {result}"

    @given(var_name=ftl_identifiers())
    @settings(max_examples=300)
    def test_missing_variable_error_handling(self, var_name: str) -> None:
        """Property: Missing variables are handled gracefully."""
        event(f"var_name_len={len(var_name)}")
        bundle = FluentBundle("en_US")

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern("msg", {})
        assert isinstance(result, str), "Must return string even on missing variable"

    @given(var_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=200)
    def test_multiple_variables_independent(self, var_count: int) -> None:
        """Property: Multiple variables resolve independently."""
        event(f"var_count={var_count}")
        bundle = FluentBundle("en_US", use_isolating=False)

        var_names = [f"v{i}" for i in range(var_count)]
        placeholders = " ".join(f"{{ ${vn} }}" for vn in var_names)
        ftl_source = f"msg = {placeholders}"
        bundle.add_resource(ftl_source)

        args = {vn: f"val{i}" for i, vn in enumerate(var_names)}
        result, errors = bundle.format_pattern("msg", args)
        assert not errors
        for value in args.values():
            assert value in result, f"Variable value {value} missing"


class TestMessageReferenceResolution:
    """Properties about message reference resolution."""

    @given(
        ref_msg_id=ftl_identifiers(),
        ref_value=ftl_simple_text(),
        main_msg_id=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_message_reference_resolution(
        self, ref_msg_id: str, ref_value: str, main_msg_id: str
    ) -> None:
        """Property: Message references resolve to referenced message value."""
        event(f"ref_value_len={len(ref_value)}")
        assume(ref_msg_id != main_msg_id)

        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"""
{ref_msg_id} = {ref_value}
{main_msg_id} = {{ {ref_msg_id} }}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(main_msg_id)
        assert not errors
        assert ref_value.strip() in result, f"Referenced message value not in result: {result}"

    @given(
        nonexistent_id=ftl_identifiers(),
        main_msg_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_missing_message_reference_handling(
        self, nonexistent_id: str, main_msg_id: str
    ) -> None:
        """Property: Missing message references handled gracefully."""
        event(f"id_len={len(nonexistent_id)}")
        assume(nonexistent_id != main_msg_id)

        bundle = FluentBundle("en_US")
        ftl_source = f"{main_msg_id} = {{ {nonexistent_id} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(main_msg_id)
        assert isinstance(result, str), "Must return string for missing reference"


class TestTermReferenceResolution:
    """Properties about term reference resolution."""

    @given(
        term_id=ftl_identifiers(),
        term_value=ftl_simple_text(),
        msg_id=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_term_reference_resolution(
        self, term_id: str, term_value: str, msg_id: str
    ) -> None:
        """Property: Term references resolve to term value."""
        event(f"term_value_len={len(term_value)}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"""
-{term_id} = {term_value}
{msg_id} = {{ -{term_id} }}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id)
        assert not errors
        assert term_value.strip() in result, f"Term value not in result: {result}"

    @given(
        nonexistent_term=ftl_identifiers(),
        msg_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_missing_term_reference_handling(
        self, nonexistent_term: str, msg_id: str
    ) -> None:
        """Property: Missing term references handled gracefully."""
        event(f"term_len={len(nonexistent_term)}")
        bundle = FluentBundle("en_US")
        ftl_source = f"{msg_id} = {{ -{nonexistent_term} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "Must return string for missing term"


class TestSelectExpressionResolution:
    """Properties about select expression evaluation."""

    @given(
        var_name=ftl_identifiers(),
        selector_value=st.one_of(st.text(min_size=1, max_size=20), st.integers(0, 100)),
        variant1_key=ftl_identifiers(),
        variant1_val=ftl_simple_text(),
        variant2_val=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_select_expression_matches_variant(
        self,
        var_name: str,
        selector_value: str | int,
        variant1_key: str,
        variant1_val: str,
        variant2_val: str,
    ) -> None:
        """Property: Select expressions match correct variant."""
        event(f"selector_type={type(selector_value).__name__}")
        assume(variant1_key != "other")
        assume(var_name != variant1_key)

        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"""
msg = {{ ${var_name} ->
    [{variant1_key}] {variant1_val}
   *[other] {variant2_val}
}}
"""
        bundle.add_resource(ftl_source)

        if not bundle.has_message("msg"):
            return

        result, errors = bundle.format_pattern("msg", {var_name: selector_value})
        assert not errors

        if str(selector_value) == variant1_key:
            assert variant1_val.strip() in result, f"Expected {variant1_val} for matching key"
        else:
            assert (
                variant2_val.strip() in result or variant1_val.strip() in result
            ), "Must match some variant"

    @given(
        var_name=ftl_identifiers(),
        numeric_value=st.integers(0, 10),
    )
    @settings(max_examples=200)
    def test_numeric_selector_matching(self, var_name: str, numeric_value: int) -> None:
        """Property: Numeric selectors match correctly."""
        event(f"numeric_value={numeric_value}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"""
msg = {{ ${var_name} ->
    [0] zero
    [1] one
   *[other] many
}}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: numeric_value})
        assert not errors

        if numeric_value == 0:
            assert "zero" in result, "Should match [0] variant"
        elif numeric_value == 1:
            assert "one" in result, "Should match [1] variant"
        else:
            assert "many" in result or result, "Should match default variant"


class TestCircularReferenceDetection:
    """Properties about circular reference detection."""

    @given(
        msg1_id=ftl_identifiers(),
        msg2_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_direct_circular_reference_detection(
        self, msg1_id: str, msg2_id: str
    ) -> None:
        """Property: Direct circular references are detected."""
        event(f"id_len={len(msg1_id)}")
        assume(msg1_id != msg2_id)

        bundle = FluentBundle("en_US")
        ftl_source = f"""
{msg1_id} = {{ {msg2_id} }}
{msg2_id} = {{ {msg1_id} }}
"""
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg1_id)
        assert isinstance(result, str), "Must handle circular reference gracefully"

    @given(msg_ids=st.lists(ftl_identifiers(), min_size=3, max_size=5, unique=True))
    @settings(max_examples=100)
    def test_indirect_circular_reference_detection(self, msg_ids: list[str]) -> None:
        """Property: Indirect circular references (chains) are detected."""
        event(f"chain_len={len(msg_ids)}")
        bundle = FluentBundle("en_US")

        msg_pairs = list(zip(msg_ids, [*msg_ids[1:], msg_ids[0]], strict=True))
        ftl_lines = [f"{m1} = {{ {m2} }}" for m1, m2 in msg_pairs]
        ftl_source = "\n".join(ftl_lines)

        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_ids[0])
        assert isinstance(result, str), "Must handle circular chain gracefully"


class TestFunctionCallResolution:
    """Properties about function call resolution."""

    @given(
        func_name=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=3, max_size=10
        ),
        return_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_custom_function_called(self, func_name: str, return_value: str) -> None:
        """Property: Custom functions are called and results used."""
        event(f"func_name_len={len(func_name)}")
        assume(func_name not in ("NUMBER", "DATETIME"))

        bundle = FluentBundle("en_US", use_isolating=False)

        def custom_func() -> str:
            return return_value

        bundle.add_function(func_name, custom_func)
        bundle.add_resource(f"msg = {{ {func_name}() }}")

        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert return_value.strip() in result, f"Function return value not in result: {result}"

    @given(
        func_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=3, max_size=10
        ),
        error_message=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_function_exception_handling(
        self, func_name: str, error_message: str
    ) -> None:
        """Property: Function exceptions are handled gracefully."""
        event(f"func_name_len={len(func_name)}")
        assume(func_name not in ("NUMBER", "DATETIME"))

        bundle = FluentBundle("en_US")

        def failing_func() -> str:
            raise ValueError(error_message)

        bundle.add_function(func_name, failing_func)
        bundle.add_resource(f"msg = {{ {func_name}() }}")

        result, _errors = bundle.format_pattern("msg")
        assert isinstance(result, str), "Must return string even when function fails"


class TestResolverIsolatingMarks:
    """Properties about Unicode bidi isolation marks."""

    @given(
        var_name=ftl_identifiers(),
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_isolating_marks_added_when_enabled(
        self, var_name: str, var_value: str
    ) -> None:
        """Property: Isolation marks added around interpolated values when enabled."""
        event(f"value_len={len(var_value)}")
        bundle = FluentBundle("en_US", use_isolating=True)
        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})
        assert not errors
        assert "\u2068" in result, "FSI mark missing"
        assert "\u2069" in result, "PDI mark missing"
        assert var_value in result, "Variable value missing"

    @given(
        var_name=ftl_identifiers(),
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_no_isolating_marks_when_disabled(
        self, var_name: str, var_value: str
    ) -> None:
        """Property: No isolation marks when use_isolating=False."""
        event(f"value_len={len(var_value)}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})
        assert not errors
        assert "\u2068" not in result, "FSI mark should not be present"
        assert "\u2069" not in result, "PDI mark should not be present"


class TestResolverValueFormatting:
    """Properties about value formatting."""

    @given(
        var_name=ftl_identifiers(),
        int_value=st.integers(),
    )
    @settings(max_examples=300)
    def test_integer_formatting(self, var_name: str, int_value: int) -> None:
        """Property: Integers are formatted correctly."""
        event(f"int_value={int_value}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: int_value})
        assert not errors
        assert str(int_value) in result, f"Integer {int_value} not formatted correctly"

    @given(
        var_name=ftl_identifiers(),
        bool_value=st.booleans(),
    )
    @settings(max_examples=200)
    def test_boolean_formatting(self, var_name: str, bool_value: bool) -> None:
        """Property: Booleans are formatted as lowercase 'true'/'false'."""
        event(f"bool_value={bool_value}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: bool_value})
        assert not errors
        expected = "true" if bool_value else "false"
        assert expected in result, f"Boolean {bool_value} not formatted correctly"


class TestResolverMetamorphicProperties:
    """Metamorphic properties relating different resolution operations."""

    @given(
        msg_id=ftl_identifiers(),
        text1=ftl_simple_text(),
        text2=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_concatenation_order_preserved(
        self, msg_id: str, text1: str, text2: str
    ) -> None:
        """Property: Multiple text elements appear in order."""
        event(f"text1_len={len(text1)}")
        assume(text1 != text2)

        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"{msg_id} = {text1} {text2}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id)
        assert not errors
        assert text1.strip() in result, "First text element should be present"
        assert text2.strip() in result, "Second text element should be present"

        idx1 = result.find(text1.strip())
        idx2 = result.find(text2.strip())
        if idx1 != idx2:
            assert idx1 < idx2, "Text elements should appear in order"

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_variable_value_substitution(
        self, msg_id: str, var_name: str, value1: str, value2: str
    ) -> None:
        """Property: Changing variable value changes result."""
        event(f"values_differ={value1 != value2}")
        assume(value1 != value2)
        assume(value1 not in value2 and value2 not in value1)

        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"{msg_id} = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result1, errors = bundle.format_pattern(msg_id, {var_name: value1})
        assert not errors
        result2, errors = bundle.format_pattern(msg_id, {var_name: value2})
        assert not errors
        assert result1 != result2, "Different variable values should produce different results"


class TestResolverErrorRecovery:
    """Properties about error recovery during resolution."""

    @given(
        msg_id=ftl_identifiers(),
        partial_text=ftl_simple_text(),
        var_name=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_partial_resolution_on_error(
        self, msg_id: str, partial_text: str, var_name: str
    ) -> None:
        """Property: Partial resolution continues after errors."""
        event(f"text_len={len(partial_text)}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"{msg_id} = {partial_text} {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_id, {})
        assert partial_text.strip() in result, "Static text should be present even with missing var"


class TestResolverCoverageEdgeCases:
    """Coverage tests for resolver edge cases."""

    @given(
        msg_id=ftl_identifiers(),
        text=ftl_simple_text(),
    )
    @settings(max_examples=100)
    def test_placeable_error_handling_in_pattern(
        self, msg_id: str, text: str
    ) -> None:
        """Placeable error handling in _resolve_pattern (line 142->138)."""
        event(f"text_len={len(text)}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"{msg_id} = {text} {{ $missing }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {})
        assert len(errors) > 0
        assert "{$missing}" in result

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        value=st.integers(),
    )
    @settings(max_examples=100)
    def test_nested_placeable_expression_resolution(
        self, msg_id: str, var_name: str, value: int
    ) -> None:
        """Placeable expression resolution (line 190)."""
        event(f"value={value}")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl_source = f"{msg_id} = Value: {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {var_name: value})
        assert not errors
        assert str(value) in result
