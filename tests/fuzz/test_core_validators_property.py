"""Property-based fuzz tests for core.validators boundary validation primitives.

Properties verified:
- require_positive_int: for any positive int (not bool), returns n unchanged.
- require_positive_int: for bool (True/False), always raises TypeError.
- require_positive_int: for any non-int type, always raises TypeError.
- require_positive_int: for zero and negative ints, always raises ValueError.
- require_positive_int: field_name is always embedded in the error message.
- require_date: for any date (not datetime), returns value unchanged.
- require_date: for datetime (subclass of date), always raises TypeError.
- require_date: for non-date values, always raises TypeError.
- require_datetime: for any datetime, returns value unchanged.
- require_datetime: for plain date (not datetime), always raises TypeError.
- require_datetime: for non-datetime values, always raises TypeError.
- require_fluent_number: for any FluentNumber, returns value unchanged.
- require_fluent_number: for non-FluentNumber values, always raises TypeError.
"""

from __future__ import annotations

import string
from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.core.validators import (
    require_date,
    require_datetime,
    require_fluent_number,
    require_positive_int,
)
from ftllexengine.core.value_types import FluentNumber

pytestmark = pytest.mark.fuzz

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_FIELD_NAMES = st.text(
    alphabet=string.ascii_letters + string.digits + "_",
    min_size=1,
    max_size=30,
)

_POSITIVE_INTS = st.integers(min_value=1, max_value=10_000_000)

_ZERO_AND_NEGATIVE = st.integers(max_value=0)

_NON_INT_VALUES = st.one_of(
    st.floats(allow_nan=False),
    st.text(min_size=0, max_size=10),
    st.none(),
    st.binary(min_size=0, max_size=4),
    st.lists(st.integers(), max_size=3),
    st.decimals(allow_nan=False, allow_infinity=False),
)

_DATES = st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
_DATETIMES = st.datetimes(
    min_value=datetime(1900, 1, 1),
    max_value=datetime(2100, 12, 31),
)
_NON_DATE_VALUES: st.SearchStrategy[object] = st.one_of(
    st.integers(),
    st.text(min_size=0, max_size=10),
    st.none(),
    st.floats(allow_nan=False),
    st.booleans(),
)

