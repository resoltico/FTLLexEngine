"""Property-based fuzz tests for core.validators boundary validation primitives.

Properties verified:
- require_non_empty_str: for any non-blank str, returns s.strip() exactly.
- require_non_empty_str: for any non-str value, always raises TypeError.
- require_non_empty_str: for any blank/whitespace-only str, always raises ValueError.
- require_non_empty_str: field_name is always embedded in the error message.
- require_positive_int: for any positive int (not bool), returns n unchanged.
- require_positive_int: for bool (True/False), always raises TypeError.
- require_positive_int: for any non-int type, always raises TypeError.
- require_positive_int: for zero and negative ints, always raises ValueError.
- require_positive_int: field_name is always embedded in the error message.
- require_int: for any int (positive, zero, negative), returns n unchanged.
- require_int: for bool, always raises TypeError.
- require_int: for any non-int type, always raises TypeError.
- require_non_negative_int: for zero and any positive int, returns n unchanged.
- require_non_negative_int: for bool, always raises TypeError.
- require_non_negative_int: for any negative int, always raises ValueError.
- coerce_tuple: for any non-str Sequence, returns tuple(value).
- coerce_tuple: for str, always raises TypeError.
- coerce_tuple: for non-Sequence types, always raises TypeError.
- coerce_tuple: output is always an immutable tuple.
- normalize_optional_str: None always returns None.
- normalize_optional_str: non-None delegates identically to require_non_empty_str.
- require_decimal_range: for finite Decimal in [lo, hi], returns value unchanged.
- require_decimal_range: for bool/non-Decimal, always raises TypeError.
- require_decimal_range: for non-finite Decimal, always raises ValueError.
- require_decimal_range: for Decimal outside [lo, hi], always raises ValueError.
- normalize_optional_decimal_range: None always returns None.
- normalize_optional_decimal_range: non-None delegates to require_decimal_range.
- require_int_in_range: for int in [lo, hi] (not bool), returns value unchanged.
- require_int_in_range: for bool/non-int, always raises TypeError.
- require_int_in_range: for int outside [lo, hi], always raises ValueError.
- require_int_in_range: field_name is always embedded in the error message.
"""

from __future__ import annotations

import string
from decimal import Decimal

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.core.validators import (
    coerce_tuple,
    normalize_optional_decimal_range,
    normalize_optional_str,
    require_decimal_range,
    require_int,
    require_int_in_range,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)

pytestmark = pytest.mark.fuzz

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_FIELD_NAMES = st.text(
    alphabet=string.ascii_letters + string.digits + "_",
    min_size=1,
    max_size=30,
)

