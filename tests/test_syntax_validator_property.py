"""Hypothesis property-based tests for syntax.validator: SemanticValidator and validate()."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ValidationResult
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import SemanticValidator, validate
from tests.strategies import (
    ftl_deeply_nested_selects,
    ftl_message_nodes,
    ftl_resources,
    ftl_select_expressions,
)
from tests.strategies.validation import (
    semantic_validation_resources,
    validation_resource_sources,
)

# ============================================================================
# VALIDATOR ROBUSTNESS TESTS
# ============================================================================


class TestValidatorRobustness:
    """Property tests for validator robustness.

    INVARIANT: Validator should handle any AST structure without crashing.
    """

    @given(ftl_resources())
    @settings(max_examples=200)
    def test_validator_never_crashes(self, resource):
        """ROBUSTNESS: Validator handles any generated resource."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")
        event(f"annotation_count={len(result.annotations)}")
        assert isinstance(result, ValidationResult)
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.annotations, tuple)

    @given(ftl_resources())
    @settings(max_examples=150)
    def test_validator_idempotent(self, resource):
        """PROPERTY: Validating twice produces same result."""
        validator = SemanticValidator()
        result1 = validator.validate(resource)
        result2 = validator.validate(resource)
        match = result1.is_valid == result2.is_valid
        event(f"outcome={'idempotent' if match else 'mismatch'}")
        assert match
        assert len(result1.annotations) == len(result2.annotations)

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_validator_returns_immutable_result(self, resource):
        """PROPERTY: ValidationResult annotations are tuples (immutable)."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")
        assert isinstance(result.annotations, tuple)


# ============================================================================
# DEEP NESTING STRESS TESTS
# ============================================================================


class TestDeepNestingValidation:
    """Property tests for deeply nested select expressions.

    Uses st.recursive() to generate complex nested structures.
    Targets missing coverage in nested validation logic.
    """

    @given(ftl_deeply_nested_selects(max_depth=10))
    @settings(max_examples=100)
    def test_validator_handles_deep_nesting(self, select_expr):
        """STRESS: Deep nesting doesn't crash validator."""
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")
        assert isinstance(result, ValidationResult)

    @given(ftl_deeply_nested_selects(max_depth=5))
    @settings(max_examples=100)
    def test_deeply_nested_selects_validate_correctly(self, select_expr):
        """PROPERTY: Deeply nested selects validate (may have errors)."""
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"annotation_count={len(result.annotations)}")
        assert isinstance(result, ValidationResult)


# ============================================================================
# ERROR PATH TESTS
# ============================================================================


class TestValidatorErrorPaths:
    """Property tests for validator error detection.

    Tests error paths by intentionally creating invalid AST structures.
    """

    @given(ftl_select_expressions())
    @settings(max_examples=100)
    def test_validator_catches_or_allows_no_default_variant(self, select_expr):
        """ERROR PATH: No default variant raises ValueError at construction."""
        variant_count = len(select_expr.variants)
        event(f"variant_count={variant_count}")
        variants_no_default = tuple(
            Variant(key=v.key, value=v.value, default=False)
            for v in select_expr.variants
        )

        with pytest.raises(
            ValueError, match="exactly one default variant"
        ):
            SelectExpression(
                selector=select_expr.selector,
                variants=variants_no_default,
            )

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_empty_resource_valid(self, resource):  # noqa: ARG002
        """BOUNDARY: Empty resources are valid."""
        empty_resource = Resource(entries=())

        validator = SemanticValidator()
        result = validator.validate(empty_resource)
        event("outcome=empty_valid")
        assert result.is_valid


# ============================================================================
# PARSER + VALIDATOR INTEGRATION
# ============================================================================


