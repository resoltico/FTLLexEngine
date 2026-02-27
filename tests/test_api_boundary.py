"""Tests for API boundary validation.

Validates defensive type checking at public API boundaries.
Tests for SyntaxIntegrityError in strict mode.
"""

from __future__ import annotations

from collections import OrderedDict

import pytest

from ftllexengine import (
    FluentBundle,
    FormattingIntegrityError,
    ImmutabilityViolationError,
    SyntaxIntegrityError,
    validate_resource,
)
from ftllexengine.constants import FALLBACK_INVALID
from ftllexengine.localization import FluentLocalization


class TestFluentBundleBoundaryValidation:
    """Test API boundary validation in FluentBundle."""

    def test_format_pattern_with_invalid_args_type(self) -> None:
        """format_pattern returns error when args is not a Mapping (strict=False)."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello { $name }")

        # Pass a list instead of dict/Mapping
        result, errors = bundle.format_pattern("msg", ["invalid"])  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "list" in str(errors[0])

    def test_format_pattern_with_invalid_attribute_type(self) -> None:
        """format_pattern returns error when attribute is not a string (strict=False)."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello\n    .tooltip = Tooltip text")

        # Pass an int instead of string for attribute
        result, errors = bundle.format_pattern("msg", None, attribute=123)  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid attribute type" in str(errors[0])
        assert "int" in str(errors[0])

    def test_format_pattern_with_valid_args(self) -> None:
        """format_pattern works correctly with valid Mapping args."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello { $name }")

        result, errors = bundle.format_pattern("msg", {"name": "World"})

        # Unicode directional isolates wrap placeholder values
        assert "Hello" in result
        assert "World" in result
        assert errors == ()

    def test_format_pattern_with_none_args(self) -> None:
        """format_pattern works correctly with None args."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello World")

        result, errors = bundle.format_pattern("msg", None)

        assert result == "Hello World"
        assert errors == ()

    def test_format_pattern_with_tuple_args_type(self) -> None:
        """format_pattern returns error when args is a tuple (non-Mapping, strict=False)."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello")

        # Pass a tuple instead of dict/Mapping
        result, errors = bundle.format_pattern("msg", ("invalid",))  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])


class TestFluentLocalizationBoundaryValidation:
    """Test API boundary validation in FluentLocalization."""

    def test_format_value_with_invalid_args_type(self) -> None:
        """format_value returns error when args is not a Mapping (strict=False)."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = Hello { $name }")

        # Pass a string instead of dict/Mapping
        result, errors = l10n.format_value("msg", "invalid")  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "str" in str(errors[0])

    def test_format_pattern_with_invalid_args_type(self) -> None:
        """format_pattern returns error when args is not a Mapping (strict=False)."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = Hello { $name }")

        # Pass a set instead of dict/Mapping
        result, errors = l10n.format_pattern("msg", {"invalid"})  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "set" in str(errors[0])

    def test_format_pattern_with_invalid_attribute_type(self) -> None:
        """format_pattern returns error when attribute is not a string (strict=False)."""
        l10n = FluentLocalization(["en"], strict=False)
        l10n.add_resource("en", "msg = Hello\n    .tooltip = Tooltip")

        # Pass a float instead of string for attribute
        result, errors = l10n.format_pattern("msg", None, attribute=3.14)  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid attribute type" in str(errors[0])
        assert "float" in str(errors[0])

    def test_format_pattern_with_valid_args(self) -> None:
        """format_pattern works correctly with valid Mapping args."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello { $name }")

        result, errors = l10n.format_pattern("msg", {"name": "World"})

        # Unicode directional isolates wrap placeholder values
        assert "Hello" in result
        assert "World" in result
        assert errors == ()

    def test_format_value_with_none_args(self) -> None:
        """format_value works correctly with None args."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello World")

        result, errors = l10n.format_value("msg", None)

        assert result == "Hello World"
        assert errors == ()


class TestEdgeCases:
    """Test edge cases for boundary validation."""

    def test_custom_mapping_type_accepted(self) -> None:
        """Custom Mapping types are accepted as args."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $a } { $b }")

        # OrderedDict is a Mapping
        args = OrderedDict([("a", "first"), ("b", "second")])
        result, errors = bundle.format_pattern("msg", args)

        # Unicode directional isolates wrap placeholder values
        assert "first" in result
        assert "second" in result
        assert errors == ()

    def test_empty_dict_is_valid_args(self) -> None:
        """Empty dict is valid args."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Static message")

        result, errors = bundle.format_pattern("msg", {})

        assert result == "Static message"
        assert errors == ()

    def test_empty_string_attribute_is_valid(self) -> None:
        """Empty string attribute is a valid (but probably useless) string."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello\n    .tooltip = Tip")

        # Empty string is technically valid, though won't match any attribute
        _result, errors = bundle.format_pattern("msg", None, attribute="")

        # Empty attribute won't match, but no type error should occur
        # The bundle will return the message value since attribute doesn't match
        assert errors == ()  # No type validation errors


