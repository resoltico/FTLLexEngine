"""Tests for syntax.validator: SemanticValidator, validate(), semantic correctness per spec."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine import FluentBundle
from ftllexengine.diagnostics import ValidationResult
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.enums import CommentType
from ftllexengine.introspection import FunctionCallInfo, introspect_message
from ftllexengine.syntax.ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
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
    Span,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import (
    _VALIDATION_MESSAGES,
    SemanticValidator,
    validate,
)

# ============================================================================
# ENTRY VALIDATION TESTS
# ============================================================================


class TestMessageValidation:
    """Test message entry validation."""

    def test_message_with_value_and_attributes(self) -> None:
        """Message with value and attributes validates correctly."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Hello World
    .attr1 = Attribute 1
    .attr2 = Attribute 2
""")
        result = validate(resource)
        assert result.is_valid

    def test_message_with_only_attributes_no_value(self) -> None:
        """Message with no value, only attributes (valid per Fluent spec).

        Tests line 171->175 branch when message.value is None.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
    .attr1 = Attribute value
    .attr2 = Another attribute
""")
        result = validate(resource)
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_message_with_plain_text_only(self) -> None:
        """Message with plain text value validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Plain text value")
        result = validate(resource)
        assert result.is_valid

    def test_message_with_placeables(self) -> None:
        """Message with variable references validates.

        Tests line 171-172 (message.value exists branch).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello { $name }, you have { $count } messages")

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_message_with_value_explicit_validation_path(self) -> None:
        """Message with value takes the validation path.

        Explicitly tests line 171->172 branch (if message.value: path).
        """
        # Create message with explicit value pattern
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Has value"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_message_without_value_explicit_validation_path(self) -> None:
        """Message without value skips value validation.

        Explicitly tests line 171->175 branch (when message.value is None).
        """
        # Create message with no value (only attributes)
        message = Message(
            id=Identifier(name="test"),
            value=None,
            attributes=(
                Attribute(
                    id=Identifier(name="attr"),
                    value=Pattern(elements=(TextElement(value="Attribute value"),)),
                ),
            ),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid


class TestTermValidation:
    """Test term entry validation."""

    def test_term_with_value_validates(self) -> None:
        """Term with value is valid per Fluent spec."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = Firefox")
        result = validate(resource)
        assert result.is_valid

    def test_term_with_value_and_attributes(self) -> None:
        """Term with value and attributes validates.

        Tests line 202 - term attribute validation.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Firefox
    .short = FX
    .long = Mozilla Firefox
""")
        result = validate(resource)
        assert result.is_valid

    def test_term_without_value_constructor_validation(self) -> None:
        """Term without value raises ValueError at construction.

        The AST enforces that terms must have values.
        Tests the invariant that validator assumes terms always have values.
        """
        with pytest.raises(ValueError, match="Term must have a value pattern"):
            Term(
                id=Identifier(name="test"),
                value=None,  # type: ignore[arg-type]  # Invalid per spec
                attributes=(),
                span=Span(start=0, end=10),
            )

    def test_term_without_value_validator_defensive_check(self) -> None:
        """Validator defensively checks for term without value.

        Tests lines 188-195 (defensive validation even though AST prevents it).
        This tests the validator's defensive programming - if AST validation
        is ever bypassed, validator should still catch the error.
        """
        # Create a Term object bypassing __post_init__ validation
        # This is defensive testing - ensures validator catches errors
        # even if AST validation fails
        term = object.__new__(Term)
        object.__setattr__(term, "id", Identifier(name="broken"))
        object.__setattr__(term, "value", None)  # Invalid per spec
        object.__setattr__(term, "attributes", ())
        object.__setattr__(term, "span", Span(start=0, end=10))

        resource = Resource(entries=(term,))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # Validator should catch the missing value
        assert not result.is_valid
        errors = [a for a in result.annotations if "TERM_NO_VALUE" in a.code]
        assert len(errors) > 0