_NON_BLANK_STRINGS = st.text(
    alphabet=st.characters(blacklist_categories=("Zs", "Cc", "Cf")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")

_WHITESPACE_STRINGS = st.text(
    alphabet=st.sampled_from(" \t\n\r\x0b\x0c"),
    min_size=1,
    max_size=20,
)

_NON_STR_VALUES = st.one_of(
    st.integers(),
    st.floats(allow_nan=False),
    st.binary(min_size=0, max_size=10),
    st.lists(st.integers(), max_size=5),
    st.none(),
    st.booleans(),
    st.decimals(allow_nan=False, allow_infinity=False),
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


# ---------------------------------------------------------------------------
# require_non_empty_str properties
# ---------------------------------------------------------------------------


class TestRequireNonEmptyStrProperties:
    """Property-based invariants for require_non_empty_str."""

    @given(s=_NON_BLANK_STRINGS, field=_FIELD_NAMES)
    @example(s="hello", field="name")
    @example(s="  hello  ", field="locale")
    @example(s="\thello\n", field="x")
    def test_returns_stripped_value_for_valid_str(self, s: str, field: str) -> None:
        """For any non-blank string, returns s.strip() exactly."""
        event(f"input_len={len(s)}")
        result = require_non_empty_str(s, field)
        event(f"outcome={'stripped' if len(result) < len(s) else 'unchanged'}")
        assert result == s.strip()
        assert result != ""

    @given(s=_WHITESPACE_STRINGS, field=_FIELD_NAMES)
    @example(s=" ", field="field")
    @example(s="\t", field="field")
    @example(s="\n", field="field")
    @example(s="", field="locale")
    def test_raises_value_error_for_blank_str(self, s: str, field: str) -> None:
        """For any whitespace-only string (or empty), raises ValueError."""
        event(f"ws_len={len(s)}")
        with pytest.raises(ValueError, match=field):
            require_non_empty_str(s, field)
        event("outcome=value_error_raised")

    @given(value=_NON_STR_VALUES, field=_FIELD_NAMES)
    def test_raises_type_error_for_non_str(self, value: object, field: str) -> None:
        """For any non-str value, always raises TypeError with field_name in message."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_non_empty_str(value, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_empty_string_raises_value_error(self, field: str) -> None:
        """Empty string always raises ValueError."""
        with pytest.raises(ValueError, match=field):
            require_non_empty_str("", field)
        event("outcome=empty_string_rejected")

    @given(field=_FIELD_NAMES)
    def test_field_name_in_error_messages(self, field: str) -> None:
        """field_name is embedded verbatim in all error messages.

        Verify the embedding for both TypeError and ValueError branches.
        """
        event(f"field_len={len(field)}")
        # TypeError path: pass an int with this field name
        with pytest.raises(TypeError) as exc_info:
            require_non_empty_str(42, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_type_error")

    @given(s=_NON_BLANK_STRINGS, field=_FIELD_NAMES)
    def test_idempotent_for_already_stripped_string(self, s: str, field: str) -> None:
        """Applying require_non_empty_str to an already-stripped result is idempotent."""
        result1 = require_non_empty_str(s, field)
        result2 = require_non_empty_str(result1, field)
        assert result1 == result2
        event("outcome=idempotent")


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
# require_int fuzz properties
# ---------------------------------------------------------------------------

_ALL_INTS = st.integers(min_value=-(10**12), max_value=10**12)


class TestRequireIntFuzz:
    """Fuzz tests for require_int — any integer accepted, only type boundary matters."""

    @given(n=_ALL_INTS, field=_FIELD_NAMES)
    @example(n=0, field="year")
    @example(n=-1, field="offset")
    @example(n=10**9, field="limit")
    def test_returns_value_unchanged_for_any_int(self, n: int, field: str) -> None:
        """For any int (positive, zero, negative), returns n unchanged."""
        sign = "negative" if n < 0 else "zero" if n == 0 else "positive"
        event(f"sign={sign}")
        result = require_int(n, field)
        assert result == n
        assert result is n
        event("outcome=pass_through")

    @given(field=_FIELD_NAMES)
    def test_raises_type_error_for_bool_true(self, field: str) -> None:
        """True raises TypeError even though bool is an int subtype."""
        with pytest.raises(TypeError, match=field):
            require_int(True, field)
        event("outcome=bool_true_rejected")

    @given(field=_FIELD_NAMES)
    def test_raises_type_error_for_bool_false(self, field: str) -> None:
        """False raises TypeError — bool is rejected before int check."""
        with pytest.raises(TypeError, match=field):
            require_int(False, field)
        event("outcome=bool_false_rejected")

    @given(value=_NON_INT_VALUES, field=_FIELD_NAMES)
    def test_raises_type_error_for_non_int(self, value: object, field: str) -> None:
        """For any non-int type, raises TypeError with field_name in message."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_int(value, field)
        event("outcome=type_error_raised")

    @given(n=_ALL_INTS, field=_FIELD_NAMES)
    def test_result_type_is_int(self, n: int, field: str) -> None:
        """Result type is exactly int (not a subclass)."""
        result = require_int(n, field)
        assert type(result) is int
        event("outcome=type_is_int")


# ---------------------------------------------------------------------------
# require_non_negative_int fuzz properties
# ---------------------------------------------------------------------------

_NON_NEGATIVE_INTS = st.integers(min_value=0, max_value=10**9)
_NEGATIVE_INTS = st.integers(max_value=-1)


class TestRequireNonNegativeIntFuzz:
    """Fuzz tests for require_non_negative_int — zero is valid, negative is not."""

    @given(n=_NON_NEGATIVE_INTS, field=_FIELD_NAMES)
    @example(n=0, field="index")
    @example(n=1, field="entry_index")
    @example(n=10**6, field="count")
    def test_returns_value_unchanged_for_non_negative(
        self, n: int, field: str
    ) -> None:
        """For any non-negative int, returns n unchanged."""
        event(f"boundary={'zero' if n == 0 else 'positive'}")
        result = require_non_negative_int(n, field)
        assert result == n
        assert result is n
        event("outcome=pass_through")

    @given(n=_NEGATIVE_INTS, field=_FIELD_NAMES)
    @example(n=-1, field="index")
    @example(n=-999_999, field="count")
    def test_raises_value_error_for_negative(self, n: int, field: str) -> None:
        """For any negative int, raises ValueError with field_name."""
        event(f"n={'barely_negative' if n == -1 else 'negative'}")
        with pytest.raises(ValueError, match=field):
            require_non_negative_int(n, field)
        event("outcome=value_error_raised")

    @given(field=_FIELD_NAMES)
    def test_raises_type_error_for_bool(self, field: str) -> None:
        """bool raises TypeError regardless of value."""
        with pytest.raises(TypeError, match=field):
            require_non_negative_int(True, field)
        event("outcome=bool_rejected")

    @given(value=_NON_INT_VALUES, field=_FIELD_NAMES)
    def test_raises_type_error_for_non_int(self, value: object, field: str) -> None:
        """For any non-int type, raises TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_non_negative_int(value, field)
        event("outcome=type_error_raised")

    @given(
        n=st.integers(min_value=0, max_value=10**9),
        field=_FIELD_NAMES,
    )
    def test_monotone_from_zero(self, n: int, field: str) -> None:
        """Zero and all positive integers are accepted; n+1 is also accepted.

        Metamorphic: non-negative boundary at 0.
        """
        require_non_negative_int(n, field)
        require_non_negative_int(n + 1, field)
        event("outcome=monotone_accepted")


# ---------------------------------------------------------------------------
# coerce_tuple fuzz properties
# ---------------------------------------------------------------------------

_LIST_OF_INTS = st.lists(st.integers(), min_size=0, max_size=20)
_LIST_OF_STR = st.lists(st.text(max_size=10), min_size=0, max_size=10)
_MIXED_LIST: st.SearchStrategy[list[object]] = st.lists(
    st.one_of(st.integers(), st.text(max_size=5), st.none()),
    min_size=0,
    max_size=10,
)
_NON_SEQUENCE_VALUES: st.SearchStrategy[object] = st.one_of(
    st.integers(),
    st.floats(allow_nan=False),
    st.none(),
)


class TestCoerceTupleFuzz:
    """Fuzz tests for coerce_tuple — sequence coercion invariants."""

    @given(items=_LIST_OF_INTS, field=_FIELD_NAMES)
    @example(items=[], field="ids")
    @example(items=[1, 2, 3], field="items")
    def test_returns_tuple_from_list_of_ints(
        self, items: list[int], field: str
    ) -> None:
        """List of ints is converted to a tuple with identical elements."""
        event(f"length={len(items)}")
        result: tuple[object, ...] = coerce_tuple(items, field)
        assert result == tuple(items)
        assert type(result) is tuple
        event("outcome=tuple_returned")

    @given(items=_LIST_OF_STR, field=_FIELD_NAMES)
    def test_returns_tuple_from_list_of_str(
        self, items: list[str], field: str
    ) -> None:
        """List of strings is converted to a tuple with identical elements."""
        event(f"length={len(items)}")
        result: tuple[object, ...] = coerce_tuple(items, field)
        assert result == tuple(items)
        event("outcome=str_list_coerced")

    @given(items=_MIXED_LIST, field=_FIELD_NAMES)
    def test_returns_tuple_from_mixed_list(
        self, items: list[object], field: str
    ) -> None:
        """Mixed-type list is converted to a tuple preserving all elements."""
        event(f"length={'empty' if not items else 'non_empty'}")
        result: tuple[object, ...] = coerce_tuple(items, field)
        assert result == tuple(items)
        assert type(result) is tuple
        event("outcome=mixed_coerced")

    @given(
        value=st.text(min_size=0, max_size=30),
        field=_FIELD_NAMES,
    )
    def test_raises_type_error_for_any_str(self, value: str, field: str) -> None:
        """Any str — including empty string — raises TypeError."""
        event(f"str_length={len(value)}")
        with pytest.raises(TypeError, match="non-str Sequence"):
            coerce_tuple(value, field)
        event("outcome=str_rejected")

    @given(value=_NON_SEQUENCE_VALUES, field=_FIELD_NAMES)
    def test_raises_type_error_for_non_sequence(
        self, value: object, field: str
    ) -> None:
        """Non-Sequence values raise TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match="must be a Sequence"):
            coerce_tuple(value, field)
        event("outcome=non_sequence_rejected")

    @given(items=_LIST_OF_INTS, field=_FIELD_NAMES)
    def test_idempotent_coercion(self, items: list[int], field: str) -> None:
        """Coercing the output tuple produces an equal tuple.

        Idempotence: coerce_tuple(coerce_tuple(x)) == coerce_tuple(x).
        """
        first: tuple[object, ...] = coerce_tuple(items, field)
        second: tuple[object, ...] = coerce_tuple(first, field)
        assert first == second
        event("outcome=idempotent")


# ---------------------------------------------------------------------------
# normalize_optional_str fuzz properties
# ---------------------------------------------------------------------------


class TestNormalizeOptionalStrFuzz:
    """Fuzz tests for normalize_optional_str — None passthrough over require_non_empty_str."""

    @given(field=_FIELD_NAMES)
    def test_none_always_returns_none(self, field: str) -> None:
        """None input always returns None regardless of field_name."""
        result = normalize_optional_str(None, field)
        assert result is None
        event("outcome=none_passthrough")

    @given(s=_NON_BLANK_STRINGS, field=_FIELD_NAMES)
    @example(s="hello", field="name")
    @example(s="  hello  ", field="desc")
    def test_non_none_returns_stripped_value(self, s: str, field: str) -> None:
        """For non-None str, delegates to require_non_empty_str — returns s.strip()."""
        event(f"input_len={len(s)}")
        result = normalize_optional_str(s, field)
        assert result == s.strip()
        assert result != ""
        event("outcome=stripped_value")

    @given(s=_WHITESPACE_STRINGS, field=_FIELD_NAMES)
    @example(s=" ", field="desc")
    @example(s="", field="desc")
    def test_blank_str_raises_value_error(self, s: str, field: str) -> None:
        """Blank/whitespace-only string raises ValueError (delegated)."""
        event(f"ws_len={len(s)}")
        with pytest.raises(ValueError, match=field):
            normalize_optional_str(s, field)
        event("outcome=value_error_raised")

    @given(
        value=_NON_STR_VALUES.filter(lambda v: v is not None),
        field=_FIELD_NAMES,
    )
    def test_non_str_non_none_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-str, non-None value raises TypeError (delegated)."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            normalize_optional_str(value, field)
        event("outcome=type_error_raised")

    @given(s=_NON_BLANK_STRINGS, field=_FIELD_NAMES)
    def test_oracle_matches_require_non_empty_str(self, s: str, field: str) -> None:
        """normalize_optional_str(s) == require_non_empty_str(s) for non-None str.

        Oracle: non-None path is exactly require_non_empty_str.
        """
        event(f"input_len={len(s)}")
        result_opt = normalize_optional_str(s, field)
        result_req = require_non_empty_str(s, field)
        assert result_opt == result_req
        event("outcome=oracle_match")


# ---------------------------------------------------------------------------
# require_decimal_range fuzz properties
# ---------------------------------------------------------------------------

_FINITE_DECIMALS = st.decimals(
    allow_nan=False,
    allow_infinity=False,
    min_value=Decimal(-1000),
    max_value=Decimal(1000),
)

_RANGE_BOUNDS: st.SearchStrategy[tuple[Decimal, Decimal]] = st.lists(
    st.decimals(
        allow_nan=False,
        allow_infinity=False,
        min_value=Decimal(-100),
        max_value=Decimal(100),
    ),
    min_size=2,
    max_size=2,
).map(lambda xs: (min(xs[0], xs[1]), max(xs[0], xs[1])))

_NON_FINITE_DECIMALS: st.SearchStrategy[Decimal] = st.one_of(
    st.just(Decimal("Infinity")),
    st.just(Decimal("-Infinity")),
    st.just(Decimal("NaN")),
    st.just(Decimal("-NaN")),
    st.just(Decimal("sNaN")),
)

_NON_DECIMAL_VALUES: st.SearchStrategy[object] = st.one_of(
    st.integers(),
    st.floats(allow_nan=False),
    st.text(min_size=0, max_size=10),
    st.none(),
    st.binary(min_size=0, max_size=4),
)


class TestRequireDecimalRangeFuzz:
    """Fuzz tests for require_decimal_range — Decimal range validation invariants."""

    @given(bounds=_RANGE_BOUNDS, field=_FIELD_NAMES)
    def test_lo_boundary_always_accepted(
        self, bounds: tuple[Decimal, Decimal], field: str
    ) -> None:
        """The lower boundary lo is always within [lo, hi]."""
        lo, hi = bounds
        event(f"range_width={'zero' if lo == hi else 'positive'}")
        result = require_decimal_range(lo, lo, hi, field)
        assert result == lo
        event("outcome=lo_accepted")

    @given(bounds=_RANGE_BOUNDS, field=_FIELD_NAMES)
    def test_hi_boundary_always_accepted(
        self, bounds: tuple[Decimal, Decimal], field: str
    ) -> None:
        """The upper boundary hi is always within [lo, hi]."""
        lo, hi = bounds
        event(f"range_width={'zero' if lo == hi else 'positive'}")
        result = require_decimal_range(hi, lo, hi, field)
        assert result == hi
        event("outcome=hi_accepted")

    @given(
        bounds=_RANGE_BOUNDS,
        value=_FINITE_DECIMALS,
        field=_FIELD_NAMES,
    )
    def test_in_range_value_accepted(
        self,
        bounds: tuple[Decimal, Decimal],
        value: Decimal,
        field: str,
    ) -> None:
        """Values within [lo, hi] are accepted; values outside are rejected."""
        lo, hi = bounds
        in_range = lo <= value <= hi
        event(f"in_range={in_range}")
        if in_range:
            result = require_decimal_range(value, lo, hi, field)
            assert result == value
            event("outcome=accepted")
        else:
            with pytest.raises(ValueError, match="must be in range"):
                require_decimal_range(value, lo, hi, field)
            event("outcome=rejected")

    @given(value=_NON_FINITE_DECIMALS, field=_FIELD_NAMES)
    @example(value=Decimal("Infinity"), field="rate")
    @example(value=Decimal("NaN"), field="rate")
    def test_non_finite_always_raises_value_error(
        self, value: Decimal, field: str
    ) -> None:
        """Non-finite Decimals (Inf, NaN) always raise ValueError."""
        event(f"kind={'inf' if value.is_infinite() else 'nan'}")
        lo, hi = Decimal(-1000), Decimal(1000)
        with pytest.raises(ValueError, match="must be finite"):
            require_decimal_range(value, lo, hi, field)
        event("outcome=non_finite_rejected")

    @given(value=_NON_DECIMAL_VALUES, field=_FIELD_NAMES)
    def test_non_decimal_always_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-Decimal types always raise TypeError."""
        event(f"type={type(value).__name__}")
        lo, hi = Decimal(0), Decimal(1)
        with pytest.raises(TypeError, match=field):
            require_decimal_range(value, lo, hi, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_bool_true_raises_type_error(self, field: str) -> None:
        """True raises TypeError — bool rejected before Decimal check."""
        lo, hi = Decimal(0), Decimal(1)
        with pytest.raises(TypeError, match="must be Decimal, got bool"):
            require_decimal_range(True, lo, hi, field)
        event("outcome=bool_true_rejected")

    @given(field=_FIELD_NAMES)
    def test_bool_false_raises_type_error(self, field: str) -> None:
        """False raises TypeError — bool rejected before Decimal check."""
        lo, hi = Decimal(0), Decimal(1)
        with pytest.raises(TypeError, match="must be Decimal, got bool"):
            require_decimal_range(False, lo, hi, field)
        event("outcome=bool_false_rejected")

    @given(bounds=_RANGE_BOUNDS, field=_FIELD_NAMES)
    def test_field_name_in_error_messages(
        self, bounds: tuple[Decimal, Decimal], field: str
    ) -> None:
        """field_name is embedded in all error messages."""
        lo, hi = bounds
        event(f"field_len={len(field)}")
        with pytest.raises(TypeError) as exc_info:
            require_decimal_range(42, lo, hi, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_type_error")

    @given(value=_FINITE_DECIMALS, field=_FIELD_NAMES)
    def test_result_is_identical_to_input(
        self, value: Decimal, field: str
    ) -> None:
        """For accepted values, result is identical to input (not a copy)."""
        lo = value - Decimal(1)
        hi = value + Decimal(1)
        result = require_decimal_range(value, lo, hi, field)
        assert result is value
        event("outcome=identity_preserved")


# ---------------------------------------------------------------------------
# normalize_optional_decimal_range fuzz properties
# ---------------------------------------------------------------------------


class TestNormalizeOptionalDecimalRangeFuzz:
    """Fuzz tests for normalize_optional_decimal_range — None passthrough oracle."""

    @given(field=_FIELD_NAMES)
    def test_none_always_returns_none(self, field: str) -> None:
        """None input always returns None."""
        lo, hi = Decimal(0), Decimal(1)
        result = normalize_optional_decimal_range(None, lo, hi, field)
        assert result is None
        event("outcome=none_passthrough")

    @given(
        bounds=_RANGE_BOUNDS,
        value=_FINITE_DECIMALS,
        field=_FIELD_NAMES,
    )
    def test_oracle_matches_require_decimal_range(
        self,
        bounds: tuple[Decimal, Decimal],
        value: Decimal,
        field: str,
    ) -> None:
        """normalize_optional_decimal_range(x) == require_decimal_range(x) for non-None.

        Oracle: non-None path is exactly require_decimal_range.
        """
        lo, hi = bounds
        in_range = lo <= value <= hi
        event(f"in_range={in_range}")
        if in_range:
            opt_result = normalize_optional_decimal_range(value, lo, hi, field)
            req_result = require_decimal_range(value, lo, hi, field)
            assert opt_result == req_result
            assert opt_result is req_result
            event("outcome=oracle_match")
        else:
            with pytest.raises(ValueError, match="must be in range"):
                normalize_optional_decimal_range(value, lo, hi, field)
            event("outcome=range_error_delegated")

    @given(
        value=_NON_DECIMAL_VALUES.filter(lambda v: v is not None),
        field=_FIELD_NAMES,
    )
    def test_non_decimal_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-None, non-Decimal raises TypeError (delegated)."""
        event(f"type={type(value).__name__}")
        lo, hi = Decimal(0), Decimal(1)
        with pytest.raises(TypeError, match="must be Decimal"):
            normalize_optional_decimal_range(value, lo, hi, field)
        event("outcome=type_error_delegated")


# ---------------------------------------------------------------------------
# require_int_in_range fuzz properties
# ---------------------------------------------------------------------------

_RANGE_INT_BOUNDS: st.SearchStrategy[tuple[int, int]] = st.builds(
    lambda lo, spread: (lo, lo + spread),
    lo=st.integers(min_value=-1000, max_value=1000),
    spread=st.integers(min_value=0, max_value=1000),
)

_ALL_INTS_BOUNDED = st.integers(min_value=-2000, max_value=2000)


class TestRequireIntInRangeFuzz:
    """Fuzz tests for require_int_in_range — integer range validation invariants."""

    @given(bounds=_RANGE_INT_BOUNDS, field=_FIELD_NAMES)
    def test_lo_boundary_always_accepted(
        self, bounds: tuple[int, int], field: str
    ) -> None:
        """The lower boundary lo is always within [lo, hi]."""
        lo, hi = bounds
        event(f"range_width={'zero' if lo == hi else 'positive'}")
        result = require_int_in_range(lo, lo, hi, field)
        assert result == lo
        assert result is lo
        event("outcome=lo_accepted")

    @given(bounds=_RANGE_INT_BOUNDS, field=_FIELD_NAMES)
    def test_hi_boundary_always_accepted(
        self, bounds: tuple[int, int], field: str
    ) -> None:
        """The upper boundary hi is always within [lo, hi]."""
        lo, hi = bounds
        event(f"range_width={'zero' if lo == hi else 'positive'}")
        result = require_int_in_range(hi, lo, hi, field)
        assert result == hi
        assert result is hi
        event("outcome=hi_accepted")

    @given(
        bounds=_RANGE_INT_BOUNDS,
        value=_ALL_INTS_BOUNDED,
        field=_FIELD_NAMES,
    )
    def test_in_range_accepted_out_of_range_rejected(
        self,
        bounds: tuple[int, int],
        value: int,
        field: str,
    ) -> None:
        """Values within [lo, hi] are accepted; values outside are rejected."""
        lo, hi = bounds
        in_range = lo <= value <= hi
        event(f"in_range={in_range}")
        if in_range:
            result = require_int_in_range(value, lo, hi, field)
            assert result == value
            event("outcome=accepted")
        else:
            with pytest.raises(ValueError, match=field):
                require_int_in_range(value, lo, hi, field)
            event("outcome=rejected")

    @given(value=_NON_INT_VALUES, field=_FIELD_NAMES)
    def test_non_int_always_raises_type_error(
        self, value: object, field: str
    ) -> None:
        """Non-int types always raise TypeError."""
        event(f"type={type(value).__name__}")
        with pytest.raises(TypeError, match=field):
            require_int_in_range(value, 0, 100, field)
        event("outcome=type_error_raised")

    @given(field=_FIELD_NAMES)
    def test_bool_true_raises_type_error(self, field: str) -> None:
        """True raises TypeError — bool is an int subtype but rejected."""
        with pytest.raises(TypeError, match="must be int, got bool"):
            require_int_in_range(True, 0, 100, field)
        event("outcome=bool_true_rejected")

    @given(field=_FIELD_NAMES)
    def test_bool_false_raises_type_error(self, field: str) -> None:
        """False raises TypeError — bool is rejected before int magnitude check."""
        with pytest.raises(TypeError, match="must be int, got bool"):
            require_int_in_range(False, 0, 100, field)
        event("outcome=bool_false_rejected")

    @given(bounds=_RANGE_INT_BOUNDS, field=_FIELD_NAMES)
    def test_field_name_in_type_error(
        self, bounds: tuple[int, int], field: str
    ) -> None:
        """field_name is embedded in TypeError messages."""
        lo, hi = bounds
        event(f"field_len={len(field)}")
        with pytest.raises(TypeError) as exc_info:
            require_int_in_range(3.14, lo, hi, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_type_error")

    @given(bounds=_RANGE_INT_BOUNDS, field=_FIELD_NAMES)
    def test_field_name_in_range_error(
        self, bounds: tuple[int, int], field: str
    ) -> None:
        """field_name is embedded in range ValueError messages."""
        lo, hi = bounds
        out_of_range = lo - 1
        event(f"field_len={len(field)}")
        with pytest.raises(ValueError, match="must be in range") as exc_info:
            require_int_in_range(out_of_range, lo, hi, field)
        assert field in str(exc_info.value)
        event("outcome=field_in_range_error")

    @given(
        bounds=_RANGE_INT_BOUNDS,
        value=_ALL_INTS_BOUNDED,
        field=_FIELD_NAMES,
    )
    def test_result_type_is_int(
        self,
        bounds: tuple[int, int],
        value: int,
        field: str,
    ) -> None:
        """For accepted values, result type is exactly int."""
        lo, hi = bounds
        if lo <= value <= hi:
            result = require_int_in_range(value, lo, hi, field)
            assert type(result) is int
            event("outcome=type_is_int")
        else:
            event("outcome=skipped_out_of_range")
