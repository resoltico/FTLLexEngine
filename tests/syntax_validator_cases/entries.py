# mypy: ignore-errors
from tests.syntax_validator_cases import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    CommentType,
    DepthGuard,
    FluentParserV1,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SemanticValidator,
    Span,
    Term,
    TermReference,
    TextElement,
    ValidationResult,
    VariableReference,
    pytest,
    validate,
)


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

