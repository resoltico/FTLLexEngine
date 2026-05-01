# mypy: ignore-errors
from tests.syntax_validator_cases import (
    Attribute,
    CallArguments,
    Comment,
    CommentType,
    DiagnosticCode,
    FluentBundle,
    FluentParserV1,
    FunctionCallInfo,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    SemanticValidator,
    Term,
    TextElement,
    VariableReference,
    Variant,
    introspect_message,
    pytest,
    validate,
)


class TestTermPositionalArgsWarning:
    """Tests for VAL-TERM-POSITIONAL-ARGS-001 resolution.

    SemanticValidator emits warning when term references include positional
    arguments, which are silently ignored at runtime per Fluent spec.
    """

    def test_term_reference_positional_args_triggers_warning(self) -> None:
        """Term reference with positional args emits validation warning."""
        parser = FluentParserV1()
        ftl_source = """
-brand = Acme Corp
msg = Welcome to { -brand($var) }
"""
        resource = parser.parse(ftl_source)

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should have warning about positional args
        # Annotation.code is a string (enum name), not DiagnosticCode enum
        warning_codes = [a.code for a in result.annotations]
        assert "VALIDATION_TERM_POSITIONAL_ARGS" in warning_codes

    def test_term_reference_named_args_no_warning(self) -> None:
        """Term reference with only named args does NOT emit warning."""
        parser = FluentParserV1()
        ftl_source = """
-brand = { $case ->
    [nominative] Acme Corp
    *[other] Acme Corp
}
msg = Welcome to { -brand(case: "nominative") }
"""
        resource = parser.parse(ftl_source)

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should NOT have warning about positional args
        warning_codes = [a.code for a in result.annotations]
        assert "VALIDATION_TERM_POSITIONAL_ARGS" not in warning_codes

    def test_term_reference_mixed_args_triggers_warning(self) -> None:
        """Term reference with mixed positional and named args emits warning."""
        parser = FluentParserV1()
        ftl_source = """
-brand = Acme Corp
msg = Welcome to { -brand($var, extra: "value") }
"""
        resource = parser.parse(ftl_source)

        validator = SemanticValidator()
        result = validator.validate(resource)

        warning_codes = [a.code for a in result.annotations]
        assert "VALIDATION_TERM_POSITIONAL_ARGS" in warning_codes

    def test_term_reference_no_args_no_warning(self) -> None:
        """Term reference without arguments does NOT emit warning."""
        parser = FluentParserV1()
        ftl_source = """
-brand = Acme Corp
msg = Welcome to { -brand }
"""
        resource = parser.parse(ftl_source)

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Should NOT have warning about positional args
        warning_codes = [a.code for a in result.annotations]
        assert "VALIDATION_TERM_POSITIONAL_ARGS" not in warning_codes

    def test_warning_message_contains_term_name(self) -> None:
        """Warning message identifies the term reference causing the warning."""
        parser = FluentParserV1()
        ftl_source = """
-my_special_term = Test
msg = { -my_special_term($x) }
"""
        resource = parser.parse(ftl_source)

        validator = SemanticValidator()
        result = validator.validate(resource)

        annotations = [
            a
            for a in result.annotations
            if a.code == "VALIDATION_TERM_POSITIONAL_ARGS"
        ]
        assert len(annotations) == 1
        assert "-my_special_term" in annotations[0].message
        assert "positional arguments are ignored" in annotations[0].message


class TestFunctionCallInfoPositionalArgVarsRename:
    """Tests for SEM-INTROSPECTION-DATA-LOSS-001 resolution.

    FunctionCallInfo.positional_args renamed to positional_arg_vars to
    clarify that it contains only variable reference names, not all arguments.
    """

    def test_positional_arg_vars_field_exists(self) -> None:
        """FunctionCallInfo has positional_arg_vars field."""
        info = FunctionCallInfo(
            name="NUMBER",
            positional_arg_vars=("amount", "extra"),
            named_args=frozenset({"minimumFractionDigits"}),
            span=None,
        )
        assert info.positional_arg_vars == ("amount", "extra")

    def test_positional_arg_vars_contains_only_variable_names(self) -> None:
        """positional_arg_vars only contains VariableReference names."""
        parser = FluentParserV1()
        # FTL with function that has mixed positional args (variable and literal)
        ftl_source = 'msg = { NUMBER($var, "literal") }'
        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)
        func = next(iter(result.functions))

        # Only variable reference name should be present, not "literal"
        assert func.positional_arg_vars == ("var",)

    def test_introspect_message_extracts_positional_arg_vars(self) -> None:
        """introspect_message correctly populates positional_arg_vars."""
        bundle = FluentBundle("en")
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")

        info = bundle.introspect_message("price")
        funcs = list(info.functions)
        assert len(funcs) == 1

        func = funcs[0]
        assert func.name == "NUMBER"
        assert "amount" in func.positional_arg_vars
        assert "minimumFractionDigits" in func.named_args

    def test_positional_arg_vars_multiple_variables(self) -> None:
        """positional_arg_vars captures multiple variable references."""
        parser = FluentParserV1()
        ftl_source = "msg = { FUNC($a, $b, $c) }"
        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)
        func = next(iter(result.functions))

        assert set(func.positional_arg_vars) == {"a", "b", "c"}


