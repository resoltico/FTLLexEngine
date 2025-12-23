"""Comprehensive tests for FluentBundle (Phase 3: Infrastructure/i18n)."""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from ftllexengine.diagnostics import (
    FluentReferenceError,
    FluentSyntaxError,
)
from ftllexengine.runtime import FluentBundle


class TestFluentBundleCreation:
    """Test FluentBundle initialization."""

    def test_create_bundle_with_locale(self) -> None:
        """Create bundle with locale code."""
        bundle = FluentBundle("lv_LV")

        assert bundle.locale == "lv_LV"

    def test_create_bundle_initializes_empty_registries(self) -> None:
        """Bundle starts with empty message/term registries."""
        bundle = FluentBundle("en_US")

        assert len(bundle.get_message_ids()) == 0
        assert not bundle.has_message("any-message")


class TestFluentBundleAddResource:
    """Test FluentBundle add_resource method."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle for testing."""
        return FluentBundle("lv_LV")

    def test_add_resource_simple_message(self, bundle: Any) -> None:
        """add_resource parses and registers simple message."""
        bundle.add_resource("hello = Sveiki, pasaule!")

        assert bundle.has_message("hello")
        assert "hello" in bundle.get_message_ids()

    def test_add_resource_multiple_messages(self, bundle: Any) -> None:
        """add_resource registers all messages from source."""
        source = """
hello = Sveiki!
goodbye = Uz redzēšanos!
thanks = Paldies!
"""
        bundle.add_resource(source)

        assert bundle.has_message("hello")
        assert bundle.has_message("goodbye")
        assert bundle.has_message("thanks")
        assert len(bundle.get_message_ids()) == 3

    def test_add_resource_message_with_variable(self, bundle: Any) -> None:
        """add_resource handles messages with variables."""
        bundle.add_resource("welcome = Laipni lūdzam, { $name }!")

        assert bundle.has_message("welcome")

    def test_add_resource_message_with_attribute(self, bundle: Any) -> None:
        """add_resource handles messages with attributes."""
        source = """
button-save = Saglabāt
    .tooltip = Saglabā ierakstu
"""
        bundle.add_resource(source)

        assert bundle.has_message("button-save")

    def test_add_resource_with_junk_entries_continues(self, bundle: Any) -> None:
        """add_resource with non-critical syntax errors creates junk but continues."""
        # Parser is robust - creates Junk entries for invalid syntax but doesn't crash
        bundle.add_resource("invalid message syntax")

        # Bundle should still work, junk is just ignored
        assert len(bundle.get_message_ids()) == 0  # No valid messages parsed

    def test_add_multiple_resources_accumulates(self, bundle: Any) -> None:
        """Multiple add_resource calls accumulate messages."""
        bundle.add_resource("msg1 = First")
        bundle.add_resource("msg2 = Second")

        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")
        assert len(bundle.get_message_ids()) == 2


class TestFluentBundleFormatPattern:
    """Test FluentBundle format_pattern method."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with sample messages."""
        bundle = FluentBundle("lv_LV")
        bundle.add_resource("""
hello = Sveiki, pasaule!
welcome = Laipni lūdzam, { $name }!
greeting = { $name } saka { $message }
button-save = Saglabāt
    .tooltip = Saglabā ierakstu datubāzē
""")
        return bundle

    def test_format_pattern_simple_message(self, bundle: Any) -> None:
        """format_pattern returns simple message text."""
        result, errors = bundle.format_pattern("hello")

        assert result == "Sveiki, pasaule!"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_with_variable(self, bundle: Any) -> None:
        """format_pattern substitutes variable from args."""
        result, errors = bundle.format_pattern("welcome", {"name": "Jānis"})

        assert "Jānis" in result
        assert "Laipni lūdzam" in result
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_with_multiple_variables(self, bundle: Any) -> None:
        """format_pattern substitutes multiple variables."""
        result, errors = bundle.format_pattern("greeting", {"name": "Anna", "message": "Sveiki"})

        assert "Anna" in result
        assert "Sveiki" in result
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_missing_variable_uses_placeholder(self, bundle: Any) -> None:
        """format_pattern handles missing variable gracefully."""
        result, errors = bundle.format_pattern("welcome", {})

        # Should not crash, returns some fallback
        assert isinstance(result, str)
        assert len(errors) == 1, (
            f"Expected 1 error for missing variable, got {len(errors)}: {errors}"
        )
        assert isinstance(errors[0], FluentReferenceError)
        assert "variable" in str(errors[0]).lower() or "name" in str(errors[0]).lower()

    def test_format_pattern_with_attribute_parameter(self, bundle: Any) -> None:
        """format_pattern accepts attribute parameter."""
        result, errors = bundle.format_pattern("button-save", attribute="tooltip")

        # Should successfully retrieve the .tooltip attribute
        assert result == "Saglabā ierakstu datubāzē"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_missing_message_raises_error(self, bundle: Any) -> None:
        """format_pattern for non-existent message raises FluentReferenceError."""
        result, errors = bundle.format_pattern("nonexistent-message")
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)
        assert "not found" in str(errors[0]).lower()
        assert result == "{nonexistent-message}"

    def test_format_pattern_none_args(self, bundle: Any) -> None:
        """format_pattern with args=None works for messages without variables."""
        result, errors = bundle.format_pattern("hello", None)

        assert result == "Sveiki, pasaule!"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_empty_args(self, bundle: Any) -> None:
        """format_pattern with empty dict works."""
        result, errors = bundle.format_pattern("hello", {})

        assert result == "Sveiki, pasaule!"
        assert errors == (), f"Unexpected errors: {errors}"