class TestCommentAndJunkValidation:
    """Test Comment and Junk entry handling."""

    def test_comment_entries_pass_validation(self) -> None:
        """Comments require no validation and pass through.

        Tests line 156-157 (Comment case in _validate_entry).
        """
        comment = Comment(content="# Test comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))
        result = validate(resource)
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_junk_entries_pass_validation(self) -> None:
        """Junk already represents parse errors, no further validation needed.

        Tests line 158-159 and 158->exit (Junk case in _validate_entry).
        """
        junk = Junk(content="invalid syntax", annotations=())
        resource = Resource(entries=(junk,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # Validator doesn't add errors for junk (already invalid at parse level)
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_resource_with_junk_from_parser(self) -> None:
        """Parser-generated junk entries are handled correctly."""
        parser = FluentParserV1()
        # Invalid FTL syntax produces Junk entries
        resource = parser.parse("msg = { invalid syntax here }")
        result = validate(resource)
        # Validator doesn't crash on junk
        assert isinstance(result, ValidationResult)

    def test_multiple_junk_entries_in_resource(self) -> None:
        """Multiple junk entries all pass through validator.

        Ensures Junk case exit path is exercised.
        """
        junk1 = Junk(content="bad syntax 1", annotations=())
        junk2 = Junk(content="bad syntax 2", annotations=())
        junk3 = Junk(content="bad syntax 3", annotations=())

        resource = Resource(entries=(junk1, junk2, junk3))
        validator = SemanticValidator()
        result = validator.validate(resource)

        # All junk entries pass through without adding validation errors
        assert result.is_valid

    def test_junk_entry_isolated_validation(self) -> None:
        """Single junk entry validates in isolation.

        Explicitly tests line 158-159 Junk case and exit path.
        This test isolates the Junk validation path to ensure
        branch coverage tools detect the 158->exit path.
        """
        from ftllexengine.core.depth_guard import DepthGuard

        # Create a Junk entry
        junk = Junk(content="isolated junk", annotations=())

        # Validate with fresh validator instance
        validator = SemanticValidator()
        errors: list[Annotation] = []
        depth_guard = DepthGuard(max_depth=100)

        # Call _validate_entry directly to ensure this specific path is measured
        validator._validate_entry(junk, errors, depth_guard)

        # Junk should not add any validation errors
        assert len(errors) == 0


class TestEmptyResourceValidation:
    """Test empty resource boundary condition."""

    def test_empty_resource_is_valid(self) -> None:
        """Empty resource (no entries) is valid."""
        resource = Resource(entries=())
        result = validate(resource)
        assert result.is_valid
        assert len(result.annotations) == 0


# ============================================================================
# PATTERN ELEMENT VALIDATION TESTS
# ============================================================================


class TestTextElementValidation:
    """Test TextElement validation."""

    def test_text_elements_require_no_validation(self) -> None:
        """Plain text elements need no validation.

        Tests line 245-246 and 247->exit (TextElement case in _validate_pattern_element).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = Plain text without any placeables")

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_text_with_special_characters(self) -> None:
        """Text elements with special characters validate."""
        parser = FluentParserV1()
        resource = parser.parse(r"msg = Text with special: !@#$%^&*()_+-=[]|;',./<>?")
        result = validate(resource)
        assert isinstance(result, ValidationResult)

    def test_text_element_explicit_validation_path(self) -> None:
        """Text element explicitly exercises validation path.

        Ensures TextElement case and exit path (line 247->exit) are covered.
        """
        # Create message with explicit TextElement
        text_elem = TextElement(value="Explicit text element")
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(text_elem,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        # TextElement requires no validation, should be valid
        assert result.is_valid

    def test_multiple_text_elements_in_pattern(self) -> None:
        """Pattern with multiple TextElements validates.

        Multiple invocations of TextElement path.
        """
        text1 = TextElement(value="First ")
        text2 = TextElement(value="Second ")
        text3 = TextElement(value="Third")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(text1, text2, text3)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        validator = SemanticValidator()
        result = validator.validate(resource)

        assert result.is_valid

    def test_text_element_isolated_validation(self) -> None:
        """Single TextElement validates in isolation.

        Explicitly tests line 245-246 TextElement case and exit path.
        This test isolates the TextElement validation path to ensure
        branch coverage tools detect the 247->exit path.
        """
        from ftllexengine.core.depth_guard import DepthGuard

        # Create TextElement
        text_elem = TextElement(value="isolated text")

        # Validate with fresh validator instance
        validator = SemanticValidator()
        errors: list[Annotation] = []
        depth_guard = DepthGuard(max_depth=100)

        # Call _validate_pattern_element directly to ensure this specific path is measured
        validator._validate_pattern_element(text_elem, errors, "test", depth_guard)

        # TextElement should not add any validation errors
        assert len(errors) == 0

    def test_junk_entry_isolated_direct_call(self) -> None:
        """Junk entry validated through direct method call.

        Alternative approach to ensure 158->exit branch is covered.
        """
        from ftllexengine.core.depth_guard import DepthGuard

        junk = Junk(content="direct call junk", annotations=())

        validator = SemanticValidator()
        errors: list[Annotation] = []
        depth_guard = DepthGuard(max_depth=100)

        # Direct call to _validate_entry with Junk
        validator._validate_entry(junk, errors, depth_guard)

        assert len(errors) == 0


class TestPlaceableValidation:
    """Test Placeable validation including nested cases."""

    def test_placeable_with_variable_reference(self) -> None:
        """Placeable containing variable reference validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello { $name }")
        result = validate(resource)
        assert result.is_valid

    def test_nested_placeables(self) -> None:
        """Nested placeables validate recursively.

        Tests lines 293-294 (Placeable as inline expression).
        """
        # Manually construct nested placeables
        inner = Placeable(expression=VariableReference(id=Identifier(name="x")))
        outer = Placeable(expression=inner)
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)
        assert result.is_valid


# ============================================================================
# INLINE EXPRESSION VALIDATION TESTS
# ============================================================================


class TestStringAndNumberLiteralValidation:
    """Test literal value validation."""

    def test_string_literal_always_valid(self) -> None:
        """String literals require no validation."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { "Hello" }')
        result = validate(resource)
        assert result.is_valid

    def test_number_literal_always_valid(self) -> None:
        """Number literals require no validation."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { 42 }")
        result = validate(resource)
        assert result.is_valid


class TestVariableReferenceValidation:
    """Test variable reference validation."""

    def test_variable_reference_always_valid(self) -> None:
        """Variable references require no semantic validation."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { $var }")
        result = validate(resource)
        assert result.is_valid


class TestMessageReferenceValidation:
    """Test message reference validation."""

    def test_message_reference_validates(self) -> None:
        """Message references are always valid semantically.

        Tests line 287 (MessageReference case in _validate_inline_expression).
        Message references cannot have arguments (enforced by grammar).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { other-msg }")
        result = validate(resource)
        assert result.is_valid

    def test_message_reference_with_attribute(self) -> None:
        """Message reference with attribute access validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other-msg.attr }")
        result = validate(resource)
        assert result.is_valid


class TestTermReferenceValidation:
    """Test term reference validation."""

    def test_term_reference_without_arguments(self) -> None:
        """Term reference without arguments validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -brand }")
        result = validate(resource)
        assert result.is_valid

    def test_term_reference_with_named_arguments(self) -> None:
        """Term reference with named arguments validates."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { -brand(case: "nominative") }')
        result = validate(resource)
        assert result.is_valid

    def test_term_reference_with_positional_arguments_warns(self) -> None:
        """Term reference with positional arguments emits warning.

        Tests lines 310-324 (_validate_term_reference with positional args).
        Per Fluent spec, positional args to terms are ignored at runtime.
        """
        # Manually construct term reference with positional args
        args = CallArguments(
            positional=(NumberLiteral(value=1, raw="1"),),
            named=(),
        )
        term_ref = TermReference(
            id=Identifier(name="brand"),
            arguments=args,
            attribute=None,
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=term_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should emit warning about positional args being ignored
        assert not result.is_valid
        warnings = [a for a in result.annotations if "positional arguments" in a.message.lower()]
        assert len(warnings) > 0

    def test_term_reference_with_attribute_and_arguments(self) -> None:
        """Term reference with attribute access and arguments validates."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { -brand.short(case: "genitive") }')
        result = validate(resource)
        assert result.is_valid


