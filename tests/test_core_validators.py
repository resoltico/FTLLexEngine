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
- normalize_optional_str: returns None for None input
- normalize_optional_str: delegates to require_non_empty_str for non-None
- normalize_optional_str: accessible from core package and root facade
- require_decimal_range: returns validated Decimal within range
- require_decimal_range: raises TypeError for bool and non-Decimal types
- require_decimal_range: raises ValueError for non-finite and out-of-range values
- require_decimal_range: field_name appears in error messages
- require_decimal_range: accessible from core package and root facade
- normalize_optional_decimal_range: returns None for None input
- normalize_optional_decimal_range: delegates to require_decimal_range for non-None
- normalize_optional_decimal_range: accessible from core package and root facade
- require_int_in_range: returns validated int within range
- require_int_in_range: raises TypeError for bool and non-int types
- require_int_in_range: raises ValueError for out-of-range values
- require_int_in_range: field_name appears in error messages
- require_int_in_range: accessible from core package and root facade
- require_date: returns date unchanged (identity); rejects datetime and non-date
- require_datetime: returns datetime unchanged (identity); rejects plain date
- require_fluent_number: returns FluentNumber unchanged; rejects non-FluentNumber
- require_fiscal_period: returns FiscalPeriod unchanged; rejects wrong types
- require_fiscal_calendar: returns FiscalCalendar unchanged; rejects wrong types
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

import ftllexengine
import ftllexengine.core as core_module
from ftllexengine.core.fiscal import FiscalCalendar, FiscalPeriod
from ftllexengine.core.validators import (
    coerce_tuple,
    normalize_optional_decimal_range,
    normalize_optional_str,
    require_date,
    require_datetime,
    require_decimal_range,
    require_fiscal_calendar,
    require_fiscal_period,
    require_fluent_number,
    require_int,
    require_int_in_range,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)
from ftllexengine.core.value_types import FluentNumber


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


# ---------------------------------------------------------------------------
# normalize_optional_str
# ---------------------------------------------------------------------------


class TestNormalizeOptionalStr:
    """Tests for normalize_optional_str None-passthrough validator."""

    def test_returns_none_for_none(self) -> None:
        """None input returns None."""
        assert normalize_optional_str(None, "description") is None

    def test_returns_stripped_string_for_non_none(self) -> None:
        """Non-None str delegates to require_non_empty_str (strips whitespace)."""
        assert normalize_optional_str("  hello  ", "description") == "hello"

    def test_returns_clean_string_unchanged(self) -> None:
        """A clean string with no surrounding whitespace is returned as-is."""
        assert normalize_optional_str("hello", "description") == "hello"

    def test_raises_value_error_for_empty_string(self) -> None:
        """Empty string raises ValueError (delegated to require_non_empty_str)."""
        with pytest.raises(ValueError, match="description cannot be blank"):
            normalize_optional_str("", "description")

    def test_raises_value_error_for_whitespace_only(self) -> None:
        """Whitespace-only string raises ValueError."""
        with pytest.raises(ValueError, match="description cannot be blank"):
            normalize_optional_str("   ", "description")

    def test_raises_type_error_for_int(self) -> None:
        """Non-str, non-None value raises TypeError."""
        with pytest.raises(TypeError, match="description must be str, got int"):
            normalize_optional_str(42, "description")

    def test_raises_type_error_for_list(self) -> None:
        """List raises TypeError."""
        with pytest.raises(TypeError, match="field must be str, got list"):
            normalize_optional_str([], "field")

    def test_raises_type_error_for_bytes(self) -> None:
        """Bytes raises TypeError (bytes is not str)."""
        with pytest.raises(TypeError, match="field must be str, got bytes"):
            normalize_optional_str(b"hello", "field")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_field must be str"):
            normalize_optional_str(3.14, "my_field")

    def test_field_name_in_value_error(self) -> None:
        """field_name appears in ValueError message."""
        with pytest.raises(ValueError, match="my_field cannot be blank"):
            normalize_optional_str("", "my_field")

    def test_return_type_is_none_for_none(self) -> None:
        """Return type is NoneType when value is None."""
        result = normalize_optional_str(None, "f")
        assert result is None

    def test_return_type_is_str_for_valid_input(self) -> None:
        """Return type is str for valid string input."""
        result = normalize_optional_str("hello", "f")
        assert type(result) is str


