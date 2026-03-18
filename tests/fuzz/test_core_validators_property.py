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
"""

from __future__ import annotations

import string

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.core.validators import require_non_empty_str, require_positive_int

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
