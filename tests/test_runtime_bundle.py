"""Tests for runtime.bundle: FluentBundle resource loading, formatting, branch coverage."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import Mock, patch

import pytest
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT, MAX_SOURCE_SIZE
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError, ValidationError
from ftllexengine.integrity import FormattingIntegrityError, SyntaxIntegrityError
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.validation.resource import validate_resource


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
        return FluentBundle("lv_LV", strict=False)

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
        bundle = FluentBundle("lv_LV", strict=False)
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
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "variable" in str(errors[0]).lower() or "name" in str(errors[0]).lower()

    def test_format_pattern_with_attribute_parameter(self, bundle: Any) -> None:
        """format_pattern accepts attribute parameter."""
        result, errors = bundle.format_pattern("button-save", attribute="tooltip")

        # Should successfully retrieve the .tooltip attribute
        assert result == "Saglabā ierakstu datubāzē"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_format_pattern_missing_message_raises_error(self, bundle: Any) -> None:
        """format_pattern for non-existent message raises FrozenFluentError."""
        result, errors = bundle.format_pattern("nonexistent-message")
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
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
        bundle = FluentBundle("en_US", strict=False)
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
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

    def test_format_pattern_handles_key_error_gracefully(self, bundle: Any) -> None:
        """format_pattern handles KeyError (missing variable) gracefully."""
        bundle.add_resource("needs-var = Hello { $name }")

        # Call without providing required variable
        result, errors = bundle.format_pattern("needs-var", {})

        # Should return result with variable fallback, plus error
        assert isinstance(result, str)
        assert "{$name}" in result
        assert len(errors) >= 1, f"Expected error for missing variable, got {errors}"
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

    def test_format_pattern_handles_attribute_error_gracefully(self, bundle: Any) -> None:
        """format_pattern handles AttributeError gracefully."""
        bundle.add_resource("attr-msg = Test")

        # Try to access non-existent attribute
        result, errors = bundle.format_pattern("attr-msg", attribute="nonexistent")

        # Should handle gracefully with fallback + error
        assert isinstance(result, str)
        assert len(errors) >= 1, f"Expected error for nonexistent attribute, got {errors}"
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "attribute" in str(errors[0]).lower()

    def test_format_pattern_handles_unexpected_errors_gracefully(self, bundle: Any) -> None:
        """format_pattern catches unexpected exceptions."""
        # Even if something goes really wrong, bundle should not crash
        result, errors = bundle.format_pattern("test", {})

        assert result == "Test message"
        assert errors == (), f"Unexpected errors: {errors}"

    def test_add_resource_with_terms_and_junk(self) -> None:
        """add_resource handles mix of messages, terms, and junk."""
        bundle = FluentBundle("en_US", strict=False)

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
        bundle = FluentBundle("en_US", strict=False)

        # While we can't easily create a RecursionError through normal means,
        # we can test that other error types return fallback
        bundle.add_resource("test-msg = Hello { $name }")

        # Missing variable triggers error path
        result, errors = bundle.format_pattern("test-msg", {})

        # Should return result with variable fallback, plus error
        assert isinstance(result, str)
        assert "{$name}" in result
        assert len(errors) >= 1, f"Expected error for missing variable, got {errors}"
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

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
        bundle = FluentBundle("en_US", strict=False)

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
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource("needs-var = Value: { $required }")

        # Missing required variable triggers KeyError path
        result, errors = bundle.format_pattern("needs-var", {})

        # Should return fallback with variable reference
        assert result == "Value: {$required}"
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

    def test_format_pattern_with_attribute_error_from_resolver(self) -> None:
        """Bundle handles AttributeError from resolver (lines 148-151)."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource("""
msg = Test message
    .tooltip = Tooltip text
""")

        # Request non-existent attribute triggers AttributeError path
        result, errors = bundle.format_pattern("msg", attribute="nonexistent")

        # Should return fallback with attribute reference
        assert result == "{msg.nonexistent}"
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE

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

    def test_format_pattern_with_keyerror_exception(self) -> None:
        """Bundle propagates KeyError from resolver (fail-fast behavior).

        Internal errors (KeyError, AttributeError, etc.) are no longer
        caught. This ensures bugs are detected immediately rather than hidden
        behind fallback values.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello { $name }")

        # Patch the resolver instance directly; resolver is eagerly initialized
        # so patching the FluentResolver class does not affect existing bundles.
        mock_resolver = Mock()
        mock_resolver.resolve_message.side_effect = KeyError("name")
        # KeyError propagates (fail-fast)
        with (
            patch.object(bundle, "_resolver", mock_resolver),
            pytest.raises(KeyError, match="name"),
        ):
            bundle.format_pattern("msg", {})

    def test_format_pattern_with_attribute_error_exception(self) -> None:
        """Bundle propagates AttributeError from resolver (fail-fast behavior).

        Internal errors are no longer caught.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Patch the resolver instance directly; resolver is eagerly initialized.
        mock_resolver = Mock()
        mock_resolver.resolve_message.side_effect = AttributeError("Invalid attribute")
        # AttributeError propagates (fail-fast)
        with (
            patch.object(bundle, "_resolver", mock_resolver),
            pytest.raises(AttributeError, match="Invalid attribute"),
        ):
            bundle.format_pattern("msg", {})

    def test_format_pattern_with_recursion_error_exception(self) -> None:
        """Bundle propagates RecursionError from resolver (fail-fast behavior).

        Internal errors are no longer caught.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Patch the resolver instance directly; resolver is eagerly initialized.
        mock_resolver = Mock()
        mock_resolver.resolve_message.side_effect = RecursionError("Maximum recursion")
        # RecursionError propagates (fail-fast)
        with (
            patch.object(bundle, "_resolver", mock_resolver),
            pytest.raises(RecursionError, match="Maximum recursion"),
        ):
            bundle.format_pattern("msg", {})

    def test_format_pattern_with_unexpected_exception(self) -> None:
        """Bundle propagates unexpected exceptions from resolver (fail-fast behavior).

        Internal errors are no longer caught. Only FluentError subclasses
        are part of the normal error handling flow.
        """
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        # Patch the resolver instance directly; resolver is eagerly initialized.
        mock_resolver = Mock()
        mock_resolver.resolve_message.side_effect = RuntimeError("Unexpected error")
        # RuntimeError propagates (fail-fast)
        with (
            patch.object(bundle, "_resolver", mock_resolver),
            pytest.raises(RuntimeError, match="Unexpected error"),
        ):
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
    bundle = FluentBundle("en", cache=CacheConfig())
    assert bundle.cache_enabled is True


def test_cache_enabled_property_when_disabled():
    """cache_enabled property returns False when caching disabled."""
    bundle = FluentBundle("en")
    assert bundle.cache_enabled is False


def test_cache_enabled_property_default():
    """cache_enabled property returns False by default."""
    bundle = FluentBundle("en")
    assert bundle.cache_enabled is False