class TestNormalizeOptionalStrFacadeExport:
    """normalize_optional_str is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """normalize_optional_str is exported from ftllexengine.core."""
        assert callable(core_module.normalize_optional_str)
        assert core_module.normalize_optional_str is normalize_optional_str

    def test_accessible_from_root_facade(self) -> None:
        """normalize_optional_str is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.normalize_optional_str)
        assert ftllexengine.normalize_optional_str is normalize_optional_str

    def test_in_core_all(self) -> None:
        """normalize_optional_str is listed in ftllexengine.core.__all__."""
        assert "normalize_optional_str" in core_module.__all__

    def test_in_root_all(self) -> None:
        """normalize_optional_str is listed in ftllexengine.__all__."""
        assert "normalize_optional_str" in ftllexengine.__all__


# ---------------------------------------------------------------------------
# require_decimal_range
# ---------------------------------------------------------------------------

_LO = Decimal(0)
_HI = Decimal(1)
_HALF = Decimal("0.5")


class TestRequireDecimalRange:
    """Tests for require_decimal_range boundary validator."""

    def test_returns_value_within_range(self) -> None:
        """A Decimal within [lo, hi] is returned unchanged."""
        assert require_decimal_range(_HALF, _LO, _HI, "rate") == _HALF

    def test_returns_lo_boundary(self) -> None:
        """The lower boundary itself is valid and returned unchanged."""
        assert require_decimal_range(_LO, _LO, _HI, "rate") == _LO

    def test_returns_hi_boundary(self) -> None:
        """The upper boundary itself is valid and returned unchanged."""
        assert require_decimal_range(_HI, _LO, _HI, "rate") == _HI

    def test_returns_value_unchanged_identity(self) -> None:
        """The exact input Decimal object is returned (identity, not a copy)."""
        val = Decimal("0.25")
        result = require_decimal_range(val, _LO, _HI, "rate")
        assert result is val

    def test_raises_value_error_for_below_range(self) -> None:
        """Value below lo raises ValueError."""
        with pytest.raises(ValueError, match="rate must be in range"):
            require_decimal_range(Decimal("-0.01"), _LO, _HI, "rate")

    def test_raises_value_error_for_above_range(self) -> None:
        """Value above hi raises ValueError."""
        with pytest.raises(ValueError, match="rate must be in range"):
            require_decimal_range(Decimal("1.01"), _LO, _HI, "rate")

    def test_raises_value_error_for_infinity(self) -> None:
        """Positive infinity raises ValueError."""
        with pytest.raises(ValueError, match="rate must be finite"):
            require_decimal_range(Decimal("Infinity"), _LO, _HI, "rate")

    def test_raises_value_error_for_negative_infinity(self) -> None:
        """Negative infinity raises ValueError."""
        with pytest.raises(ValueError, match="rate must be finite"):
            require_decimal_range(Decimal("-Infinity"), _LO, _HI, "rate")

    def test_raises_value_error_for_nan(self) -> None:
        """NaN raises ValueError."""
        with pytest.raises(ValueError, match="rate must be finite"):
            require_decimal_range(Decimal("NaN"), _LO, _HI, "rate")

    def test_raises_type_error_for_int(self) -> None:
        """int raises TypeError even if value would be in range."""
        with pytest.raises(TypeError, match="rate must be Decimal, got int"):
            require_decimal_range(0, _LO, _HI, "rate")

    def test_raises_type_error_for_float(self) -> None:
        """float raises TypeError."""
        with pytest.raises(TypeError, match="rate must be Decimal, got float"):
            require_decimal_range(0.5, _LO, _HI, "rate")

    def test_raises_type_error_for_str(self) -> None:
        """str raises TypeError."""
        with pytest.raises(TypeError, match="rate must be Decimal, got str"):
            require_decimal_range("0.5", _LO, _HI, "rate")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="rate must be Decimal, got NoneType"):
            require_decimal_range(None, _LO, _HI, "rate")

    def test_raises_type_error_for_bool_true(self) -> None:
        """True raises TypeError — bool is rejected explicitly."""
        with pytest.raises(TypeError, match="rate must be Decimal, got bool"):
            require_decimal_range(True, _LO, _HI, "rate")

    def test_raises_type_error_for_bool_false(self) -> None:
        """False raises TypeError — bool is rejected before Decimal check."""
        with pytest.raises(TypeError, match="rate must be Decimal, got bool"):
            require_decimal_range(False, _LO, _HI, "rate")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_rate must be Decimal"):
            require_decimal_range(0.5, _LO, _HI, "my_rate")

    def test_field_name_in_range_error(self) -> None:
        """field_name appears in range ValueError message."""
        with pytest.raises(ValueError, match="my_rate must be in range"):
            require_decimal_range(Decimal(2), _LO, _HI, "my_rate")

    def test_field_name_in_finite_error(self) -> None:
        """field_name appears in finiteness ValueError message."""
        with pytest.raises(ValueError, match="my_rate must be finite"):
            require_decimal_range(Decimal("Inf"), _LO, _HI, "my_rate")

    def test_range_message_includes_bounds(self) -> None:
        """Error message includes the lo and hi bounds."""
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            require_decimal_range(Decimal(5), _LO, _HI, "rate")

    def test_arbitrary_range(self) -> None:
        """Works correctly with arbitrary lo/hi bounds."""
        lo = Decimal(-10)
        hi = Decimal(10)
        val = Decimal(-5)
        assert require_decimal_range(val, lo, hi, "offset") == val

    def test_single_point_range(self) -> None:
        """When lo == hi, only that exact value is valid."""
        mid = Decimal("0.5")
        assert require_decimal_range(mid, mid, mid, "exact") == mid
        with pytest.raises(ValueError, match="exact must be in range"):
            require_decimal_range(Decimal("0.4"), mid, mid, "exact")


