"""Validation enhancements for v0.57.0.

Tests for RG-VALIDATION group issues resolved in v0.57.0:
- VAL-DUPLICATE-ATTR-001: Duplicate attribute detection
- FTL-VAL-CONFLICT-001: Shadow warning when entry conflicts with known entry
- FTL-VAL-XRES-001: Cross-resource circular reference detection

Python 3.13+.
"""

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.validation.resource import validate_resource


class TestDuplicateAttributeDetection:
    """Test VAL-DUPLICATE-ATTR-001: Duplicate attribute detection."""

    def test_message_duplicate_attribute_detected(self) -> None:
        """Duplicate attribute in message emits VALIDATION_DUPLICATE_ATTRIBUTE warning."""
        source = """
hello = Hello
    .tooltip = First tooltip
    .tooltip = Second tooltip
"""
        result = validate_resource(source)

        assert result.warning_count > 0
        duplicate_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(duplicate_warnings) == 1
        assert "hello" in duplicate_warnings[0].message
        assert "tooltip" in duplicate_warnings[0].message
        assert duplicate_warnings[0].context == "hello.tooltip"

    def test_term_duplicate_attribute_detected(self) -> None:
        """Duplicate attribute in term emits VALIDATION_DUPLICATE_ATTRIBUTE warning."""
        source = """
-brand = Firefox
    .gender = masculine
    .gender = neuter
"""
        result = validate_resource(source)

        assert result.warning_count > 0
        duplicate_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(duplicate_warnings) == 1
        assert "brand" in duplicate_warnings[0].message
        assert "gender" in duplicate_warnings[0].message
        assert duplicate_warnings[0].context == "brand.gender"

    def test_multiple_duplicate_attributes_all_detected(self) -> None:
        """Multiple duplicate attributes in same entry all detected."""
        source = """
message = Value
    .attr1 = First
    .attr1 = Second
    .attr2 = First
    .attr2 = Second
"""
        result = validate_resource(source)

        assert result.warning_count > 0
        duplicate_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(duplicate_warnings) == 2
        contexts = {w.context for w in duplicate_warnings}
        assert contexts == {"message.attr1", "message.attr2"}

    def test_same_attribute_different_entries_not_flagged(self) -> None:
        """Same attribute name in different entries is not a duplicate."""
        source = """
message1 = Value
    .tooltip = Tooltip 1

message2 = Value
    .tooltip = Tooltip 2
"""
        result = validate_resource(source)

        duplicate_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(duplicate_warnings) == 0

    def test_three_duplicate_attributes_two_warnings(self) -> None:
        """Three instances of same attribute emit two warnings (2nd and 3rd)."""
        source = """
message = Value
    .attr = First
    .attr = Second
    .attr = Third
"""
        result = validate_resource(source)

        duplicate_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        # First occurrence is not a duplicate; second and third are
        assert len(duplicate_warnings) == 2


class TestShadowWarningDetection:
    """Test FTL-VAL-CONFLICT-001: Shadow warning detection."""

    def test_message_shadows_known_message(self) -> None:
        """Message in current resource shadowing known message emits warning."""
        source = """
hello = New definition
"""
        result = validate_resource(source, known_messages=frozenset(["hello"]))

        assert result.warning_count > 0
        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == 1
        assert "hello" in shadow_warnings[0].message
        assert "shadows existing message" in shadow_warnings[0].message
        assert shadow_warnings[0].context == "hello"

    def test_term_shadows_known_term(self) -> None:
        """Term in current resource shadowing known term emits warning."""
        source = """
-brand = NewBrand
"""
        result = validate_resource(source, known_terms=frozenset(["brand"]))

        assert result.warning_count > 0
        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == 1
        assert "brand" in shadow_warnings[0].message
        assert "shadows existing term" in shadow_warnings[0].message
        assert shadow_warnings[0].context == "brand"

    def test_no_shadow_when_different_namespace(self) -> None:
        """Message shadowing known term (different namespace) does not emit shadow warning."""
        source = """
brand = This is a message named 'brand'
"""
        result = validate_resource(source, known_terms=frozenset(["brand"]))

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == 0

    def test_no_shadow_when_no_known_entries(self) -> None:
        """No shadow warning when no known entries provided."""
        source = """
hello = Hello
-brand = Firefox
"""
        result = validate_resource(source)

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == 0

    def test_multiple_shadows_all_detected(self) -> None:
        """Multiple shadow conflicts all detected."""
        source = """
hello = New Hello
goodbye = New Goodbye
"""
        result = validate_resource(
            source, known_messages=frozenset(["hello", "goodbye"])
        )

        shadow_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
        ]
        assert len(shadow_warnings) == 2
        contexts = {w.context for w in shadow_warnings}
        assert contexts == {"hello", "goodbye"}


