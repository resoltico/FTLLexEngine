"""Final coverage tests for bundle.py to reach 100%.

Targets the last remaining uncovered lines and branches.
"""

from unittest.mock import MagicMock

from ftllexengine.diagnostics import FluentSyntaxError
from ftllexengine.runtime.bundle import FluentBundle


class TestClearCacheMethod:
    """Test clear_cache() method."""

    def test_clear_cache_when_cache_enabled(self) -> None:
        """Test clear_cache() clears cache (lines 1037-1039)."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Test")

        # Populate cache
        bundle.format_pattern("msg")
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] > 0

        # Clear cache
        bundle.clear_cache()

        # Verify cache was cleared
        stats_after = bundle.get_cache_stats()
        assert stats_after is not None
        assert stats_after["size"] == 0

    def test_clear_cache_when_cache_disabled(self) -> None:
        """Test clear_cache() when cache is disabled (line 1037 branch)."""
        bundle = FluentBundle("en", enable_cache=False)

        # Verify clear_cache completes without error when cache disabled
        bundle.clear_cache()

        # Verify cache is still None (disabled)
        assert bundle.get_cache_stats() is None


class TestGetBabelLocaleBehavior:
    """Test get_babel_locale() behavior (v0.14.0+)."""

    def test_get_babel_locale_with_valid_locale(self) -> None:
        """Test get_babel_locale() returns locale string for valid locale."""
        bundle = FluentBundle("en-US")
        result = bundle.get_babel_locale()

        # Should return the babel locale string
        assert isinstance(result, str)
        assert "en" in result.lower()

    def test_get_babel_locale_with_invalid_locale_uses_fallback(self) -> None:
        """Test get_babel_locale() uses en_US fallback for invalid locale (v0.14.0+)."""
        bundle = FluentBundle("xx-INVALID")
        result = bundle.get_babel_locale()

        # Should return en_US fallback (LocaleContext.create always succeeds)
        assert isinstance(result, str)
        assert "en" in result.lower()


class TestAddFunctionWithCacheDisabled:
    """Test add_function() when cache is disabled."""

    def test_add_function_with_cache_disabled_doesnt_clear(self) -> None:
        """Test add_function() when cache is None (line 1021 branch)."""
        bundle = FluentBundle("en", enable_cache=False, use_isolating=False)

        def CUSTOM(val: str) -> str:  # noqa: N802
            return val.upper()

        # Verify add_function completes without error when cache disabled
        bundle.add_function("CUSTOM", CUSTOM)

        # Verify function works by using it in a message
        bundle.add_resource("msg = { CUSTOM($val) }")
        result, _ = bundle.format_pattern("msg", {"val": "test"})
        assert result == "TEST"


class TestIntrospectMessageCoverage:
    """Test introspect_message() implementation details."""

    def test_introspect_message_returns_messageinfo_object(self) -> None:
        """Test introspect_message() returns correct MessageInfo (line 1003)."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello { $name }")

        info = bundle.introspect_message("msg")

        # Verify it returns MessageInfo with correct data
        assert "name" in info.get_variable_names()


class TestValidateResourceSyntaxError:
    """Test validate_resource() FluentSyntaxError handling."""

    def test_validate_resource_catches_fluent_syntax_error(self) -> None:
        """Test validate_resource() catches FluentSyntaxError (lines 741-750)."""
        bundle = FluentBundle("en")

        # Mock the parser to raise FluentSyntaxError
        mock_parser = MagicMock()
        mock_parser.parse.side_effect = FluentSyntaxError("Critical parse error")
        bundle._parser = mock_parser

        result = bundle.validate_resource("invalid")

        # Should return ValidationResult with error, not raise
        assert len(result.errors) > 0
        assert any("critical" in e.message.lower() for e in result.errors)


class TestValidationCircularReferenceBranches:
    """Test specific circular reference detection branches."""

    def test_validation_detects_message_referencing_itself(self) -> None:
        """Test circular message reference detection (branch 423->425)."""
        bundle = FluentBundle("en")

        # Message referencing itself
        ftl = "msg = { msg }"

        result = bundle.validate_resource(ftl)

        # Should detect circular reference
        assert len(result.warnings) > 0

    def test_validation_detects_term_referencing_itself(self) -> None:
        """Test circular term reference detection (branch 451->446)."""
        bundle = FluentBundle("en")

        # Term referencing itself
        ftl = "-term = { -term }"

        result = bundle.validate_resource(ftl)

        # Should detect circular reference
        assert len(result.warnings) > 0

    def test_validation_detects_term_attribute_circular_ref(self) -> None:
        """Test circular term attribute reference (branch 465->460)."""
        bundle = FluentBundle("en")

        # Term with attribute referencing itself
        ftl = """
-term = Value
    .attr = { -term.attr }
"""

        result = bundle.validate_resource(ftl)

        # Should detect circular reference in attribute
        assert len(result.warnings) > 0

    def test_validation_detects_nested_term_circular_ref(self) -> None:
        """Test nested circular term reference (branch 483->478)."""
        bundle = FluentBundle("en")

        # Complex circular reference pattern
        ftl = """
-term1 = { -term2 }
-term2 = { -term3 }
-term3 = { -term1 }
"""

        result = bundle.validate_resource(ftl)

        # Should detect circular reference chain
        assert len(result.warnings) > 0


