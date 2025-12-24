"""Tests for v0.30.0 changes.

This module tests the specific fixes and improvements introduced in v0.30.0:
- LOGIC-PLURALCAT-001: Decimal support in plural category matching
- LOGIC-TERMSELF-001/BUILD-DEPS-001: Cross-type cycle detection
- API-VALIDWARN-001: ValidationWarning with line/column position
- LOGIC-FUTUREWARN-001: DeprecationWarning instead of FutureWarning
- STRUCT-ENUM-001: StrEnum migration for enum types
"""

from __future__ import annotations

import warnings
from decimal import Decimal
from enum import StrEnum

from ftllexengine.deprecation import deprecated, warn_deprecated
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.diagnostics.validation import ValidationWarning
from ftllexengine.enums import CommentType, ReferenceKind, VariableContext
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_metadata import FunctionCategory
from ftllexengine.validation.resource import validate_resource


class TestDecimalPluralMatching:
    """Test Decimal type support in plural category matching (LOGIC-PLURALCAT-001)."""

    def test_decimal_selector_triggers_plural_matching(self) -> None:
        """Test that Decimal values trigger plural category matching."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [one] one item
   *[other] { $count } items
}
""")

        # Decimal(1) should match "one" category
        result, _errors = bundle.format_pattern("items", {"count": Decimal("1")})
        assert result == "one item"

        # Decimal(5) should match "other" category
        result, _errors = bundle.format_pattern("items", {"count": Decimal("5")})
        assert result == "5 items"

    def test_decimal_zero_uses_other_category(self) -> None:
        """Test Decimal(0) uses 'other' category in English."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [one] one item
   *[other] { $count } items
}
""")

        result, _errors = bundle.format_pattern("items", {"count": Decimal("0")})
        assert result == "0 items"

    def test_decimal_fractional_uses_other_category(self) -> None:
        """Test fractional Decimal uses 'other' category."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [one] one item
   *[other] { $count } items
}
""")

        result, _errors = bundle.format_pattern("items", {"count": Decimal("1.5")})
        assert result == "1.5 items"

    def test_decimal_exact_match_takes_precedence(self) -> None:
        """Test exact numeric match takes precedence over plural category."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [1] exactly one
    [one] one item
   *[other] { $count } items
}
""")

        # Exact match [1] should take precedence over plural category [one]
        result, _errors = bundle.format_pattern("items", {"count": Decimal("1")})
        assert result == "exactly one"

    def test_decimal_with_locale_specific_plurals(self) -> None:
        """Test Decimal respects locale-specific plural rules."""
        # Polish has complex plural rules
        bundle = FluentBundle("pl", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [one] { $count } element
    [few] { $count } elementy
    [many] { $count } elementow
   *[other] { $count } elementu
}
""")

        # 1 -> one
        result, _errors = bundle.format_pattern("items", {"count": Decimal("1")})
        assert "element" in result
        assert "elementy" not in result

        # 2-4 -> few
        result, _errors = bundle.format_pattern("items", {"count": Decimal("2")})
        assert "elementy" in result


class TestCrossTypeCycleDetection:
    """Test cross-type cycle detection (LOGIC-TERMSELF-001, LOGIC-BUILD-DEPS-001)."""

    def test_message_only_cycle_detected(self) -> None:
        """Test detection of message-only cycles."""
        ftl = """
msg-a = { msg-b }
msg-b = { msg-a }
"""
        result = validate_resource(ftl)

        # Should have circular reference warning
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) > 0

    def test_term_only_cycle_detected(self) -> None:
        """Test detection of term-only cycles."""
        ftl = """
-term-a = { -term-b }
-term-b = { -term-a }
"""
        result = validate_resource(ftl)

        # Should have circular reference warning
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) > 0

    def test_cross_type_message_term_message_cycle_detected(self) -> None:
        """Test detection of message -> term -> message cycles."""
        ftl = """