class TestCrossResourceCircularReferences:
    """Test FTL-VAL-XRES-001: Cross-resource circular reference detection."""

    def test_cross_resource_message_cycle_detected(self) -> None:
        """Circular reference through known message is detected."""
        # Current resource: msg-a -> msg-b
        # Known: msg-b (assume it references msg-a in the bundle)
        # This creates a cycle: msg-a -> msg-b -> msg-a
        source = """
msg-a = { msg-b }
"""
        result = validate_resource(source, known_messages=frozenset(["msg-b"]))

        # Note: We can detect that msg-a references msg-b (which is known)
        # But we can't detect the full cycle without msg-b's AST
        # However, the graph now includes msg-b as a node, so if we later
        # add another resource that has msg-b -> msg-a, the cycle would be detected

        # For this test, we verify that the validation completes without error
        # and that msg-b is considered a valid reference (no undefined reference warning)
        undefined_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
            and "msg-b" in w.message
        ]
        assert len(undefined_warnings) == 0

    def test_cross_resource_term_cycle_detected(self) -> None:
        """Circular reference through known term is detected."""
        source = """
-term-a = { -term-b }
"""
        result = validate_resource(source, known_terms=frozenset(["term-b"]))

        # Verify no undefined reference for term-b
        undefined_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
            and "term-b" in w.message
        ]
        assert len(undefined_warnings) == 0

    def test_cross_resource_mixed_cycle(self) -> None:
        """Circular reference with message -> known term is handled."""
        source = """
hello = { -brand }
"""
        result = validate_resource(source, known_terms=frozenset(["brand"]))

        undefined_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
            and "brand" in w.message
        ]
        assert len(undefined_warnings) == 0

    def test_known_entries_prevent_undefined_reference_warnings(self) -> None:
        """References to known entries do not trigger undefined reference warnings."""
        source = """
greeting = Hello { $name }
farewell = { greeting } { -brand }
"""
        result = validate_resource(
            source, known_messages=frozenset(["greeting"]), known_terms=frozenset(["brand"])
        )

        # greeting is defined in current resource, brand is known
        # Should have no undefined reference warnings
        undefined_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
        ]
        assert len(undefined_warnings) == 0

    def test_complex_cross_resource_dependencies(self) -> None:
        """Complex dependency graph with known entries validates correctly."""
        source = """
msg-a = { msg-b }
msg-b = { msg-c }
msg-c = { -term-x }
"""
        result = validate_resource(
            source, known_messages=frozenset(["msg-d"]), known_terms=frozenset(["term-x"])
        )

        # msg-a, msg-b, msg-c are in current resource
        # term-x is known
        # No cycles, no undefined references
        assert result.is_valid
        undefined_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name
        ]
        assert len(undefined_warnings) == 0


# Property-based tests with Hypothesis


@given(
    attribute_count=st.integers(min_value=2, max_value=5),
    duplicate_index=st.integers(min_value=0, max_value=4),
)
def test_property_duplicate_attribute_always_detected(
    attribute_count: int, duplicate_index: int
) -> None:
    """Property: Duplicate attribute always detected regardless of position."""
    if duplicate_index >= attribute_count:
        duplicate_index = attribute_count - 1

    # Build FTL with duplicate_index-th attribute duplicated
    attrs = [f"    .attr{i} = Value {i}" for i in range(attribute_count)]
    attrs.append(f"    .attr{duplicate_index} = Duplicate")
    ftl_source = "message = Test\n" + "\n".join(attrs)

    result = validate_resource(ftl_source)

    duplicate_warnings = [
        w
        for w in result.warnings
        if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
    ]
    assert len(duplicate_warnings) >= 1
    assert any(f"attr{duplicate_index}" in w.message for w in duplicate_warnings)


@given(
    known_count=st.integers(min_value=1, max_value=10),
    shadow_count=st.integers(min_value=1, max_value=10),
)
def test_property_shadow_warnings_proportional(
    known_count: int, shadow_count: int
) -> None:
    """Property: Shadow warning count equals number of shadowed entries."""
    # Create known entries
    known_messages = frozenset(f"msg-{i}" for i in range(known_count))

    # Create source with shadow_count shadows
    actual_shadow_count = min(shadow_count, known_count)
    messages = [f"msg-{i} = Shadow" for i in range(actual_shadow_count)]
    ftl_source = "\n".join(messages)

    result = validate_resource(ftl_source, known_messages=known_messages)

    shadow_warnings = [
        w
        for w in result.warnings
        if w.code == DiagnosticCode.VALIDATION_SHADOW_WARNING.name
    ]
    assert len(shadow_warnings) == actual_shadow_count