class TestSourceTypeValidation:
    """Test source parameter type validation at API boundaries."""

    def test_add_resource_rejects_bytes(self) -> None:
        """add_resource raises TypeError when bytes are passed."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError) as exc_info:
            bundle.add_resource(b"msg = Hello")  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "bytes" in str(exc_info.value)
        assert "decode" in str(exc_info.value).lower()

    def test_add_resource_rejects_none(self) -> None:
        """add_resource raises TypeError when None is passed."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError) as exc_info:
            bundle.add_resource(None)  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "NoneType" in str(exc_info.value)

    def test_add_resource_rejects_int(self) -> None:
        """add_resource raises TypeError when int is passed."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError) as exc_info:
            bundle.add_resource(42)  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "int" in str(exc_info.value)

    def test_add_resource_accepts_string(self) -> None:
        """add_resource accepts valid string source."""
        bundle = FluentBundle("en")

        junk = bundle.add_resource("msg = Hello World")

        assert junk == ()
        result, errors = bundle.format_pattern("msg")
        assert result == "Hello World"
        assert errors == ()

    def test_bundle_validate_resource_rejects_bytes(self) -> None:
        """FluentBundle.validate_resource raises TypeError for bytes."""
        bundle = FluentBundle("en")

        with pytest.raises(TypeError) as exc_info:
            bundle.validate_resource(b"msg = Hello")  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "bytes" in str(exc_info.value)

    def test_bundle_validate_resource_accepts_string(self) -> None:
        """FluentBundle.validate_resource accepts valid string source."""
        bundle = FluentBundle("en")

        result = bundle.validate_resource("msg = Hello World")

        assert result.is_valid
        assert result.error_count == 0

    def test_standalone_validate_resource_rejects_bytes(self) -> None:
        """Standalone validate_resource raises TypeError for bytes."""
        with pytest.raises(TypeError) as exc_info:
            validate_resource(b"msg = Hello")  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "bytes" in str(exc_info.value)

    def test_standalone_validate_resource_rejects_list(self) -> None:
        """Standalone validate_resource raises TypeError for list."""
        with pytest.raises(TypeError) as exc_info:
            validate_resource(["msg = Hello"])  # type: ignore[arg-type]

        assert "source must be str" in str(exc_info.value)
        assert "list" in str(exc_info.value)

    def test_standalone_validate_resource_accepts_string(self) -> None:
        """Standalone validate_resource accepts valid string source."""
        result = validate_resource("msg = Hello World")

        assert result.is_valid
        assert result.error_count == 0


class TestStrictModeSyntaxErrors:
    """Test SyntaxIntegrityError in strict mode."""

    def test_strict_mode_raises_on_syntax_error(self) -> None:
        """Strict mode raises SyntaxIntegrityError on syntax errors."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource("this is not valid FTL")

        err = exc_info.value
        assert "Strict mode" in str(err)
        assert "syntax error" in str(err).lower()
        assert len(err.junk_entries) >= 1
        assert err.context is not None
        assert err.context.component == "bundle"
        assert err.context.operation == "add_resource"

    def test_strict_mode_raises_with_source_path(self) -> None:
        """Strict mode includes source_path in exception."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource("invalid content", source_path="locales/en/ui.ftl")

        err = exc_info.value
        assert err.source_path == "locales/en/ui.ftl"
        assert "locales/en/ui.ftl" in str(err)
        assert err.context is not None
        assert err.context.key == "locales/en/ui.ftl"

    def test_strict_mode_allows_valid_resources(self) -> None:
        """Strict mode does not raise for valid FTL."""
        bundle = FluentBundle("en", strict=True)

        # Should not raise
        junk = bundle.add_resource("msg = Hello World")

        assert junk == ()
        result, errors = bundle.format_pattern("msg")
        assert result == "Hello World"
        assert errors == ()

    def test_non_strict_mode_returns_junk(self) -> None:
        """Non-strict mode returns junk tuple instead of raising."""
        bundle = FluentBundle("en", strict=False)

        junk = bundle.add_resource("this is not valid FTL")

        assert len(junk) >= 1
        assert junk[0].content == "this is not valid FTL"

    def test_strict_mode_multiple_syntax_errors(self) -> None:
        """Strict mode reports multiple syntax errors."""
        bundle = FluentBundle("en", strict=True)

        ftl_with_multiple_errors = """invalid line one
another invalid line
yet another error"""

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource(ftl_with_multiple_errors)

        err = exc_info.value
        # Multiple invalid lines should produce multiple junk entries
        assert len(err.junk_entries) >= 1

    def test_strict_mode_partial_valid_resource(self) -> None:
        """Strict mode raises even with partially valid resource."""
        bundle = FluentBundle("en", strict=True)

        # First message is valid, second is not
        ftl_source = """valid-msg = Hello World
this is not valid"""

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource(ftl_source)

        err = exc_info.value
        assert len(err.junk_entries) >= 1

    def test_strict_mode_error_is_immutable(self) -> None:
        """SyntaxIntegrityError is immutable after construction."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource("invalid")

        err = exc_info.value

        # Attempting to modify should raise ImmutabilityViolationError
        with pytest.raises(ImmutabilityViolationError):
            err._junk_entries = ()

    def test_syntax_integrity_error_repr(self) -> None:
        """SyntaxIntegrityError has informative repr."""
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError) as exc_info:
            bundle.add_resource("invalid", source_path="test.ftl")

        err = exc_info.value
        repr_str = repr(err)

        assert "SyntaxIntegrityError" in repr_str
        assert "test.ftl" in repr_str
        assert "junk_count=" in repr_str


class TestStrictModeFormattingVsSyntax:
    """Test distinction between formatting and syntax errors in strict mode."""

    def test_strict_mode_syntax_vs_formatting_error(self) -> None:
        """Syntax and formatting errors are raised by different operations."""
        # SyntaxIntegrityError is raised during add_resource
        bundle = FluentBundle("en", strict=True)

        with pytest.raises(SyntaxIntegrityError):
            bundle.add_resource("not valid FTL syntax")

        # FormattingIntegrityError is raised during format_pattern
        bundle2 = FluentBundle("en", strict=True)
        bundle2.add_resource("msg = { $undefined }")

        with pytest.raises(FormattingIntegrityError):
            bundle2.format_pattern("msg", {})