msg-a = { -term-b }
-term-b = { msg-a }
"""
        result = validate_resource(ftl)

        # Should have circular reference warning (cross-type)
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) > 0
        # Should indicate cross-reference
        assert any("cross" in w.message.lower() for w in cycle_warnings)

    def test_term_message_term_cycle_detected(self) -> None:
        """Test detection of term -> message -> term cycles."""
        ftl = """
-term-a = { msg-b }
msg-b = { -term-a }
"""
        result = validate_resource(ftl)

        # Should have circular reference warning
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) > 0

    def test_longer_cross_type_cycle_detected(self) -> None:
        """Test detection of longer cross-type cycles."""
        ftl = """
msg-a = { -term-b }
-term-b = { msg-c }
msg-c = { msg-a }
"""
        result = validate_resource(ftl)

        # Should have circular reference warning
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) > 0

    def test_no_false_positive_for_shared_dependencies(self) -> None:
        """Test no false positive when messages share a common dependency."""
        ftl = """
msg-a = { -common }
msg-b = { -common }
-common = shared value
"""
        result = validate_resource(ftl)

        # Should NOT have circular reference warning
        cycle_warnings = [w for w in result.warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) == 0


class TestValidationWarningPosition:
    """Test ValidationWarning with line/column position (API-VALIDWARN-001)."""

    def test_validation_warning_has_position_fields(self) -> None:
        """Test ValidationWarning dataclass has line and column fields."""
        warning = ValidationWarning(
            code="test-code",
            message="Test message",
            context="test",
            line=10,
            column=5,
        )

        assert warning.line == 10
        assert warning.column == 5

    def test_validation_warning_position_is_optional(self) -> None:
        """Test line/column are optional (default None)."""
        warning = ValidationWarning(
            code="test-code",
            message="Test message",
        )

        assert warning.line is None
        assert warning.column is None

    def test_duplicate_id_warning_has_position(self) -> None:
        """Test duplicate ID warnings include position information."""
        ftl = """msg-first = First
msg-duplicate = Original

msg-duplicate = Duplicate definition
"""
        result = validate_resource(ftl)

        # Find duplicate warning
        dup_warnings = [
            w for w in result.warnings if "duplicate" in w.message.lower()
        ]
        assert len(dup_warnings) > 0

        # Should have position info (line of the duplicate)
        warning = dup_warnings[0]
        assert warning.line is not None
        assert warning.line > 1  # Should be line of duplicate, not first occurrence

    def test_undefined_reference_warning_has_position(self) -> None:
        """Test undefined reference warnings include position information."""
        ftl = """msg = { nonexistent }