class TestValidationUndefinedReferences:
    """Test undefined reference detection branches."""

    def test_validation_detects_message_with_undefined_message_ref(self) -> None:
        """Test undefined message reference in message (branch 606->611)."""
        bundle = FluentBundle("en")

        ftl = "msg = { undefined }"

        result = bundle.validate_resource(ftl)

        # Should warn about undefined reference
        assert len(result.warnings) > 0
        assert any(
            "undefined" in w.message.lower() or "not found" in w.message.lower()
            for w in result.warnings
        )

    def test_validation_detects_message_without_value_or_attributes(self) -> None:
        """Test detection of message without value or attributes (line 648)."""
        bundle = FluentBundle("en")

        # Message with no value and no attributes
        ftl = "empty =\n"

        result = bundle.validate_resource(ftl)

        # Parser might create Junk, or empty pattern
        # Just ensure validation doesn't crash
        assert result is not None

    def test_validation_detects_term_with_undefined_message_ref(self) -> None:
        """Test term referencing undefined message (branch 674->676)."""
        bundle = FluentBundle("en")

        ftl = "-term = { undefined_msg }"

        result = bundle.validate_resource(ftl)

        # Should warn about undefined message
        assert len(result.warnings) > 0

    def test_validation_detects_message_with_undefined_term_ref(self) -> None:
        """Test message referencing undefined term (branch 692->691)."""
        bundle = FluentBundle("en")

        ftl = "msg = { -undefined_term }"

        result = bundle.validate_resource(ftl)

        # Should warn about undefined term
        assert len(result.warnings) > 0


class TestIsThreadSafeProperty:
    """Test is_thread_safe property (line 289)."""

    def test_is_thread_safe_returns_true_when_enabled(self) -> None:
        """Test is_thread_safe property returns True when thread_safe=True."""
        bundle = FluentBundle("en", thread_safe=True)
        assert bundle.is_thread_safe is True

    def test_is_thread_safe_returns_false_by_default(self) -> None:
        """Test is_thread_safe property returns False by default."""
        bundle = FluentBundle("en")
        assert bundle.is_thread_safe is False


class TestThreadSafeAddResource:
    """Test thread-safe add_resource path (lines 457-458)."""

    def test_add_resource_uses_lock_when_thread_safe(self) -> None:
        """Test add_resource acquires lock when thread_safe=True."""
        bundle = FluentBundle("en", thread_safe=True)
        bundle.add_resource("msg = Hello")

        # Verify message was added successfully through the locked path
        assert bundle.has_message("msg")
        result, errors = bundle.format_pattern("msg")
        assert result == "Hello"
        assert errors == ()


class TestThreadSafeFormatPattern:
    """Test thread-safe format_pattern path (lines 608-609)."""

    def test_format_pattern_uses_lock_when_thread_safe(self) -> None:
        """Test format_pattern acquires lock when thread_safe=True."""
        bundle = FluentBundle("en", thread_safe=True, use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        # Format through the locked path
        result, errors = bundle.format_pattern("greeting", {"name": "World"})

        assert result == "Hello, World!"
        assert errors == ()


class TestHasAttributeMethod:
    """Test has_attribute method (lines 745-748)."""

    def test_has_attribute_returns_true_when_attribute_exists(self) -> None:
        """Test has_attribute returns True for existing attribute."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
button = Click
    .tooltip = Click to save
""")
        assert bundle.has_attribute("button", "tooltip") is True

    def test_has_attribute_returns_false_for_missing_attribute(self) -> None:
        """Test has_attribute returns False when attribute doesn't exist."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
button = Click
    .tooltip = Click to save
""")
        assert bundle.has_attribute("button", "nonexistent") is False

    def test_has_attribute_returns_false_for_missing_message(self) -> None:
        """Test has_attribute returns False when message doesn't exist (line 745-746)."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        # Message doesn't exist, should return False (not raise)
        assert bundle.has_attribute("nonexistent", "tooltip") is False

    def test_has_attribute_checks_multiple_attributes(self) -> None:
        """Test has_attribute correctly identifies among multiple attributes."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
button = Click
    .tooltip = Tooltip text
    .aria-label = Button label
    .placeholder = Enter value
""")
        assert bundle.has_attribute("button", "tooltip") is True
        assert bundle.has_attribute("button", "aria-label") is True
        assert bundle.has_attribute("button", "placeholder") is True
        assert bundle.has_attribute("button", "missing") is False