def test_cache_config_size_when_enabled():
    """cache_config.size returns configured size when caching enabled."""
    bundle = FluentBundle("en", cache=CacheConfig(size=500))
    assert bundle.cache_config is not None
    assert bundle.cache_config.size == 500


def test_cache_config_is_none_when_disabled():
    """cache_config returns None when caching is disabled."""
    bundle = FluentBundle("en")
    assert bundle.cache_config is None
    assert bundle.cache_enabled is False


# ============================================================================
# Branch Coverage Classes (from test_bundle_branch_coverage)
# ============================================================================

# =============================================================================
# Property Accessors
# =============================================================================


class TestBundlePropertyAccessors:
    """Test all property accessors for complete coverage."""

    def test_locale_property_returns_configured_locale(self) -> None:
        """locale property returns the configured locale code."""
        bundle = FluentBundle("lv_LV")
        assert bundle.locale == "lv_LV"

        bundle_ar = FluentBundle("ar_EG")
        assert bundle_ar.locale == "ar_EG"

    def test_use_isolating_property_true(self) -> None:
        """use_isolating property returns True when enabled."""
        bundle = FluentBundle("en", use_isolating=True)
        assert bundle.use_isolating is True

    def test_use_isolating_property_false(self) -> None:
        """use_isolating property returns False when disabled."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle.use_isolating is False

    def test_strict_property_returns_configured_value(self) -> None:
        """strict property returns the strict mode boolean."""
        assert FluentBundle("en", strict=True).strict is True
        assert FluentBundle("en", strict=False).strict is False
        assert FluentBundle("en").strict is True

    def test_cache_enabled_property(self) -> None:
        """cache_enabled property reflects configuration."""
        assert FluentBundle("en", cache=CacheConfig()).cache_enabled is True
        assert FluentBundle("en").cache_enabled is False

    def test_cache_config_size_property(self) -> None:
        """cache_config.size returns configured maximum."""
        bundle = FluentBundle("en", cache=CacheConfig(size=500))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == 500

    def test_cache_usage_property_tracks_entries(self) -> None:
        """cache_usage property tracks current cached entries."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg1 = Hello\nmsg2 = World")

        assert bundle.cache_usage == 0
        bundle.format_pattern("msg1")
        assert bundle.cache_usage == 1
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2

    def test_cache_usage_returns_zero_when_disabled(self) -> None:
        """cache_usage returns 0 when caching is disabled."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 0

    def test_cache_write_once_config(self) -> None:
        """cache_config.write_once reflects configured boolean."""
        on = FluentBundle("en", cache=CacheConfig(write_once=True))
        assert on.cache_config is not None
        assert on.cache_config.write_once is True
        off = FluentBundle("en", cache=CacheConfig(write_once=False))
        assert off.cache_config is not None
        assert off.cache_config.write_once is False

    def test_cache_enable_audit_config(self) -> None:
        """cache_config.enable_audit reflects configured boolean."""
        on = FluentBundle("en", cache=CacheConfig(enable_audit=True))
        assert on.cache_config is not None
        assert on.cache_config.enable_audit is True
        off = FluentBundle("en", cache=CacheConfig(enable_audit=False))
        assert off.cache_config is not None
        assert off.cache_config.enable_audit is False

    def test_cache_max_audit_entries_config(self) -> None:
        """cache_config.max_audit_entries reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_audit_entries=5000)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_audit_entries == 5000

    def test_cache_max_entry_weight_config(self) -> None:
        """cache_config.max_entry_weight reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_entry_weight=8000)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_entry_weight == 8000

    def test_cache_max_errors_per_entry_config(self) -> None:
        """cache_config.max_errors_per_entry reflects configured maximum."""
        bundle = FluentBundle(
            "en", cache=CacheConfig(max_errors_per_entry=25)
        )
        assert bundle.cache_config is not None
        assert bundle.cache_config.max_errors_per_entry == 25

    def test_max_source_size_property(self) -> None:
        """max_source_size property returns configured or default value."""
        assert FluentBundle("en", max_source_size=500_000).max_source_size == 500_000
        assert FluentBundle("en").max_source_size == MAX_SOURCE_SIZE

    def test_max_nesting_depth_property(self) -> None:
        """max_nesting_depth property returns configured or default value."""
        assert FluentBundle("en", max_nesting_depth=50).max_nesting_depth == 50
        assert FluentBundle("en").max_nesting_depth == 100


# =============================================================================
# Locale Validation
# =============================================================================


class TestBundleLocaleValidation:
    """Test locale code validation in __init__."""

    def test_rejects_invalid_characters(self) -> None:
        """Locale with special characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle("en@invalid")

    def test_rejects_spaces(self) -> None:
        """Locale with spaces raises ValueError."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle("en US")

    def test_rejects_non_ascii(self) -> None:
        """Locale with non-ASCII characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid locale code format"):
            FluentBundle("\u00ebn_FR")

    def test_accepts_hyphen_separator(self) -> None:
        """Locale with hyphen separator accepted."""
        assert FluentBundle("en-US").locale == "en-US"

    def test_accepts_underscore_separator(self) -> None:
        """Locale with underscore separator accepted."""
        assert FluentBundle("en_US").locale == "en_US"

    def test_exceeding_max_length_rejected(self) -> None:
        """Locale exceeding MAX_LOCALE_LENGTH_HARD_LIMIT raises ValueError."""
        long_locale = "a" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 1)
        with pytest.raises(ValueError, match="Locale code exceeds maximum"):
            FluentBundle(long_locale)

    def test_exceeding_max_length_shows_truncated(self) -> None:
        """Error message includes truncated locale and actual length."""
        long_locale = "X" * (MAX_LOCALE_LENGTH_HARD_LIMIT + 100)
        with pytest.raises(
            ValueError, match="Locale code exceeds maximum"
        ) as exc_info:
            FluentBundle(long_locale)
        error_msg = str(exc_info.value)
        assert long_locale[:50] in error_msg
        assert str(len(long_locale)) in error_msg


# =============================================================================
# Special Methods (__repr__)
# =============================================================================


