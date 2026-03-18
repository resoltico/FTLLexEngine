"""Tests for ftllexengine.core.validators boundary validation primitives.

Tests cover:
- require_non_empty_str: returns stripped non-blank string
- require_non_empty_str: raises TypeError for non-str input
- require_non_empty_str: raises ValueError for blank string
- require_non_empty_str: raises ValueError for whitespace-only string
- require_non_empty_str: field_name appears in error message
- require_non_empty_str: accessible from core package and root facade
- require_positive_int: returns value unchanged for positive int
- require_positive_int: raises TypeError for non-int, including bool
- require_positive_int: raises ValueError for zero and negative
- require_positive_int: field_name appears in error message
- require_positive_int: accessible from core package and root facade
"""

from __future__ import annotations

import pytest

import ftllexengine
import ftllexengine.core as core_module
from ftllexengine.core.validators import require_non_empty_str, require_positive_int


class TestRequireNonEmptyStr:
    """Tests for require_non_empty_str boundary validator."""

    def test_returns_stripped_string(self) -> None:
        """Surrounding whitespace is stripped and the clean value returned."""
        assert require_non_empty_str("  hello  ", "name") == "hello"

    def test_returns_value_without_leading_whitespace(self) -> None:
        """Leading whitespace alone is stripped."""
        assert require_non_empty_str("   world", "field") == "world"

    def test_returns_value_without_trailing_whitespace(self) -> None:
        """Trailing whitespace alone is stripped."""
        assert require_non_empty_str("world   ", "field") == "world"

    def test_returns_already_clean_string(self) -> None:
        """A string without surrounding whitespace is returned as-is."""
        assert require_non_empty_str("clean", "field") == "clean"

    def test_raises_type_error_for_int(self) -> None:
        """TypeError is raised when value is an int."""
        with pytest.raises(TypeError, match="name must be str, got int"):
            require_non_empty_str(42, "name")

    def test_raises_type_error_for_none(self) -> None:
        """TypeError is raised when value is None."""
        with pytest.raises(TypeError, match="field must be str, got NoneType"):
            require_non_empty_str(None, "field")

    def test_raises_type_error_for_bytes(self) -> None:
        """TypeError is raised when value is bytes."""
        with pytest.raises(TypeError, match="label must be str, got bytes"):
            require_non_empty_str(b"hello", "label")

    def test_raises_type_error_for_list(self) -> None:
        """TypeError is raised when value is a list."""
        with pytest.raises(TypeError, match="x must be str, got list"):
            require_non_empty_str([], "x")

    def test_raises_value_error_for_empty_string(self) -> None:
        """ValueError is raised for an empty string."""
        with pytest.raises(ValueError, match="locale cannot be blank"):
            require_non_empty_str("", "locale")

    def test_raises_value_error_for_whitespace_only(self) -> None:
        """ValueError is raised when the string is all whitespace."""
        with pytest.raises(ValueError, match="locale cannot be blank"):
            require_non_empty_str("   ", "locale")

    def test_raises_value_error_for_tab_only(self) -> None:
        """ValueError is raised when the string contains only a tab."""
        with pytest.raises(ValueError, match="field cannot be blank"):
            require_non_empty_str("\t", "field")

    def test_raises_value_error_for_newline_only(self) -> None:
        """ValueError is raised when the string is a bare newline."""
        with pytest.raises(ValueError, match="field cannot be blank"):
            require_non_empty_str("\n", "field")

    def test_field_name_appears_in_type_error(self) -> None:
        """The field_name argument is used verbatim in TypeError messages."""
        with pytest.raises(TypeError, match="my_custom_field must be str"):
            require_non_empty_str(3.14, "my_custom_field")

    def test_field_name_appears_in_value_error(self) -> None:
        """The field_name argument is used verbatim in ValueError messages."""
        with pytest.raises(ValueError, match="my_custom_field cannot be blank"):
            require_non_empty_str("", "my_custom_field")

    def test_mixed_whitespace_stripped(self) -> None:
        """Mixed leading/trailing whitespace (spaces, tabs, newlines) is stripped."""
        assert require_non_empty_str("\t  text\n  ", "field") == "text"

    def test_internal_whitespace_preserved(self) -> None:
        """Whitespace within the value (not at boundaries) is preserved."""
        assert require_non_empty_str("hello world", "field") == "hello world"


