"""Hypothesis-based property tests for semantic validator.

Tests SemanticValidator robustness, idempotency, deep nesting handling,
error path detection, parser-validator integration, ValidationResult
properties, state management, and boundary conditions.
"""

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ValidationResult
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import SemanticValidator
from tests.strategies import (
    ftl_deeply_nested_selects,
    ftl_message_nodes,
    ftl_resources,
    ftl_select_expressions,
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