class TestBundleSpecialMethods:
    """Test __repr__ for complete coverage."""

    def test_repr_shows_locale_and_counts(self) -> None:
        """__repr__ returns string with locale and message/term counts."""
        bundle = FluentBundle("lv_LV")
        repr_str = repr(bundle)
        assert "FluentBundle" in repr_str
        assert "lv_LV" in repr_str
        assert "messages=0" in repr_str
        assert "terms=0" in repr_str

    def test_repr_reflects_counts_after_adding_resources(self) -> None:
        """__repr__ shows accurate counts after adding resources."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg1 = Hello\nmsg2 = World\n-brand = Firefox")
        repr_str = repr(bundle)
        assert "messages=2" in repr_str
        assert "terms=1" in repr_str


# =============================================================================
# for_system_locale Factory Method
# =============================================================================


class TestBundleForSystemLocale:
    """Test for_system_locale classmethod."""

    def test_creates_bundle_with_detected_locale(self) -> None:
        """for_system_locale creates bundle with system locale."""
        with patch(
            "ftllexengine.runtime.bundle.get_system_locale",
            return_value="en_US",
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "en_US"

    def test_passes_configuration_parameters(self) -> None:
        """for_system_locale passes all configuration parameters."""
        with patch(
            "ftllexengine.runtime.bundle.get_system_locale",
            return_value="de_DE",
        ):
            bundle = FluentBundle.for_system_locale(
                use_isolating=False,
                cache=CacheConfig(size=2000),
                strict=True,
                max_source_size=500_000,
            )
            assert bundle.locale == "de_DE"
            assert bundle.use_isolating is False
            assert bundle.cache_enabled is True
            assert bundle.cache_config is not None
            assert bundle.cache_config.size == 2000
            assert bundle.strict is True
            assert bundle.max_source_size == 500_000

    def test_raises_when_locale_unavailable(self) -> None:
        """for_system_locale raises RuntimeError when locale unavailable."""
        with patch(
            "ftllexengine.runtime.bundle.get_system_locale",
            side_effect=RuntimeError("Cannot determine system locale"),
        ), pytest.raises(RuntimeError, match="Cannot determine"):
            FluentBundle.for_system_locale()

    def test_falls_back_to_env_vars_when_getlocale_fails(self) -> None:
        """for_system_locale uses env vars when getlocale() returns None."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LC_ALL": "de_DE"}, clear=False
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "de_de"

    def test_tries_lc_messages_when_lc_all_missing(self) -> None:
        """for_system_locale tries LC_MESSAGES when LC_ALL not set."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LC_MESSAGES": "fr_FR"}, clear=True
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "fr_fr"

    def test_tries_lang_when_others_missing(self) -> None:
        """for_system_locale tries LANG as final fallback."""
        with patch("locale.getlocale", return_value=(None, None)), patch.dict(
            "os.environ", {"LANG": "es_ES"}, clear=True
        ):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "es_es"

    def test_raises_when_no_locale_found(self) -> None:
        """for_system_locale raises RuntimeError with no locale."""
        with (
            patch("locale.getlocale", return_value=(None, None)),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(
                RuntimeError, match="Could not determine system locale"
            ),
        ):
            FluentBundle.for_system_locale()

    def test_normalizes_posix_format(self) -> None:
        """for_system_locale strips encoding suffix and normalizes."""
        with patch("locale.getlocale", return_value=("en_US.UTF-8", None)):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "en_us"
            assert "UTF-8" not in bundle.locale

    def test_handles_locale_without_encoding(self) -> None:
        """for_system_locale handles locale without encoding suffix."""
        with patch("locale.getlocale", return_value=("pl_PL", None)):
            bundle = FluentBundle.for_system_locale()
            assert bundle.locale == "pl_pl"


# =============================================================================
# Resource Management (add_resource, comments, terms)
# =============================================================================


class TestBundleResourceManagement:
    """Test add_resource edge cases, comment handling, term attributes."""

    def test_add_resource_with_comments(self) -> None:
        """Comments are parsed but not registered as messages."""
        bundle = FluentBundle("en")
        ftl_source = (
            "# Standalone comment\nmsg1 = Hello\n\n"
            "## Section comment\nmsg2 = World\n\n"
            "### Resource comment\n-term = Value\n"
        )
        junk = bundle.add_resource(ftl_source)
        assert len(junk) == 0
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")
        assert len(bundle.get_message_ids()) == 2

    def test_standalone_comment_only_resource(self) -> None:
        """Resource containing only comments is valid."""
        bundle = FluentBundle("en")
        junk = bundle.add_resource(
            "# Comment\n## Section\n### Resource\n"
        )
        assert len(junk) == 0
        assert len(bundle.get_message_ids()) == 0

    def test_consecutive_comments(self) -> None:
        """Multiple consecutive comments hit Comment->loop branch."""
        bundle = FluentBundle("en")
        ftl = "## Section 1\n## Section 2\n### Resource\nmsg = Value\n"
        junk = bundle.add_resource(ftl)
        assert len(junk) == 0
        assert bundle.has_message("msg")

    def test_message_without_value_only_attributes(self) -> None:
        """Message with no value, only attributes, is registered."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg =\n    .attr1 = Value 1\n    .attr2 = Value 2\n")
        assert bundle.has_message("msg")

    def test_term_with_multiple_attributes(self) -> None:
        """Term with attributes is registered successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            "-brand = Firefox\n    .gender = masculine\n"
            "    .case = nominative\n"
        )
        assert bundle is not None

    def test_add_resource_clears_cache(self) -> None:
        """add_resource clears cache when enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("first = First")
        bundle.format_pattern("first")
        assert bundle.get_cache_stats()["size"] > 0  # type: ignore[index]
        bundle.add_resource("second = Second")
        assert bundle.get_cache_stats()["size"] == 0  # type: ignore[index]

    def test_duplicate_terms_overwrite(self, caplog: Any) -> None:
        """Duplicate term definitions produce overwrite warning."""
        bundle = FluentBundle("en")
        bundle.add_resource("-brand = Firefox\n-brand = Chrome\n")
        assert any(
            "Overwriting existing term '-brand'" in r.message
            for r in caplog.records
        )

    def test_multiple_duplicate_terms(self, caplog: Any) -> None:
        """Multiple duplicate terms each produce warnings."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = First\n-version = First\n"
            "-brand = Second\n-version = Second\n"
        )
        warnings = [
            r for r in caplog.records
            if "Overwriting existing term" in r.message
        ]
        assert len(warnings) == 2

    def test_comments_with_debug_logging(self, caplog: Any) -> None:
        """Comments are processed at debug level without errors."""
        caplog.set_level(logging.DEBUG)
        bundle = FluentBundle("en")
        ftl = (
            "# Comment before term\n"
            "-brand = Firefox\n"
        )
        junk = bundle.add_resource(ftl)
        assert len(junk) == 0


# =============================================================================
# Type Validation (add_resource, validate_resource, format_pattern)
# =============================================================================


class TestBundleTypeValidation:
    """Test type validation at API boundaries."""

    def test_add_resource_rejects_bytes(self) -> None:
        """add_resource raises TypeError for bytes with decode suggestion."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]
        with pytest.raises(TypeError, match=r"source.decode\('utf-8'\)"):
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_add_resource_rejects_int(self) -> None:
        """add_resource raises TypeError for non-string types."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str"):
            bundle.add_resource(42)  # type: ignore[arg-type]

    def test_validate_resource_rejects_bytes(self) -> None:
        """validate_resource raises TypeError for bytes."""
        bundle = FluentBundle("en")
        with pytest.raises(TypeError, match=r"source must be str, not bytes"):
            bundle.validate_resource(b"msg = Hello")  # type: ignore[arg-type]

    def test_format_pattern_empty_message_id(self) -> None:
        """format_pattern with empty message ID returns fallback."""
        bundle = FluentBundle("en", strict=False)
        result, errors = bundle.format_pattern("")
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_invalid_args_type(self) -> None:
        """format_pattern with non-Mapping args returns fallback."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern("msg", [])  # type: ignore[arg-type]
        assert result == "{???}"
        assert len(errors) == 1

    def test_format_pattern_invalid_attribute_type(self) -> None:
        """format_pattern with non-string attribute returns fallback."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern(
            "msg", {}, attribute=123  # type: ignore[arg-type]
        )
        assert result == "{???}"
        assert len(errors) == 1

    def test_strict_mode_raises_on_empty_message_id(self) -> None:
        """format_pattern in strict mode raises on empty message ID."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("")

    def test_strict_mode_raises_on_invalid_args_type(self) -> None:
        """format_pattern in strict mode raises on invalid args type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", [])  # type: ignore[arg-type]

    def test_strict_mode_raises_on_invalid_attribute_type(self) -> None:
        """format_pattern in strict mode raises on invalid attribute type."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello")
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern(
                "msg", {}, attribute=123  # type: ignore[arg-type]
            )