class TestRequireNonEmptyStrFacadeExport:
    """require_non_empty_str is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_non_empty_str is exported from ftllexengine.core."""
        assert callable(core_module.require_non_empty_str)
        assert core_module.require_non_empty_str is require_non_empty_str

    def test_accessible_from_root_facade(self) -> None:
        """require_non_empty_str is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_non_empty_str)
        assert ftllexengine.require_non_empty_str is require_non_empty_str

    def test_in_core_all(self) -> None:
        """require_non_empty_str is listed in ftllexengine.core.__all__."""
        assert "require_non_empty_str" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_non_empty_str is listed in ftllexengine.__all__."""
        assert "require_non_empty_str" in ftllexengine.__all__


class TestRequirePositiveInt:
    """Tests for require_positive_int boundary validator."""

    def test_returns_positive_int_unchanged(self) -> None:
        """A positive int is returned as-is."""
        assert require_positive_int(1, "size") == 1
        assert require_positive_int(1000, "size") == 1000

    def test_returns_large_int(self) -> None:
        """Large positive integers are accepted."""
        assert require_positive_int(10_000_000, "limit") == 10_000_000

    def test_raises_value_error_for_zero(self) -> None:
        """Zero raises ValueError."""
        with pytest.raises(ValueError, match="size must be positive"):
            require_positive_int(0, "size")

    def test_raises_value_error_for_negative(self) -> None:
        """Negative integers raise ValueError."""
        with pytest.raises(ValueError, match="count must be positive"):
            require_positive_int(-1, "count")

    def test_raises_value_error_for_large_negative(self) -> None:
        """Large negative integers raise ValueError."""
        with pytest.raises(ValueError, match="limit must be positive"):
            require_positive_int(-999, "limit")

    def test_raises_type_error_for_float(self) -> None:
        """Float raises TypeError even if value would be positive."""
        with pytest.raises(TypeError, match="size must be int, got float"):
            require_positive_int(1.0, "size")

    def test_raises_type_error_for_str(self) -> None:
        """String raises TypeError."""
        with pytest.raises(TypeError, match="size must be int, got str"):
            require_positive_int("5", "size")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="size must be int, got NoneType"):
            require_positive_int(None, "size")

    def test_raises_type_error_for_bool_true(self) -> None:
        """True raises TypeError — bool is an int subtype but rejected."""
        with pytest.raises(TypeError, match="size must be int, got bool"):
            require_positive_int(True, "size")

    def test_raises_type_error_for_bool_false(self) -> None:
        """False raises TypeError — bool is rejected before int check."""
        with pytest.raises(TypeError, match="size must be int, got bool"):
            require_positive_int(False, "size")

    def test_field_name_in_value_error(self) -> None:
        """field_name appears in ValueError message."""
        with pytest.raises(ValueError, match="my_field must be positive"):
            require_positive_int(0, "my_field")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_field must be int"):
            require_positive_int("x", "my_field")


class TestRequirePositiveIntFacadeExport:
    """require_positive_int is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_positive_int is exported from ftllexengine.core."""
        assert callable(core_module.require_positive_int)
        assert core_module.require_positive_int is require_positive_int

    def test_accessible_from_root_facade(self) -> None:
        """require_positive_int is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_positive_int)
        assert ftllexengine.require_positive_int is require_positive_int

    def test_in_core_all(self) -> None:
        """require_positive_int is listed in ftllexengine.core.__all__."""
        assert "require_positive_int" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_positive_int is listed in ftllexengine.__all__."""
        assert "require_positive_int" in ftllexengine.__all__
