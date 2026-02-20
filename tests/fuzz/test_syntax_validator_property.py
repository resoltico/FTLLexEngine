"""Fuzz tests for syntax.validator: SemanticValidator and validate_resource() intensive."""

from __future__ import annotations

import pytest
from hypothesis import event, given

from ftllexengine.syntax.ast import Resource
from ftllexengine.syntax.validator import SemanticValidator
from tests.strategies.validation import (
    semantic_validation_resources,
    validation_resource_sources,
)

pytestmark = pytest.mark.fuzz


@pytest.mark.fuzz
class TestSemanticValidatorFuzz:
    """Fuzz tests for SemanticValidator using intensive AST generation.

    These tests are skipped in normal CI and run only with HypoFuzz or
    explicit -m fuzz invocation.

    FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
    """

    pytestmark = pytest.mark.skip(
        reason="FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz"
    )

    @given(resource=semantic_validation_resources())
    def test_fuzz_semantic_validator_all_variants(
        self, resource: Resource
    ) -> None:
        """FUZZ: Exhaustive SemanticValidator testing across all AST variants."""
        validator = SemanticValidator()
        result = validator.validate(resource)
        event(f"outcome_annotations={len(result.annotations)}")
        event(f"outcome_is_valid={result.is_valid}")
        assert result.annotations is not None

    @given(source=validation_resource_sources())
    def test_fuzz_validate_resource_all_scenarios(self, source: str) -> None:
        """FUZZ: Exhaustive validate_resource() testing across all source scenarios."""
        from ftllexengine.validation import validate_resource  # noqa: PLC0415

        result = validate_resource(source)
        event(f"outcome_errors={len(result.errors)}")
        event(f"outcome_warnings={len(result.warnings)}")
        assert result is not None
