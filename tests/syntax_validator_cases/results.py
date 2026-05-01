# mypy: ignore-errors
from tests.syntax_validator_cases import (
    _VALIDATION_MESSAGES,
    Annotation,
    CallArguments,
    Decimal,
    DiagnosticCode,
    FluentParserV1,
    FunctionReference,
    Identifier,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    SemanticValidator,
    Span,
    TextElement,
    ValidationResult,
    VariableReference,
    Variant,
    pytest,
    validate,
)


class TestSelectExpressionValidation:
    """Test select expression validation."""

    def test_select_with_valid_default_variant(self) -> None:
        """Select expression with exactly one default variant validates."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [one] One item
    *[other] Many items
}
""")
        result = validate(resource)
        assert result.is_valid

    def test_select_without_variants_constructor_validation(self) -> None:
        """SelectExpression without variants raises ValueError at construction.

        Tests AST __post_init__ validation that enforces at least one variant.
        Tests assumption that validator can rely on this invariant.
        """
        with pytest.raises(ValueError, match="at least one variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="count")),
                variants=(),
            )

    def test_select_without_variants_validator_defensive_check(self) -> None:
        """Validator catches empty-variants SelectExpression constructed via object.__new__.

        SelectExpression.__post_init__ enforces non-empty variants at construction.
        The validator's check is intentional defense-in-depth for ASTs that bypass
        __post_init__ (e.g., via object.__new__ + object.__setattr__).
        """
        # Create SelectExpression bypassing __post_init__ validation
        select = object.__new__(SelectExpression)
        object.__setattr__(select, "selector", VariableReference(id=Identifier(name="x")))
        object.__setattr__(select, "variants", ())  # Invalid per spec
        object.__setattr__(select, "span", None)

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Validator should catch missing variants
        assert not result.is_valid
        errors = [a for a in result.annotations if "NO_VARIANTS" in a.code]
        assert len(errors) > 0

    def test_select_with_multiple_defaults_constructor_validation(self) -> None:
        """SelectExpression with multiple defaults raises ValueError.

        Tests AST __post_init__ validation.
        """
        variants = (
            Variant(
                key=Identifier(name="one"),
                value=Pattern(elements=(TextElement(value="One"),)),
                default=True,  # First default
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value="Other"),)),
                default=True,  # Second default - invalid!
            ),
        )
        with pytest.raises(ValueError, match="exactly one default variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="count")),
                variants=variants,
            )

    def test_select_with_zero_defaults_validator_defensive_check(self) -> None:
        """Validator catches zero-default SelectExpression constructed via object.__new__.

        SelectExpression.__post_init__ enforces exactly one default at construction.
        The validator's check is intentional defense-in-depth for ASTs that bypass
        __post_init__ (e.g., via object.__new__ + object.__setattr__).
        """
        # Create SelectExpression with zero defaults (bypassing __post_init__)
        variant = object.__new__(Variant)
        object.__setattr__(variant, "key", Identifier(name="one"))
        object.__setattr__(variant, "value", Pattern(elements=(TextElement(value="One"),)))
        object.__setattr__(variant, "default", False)  # No default!
        object.__setattr__(variant, "span", None)

        select = object.__new__(SelectExpression)
        object.__setattr__(select, "selector", VariableReference(id=Identifier(name="x")))
        object.__setattr__(select, "variants", (variant,))
        object.__setattr__(select, "span", None)

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Validator should catch default count != 1
        assert not result.is_valid
        errors = [a for a in result.annotations if "NO_DEFAULT" in a.code]
        assert len(errors) > 0

    def test_select_with_duplicate_variant_keys_invalid(self) -> None:
        """Select expression with duplicate variant keys is invalid.

        Tests line 418 (duplicate variant key detection).
        """
        # Manually construct select with duplicate keys
        variants = (
            Variant(
                key=Identifier(name="one"),
                value=Pattern(elements=(TextElement(value="First one"),)),
                default=False,
            ),
            Variant(
                key=Identifier(name="one"),  # Duplicate!
                value=Pattern(elements=(TextElement(value="Second one"),)),
                default=False,
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value="Other"),)),
                default=True,
            ),
        )
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=variants,
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should detect duplicate variant key
        assert not result.is_valid
        errors = [
            a
            for a in result.annotations
            if "DUPLICATE" in a.code or "duplicate" in a.message.lower()
        ]
        assert len(errors) > 0

    def test_select_with_numeric_variant_keys(self) -> None:
        """Select expression with numeric variant keys validates."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [0] Zero
    [1] One
    *[other] Many
}
""")
        result = validate(resource)
        assert result.is_valid

    def test_select_with_duplicate_numeric_keys_different_forms(self) -> None:
        """Numeric variant keys 1 and 1.0 are duplicates.

        Tests Decimal normalization in _variant_key_to_string.
        """
        # Manually construct select with 1 and 1.0 (should be duplicates)
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="One"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=Decimal("1.0"), raw="1.0"),  # Duplicate!
                value=Pattern(elements=(TextElement(value="One point zero"),)),
                default=False,
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value="Other"),)),
                default=True,
            ),
        )
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=variants,
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should detect duplicate (1 and 1.0 are same value)
        assert not result.is_valid

    def test_select_nested_in_variant(self) -> None:
        """Nested select expressions validate recursively."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    [one] { $y ->
        [a] One-A
        *[b] One-B
    }
    *[other] Other
}
""")
        result = validate(resource)
        assert result.is_valid


