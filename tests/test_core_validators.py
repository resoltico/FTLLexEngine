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
- require_int: returns value unchanged for any int (positive, zero, negative)
- require_int: raises TypeError for bool and non-int types
- require_int: no range check (zero and negative are valid)
- require_int: accessible from core package and root facade
- require_non_negative_int: returns value unchanged for zero and positive int
- require_non_negative_int: raises TypeError for bool and non-int types
- require_non_negative_int: raises ValueError for negative values
- require_non_negative_int: accessible from core package and root facade
- coerce_tuple: returns tuple from list, tuple, range, and other sequences
- coerce_tuple: raises TypeError for str input
- coerce_tuple: raises TypeError for non-Sequence input (int, None, generator)
- coerce_tuple: accessible from core package and root facade
"""

from __future__ import annotations

import pytest

import ftllexengine
import ftllexengine.core as core_module
from ftllexengine.core.validators import (
    coerce_tuple,
    require_int,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)


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


class TestRequireInt:
    """Tests for require_int boundary validator."""

    def test_returns_positive_int_unchanged(self) -> None:
        """A positive int is returned as-is."""
        assert require_int(42, "year") == 42

    def test_returns_zero_unchanged(self) -> None:
        """Zero is valid and returned unchanged."""
        assert require_int(0, "year") == 0

    def test_returns_negative_int_unchanged(self) -> None:
        """Negative integers are valid and returned unchanged."""
        assert require_int(-5, "offset") == -5

    def test_returns_large_int(self) -> None:
        """Large integers are accepted."""
        assert require_int(10_000_000, "year") == 10_000_000

    def test_returns_large_negative_int(self) -> None:
        """Large negative integers are accepted."""
        assert require_int(-10_000_000, "year") == -10_000_000

    def test_raises_type_error_for_bool_true(self) -> None:
        """True raises TypeError — bool is an int subtype but rejected."""
        with pytest.raises(TypeError, match="year must be int, got bool"):
            require_int(True, "year")

    def test_raises_type_error_for_bool_false(self) -> None:
        """False raises TypeError — bool is rejected before int check."""
        with pytest.raises(TypeError, match="year must be int, got bool"):
            require_int(False, "year")

    def test_raises_type_error_for_float(self) -> None:
        """Float raises TypeError."""
        with pytest.raises(TypeError, match="year must be int, got float"):
            require_int(1.0, "year")

    def test_raises_type_error_for_str(self) -> None:
        """String raises TypeError."""
        with pytest.raises(TypeError, match="year must be int, got str"):
            require_int("2024", "year")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="year must be int, got NoneType"):
            require_int(None, "year")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_year must be int"):
            require_int(3.14, "my_year")

    def test_no_range_check_zero(self) -> None:
        """Zero passes — no range check applied."""
        assert require_int(0, "count") == 0

    def test_no_range_check_negative(self) -> None:
        """Negative values pass — no range check applied."""
        assert require_int(-1, "offset") == -1


class TestRequireIntFacadeExport:
    """require_int is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_int is exported from ftllexengine.core."""
        assert callable(core_module.require_int)
        assert core_module.require_int is require_int

    def test_accessible_from_root_facade(self) -> None:
        """require_int is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_int)
        assert ftllexengine.require_int is require_int

    def test_in_core_all(self) -> None:
        """require_int is listed in ftllexengine.core.__all__."""
        assert "require_int" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_int is listed in ftllexengine.__all__."""
        assert "require_int" in ftllexengine.__all__


class TestRequireNonNegativeInt:
    """Tests for require_non_negative_int boundary validator."""

    def test_returns_positive_int_unchanged(self) -> None:
        """A positive int is returned as-is."""
        assert require_non_negative_int(5, "index") == 5

    def test_returns_zero_unchanged(self) -> None:
        """Zero is valid (zero-based index boundary) and returned unchanged."""
        assert require_non_negative_int(0, "index") == 0

    def test_returns_large_int(self) -> None:
        """Large positive integers are accepted."""
        assert require_non_negative_int(10_000_000, "index") == 10_000_000

    def test_raises_value_error_for_negative(self) -> None:
        """Negative integers raise ValueError."""
        with pytest.raises(ValueError, match="index must be non-negative"):
            require_non_negative_int(-1, "index")

    def test_raises_value_error_for_large_negative(self) -> None:
        """Large negative integers raise ValueError."""
        with pytest.raises(ValueError, match="index must be non-negative"):
            require_non_negative_int(-999, "index")

    def test_raises_type_error_for_float(self) -> None:
        """Float raises TypeError."""
        with pytest.raises(TypeError, match="index must be int, got float"):
            require_non_negative_int(0.0, "index")

    def test_raises_type_error_for_str(self) -> None:
        """String raises TypeError."""
        with pytest.raises(TypeError, match="index must be int, got str"):
            require_non_negative_int("0", "index")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="index must be int, got NoneType"):
            require_non_negative_int(None, "index")

    def test_raises_type_error_for_bool_true(self) -> None:
        """True raises TypeError — bool is an int subtype but rejected."""
        with pytest.raises(TypeError, match="index must be int, got bool"):
            require_non_negative_int(True, "index")

    def test_raises_type_error_for_bool_false(self) -> None:
        """False raises TypeError — bool is rejected before int check."""
        with pytest.raises(TypeError, match="index must be int, got bool"):
            require_non_negative_int(False, "index")

    def test_field_name_in_value_error(self) -> None:
        """field_name appears in ValueError message."""
        with pytest.raises(ValueError, match="my_index must be non-negative"):
            require_non_negative_int(-1, "my_index")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_index must be int"):
            require_non_negative_int("x", "my_index")

    def test_zero_is_boundary_and_valid(self) -> None:
        """Zero is at the valid boundary (non-negative means >= 0)."""
        assert require_non_negative_int(0, "entry_index") == 0


class TestRequireNonNegativeIntFacadeExport:
    """require_non_negative_int is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_non_negative_int is exported from ftllexengine.core."""
        assert callable(core_module.require_non_negative_int)
        assert core_module.require_non_negative_int is require_non_negative_int

    def test_accessible_from_root_facade(self) -> None:
        """require_non_negative_int is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_non_negative_int)
        assert ftllexengine.require_non_negative_int is require_non_negative_int

    def test_in_core_all(self) -> None:
        """require_non_negative_int is listed in ftllexengine.core.__all__."""
        assert "require_non_negative_int" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_non_negative_int is listed in ftllexengine.__all__."""
        assert "require_non_negative_int" in ftllexengine.__all__


class TestCoerceTuple:
    """Tests for coerce_tuple sequence coercion utility."""

    def test_coerces_list_to_tuple(self) -> None:
        """A list is coerced to a tuple with the same elements."""
        assert coerce_tuple([1, 2, 3], "items") == (1, 2, 3)

    def test_coerces_tuple_to_tuple(self) -> None:
        """An existing tuple produces a new tuple with the same elements."""
        assert coerce_tuple((4, 5), "ids") == (4, 5)

    def test_coerces_range_to_tuple(self) -> None:
        """A range is coerced to a tuple."""
        assert coerce_tuple(range(3), "indices") == (0, 1, 2)

    def test_coerces_empty_list_to_empty_tuple(self) -> None:
        """An empty list produces an empty tuple."""
        assert coerce_tuple([], "items") == ()

    def test_coerces_empty_tuple_to_empty_tuple(self) -> None:
        """An empty tuple produces an empty tuple."""
        assert coerce_tuple((), "items") == ()

    def test_result_is_always_tuple(self) -> None:
        """The return value is always of type tuple, not a subclass."""
        result: tuple[object, ...] = coerce_tuple([1, 2], "items")
        assert type(result) is tuple

    def test_raises_type_error_for_str(self) -> None:
        """str raises TypeError — str is a Sequence but semantically a scalar here."""
        with pytest.raises(TypeError, match="items must be a non-str Sequence, got str"):
            coerce_tuple("hello", "items")

    def test_raises_type_error_for_int(self) -> None:
        """int raises TypeError — not a Sequence."""
        with pytest.raises(TypeError, match="items must be a Sequence, got int"):
            coerce_tuple(42, "items")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="items must be a Sequence, got NoneType"):
            coerce_tuple(None, "items")

    def test_raises_type_error_for_generator(self) -> None:
        """Generator raises TypeError — generators are Iterable but not Sequence."""
        gen = (x for x in range(3))
        with pytest.raises(TypeError, match="items must be a Sequence, got generator"):
            coerce_tuple(gen, "items")

    def test_raises_type_error_for_set(self) -> None:
        """Set raises TypeError — sets are not Sequences (no __getitem__)."""
        with pytest.raises(TypeError, match="items must be a Sequence, got set"):
            coerce_tuple({1, 2, 3}, "items")

    def test_field_name_in_type_error_for_str(self) -> None:
        """field_name appears in TypeError when str is passed."""
        with pytest.raises(TypeError, match="my_field must be a non-str Sequence"):
            coerce_tuple("x", "my_field")

    def test_field_name_in_type_error_for_non_sequence(self) -> None:
        """field_name appears in TypeError when non-Sequence is passed."""
        with pytest.raises(TypeError, match="my_field must be a Sequence"):
            coerce_tuple(99, "my_field")

    def test_bytes_is_accepted_as_sequence(self) -> None:
        """bytes is a Sequence[int] and is accepted (not excluded like str)."""
        result: tuple[object, ...] = coerce_tuple(b"\x01\x02\x03", "raw")
        assert result == (1, 2, 3)


class TestCoerceTupleFacadeExport:
    """coerce_tuple is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """coerce_tuple is exported from ftllexengine.core."""
        assert callable(core_module.coerce_tuple)
        assert core_module.coerce_tuple is coerce_tuple

    def test_accessible_from_root_facade(self) -> None:
        """coerce_tuple is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.coerce_tuple)
        assert ftllexengine.coerce_tuple is coerce_tuple

    def test_in_core_all(self) -> None:
        """coerce_tuple is listed in ftllexengine.core.__all__."""
        assert "coerce_tuple" in core_module.__all__

    def test_in_root_all(self) -> None:
        """coerce_tuple is listed in ftllexengine.__all__."""
        assert "coerce_tuple" in ftllexengine.__all__