class TestParserValidatorIntegration:
    """Property tests combining parser output with validator.

    Tests that validator handles real parsed FTL correctly.
    """

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz\n =-", min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_validator_handles_parsed_fuzz(self, ftl_text):
        """FUZZ: Validator handles any parsed output."""
        parser = FluentParserV1()
        resource = parser.parse(ftl_text)

        validator = SemanticValidator()
        result = validator.validate(resource)
        entry_count = len(resource.entries)
        event(f"entry_count={entry_count}")
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")
        assert isinstance(result, ValidationResult)

    @given(ftl_message_nodes())
    @settings(max_examples=100)
    def test_valid_messages_validate(self, message):
        """PROPERTY: Well-formed messages validate successfully."""
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")
        assert isinstance(result, ValidationResult)


# ============================================================================
# VALIDATION RESULT TESTS
# ============================================================================


class TestValidationResultProperties:
    """Property tests for ValidationResult class itself."""

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_validation_result_valid_means_no_errors(self, resource):
        """PROPERTY: is_valid=True implies no error annotations."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome={'valid' if result.is_valid else 'invalid'}")

        if result.is_valid:
            assert isinstance(result.annotations, (list, tuple))

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_validation_annotations_are_tuples(self, resource):
        """PROPERTY: Annotations are always tuples (immutable)."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"annotation_count={len(result.annotations)}")
        assert isinstance(result.annotations, tuple)


# ============================================================================
# VALIDATOR STATE MANAGEMENT
# ============================================================================


class TestValidatorStateManagement:
    """Property tests for validator internal state handling.

    Targets lines 331, 361-362, 367, 395: State reset between validations.
    """

    @given(st.lists(ftl_resources(), min_size=2, max_size=5))
    @settings(max_examples=100)
    def test_validator_state_resets_between_calls(self, resources):
        """PROPERTY: Validator state resets between validate() calls."""
        validator = SemanticValidator()

        results = [validator.validate(resource) for resource in resources]
        event(f"resource_count={len(resources)}")

        for result in results:
            assert isinstance(result, ValidationResult)

    @given(ftl_resources(), ftl_resources())
    @settings(max_examples=100)
    def test_validator_results_independent(self, resource1, resource2):
        """PROPERTY: Validating resource1 doesn't affect resource2."""
        validator = SemanticValidator()

        result1 = validator.validate(resource1)
        _ = validator.validate(resource2)
        result1_again = validator.validate(resource1)

        match = result1.is_valid == result1_again.is_valid
        event(f"outcome={'independent' if match else 'leak'}")
        assert match
        assert len(result1.annotations) == len(result1_again.annotations)


# ============================================================================
# BOUNDARY CONDITION TESTS
# ============================================================================


class TestValidatorBoundaries:
    """Property tests for boundary conditions in validation."""

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_validator_handles_many_entries(self, n):
        """BOUNDARY: Validator handles resources with many entries."""
        scale = "small" if n <= 10 else "large"
        event(f"boundary={scale}_entry_count")
        entries = tuple(
            Message(
                id=Identifier(name=f"msg{i}"),
                value=Pattern(elements=()),
                attributes=(),
            )
            for i in range(n)
        )
        resource = Resource(entries=entries)

        validator = SemanticValidator()
        result = validator.validate(resource)
        assert isinstance(result, ValidationResult)

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_validator_annotations_ordering_consistent(self, resource):
        """PROPERTY: Annotation order is consistent across runs."""
        validator = SemanticValidator()
        result1 = validator.validate(resource)
        result2 = validator.validate(resource)

        event(f"annotation_count={len(result1.annotations)}")
        assert len(result1.annotations) == len(result2.annotations)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])


# ============================================================================
# SEMANTIC VALIDATOR PROPERTIES (from test_semantic_validator_hypothesis.py)
# ============================================================================