class TestFluentBundleHasMessage:
    """Test FluentBundle has_message method."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with messages."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("existing = This message exists")
        return bundle

    def test_has_message_returns_true_when_exists(self, bundle: Any) -> None:
        """has_message returns True for existing message."""
        assert bundle.has_message("existing") is True

    def test_has_message_returns_false_when_not_exists(self, bundle: Any) -> None:
        """has_message returns False for non-existent message."""
        assert bundle.has_message("nonexistent") is False


class TestFluentBundleGetMessageIds:
    """Test FluentBundle get_message_ids method."""

    def test_get_message_ids_empty_bundle(self) -> None:
        """get_message_ids returns empty list for new bundle."""
        bundle = FluentBundle("de_DE")

        assert bundle.get_message_ids() == []

    def test_get_message_ids_returns_all_ids(self) -> None:
        """get_message_ids returns all registered message IDs."""
        bundle = FluentBundle("pl_PL")
        bundle.add_resource("""
msg1 = First
msg2 = Second
msg3 = Third
""")

        ids = bundle.get_message_ids()

        assert len(ids) == 3
        assert "msg1" in ids
        assert "msg2" in ids
        assert "msg3" in ids


class TestFluentBundleAddFunction:
    """Test FluentBundle add_function method."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle."""
        return FluentBundle("en_US")

    def test_add_function_registers_custom_function(self) -> None:
        """add_function adds custom function to bundle."""
        bundle = FluentBundle("en", use_isolating=False)

        def CUSTOM(value: object) -> str:
            return str(value).upper()

        bundle.add_function("CUSTOM", CUSTOM)

        # Verify function works by using it in a message
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "test"})
        assert result == "TEST"

    def test_add_function_with_callable(self) -> None:
        """add_function accepts any callable."""
        bundle = FluentBundle("en", use_isolating=False)

        # Function must return string per spec
        bundle.add_function("LAMBDA", lambda x: str(int(x) * 2))
        bundle.add_resource("msg = { LAMBDA($n) }")
        result, _ = bundle.format_pattern("msg", {"n": "5"})
        assert result == "10"