class TestRequireDecimalRangeFacadeExport:
    """require_decimal_range is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_decimal_range is exported from ftllexengine.core."""
        assert callable(core_module.require_decimal_range)
        assert core_module.require_decimal_range is require_decimal_range

    def test_accessible_from_root_facade(self) -> None:
        """require_decimal_range is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_decimal_range)
        assert ftllexengine.require_decimal_range is require_decimal_range

    def test_in_core_all(self) -> None:
        """require_decimal_range is listed in ftllexengine.core.__all__."""
        assert "require_decimal_range" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_decimal_range is listed in ftllexengine.__all__."""
        assert "require_decimal_range" in ftllexengine.__all__


# ---------------------------------------------------------------------------
# normalize_optional_decimal_range
# ---------------------------------------------------------------------------


class TestNormalizeOptionalDecimalRange:
    """Tests for normalize_optional_decimal_range None-passthrough validator."""

    def test_returns_none_for_none(self) -> None:
        """None input returns None."""
        assert normalize_optional_decimal_range(None, _LO, _HI, "rate") is None

    def test_returns_valid_decimal_unchanged(self) -> None:
        """Valid Decimal in range is returned unchanged."""
        val = Decimal("0.25")
        result = normalize_optional_decimal_range(val, _LO, _HI, "rate")
        assert result == val
        assert result is val

    def test_returns_lo_boundary(self) -> None:
        """Lower boundary is valid."""
        assert normalize_optional_decimal_range(_LO, _LO, _HI, "rate") == _LO

    def test_returns_hi_boundary(self) -> None:
        """Upper boundary is valid."""
        assert normalize_optional_decimal_range(_HI, _LO, _HI, "rate") == _HI

    def test_raises_value_error_for_out_of_range(self) -> None:
        """Out-of-range Decimal raises ValueError (delegated)."""
        with pytest.raises(ValueError, match="rate must be in range"):
            normalize_optional_decimal_range(Decimal(2), _LO, _HI, "rate")

    def test_raises_value_error_for_nan(self) -> None:
        """NaN raises ValueError (delegated)."""
        with pytest.raises(ValueError, match="rate must be finite"):
            normalize_optional_decimal_range(Decimal("NaN"), _LO, _HI, "rate")

    def test_raises_type_error_for_int(self) -> None:
        """int raises TypeError (delegated)."""
        with pytest.raises(TypeError, match="rate must be Decimal, got int"):
            normalize_optional_decimal_range(0, _LO, _HI, "rate")

    def test_raises_type_error_for_bool(self) -> None:
        """bool raises TypeError (delegated)."""
        with pytest.raises(TypeError, match="rate must be Decimal, got bool"):
            normalize_optional_decimal_range(True, _LO, _HI, "rate")

    def test_return_type_is_none_for_none(self) -> None:
        """Return type is NoneType when value is None."""
        result = normalize_optional_decimal_range(None, _LO, _HI, "f")
        assert result is None

    def test_return_type_is_decimal_for_valid_input(self) -> None:
        """Return type is Decimal for valid Decimal input."""
        result = normalize_optional_decimal_range(_HALF, _LO, _HI, "f")
        assert isinstance(result, Decimal)