"""
        result = validate_resource(ftl)

        # Find undefined reference warning
        ref_warnings = [
            w for w in result.warnings if "undefined" in w.message.lower()
        ]
        assert len(ref_warnings) > 0

        # Should have position info
        warning = ref_warnings[0]
        assert warning.line is not None
        assert warning.line == 1

    def test_validation_warning_format_method(self) -> None:
        """Test ValidationWarning.format() includes position info."""
        warning = ValidationWarning(
            code="test-code",
            message="Test message",
            context="test-ctx",
            line=5,
            column=10,
        )

        formatted = warning.format()
        assert "line 5" in formatted
        assert "column 10" in formatted
        assert "test-code" in formatted

    def test_validation_warning_format_without_position(self) -> None:
        """Test ValidationWarning.format() works without position."""
        warning = ValidationWarning(
            code="test-code",
            message="Test message",
        )

        formatted = warning.format()
        assert "test-code" in formatted
        assert "line" not in formatted


class TestDeprecationWarningCategory:
    """Test DeprecationWarning instead of FutureWarning (LOGIC-FUTUREWARN-001)."""

    def test_warn_deprecated_uses_deprecation_warning(self) -> None:
        """Test warn_deprecated emits DeprecationWarning, not FutureWarning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warn_deprecated(
                "test_feature",
                removal_version="2.0.0",
            )

        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)
        assert not issubclass(caught[0].category, FutureWarning)

    def test_deprecated_decorator_uses_deprecation_warning(self) -> None:
        """Test @deprecated decorator emits DeprecationWarning."""

        @deprecated(removal_version="2.0.0")
        def old_function() -> str:
            return "result"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = old_function()

        assert result == "result"
        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)

    def test_deprecation_warning_message_format(self) -> None:
        """Test deprecation warning message includes version and alternative."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warn_deprecated(
                "old_api",
                removal_version="2.0.0",
                alternative="new_api",
            )

        assert len(caught) == 1
        msg = str(caught[0].message)
        assert "old_api" in msg
        assert "2.0.0" in msg
        assert "new_api" in msg


class TestStrEnumMigration:
    """Test StrEnum migration for enum types (STRUCT-ENUM-001)."""

    def test_comment_type_is_str_enum(self) -> None:
        """Test CommentType is a StrEnum."""
        assert issubclass(CommentType, StrEnum)

    def test_variable_context_is_str_enum(self) -> None:
        """Test VariableContext is a StrEnum."""
        assert issubclass(VariableContext, StrEnum)

    def test_reference_kind_is_str_enum(self) -> None:
        """Test ReferenceKind is a StrEnum."""
        assert issubclass(ReferenceKind, StrEnum)

    def test_function_category_is_str_enum(self) -> None:
        """Test FunctionCategory is a StrEnum."""
        assert issubclass(FunctionCategory, StrEnum)

    def test_str_enum_automatic_string_conversion(self) -> None:
        """Test StrEnum members convert to string automatically."""
        # StrEnum members ARE strings
        assert str(CommentType.COMMENT) == "comment"
        assert str(VariableContext.PATTERN) == "pattern"
        assert str(ReferenceKind.MESSAGE) == "message"
        assert str(FunctionCategory.FORMATTING) == "formatting"

    def test_str_enum_equality_with_strings(self) -> None:
        """Test StrEnum members are equal to their string values.

        Note: We use str() conversion for comparison because mypy's type system
        doesn't recognize that StrEnum members ARE strings (comparison-overlap).
        At runtime, StrEnum members are strings and equality works directly.
        """
        # Use str() to satisfy type checker while testing runtime behavior
        assert str(CommentType.COMMENT) == "comment"
        assert str(VariableContext.SELECTOR) == "selector"
        assert str(ReferenceKind.TERM) == "term"
        assert str(FunctionCategory.TEXT) == "text"

    def test_str_enum_in_format_strings(self) -> None:
        """Test StrEnum members work in f-strings without .value."""
        msg = f"Type: {CommentType.GROUP}"
        assert msg == "Type: group"

    def test_str_enum_values(self) -> None:
        """Test all enum values are correct."""
        # CommentType
        assert CommentType.COMMENT.value == "comment"
        assert CommentType.GROUP.value == "group"
        assert CommentType.RESOURCE.value == "resource"

        # VariableContext
        assert VariableContext.PATTERN.value == "pattern"
        assert VariableContext.SELECTOR.value == "selector"
        assert VariableContext.VARIANT.value == "variant"
        assert VariableContext.FUNCTION_ARG.value == "function_arg"

        # ReferenceKind
        assert ReferenceKind.MESSAGE.value == "message"
        assert ReferenceKind.TERM.value == "term"

        # FunctionCategory
        assert FunctionCategory.FORMATTING.value == "formatting"
        assert FunctionCategory.TEXT.value == "text"
        assert FunctionCategory.CUSTOM.value == "custom"


class TestCurrencyInBuiltinHint:
    """Test CURRENCY is included in built-in functions hint (DOCS-TEMPLATE-001)."""

    def test_function_not_found_hint_includes_currency(self) -> None:
        """Test function_not_found error hint mentions CURRENCY."""
        diagnostic = ErrorTemplate.function_not_found("UNKNOWN")

        assert diagnostic.hint is not None
        assert "CURRENCY" in diagnostic.hint
        assert "NUMBER" in diagnostic.hint
        assert "DATETIME" in diagnostic.hint