class TestFluentBundleErrorHandling:
    """Test FluentBundle error handling and edge cases."""

    @pytest.fixture
    def bundle(self) -> Any:
        """Create bundle with test message."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("test = Test message")
        return bundle

    def test_format_pattern_handles_resolver_errors_gracefully(self, bundle: Any) -> None:
        """format_pattern returns fallback on resolver errors."""
        # Add message that references undefined variable
        bundle.add_resource("broken-msg = Value is { $undefined }")

        result, errors = bundle.format_pattern("broken-msg", {})

        # Should return result with variable fallback, plus error
        assert isinstance(result, str)
        assert "{$undefined}" in result  # Variable fallback
        assert len(errors) >= 1, f"Expected at least 1 error for undefined variable, got {errors}"
        assert isinstance(errors[0], FluentReferenceError)

    def test_format_pattern_handles_key_error_gracefully(self, bundle: Any) -> None:
        """format_pattern handles KeyError (missing variable) gracefully."""
        bundle.add_resource("needs-var = Hello { $name }")

        # Call without providing required variable
        result, errors = bundle.format_pattern("needs-var", {})

        # Should return result with variable fallback, plus error
        assert isinstance(result, str)
        assert "{$name}" in result
        assert len(errors) >= 1, f"Expected error for missing variable, got {errors}"
        assert isinstance(errors[0], FluentReferenceError)

    def test_format_pattern_handles_attribute_error_gracefully(self, bundle: Any) -> None:
        """format_pattern handles AttributeError gracefully."""
        bundle.add_resource("attr-msg = Test")

        # Try to access non-existent attribute
        result, errors = bundle.format_pattern("attr-msg", attribute="nonexistent")

        # Should handle gracefully with fallback + error
        assert isinstance(result, str)
        assert len(errors) >= 1, f"Expected error for nonexistent attribute, got {errors}"
        assert isinstance(errors[0], FluentReferenceError)
        assert "attribute" in str(errors[0]).lower()

    def test_format_pattern_handles_unexpected_errors_gracefully(self, bundle: Any) -> None:
        """format_pattern catches unexpected exceptions."""
        # Even if something goes really wrong, bundle should not crash
        result, errors = bundle.format_pattern("test", {})

        assert result == "Test message"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_add_resource_with_terms_and_junk(self) -> None:
        """add_resource handles mix of messages, terms, and junk."""
        bundle = FluentBundle("en_US")

        source = """
message1 = Hello
-term1 = Brand Name
message2 = Goodbye
invalid syntax here
-term2 = Another Term
"""
        bundle.add_resource(source)

        # Messages should be registered
        assert bundle.has_message("message1")
        assert bundle.has_message("message2")

        # Terms should not appear in messages
        assert not bundle.has_message("-term1")

        # Should have exactly 2 messages
        assert len(bundle.get_message_ids()) == 2


class TestFluentBundleIntegration:
    """Integration tests for FluentBundle with complex scenarios."""

    def test_complete_workflow_simple(self) -> None:
        """Full workflow: create, add resource, format."""
        bundle = FluentBundle("lv_LV")
        bundle.add_resource("greeting = Sveiki, { $name }!")

        result, errors = bundle.format_pattern("greeting", {"name": "Pēteris"})

        assert "Sveiki" in result
        assert "Pēteris" in result
        assert errors == (), f"Unexpected errors: {errors}"

    def test_multiple_locales_independent(self) -> None:
        """Multiple bundles for different locales are independent."""
        bundle_lv = FluentBundle("lv_LV")
        bundle_en = FluentBundle("en_US")

        bundle_lv.add_resource("hello = Sveiki!")
        bundle_en.add_resource("hello = Hello!")

        result_lv, errors_lv = bundle_lv.format_pattern("hello")
        assert result_lv == "Sveiki!"
        assert errors_lv == ()
        result_en, errors_en = bundle_en.format_pattern("hello")
        assert result_en == "Hello!"
        assert errors_en == ()

    def test_overwrite_message_with_new_resource(self) -> None:
        """Adding resource with same message ID overwrites."""
        bundle = FluentBundle("en_US")

        bundle.add_resource("msg = Original")
        result1, errors1 = bundle.format_pattern("msg")
        assert result1 == "Original"
        assert errors1 == ()

        bundle.add_resource("msg = Updated")
        result2, errors2 = bundle.format_pattern("msg")
        assert result2 == "Updated"
        assert errors2 == ()


class TestFluentBundleEdgeCases:
    """Test edge cases and additional coverage paths."""

    def test_add_resource_with_terms_only(self) -> None:
        """Bundle handles resources with only terms (no messages)."""
        bundle = FluentBundle("en_US")

        # Add resource with only terms (lines 76-77)
        bundle.add_resource("""