class TestNormalizeOptionalDecimalRangeFacadeExport:
    """normalize_optional_decimal_range reachable from core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """normalize_optional_decimal_range is exported from ftllexengine.core."""
        assert callable(core_module.normalize_optional_decimal_range)
        assert (
            core_module.normalize_optional_decimal_range
            is normalize_optional_decimal_range
        )

    def test_accessible_from_root_facade(self) -> None:
        """normalize_optional_decimal_range is exported from the root facade."""
        assert callable(ftllexengine.normalize_optional_decimal_range)
        assert (
            ftllexengine.normalize_optional_decimal_range
            is normalize_optional_decimal_range
        )

    def test_in_core_all(self) -> None:
        """normalize_optional_decimal_range is in ftllexengine.core.__all__."""
        assert "normalize_optional_decimal_range" in core_module.__all__

    def test_in_root_all(self) -> None:
        """normalize_optional_decimal_range is in ftllexengine.__all__."""
        assert "normalize_optional_decimal_range" in ftllexengine.__all__


# ---------------------------------------------------------------------------
# require_int_in_range
# ---------------------------------------------------------------------------


class TestRequireIntInRange:
    """Tests for require_int_in_range boundary validator."""

    def test_returns_value_within_range(self) -> None:
        """An int within [lo, hi] is returned unchanged."""
        assert require_int_in_range(5, 1, 10, "page_size") == 5

    def test_returns_lo_boundary(self) -> None:
        """The lower boundary itself is valid."""
        assert require_int_in_range(1, 1, 10, "page_size") == 1

    def test_returns_hi_boundary(self) -> None:
        """The upper boundary itself is valid."""
        assert require_int_in_range(10, 1, 10, "page_size") == 10

    def test_returns_value_unchanged_identity(self) -> None:
        """The exact input int is returned (identity, not a copy)."""
        val = 5
        result = require_int_in_range(val, 1, 10, "page_size")
        assert result is val

    def test_returns_zero_when_in_range(self) -> None:
        """Zero is accepted when it is within [lo, hi]."""
        assert require_int_in_range(0, -5, 5, "offset") == 0

    def test_returns_negative_when_in_range(self) -> None:
        """Negative values are accepted when within [lo, hi]."""
        assert require_int_in_range(-3, -10, 0, "delta") == -3

    def test_raises_value_error_for_below_range(self) -> None:
        """Value below lo raises ValueError."""
        with pytest.raises(ValueError, match="page_size must be in range"):
            require_int_in_range(0, 1, 10, "page_size")

    def test_raises_value_error_for_above_range(self) -> None:
        """Value above hi raises ValueError."""
        with pytest.raises(ValueError, match="page_size must be in range"):
            require_int_in_range(11, 1, 10, "page_size")

    def test_raises_type_error_for_float(self) -> None:
        """float raises TypeError even if value would be in range."""
        with pytest.raises(TypeError, match="page_size must be int, got float"):
            require_int_in_range(5.0, 1, 10, "page_size")

    def test_raises_type_error_for_str(self) -> None:
        """str raises TypeError."""
        with pytest.raises(TypeError, match="page_size must be int, got str"):
            require_int_in_range("5", 1, 10, "page_size")

    def test_raises_type_error_for_none(self) -> None:
        """None raises TypeError."""
        with pytest.raises(TypeError, match="page_size must be int, got NoneType"):
            require_int_in_range(None, 1, 10, "page_size")

    def test_raises_type_error_for_bool_true(self) -> None:
        """True raises TypeError — bool is an int subtype but rejected."""
        with pytest.raises(TypeError, match="page_size must be int, got bool"):
            require_int_in_range(True, 1, 10, "page_size")

    def test_raises_type_error_for_bool_false(self) -> None:
        """False raises TypeError — bool is rejected before int check."""
        with pytest.raises(TypeError, match="page_size must be int, got bool"):
            require_int_in_range(False, 1, 10, "page_size")

    def test_field_name_in_type_error(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_field must be int"):
            require_int_in_range("x", 1, 10, "my_field")

    def test_field_name_in_range_error(self) -> None:
        """field_name appears in range ValueError message."""
        with pytest.raises(ValueError, match="my_field must be in range"):
            require_int_in_range(0, 1, 10, "my_field")

    def test_range_message_includes_bounds(self) -> None:
        """Error message includes the lo and hi bounds."""
        with pytest.raises(ValueError, match=r"\[1, 10\]"):
            require_int_in_range(0, 1, 10, "page_size")

    def test_single_point_range(self) -> None:
        """When lo == hi, only that exact value is valid."""
        assert require_int_in_range(5, 5, 5, "exact") == 5
        with pytest.raises(ValueError, match="exact must be in range"):
            require_int_in_range(4, 5, 5, "exact")

    def test_large_positive_int(self) -> None:
        """Large positive integers are accepted when in range."""
        assert require_int_in_range(999_999, 0, 1_000_000, "count") == 999_999


class TestRequireIntInRangeFacadeExport:
    """require_int_in_range is reachable from both the core package and root facade."""

    def test_accessible_from_core_package(self) -> None:
        """require_int_in_range is exported from ftllexengine.core."""
        assert callable(core_module.require_int_in_range)
        assert core_module.require_int_in_range is require_int_in_range

    def test_accessible_from_root_facade(self) -> None:
        """require_int_in_range is exported from the ftllexengine root facade."""
        assert callable(ftllexengine.require_int_in_range)
        assert ftllexengine.require_int_in_range is require_int_in_range

    def test_in_core_all(self) -> None:
        """require_int_in_range is listed in ftllexengine.core.__all__."""
        assert "require_int_in_range" in core_module.__all__

    def test_in_root_all(self) -> None:
        """require_int_in_range is listed in ftllexengine.__all__."""
        assert "require_int_in_range" in ftllexengine.__all__


class TestRequireDate:
    """Tests for require_date boundary validator."""

    def test_returns_date_identity(self) -> None:
        """A plain date is returned unchanged (same object)."""
        d = date(2024, 6, 15)
        assert require_date(d, "effective_date") is d

    def test_rejects_datetime_subtype(self) -> None:
        """datetime (subclass of date) raises TypeError with field_name in message."""
        dt = datetime(2024, 6, 15, 9, 0)
        with pytest.raises(TypeError, match="effective_date"):
            require_date(dt, "effective_date")

    def test_datetime_error_message_names_got_type(self) -> None:
        """Error message for datetime input says 'got datetime'."""
        with pytest.raises(TypeError, match="got datetime"):
            require_date(datetime(2024, 1, 1), "field")

    def test_rejects_non_date_types(self) -> None:
        """Non-date types raise TypeError."""
        for bad in ("2024-01-01", 42, None, 3.14):
            with pytest.raises(TypeError, match="field"):
                require_date(bad, "field")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in TypeError message for any invalid value."""
        with pytest.raises(TypeError, match="my_date_field"):
            require_date("not-a-date", "my_date_field")

    def test_accessible_from_core(self) -> None:
        """require_date is exported from ftllexengine.core."""
        assert require_date is core_module.require_date

    def test_accessible_from_root_facade(self) -> None:
        """require_date is exported from the ftllexengine root facade."""
        assert ftllexengine.require_date is require_date

    def test_in_root_all(self) -> None:
        """require_date is listed in ftllexengine.__all__."""
        assert "require_date" in ftllexengine.__all__