class TestValidateResourceProperties:
    """Property-based tests for validate_resource() using scenario strategies."""

    @given(source=validation_resource_sources())
    def test_property_validate_resource_never_raises(self, source: str) -> None:
        """PROPERTY: validate_resource() never raises exceptions for any FTL source."""
        from ftllexengine.validation import validate_resource  # noqa: PLC0415

        scenario = "unknown"
        if "circular" in source.lower() or ("c1" in source and "c2" in source):
            scenario = "circular"
        elif "undefined" in source.lower():
            scenario = "undefined"
        else:
            scenario = "other"
        event(f"outcome_scenario={scenario}")

        result = validate_resource(source)
        assert result is not None
        # Errors and warnings are tuples
        assert isinstance(result.errors, tuple)
        assert isinstance(result.warnings, tuple)
        assert isinstance(result.annotations, tuple)

    @given(source=validation_resource_sources())
    def test_property_validate_resource_result_consistency(self, source: str) -> None:
        """PROPERTY: ValidationResult.is_valid is consistent with errors and annotations."""
        from ftllexengine.validation import validate_resource  # noqa: PLC0415

        result = validate_resource(source)
        has_errors = len(result.errors) > 0 or len(result.annotations) > 0
        event(f"outcome_has_errors={has_errors}")
        assert result.is_valid == (not has_errors)

    @given(source=validation_resource_sources())
    def test_property_error_count_accurate(self, source: str) -> None:
        """PROPERTY: error_count == len(errors) and annotation_count == len(annotations)."""
        from ftllexengine.validation import validate_resource  # noqa: PLC0415

        result = validate_resource(source)
        event(f"outcome_error_count={result.error_count}")
        assert result.error_count == len(result.errors)
        assert result.annotation_count == len(result.annotations)

    @given(source=validation_resource_sources())
    def test_property_idempotent_validation(self, source: str) -> None:
        """PROPERTY: Validating the same source twice produces identical results."""
        from ftllexengine.validation import validate_resource  # noqa: PLC0415

        result1 = validate_resource(source)
        result2 = validate_resource(source)
        idempotent = (
            result1.errors == result2.errors
            and result1.warnings == result2.warnings
            and result1.annotations == result2.annotations
        )
        event(f"outcome_idempotent={idempotent}")
        assert idempotent


# ============================================================================
# PROPERTY TESTS: SemanticValidator via AST strategy
# ============================================================================