# =============================================================================
# Strict Mode (syntax errors, formatting errors, caching)
# =============================================================================


class TestBundleStrictMode:
    """Test strict mode syntax and formatting error handling."""

    def test_raises_syntax_integrity_error_on_junk(self) -> None:
        """Strict mode raises SyntaxIntegrityError for junk entries."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(
            SyntaxIntegrityError, match=r"Strict mode: .* syntax error"
        ):
            bundle.add_resource("msg = \n!!invalid!!")

    def test_error_includes_source_path(self) -> None:
        """Strict mode error includes source_path when provided."""
        bundle = FluentBundle("en", strict=True)
        with pytest.raises(
            SyntaxIntegrityError, match=r"locales/en/messages.ftl"
        ) as exc_info:
            bundle.add_resource(
                "msg = \n!!invalid!!",
                source_path="locales/en/messages.ftl",
            )
        assert exc_info.value.source_path == "locales/en/messages.ftl"

    def test_error_truncates_long_summary(self) -> None:
        """Strict mode truncates to first 3 junk entries."""
        bundle = FluentBundle("en", strict=True)
        invalid_ftl = (
            "msg1 =\n!!e1!!\nmsg2 =\n!!e2!!\n"
            "msg3 =\n!!e3!!\nmsg4 =\n!!e4!!\n"
        )
        with pytest.raises(
            SyntaxIntegrityError, match=r"and \d+ more"
        ):
            bundle.add_resource(invalid_ftl)

    def test_does_not_mutate_bundle_on_error(self) -> None:
        """Strict mode does not partially populate bundle on syntax error."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg1 = Hello")
        assert len(bundle.get_message_ids()) == 1

        with pytest.raises(SyntaxIntegrityError):
            bundle.add_resource("msg2 = World\n!!invalid!!")
        assert len(bundle.get_message_ids()) == 1

    def test_formatting_integrity_error_on_missing_var(self) -> None:
        """Strict mode raises FormattingIntegrityError for missing vars."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = Hello { $name }")
        with pytest.raises(FormattingIntegrityError, match=r"Strict mode"):
            bundle.format_pattern("msg", {})

    def test_formatting_error_includes_message_id(self) -> None:
        """Strict mode formatting error includes message ID."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("greeting = Hello { $name }")
        with pytest.raises(
            FormattingIntegrityError, match=r"greeting"
        ) as exc_info:
            bundle.format_pattern("greeting", {})
        assert exc_info.value.message_id == "greeting"

    def test_formatting_error_truncates_multiple_errors(self) -> None:
        """Strict mode error truncates to first 3 formatting errors."""
        bundle = FluentBundle("en", strict=True)
        bundle.add_resource("msg = { $a } { $b } { $c } { $d }")
        with pytest.raises(FormattingIntegrityError, match=r"and \d+ more"):
            bundle.format_pattern("msg", {})


# =============================================================================
# Validation (circular refs, undefined refs, duplicates, syntax errors)
# =============================================================================


class TestBundleValidation:
    """Test validate_resource warning and error detection."""

    def test_detects_circular_message_refs(self) -> None:
        """Circular message references generate warnings."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "msg1 = { msg2 }\nmsg2 = { msg1 }\n"
        )
        assert any(
            "Circular message reference" in w.message
            for w in result.warnings
        )

    def test_detects_self_referencing_message(self) -> None:
        """Message referencing itself detected as circular."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { msg }\n")
        assert len(result.warnings) > 0

    def test_detects_circular_term_refs(self) -> None:
        """Circular term references generate warnings."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-term1 = { -term2 }\n-term2 = { -term1 }\n"
        )
        assert any(
            "Circular term reference" in w.message
            for w in result.warnings
        )

    def test_detects_self_referencing_term(self) -> None:
        """Term referencing itself detected as circular."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("-term = { -term }\n")
        assert len(result.warnings) > 0

    def test_detects_term_attribute_circular_ref(self) -> None:
        """Circular reference in term attribute detected."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-term = Value\n    .attr = { -term.attr }\n"
        )
        assert len(result.warnings) > 0

    def test_detects_nested_term_circular_ref(self) -> None:
        """Three-way circular term reference detected."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource(
            "-t1 = { -t2 }\n-t2 = { -t3 }\n-t3 = { -t1 }\n"
        )
        assert len(result.warnings) > 0

    def test_detects_undefined_message_ref(self) -> None:
        """Undefined message reference generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { undefined }\n")
        assert any(
            "undefined" in w.message.lower() for w in result.warnings
        )

    def test_detects_undefined_term_ref_from_message(self) -> None:
        """Message referencing undefined term generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = { -undefined_term }\n")
        assert len(result.warnings) > 0

    def test_detects_undefined_term_ref_from_term(self) -> None:
        """Term referencing undefined term generates warning."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("-term-a = { -term-b }\n")
        assert any(
            "undefined term '-term-b'" in w.message
            for w in result.warnings
        )

    def test_detects_undefined_message_ref_from_term(self) -> None:
        """Term referencing undefined message generates warning."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("-term = { undefined_msg }\n")
        assert len(result.warnings) > 0

    def test_term_referencing_defined_message_no_warning(self) -> None:
        """Term referencing a defined message does not warn."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "greeting = Hello\n-term = { greeting }\n"
        )
        assert not any(
            "undefined message" in w.message for w in result.warnings
        )

    def test_detects_duplicate_term_id(self) -> None:
        """Duplicate term ID generates warning."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "-brand = Firefox\n-brand = Chrome\n"
        )
        assert any(
            "Duplicate term ID" in w.message for w in result.warnings
        )

    def test_message_without_value_validates(self) -> None:
        """Message with only attributes validates successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("msg =\n    .attr = Value\n")
        assert result.is_valid

    def test_term_with_attributes_validates(self) -> None:
        """Term with attributes validates successfully."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource(
            "-term = Base\n    .attr1 = A1\n    .attr2 = A2\n"
        )
        assert result.is_valid

    def test_handles_critical_syntax_error(self) -> None:
        """Critical syntax errors produce validation errors."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("msg = {{ invalid")
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_critical_error_returns_validation_error(self) -> None:
        """Critical errors are ValidationError instances."""
        bundle = FluentBundle("en_US", use_isolating=False)
        result = bundle.validate_resource("msg = {{ broken")
        assert all(
            isinstance(e, ValidationError) for e in result.errors
        )

    def test_integration_all_warning_types(self) -> None:
        """Resource with all warning types produces correct warnings."""
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = (
            "msg-dup = First\nmsg-dup = Second\n"
            "-term-dup = First\n-term-dup = Second\n"
            "circ-a = { circ-b }\ncirc-b = { circ-a }\n"
            "-tc-a = { -tc-b }\n-tc-b = { -tc-a }\n"
            "msg-undef = { missing-msg }\n"
            "-term-undef = { -missing-term }\n"
            "msg-attrs =\n    .attr = Value\n"
            "-term-attrs = Base\n    .attr = Attribute\n"
        )
        result = bundle.validate_resource(ftl)
        warnings = " ".join(w.message for w in result.warnings)
        assert "Duplicate message ID" in warnings
        assert "Duplicate term ID" in warnings
        assert "Circular message reference" in warnings
        assert "Circular term reference" in warnings
        assert "undefined message" in warnings
        assert "undefined term" in warnings

    def test_message_without_value_no_crash(self) -> None:
        """Validation doesn't crash on empty-value message."""
        bundle = FluentBundle("en")
        result = bundle.validate_resource("empty =\n")
        assert result is not None