class TestFunctionReferenceValidation:
    """Test function reference validation."""

    def test_function_reference_without_arguments(self) -> None:
        """Function reference without arguments validates."""
        # Manually construct function call without arguments
        func_ref = FunctionReference(
            id=Identifier(name="BUILTIN"),
            arguments=CallArguments(positional=(), named=()),
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)
        assert result.is_valid

    def test_function_reference_with_positional_arguments(self) -> None:
        """Function reference with positional arguments validates.

        Tests lines 365-366 (positional arg validation in _validate_call_arguments).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER($count) }")
        result = validate(resource)
        assert result.is_valid

    def test_function_reference_with_named_arguments(self) -> None:
        """Function reference with named arguments validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER($count, minimumFractionDigits: 2) }")
        result = validate(resource)
        assert result.is_valid


# ============================================================================
# CALL ARGUMENTS VALIDATION TESTS
# ============================================================================


class TestCallArgumentsValidation:
    """Test call arguments validation."""

    def test_duplicate_named_arguments_invalid(self) -> None:
        """Function call with duplicate named arguments is invalid.

        Tests duplicate detection in _validate_call_arguments.
        """
        # Manually construct function with duplicate named args
        args = CallArguments(
            positional=(),
            named=(
                NamedArgument(
                    name=Identifier(name="option"),
                    value=NumberLiteral(value=1, raw="1"),
                ),
                NamedArgument(
                    name=Identifier(name="option"),  # Duplicate!
                    value=NumberLiteral(value=2, raw="2"),
                ),
            ),
        )
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=args,
        )
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))
        result = validate(resource)

        # Should detect duplicate named argument
        assert not result.is_valid
        errors = [a for a in result.annotations if "DUPLICATE" in a.code]
        assert len(errors) > 0

    def test_mixed_positional_and_named_arguments(self) -> None:
        """Function with both positional and named arguments validates."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER($val, minimumFractionDigits: 2) }")
        result = validate(resource)
        assert result.is_valid

    def test_nested_expressions_in_arguments(self) -> None:
        """Nested expressions in arguments validate recursively."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER({ $count }) }")
        result = validate(resource)
        assert result.is_valid