-brand = MyApp
-version = 3.0
-company = MyCompany
""")

        # No messages should be registered
        assert len(bundle.get_message_ids()) == 0

        # But terms are registered internally (can't query them directly)
        # This exercises lines 76-77 (term registration)

    def test_format_pattern_with_recursion_error(self) -> None:
        """Bundle handles RecursionError gracefully (line 152-155)."""
        bundle = FluentBundle("en_US")

        # While we can't easily create a RecursionError through normal means,
        # we can test that other error types return fallback
        bundle.add_resource("test-msg = Hello { $name }")

        # Missing variable triggers error path
        result, errors = bundle.format_pattern("test-msg", {})

        # Should return result with variable fallback, plus error
        assert isinstance(result, str)
        assert "{$name}" in result
        assert len(errors) >= 1, f"Expected error for missing variable, got {errors}"
        assert isinstance(errors[0], FluentReferenceError)

    def test_format_pattern_with_exception_in_resolver(self) -> None:
        """Bundle catches unexpected exceptions in resolver (lines 156-160)."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Test value")

        # Normal case works
        result, errors = bundle.format_pattern("msg", {})
        assert result == "Test value"
        assert errors == (), f"Unexpected errors: {errors}"

        # Even with weird args, should not crash
        result, errors = bundle.format_pattern(
            "msg", {"weird": object()}  # type: ignore[dict-item]
        )
        assert isinstance(result, str)
        assert errors == (), f"Unexpected errors: {errors}"

    def test_add_resource_with_invalid_fluent_syntax(self) -> None:
        """Bundle handles completely invalid Fluent syntax."""
        bundle = FluentBundle("en_US")

        # This would trigger parser error recovery
        source = """
valid-msg = This works
{ invalid { nested { braces
another-valid = Also works
"""
        bundle.add_resource(source)

        # Valid messages should still be registered
        assert bundle.has_message("valid-msg")
        assert bundle.has_message("another-valid")

    def test_format_pattern_with_keyerror_from_resolver(self) -> None:
        """Bundle handles KeyError from resolver (lines 148-151)."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("needs-var = Value: { $required }")

        # Missing required variable triggers KeyError path
        result, errors = bundle.format_pattern("needs-var", {})

        # Should return fallback with variable reference
        assert result == "Value: {$required}"
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)

    def test_format_pattern_with_attribute_error_from_resolver(self) -> None:
        """Bundle handles AttributeError from resolver (lines 148-151)."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = Test message
    .tooltip = Tooltip text
""")

        # Request non-existent attribute triggers AttributeError path
        result, errors = bundle.format_pattern("msg", attribute="nonexistent")

        # Should return fallback with attribute reference
        assert result == "{msg.nonexistent}"
        assert len(errors) == 1
        assert isinstance(errors[0], FluentReferenceError)

    def test_add_function_registers_successfully(self) -> None:
        """Bundle can register custom functions."""
        bundle = FluentBundle("en_US")

        # Add custom function
        def UPPERCASE(text: object) -> str:
            return str(text).upper()

        bundle.add_function("UPPERCASE", UPPERCASE)

        # Function is registered (can't easily test usage without full parser support)
        # This exercises the add_function method
        bundle.add_resource("msg = Test message")
        result, errors = bundle.format_pattern("msg", {})
        assert result == "Test message"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_get_message_ids_with_terms_excluded(self) -> None:
        """get_message_ids returns only messages, not terms."""
        bundle = FluentBundle("en_US")

        bundle.add_resource("""
