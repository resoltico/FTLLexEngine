"""Property-based tests for ftllexengine.core.validators boundary validation primitives.

Properties verified:
- require_positive_int returns value unchanged for all positive int inputs
- require_positive_int rejects all non-int types (including bool) with TypeError
- require_positive_int rejects zero and all negative ints with ValueError
- require_positive_int is idempotent: require_positive_int(require_positive_int(x)) == x
"""

from __future__ import annotations

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.core.validators import require_positive_int

# ---------------------------------------------------------------------------
# Strategies
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
        event(f"value_magnitude={'large' if value > 100_000 else 'small'}")
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
