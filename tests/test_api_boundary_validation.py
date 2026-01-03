"""Tests for API boundary validation.

Validates defensive type checking at public API boundaries.
"""

from __future__ import annotations

from collections import OrderedDict

from ftllexengine import FluentBundle
from ftllexengine.constants import FALLBACK_INVALID
from ftllexengine.localization import FluentLocalization


class TestFluentBundleBoundaryValidation:
    """Test API boundary validation in FluentBundle."""

    def test_format_pattern_with_invalid_args_type(self) -> None:
        """format_pattern returns error when args is not a Mapping."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello { $name }")

        # Pass a list instead of dict/Mapping
        result, errors = bundle.format_pattern("msg", ["invalid"])  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "list" in str(errors[0])

    def test_format_pattern_with_invalid_attribute_type(self) -> None:
        """format_pattern returns error when attribute is not a string."""
        bundle = FluentBundle("en")
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

    def test_format_value_with_invalid_args_type(self) -> None:
        """format_value returns error when args is not a Mapping."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")

        # Pass a tuple instead of dict/Mapping
        result, errors = bundle.format_value("msg", ("invalid",))  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])


class TestFluentLocalizationBoundaryValidation:
    """Test API boundary validation in FluentLocalization."""

    def test_format_value_with_invalid_args_type(self) -> None:
        """format_value returns error when args is not a Mapping."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello { $name }")

        # Pass a string instead of dict/Mapping
        result, errors = l10n.format_value("msg", "invalid")  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "str" in str(errors[0])

    def test_format_pattern_with_invalid_args_type(self) -> None:
        """format_pattern returns error when args is not a Mapping."""
        l10n = FluentLocalization(["en"])
        l10n.add_resource("en", "msg = Hello { $name }")

        # Pass a set instead of dict/Mapping
        result, errors = l10n.format_pattern("msg", {"invalid"})  # type: ignore[arg-type]

        assert result == FALLBACK_INVALID
        assert len(errors) == 1
        assert "Invalid args type" in str(errors[0])
        assert "set" in str(errors[0])

    def test_format_pattern_with_invalid_attribute_type(self) -> None:
        """format_pattern returns error when attribute is not a string."""
        l10n = FluentLocalization(["en"])
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
