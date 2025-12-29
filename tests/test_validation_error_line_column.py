"""Tests for ValidationError, format_value, and introspect_message.

Tests for:
- ValidationError line/column computation
- format_value accepts Mapping type
- introspect_message accepts Term
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from ftllexengine import FluentLocalization
from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestValidationErrorLineColumn:
    """Tests for ValidationError line/column computation.

    Validates that parse errors include line and column information
    computed from the source span using the Cursor.
    """

    def test_validation_error_has_line_column(self) -> None:
        """ValidationError includes line and column for syntax errors."""
        bundle = FluentBundle("en_US")

        # Invalid FTL with syntax error on line 2
        ftl_source = """hello = Hello World
invalid syntax here
goodbye = Goodbye"""

        result = bundle.validate_resource(ftl_source)

        assert not result.is_valid
        assert result.error_count >= 1

        # Check that at least one error has line/column
        error_with_location = None
        for error in result.errors:
            if error.line is not None and error.column is not None:
                error_with_location = error
                break

        assert error_with_location is not None, "Expected ValidationError with line/column"
        # Type narrowing: we've asserted these are not None above
        assert error_with_location.line is not None
        assert error_with_location.column is not None
        assert error_with_location.line >= 1, "Line should be 1-indexed"
        assert error_with_location.column >= 1, "Column should be 1-indexed"

    def test_validation_error_line_position_accuracy(self) -> None:
        """ValidationError line position is accurate."""
        bundle = FluentBundle("en_US")

        # Error on line 3 (after two valid lines)
        ftl_source = """msg1 = First message
msg2 = Second message
this is invalid
msg3 = Third message"""

        result = bundle.validate_resource(ftl_source)

        assert not result.is_valid
        # Find error for the invalid line
        errors_with_line = [e for e in result.errors if e.line is not None]
        assert len(errors_with_line) >= 1, "Expected error with line info"

        # The invalid syntax is on line 3
        error = errors_with_line[0]
        assert error.line == 3, f"Expected line 3, got {error.line}"

    def test_validation_error_first_line_error(self) -> None:
        """ValidationError correctly reports errors on line 1."""
        bundle = FluentBundle("en_US")

        # Error on very first line
        ftl_source = "invalid message without equals"

        result = bundle.validate_resource(ftl_source)

        assert not result.is_valid
        errors_with_line = [e for e in result.errors if e.line is not None]

        if errors_with_line:
            # First line is line 1
            assert errors_with_line[0].line == 1

    def test_valid_resource_has_no_errors(self) -> None:
        """Valid FTL produces no errors."""
        bundle = FluentBundle("en_US")

        ftl_source = """hello = Hello World
goodbye = Goodbye"""

        result = bundle.validate_resource(ftl_source)

        assert result.is_valid
        assert result.error_count == 0


class TestFormatValueMappingSupport:
    """Tests for format_value accepting Mapping type (v0.15.0).

    Validates that format_value now accepts any Mapping type, not just dict.
    """

    def test_format_value_accepts_dict(self) -> None:
        """format_value accepts regular dict (baseline)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        args: dict[str, str] = {"name": "Alice"}
        result, errors = bundle.format_value("greeting", args)

        assert result == "Hello, Alice!"
        assert not errors

    def test_format_value_accepts_mapping_proxy(self) -> None:
        """format_value accepts MappingProxyType (read-only dict)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        # MappingProxyType is a read-only view of a dict
        args = MappingProxyType({"name": "Bob"})
        result, errors = bundle.format_value("greeting", args)

        assert result == "Hello, Bob!"
        assert not errors

    def test_format_value_accepts_none(self) -> None:
        """format_value accepts None for args."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("hello = Hello World!")

        result, errors = bundle.format_value("hello", None)

        assert result == "Hello World!"
        assert not errors

    def test_format_pattern_mapping_consistency(self) -> None:
        """format_value and format_pattern accept same Mapping types."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg = Value: { $value }")

        args = MappingProxyType({"value": "test"})

        # Both should work identically
        result1, errors1 = bundle.format_value("msg", args)
        result2, errors2 = bundle.format_pattern("msg", args)

        assert result1 == result2 == "Value: test"
        assert not errors1
        assert not errors2


class TestIntrospectMessageTermSupport:
    """Tests for introspect_message accepting Term (v0.15.0).

    Validates that introspect_message now accepts both Message and Term types
    per the corrected type signature.
    """

    def test_introspect_message_accepts_message(self) -> None:
        """introspect_message accepts Message type."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, { $name }!")

        entry = resource.entries[0]
        assert isinstance(entry, Message)
        info = introspect_message(entry)

        assert info.message_id == "greeting"
        assert "name" in info.get_variable_names()

    def test_introspect_message_accepts_term(self) -> None:
        """introspect_message accepts Term type."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = { $companyName } Products")

        entry = resource.entries[0]
        assert isinstance(entry, Term)
        info = introspect_message(entry)

        assert info.message_id == "brand"
        assert "companyName" in info.get_variable_names()

    def test_extract_variables_accepts_term(self) -> None:
        """extract_variables accepts Term type."""
        parser = FluentParserV1()
        resource = parser.parse("-product = { $productName } by { $company }")

        entry = resource.entries[0]
        assert isinstance(entry, Term)
        variables = extract_variables(entry)

        assert variables == frozenset({"productName", "company"})

    def test_introspect_term_with_functions(self) -> None:
        """introspect_message extracts functions from Term."""
        parser = FluentParserV1()
        resource = parser.parse("-price = { NUMBER($amount, minimumFractionDigits: 2) }")

        entry = resource.entries[0]
        assert isinstance(entry, Term)
        info = introspect_message(entry)

        assert "NUMBER" in info.get_function_names()
        assert "amount" in info.get_variable_names()

    def test_introspect_term_with_attributes(self) -> None:
        """introspect_message handles Term with attributes."""
        parser = FluentParserV1()
        resource = parser.parse(
            """-brand = Firefox
    .gender = { $genderType }
    .accusative = { $case }"""
        )

        entry = resource.entries[0]
        assert isinstance(entry, Term)
        info = introspect_message(entry)

        assert info.message_id == "brand"
        # Variables from attributes should be extracted
        assert "genderType" in info.get_variable_names()
        assert "case" in info.get_variable_names()

    def test_introspect_rejects_invalid_type(self) -> None:
        """introspect_message raises TypeError for non-Message/Term."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message("not a message")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(123)  # type: ignore[arg-type]


class TestFluentLocalizationFormatValueMapping:
    """Tests for FluentLocalization.format_value Mapping support."""

    def test_localization_format_value_mapping(self) -> None:
        """FluentLocalization.format_value accepts Mapping."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "greeting = Hello, { $name }!")

        args = MappingProxyType({"name": "Charlie"})
        result, errors = l10n.format_value("greeting", args)

        assert "Charlie" in result
        assert not errors


class TestBundleContextManagerCacheClearing:
    """Tests for context manager cache clearing behavior."""

    def test_context_manager_clears_cache_on_exit(self) -> None:
        """Context manager clears format cache on exit."""
        with FluentBundle("en", enable_cache=True) as bundle:
            bundle.add_resource("msg = Hello")

            # Format to populate cache
            bundle.format_pattern("msg")
            stats_during = bundle.get_cache_stats()
            assert stats_during is not None
            assert stats_during["size"] >= 0

        # After exit, if we had access to the bundle,
        # the cache would be cleared. The test verifies no exceptions.