_FLUENT_NUMBERS: st.SearchStrategy[FluentNumber] = st.one_of(
    st.integers(min_value=-1_000_000, max_value=1_000_000).map(
        lambda v: FluentNumber(value=v, formatted=str(v), precision=0)
    ),
    st.decimals(
        min_value=Decimal("-999999.99"),
        max_value=Decimal("999999.99"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ).map(lambda v: FluentNumber(value=v, formatted=str(v), precision=2)),
)

_NON_FLUENT_NUMBER_VALUES: st.SearchStrategy[object] = st.one_of(
    st.integers(),
    st.decimals(allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=10),
    st.none(),
    st.floats(allow_nan=False),
    st.booleans(),
)


# ---------------------------------------------------------------------------
# require_positive_int properties
# ---------------------------------------------------------------------------


class TestRequirePositiveIntProperties:
    """Property-based invariants for require_positive_int."""

    @given(n=_POSITIVE_INTS, field=_FIELD_NAMES)
    @example(n=1, field="size")
    @example(n=1_000_000, field="limit")
    def test_returns_value_unchanged_for_positive_int(
        self, n: int, field: str
    ) -> None:
        """For any positive int (not bool), returns n unchanged."""
        event(f"magnitude={'small' if n < 100 else 'medium' if n < 100_000 else 'large'}")
        result = require_positive_int(n, field)
        assert result == n
        assert result is n  # identity, not a copy
        event("outcome=pass_through")

    @given(n=_ZERO_AND_NEGATIVE, field=_FIELD_NAMES)
    @example(n=0, field="count")
    @example(n=-1, field="depth")
    @example(n=-999_999, field="limit")
    def test_raises_value_error_for_non_positive(self, n: int, field: str) -> None:
        """For zero and negative integers, raises ValueError with field_name."""
        event(f"n={'zero' if n == 0 else 'negative'}")
        with pytest.raises(ValueError, match=field):
            require_positive_int(n, field)
        event("outcome=value_error_raised")

    @given(field=_FIELD_NAMES)
    def test_raises_type_error_for_bool_true(self, field: str) -> None:
        """True raises TypeError even though bool is an int subtype."""
        with pytest.raises(TypeError, match=field):
            require_positive_int(True, field)
        event("outcome=bool_true_rejected")

    @given(field=_FIELD_NAMES)
    def test_raises_type_error_for_bool_false(self, field: str) -> None:
        """False raises TypeError — bool is rejected before int magnitude check."""
        with pytest.raises(TypeError, match=field):
            require_positive_int(False, field)
        event("outcome=bool_false_rejected")

    @given(value=_NON_INT_VALUES, field=_FIELD_NAMES)
    def test_raises_type_error_for_non_int(self, value: object, field: str) -> None:
        """For any non-int type, raises TypeError with field_name in message."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_positive_int(value, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_value_error(self, field: str) -> None:
        """field_name appears in ValueError when n == 0."""
        with pytest.raises(ValueError, match=field) as exc_info:
            require_positive_int(0, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_value_error")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_type_error(self, field: str) -> None:
        """field_name appears in TypeError when value is wrong type."""
        with pytest.raises(TypeError, match=field) as exc_info:
            require_positive_int(3.14, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_type_error")

    @given(n=_POSITIVE_INTS, field=_FIELD_NAMES)
    def test_result_type_is_int(self, n: int, field: str) -> None:
        """Result type is exactly int (not a subclass)."""
        result = require_positive_int(n, field)
        assert type(result) is int
        event("outcome=type_is_int")

    @given(
        n=st.integers(min_value=1, max_value=10_000_000),
        field=_FIELD_NAMES,
    )
    def test_monotone_acceptance(self, n: int, field: str) -> None:
        """All positive integers are accepted; the boundary is strictly at zero.

        Metamorphic: n+1 is also accepted whenever n is accepted.
        """
        require_positive_int(n, field)
        require_positive_int(n + 1, field)
        event("outcome=monotone_accepted")


# ---------------------------------------------------------------------------
# require_date properties
# ---------------------------------------------------------------------------


class TestRequireDateProperties:
    """Property-based invariants for require_date."""

    @given(d=_DATES, field=_FIELD_NAMES)
    @example(d=date(2024, 1, 15), field="effective_date")
    @example(d=date(1900, 1, 1), field="start")
    def test_returns_date_unchanged(self, d: date, field: str) -> None:
        """For any date (not datetime), returns value unchanged (identity)."""
        event(f"year={d.year}")
        result = require_date(d, field)
        assert result is d
        event("outcome=pass_through")

    @given(d=_DATETIMES, field=_FIELD_NAMES)
    @example(d=datetime(2024, 1, 15, 9, 0), field="effective_date")
    def test_datetime_always_raises_type_error(self, d: datetime, field: str) -> None:
        """datetime (subclass of date) always raises TypeError."""
        event(f"has_time={'yes' if d.hour != 0 or d.minute != 0 else 'midnight'}")
        with pytest.raises(TypeError, match="must be date, got datetime"):
            require_date(d, field)
        event("outcome=datetime_rejected")

    @given(value=_NON_DATE_VALUES, field=_FIELD_NAMES)
    def test_non_date_always_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-date, non-datetime values always raise TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_date(value, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_type_error(self, field: str) -> None:
        """field_name is embedded in the TypeError message."""
        with pytest.raises(TypeError) as exc_info:
            require_date(42, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_error")


# ---------------------------------------------------------------------------
# require_datetime properties
# ---------------------------------------------------------------------------


class TestRequireDatetimeProperties:
    """Property-based invariants for require_datetime."""

    @given(d=_DATETIMES, field=_FIELD_NAMES)
    @example(d=datetime(2024, 1, 15, 9, 0, 0), field="created_at")
    def test_returns_datetime_unchanged(self, d: datetime, field: str) -> None:
        """For any datetime, returns value unchanged (identity)."""
        event(f"has_time={'yes' if d.hour != 0 or d.minute != 0 else 'midnight'}")
        result = require_datetime(d, field)
        assert result is d
        event("outcome=pass_through")

    @given(d=_DATES.filter(lambda d: type(d) is date), field=_FIELD_NAMES)
    @example(d=date(2024, 1, 15), field="created_at")
    def test_plain_date_always_raises_type_error(self, d: date, field: str) -> None:
        """Plain date (not datetime) always raises TypeError."""
        event(f"year={d.year}")
        with pytest.raises(TypeError, match="must be datetime, got date"):
            require_datetime(d, field)
        event("outcome=date_rejected")

    @given(value=_NON_DATE_VALUES, field=_FIELD_NAMES)
    def test_non_datetime_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-datetime values always raise TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_datetime(value, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_type_error(self, field: str) -> None:
        """field_name is embedded in the TypeError message."""
        with pytest.raises(TypeError) as exc_info:
            require_datetime(date(2024, 1, 1), field)
        assert field in str(exc_info.value)
        event("outcome=field_in_error")


# ---------------------------------------------------------------------------
# require_fluent_number properties
# ---------------------------------------------------------------------------


class TestRequireFluentNumberProperties:
    """Property-based invariants for require_fluent_number."""

    @given(fn=_FLUENT_NUMBERS, field=_FIELD_NAMES)
    def test_returns_fluent_number_unchanged(
        self, fn: FluentNumber, field: str
    ) -> None:
        """For any FluentNumber, returns value unchanged (identity)."""
        event(f"precision={fn.precision}")
        result = require_fluent_number(fn, field)
        assert result is fn
        event("outcome=pass_through")

    @given(value=_NON_FLUENT_NUMBER_VALUES, field=_FIELD_NAMES)
    def test_non_fluent_number_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-FluentNumber values always raise TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match="must be FluentNumber"):
            require_fluent_number(value, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_type_error(self, field: str) -> None:
        """field_name is embedded in the TypeError message."""
        with pytest.raises(TypeError) as exc_info:
            require_fluent_number(42, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_error")


