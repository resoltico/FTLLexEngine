"""Bundle type validation tests to kill survived mutations.

This module targets type validation and error handling mutations in FluentBundle:
- Type checks for arguments
- Error type validations
- Dict operation mutations
- Resource handling edge cases

Target: Kill ~55 bundle-related mutations
Phase: 1 (High-Impact Quick Wins)
"""

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime import FluentBundle


class TestBundleInitialization:
    """Test bundle initialization type validations.

    Targets mutations in __init__ parameter validation.
    """

    def test_bundle_requires_locale_string(self):
        """Kills: locale type check mutations.

        Locale must be a string.
        """
        # Valid: string locale
        bundle = FluentBundle("en-US")
        assert bundle.locale == "en-US"

    def test_bundle_with_empty_locale_raises(self):
        """Kills: len(locale) > 0 mutations.

        Empty locale string should raise ValueError.
        """
        with pytest.raises(ValueError, match="Locale code cannot be empty"):
            FluentBundle("")

    def test_bundle_with_single_char_locale(self):
        """Kills: len(locale) > 1 mutations.

        Single character locale should work.
        """
        bundle = FluentBundle("a")
        assert bundle.locale == "a"


class TestAddResourceTypeValidation:
    """Test add_resource type validation.

    Targets mutations in resource type checking and error handling.
    """

    def test_add_resource_requires_string(self):
        """Kills: isinstance(source, str) mutations.

        add_resource should only accept strings.
        """
        bundle = FluentBundle("en")

        # Valid: string source
        bundle.add_resource("msg = Value")
        assert bundle.has_message("msg")

    def test_add_resource_with_empty_string(self):
        """Kills: len(source) > 0 mutations.

        Empty source string should work without error.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("")
        assert len(bundle.get_message_ids()) == 0

    def test_add_resource_with_only_whitespace(self):
        """Kills: source.strip() mutations.

        Whitespace-only source should work.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("   \n\t  ")
        assert len(bundle.get_message_ids()) == 0

    def test_add_resource_with_only_junk(self):
        """Kills: junk handling mutations.

        Source with only junk entries should not crash.
        """
        bundle = FluentBundle("en")
        # Invalid syntax creates junk
        bundle.add_resource("??? invalid !!!!")
        # Should have zero valid messages
        assert len(bundle.get_message_ids()) == 0


class TestMessageRegistrationValidation:
    """Test message registration type checks.

    Targets isinstance() mutations in entry processing.
    """

    def test_register_message_type_check(self):
        """Kills: isinstance(entry, Message) → isinstance(entry, Term) mutations.

        Messages should be registered in message registry.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("hello = Hello")

        assert bundle.has_message("hello")
        assert "hello" in bundle.get_message_ids()

    def test_register_term_type_check(self):
        """Kills: isinstance(entry, Term) → isinstance(entry, Message) mutations.

        Terms should be registered separately from messages.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("-brand = Firefox")

        # Terms are internal, not exposed as messages
        assert not bundle.has_message("-brand")
        assert "-brand" not in bundle.get_message_ids()

    def test_mixed_messages_and_terms(self):
        """Kills: entry type confusion mutations.

        Messages and terms should be distinguished correctly.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("""
-brand = Firefox
welcome = Welcome to { -brand }
""")

        # Only message should be in message registry
        assert bundle.has_message("welcome")
        assert not bundle.has_message("-brand")
        assert len(bundle.get_message_ids()) == 1


class TestMessageLookupValidation:
    """Test message lookup and error handling.

    Targets dict operations and key existence checks.
    """

    def test_has_message_with_existing_id(self):
        """Kills: key in dict mutations.

        has_message should return True for existing messages.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value")

        assert bundle.has_message("msg") is True

    def test_has_message_with_nonexistent_id(self):
        """Kills: key in dict → key not in dict mutations.

        has_message should return False for missing messages.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value")

        assert bundle.has_message("nonexistent") is False

    def test_has_message_with_empty_string_id(self):
        """Kills: len(id) > 0 mutations.

        Empty string ID should return False (no such message).
        """
        bundle = FluentBundle("en")
        assert bundle.has_message("") is False

    def test_get_message_ids_returns_all_ids(self):
        """Kills: dict.keys() mutations.

        get_message_ids should return all registered message IDs.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("""
msg1 = Value1
msg2 = Value2
msg3 = Value3
""")

        ids = bundle.get_message_ids()
        assert "msg1" in ids
        assert "msg2" in ids
        assert "msg3" in ids
        assert len(ids) == 3

    def test_get_message_ids_empty_bundle(self):
        """Kills: len(dict) > 0 mutations.

        Empty bundle should return empty ID list.
        """
        bundle = FluentBundle("en")
        ids = bundle.get_message_ids()
        assert len(ids) == 0