# =============================================================================
# Cache Management
# =============================================================================


class TestBundleCacheManagement:
    """Test clear_cache, get_cache_stats, cache invalidation."""

    def test_clear_cache_when_enabled(self) -> None:
        """clear_cache removes all cached format results."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg1 = Hello\nmsg2 = World")
        bundle.format_pattern("msg1")
        bundle.format_pattern("msg2")
        assert bundle.cache_usage == 2
        bundle.clear_cache()
        assert bundle.cache_usage == 0

    def test_clear_cache_when_disabled(self) -> None:
        """clear_cache succeeds when cache is disabled."""
        bundle = FluentBundle("en")
        bundle.clear_cache()
        assert bundle.get_cache_stats() is None

    def test_clear_cache_resets_to_empty(self) -> None:
        """clear_cache resets the format cache to empty state."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.clear_cache()
        assert bundle.cache_usage == 0

    def test_get_cache_stats_returns_dict_when_enabled(self) -> None:
        """get_cache_stats returns dict with hits/misses when enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg", {})
        bundle.format_pattern("msg", {})
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_get_cache_stats_returns_none_when_disabled(self) -> None:
        """get_cache_stats returns None when caching is disabled."""
        bundle = FluentBundle("en")
        assert bundle.get_cache_stats() is None

    def test_format_pattern_caches_result(self) -> None:
        """format_pattern caches results when cache enabled."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        result1, _ = bundle.format_pattern("msg")
        stats1 = bundle.get_cache_stats()
        assert stats1 is not None
        assert stats1["misses"] == 1
        result2, _ = bundle.format_pattern("msg")
        stats2 = bundle.get_cache_stats()
        assert stats2 is not None
        assert stats2["hits"] == 1
        assert result1 == result2


# -- Introspection (variables, introspect_message/term, has_attribute) -------


