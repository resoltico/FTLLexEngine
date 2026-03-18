"""Property-based tests for ftllexengine.core.validators boundary validation primitives.

Properties verified:
- require_non_empty_str is idempotent on its output (strip(strip(x)) == strip(x))
- require_non_empty_str accepts any non-blank string and returns stripped form
- require_non_empty_str rejects all non-str types with TypeError
- require_non_empty_str rejects all whitespace-only strings with ValueError
- field_name is preserved verbatim in error messages
- require_positive_int returns value unchanged for all positive int inputs
- require_positive_int rejects all non-int types (including bool) with TypeError
- require_positive_int rejects zero and all negative ints with ValueError
- require_positive_int is idempotent: require_positive_int(require_positive_int(x)) == x
"""

from __future__ import annotations

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.core.validators import require_non_empty_str, require_positive_int

# Strategy for non-str values (covers common Python types)
_non_str_values = st.one_of(
    st.integers(),
    st.floats(allow_nan=False),
    st.binary(),
    st.booleans(),
    st.none(),
    st.lists(st.integers()),
    st.dictionaries(st.integers(), st.integers()),
)

# Strategy for non-blank strings: at least one non-whitespace character
_non_blank_strings = st.text(min_size=1).filter(lambda s: s.strip())

# Strategy for whitespace-only strings: non-empty but all whitespace
_whitespace_only_strings = st.text(
    alphabet=st.sampled_from(" \t\n\r\x0b\x0c"),
    min_size=1,
    max_size=20,
)


class TestRequireNonEmptyStrProperties:
    """Property-based tests for require_non_empty_str."""

    @given(value=_non_blank_strings, field_name=st.text(min_size=1))
    def test_returns_stripped_non_blank_string(self, value: str, field_name: str) -> None:
        """For any non-blank string, the result equals value.strip().

        Property: require_non_empty_str(x, f) == x.strip() for all non-blank x.
        """
        event(f"value_length={len(value)}")
        result = require_non_empty_str(value, field_name)
        assert result == value.strip()
        assert result  # result must be non-empty

    @given(value=_non_blank_strings, field_name=st.text(min_size=1))
    def test_output_is_idempotent(self, value: str, field_name: str) -> None:
        """Passing the output back through the validator returns the same value.

        Property: require_non_empty_str(require_non_empty_str(x, f), f) == require_non_empty_str(x, f)
        """
        event(f"has_surrounding_whitespace={value != value.strip()}")
        first = require_non_empty_str(value, field_name)
        second = require_non_empty_str(first, field_name)
        assert first == second

    @given(value=_non_str_values, field_name=st.text(min_size=1))
    def test_raises_type_error_for_non_str(
        self, value: object, field_name: str
    ) -> None:
        """TypeError is raised for any non-str input.

        Property: require_non_empty_str(x, f) raises TypeError for all x where type(x) != str.
        """
        type_name = type(value).__name__
        event(f"non_str_type={type_name}")
        with pytest.raises(TypeError) as exc_info:
            require_non_empty_str(value, field_name)
        msg = str(exc_info.value)
        assert field_name in msg
        assert type_name in msg

    @given(value=_whitespace_only_strings, field_name=st.text(min_size=1))
    def test_raises_value_error_for_whitespace_only(
        self, value: str, field_name: str
    ) -> None:
        """ValueError is raised for any whitespace-only string.

        Property: require_non_empty_str(x, f) raises ValueError for all x where x.strip() == ''.
        """
        event(f"whitespace_length={len(value)}")
        with pytest.raises(ValueError, match="cannot be blank") as exc_info:
            require_non_empty_str(value, field_name)
        assert field_name in str(exc_info.value)

    @given(
        value=_non_blank_strings,
        field_name=st.text(
            alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
            min_size=1,
            max_size=30,
        ),
    )
    def test_field_name_not_in_success_result(self, value: str, field_name: str) -> None:
        """On success, the return value is the stripped input, not the field_name.

        The field_name is only used in error messages; the return value is purely
        the stripped input.
        """
        event("outcome=success")
        result = require_non_empty_str(value, field_name)
        assert result == value.strip()


# ---------------------------------------------------------------------------
# Strategies for require_positive_int
# ---------------------------------------------------------------------------

_positive_ints = st.integers(min_value=1, max_value=10_000_000)
_non_positive_ints = st.integers(max_value=0)
_non_int_non_bool = st.one_of(
    st.floats(allow_nan=False),
    st.text(),
    st.binary(),
    st.none(),
    st.lists(st.integers()),
)


class TestRequirePositiveIntProperties:
    """Property-based tests for require_positive_int."""

    @given(value=_positive_ints, field_name=st.text(min_size=1))
    def test_returns_positive_int_unchanged(self, value: int, field_name: str) -> None:
        """For any positive int, the return value is identical to the input.

        Property: require_positive_int(x, f) == x for all x > 0.
        """
        event(f"value_magnitude={'large' if value > 100_000 else 'small'}")
        result = require_positive_int(value, field_name)
        assert result == value
        assert type(result) is int

    @given(value=_positive_ints, field_name=st.text(min_size=1))
    def test_output_is_idempotent(self, value: int, field_name: str) -> None:
        """Passing the output back through the validator returns the same value.

        Property: require_positive_int(require_positive_int(x, f), f) == x for all x > 0.
        """
        event(f"value={value}")
        first = require_positive_int(value, field_name)
        second = require_positive_int(first, field_name)
        assert first == second

    @given(value=_non_positive_ints, field_name=st.text(min_size=1))
    def test_raises_value_error_for_non_positive(
        self, value: int, field_name: str
    ) -> None:
        """ValueError is raised for zero and all negative integers.

        Property: require_positive_int(x, f) raises ValueError for all x <= 0.
        """
        event(f"non_positive={'zero' if value == 0 else 'negative'}")
        with pytest.raises(ValueError, match="must be positive"):
            require_positive_int(value, field_name)

    @given(value=_non_int_non_bool, field_name=st.text(min_size=1))
    def test_raises_type_error_for_non_int(
        self, value: object, field_name: str
    ) -> None:
        """TypeError is raised for any non-int type (excluding bool, tested separately).

        Property: require_positive_int(x, f) raises TypeError when type(x) not in {int}.
        """
        type_name = type(value).__name__
        event(f"non_int_type={type_name}")
        with pytest.raises(TypeError) as exc_info:
            require_positive_int(value, field_name)
        assert "must be int" in str(exc_info.value)

    @given(value=st.booleans(), field_name=st.text(min_size=1))
    def test_raises_type_error_for_bool(self, value: bool, field_name: str) -> None:
        """TypeError is raised for bool, even though bool is an int subtype.

        Property: require_positive_int(x, f) raises TypeError for all bool x.
        """
        event(f"bool_value={value}")
        with pytest.raises(TypeError, match="must be int, got bool"):
            require_positive_int(value, field_name)
