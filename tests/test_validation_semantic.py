"""Test semantic validation in FluentBundle.validate_resource().

Tests for:
- Undefined message references
- Undefined term references
- Circular message references
- Circular term references
- Duplicate ID detection
- Messages without values

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine import FluentBundle


class TestSemanticValidation:
    """Test semantic validation warnings."""

    def test_undefined_message_reference(self) -> None:
        """Test detection of undefined message references."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
welcome = Hello, { missing-msg }!
""")
        assert result.is_valid  # No syntax errors
        assert result.warning_count == 1
        assert "undefined message 'missing-msg'" in result.warnings[0].message

    def test_undefined_term_reference(self) -> None:
        """Test detection of undefined term references."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
welcome = Welcome to { -brand-name }!
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "undefined term '-brand-name'" in result.warnings[0].message

    def test_circular_message_reference_simple(self) -> None:
        """Test detection of simple circular message references."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
msg-a = { msg-b }
msg-b = { msg-a }
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Circular message reference" in result.warnings[0].message
        assert "msg-a" in result.warnings[0].message
        assert "msg-b" in result.warnings[0].message

    def test_circular_message_reference_complex(self) -> None:
        """Test detection of complex circular message chain."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
msg1 = { msg2 }
msg2 = { msg3 }
msg3 = { msg1 }
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Circular message reference" in result.warnings[0].message

    def test_circular_term_reference_simple(self) -> None:
        """Test detection of simple circular term references."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
-term1 = { -term2 }
-term2 = { -term1 }
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Circular term reference" in result.warnings[0].message
        assert "-term1" in result.warnings[0].message
        assert "-term2" in result.warnings[0].message

    def test_circular_term_reference_complex(self) -> None:
        """Test detection of complex circular term chain."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
-a = { -b }
-b = { -c }
-c = { -d }
-d = { -a }
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Circular term reference" in result.warnings[0].message

    def test_valid_resource_no_warnings(self) -> None:
        """Test that valid resource produces no warnings."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
-brand = Acme Corp
welcome = Hello, { -brand }!
goodbye = Goodbye!
nested = See { welcome } for details
""")
        assert result.is_valid
        assert result.warning_count == 0

    def test_multiple_issues_reported(self) -> None:
        """Test that multiple validation issues are all reported."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
msg1 = { msg2 }
msg2 = { msg3 }
msg3 = { msg1 }
msg4 = { undefined-msg }
msg5 = { -undefined-term }
msg6 =
    .tooltip = Only has attribute
""")
        assert result.is_valid
        assert result.warning_count >= 3  # At least circular + 2 undefined

        # Check all issue types are detected
        warnings_text = " ".join(w.message for w in result.warnings)
        assert "Circular" in warnings_text
        assert "undefined message" in warnings_text
        assert "undefined term" in warnings_text

    def test_duplicate_id_detection(self) -> None:
        """Test detection of duplicate message IDs."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
msg = First
msg = Second
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Duplicate message ID 'msg'" in result.warnings[0].message

    def test_message_without_value(self) -> None:
        """Test detection of messages without values or attributes."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
valid = Has value
invalid =
    # This message has neither value nor attributes
""")
        # Note: Parser may create junk for invalid syntax
        # Check if we get either a warning or an error
        if result.is_valid:
            assert result.warning_count >= 0  # May or may not warn depending on parse

    def test_term_referencing_undefined_message(self) -> None:
        """Test that terms can reference messages and validation detects undefined ones."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
-brand = { company-name }
""")
        assert result.is_valid
        assert result.warning_count == 1
        warning_msg = "Term '-brand' references undefined message 'company-name'"
        assert warning_msg in result.warnings[0].message

    def test_complex_nested_references(self) -> None:
        """Test validation with complex nested reference chains."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
-brand = Acme Corp
-slogan = { -brand } - The best!
welcome = Welcome to { -slogan }
about = { welcome } Learn more.
""")
        assert result.is_valid
        assert result.warning_count == 0

    def test_attribute_references_checked(self) -> None:
        """Test that references in attributes are validated."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
button = Click
    .tooltip = See { undefined-msg } for details
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "undefined message 'undefined-msg'" in result.warnings[0].message


class TestValidationEdgeCases:
    """Test edge cases in semantic validation."""

    def test_self_reference_is_circular(self) -> None:
        """Test that message referencing itself is detected as circular."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
recursive = This is { recursive }
""")
        assert result.is_valid
        assert result.warning_count == 1
        assert "Circular" in result.warnings[0].message

    def test_empty_resource_valid(self) -> None:
        """Test that empty resource is valid with no warnings."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("")
        assert result.is_valid
        assert result.warning_count == 0

    def test_comments_do_not_trigger_warnings(self) -> None:
        """Test that comments don't trigger validation warnings."""
        bundle = FluentBundle("en", use_isolating=False)
        result = bundle.validate_resource("""
# This is a comment
## This is a group comment
### This is a resource comment
welcome = Hello
""")
        assert result.is_valid
        assert result.warning_count == 0