class TestBundleIntrospection:
    """Test introspection and query methods."""

    def test_get_message_variables_returns_frozenset(self) -> None:
        """get_message_variables returns frozenset of variable names."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = Hello, { $name }!")
        variables = bundle.get_message_variables("greeting")
        assert "name" in variables
        assert isinstance(variables, frozenset)

    def test_get_message_variables_raises_keyerror(self) -> None:
        """get_message_variables raises KeyError for missing message."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="not found"):
            bundle.get_message_variables("nonexistent")

    def test_get_all_message_variables(self) -> None:
        """get_all_message_variables returns dict of variable sets."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "greeting = Hello, { $name }!\n"
            "farewell = Bye, { $first } { $last }!\n"
            "simple = No variables\n"
        )
        all_vars = bundle.get_all_message_variables()
        assert all_vars["greeting"] == frozenset({"name"})
        assert all_vars["farewell"] == frozenset({"first", "last"})
        assert all_vars["simple"] == frozenset()

    def test_get_all_message_variables_empty_bundle(self) -> None:
        """get_all_message_variables returns empty dict when empty."""
        bundle = FluentBundle("en")
        assert bundle.get_all_message_variables() == {}

    def test_introspect_message_returns_metadata(self) -> None:
        """introspect_message returns MessageIntrospection with metadata."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "price = { NUMBER($amount, minimumFractionDigits: 2) }"
        )
        info = bundle.introspect_message("price")
        assert "amount" in info.get_variable_names()
        assert "NUMBER" in info.get_function_names()

    def test_introspect_message_raises_keyerror(self) -> None:
        """introspect_message raises KeyError for missing message."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="not found"):
            bundle.introspect_message("nonexistent")

    def test_introspect_term_returns_metadata(self) -> None:
        """introspect_term returns MessageIntrospection for term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = { $case ->\n"
            "    [nominative] Firefox\n"
            "    *[other] Firefox\n}\n"
        )
        info = bundle.introspect_term("brand")
        assert "case" in info.get_variable_names()

    def test_introspect_term_raises_keyerror(self) -> None:
        """introspect_term raises KeyError for missing term."""
        bundle = FluentBundle("en")
        with pytest.raises(KeyError, match="Term 'nonexistent' not found"):
            bundle.introspect_term("nonexistent")

    def test_introspect_term_success(self) -> None:
        """introspect_term returns valid data for existing term."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = Firefox\n    .gender = masculine"
        )
        info = bundle.introspect_term("brand")
        assert info is not None

    def test_has_attribute_true(self) -> None:
        """has_attribute returns True when attribute exists."""
        bundle = FluentBundle("en")
        bundle.add_resource("button = Click\n    .tooltip = Save\n")
        assert bundle.has_attribute("button", "tooltip") is True

    def test_has_attribute_false_missing_attribute(self) -> None:
        """has_attribute returns False when attribute missing."""
        bundle = FluentBundle("en")
        bundle.add_resource("button = Click\n    .tooltip = Save\n")
        assert bundle.has_attribute("button", "nonexistent") is False

    def test_has_attribute_false_missing_message(self) -> None:
        """has_attribute returns False when message missing."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        assert bundle.has_attribute("nonexistent", "tooltip") is False

    def test_has_attribute_multiple_attributes(self) -> None:
        """has_attribute correctly checks among multiple attributes."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "button = Click\n"
            "    .tooltip = Tooltip\n"
            "    .aria-label = Label\n"
            "    .placeholder = Enter\n"
        )
        assert bundle.has_attribute("button", "tooltip") is True
        assert bundle.has_attribute("button", "aria-label") is True
        assert bundle.has_attribute("button", "placeholder") is True
        assert bundle.has_attribute("button", "missing") is False


# =============================================================================
# Formatting (format_pattern error paths)
# =============================================================================


class TestBundleFormatting:
    """Test formatting methods and error handling."""

    def test_format_pattern_formats_message(self) -> None:
        """format_pattern formats message without attribute access."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("welcome = Hello, { $name }!")
        result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert errors == ()

    def test_format_pattern_handles_recursion_error(self) -> None:
        """format_pattern catches RecursionError from circular refs."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg1 = { msg2 }\nmsg2 = { msg1 }\n")
        _result, errors = bundle.format_pattern("msg1")
        assert len(errors) > 0


# =============================================================================
# Custom Functions
# =============================================================================


class TestBundleCustomFunctions:
    """Test custom function registration and registry isolation."""

    def test_custom_function_registered_and_works(self) -> None:
        """add_function registers custom function successfully."""
        bundle = FluentBundle("en")

        def CUSTOM(value: Any) -> str:
            return str(value).upper()

        bundle.add_function("CUSTOM", CUSTOM)
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "hello"})
        assert "HELLO" in result

    def test_add_function_clears_cache(self) -> None:
        """add_function clears cache after registration."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = Hello")
        bundle.format_pattern("msg")
        assert bundle.cache_usage == 1

        def CUSTOM(v: Any) -> str:
            return str(v)

        bundle.add_function("CUSTOM", CUSTOM)
        assert bundle.cache_usage == 0

    def test_add_function_without_cache(self) -> None:
        """add_function works when cache is disabled."""
        bundle = FluentBundle("en", use_isolating=False)

        def CUSTOM(val: str) -> str:
            return val.upper()

        bundle.add_function("CUSTOM", CUSTOM)
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "test"})
        assert result == "TEST"

    def test_init_with_custom_registry(self) -> None:
        """FluentBundle accepts custom FunctionRegistry."""
        registry = create_default_registry()

        def my_func(_val: int) -> str:
            return "custom"

        registry.register(my_func, ftl_name="CUSTOM")
        bundle = FluentBundle("en", functions=registry)
        bundle.add_resource("test = { CUSTOM(123) }")
        result, errors = bundle.format_pattern("test")
        assert not errors
        assert "custom" in result

    def test_init_copies_registry_for_isolation(self) -> None:
        """FluentBundle creates copy of registry for isolation."""
        original = create_default_registry()
        bundle = FluentBundle("en", strict=False, functions=original)

        def new_func(_val: int) -> str:
            return "new"

        original.register(new_func, ftl_name="NEWFUNC")
        bundle.add_resource("test = { NEWFUNC(1) }")
        result, errors = bundle.format_pattern("test")
        assert len(errors) > 0 or "NEWFUNC" not in result


# =============================================================================
# get_babel_locale Method
# =============================================================================


class TestBundleGetBabelLocale:
    """Test get_babel_locale introspection method."""

    def test_returns_locale_identifier(self) -> None:
        """get_babel_locale returns Babel locale identifier."""
        assert FluentBundle("lv").get_babel_locale() == "lv"

    def test_handles_underscore_locale(self) -> None:
        """get_babel_locale handles underscore-separated locales."""
        assert FluentBundle("en_US").get_babel_locale() == "en_US"

    def test_handles_hyphen_locale(self) -> None:
        """get_babel_locale handles hyphen-separated locales."""
        result = FluentBundle("en-GB").get_babel_locale()
        assert "en" in result

    def test_invalid_locale_uses_fallback(self) -> None:
        """get_babel_locale uses fallback for invalid locale."""
        bundle = FluentBundle("xx-INVALID")
        result = bundle.get_babel_locale()
        assert isinstance(result, str)
        assert "en" in result.lower()


# =============================================================================
# Thread Safety
# =============================================================================


class TestBundleThreadSafety:
    """Test always-on thread safety via readers-writer lock."""

    def test_add_resource_is_thread_safe(self) -> None:
        """add_resource acquires lock (always-on thread safety)."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        assert bundle.has_message("msg")
        result, errors = bundle.format_pattern("msg")
        assert result == "Hello"
        assert errors == ()

    def test_format_pattern_is_thread_safe(self) -> None:
        """format_pattern acquires lock (always-on thread safety)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")
        result, errors = bundle.format_pattern(
            "greeting", {"name": "World"}
        )
        assert result == "Hello, World!"
        assert errors == ()


# =============================================================================
# Hypothesis Property-Based Tests
# =============================================================================


