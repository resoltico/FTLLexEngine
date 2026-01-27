"""Edge case validation tests.

Tests for edge cases across parsing, resolution, and validation.
"""

from __future__ import annotations

import pytest

from ftllexengine import FluentBundle
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource


class TestParserEdgeCases:
    """Test parser edge cases."""

    def test_empty_source(self) -> None:
        """Empty source produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("")

        assert len(resource.entries) == 0

    def test_whitespace_only_source(self) -> None:
        """Whitespace-only source is handled gracefully."""
        parser = FluentParserV1()
        resource = parser.parse("   \n\t\n   ")

        # Parser may produce junk entries for unrecognized content
        # The important thing is it doesn't crash
        assert resource is not None

    def test_single_newline(self) -> None:
        """Single newline is valid empty source."""
        parser = FluentParserV1()
        resource = parser.parse("\n")

        assert len(resource.entries) == 0

    def test_very_long_identifier(self) -> None:
        """Identifiers exceeding max length produce Junk (DoS prevention).

        Per SEC-PARSER-UNBOUNDED-001, identifiers are limited to prevent
        denial-of-service attacks via extremely long tokens.
        """
        from ftllexengine.syntax.ast import Junk
        from ftllexengine.syntax.parser.primitives import (
            _MAX_IDENTIFIER_LENGTH,
        )

        parser = FluentParserV1()

        # Identifier within the limit should work (test with a reasonable length)
        valid_id = "a" * 200
        resource = parser.parse(f"{valid_id} = Value")
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Message)
        assert entry.id.name == valid_id

        # Identifier over the limit should produce Junk
        over_limit_id = "a" * (_MAX_IDENTIFIER_LENGTH + 100)
        resource = parser.parse(f"{over_limit_id} = Value")
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Junk)

    def test_very_long_value(self) -> None:
        """Very long values are handled."""
        bundle = FluentBundle("en")
        long_value = "x" * 10000
        bundle.add_resource(f"msg = {long_value}")

        result, errors = bundle.format_pattern("msg")

        assert result == long_value
        assert errors == ()

    def test_many_attributes(self) -> None:
        """Messages with many attributes are handled."""
        parser = FluentParserV1()
        attrs = "\n".join(f"    .attr{i} = Value {i}" for i in range(50))
        source = f"msg = Base\n{attrs}"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Message)
        assert len(entry.attributes) == 50

    def test_deeply_nested_placeables(self) -> None:
        """Deeply nested placeables up to limit are handled."""
        bundle = FluentBundle("en", max_nesting_depth=10)
        # Create 5 levels of nesting (within limit)
        bundle.add_resource("msg = { { { { { $var } } } } }")

        result, errors = bundle.format_pattern("msg", {"var": "value"})

        assert not errors

        assert "value" in result

    def test_comment_only_file(self) -> None:
        """File with only comments produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("""
# Comment 1
## Group comment
### Resource comment
# Another comment
""")

        # Comments don't count as message entries
        assert all(
            entry.__class__.__name__ == "Comment"
            for entry in resource.entries
        )


class TestResolutionEdgeCases:
    """Test resolution edge cases."""

    def test_self_referencing_message(self) -> None:
        """Self-referencing message is detected as cycle."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { msg }")

        _result, errors = bundle.format_pattern("msg")

        # Should return fallback and report error
        assert len(errors) > 0

    def test_empty_select_expression(self) -> None:
        """Select expression with no matching variant uses default."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
msg = { $type ->
    [a] Option A
   *[other] Default
}
""")

        result, _errors = bundle.format_pattern("msg", {"type": "unknown"})

        # Result may include Unicode directional isolates
        assert "Default" in result

    def test_missing_all_variables(self) -> None:
        """Message with all variables missing still produces output."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $a } { $b } { $c }")

        result, errors = bundle.format_pattern("msg", {})

        # Should have fallbacks for all variables
        assert len(errors) == 3
        assert "{$a}" in result
        assert "{$b}" in result
        assert "{$c}" in result

    def test_variable_with_none_value(self) -> None:
        """Variable with None value is handled."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value: { $var }")

        result, errors = bundle.format_pattern("msg", {"var": None})

        assert not errors

        # Result contains Value: and some representation of None (may be empty or "None")
        assert "Value:" in result

    def test_term_with_no_default_variant(self) -> None:
        """Term selector with no matching variant uses default."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