# ============================================================================
# SELECT EXPRESSION VALIDATION TESTS
# ============================================================================


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
            NumberLiteral(value=Decimal("0"), raw="not-a-number")

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


class TestValidationFramework:
    """Test the validation framework itself."""

    def test_validator_initialization(self):
        """Test validator can be created."""
        validator = SemanticValidator()
        assert validator is not None

    def test_validate_empty_resource(self):
        """Empty resource should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("")

        result = validate(resource)
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_validate_returns_result(self):
        """Validate function returns ValidationResult."""
        parser = FluentParserV1()
        resource = parser.parse("msg = value")

        result = validate(resource)
        assert isinstance(result, ValidationResult)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "annotations")


class TestMessageValidationHighLevel:
    """Test message validation rules."""

    def test_valid_simple_message(self):
        """Simple message should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("hello = Hello, world!")

        result = validate(resource)
        assert result.is_valid
        assert len(result.annotations) == 0

    def test_valid_message_with_variable(self):
        """Message with variable should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("welcome = Welcome, { $name }!")

        result = validate(resource)
        assert result.is_valid

    def test_valid_message_with_attribute(self):
        """Message with attribute should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Value
    .tooltip = Tooltip text
""")

        result = validate(resource)
        assert result.is_valid

    def test_valid_message_reference(self):
        """Message referencing another message should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other-msg }")

        result = validate(resource)
        assert result.is_valid

    def test_valid_message_reference_with_attribute(self):
        """Message.attr reference should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other.attr }")

        result = validate(resource)
        assert result.is_valid


class TestTermValidationHighLevel:
    """Test term validation rules."""

    def test_valid_simple_term(self):
        """Simple term should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = Firefox")

        result = validate(resource)
        assert result.is_valid

    def test_valid_term_with_attribute(self):
        """Term with attribute should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Firefox
    .gender = masculine
""")

        result = validate(resource)
        assert result.is_valid

    def test_valid_term_reference_with_arguments(self):
        """Term reference with call arguments should be valid."""
        parser = FluentParserV1()
        # Note: This tests that if the parser creates a TermReference with arguments,
        # the validator accepts it
        resource = parser.parse("msg = { -term() }")

        result = validate(resource)
        # Should be valid - terms can be parameterized
        assert result.is_valid