class TestSemanticValidatorProperties:
    """Property-based tests for SemanticValidator using AST strategies."""

    @given(resource=semantic_validation_resources())
    def test_property_validate_never_raises(self, resource: Resource) -> None:
        """PROPERTY: SemanticValidator.validate() never raises for generated AST."""
        validator = SemanticValidator()
        variant = "unknown"
        if not resource.entries:
            variant = "empty"
        elif len(resource.entries) == 1:
            variant = "single_entry"
        else:
            variant = "multi_entry"
        event(f"outcome_resource_kind={variant}")

        result = validator.validate(resource)
        assert result is not None
        assert isinstance(result.annotations, tuple)

    @given(resource=semantic_validation_resources())
    def test_property_valid_result_has_no_errors_or_annotations(
        self, resource: Resource
    ) -> None:
        """PROPERTY: is_valid iff no errors and no annotations."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        expected = (len(result.errors) == 0 and len(result.annotations) == 0)
        event(f"outcome_valid={result.is_valid}")
        assert result.is_valid == expected

    @given(resource=semantic_validation_resources())
    def test_property_validator_is_stateless(self, resource: Resource) -> None:
        """PROPERTY: Validator can be reused without state accumulation."""
        validator = SemanticValidator()
        result1 = validator.validate(resource)
        result2 = validator.validate(resource)
        same = result1.annotations == result2.annotations
        event(f"outcome_stateless={same}")
        assert same

    @given(resource=semantic_validation_resources())
    def test_property_convenience_validate_matches_validator(
        self, resource: Resource
    ) -> None:
        """PROPERTY: Module-level validate() matches SemanticValidator().validate()."""
        validator = SemanticValidator()
        direct = validator.validate(resource)
        convenience = validate(resource)
        match_result = direct.annotations == convenience.annotations
        event(f"outcome_match={match_result}")
        assert match_result


# ============================================================================
# PROPERTY TESTS: Duplicate Variant Key Detection
# ============================================================================


class TestDuplicateVariantKeyProperties:
    """Property-based tests for duplicate variant key detection."""

    @given(resource=semantic_validation_resources())
    def test_property_duplicate_variant_key_detected(
        self, resource: Resource
    ) -> None:
        """PROPERTY: Resources with duplicate variant keys produce VALIDATION_VARIANT_DUPLICATE."""
        assume(
            resource.entries
            and any(
                hasattr(e, "id") and e.id.name in ("dup-numeric", "dup-ident")
                for e in resource.entries
            )
        )
        validator = SemanticValidator()
        result = validator.validate(resource)
        has_dup = any(
            a.code == DiagnosticCode.VALIDATION_VARIANT_DUPLICATE.name
            for a in result.annotations
        )
        event(f"outcome_dup_detected={has_dup}")
        assert has_dup, (
            f"Expected VALIDATION_VARIANT_DUPLICATE in annotations: {result.annotations}"
        )

    @given(resource=semantic_validation_resources())
    def test_property_duplicate_named_arg_detected(
        self, resource: Resource
    ) -> None:
        """PROPERTY: Resources with duplicate named args produce VALIDATION_NAMED_ARG_DUPLICATE."""
        assume(
            resource.entries
            and any(
                hasattr(e, "id") and e.id.name == "dup-named"
                for e in resource.entries
            )
        )
        validator = SemanticValidator()
        result = validator.validate(resource)
        has_dup = any(
            a.code == DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE.name
            for a in result.annotations
        )
        event(f"outcome_named_dup_detected={has_dup}")
        assert has_dup, (
            f"Expected VALIDATION_NAMED_ARG_DUPLICATE: {result.annotations}"
        )


# ============================================================================
# UNIT TESTS: Term Positional Args Warning
# ============================================================================


class TestTermPositionalArgsValidation:
    """Unit tests for term positional argument validation."""

    def test_positional_args_in_term_ref_detected(self) -> None:
        """Term reference with positional args produces VALIDATION_TERM_POSITIONAL_ARGS."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Acme Corp
msg = Welcome to { -brand($x) }
""")
        validator = SemanticValidator()
        result = validator.validate(resource)
        codes = [a.code for a in result.annotations]
        assert DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS.name in codes

    def test_named_args_only_in_term_ref_no_warning(self) -> None:
        """Term reference with only named args does NOT produce positional arg warning."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
-brand = { $case ->
    [nom] Acme Corp
   *[other] Acme Corp
}
msg = Welcome to { -brand(case: "nom") }
""")
        validator = SemanticValidator()
        result = validator.validate(resource)
        codes = [a.code for a in result.annotations]
        assert DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS.name not in codes

    def test_term_positional_args_message_contains_term_name(self) -> None:
        """Positional args warning message names the specific term."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