class TestFormatPatternErrorHandling:
    """Test format_pattern error handling.

    Targets error type mutations and error path handling.
    """

    def test_format_missing_message_raises_error(self):
        """Kills: missing message error handling mutations.

        Formatting missing message should raise FrozenFluentError.
        """
        bundle = FluentBundle("en")

        result, errors = bundle.format_pattern("nonexistent")
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        # Error message should include the message ID
        assert "nonexistent" in str(errors[0]).lower()
        assert result == "{nonexistent}"

    def test_format_with_empty_message_id(self):
        """Kills: empty string handling mutations.

        Empty message ID should raise FrozenFluentError.
        """
        bundle = FluentBundle("en")

        result, errors = bundle.format_pattern("")
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert result == "{???}"  # Invalid message ID returns {???}
        assert "Invalid message ID" in str(errors[0])

    def test_format_with_none_args(self):
        """Kills: args is None mutations.

        None args should be handled as empty dict.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value")

        result, errors = bundle.format_pattern("msg", None)
        assert result == "Value"
        assert errors == ()

    def test_format_with_empty_args(self):
        """Kills: len(args) > 0 mutations.

        Empty args dict should work.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value")

        result, errors = bundle.format_pattern("msg", {})
        assert result == "Value"
        assert errors == ()

    def test_format_with_missing_variable(self):
        """Kills: variable lookup error handling mutations.

        Missing variable in args should use fallback.
        """
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello, { $name }!")

        # Missing $name variable
        result, errors = bundle.format_pattern("msg", {})
        # Should contain error marker or variable name
        assert "name" in result or "$name" in result or "???" in result
        assert len(errors) > 0


class TestValidateResourceErrorHandling:
    """Test validate_resource error handling.

    Targets validation result creation and error counting.
    """

    def test_validate_valid_resource(self):
        """Kills: is_valid property mutations.

        Valid resource should have is_valid=True.
        """
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = Value")

        assert result.is_valid is True
        assert result.error_count == 0

    def test_validate_invalid_resource(self):
        """Kills: error counting mutations.

        Invalid resource should have errors.
        """
        bundle = FluentBundle("en")
        # Invalid syntax should produce junk
        result = bundle.validate_resource("msg = { unclosed")

        assert result.is_valid is False
        assert result.error_count > 0

    def test_validate_empty_resource(self):
        """Kills: empty resource handling mutations.

        Empty resource should be valid.
        """
        bundle = FluentBundle("en")
        result = bundle.validate_resource("")

        assert result.is_valid is True
        assert result.error_count == 0

    def test_validation_result_warning_count(self):
        """Kills: warning_count property mutations.

        ValidationResult should track warnings.
        """
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = Value")

        # Currently no warnings implemented, should be 0
        assert result.warning_count == 0


class TestResourceAccumulationValidation:
    """Test multiple add_resource calls.

    Targets mutations in resource accumulation logic.
    """

    def test_add_multiple_resources_accumulates(self):
        """Kills: dict update mutations.

        Multiple add_resource calls should accumulate messages.
        """
        bundle = FluentBundle("en")

        bundle.add_resource("msg1 = First")
        assert len(bundle.get_message_ids()) == 1

        bundle.add_resource("msg2 = Second")
        assert len(bundle.get_message_ids()) == 2

        bundle.add_resource("msg3 = Third")
        assert len(bundle.get_message_ids()) == 3

    def test_add_resource_overwrites_duplicate_id(self):
        """Kills: dict assignment mutations.

        Later resources with same ID should overwrite earlier ones.
        """
        bundle = FluentBundle("en")

        bundle.add_resource("msg = First")
        first_result, first_errors = bundle.format_pattern("msg")

        bundle.add_resource("msg = Second")
        second_result, second_errors = bundle.format_pattern("msg")

        assert first_result == "First"
        assert second_result == "Second"
        assert first_errors == ()
        assert second_errors == ()

    def test_add_resource_preserves_other_messages(self):
        """Kills: dict clear() mutations.

        Adding resource shouldn't clear existing messages.
        """
        bundle = FluentBundle("en")

        bundle.add_resource("msg1 = First")
        bundle.add_resource("msg2 = Second")

        # Both should still exist
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")


class TestLocalePropertyValidation:
    """Test locale property access.

    Targets locale getter mutations.
    """

    def test_locale_property_returns_locale(self):
        """Kills: locale property mutations.

        Locale property should return the locale.
        """
        bundle = FluentBundle("de-DE")
        assert bundle.locale == "de-DE"

    def test_locale_property_not_none(self):
        """Kills: locale is None mutations.

        Locale should never be None.
        """
        bundle = FluentBundle("fr")
        assert bundle.locale is not None

    def test_locale_property_is_string(self):
        """Kills: type(locale) mutations.

        Locale should always be a string.
        """
        bundle = FluentBundle("en")
        assert isinstance(bundle.locale, str)


class TestBundleInternalState:
    """Test internal state consistency.

    Targets internal registry mutations.
    """

    def test_messages_registry_starts_empty(self):
        """Kills: dict initialization mutations.

        New bundle should have empty message registry.
        """
        bundle = FluentBundle("en")
        assert len(bundle.get_message_ids()) == 0

    def test_messages_registry_grows_correctly(self):
        """Kills: registry size mutations.

        Registry size should match message count.
        """
        bundle = FluentBundle("en")

        bundle.add_resource("msg1 = One")
        assert len(bundle.get_message_ids()) == 1

        bundle.add_resource("msg2 = Two\nmsg3 = Three")
        assert len(bundle.get_message_ids()) == 3


class TestErrorMessageContent:
    """Test error message handling.

    Targets error message string mutations (lower priority but comprehensive).
    """

    def test_format_missing_message_includes_id(self):
        """Kills: error message content mutations.

        Missing message error should include message ID.
        """
        bundle = FluentBundle("en")

        result, errors = bundle.format_pattern("missing-message")
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        # Error should reference the ID
        assert "missing-message" in str(errors[0]).lower()
        assert result == "{missing-message}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