# ============================================================================
# VARIANT KEY NORMALIZATION TESTS
# ============================================================================


class TestVariantKeyNormalization:
    """Test variant key normalization and Decimal handling."""

    def test_decimal_normalization_for_numeric_keys(self) -> None:
        """Numeric keys are normalized using Decimal for comparison.

        100 (int, raw="100") and 1E+2 (Decimal, raw="1E2") are the same numeric
        value after Decimal normalization; the validator must detect them as
        duplicate variant keys.
        """
        variants = (
            Variant(
                key=NumberLiteral(value=100, raw="100"),
                value=Pattern(elements=(TextElement(value="Hundred"),)),
                default=False,
            ),
            Variant(
                # Decimal("1E2") == Decimal("100") after normalization.
                # raw="1E2" is a valid Decimal literal; value must be Decimal, not int,
                # because int("1E2") fails. Both normalize to format("f") = "100".
                key=NumberLiteral(value=Decimal("1E2"), raw="1E2"),
                value=Pattern(elements=(TextElement(value="Also hundred"),)),
                default=False,
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value="Other"),)),
                default=True,
            ),
        )
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=variants,
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should detect as duplicates after normalization
        assert not result.is_valid

    def test_number_literal_rejects_invalid_raw(self) -> None:
        """NumberLiteral.__post_init__ rejects raw strings that do not parse as numbers.

        The validator's former fallback (returning key.raw on Decimal conversion failure)
        is now unreachable because NumberLiteral enforces the raw/value invariant at
        construction time.
        """
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=Decimal(0), raw="not-a-number")

    def test_number_literal_rejects_non_finite_decimal(self) -> None:
        """NumberLiteral.__post_init__ rejects non-finite Decimal values.

        Infinity and NaN are not valid FTL number literal values.
        The validator's former exception handling for format(Infinity, 'f') is now
        unreachable because NumberLiteral rejects non-finite Decimals at construction.
        """
        with pytest.raises(ValueError, match="not a finite number"):
            NumberLiteral(value=Decimal("Infinity"), raw="Infinity")


# ============================================================================
# VALIDATION RESULT TESTS
# ============================================================================


class TestValidationResultFactory:
    """Test ValidationResult factory methods."""

    def test_validation_result_valid_factory(self) -> None:
        """ValidationResult.valid() creates valid result."""
        result = ValidationResult.valid()
        assert result.is_valid is True
        assert len(result.annotations) == 0

    def test_validation_result_invalid_factory(self) -> None:
        """ValidationResult.invalid() creates invalid result."""
        annotation = Annotation(
            code="E0001",
            message="Test error",
            span=Span(start=0, end=1),
        )
        result = ValidationResult.invalid(annotations=(annotation,))
        assert result.is_valid is False
        assert len(result.annotations) == 1

    def test_validation_result_from_annotations_empty(self) -> None:
        """ValidationResult.from_annotations() with empty tuple is valid."""
        result = ValidationResult.from_annotations(())
        assert result.is_valid is True
        assert len(result.annotations) == 0

    def test_validation_result_from_annotations_with_errors(self) -> None:
        """ValidationResult.from_annotations() with errors is invalid."""
        annotations = (
            Annotation(code="E0001", message="Error 1", span=Span(start=0, end=1)),
            Annotation(code="E0002", message="Error 2", span=Span(start=2, end=3)),
        )
        result = ValidationResult.from_annotations(annotations)
        assert not result.is_valid
        assert len(result.annotations) == 2


class TestValidationResultProperties:
    """Test ValidationResult properties."""

    def test_annotations_are_immutable_tuples(self) -> None:
        """Annotations are stored as tuples (immutable)."""
        annotation = Annotation(
            code="E0001",
            message="Error",
            span=Span(start=0, end=1),
        )
        result = ValidationResult.invalid(annotations=(annotation,))
        assert isinstance(result.annotations, tuple)

    def test_is_valid_true_means_no_errors(self) -> None:
        """is_valid=True implies no error-level annotations."""
        result = ValidationResult.valid()
        assert result.is_valid is True
        assert len(result.annotations) == 0


# ============================================================================
# ERROR MESSAGE HANDLING TESTS
# ============================================================================


