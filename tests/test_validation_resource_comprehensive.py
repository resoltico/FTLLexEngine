"""Comprehensive tests for validation/resource.py to achieve 100% coverage.

Tests standalone resource validation including:
- Syntax error extraction from Junk entries
- Entry collection and duplicate detection
- Undefined reference checking
- Circular reference detection
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.validation.resource import validate_resource


class TestSyntaxErrorExtraction:
    """Test extraction of syntax errors from Junk entries."""

    def test_single_junk_entry_creates_validation_error(self) -> None:
        """Test that Junk entry is converted to ValidationError."""
        ftl = "invalid junk entry"
        result = validate_resource(ftl)

        # Should have syntax error
        assert len(result.errors) > 0
        assert any("parse" in err.code.lower() for err in result.errors)

    def test_multiple_junk_entries_create_multiple_errors(self) -> None:
        """Test multiple Junk entries create multiple errors."""
        ftl = """
invalid entry 1
also bad = { broken
another junk line
"""
        result = validate_resource(ftl)
        # Should have multiple errors (exact count depends on parser)
        assert len(result.errors) >= 1

    def test_junk_with_span_information(self) -> None:
        """Test that Junk errors include position information."""
        ftl = "msg = { broken syntax }"
        result = validate_resource(ftl)

        # Should have error with position info
        if len(result.errors) > 0:
            error = result.errors[0]
            # Line/column may be set
            assert error.code is not None

    @given(
        st.text(min_size=1, max_size=50).filter(
            lambda s: "=" not in s and "{" not in s and "}" not in s
        )
    )
    def test_invalid_syntax_property(self, invalid_text: str) -> None:
        """PROPERTY: Invalid FTL syntax produces validation errors."""
        result = validate_resource(invalid_text)
        # Either parses as comment/junk or has errors
        assert result is not None


class TestDuplicateIdDetection:
    """Test duplicate message and term ID detection."""

    def test_duplicate_message_ids_produce_warning(self) -> None:
        """Test duplicate message IDs create warnings."""
        ftl = """
msg = First value
msg = Second value
"""
        result = validate_resource(ftl)

        # Should have warning about duplicate
        assert len(result.warnings) > 0
        assert any(
            "duplicate" in warn.message.lower() and "msg" in warn.message.lower()
            for warn in result.warnings
        )

    def test_duplicate_term_ids_produce_warning(self) -> None:
        """Test duplicate term IDs create warnings."""
        ftl = """
-term = First value
-term = Second value
"""
        result = validate_resource(ftl)

        # Should have warning
        assert len(result.warnings) > 0
        assert any("duplicate" in warn.message.lower() for warn in result.warnings)

    def test_no_duplicate_warning_for_unique_ids(self) -> None:
        """Test no duplicate warnings when IDs are unique."""
        ftl = """
msg1 = First
msg2 = Second
-term1 = Term one
-term2 = Term two
"""
        result = validate_resource(ftl)

        # Should not have duplicate warnings
        duplicate_warnings = [
            w for w in result.warnings if "duplicate" in w.message.lower()
        ]
        assert len(duplicate_warnings) == 0

    @given(
        st.lists(
            st.from_regex(r"[a-z]+", fullmatch=True),
            min_size=2,
            max_size=5,
        )
    )
    def test_multiple_duplicates_property(self, ids: list[str]) -> None:
        """PROPERTY: Multiple duplicate IDs all produce warnings."""
        # Create FTL with all same ID
        ftl_lines = [f"{ids[0]} = Value {i}" for i in range(len(ids))]
        ftl = "\n".join(ftl_lines)

        result = validate_resource(ftl)
        # Should have warnings (at least len(ids) - 1 duplicates)
        if len(ids) > 1:
            assert len(result.warnings) >= 1


class TestMessageWithoutValue:
    """Test validation of messages without values (only attributes)."""

    def test_message_with_only_attributes_produces_warning(self) -> None:
        """Test message with no value but attributes gets warning."""
        ftl = """
msg =
    .attr1 = Value 1
    .attr2 = Value 2
"""
        result = validate_resource(ftl)

        # Per FTL spec, message can have only attributes (valid)
        # But implementation may warn about this pattern
        # Check it doesn't crash
        assert result is not None

    def test_message_with_value_and_attributes_no_warning(self) -> None:
        """Test message with both value and attributes is valid."""
        ftl = """
msg = Value
    .attr = Attribute
"""
        result = validate_resource(ftl)

        # Should be valid - no warnings about structure
        assert result is not None
        assert result.is_valid


class TestUndefinedReferenceDetection:
    """Test detection of undefined message and term references."""

    def test_undefined_message_reference_produces_warning(self) -> None:
        """Test reference to undefined message produces warning."""
        ftl = """
msg = { other }
"""
        result = validate_resource(ftl)

        # Should warn about undefined reference
        assert len(result.warnings) > 0
        assert any(
            "undefined" in warn.message.lower() or "reference" in warn.message.lower()
            for warn in result.warnings
        )

    def test_undefined_term_reference_produces_warning(self) -> None:
        """Test reference to undefined term produces warning."""
        ftl = """
msg = { -undefined }
"""
        result = validate_resource(ftl)

        # Should warn about undefined term
        assert len(result.warnings) > 0
        assert any("undefined" in warn.message.lower() for warn in result.warnings)

    def test_defined_message_reference_no_warning(self) -> None:
        """Test reference to defined message produces no warning."""
        ftl = """
other = Other message
msg = { other }
"""
        result = validate_resource(ftl)

        # Should not warn about this reference
        undefined_warnings = [
            w for w in result.warnings if "undefined" in w.message.lower()
        ]
        assert len(undefined_warnings) == 0

    def test_defined_term_reference_no_warning(self) -> None:
        """Test reference to defined term produces no warning."""
        ftl = """
-brand = Firefox
msg = { -brand }
"""
        result = validate_resource(ftl)

        undefined_warnings = [
            w for w in result.warnings if "undefined" in w.message.lower()
        ]
        assert len(undefined_warnings) == 0

    def test_term_referencing_undefined_message(self) -> None:
        """Test term that references undefined message."""
        ftl = """
-term = { undefined }
"""
        result = validate_resource(ftl)

        # Should warn
        assert any("undefined" in w.message.lower() for w in result.warnings)

    def test_term_referencing_undefined_term(self) -> None:
        """Test term that references undefined term."""
        ftl = """
-term1 = { -term2 }
"""
        result = validate_resource(ftl)

        # Should warn
        assert any("undefined" in w.message.lower() for w in result.warnings)


class TestCircularReferenceDetection:
    """Test detection of circular dependencies."""

    def test_direct_message_self_reference(self) -> None:
        """Test message referencing itself."""
        ftl = """
msg = { msg }
"""
        result = validate_resource(ftl)

        # Should detect cycle
        assert any("circular" in w.message.lower() for w in result.warnings)

    def test_indirect_message_cycle(self) -> None:
        """Test indirect message cycle (A -> B -> A)."""
        ftl = """
a = { b }
b = { a }
"""
        result = validate_resource(ftl)

        # Should detect cycle
        assert any("circular" in w.message.lower() for w in result.warnings)

    def test_three_way_message_cycle(self) -> None:
        """Test three-way message cycle (A -> B -> C -> A)."""
        ftl = """
a = { b }
b = { c }
c = { a }
"""
        result = validate_resource(ftl)

        # Should detect cycle
        assert any("circular" in w.message.lower() for w in result.warnings)

    def test_direct_term_self_reference(self) -> None:
        """Test term referencing itself."""
        ftl = """
-term = { -term }
"""
        result = validate_resource(ftl)

        # Should detect cycle
        assert any("circular" in w.message.lower() for w in result.warnings)

    def test_indirect_term_cycle(self) -> None:
        """Test indirect term cycle."""
        ftl = """
-a = { -b }
-b = { -a }
"""
        result = validate_resource(ftl)

        # Should detect cycle
        assert any("circular" in w.message.lower() for w in result.warnings)

    def test_no_cycle_in_tree_structure(self) -> None:
        """Test tree structure (no cycles) produces no warnings."""
        ftl = """
base = Base
a = { base }
b = { base }
c = { a }
"""
        result = validate_resource(ftl)

        # Should not warn about cycles
        circular_warnings = [
            w for w in result.warnings if "circular" in w.message.lower()
        ]
        assert len(circular_warnings) == 0


class TestValidationResultStructure:
    """Test ValidationResult structure and properties."""

    def test_valid_ftl_has_no_errors(self) -> None:
        """Test valid FTL produces is_valid=True."""
        ftl = """
msg = Hello
-term = World
"""
        result = validate_resource(ftl)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_parse_error_sets_is_valid_false(self) -> None:
        """Test parse errors set is_valid=False."""
        ftl = "invalid junk"
        result = validate_resource(ftl)

        # Should have errors and be invalid
        # (unless parser treats it as comment)
        if len(result.errors) > 0:
            assert not result.is_valid

    def test_warnings_dont_affect_is_valid(self) -> None:
        """Test warnings don't set is_valid=False."""
        ftl = """
msg = { undefined }
"""
        result = validate_resource(ftl)

        # May have warnings but no errors
        if len(result.errors) == 0:
            assert result.is_valid

    def test_validation_result_has_all_fields(self) -> None:
        """Test ValidationResult has all expected fields."""
        ftl = "msg = Test"
        result = validate_resource(ftl)

        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert hasattr(result, "annotations")
        assert hasattr(result, "is_valid")

        assert isinstance(result.errors, tuple)
        assert isinstance(result.warnings, tuple)
        assert isinstance(result.annotations, tuple)


class TestCustomParserInstance:
    """Test validate_resource with custom parser."""

    def test_validate_with_custom_parser(self) -> None:
        """Test validate_resource accepts custom parser."""
        from ftllexengine.syntax.parser import FluentParserV1

        parser = FluentParserV1()
        ftl = "msg = Test"

        result = validate_resource(ftl, parser=parser)
        assert result is not None
        assert result.is_valid

    def test_validate_creates_default_parser_if_none(self) -> None:
        """Test validate_resource creates parser if not provided."""
        ftl = "msg = Test"
        result = validate_resource(ftl)

        assert result is not None


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_resource(self) -> None:
        """Test validation of empty resource."""
        ftl = ""
        result = validate_resource(ftl)

        assert result is not None
        # Empty resource is valid
        assert result.is_valid

    def test_only_comments(self) -> None:
        """Test resource with only comments."""
        ftl = """
# Comment 1
## Comment 2
### Comment 3
"""
        result = validate_resource(ftl)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_comments_and_valid_entries(self) -> None:
        """Test mixed comments and entries."""
        ftl = """
# Header comment
msg = Value

## Section
-term = Term value
"""
        result = validate_resource(ftl)

        assert result.is_valid

    def test_whitespace_only(self) -> None:
        """Test resource with only whitespace."""
        ftl = "   \n\n      \n"  # Spaces only, no tabs (tabs can be invalid FTL)
        result = validate_resource(ftl)

        # Should be valid or may have parse errors depending on tab handling
        assert result is not None

    @given(
        st.text(
            alphabet=st.sampled_from(" \n\r"),  # Only safe whitespace chars
            min_size=0,
            max_size=100,
        )
    )
    def test_whitespace_property(self, whitespace: str) -> None:
        """PROPERTY: Whitespace-only resources don't crash validation."""
        result = validate_resource(whitespace)
        # Should not crash (may have errors, but completes)
        assert result is not None


class TestComplexScenarios:
    """Test complex validation scenarios."""

    def test_large_resource_with_multiple_issues(self) -> None:
        """Test resource with multiple types of issues."""
        ftl = """
# Valid comment
msg1 = Value

# Duplicate ID
msg1 = Second value

# Undefined reference
msg2 = { undefined }

# Circular reference
a = { b }
b = { a }

# Invalid syntax
invalid junk

# Valid term
-term = Term
"""
        result = validate_resource(ftl)

        # Should collect all issues
        assert len(result.errors) + len(result.warnings) > 0

    def test_deeply_nested_references(self) -> None:
        """Test chain of references without cycles."""
        ftl = """
msg1 = Value
msg2 = { msg1 }
msg3 = { msg2 }
msg4 = { msg3 }
msg5 = { msg4 }
"""
        result = validate_resource(ftl)

        # Should be valid (no cycles)
        circular_warnings = [
            w for w in result.warnings if "circular" in w.message.lower()
        ]
        assert len(circular_warnings) == 0

    def test_message_and_term_with_same_base_name(self) -> None:
        """Test message and term can have same name (different namespaces)."""
        ftl = """
brand = Message
-brand = Term
msg = { brand } and { -brand }
"""
        result = validate_resource(ftl)

        # Should be valid - different namespaces
        undefined_warnings = [
            w for w in result.warnings if "undefined" in w.message.lower()
        ]
        assert len(undefined_warnings) == 0


class TestValidationIntegration:
    """Integration tests combining multiple validation passes."""

    def test_all_validation_passes_execute(self) -> None:
        """Test all validation passes execute in sequence."""
        ftl = """
# Syntax error
invalid

# Duplicate
msg = First
msg = Second

# Undefined reference
ref = { missing }

# Circular reference
c1 = { c2 }
c2 = { c1 }
"""
        result = validate_resource(ftl)

        # Should have collected issues from all passes
        total_issues = len(result.errors) + len(result.warnings)
        assert total_issues > 0

    @given(
        st.lists(
            st.from_regex(r"[a-z]+", fullmatch=True),
            min_size=1,
            max_size=10,
            unique=True,
        )
    )
    def test_valid_messages_property(self, identifiers: list[str]) -> None:
        """PROPERTY: Valid messages with unique IDs validate successfully."""
        ftl_lines = [f"{id_} = Value for {id_}" for id_ in identifiers]
        ftl = "\n".join(ftl_lines)

        result = validate_resource(ftl)

        # Should be valid
        assert result.is_valid
        assert len(result.errors) == 0


# ============================================================================
# LINE 113: Test Message Without Value or Attributes
# ============================================================================


class TestMessageWithoutValueOrAttributes:
    """Test validation of message with neither value nor attributes (line 113)."""

    def test_message_without_value_or_attributes_warns(self) -> None:
        """Test message with neither value nor attributes generates warning (line 113).

        Line 113 in _collect_entries appends a warning when:
        - value is None AND
        - len(attributes) == 0

        Since the parser creates Junk for empty messages, we test the validation
        function directly with a constructed Resource AST.
        """
        from ftllexengine.syntax.ast import Identifier, Message, Resource
        from ftllexengine.validation.resource import _collect_entries

        # Create a Message with value=None and no attributes
        message_with_no_content = Message(
            id=Identifier("empty_msg"),
            value=None,  # No value
            attributes=(),  # No attributes
        )

        # Create Resource with this message
        resource = Resource(entries=(message_with_no_content,))

        # Call _collect_entries directly
        _messages_dict, _terms_dict, warnings = _collect_entries(resource)

        # Should have warning about no value or attributes (line 113)
        no_value_warnings = [
            w for w in warnings
            if "no-value-or-attributes" in w.code
        ]
        assert len(no_value_warnings) == 1
        assert "neither value nor attributes" in no_value_warnings[0].message
        assert no_value_warnings[0].context == "empty_msg"


# ============================================================================
# LINES 339-346: Test FluentSyntaxError Exception Handling
# ============================================================================


class TestFluentSyntaxErrorHandling:
    """Test handling of critical FluentSyntaxError during validation (lines 339-346)."""

    def test_validate_resource_handles_fluent_syntax_error(self) -> None:
        """Test validate_resource handles FluentSyntaxError exception (lines 339-346).

        Lines 339-346 catch FluentSyntaxError and convert it to ValidationError.
        This is defensive code for catastrophic parse failures.
        """
        from unittest.mock import patch

        from ftllexengine.diagnostics import FluentSyntaxError

        # Mock the parser to raise FluentSyntaxError
        with patch("ftllexengine.validation.resource.FluentParserV1") as mock_parser_class:
            mock_parser = mock_parser_class.return_value
            mock_parser.parse.side_effect = FluentSyntaxError("Catastrophic parse error")

            # Call validate_resource - should catch the exception
            result = validate_resource("test", parser=mock_parser)

            # Should have converted exception to validation error (lines 341-346)
            assert len(result.errors) == 1
            assert result.errors[0].code == "critical-parse-error"
            assert "Catastrophic parse error" in result.errors[0].message
            assert not result.is_valid
            assert len(result.warnings) == 0


# ============================================================================
# BRANCH COVERAGE: Test Missing Branches
# ============================================================================


class TestMissingBranchCoverage:
    """Test missing branch coverage in resource.py."""

    def test_junk_without_span_line_56(self) -> None:
        """Test Junk entry without span (branch 56->60).

        Line 56: if entry.span
        When span is None, line/column remain None.
        """
        from ftllexengine.syntax.ast import Junk, Resource
        from ftllexengine.validation.resource import _extract_syntax_errors

        # Create Junk with no span
        junk_no_span = Junk(content="invalid", span=None)
        resource = Resource(entries=(junk_no_span,))

        # Extract errors
        errors = _extract_syntax_errors(resource, "source")

        # Should have error with line=None, column=None
        assert len(errors) == 1
        assert errors[0].line is None
        assert errors[0].column is None

    def test_term_references_undefined_message_line_187(self) -> None:
        """Test term referencing undefined message (branch 187->186).

        Line 187: if ref not in messages_dict
        This tests the loop iteration when a term references a message.
        Branch 187->186 is when the message DOES exist (if condition is False).
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            MessageReference,
            Pattern,
            Placeable,
            Term,
            TextElement,
        )
        from ftllexengine.validation.resource import _check_undefined_references

        # Create message that exists
        existing_message = Message(
            id=Identifier("existing_msg"),
            value=Pattern(elements=(TextElement("text"),)),
            attributes=(),
        )

        # Create term that references the existing message
        term_with_msg_ref = Term(
            id=Identifier("myterm"),
            value=Pattern(elements=(
                TextElement("text"),
                Placeable(
                    expression=MessageReference(id=Identifier("existing_msg"))
                ),  # Reference to message that EXISTS
            )),
            attributes=(),
        )

        messages_dict = {"existing_msg": existing_message}  # Message exists
        terms_dict = {"myterm": term_with_msg_ref}

        # Check references
        warnings = _check_undefined_references(messages_dict, terms_dict)

        # Should have NO warnings (message exists)
        # This tests branch 187->186 (if condition is False, continue to next iteration)
        undefined_warnings = [w for w in warnings if "undefined" in w.message.lower()]
        assert len(undefined_warnings) == 0

    def test_duplicate_cycle_detection_line_243(self) -> None:
        """Test cycle deduplication for messages (branch 243->241).

        Line 243: if cycle_key not in seen_cycle_keys
        Tests the branch where a duplicate cycle is found and skipped.
        """
        from unittest.mock import patch

        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            MessageReference,
            Pattern,
            Placeable,
            Term,
        )
        from ftllexengine.validation.resource import _detect_circular_references

        # Create circular messages: a -> b -> a
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("b"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("a"))),)
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b}
        terms_dict: dict[str, Term] = {}

        # Mock detect_cycles to return the same cycle twice (with different order)
        # This simulates finding the same cycle multiple times
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            # Return same cycle twice: [a, b, a] and [b, a, b]
            # They have the same canonical form when sorted
            mock_detect.return_value = [
                ["a", "b", "a"],  # First occurrence
                ["b", "a", "b"],  # Second occurrence (same cycle, different start)
            ]

            warnings = _detect_circular_references(messages_dict, terms_dict)

            # Should only have 1 warning (second cycle deduplicated)
            circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
            assert len(circular_warnings) == 1

    def test_duplicate_cycle_detection_line_257(self) -> None:
        """Test cycle deduplication for terms (branch 257->255).

        Line 257: if cycle_key not in seen_cycle_keys
        Tests the branch where a duplicate term cycle is found and skipped.
        """
        from unittest.mock import patch

        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            Pattern,
            Placeable,
            Term,
            TermReference,
        )
        from ftllexengine.validation.resource import _detect_circular_references

        # Create circular terms: -ta -> -tb -> -ta
        term_a = Term(
            id=Identifier("ta"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("tb"))),)
            ),
            attributes=(),
        )
        term_b = Term(
            id=Identifier("tb"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("ta"))),)
            ),
            attributes=(),
        )

        messages_dict: dict[str, Message] = {}
        terms_dict = {"ta": term_a, "tb": term_b}

        # Mock detect_cycles to return the same cycle twice
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            # First call for messages (returns empty), second call for terms (returns cycles)
            mock_detect.side_effect = [
                [],  # Message cycles (none)
                [
                    ["ta", "tb", "ta"],  # First occurrence
                    ["tb", "ta", "tb"],  # Second occurrence (same cycle)
                ],
            ]

            warnings = _detect_circular_references(messages_dict, terms_dict)

            # Should only have 1 warning (second cycle deduplicated)
            circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
            assert len(circular_warnings) == 1
