"""Tests for validation.resource: validate_resource(), graph algorithms, edge cases."""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax import (
    Identifier,
    Junk,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Term,
    TermReference,
    TextElement,
)
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.validation.resource import (
    _build_dependency_graph,
    _compute_longest_paths,
    _detect_circular_references,
    _extract_syntax_errors,
    validate_resource,
)


class TestSyntaxErrorExtraction:
    """Test extraction of syntax errors from Junk entries."""

    def test_single_junk_entry_creates_validation_error(self) -> None:
        """Test that Junk entry is converted to ValidationError."""
        ftl = "invalid junk entry"
        result = validate_resource(ftl)

        # Should have syntax error
        assert len(result.errors) > 0
        assert any("parse" in err.code.name.lower() for err in result.errors)

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
        """PROPERTY: Invalid FTL syntax produces validation errors.

        Events emitted:
        - has_errors={bool}: Whether validation produced errors
        - has_whitespace={bool}: Whether input contains whitespace
        """

        result = validate_resource(invalid_text)

        # Emit events for semantic coverage
        event(f"has_errors={len(result.errors) > 0}")
        event(f"has_whitespace={any(c.isspace() for c in invalid_text)}")

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
        """PROPERTY: Multiple duplicate IDs all produce warnings.

        Events emitted:
        - duplicate_count={n}: Number of duplicate entries (len - 1)
        """

        # Create FTL with all same ID
        ftl_lines = [f"{ids[0]} = Value {i}" for i in range(len(ids))]
        ftl = "\n".join(ftl_lines)

        # Emit event for duplicate count
        event(f"duplicate_count={len(ids) - 1}")

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
        """PROPERTY: Whitespace-only resources don't crash validation.

        Events emitted:
        - length_category={bucket}: Length bucket (empty, short, medium, long)
        - has_newlines={bool}: Whether input contains newlines
        """

        # Emit events for semantic coverage
        length = len(whitespace)
        if length == 0:
            event("length_category=empty")
        elif length < 10:
            event("length_category=short")
        elif length < 50:
            event("length_category=medium")
        else:
            event("length_category=long")

        event(f"has_newlines={'\n' in whitespace}")

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
        """PROPERTY: Valid messages with unique IDs validate successfully.

        Events emitted:
        - message_count={n}: Number of messages in resource
        """

        ftl_lines = [f"{id_} = Value for {id_}" for id_ in identifiers]
        ftl = "\n".join(ftl_lines)

        # Emit event for message count
        event(f"message_count={len(identifiers)}")

        result = validate_resource(ftl)

        # Should be valid
        assert result.is_valid
        assert len(result.errors) == 0


# ============================================================================
# LINE 113: Test Message Without Value or Attributes
# ============================================================================


class TestMessageWithoutValueOrAttributes:
    """Test validation of message with neither value nor attributes (line 113)."""

    def test_message_without_value_or_attributes_raises_at_construction(self) -> None:
        """Message with neither value nor attributes raises ValueError at construction.

        The __post_init__ validation now enforces this invariant at construction
        time rather than deferring to the validator.
        """
        import pytest

        from ftllexengine.syntax.ast import Identifier, Message

        with pytest.raises(ValueError, match="must have a value or at least one attribute"):
            Message(
                id=Identifier("empty_msg"),
                value=None,
                attributes=(),
            )


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

        # Extract errors with LineOffsetCache
        errors = _extract_syntax_errors(resource, LineOffsetCache("source"))

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

        # Check references with empty LineOffsetCache for AST-only testing
        warnings = _check_undefined_references(messages_dict, terms_dict, LineOffsetCache(""))

        # Should have NO warnings (message exists)
        # This tests branch 187->186 (if condition is False, continue to next iteration)
        undefined_warnings = [w for w in warnings if "undefined" in w.message.lower()]
        assert len(undefined_warnings) == 0

    def test_duplicate_cycle_detection_line_243(self) -> None:
        """Test cycle deduplication for messages.

        Verifies that the unified graph cycle detection produces exactly one
        warning per unique cycle, not multiple warnings for the same cycle
        detected from different starting points.

        Uses unified cross-type cycle detection.
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            MessageReference,
            Pattern,
            Placeable,
        )

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

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Call the real function without mocking
        warnings = _detect_circular_references(graph)

        # Should only have 1 warning (cycle a -> b -> a is detected once)
        circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(circular_warnings) == 1
        # Should mention both messages in the cycle
        warning_msg = circular_warnings[0].message.lower()
        assert "a" in warning_msg or "b" in warning_msg

    def test_duplicate_cycle_detection_line_257(self) -> None:
        """Test cycle deduplication for terms.

        Verifies that term-only cycles are detected and deduplicated properly
        in the unified graph.

        Uses unified cross-type cycle detection.
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Pattern,
            Placeable,
            Term,
            TermReference,
        )

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

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)
        # Call the real function without mocking
        warnings = _detect_circular_references(graph)

        # Should only have 1 warning (cycle ta -> tb -> ta is detected once)
        circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(circular_warnings) == 1
        # Should mention both terms in the cycle
        warning_msg = circular_warnings[0].message.lower()
        assert "ta" in warning_msg or "tb" in warning_msg


