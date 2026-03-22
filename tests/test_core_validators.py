"""Tests for ftllexengine.core.validators boundary validation primitives.

Tests cover:
- require_positive_int: returns value unchanged for positive int
- require_positive_int: raises TypeError for non-int, including bool
- require_positive_int: raises ValueError for zero and negative
- require_positive_int: field_name appears in error message
- require_date: returns date unchanged (identity); rejects datetime and non-date
- require_datetime: returns datetime unchanged (identity); rejects plain date
- require_fluent_number: returns FluentNumber unchanged; rejects non-FluentNumber
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

import ftllexengine
import ftllexengine.core as core_module
from ftllexengine.core.validators import (
    require_date,
    require_datetime,
    require_fluent_number,
    require_positive_int,
)
from ftllexengine.core.value_types import FluentNumber


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