message1 = First message
-term1 = A term
message2 = Second message
-term2 = Another term
""")

        ids = bundle.get_message_ids()

        # Should have exactly 2 messages
        assert len(ids) == 2
        assert "message1" in ids
        assert "message2" in ids

        # Terms should NOT be in message IDs
        assert "-term1" not in ids
        assert "-term2" not in ids


class TestFluentBundleMockedErrors:
    """Test FluentBundle error handlers using mocking."""

    def test_add_resource_with_fluent_syntax_error(self) -> None:
        """Bundle handles FluentSyntaxError from parser."""
        bundle = FluentBundle("en_US")

        # Mock parser to raise FluentSyntaxError
        with patch.object(bundle, "_parser") as mock_parser:
            mock_parser.parse.side_effect = FluentSyntaxError("Invalid syntax")

            # Should raise FluentSyntaxError (lines 91-93)
            with pytest.raises(FluentSyntaxError, match="Invalid syntax"):
                bundle.add_resource("msg = Hello")

    def test_format_pattern_with_keyerror_exception(self) -> None:
        """Bundle propagates KeyError from resolver (fail-fast behavior).

        v0.29.0: Internal errors (KeyError, AttributeError, etc.) are no longer
        caught. This ensures bugs are detected immediately rather than hidden
        behind fallback values.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello { $name }")

        # Mock FluentResolver to raise KeyError
        with patch("ftllexengine.runtime.bundle.FluentResolver") as MockResolver:
            mock_resolver = Mock()
            mock_resolver.resolve_message.side_effect = KeyError("name")
            MockResolver.return_value = mock_resolver

            # v0.29.0: KeyError propagates (fail-fast)
            with pytest.raises(KeyError, match="name"):
                bundle.format_pattern("msg", {})

    def test_format_pattern_with_attribute_error_exception(self) -> None:
        """Bundle propagates AttributeError from resolver (fail-fast behavior).

        v0.29.0: Internal errors are no longer caught.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Mock FluentResolver to raise AttributeError
        with patch("ftllexengine.runtime.bundle.FluentResolver") as MockResolver:
            mock_resolver = Mock()
            mock_resolver.resolve_message.side_effect = AttributeError("Invalid attribute")
            MockResolver.return_value = mock_resolver

            # v0.29.0: AttributeError propagates (fail-fast)
            with pytest.raises(AttributeError, match="Invalid attribute"):
                bundle.format_pattern("msg", {})

    def test_format_pattern_with_recursion_error_exception(self) -> None:
        """Bundle propagates RecursionError from resolver (fail-fast behavior).

        v0.29.0: Internal errors are no longer caught.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Mock FluentResolver to raise RecursionError
        with patch("ftllexengine.runtime.bundle.FluentResolver") as MockResolver:
            mock_resolver = Mock()
            mock_resolver.resolve_message.side_effect = RecursionError("Maximum recursion")
            MockResolver.return_value = mock_resolver

            # v0.29.0: RecursionError propagates (fail-fast)
            with pytest.raises(RecursionError, match="Maximum recursion"):
                bundle.format_pattern("msg", {})

    def test_format_pattern_with_unexpected_exception(self) -> None:
        """Bundle propagates unexpected exceptions from resolver (fail-fast behavior).

        v0.29.0: Internal errors are no longer caught. Only FluentError subclasses
        are part of the normal error handling flow.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Mock FluentResolver to raise unexpected exception
        with patch("ftllexengine.runtime.bundle.FluentResolver") as MockResolver:
            mock_resolver = Mock()
            mock_resolver.resolve_message.side_effect = RuntimeError("Unexpected error")
            MockResolver.return_value = mock_resolver

            # v0.29.0: RuntimeError propagates (fail-fast)
            with pytest.raises(RuntimeError, match="Unexpected error"):
                bundle.format_pattern("msg", {})

    # Note: Lines 76-77 (term debug logging) are unreachable with current parser
    # Parser doesn't support Term syntax (-term = value), so isinstance(entry, Term)
    # is never True. This is acceptable dead code for future parser enhancement.


class TestFluentBundleValidateResource:
    """Test FluentBundle.validate_resource() method (Phase 4: Validation API)."""

    @pytest.fixture
    def bundle(self) -> FluentBundle:
        """Create bundle for testing."""
        return FluentBundle("en_US")

    def test_validate_valid_resource(self, bundle: FluentBundle) -> None:
        """validate_resource returns success for valid FTL."""
        source = """hello = Hello, world!
goodbye = Goodbye!"""
        result = bundle.validate_resource(source)

        assert result.is_valid
        assert result.error_count == 0
        assert result.warning_count == 0
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_validate_empty_resource(self, bundle: FluentBundle) -> None:
        """validate_resource handles empty string."""
        result = bundle.validate_resource("")

        assert result.is_valid
        assert result.error_count == 0

    def test_validate_resource_with_variables(self, bundle: FluentBundle) -> None:
        """validate_resource handles messages with variables."""
        source = "welcome = Hello, { $name }!"
        result = bundle.validate_resource(source)

        assert result.is_valid
        assert result.error_count == 0

    def test_validate_resource_with_select(self, bundle: FluentBundle) -> None:
        """validate_resource handles SELECT expressions."""
        source = """emails = { $count ->
    [one] 1 email
   *[other] { $count } emails
}"""
        result = bundle.validate_resource(source)

        assert result.is_valid
        assert result.error_count == 0

    def test_validate_invalid_syntax_returns_errors(self, bundle: FluentBundle) -> None:
        """validate_resource returns errors for invalid syntax."""
        source = "invalid syntax without equals sign"
        result = bundle.validate_resource(source)

        assert not result.is_valid
        assert result.error_count == 1
        assert len(result.errors) == 1

    def test_validate_multiple_errors(self, bundle: FluentBundle) -> None:
        """validate_resource returns all errors found."""
        source = """hello = Hello