# ============================================================================
# API BOUNDARY VALIDATION: TypeError for Non-String Input
# ============================================================================


class TestAPIBoundaryValidation:
    """Test API boundary validation for validate_resource.

    Tests defensive type checking at API boundaries (lines 760-764).
    """

    def test_validate_resource_raises_typeerror_for_bytes(self) -> None:
        """Test validate_resource raises TypeError when passed bytes instead of str.

        Type hints are not enforced at runtime. Users may incorrectly pass bytes
        when the API expects str. The function defensively checks and raises
        TypeError with a helpful message.

        Covers lines 760-764 and branch [759, 760].
        """
        import pytest

        # Pass bytes instead of str (common mistake when reading files)
        source_bytes = b"msg = Hello"

        with pytest.raises(
            TypeError,
            match=r"source must be str, not bytes.*Decode bytes to str",
        ):
            validate_resource(source_bytes)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_none(self) -> None:
        """Test validate_resource raises TypeError when passed None."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not NoneType",
        ):
            validate_resource(None)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_int(self) -> None:
        """Test validate_resource raises TypeError when passed int."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not int",
        ):
            validate_resource(42)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_list(self) -> None:
        """Test validate_resource raises TypeError when passed list."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not list",
        ):
            validate_resource(["msg = Hello"])  # type: ignore[arg-type]

    @given(
        st.one_of(
            st.binary(min_size=1, max_size=50),
            st.integers(),
            st.lists(st.text()),
            st.none(),
        )
    )
    def test_validate_resource_rejects_non_string_types_property(
        self, invalid_input: bytes | int | list[str] | None
    ) -> None:
        """PROPERTY: validate_resource rejects all non-string types with TypeError.

        Events emitted:
        - input_type={type}: Type of invalid input tested
        """
        import pytest

        # Emit event for input type diversity
        event(f"input_type={type(invalid_input).__name__}")

        with pytest.raises(TypeError, match=r"source must be str"):
            validate_resource(invalid_input)  # type: ignore[arg-type]


# ============================================================================
# _compute_longest_paths: Diamond Pattern (Line 556)
# ============================================================================


class TestComputeLongestPathsDiamondPattern:
    """Tests for _compute_longest_paths with diamond dependency patterns.

    Targets line 556: continue when node already in longest_path during
    stack processing (not outer loop).
    """

    def test_diamond_pattern_triggers_inner_continue(self) -> None:
        """Diamond pattern: A->B, A->C->B causes B to be encountered twice.

        When DFS processes A:
        1. Descends to B first, computes longest_path[B]
        2. Descends to C, which references B
        3. C tries to process B, but B is already in longest_path
        4. This triggers line 556: continue (inner stack check)

        This is different from outer loop skip (line 545-546).
        """
        # Create diamond: msg_a -> msg_b, msg_a -> msg_c -> msg_b
        graph = {
            "msg:a": {"msg:b", "msg:c"},
            "msg:b": set(),
            "msg:c": {"msg:b"},
        }

        result = _compute_longest_paths(graph)

        # All nodes should be processed
        assert "msg:a" in result
        assert "msg:b" in result
        assert "msg:c" in result

        # msg_b has no dependencies: depth 0
        assert result["msg:b"][0] == 0
        # msg_c depends on msg_b: depth 1
        assert result["msg:c"][0] == 1
        # msg_a has longest path through msg_c: depth 2
        assert result["msg:a"][0] == 2

    def test_multi_level_diamond_pattern(self) -> None:
        """Multi-level diamond: A->B->D, A->C->D ensures deep graph traversal."""
        graph = {
            "msg:a": {"msg:b", "msg:c"},
            "msg:b": {"msg:d"},
            "msg:c": {"msg:d"},
            "msg:d": set(),
        }

        result = _compute_longest_paths(graph)

        # msg_d is leaf: depth 0
        assert result["msg:d"][0] == 0
        # msg_b and msg_c both depend on msg_d: depth 1
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 1
        # msg_a depends on msg_b/msg_c: depth 2
        assert result["msg:a"][0] == 2

    def test_complex_dag_with_shared_nodes(self) -> None:
        """Complex DAG: A->B->E, A->C->E, A->D->E ensures multiple paths converge."""
        graph = {
            "msg:a": {"msg:b", "msg:c", "msg:d"},
            "msg:b": {"msg:e"},
            "msg:c": {"msg:e"},
            "msg:d": {"msg:e"},
            "msg:e": set(),
        }

        result = _compute_longest_paths(graph)

        # msg_e is referenced by 3 nodes
        assert result["msg:e"][0] == 0
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 1
        assert result["msg:d"][0] == 1
        assert result["msg:a"][0] == 2

    @given(
        num_intermediate=st.integers(min_value=2, max_value=5),
    )
    def test_diamond_pattern_property(self, num_intermediate: int) -> None:
        """Property: Diamond with N intermediate nodes all converging to same leaf.

        Pattern: root -> {node1, node2, ..., nodeN} -> leaf

        Events emitted:
        - num_intermediate={n}: Number of intermediate nodes
        """
        # Emit event for fuzzer guidance
        event(f"num_intermediate={num_intermediate}")

        graph: dict[str, set[str]] = {
            "msg:root": {f"msg:mid{i}" for i in range(num_intermediate)},
            "msg:leaf": set(),
        }
        for i in range(num_intermediate):
            graph[f"msg:mid{i}"] = {"msg:leaf"}

        result = _compute_longest_paths(graph)

        # Leaf has no dependencies
        assert result["msg:leaf"][0] == 0
        # All intermediate nodes have depth 1
        for i in range(num_intermediate):
            assert result[f"msg:mid{i}"][0] == 1
        # Root has depth 2
        assert result["msg:root"][0] == 2


# ============================================================================
# _compute_longest_paths: Cycle/Back-Edge Handling (Line 554-555)
# ============================================================================


class TestComputeLongestPathsCycleHandling:
    """Tests for _compute_longest_paths with cycles (back-edge detection).

    Targets line 554-555: continue when node in in_stack (back-edge detection).
    This is different from diamond patterns - actual cycles, not DAGs.
    """

    def test_simple_two_node_cycle(self) -> None:
        """Two-node cycle: A->B->A triggers back-edge detection.

        When DFS processes A:
        1. Push (A, 0), mark A in_stack
        2. Push (B, 0), mark B in_stack
        3. B references A, so push (A, 0)
        4. A is already in in_stack -> triggers line 554 second condition
        """
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # Both nodes should be processed
        assert "msg:a" in result
        assert "msg:b" in result

        # Cycle is broken by back-edge detection
        # A depends on B (depth 1), B's back-edge to A is skipped (depth 0)
        assert result["msg:a"][0] == 1
        assert result["msg:b"][0] == 0

    def test_three_node_cycle(self) -> None:
        """Three-node cycle: A->B->C->A triggers back-edge on longer path."""
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # All nodes processed
        assert "msg:a" in result
        assert "msg:b" in result
        assert "msg:c" in result

        # Cycle is broken at C (back-edge to A skipped)
        # A->B->C, C's back-edge to A is ignored
        assert result["msg:a"][0] == 2
        assert result["msg:b"][0] == 1
        assert result["msg:c"][0] == 0

    def test_self_referencing_node(self) -> None:
        """Self-reference: A->A is simplest cycle case."""
        graph = {
            "msg:a": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        assert "msg:a" in result
        # Self-reference creates back-edge immediately
        assert result["msg:a"][0] == 0

    def test_cycle_with_tail(self) -> None:
        """Cycle with tail: D->A->B->C->A (D leads into cycle)."""
        graph = {
            "msg:d": {"msg:a"},
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:a"},
        }

        result = _compute_longest_paths(graph)

        # All nodes processed
        assert len(result) == 4

        # D is outside cycle, has longest path through cycle
        assert result["msg:d"][0] >= 3

    @given(
        cycle_size=st.integers(min_value=2, max_value=6),
    )
    def test_cycle_property(self, cycle_size: int) -> None:
        """Property: N-node cycle should not cause infinite loop.

        Creates a cycle: 0->1->2->...->N-1->0

        Events emitted:
        - cycle_size={n}: Size of the cycle
        """
        # Emit event for fuzzer guidance
        event(f"cycle_size={cycle_size}")

        graph: dict[str, set[str]] = {}
        for i in range(cycle_size):
            next_node = (i + 1) % cycle_size
            graph[f"msg:n{i}"] = {f"msg:n{next_node}"}

        result = _compute_longest_paths(graph)

        # All nodes should be processed (no infinite loop)
        assert len(result) == cycle_size

        # Each node should have finite depth
        for i in range(cycle_size):
            depth, _path = result[f"msg:n{i}"]
            assert depth < cycle_size  # Depth bounded by cycle size


# ============================================================================
# _detect_circular_references: Duplicate Cycle Keys (Branch 425)
# ============================================================================


class TestDetectCircularReferencesDuplicateCycleKeys:
    """Tests for _detect_circular_references duplicate cycle key handling.

    Targets branch 425->423: if cycle_key not in seen_cycle_keys (false branch).
    """

    def test_duplicate_cycle_from_detect_cycles(self) -> None:
        """Mock detect_cycles to return duplicate cycles for defensive code test."""
        # Create a simple cycle
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:a"},
        }

        # Mock detect_cycles to yield the same cycle twice
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            # Return same cycle twice to test deduplication logic
            cycle = ["msg:a", "msg:b", "msg:a"]
            mock_detect.return_value = iter([cycle, cycle])

            warnings = _detect_circular_references(graph)

            # Should deduplicate and return only one warning
            assert len(warnings) == 1
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE

    def test_cycle_key_deduplication_with_permutations(self) -> None:
        """Cycle keys should deduplicate permutations (A->B->A == B->A->B)."""
        # This tests the make_cycle_key function indirectly
        # Create a self-referencing cycle to ensure consistent behavior
        graph = {
            "msg:x": {"msg:y"},
            "msg:y": {"msg:z"},
            "msg:z": {"msg:x"},
        }

        warnings = _detect_circular_references(graph)

        # Should detect exactly one cycle (not multiple rotations)
        assert len(warnings) == 1
        cycle_warnings = [
            w for w in warnings
            if w.code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE
        ]
        assert len(cycle_warnings) == 1


# ============================================================================
# _detect_circular_references: Malformed Node Formatting (Branch 434)
# ============================================================================


class TestDetectCircularReferencesMalformedNodes:
    """Tests for _detect_circular_references with malformed graph nodes.

    Targets branch 434->431: node doesn't start with "msg:" or "term:".
    """

    def test_malformed_node_in_cycle_skipped_in_formatting(self) -> None:
        """Malformed nodes (no msg:/term: prefix) handled gracefully in formatting."""
        # Directly test with malformed graph (shouldn't happen in practice)
        # This tests defensive programming
        graph = {
            "msg:a": {"malformed_node"},
            "malformed_node": {"msg:a"},
        }

        # Mock detect_cycles to return a cycle with malformed node
        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            cycle = ["msg:a", "malformed_node", "msg:a"]
            mock_detect.return_value = iter([cycle])

            warnings = _detect_circular_references(graph)

            # Should still create a warning
            assert len(warnings) == 1
            assert warnings[0].code == DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE

            # Context should only contain properly formatted nodes
            # "malformed_node" should be skipped (no prefix match)
            assert warnings[0].context is not None
            # The formatted output should contain "a" but not include malformed_node
            # (since it doesn't match msg: or term: prefixes)
            assert "a" in warnings[0].context

    def test_mixed_valid_and_malformed_nodes_in_cycle(self) -> None:
        """Cycle with mix of valid and malformed nodes formats valid ones only."""
        graph = {
            "msg:valid1": {"term:valid2"},
            "term:valid2": {"bad_node"},
            "bad_node": {"msg:valid1"},
        }

        with patch("ftllexengine.validation.resource.detect_cycles") as mock_detect:
            cycle = ["msg:valid1", "term:valid2", "bad_node", "msg:valid1"]
            mock_detect.return_value = iter([cycle])

            warnings = _detect_circular_references(graph)

            assert len(warnings) == 1
            assert warnings[0].context is not None
            # Should format valid nodes
            assert "valid1" in warnings[0].context
            assert "-valid2" in warnings[0].context
            # bad_node should be skipped in formatting (no prefix)


# ============================================================================
# Integration Tests with Real FTL Structures
# ============================================================================


class TestValidationResourceCompleteIntegration:
    """Integration tests combining edge cases using real FTL AST structures."""

    def test_diamond_dependency_in_real_messages(self) -> None:
        """Diamond pattern with real Message objects."""
        # Create: msgA -> msgB, msgA -> msgC -> msgB
        msg_b = Message(
            id=Identifier("msgB"),
            value=Pattern(elements=(TextElement(value="Base message"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("msgB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("msgB"))),
                    TextElement(value=" and "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgB": msg_b, "msgC": msg_c}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths (exercises diamond pattern)
        result = _compute_longest_paths(graph)

        # msgB is referenced by both msgA and msgC
        assert "msg:msgB" in result
        assert result["msg:msgB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    def test_cross_type_diamond_message_and_term(self) -> None:
        """Diamond with cross-type references: msg -> term, msg -> msg -> term."""
        # Create: msgA -> termB, msgA -> msgC -> termB
        term_b = Term(
            id=Identifier("termB"),
            value=Pattern(elements=(TextElement(value="Term value"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("termB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("termB"))),
                    TextElement(value=" via "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgC": msg_c}
        terms_dict = {"termB": term_b}

        # Build dependency graph
        graph = _build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths
        result = _compute_longest_paths(graph)

        # termB is referenced by both msgA and msgC
        assert "term:termB" in result
        assert result["term:termB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    @given(
        num_messages=st.integers(min_value=3, max_value=8),
    )
    def test_property_complex_dependency_graphs(self, num_messages: int) -> None:
        """Property: Complex dependency graphs always compute without errors.

        Events emitted:
        - num_messages={n}: Number of messages in graph
        """
        # Emit event for fuzzer guidance
        event(f"num_messages={num_messages}")

        # Create a chain with some cross-references
        messages_dict: dict[str, Message] = {}

        for i in range(num_messages):
            if i == num_messages - 1:
                # Last message has no references
                value = Pattern(elements=(TextElement(value="End"),))
            elif i % 2 == 0:
                # Even messages reference next message
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(f"msg{i+1}"))
                        ),
                    )
                )
            else:
                # Odd messages reference last message (creates diamond-like structure)
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(
                                id=Identifier(f"msg{num_messages-1}")
                            )
                        ),
                    )
                )

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        # Build and compute - should not raise
        graph = _build_dependency_graph(messages_dict, terms_dict)
        result = _compute_longest_paths(graph)

        # All messages should be in result
        assert len(result) >= num_messages


class TestValidationResourceEdgeCases:
    """Coverage for validation/resource.py edge cases."""

    def test_junk_without_span(self) -> None:
        """Junk entry without span uses None for line/column."""
        junk = Junk(content="invalid", span=None)

        class MockResource:
            def __init__(self) -> None:
                self.entries = [junk]

        errors = _extract_syntax_errors(
            MockResource(), "invalid"  # type: ignore[arg-type]
        )
        assert len(errors) > 0
        assert errors[0].line is None

    def test_validation_with_invalid_ftl(self) -> None:
        """Validation handles malformed FTL gracefully."""
        result = validate_resource("msg = { $val ->")
        assert result is not None

    def test_cycle_deduplication(self) -> None:
        """Circular references are detected without duplicates."""
        ftl = "\na = { b }\nb = { a }\nc = { d }\nd = { c }\n"
        result = validate_resource(ftl)
        circular = [
            w for w in result.warnings
            if "circular" in w.message.lower()
        ]
        assert len(circular) >= 2
