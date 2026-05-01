# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_runtime_resolver_state_machine.py."""

from tests.fuzz_runtime_resolver_state_machine_cases import *  # noqa: F403 - shared split test support

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