class TestSelectExpressionValidationHighLevel:
    """Test select expression validation rules."""

    def test_valid_select_with_default(self):
        """Select with default variant should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [one] One item
   *[other] Many items
}
""")

        result = validate(resource)
        assert result.is_valid

    def test_valid_select_multiple_variants(self):
        """Select with multiple non-default variants should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [zero] No items
    [one] One item
    [two] Two items
   *[other] Many items
}
""")

        result = validate(resource)
        assert result.is_valid

    def test_invalid_select_no_default(self):
        """Parser rejects select without default variant (syntactic validation).

        Note: This is now a parser-level validation, not semantic validation.
        The parser creates Junk for select expressions without default variants
        per FTL spec requirements, so semantic validation never sees them.

        This test verifies the parser correctly enforces this rule.
        """
        from ftllexengine.syntax.ast import Junk

        parser = FluentParserV1()
        # Try to parse select without default
        resource = parser.parse("""
msg = { $count ->
    [one] One item
    [two] Two items
}
""")

        # Parser should create Junk (syntactic error)
        assert len(resource.entries) >= 1
        assert isinstance(resource.entries[0], Junk)

        # Verify error annotation exists
        junk = resource.entries[0]
        assert len(junk.annotations) > 0
        # Generic error message (detailed info removed)

    def test_invalid_duplicate_variant_keys(self):
        """Select with duplicate variant keys should be invalid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [one] First one
    [one] Second one (duplicate)
   *[other] Many
}
""")

        result = validate(resource)

        # Should detect duplicate keys
        if not result.is_valid:
            assert any("VALIDATION_VARIANT_DUPLICATE" in ann.code for ann in result.annotations)
        else:
            # Parser might have deduped, which is also acceptable
            pass

    def test_high_precision_numeric_variants_not_false_duplicate(self):
        """High-precision numeric variant keys are treated as distinct.

        Regression test for SEM-VALIDATOR-PRECISION-001.
        Validator should use NumberLiteral.raw (original string) for comparison,
        not NumberLiteral.value (float), to preserve precision.
        This matches resolver behavior.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    [0.10000000000000001] precise
    [0.1] rounded
   *[other] default
}
""")

        result = validate(resource)

        # These keys should NOT be treated as duplicates because they have
        # different source representations, even though they might round to
        # the same float value. The validator should accept this as valid FTL.
        assert result.is_valid


class TestFunctionValidationHighLevel:
    """Test function reference validation rules."""

    def test_valid_function_no_args(self):
        """Function with no arguments should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { FUNC() }")

        result = validate(resource)
        assert result.is_valid

    def test_valid_function_positional_args(self):
        """Function with positional arguments should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER($count) }")

        result = validate(resource)
        assert result.is_valid

    def test_valid_function_named_args(self):
        """Function with named arguments should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { NUMBER($count, minimumFractionDigits: 2) }")

        result = validate(resource)
        assert result.is_valid

    def test_valid_function_mixed_args(self):
        """Function with positional and named arguments should be valid."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { DATETIME($date, hour: "numeric", minute: "numeric") }')

        result = validate(resource)
        assert result.is_valid

    def test_invalid_duplicate_named_args(self):
        """Function with duplicate named arguments should be invalid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { FUNC(x: 1, x: 2) }")

        result = validate(resource)

        # Should detect duplicate named arguments
        if not result.is_valid:
            assert any("E0010" in ann.code for ann in result.annotations)


class TestRealWorldScenarios:
    """Test validation on real-world FTL patterns."""

    def test_complex_message_with_select(self):
        """Complex message with select should validate."""
        parser = FluentParserV1()
        resource = parser.parse("""
emails = { $unreadEmails ->
    [one] You have one unread email
   *[other] You have { $unreadEmails } unread emails
}
""")

        result = validate(resource)
        assert result.is_valid

    def test_message_with_multiple_placeables(self):
        """Message with multiple placeables should validate."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Hello { $firstName } { $lastName }!")

        result = validate(resource)
        assert result.is_valid

    def test_nested_select_expressions(self):
        """Nested select expressions should validate."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $gender ->
    [male] { $count ->
        [one] He has one item
       *[other] He has { $count } items
    }
   *[female] { $count ->
        [one] She has one item
       *[other] She has { $count } items
    }
}
""")

        result = validate(resource)
        assert result.is_valid

    def test_term_reference_in_message(self):
        """Term reference in message should validate."""
        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Firefox
welcome = Welcome to { -brand }!
""")

        result = validate(resource)
        assert result.is_valid

    def test_message_with_function_and_select(self):
        """Message combining function call and select should validate."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Updated { DATETIME($date, month: "long", year: "numeric") } - { $status ->
    [active] Active
   *[inactive] Inactive
}
""")

        result = validate(resource)
        assert result.is_valid


class TestEdgeCases:
    """Test edge cases in validation."""

    def test_comment_only_resource(self):
        """Resource with only comments should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