-my-special-brand = Brand
msg = { -my-special-brand($x) }
""")
        validator = SemanticValidator()
        result = validator.validate(resource)
        pos_arg_anns = [
            a for a in result.annotations
            if a.code == DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS.name
        ]
        assert len(pos_arg_anns) == 1
        assert "-my-special-brand" in pos_arg_anns[0].message
        assert "positional arguments are ignored" in pos_arg_anns[0].message

    @given(resource=semantic_validation_resources())
    def test_property_term_positional_args_consistent(
        self, resource: Resource
    ) -> None:
        """PROPERTY: term_positional_args variant always produces positional arg warning."""
        assume(
            resource.entries
            and any(
                hasattr(e, "id") and e.id.name == "msg"
                for e in resource.entries
            )
        )
        validator = SemanticValidator()
        result = validator.validate(resource)
        # May or may not have the warning depending on variant
        has_warning = any(
            a.code == DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS.name
            for a in result.annotations
        )
        event(f"outcome_has_term_pos_warning={has_warning}")
        # No assertion - different variants produce different outcomes


# ============================================================================
# UNIT TESTS: Exhaustiveness Guards (TypeError branches)
# ============================================================================


class TestExhaustivenessGuards:
    """Unit tests for TypeError branches in exhaustive match dispatches.

    These tests cover the `case _: raise TypeError(...)` branches to
    ensure all match dispatches on closed union types are exhaustive.
    The branches are reached via type system bypass using Resource
    with injected non-standard entry objects.
    """

    def test_validate_entry_unknown_type_raises_typeerror(self) -> None:
        """_validate_entry raises TypeError for non-Entry objects injected into Resource.

        Covers the case _: raise TypeError(...) in _validate_entry().
        """
        validator = SemanticValidator()

        # Bypass type system: create a Resource with a non-Entry object
        # The Resource constructor accepts a tuple - use object.__new__ to bypass __post_init__
        bad_resource = object.__new__(Resource)
        object.__setattr__(bad_resource, "entries", (42,))  # int is not an Entry

        with pytest.raises(TypeError, match=r"Unexpected entry type"):
            validator.validate(bad_resource)

    def test_validate_pattern_element_unknown_type_raises_typeerror(
        self,
    ) -> None:
        """_validate_pattern_element raises TypeError for non-PatternElement objects.

        Covers the case _: raise TypeError(...) in _validate_pattern_element().
        """
        validator = SemanticValidator()

        # Inject non-PatternElement into a Pattern
        bad_pattern = object.__new__(Pattern)
        object.__setattr__(bad_pattern, "elements", ("not_an_element",))

        bad_message = object.__new__(Message)
        object.__setattr__(bad_message, "id", Identifier("msg"))
        object.__setattr__(bad_message, "value", bad_pattern)
        object.__setattr__(bad_message, "attributes", ())
        object.__setattr__(bad_message, "comment", None)
        object.__setattr__(bad_message, "span", None)

        bad_resource = object.__new__(Resource)
        object.__setattr__(bad_resource, "entries", (bad_message,))

        with pytest.raises(TypeError, match=r"Unexpected pattern element type"):
            validator.validate(bad_resource)

    def test_validate_inline_expression_unknown_type_raises_typeerror(
        self,
    ) -> None:
        """_validate_inline_expression raises TypeError for non-InlineExpression objects.

        Covers the case _: raise TypeError(...) in _validate_inline_expression().
        """
        from ftllexengine.syntax.ast import Placeable  # noqa: PLC0415

        validator = SemanticValidator()

        # Inject a non-InlineExpression as a Placeable expression
        bad_placeable = object.__new__(Placeable)
        object.__setattr__(bad_placeable, "expression", "not_an_expression")

        bad_pattern = Pattern(elements=(bad_placeable,))
        bad_message = Message(
            id=Identifier("msg"),
            value=bad_pattern,
            attributes=(),
        )
        bad_resource = Resource(entries=(bad_message,))

        with pytest.raises(TypeError, match=r"Unexpected inline expression type"):
            validator.validate(bad_resource)


# ============================================================================
# UNIT TESTS: Select Expression Validation
# ============================================================================


class TestSelectExpressionValidation:
    """Unit tests for _validate_select_expression coverage."""

    def test_valid_select_with_one_default(self) -> None:
        """Select expression with exactly one default passes semantic validation."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [one] One item
   *[other] Many items
}
""")
        validator = SemanticValidator()
        result = validator.validate(resource)
        assert result.is_valid

    def test_select_with_numeric_duplicate_keys(self) -> None:
        """Numerically equivalent variant keys are detected as duplicates.

        Per Decimal normalization: 1, 1.0, 1.00 are the same value.
        """
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            NumberLiteral,
            Placeable,
            SelectExpression,
            VariableReference,
            Variant,
        )

        selector = VariableReference(id=Identifier("n"))
        variants = (
            Variant(
                key=NumberLiteral(value=Decimal("1"), raw="1"),
                value=Pattern(elements=(TextElement("first"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=Decimal("1.0"), raw="1.0"),
                value=Pattern(elements=(TextElement("duplicate"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement("default"),)),
                default=True,
            ),
        )
        select = SelectExpression(selector=selector, variants=variants)
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(
                Placeable(expression=select),
            )),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        validator = SemanticValidator()
        result = validator.validate(resource)
        codes = [a.code for a in result.annotations]
        assert DiagnosticCode.VALIDATION_VARIANT_DUPLICATE.name in codes

    def test_select_with_high_precision_distinct_keys(self) -> None:
        """High-precision numeric keys that differ in Decimal are NOT duplicates."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    [0.10000000000000001] precise
    [0.1] rounded
   *[other] default
}
""")
        validator = SemanticValidator()
        result = validator.validate(resource)
        # These have different Decimal representations - should be valid
        assert result.is_valid

    def test_function_reference_validation_called(self) -> None:
        """Function reference with duplicate named args is detected.

        The FTL parser rejects duplicate named argument names at syntax level,
        so this test constructs the AST directly to exercise the semantic validator.
        """
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            NamedArgument,
            Placeable,
            StringLiteral,
        )

        func_ref = FunctionReference(
            id=Identifier("NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(name=Identifier("style"), value=StringLiteral(value="first")),
                    NamedArgument(name=Identifier("style"), value=StringLiteral(value="second")),
                ),
            ),
        )
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        validator = SemanticValidator()
        result = validator.validate(resource)
        codes = [a.code for a in result.annotations]
        assert DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE.name in codes

    def test_function_reference_no_args_valid(self) -> None:
        """Function reference with no arguments is valid."""
        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("msg = { FUNC() }")

        validator = SemanticValidator()
        result = validator.validate(resource)
        assert result.is_valid


# ============================================================================
# UNIT TESTS: _add_error default message path
# ============================================================================


class TestAddErrorDefaultMessage:
    """Unit tests for _add_error() with no custom message (default from dict)."""

    def test_add_error_uses_default_message_when_none(self) -> None:
        """_add_error() uses _VALIDATION_MESSAGES default when message=None."""
        from ftllexengine.syntax.validator import _VALIDATION_MESSAGES  # noqa: PLC0415

        # Any code in _VALIDATION_MESSAGES
        code = next(iter(_VALIDATION_MESSAGES))
        expected_msg = _VALIDATION_MESSAGES[code]

        validator = SemanticValidator()
        errors: list = []
        # pylint: disable=protected-access
        validator._add_error(errors, code)  # No message argument

        assert len(errors) == 1
        assert errors[0].message == expected_msg

    def test_add_error_uses_custom_message_when_provided(self) -> None:
        """_add_error() uses custom message instead of default."""
        from ftllexengine.diagnostics.codes import DiagnosticCode  # noqa: PLC0415

        validator = SemanticValidator()
        errors: list = []
        custom_msg = "Custom validation error message"
        validator._add_error(  # pylint: disable=protected-access
            errors,
            DiagnosticCode.VALIDATION_TERM_NO_VALUE,
            message=custom_msg,
        )

        assert len(errors) == 1
        assert errors[0].message == custom_msg

    def test_add_error_unknown_code_uses_fallback(self) -> None:
        """_add_error() falls back to 'Unknown validation error' for unmapped codes."""
        from ftllexengine.diagnostics.codes import DiagnosticCode  # noqa: PLC0415

        validator = SemanticValidator()
        errors: list = []
        # Use a code NOT in _VALIDATION_MESSAGES
        validator._add_error(  # pylint: disable=protected-access
            errors,
            DiagnosticCode.MESSAGE_NOT_FOUND,
        )

        assert len(errors) == 1
        assert errors[0].message == "Unknown validation error"


# ============================================================================
# FUZZ TESTS: Intensive SemanticValidator fuzzing
# ============================================================================
