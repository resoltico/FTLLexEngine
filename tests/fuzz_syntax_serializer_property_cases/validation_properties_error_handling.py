# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Validation Properties (Error Handling)
# =============================================================================


class TestValidationProperties:
    """Test validation error detection for invalid ASTs."""

    def test_select_no_defaults_raises_validation_error(self) -> None:
        """COVERAGE: Lines 117-118 - SelectExpression with 0 defaults."""

        # Build invalid SelectExpression with no defaults
        invalid_select = build_invalid_select_no_defaults()

        # Wrap in a message
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Validation should catch the error
        with pytest.raises(SerializationValidationError, match="no default variant"):
            serialize(resource, validate=True)

    def test_select_multiple_defaults_raises_validation_error(self) -> None:
        """COVERAGE: Lines 121-125 - SelectExpression with >1 defaults."""

        # Build invalid SelectExpression with multiple defaults
        invalid_select = build_invalid_select_multiple_defaults()

        # Wrap in a message
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Validation should catch the error
        with pytest.raises(SerializationValidationError, match="2 default variants"):
            serialize(resource, validate=True)

    @given(message=ftl_message_nodes())
    def test_valid_ast_passes_validation(self, message: Message) -> None:
        """PROPERTY: Valid ASTs pass validation without error.

        Events emitted:
        - validation=passed: Successful validation
        """
        resource = Resource(entries=(message,))

        event("validation=passed")

        # Should not raise
        serialized = serialize(resource, validate=True)
        assert isinstance(serialized, str)

    def test_validation_can_be_disabled(self) -> None:
        """COVERAGE: validate=False parameter skips validation."""

        # Build invalid SelectExpression
        invalid_select = build_invalid_select_no_defaults()
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=invalid_select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should not raise when validate=False
        serialized = serialize(resource, validate=False)
        assert isinstance(serialized, str)

    def test_invalid_identifier_raises_validation_error(self) -> None:
        """COVERAGE: Invalid identifier validation."""

        # Create message with invalid identifier (empty string)
        # Bypass validation by using object.__new__
        identifier = object.__new__(Identifier)
        object.__setattr__(identifier, "name", "")  # Invalid: empty
        object.__setattr__(identifier, "span", None)

        message = Message(
            id=identifier,
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_duplicate_named_arguments_raises_validation_error(self) -> None:
        """COVERAGE: Duplicate named arguments validation."""

        # Create function call with duplicate named arguments
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=StringLiteral(value="currency"),
                    ),
                    NamedArgument(
                        name=Identifier(name="style"),  # Duplicate!
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="Duplicate named argument"):
            serialize(resource, validate=True)

    def test_invalid_named_argument_value_type_raises_error(self) -> None:
        """COVERAGE: Named argument value type validation."""

        # Create function call with invalid named argument value (not literal)
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="style"),
                        value=cast("FTLLiteral", VariableReference(id=Identifier(name="var"))),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationValidationError, match="invalid value type"):
            serialize(resource, validate=True)