class TestErrorMessageHandling:
    """Test error message generation and diagnostic codes."""

    def test_validation_messages_dict_exists(self) -> None:
        """_VALIDATION_MESSAGES dict contains error message templates."""
        assert isinstance(_VALIDATION_MESSAGES, dict)
        assert len(_VALIDATION_MESSAGES) > 0

    def test_diagnostic_codes_for_validation_exist(self) -> None:
        """Validation-related DiagnosticCodes are defined."""
        expected_codes = [
            DiagnosticCode.VALIDATION_TERM_NO_VALUE,
            DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT,
            DiagnosticCode.VALIDATION_SELECT_NO_VARIANTS,
            DiagnosticCode.VALIDATION_VARIANT_DUPLICATE,
            DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE,
        ]
        for code in expected_codes:
            assert isinstance(code, DiagnosticCode)
            assert code.value >= 5000  # Validation codes in 5000+ range

    def test_error_message_fallback_for_unknown_code(self) -> None:
        """Error message uses fallback for unknown diagnostic code.

        Tests line 129->133 in _add_error method.
        """
        # Create an annotation with a code not in _VALIDATION_MESSAGES
        validator = SemanticValidator()
        errors: list[Annotation] = []

        # Use a diagnostic code that won't be in the validation messages dict
        # Call the _add_error method directly (accessing private method for testing)
        validator._add_error(
            errors,
            DiagnosticCode.MESSAGE_NOT_FOUND,  # Not a validation code
            span=Span(start=0, end=1),
        )

        # Should have added an error with fallback message
        assert len(errors) == 1
        assert errors[0].message == "Unknown validation error"


# ============================================================================
# VALIDATOR STATE MANAGEMENT TESTS
# ============================================================================


class TestValidatorStateManagement:
    """Test validator internal state handling."""

    def test_validator_reusable_across_validations(self) -> None:
        """Validator can validate multiple resources without state leakage."""
        parser = FluentParserV1()
        validator = SemanticValidator()

        # First validation
        resource1 = parser.parse("msg1 = Value 1")
        result1 = validator.validate(resource1)
        assert result1.is_valid

        # Second validation should not be affected by first
        resource2 = parser.parse("msg2 = Value 2")
        result2 = validator.validate(resource2)
        assert result2.is_valid

    def test_validator_results_independent(self) -> None:
        """Validating one resource doesn't affect validation of another."""
        parser = FluentParserV1()
        validator = SemanticValidator()

        resource1 = parser.parse("msg1 = Value 1")
        resource2 = parser.parse("msg2 = Value 2")

        result1_first = validator.validate(resource1)
        validator.validate(resource2)  # Validate resource2
        result1_again = validator.validate(resource1)  # Validate resource1 again

        # Results for same resource should be identical
        assert result1_first.is_valid == result1_again.is_valid
        assert len(result1_first.annotations) == len(result1_again.annotations)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestValidatorIntegration:
    """Integration tests combining multiple validation aspects."""

    def test_complex_message_with_all_features(self) -> None:
        """Complex message with multiple features validates correctly."""
        parser = FluentParserV1()
        resource = parser.parse("""
# Comment
greeting = Hello { $name }, you have { $count ->
    [0] no messages
    [1] one message
    *[other] { NUMBER($count) } messages
}!
    .formal = Dear { $name }, you have { NUMBER($count) } message(s).

-brand = Firefox
    .short = FX

status =
    .online = Online now
    .offline = Offline

invalid junk entry
""")
        result = validate(resource)
        # Should handle all entry types and complex patterns
        assert isinstance(result, ValidationResult)

    def test_deeply_nested_structures(self) -> None:
        """Deeply nested select expressions validate without issues."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $a ->
    [1] { $b ->
        [1] { $c ->
            [1] Triple nested
            *[other] C-other
        }
        *[other] B-other
    }
    *[other] A-other
}
""")
        result = validate(resource)
        assert isinstance(result, ValidationResult)

    def test_multiple_entries_with_mixed_validity(self) -> None:
        """Resource with mix of valid and invalid entries."""
        # Construct resource with some invalid entries
        valid_message = Message(
            id=Identifier(name="valid"),
            value=Pattern(elements=(TextElement(value="Valid"),)),
            attributes=(),
        )

        # Invalid: duplicate named args
        invalid_func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt"),
                        value=NumberLiteral(value=1, raw="1"),
                    ),
                    NamedArgument(
                        name=Identifier(name="opt"),  # Duplicate
                        value=NumberLiteral(value=2, raw="2"),
                    ),
                ),
            ),
        )
        invalid_message = Message(
            id=Identifier(name="invalid"),
            value=Pattern(elements=(Placeable(expression=invalid_func),)),
            attributes=(),
        )

        resource = Resource(entries=(valid_message, invalid_message))
        result = validate(resource)

        # Should detect the invalid entry
        assert not result.is_valid
        assert len(result.annotations) > 0


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================


class TestConvenienceFunction:
    """Test the validate() convenience function."""

    def test_validate_function_creates_validator_internally(self) -> None:
        """validate() function is a convenience wrapper."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")

        # Use convenience function
        result = validate(resource)

        assert isinstance(result, ValidationResult)
        assert result.is_valid

    def test_validate_function_same_result_as_validator_class(self) -> None:
        """validate() function produces same result as SemanticValidator."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello World")

        # Use convenience function
        result1 = validate(resource)

        # Use validator class
        validator = SemanticValidator()
        result2 = validator.validate(resource)

        assert result1.is_valid == result2.is_valid
        assert len(result1.annotations) == len(result2.annotations)


# ============================================================================
# SEMANTIC VALIDATION (from test_semantic_validation.py)
# ============================================================================

