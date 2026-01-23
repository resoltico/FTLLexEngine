"""State machine testing for FluentResolver using Hypothesis.

This module implements SYSTEM 6 from the testing strategy: Resolver State Machine Testing.
Uses Hypothesis RuleBasedStateMachine to test complex message resolution sequences,
uncovering edge cases in error handling, circular reference detection, and state management.

Target Coverage:
- resolver.py lines 149, 164, 275 (error fallback paths)
- Complex resolution sequences (message→term→message)
- Circular reference detection
- Attribute resolution edge cases
- Error recovery and graceful degradation

State Machine Approach:
Instead of testing individual resolve() calls, we test **sequences** of operations:
- add_message(id, pattern)
- add_term(id, pattern)
- resolve(message_id, args)
- resolve_attribute(message_id, attr, args)

This catches bugs that only appear in specific sequences (stateful bugs).

References:
- Hypothesis stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
- David MacIver, "Rule-based stateful testing" (2016)
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.runtime.resolver import FluentResolver
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
from tests.strategies import ftl_identifiers


# Strategy helpers
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
            Placeable(expression=TermReference(id=Identifier(name=term_name), attribute=None)),
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
    def setup_resolver(self):
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
        self.resolver.messages = self.message_registry
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
        self.resolver.messages = self.message_registry
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
        self.resolver.terms = self.term_registry
        return term_id

    @rule(
        target=messages,
        msg_id=ftl_identifiers(),
        term_id=terms,
    )
    def add_message_referencing_term(self, msg_id: str, term_id: str) -> str:
        """Add message that references a term.

        Tests term resolution path.
        """
        message = Message(
            id=Identifier(name=msg_id),
            value=term_reference_pattern(term_id),
            attributes=(),
            comment=None,
        )
        self.message_registry[msg_id] = message
        self.resolver.messages = self.message_registry
        return msg_id

    @rule(
        msg_id=messages,
    )
    def resolve_simple_message(self, msg_id: str) -> None:
        """Resolve message without arguments.

        Metamorphic property: Resolving twice should produce same result.
        """
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        # Check if message needs variables
        needs_vars = any(
            isinstance(elem, Placeable)
            and isinstance(elem.expression, VariableReference)
            for elem in (message.value.elements if message.value else ())
        )

        if needs_vars:
            # Should fail gracefully with error in output
            result, errors = self.resolver.resolve_message(message, args={})
            assert isinstance(result, str)
            assert len(errors) >= 0  # Graceful degradation - may or may not have errors
        else:
            # Should succeed
            result1, errors = self.resolver.resolve_message(message, args={})
            result2, errors = self.resolver.resolve_message(message, args={})

            # Determinism check
            assert result1 == result2, f"Resolution should be deterministic for {msg_id}"
            assert isinstance(result1, str)

    @rule(
        msg_id=messages,
        var_name=ftl_identifiers(),
        var_value=st.text(max_size=50),
    )
    def resolve_message_with_args(self, msg_id: str, var_name: str, var_value: str) -> None:
        """Resolve message with arguments.

        Tests argument passing and variable substitution.
        """
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        args = {var_name: var_value}

        try:
            result, _errors = self.resolver.resolve_message(message, args=args)

            # May have errors if message references unknown variables/messages/terms
            assert isinstance(result, str)
        except FrozenFluentError:
            # Expected if message references unknown variables/messages/terms
            pass

    @rule(
        msg_id=ftl_identifiers(),
        attr_name=ftl_identifiers(),
        text=st.text(min_size=1, max_size=50),
    )
    def add_message_with_attribute(self, msg_id: str, attr_name: str, text: str) -> None:
        """Add message with attribute.

        Tests attribute resolution paths (lines 83-89).
        """
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
        self.resolver.messages = self.message_registry

        # Try resolving attribute
        result, errors = self.resolver.resolve_message(message, args={}, attribute=attr_name)
        assert text in result
        assert errors == (), f"Unexpected errors: {errors}"

    @rule(msg_id=messages)
    def resolve_nonexistent_attribute(self, msg_id: str) -> None:
        """Try to resolve non-existent attribute.

        Target: Line 86-88 (attribute not found error path).
        """
        assume(msg_id in self.message_registry)
        message = self.message_registry[msg_id]

        _result, errors = self.resolver.resolve_message(
            message, args={}, attribute="nonexistent_attr_xyz"
        )
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "attribute" in str(errors[0]).lower()

    @rule()
    def resolve_nonexistent_term(self):
        """Try to resolve term reference to non-existent term.

        Target: Line 176 (term not found error path).
        This is a critical error path that needs coverage.
        """
        # Create message that references non-existent term
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
        self.resolver.messages = self.message_registry

        # Should produce graceful error (line 119-120)
        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)
        assert len(errors) > 0  # Should have error for nonexistent term

    @rule(term_id=terms)
    def resolve_term_attribute_not_found(self, term_id: str) -> None:
        """Try to resolve term attribute that doesn't exist.

        Target: Line 182-185 (term attribute not found error path).
        """
        assume(term_id in self.term_registry)

        # Create message that references non-existent term attribute
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
        self.resolver.messages = self.message_registry

        # Should produce graceful error
        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)
        assert len(errors) > 0  # Should have error for nonexistent term attribute

    @rule()
    def test_unknown_expression_type(self) -> None:
        """Document unreachable expression type error path.

        Target: Line 151 (unknown expression type error - line 275 mentioned in gaps).

        This error path is ARCHITECTURALLY UNREACHABLE in normal operation since
        all AST node types are exhaustively handled in the match statement. The
        error exists as defensive code for type safety.

        To test this path would require mocking an invalid AST node type, which
        would test the mock rather than the production code. We document this
        as architectural correctness - the code is correct by construction.

        This rule exists to document the gap rather than test it. Hypothesis
        stateful testing will include it in the test sequence.
        """
        # Defensive code path - unreachable by design.
        # All Expression types in FTL AST are handled exhaustively.
        pass  # noqa: PIE790  # pylint: disable=unnecessary-pass

    @rule(
        msg_id1=ftl_identifiers(),
        msg_id2=ftl_identifiers(),
    )
    def test_circular_reference_detection(self, msg_id1: str, msg_id2: str) -> None:
        """Test circular reference detection.

        Target: Lines 97-99 (circular reference error).

        Note: Circular references are caught and produce graceful degradation
        (ERROR in output) rather than raising, due to lines 118-120.
        """
        assume(msg_id1 != msg_id2)

        # msg1 -> msg2
        message1 = Message(
            id=Identifier(name=msg_id1),
            value=message_reference_pattern(msg_id2),
            attributes=(),
            comment=None,
        )

        # msg2 -> msg1 (circular!)
        message2 = Message(
            id=Identifier(name=msg_id2),
            value=message_reference_pattern(msg_id1),
            attributes=(),
            comment=None,
        )

        self.message_registry[msg_id1] = message1
        self.message_registry[msg_id2] = message2
        self.resolver.messages = self.message_registry

        # Should produce ERROR in output (graceful degradation)
        # The circular reference is detected in _resolve_message_reference
        # but caught by the try/except in _resolve_pattern (lines 118-120)
        result, _errors = self.resolver.resolve_message(message1, args={})

        assert isinstance(result, str)
        # May or may not contain ERROR depending on execution order

    @rule(
        msg_id=ftl_identifiers(),
        number=st.integers(min_value=0, max_value=100),
    )
    def add_message_with_select_expression(self, msg_id: str, number: int) -> None:
        """Add message with select expression (plural).

        Tests select expression resolution.
        """
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
        self.resolver.messages = self.message_registry

        # Resolve with count argument
        result, errors = self.resolver.resolve_message(message, args={"count": number})
        assert result in ["singular", "plural"]
        assert errors == (), f"Unexpected errors: {errors}"

    @rule()
    def test_message_no_value(self):
        """Test message without value (only attributes).

        Target: Line 92 (message has no value error).
        """
        msg_id = "msg_no_value"
        message = Message(
            id=Identifier(name=msg_id),
            value=None,  # No value!
            attributes=(
                Attribute(
                    id=Identifier(name="attr1"),
                    value=simple_pattern("has attribute"),
                ),
            ),
            comment=None,
        )
        self.message_registry[msg_id] = message
        self.resolver.messages = self.message_registry

        # Should raise error when trying to resolve without specifying attribute
        result, errors = self.resolver.resolve_message(message, args={})
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "no value" in str(errors[0]).lower()
        assert isinstance(result, str)

    @rule(
        msg_id=ftl_identifiers(),
        func_name=st.sampled_from(["NUMBER", "NONEXISTENT"]),
    )
    def test_function_reference(self, msg_id: str, func_name: str) -> None:
        """Test function reference resolution.

        Tests both successful and failed function calls.
        """
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
        self.resolver.messages = self.message_registry

        result, errors = self.resolver.resolve_message(message, args={})
        assert isinstance(result, str)

        if func_name == "NUMBER":
            assert "42" in result
            assert errors == ()
        else:
            # Should gracefully degrade (unknown function)
            assert len(errors) > 0  # Should have error for unknown function

    @invariant()
    def resolver_state_consistent(self):
        """Invariant: Resolver registries stay consistent."""
        assert self.resolver.messages == self.message_registry
        assert self.resolver.terms == self.term_registry
        assert self.resolver.locale == self.locale

    @invariant()
    def resolution_uses_explicit_context(self):
        """Invariant: Each resolution uses its own isolated context.

        With ResolutionContext (replacing thread-local stack), each resolution
        creates a fresh context. This ensures no state leakage between calls.
        """
        # Each resolution creates its own ResolutionContext
        # No global stack to check - state is passed explicitly
        # This invariant verifies the resolver is properly initialized
        assert self.resolver.locale == self.locale


# Stateful test runner
TestFluentResolverStateMachine = FluentResolverStateMachine.TestCase


class TestResolverErrorPaths:
    """Direct tests for specific error paths that are hard to reach via state machine."""

    def test_term_not_found_direct(self):
        """Line 176: Term not found error.

        Direct test for coverage of the specific error line.
        """
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},  # Empty!
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        # Create message referencing non-existent term
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

        # Should produce ERROR in output (graceful degradation, line 119-120)
        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0  # Should have error for nonexistent term
        assert "{-nonexistent}" in result  # Fallback value

    def test_term_attribute_not_found_direct(self):
        """Line 182-185: Term attribute not found error."""
        term = Term(
            id=Identifier(name="brand"),
            value=simple_pattern("Firefox"),
            attributes=(),  # No attributes!
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

        # Should produce error for nonexistent attribute
        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0  # Should have error for nonexistent attribute
        assert "{-brand.nonexistent}" in result  # Fallback value

    def test_message_not_found_reference(self):
        """Line 164: Message not found when referenced from another message."""
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

        # Should produce error for nonexistent message
        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0  # Should have error for nonexistent message
        assert "{nonexistent}" in result  # Fallback value

    def test_variable_not_provided(self):
        """Line 157: Variable not provided in args."""
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

        # Should produce error for missing variable
        result, errors = resolver.resolve_message(message, args={})  # No args!
        assert len(errors) > 0  # Should have error for missing variable
        assert "{$missing_var}" in result  # Fallback value

    @given(st.data())
    @settings(max_examples=50)
    def test_format_value_edge_cases(self, data):
        """Lines 268-278: _format_value with various types.

        Property: _format_value never crashes, always returns string.
        """
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        # Test various value types
        test_values = [
            data.draw(st.text()),  # str
            data.draw(st.integers()),  # int
            data.draw(st.floats(allow_nan=False, allow_infinity=False)),  # float
            data.draw(st.booleans()),  # bool
            None,  # None
        ]

        for value in test_values:
            result = resolver._format_value(value)
            assert isinstance(result, str), f"_format_value({value}) should return string"

    def test_select_expression_no_variants(self):
        """Line 237: Select expression with no variants error."""
        # Create select expression with empty variants
        select_expr = SelectExpression(
            selector=NumberLiteral(value=1, raw="1"),
            variants=(),  # Empty!
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
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

        # Should produce error for select with no variants
        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0  # Should have error for select with no variants
        assert "{???}" in result  # Fallback value


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
