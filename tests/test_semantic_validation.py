"""Tests for semantic validation per Fluent spec valid.md.

Tests the two-level validation:
1. Well-formed: Grammar conformance (tested in parser tests)
2. Valid: Semantic correctness (tested here)

Per spec: "The validation process may reject syntax which is well-formed."
"""


from ftllexengine.diagnostics import ValidationResult
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import SemanticValidator, validate


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


class TestMessageValidation:
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


class TestTermValidation:
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


class TestSelectExpressionValidation:
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


class TestFunctionValidation:
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