class TestRequireDatetime:
    """Tests for require_datetime boundary validator."""

    def test_returns_datetime_identity(self) -> None:
        """A datetime is returned unchanged (same object)."""
        dt = datetime(2024, 6, 15, 9, 30)
        assert require_datetime(dt, "created_at") is dt

    def test_rejects_plain_date(self) -> None:
        """A plain date (not datetime) raises TypeError with field_name."""
        d = date(2024, 6, 15)
        with pytest.raises(TypeError, match="created_at"):
            require_datetime(d, "created_at")

    def test_rejects_non_datetime_types(self) -> None:
        """Non-datetime types raise TypeError."""
        for bad in ("2024-01-01T09:00:00", 42, None, 3.14):
            with pytest.raises(TypeError, match="field"):
                require_datetime(bad, "field")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_dt_field"):
            require_datetime(date(2024, 1, 1), "my_dt_field")

    def test_accessible_from_core(self) -> None:
        """require_datetime is exported from ftllexengine.core."""
        assert require_datetime is core_module.require_datetime

    def test_accessible_from_root_facade(self) -> None:
        """require_datetime is exported from the ftllexengine root facade."""
        assert ftllexengine.require_datetime is require_datetime

    def test_in_root_all(self) -> None:
        """require_datetime is listed in ftllexengine.__all__."""
        assert "require_datetime" in ftllexengine.__all__