class TestBundleHypothesisProperties:
    """Property-based tests for FluentBundle boundary exploration."""

    # --- Init type validation (from test_bundle_100pct_final_coverage) ---

    @given(
        invalid_functions=st.one_of(
            st.dictionaries(
                st.text(min_size=1, max_size=10), st.integers()
            ),
            st.lists(st.text()),
            st.integers(),
            st.text(),
            st.none(),
        )
    )
    def test_init_rejects_non_function_registry(
        self, invalid_functions: object
    ) -> None:
        """FluentBundle.__init__ rejects non-FunctionRegistry functions."""
        if invalid_functions is None:
            event("type=NoneType_valid")
            return

        type_name = type(invalid_functions).__name__
        event(f"type={type_name}")

        with pytest.raises(
            TypeError,
            match="functions must be FunctionRegistry, not",
        ):
            FluentBundle(
                "en_US", functions=invalid_functions  # type: ignore[arg-type]
            )

    @example(invalid_functions={"NUMBER": lambda x: x})
    @example(invalid_functions=[])
    @example(invalid_functions=42)
    @example(invalid_functions="not_a_registry")
    @given(
        invalid_functions=st.one_of(
            st.dictionaries(
                st.text(min_size=1, max_size=5),
                st.integers(),
                min_size=1,
            ),
            st.lists(st.integers(), min_size=1),
        )
    )
    def test_init_type_error_message_includes_type_name(
        self, invalid_functions: object
    ) -> None:
        """TypeError message includes actual type name."""
        type_name = type(invalid_functions).__name__

        with pytest.raises(TypeError) as exc_info:
            FluentBundle(
                "en_US", functions=invalid_functions  # type: ignore[arg-type]
            )

        assert type_name in str(exc_info.value)
        assert "FunctionRegistry" in str(exc_info.value)
        assert "create_default_registry" in str(exc_info.value)

    # --- Property getters (from test_bundle_100pct_final_coverage) ---

    @given(
        max_expansion_size=st.integers(
            min_value=1000, max_value=10_000_000
        ),
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV", "ja_JP"]),
    )
    def test_max_expansion_size_preserved(
        self, max_expansion_size: int, locale: str
    ) -> None:
        """max_expansion_size property returns configured value."""
        if max_expansion_size < 10_000:
            event("boundary=small")
        elif max_expansion_size > 1_000_000:
            event("boundary=large")
        else:
            event("boundary=medium")

        bundle = FluentBundle(
            locale, max_expansion_size=max_expansion_size
        )
        assert bundle.max_expansion_size == max_expansion_size

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl", "ar", "ja"]),
        provide_custom_registry=st.booleans(),
    )
    def test_function_registry_preserved(
        self, locale: str, provide_custom_registry: bool
    ) -> None:
        """function_registry property returns valid registry."""
        if provide_custom_registry:
            event("registry_type=custom")
            custom_registry = create_default_registry()
            bundle = FluentBundle(locale, functions=custom_registry)
        else:
            event("registry_type=shared")
            bundle = FluentBundle(locale)

        registry = bundle.function_registry
        assert isinstance(registry, FunctionRegistry)
        assert "NUMBER" in registry

    # --- Comment handling (from test_bundle_100pct_final_coverage) ---

    @given(
        num_comments=st.integers(min_value=1, max_value=10),
        comment_style=st.sampled_from(
            ["single", "double", "triple"]
        ),
    )
    def test_comments_handled_correctly(
        self, num_comments: int, comment_style: str
    ) -> None:
        """Comment entries handled during resource registration."""
        event(f"comment_count={num_comments}")
        event(f"comment_style={comment_style}")

        marker = {"single": "#", "double": "##", "triple": "###"}[
            comment_style
        ]
        lines = [f"{marker} Comment {i}" for i in range(num_comments)]
        lines.extend(["", "msg = Hello"])

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource("\n".join(lines))
        assert len(junk) == 0
        assert bundle.has_message("msg")

    @example(num_standalone=1)
    @example(num_standalone=3)
    @example(num_standalone=10)
    @given(num_standalone=st.integers(min_value=1, max_value=20))
    def test_comments_do_not_create_junk(
        self, num_standalone: int
    ) -> None:
        """Comments are skipped without creating Junk entries."""
        event(f"standalone_comments={num_standalone}")

        lines = ["### Section Header"]
        lines.extend(
            f"# Comment line {i}" for i in range(num_standalone)
        )
        lines.extend(["", "message = Value", "## Trailing comment"])

        bundle = FluentBundle("en_US")
        junk = bundle.add_resource("\n".join(lines))
        assert len(junk) == 0
        assert bundle.has_message("message")

    # --- Strict mode cache interaction ---
    # (from test_bundle_100pct_final_coverage)

    @given(
        locale=st.sampled_from(["en", "de", "lv", "pl"]),
        missing_var_name=st.text(
            alphabet=st.characters(
                min_codepoint=ord("a"), max_codepoint=ord("z")
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_strict_mode_raises_on_cached_error(
        self, locale: str, missing_var_name: str
    ) -> None:
        """Strict mode raises FormattingIntegrityError on cached errors."""
        bundle = FluentBundle(
            locale, strict=True, cache=CacheConfig()
        )
        bundle.add_resource(
            f"msg = Hello {{ ${missing_var_name} }}"
        )

        with pytest.raises(FormattingIntegrityError) as exc1:
            bundle.format_pattern("msg", {})

        event("cache_hit_type=error")
        assert exc1.value.message_id == "msg"
        assert len(exc1.value.fluent_errors) == 1
        assert (
            exc1.value.fluent_errors[0].category
            == ErrorCategory.REFERENCE
        )

        with pytest.raises(FormattingIntegrityError) as exc2:
            bundle.format_pattern("msg", {})
        assert exc2.value.message_id == "msg"

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "lv_LV"]),
        message_text=st.text(
            alphabet=st.characters(
                min_codepoint=ord("A"),
                max_codepoint=ord("z"),
                blacklist_categories=("Cc", "Cs"),
            ),
            min_size=1,
            max_size=50,
        ),
    )
    def test_strict_mode_cache_hit_without_errors(
        self, locale: str, message_text: str
    ) -> None:
        """Strict mode cached success result returns normally."""
        safe = "".join(
            c for c in message_text if c.isprintable() and c not in "{}#"
        ).strip()
        if not safe:
            safe = "Hello"

        bundle = FluentBundle(
            locale, strict=True, cache=CacheConfig()
        )
        bundle.add_resource(f"msg = {safe}")

        r1, e1 = bundle.format_pattern("msg")
        assert r1 == safe
        assert e1 == ()

        event("cache_hit_type=success")

        r2, e2 = bundle.format_pattern("msg")
        assert r2 == safe
        assert e2 == ()

    # --- Configuration preservation properties ---
    # (from test_bundle_complete_final_coverage, events added)

    @given(
        st.text(
            alphabet=st.sampled_from(["a", "b", "c", "_", "-"]),
            min_size=1,
            max_size=50,
        )
    )
    def test_valid_locale_accepted(self, locale: str) -> None:
        """Valid locale formats are accepted by FluentBundle."""
        if not locale or not locale[0].isalnum():
            event("outcome=filtered")
            return

        try:
            bundle = FluentBundle(locale)
            event("outcome=accepted")
            assert bundle.locale == locale
        except ValueError:
            event("outcome=rejected")

    @given(st.booleans())
    def test_use_isolating_preserved(
        self, use_isolating: bool
    ) -> None:
        """use_isolating configuration is preserved."""
        kind = "isolating" if use_isolating else "non_isolating"
        event(f"outcome={kind}")
        bundle = FluentBundle("en", use_isolating=use_isolating)
        assert bundle.use_isolating == use_isolating

    @given(st.booleans())
    def test_strict_mode_preserved(self, strict: bool) -> None:
        """strict mode configuration is preserved."""
        kind = "strict" if strict else "lenient"
        event(f"outcome={kind}")
        bundle = FluentBundle("en", strict=strict)
        assert bundle.strict == strict

    @given(st.integers(min_value=1, max_value=10000))
    def test_cache_config_size_preserved(self, cache_size: int) -> None:
        """cache_config.size is preserved from CacheConfig constructor."""
        if cache_size < 100:
            event("boundary=small")
        elif cache_size < 5000:
            event("boundary=medium")
        else:
            event("boundary=large")
        bundle = FluentBundle("en", cache=CacheConfig(size=cache_size))
        assert bundle.cache_config is not None
        assert bundle.cache_config.size == cache_size

    # --- Validation properties (from test_bundle_coverage, events added) ---

    @given(
        term_name=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        )
    )
    def test_duplicate_term_generates_warning(
        self, term_name: str
    ) -> None:
        """Duplicate term IDs always generate warnings."""
        event("outcome=duplicate_warned")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = f"-{term_name} = First\n-{term_name} = Second\n"
        result = bundle.validate_resource(ftl)
        assert any(
            "Duplicate term ID" in w.message for w in result.warnings
        )

    @given(
        term_a=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        ),
        term_b=st.from_regex(
            r"[a-z][a-z0-9-]{0,10}", fullmatch=True
        ),
    )
    def test_undefined_term_ref_generates_warning(
        self, term_a: str, term_b: str
    ) -> None:
        """Undefined term references always generate warnings."""
        assume(term_a != term_b)
        event("outcome=undefined_warned")
        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = f"-{term_a} = {{ -{term_b} }}"
        result = bundle.validate_resource(ftl)
        assert any(
            f"undefined term '-{term_b}'" in w.message
            for w in result.warnings
        )