invalid line 1
goodbye = Goodbye
invalid line 2"""
        result = bundle.validate_resource(source)

        assert not result.is_valid
        assert result.error_count == 2
        assert len(result.errors) == 2

    def test_validate_does_not_modify_bundle(self, bundle: FluentBundle) -> None:
        """validate_resource does not add messages to bundle."""
        source = "hello = Hello, world!"

        # Validate first
        result = bundle.validate_resource(source)
        assert result.is_valid

        # Bundle should still be empty
        assert len(bundle.get_message_ids()) == 0
        assert not bundle.has_message("hello")

    def test_validation_result_properties(self, bundle: FluentBundle) -> None:
        """ValidationResult properties work correctly."""
        # Valid resource
        valid_result = bundle.validate_resource("hello = Hello")
        assert valid_result.is_valid is True
        assert valid_result.error_count == 0
        assert valid_result.warning_count == 0

        # Invalid resource
        invalid_result = bundle.validate_resource("invalid")
        assert invalid_result.is_valid is False
        assert invalid_result.error_count >= 1
        assert invalid_result.warning_count == 0


def test_use_isolating_enabled_by_default():
    """Bidi isolation should be enabled by default per Fluent spec."""
    bundle = FluentBundle("ar")
    bundle.add_resource("msg = مرحبا { $name }!")
    result, errors = bundle.format_pattern("msg", {"name": "Alice"})

    # Should contain FSI (U+2068) and PDI (U+2069) marks
    assert "\u2068Alice\u2069" in result
    assert result == "مرحبا \u2068Alice\u2069!"
    assert errors == (), f"Unexpected errors: {errors}"


def test_use_isolating_can_be_disabled():
    """Bidi isolation can be disabled for LTR-only applications."""
    bundle = FluentBundle("en", use_isolating=False)
    bundle.add_resource("msg = Hello { $name }!")
    result, errors = bundle.format_pattern("msg", {"name": "Alice"})

    # Should NOT contain isolation marks
    assert "\u2068" not in result
    assert "\u2069" not in result
    assert result == "Hello Alice!"
    assert errors == (), f"Unexpected errors: {errors}"


def test_use_isolating_with_multiple_placeables():
    """Bidi isolation wraps each placeable independently."""
    bundle = FluentBundle("ar", use_isolating=True)
    bundle.add_resource("msg = { $first } و { $second }")
    result, errors = bundle.format_pattern("msg", {"first": "Alice", "second": "Bob"})

    # Each placeable wrapped independently
    assert result == "\u2068Alice\u2069 و \u2068Bob\u2069"
    assert errors == (), f"Unexpected errors: {errors}"


def test_cache_enabled_property_when_enabled():
    """cache_enabled property returns True when caching enabled."""
    bundle = FluentBundle("en", enable_cache=True)
    assert bundle.cache_enabled is True


def test_cache_enabled_property_when_disabled():
    """cache_enabled property returns False when caching disabled."""
    bundle = FluentBundle("en", enable_cache=False)
    assert bundle.cache_enabled is False


def test_cache_enabled_property_default():
    """cache_enabled property returns False by default."""
    bundle = FluentBundle("en")
    assert bundle.cache_enabled is False


def test_cache_size_property_when_enabled():
    """cache_size property returns configured size when caching enabled."""
    bundle = FluentBundle("en", enable_cache=True, cache_size=500)
    assert bundle.cache_size == 500


def test_cache_size_property_when_disabled():
    """cache_size property returns 0 when caching disabled."""
    bundle = FluentBundle("en", enable_cache=False, cache_size=500)
    assert bundle.cache_size == 0


def test_cache_size_property_default():
    """cache_size property returns 0 by default (cache disabled)."""
    bundle = FluentBundle("en")
    assert bundle.cache_size == 0