class TestRequireFluentNumber:
    """Tests for require_fluent_number boundary validator."""

    def test_returns_fluent_number_identity(self) -> None:
        """A FluentNumber is returned unchanged (same object)."""
        fn = FluentNumber(value=42, formatted="42", precision=0)
        assert require_fluent_number(fn, "count") is fn

    def test_rejects_plain_int(self) -> None:
        """A plain int raises TypeError."""
        with pytest.raises(TypeError, match="count"):
            require_fluent_number(42, "count")

    def test_rejects_non_fluent_number_types(self) -> None:
        """Non-FluentNumber types raise TypeError."""
        for bad in ("42", 42.0, None, Decimal(42)):
            with pytest.raises(TypeError, match="field"):
                require_fluent_number(bad, "field")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_num_field"):
            require_fluent_number(99, "my_num_field")

    def test_accessible_from_core(self) -> None:
        """require_fluent_number is exported from ftllexengine.core."""
        assert require_fluent_number is core_module.require_fluent_number

    def test_accessible_from_root_facade(self) -> None:
        """require_fluent_number is exported from the ftllexengine root facade."""
        assert ftllexengine.require_fluent_number is require_fluent_number

    def test_in_root_all(self) -> None:
        """require_fluent_number is listed in ftllexengine.__all__."""
        assert "require_fluent_number" in ftllexengine.__all__


class TestRequireFiscalPeriod:
    """Tests for require_fiscal_period boundary validator."""

    def test_returns_fiscal_period_identity(self) -> None:
        """A FiscalPeriod is returned unchanged (same object)."""
        fp = FiscalPeriod(fiscal_year=2024, quarter=2, month=4)
        assert require_fiscal_period(fp, "period") is fp

    def test_rejects_non_fiscal_period(self) -> None:
        """Non-FiscalPeriod values raise TypeError."""
        for bad in ("2024-Q2", 2024, None, (2024, 2, 4)):
            with pytest.raises(TypeError, match="period"):
                require_fiscal_period(bad, "period")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_period_field"):
            require_fiscal_period("Q2", "my_period_field")

    def test_accessible_from_core(self) -> None:
        """require_fiscal_period is exported from ftllexengine.core."""
        assert require_fiscal_period is core_module.require_fiscal_period

    def test_accessible_from_root_facade(self) -> None:
        """require_fiscal_period is exported from the ftllexengine root facade."""
        assert ftllexengine.require_fiscal_period is require_fiscal_period

    def test_in_root_all(self) -> None:
        """require_fiscal_period is listed in ftllexengine.__all__."""
        assert "require_fiscal_period" in ftllexengine.__all__


class TestRequireFiscalCalendar:
    """Tests for require_fiscal_calendar boundary validator."""

    def test_returns_fiscal_calendar_identity(self) -> None:
        """A FiscalCalendar is returned unchanged (same object)."""
        fc = FiscalCalendar(start_month=10)
        assert require_fiscal_calendar(fc, "cal") is fc

    def test_rejects_non_fiscal_calendar(self) -> None:
        """Non-FiscalCalendar values raise TypeError."""
        for bad in (10, "October", None, {"year_start_month": 10}):
            with pytest.raises(TypeError, match="cal"):
                require_fiscal_calendar(bad, "cal")

    def test_field_name_in_error_message(self) -> None:
        """field_name appears in TypeError message."""
        with pytest.raises(TypeError, match="my_cal_field"):
            require_fiscal_calendar(None, "my_cal_field")

    def test_accessible_from_core(self) -> None:
        """require_fiscal_calendar is exported from ftllexengine.core."""
        assert require_fiscal_calendar is core_module.require_fiscal_calendar

    def test_accessible_from_root_facade(self) -> None:
        """require_fiscal_calendar is exported from the ftllexengine root facade."""
        assert ftllexengine.require_fiscal_calendar is require_fiscal_calendar

    def test_in_root_all(self) -> None:
        """require_fiscal_calendar is listed in ftllexengine.__all__."""
        assert "require_fiscal_calendar" in ftllexengine.__all__