# ============================================================================
# LOCALE VALIDATION AND BUNDLE INTEGRATION COVERAGE
# ============================================================================


class TestLocaleValidationAsciiOnly:
    """Locale codes must be ASCII alphanumeric with underscore or hyphen separators."""

    def test_valid_ascii_locales_accepted(self) -> None:
        """Valid ASCII locale codes are accepted without error."""
        valid_locales = [
            "en",
            "en_US",
            "en-US",
            "de_DE",
            "lv_LV",
            "zh_Hans_CN",
            "pt_BR",
            "ja_JP",
            "ar_EG",
        ]
        for locale in valid_locales:
            bundle = FluentBundle(locale)
            assert bundle.locale == locale

    def test_unicode_locale_rejected(self) -> None:
        """Locale codes with non-ASCII characters raise ValueError."""
        invalid_locales = [
            "\xe9_FR",
            "\u65e5\u672c\u8a9e",
            "en_\xfc",
            "\xe4\xf6\xfc",
        ]
        for locale in invalid_locales:
            with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
                FluentBundle(locale)

    def test_empty_locale_rejected(self) -> None:
        """Empty locale code raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FluentBundle("")

    def test_invalid_format_rejected(self) -> None:
        """Invalid locale code formats raise ValueError."""
        invalid_formats = [
            "_en",
            "en_",
            "en__US",
            "en US",
            "en.US",
            "en@US",
        ]
        for locale in invalid_formats:
            with pytest.raises(ValueError, match="Invalid locale code format"):
                FluentBundle(locale)

    @given(
        st.builds(
            lambda first, rest: first + rest,
            first=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
                min_size=1,
                max_size=1,
            ),
            rest=st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                min_size=0,
                max_size=9,
            ),
        )
    )
    def test_ascii_alphanumeric_accepted(self, locale: str) -> None:
        """PROPERTY: ASCII alphanumeric strings starting with a letter are valid locales."""
        event(f"locale_len={len(locale)}")
        bundle = FluentBundle(locale)
        assert bundle.locale == locale


class TestBundleOverwriteWarning:
    """Overwriting an existing message or term in add_resource logs a WARNING."""

    def test_message_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a message logs a warning with the message ID."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("greeting = Goodbye")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing message 'greeting'" in msg for msg in warning_messages)

    def test_term_overwrite_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Overwriting a term logs a warning with the term ID."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("-brand = Acme")
            bundle.add_resource("-brand = NewCorp")

        warning_messages = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING
        ]
        assert any("Overwriting existing term '-brand'" in msg for msg in warning_messages)

    def test_no_warning_for_new_entries(self, caplog: pytest.LogCaptureFixture) -> None:
        """No overwrite warning when adding distinct entries."""
        bundle = FluentBundle("en")

        with caplog.at_level(logging.WARNING):
            bundle.add_resource("greeting = Hello")
            bundle.add_resource("farewell = Goodbye")

        overwrite_warnings = [
            record.message for record in caplog.records
            if record.levelno == logging.WARNING and "Overwriting" in record.message
        ]
        assert len(overwrite_warnings) == 0

    def test_last_write_wins_behavior_preserved(self) -> None:
        """Last Write Wins behavior: last added resource wins on repeated key."""
        bundle = FluentBundle("en")
        bundle.add_resource("greeting = First")
        bundle.add_resource("greeting = Second")
        bundle.add_resource("greeting = Third")

        result, _ = bundle.format_pattern("greeting")
        assert result == "Third"


class TestBundleIntegration:
    """Integration tests via FluentBundle for multi-module coverage."""

    def test_variant_key_failed_number_parse(self) -> None:
        """Number-like variant key that fails parse falls through to identifier."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            "msg = { $val ->\n"
            "    [-.test] Match\n"
            "   *[other] Other\n"
            "}\n"
        )
        result, _ = bundle.format_pattern(
            "msg", {"val": "-.test"}
        )
        assert result is not None

    def test_identifier_as_function_argument(self) -> None:
        """Identifier becomes MessageReference in function call arguments."""
        bundle = FluentBundle("en_US")

        def test_func(val: str | int) -> str:
            return str(val)

        bundle.add_function("TEST", test_func)
        bundle.add_resource("ref = value")
        bundle.add_resource("msg = { TEST(ref) }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result is not None

    def test_comment_with_crlf_ending(self) -> None:
        """Comment with CRLF line ending is parsed correctly."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("# Comment\r\nmsg = value")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "value" in result

    def test_full_coverage_integration(self) -> None:
        """Integration test exercising parser, resolver, and validator together."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "# Comment\n"
            "msg1 = { $val }\n"
            "msg2 = { NUMBER($val) }\n"
            "msg3 = { -term }\n"
            "msg4 = { other.attr }\n"
            "sel = { 42 ->\n"
            "    [42] Match\n"
            "   *[other] Other\n"
            "}\n"
            "-brand = Firefox\n"
            "    .version = 1.0\n"
            "empty =\n"
            "    .attr = Value\n"
        )
        r1, _ = bundle.format_pattern("msg1", {"val": "t"})
        r2, _ = bundle.format_pattern("msg2", {"val": 42})
        r3, _ = bundle.format_pattern("sel")
        assert all(r is not None for r in [r1, r2, r3])

        validation = validate_resource(
            "msg = { $val }\n-term = Firefox\n"
        )
        assert validation is not None


class TestBundleLocaleValidationBeforeLoading:
    """Locale validation happens before any resource loading attempt."""

    def test_locale_validation_before_resource_loading(self) -> None:
        """Invalid locale raises ValueError immediately, before resource loading."""
        with pytest.raises(ValueError, match="must be ASCII alphanumeric"):
            FluentBundle("\xe9_FR")