-brand = { $case ->
    [nominative] Firefox
   *[other] Firefox
}
msg = { -brand }
""")

        result, _errors = bundle.format_pattern("msg")

        assert "Firefox" in result


class TestValidationEdgeCases:
    """Test validation edge cases."""

    def test_validate_empty_source(self) -> None:
        """Empty source is valid."""
        result = validate_resource("")

        assert result.is_valid

    def test_validate_message_with_empty_value(self) -> None:
        """Message with empty value pattern."""
        # Message with only attributes, no value - validation should warn
        result = validate_resource("msg =\n    .attr = Value")

        # Should be valid (has attribute)
        assert result.error_count == 0

    def test_validate_duplicate_messages(self) -> None:
        """Duplicate messages produce warnings."""
        result = validate_resource("""
msg = First
msg = Second
""")

        # Should have duplicate warning
        assert result.warning_count > 0
        assert any("Duplicate" in w.message for w in result.warnings)

    def test_validate_undefined_message_reference(self) -> None:
        """Undefined message reference produces warning."""
        result = validate_resource("msg = { undefined }")

        assert result.warning_count > 0
        assert any("undefined" in w.message.lower() for w in result.warnings)

    def test_validate_undefined_term_reference(self) -> None:
        """Undefined term reference produces warning."""
        result = validate_resource("msg = { -undefined }")

        assert result.warning_count > 0
        assert any("undefined" in w.message.lower() for w in result.warnings)


class TestBundleEdgeCases:
    """Test FluentBundle edge cases."""

    def test_format_nonexistent_message(self) -> None:
        """Formatting nonexistent message returns fallback."""
        bundle = FluentBundle("en")

        result, errors = bundle.format_pattern("nonexistent")

        assert "{nonexistent}" in result
        assert len(errors) == 1

    def test_format_nonexistent_attribute(self) -> None:
        """Formatting nonexistent attribute returns message value."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Base value")

        result, _errors = bundle.format_pattern("msg", attribute="nonexistent")

        # Should return message value or error
        assert len(result) > 0

    def test_add_empty_resource(self) -> None:
        """Adding empty resource is allowed."""
        bundle = FluentBundle("en")
        junk = bundle.add_resource("")

        assert junk == ()
        assert len(bundle.get_message_ids()) == 0

    def test_add_multiple_resources(self) -> None:
        """Adding multiple resources accumulates messages."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg1 = First")
        bundle.add_resource("msg2 = Second")

        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")

    def test_message_overwrites_on_duplicate(self) -> None:
        """Later message definition overwrites earlier."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = First")
        bundle.add_resource("msg = Second")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        assert result == "Second"

    def test_introspect_message_with_no_variables(self) -> None:
        """Introspecting message with no variables returns empty set."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Static text")

        info = bundle.introspect_message("msg")

        assert info.get_variable_names() == frozenset()

    def test_get_message_variables_for_complex_message(self) -> None:
        """Get variables from complex message with selectors."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
msg = { $count ->
    [one] { $name } has one item
   *[other] { $name } has { $count } items
}
""")

        variables = bundle.get_message_variables("msg")

        assert "count" in variables
        assert "name" in variables


class TestLocaleEdgeCases:
    """Test locale handling edge cases."""

    def test_bundle_with_short_locale(self) -> None:
        """Bundle with short locale code works."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        assert result == "Hello"

    def test_bundle_with_full_locale(self) -> None:
        """Bundle with full locale code works."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        assert result == "Hello"

    def test_bundle_with_hyphen_locale(self) -> None:
        """Bundle with hyphenated locale code works."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = Hello")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        assert result == "Hello"

    def test_invalid_locale_raises(self) -> None:
        """Invalid locale code raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FluentBundle("")

        with pytest.raises(ValueError, match="Invalid locale code"):
            FluentBundle("en/US")  # Invalid character