class TestCrossResourceCycleDetection:
    """Tests for VAL-CROSS-RESOURCE-CYCLES-001 resolution.

    FluentBundle.validate_resource() now detects cycles involving dependencies
    OF existing bundle entries, not just their names.
    """

    def test_simple_cross_resource_cycle_detected(self) -> None:
        """Cycle through dependencies of existing entry is detected.

        Scenario:
        - Resource 1: msg_a = { msg_b }
        - Resource 2: msg_b = { msg_a }

        When validating Resource 2, msg_b references msg_a which is in the bundle.
        Since msg_a's dependencies (msg_b) now complete a cycle, it should be detected.
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Add first resource: msg_a depends on msg_b (not yet defined)
        bundle.add_resource("msg_a = { msg_b }")

        # Now validate second resource that completes the cycle
        result = bundle.validate_resource("msg_b = { msg_a }")

        # Should detect the circular reference
        warning_texts = " ".join(w.message for w in result.warnings)
        assert "Circular" in warning_texts

    def test_term_cross_resource_cycle_detected(self) -> None:
        """Cycle through term dependencies is detected.

        Scenario:
        - Resource 1: -term_a = { -term_b }
        - Resource 2: -term_b = { -term_a }
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Add first resource: term_a depends on term_b
        bundle.add_resource("-term_a = { -term_b }")

        # Validate second resource that completes the cycle
        result = bundle.validate_resource("-term_b = { -term_a }")

        # Should detect the circular reference
        warning_texts = " ".join(w.message for w in result.warnings)
        assert "Circular" in warning_texts

    def test_mixed_message_term_cross_resource_cycle_detected(self) -> None:
        """Cycle involving both messages and terms across resources is detected.

        Scenario:
        - Resource 1: -brand = { greeting }
        - Resource 2: greeting = { -brand }
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Add first resource: term depends on message
        bundle.add_resource("-brand = { greeting }")

        # Validate second resource that completes the cycle
        result = bundle.validate_resource("greeting = { -brand }")

        # Should detect the circular reference
        warning_texts = " ".join(w.message for w in result.warnings)
        assert "Circular" in warning_texts

    def test_no_false_positive_for_valid_cross_resource(self) -> None:
        """Valid cross-resource references don't trigger false positives.

        Scenario:
        - Resource 1: msg_a = Hello
        - Resource 2: msg_b = { msg_a }

        This is a valid dependency chain, not a cycle.
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Add first resource: msg_a has no dependencies
        bundle.add_resource("msg_a = Hello")

        # Validate second resource that references msg_a
        result = bundle.validate_resource("msg_b = { msg_a }")

        # Should NOT have circular reference warnings
        warning_texts = " ".join(w.message for w in result.warnings)
        assert "Circular" not in warning_texts

    def test_transitive_cross_resource_cycle_detected(self) -> None:
        """Transitive cycles across resources are detected.

        Scenario:
        - Resource 1: msg_a = { msg_b }, msg_b = { msg_c }
        - Resource 2: msg_c = { msg_a }
        """
        bundle = FluentBundle("en", use_isolating=False)

        # Add first resource with chain msg_a -> msg_b -> msg_c (incomplete)
        bundle.add_resource("""
msg_a = { msg_b }
msg_b = { msg_c }
""")

        # Validate second resource that completes the cycle
        result = bundle.validate_resource("msg_c = { msg_a }")

        # Should detect the circular reference
        warning_texts = " ".join(w.message for w in result.warnings)
        assert "Circular" in warning_texts

    def test_bundle_deps_tracking_accuracy(self) -> None:
        """Internal _msg_deps and _term_deps are correctly populated."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add resources with various dependencies
        bundle.add_resource("""