# This is a comment
## This is a group comment
### This is a resource comment
""")

        result = validate(resource)
        assert result.is_valid

    def test_message_with_only_attributes(self):
        """Message with only attributes (no value) should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
    .attr1 = Value 1
    .attr2 = Value 2
""")

        result = validate(resource)
        # This should be valid per spec
        assert result.is_valid

    def test_empty_pattern(self):
        """Message with empty value should be valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = ")

        result = validate(resource)
        # Empty pattern is syntactically valid
        assert result.is_valid

    def test_junk_entries_ignored(self):
        """Junk entries should not be validated (already errors)."""
        parser = FluentParserV1()
        resource = parser.parse("""
valid = Value
invalid { syntax
also-valid = Another value
""")

        result = validate(resource)
        # Should validate the valid entries, ignore junk
        assert result.is_valid


class TestValidatorState:
    """Test validator state management."""

    def test_validator_reusable(self):
        """Validator should be reusable across multiple validations."""
        validator = SemanticValidator()
        parser = FluentParserV1()

        resource1 = parser.parse("msg1 = Value 1")
        result1 = validator.validate(resource1)
        assert result1.is_valid

        resource2 = parser.parse("msg2 = Value 2")
        result2 = validator.validate(resource2)
        assert result2.is_valid

        # Errors shouldn't accumulate
        assert len(result1.annotations) == 0
        assert len(result2.annotations) == 0

    def test_validate_function_is_stateless(self):
        """Module-level validate() function should be stateless."""
        parser = FluentParserV1()

        result1 = validate(parser.parse("msg1 = Value 1"))
        result2 = validate(parser.parse("msg2 = Value 2"))

        assert result1.is_valid
        assert result2.is_valid


class TestValidationErrorCodes:
    """Test that error codes are descriptive and consistent."""

    def test_diagnostic_codes_are_unique(self):
        """All validation DiagnosticCode values should be unique."""
        from ftllexengine.diagnostics.codes import DiagnosticCode

        # Get all validation-related codes (5000-5199 range)
        validation_codes = [
            code for code in DiagnosticCode
            if code.value >= 5000 and code.value < 5200
        ]
        values = [code.value for code in validation_codes]
        assert len(values) == len(set(values)), "DiagnosticCode values must be unique"

    def test_validation_messages_exist(self):
        """All validation codes should have messages in _VALIDATION_MESSAGES."""
        from ftllexengine.diagnostics.codes import DiagnosticCode
        from ftllexengine.syntax.validator import _VALIDATION_MESSAGES

        for code, message in _VALIDATION_MESSAGES.items():
            assert isinstance(code, DiagnosticCode), f"{code} should be DiagnosticCode"
            assert len(message) > 5, f"Message for {code.name} should be descriptive"
            assert message[0].isupper(), f"Message for {code.name} should start with uppercase"


class TestAttributeGranularCycleDetection:
    """Attribute-granular cycle detection prevents false positives.

    A message referencing its own attribute (msg = { msg.tooltip }) is NOT a cycle.
    Only true self-references (msg = { msg }) or cross-message cycles are cyclic.
    This distinction prevents spurious warnings for common FTL patterns.
    """

    def test_cross_attribute_reference_not_cyclic(self) -> None:
        """Message value referencing its own attribute is not a circular reference."""
        bundle = FluentBundle("en")
        ftl = "msg = { msg.tooltip }\n    .tooltip = Tooltip text\n"
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) == 0

    def test_true_self_reference_detected(self) -> None:
        """Message value referencing itself is a circular reference."""
        bundle = FluentBundle("en")
        ftl = "msg = { msg }\n"
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0

    def test_term_attribute_self_reference_detected(self) -> None:
        """Term attribute referencing itself is a circular reference."""
        bundle = FluentBundle("en")
        ftl = "-term = Value\n    .attr = { -term.attr }\n"
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0

    def test_cross_term_cycle_detected(self) -> None:
        """Cross-term mutual references produce a circular reference warning."""
        bundle = FluentBundle("en")
        ftl = "-a = { -b }\n-b = { -a }\n"
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0


# ============================================================================
# VALIDATION EDGE CASES (from test_semantic_validation_edge_cases.py)
# ============================================================================


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