-brand = Acme Corp
-slogan = { -brand }
welcome = Hello { -brand }
goodbye = { welcome } - { -slogan }
""")

        # pylint: disable=protected-access
        # Verify _term_deps
        assert "brand" in bundle._term_deps
        assert bundle._term_deps["brand"] == set()

        assert "slogan" in bundle._term_deps
        assert "term:brand" in bundle._term_deps["slogan"]

        # Verify _msg_deps
        assert "welcome" in bundle._msg_deps
        assert "term:brand" in bundle._msg_deps["welcome"]

        assert "goodbye" in bundle._msg_deps
        assert "msg:welcome" in bundle._msg_deps["goodbye"]
        assert "term:slogan" in bundle._msg_deps["goodbye"]
        # pylint: enable=protected-access


# ============================================================================
# VALIDATOR BRANCH COVERAGE
# ============================================================================


class TestValidatorBranchCoverage:
    """Test SemanticValidator branch coverage."""

    def test_validate_junk_entry_passthrough(self) -> None:
        """Junk entry in validation passes through without error."""
        junk = Junk(content="invalid")
        resource = Resource(entries=(junk,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result is not None

    def test_validate_comment_entry_passthrough(self) -> None:
        """Comment entry in validation passes through successfully."""
        comment = Comment(content="This is a comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_validate_message_without_value(self) -> None:
        """Message with value=None and attributes validates without crash."""
        attr = Attribute(
            id=Identifier("hint"),
            value=Pattern(elements=(TextElement("Hint text"),)),
        )
        message = Message(
            id=Identifier("noValue"),
            value=None,
            attributes=(attr,),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result is not None


class TestTermWithoutValueRejected:
    """Term with None value is rejected at construction time by __post_init__."""

    def test_term_without_value_via_manual_ast(self) -> None:
        """Term constructor raises ValueError when value is None."""
        with pytest.raises(ValueError, match="Term must have a value pattern"):
            Term(
                id=Identifier(name="empty-term"),
                value=None,  # type: ignore[arg-type]
                attributes=(),
            )


class TestPlaceableExpressionValidation:
    """Validator processes the expression inside a Placeable."""

    def test_placeable_expression_validation(self) -> None:
        """Validation processes Placeable's inner expression (hits validate_expression path)."""
        ftl = """
message = Text { $variable } more text
"""
        resource = FluentParserV1().parse(ftl)
        result = validate(resource)

        assert result.is_valid


class TestDuplicateNamedArguments:
    """Validator detects duplicate named argument names in function calls."""

    def test_duplicate_named_arguments(self) -> None:
        """Function with duplicate named arg names produces validation annotation."""
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(NumberLiteral(value=42, raw="42"),),
                named=(
                    NamedArgument(
                        name=Identifier(name="minimumFractionDigits"),
                        value=NumberLiteral(value=2, raw="2"),
                    ),
                    NamedArgument(
                        name=Identifier(name="minimumFractionDigits"),  # Duplicate
                        value=NumberLiteral(value=3, raw="3"),
                    ),
                ),
            ),
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None,
            span=(0, 0),  # type: ignore[arg-type]
        )

        resource = Resource(entries=(msg,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert len(result.annotations) > 0 or not result.is_valid


class TestSelectExpressionNoVariants:
    """SelectExpression with zero variants is rejected by __post_init__."""

    def test_select_expression_no_variants(self) -> None:
        """SelectExpression constructor raises ValueError when variants is empty."""
        with pytest.raises(ValueError, match="SelectExpression requires at least one variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="count")),
                variants=(),
            )


class TestNestedPlaceableValidation:
    """Validator processes nested Placeables (Placeable as expression of Placeable)."""

    def test_nested_placeable_validation(self) -> None:
        """Validator traverses nested Placeables without error."""
        inner_placeable = Placeable(
            expression=VariableReference(id=Identifier(name="count"))
        )
        outer_placeable = Placeable(expression=inner_placeable)

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(outer_placeable,)),
            attributes=(),
            comment=None,
            span=(0, 0),  # type: ignore[arg-type]
        )

        resource = Resource(entries=(msg,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid


class TestValidatorBranchCoverageExtended:
    """Extended validator branch coverage tests."""

    def test_validate_term_with_attributes(self) -> None:
        """Validator handles term with attributes without error."""
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
        """Validator processes message with SelectExpression in attribute."""
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


# ============================================================================
# DEFENSE-IN-DEPTH: PLACEABLE AS SELECTOR GUARD (validator.py:421-422)
# ============================================================================


class TestPlaceableAsSelectorDefenseGuard:
    """Validator defense-in-depth: Placeable used as SelectExpression selector.

    The SelectorExpression type alias excludes Placeable at the type level, so
    normal construction cannot produce this state. However, deserialization or
    object.__setattr__ bypass can. The validator re-checks this invariant at
    line 420-422 via a widened ``object`` guard to avoid mypy unreachable
    detection while still catching adversarial ASTs at runtime.

    Covers validator.py:422 (``self._add_error(errors, VALIDATION_PLACEABLE_SELECTOR)``).
    """

    def test_placeable_as_selector_adds_error(self) -> None:
        """Validator adds VALIDATION_PLACEABLE_SELECTOR error when selector is a Placeable."""
        # Build a valid SelectExpression first, then bypass __post_init__ to
        # inject a Placeable as the selector — this is the adversarial path.
        valid_select = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )
        # Bypass __post_init__: inject a Placeable as the selector
        nested_literal = Placeable(
            expression=VariableReference(id=Identifier("nested"))
        )
        object.__setattr__(valid_select, "selector", nested_literal)

        message = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=valid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result is not None
        # _add_error stores Annotation.code as DiagnosticCode.name (str), not enum.
        # Errors from SemanticValidator appear in result.annotations, not result.errors.
        selector_errors = [
            a for a in result.annotations
            if a.code == DiagnosticCode.VALIDATION_PLACEABLE_SELECTOR.name
        ]
        assert len(selector_errors) == 1
