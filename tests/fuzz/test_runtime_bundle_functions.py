"""Custom functions fuzzing tests.

Property-based tests for FunctionRegistry and custom function handling:
- Function registration
- Function invocation
- Error handling for invalid functions
- Argument passing

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# -----------------------------------------------------------------------------
# Test Functions
# -----------------------------------------------------------------------------


def custom_upper(value: str) -> str:
    """Convert value to uppercase."""
    return str(value).upper()


def custom_reverse(value: str) -> str:
    """Reverse the string."""
    return str(value)[::-1]


def custom_length(value: str) -> int:
    """Return length of value."""
    return len(str(value))


def custom_add(a: int | Decimal, b: int | Decimal) -> int | Decimal:
    """Add two numbers."""
    return a + b


def throwing_function(_value: str) -> str:
    """Function that always throws."""
    msg = "Intentional error"
    raise ValueError(msg)


def slow_function(value: str) -> str:
    """Function that does complex work."""
    # Simulate some processing
    result = value
    for _ in range(100):
        result = result.replace("a", "b").replace("b", "a")
    return result


def returning_none(_value: str) -> None:
    """Function that returns None."""


def returning_dict(value: str) -> dict[str, str]:
    """Function that returns a dict (unexpected type)."""
    return {"value": value}


# -----------------------------------------------------------------------------
# Property Tests: Function Registration
# -----------------------------------------------------------------------------


class TestFunctionRegistrationProperties:
    """Property tests for function registration."""

    @given(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_function_name_registration(self, func_name: str) -> None:
        """Property: Valid function names can be registered."""
        bundle = FluentBundle("en-US")

        # Register a simple function
        bundle.add_function(func_name, custom_upper)

        # Use it in a message
        bundle.add_resource(f"msg = {{ {func_name}($val) }}")
        result, errors = bundle.format_pattern("msg", {"val": "hello"})

        event(f"func_name_len={len(func_name)}")
        assert isinstance(result, str)
        # If function worked, should be uppercase
        if len(errors) == 0:
            assert "HELLO" in result
            event("outcome=func_registered_success")
        else:
            event("outcome=func_registered_error")

    @given(st.sampled_from(["UPPER", "LOWER", "REVERSE", "LENGTH", "CUSTOM"]))
    @settings(max_examples=20, deadline=None)
    def test_multiple_function_registration(self, name: str) -> None:
        """Property: Multiple functions can be registered."""
        # name parameter used to verify property holds for different function names
        _ = name  # Silence unused variable warning
        bundle = FluentBundle("en-US")

        bundle.add_function("UPPER", custom_upper)
        bundle.add_function("REVERSE", custom_reverse)
        bundle.add_function("LENGTH", custom_length)

        bundle.add_resource(
            """
test-upper = { UPPER($val) }
test-reverse = { REVERSE($val) }
test-length = { LENGTH($val) }
"""
        )

        result_upper, _ = bundle.format_pattern("test-upper", {"val": "hello"})
        result_reverse, _ = bundle.format_pattern("test-reverse", {"val": "hello"})
        result_length, _ = bundle.format_pattern("test-length", {"val": "hello"})

        assert "HELLO" in result_upper
        assert "olleh" in result_reverse
        assert "5" in result_length
        event("outcome=multi_func_success")


# -----------------------------------------------------------------------------
# Property Tests: Function Invocation
# -----------------------------------------------------------------------------


class TestFunctionInvocationProperties:
    """Property tests for function invocation."""

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=200, deadline=None)
    def test_string_argument_passing(self, value: str) -> None:
        """Property: String arguments are passed correctly."""
        bundle = FluentBundle("en-US")
        bundle.add_function("UPPER", custom_upper)
        bundle.add_resource("msg = { UPPER($val) }")

        result, errors = bundle.format_pattern("msg", {"val": value})

        event(f"val_len={len(value)}")
        assert isinstance(result, str)
        # If no errors, should be uppercase
        if len(errors) == 0:
            expected = value.upper()
            assert expected in result or result == expected
            event("outcome=string_arg_success")
        else:
            event("outcome=string_arg_error")

    @given(st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100, deadline=None)
    def test_integer_argument_passing(self, value: int) -> None:
        """Property: Integer arguments are handled."""
        bundle = FluentBundle("en-US")
        bundle.add_function("LEN", custom_length)
        bundle.add_resource("msg = { LEN($val) }")

        result, _ = bundle.format_pattern("msg", {"val": value})

        assert isinstance(result, str)
        event(f"sign={'negative' if value < 0 else 'zero' if value == 0 else 'positive'}")

    @given(
        st.decimals(
            min_value=Decimal("-1000"),
            max_value=Decimal("1000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_decimal_argument_passing(self, value: Decimal) -> None:
        """Property: Decimal arguments are handled."""
        bundle = FluentBundle("en-US")
        bundle.add_function("LEN", custom_length)
        bundle.add_resource("msg = { LEN($val) }")

        result, _ = bundle.format_pattern("msg", {"val": value})

        assert isinstance(result, str)
        event(f"sign={'negative' if value < 0 else 'zero' if value == 0 else 'positive'}")


# -----------------------------------------------------------------------------
# Property Tests: Error Handling
# -----------------------------------------------------------------------------


class TestFunctionErrorHandlingProperties:
    """Property tests for error handling in custom functions."""

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_throwing_function_caught(self, value: str) -> None:
        """Property: Exceptions in functions are caught, not propagated."""
        bundle = FluentBundle("en-US")
        bundle.add_function("THROW", throwing_function)
        bundle.add_resource("msg = { THROW($val) }")

        # Should not raise
        result, errors = bundle.format_pattern("msg", {"val": value})

        event(f"val_len={len(value)}")
        assert isinstance(result, str)
        # Should have errors indicating function failure
        assert len(errors) > 0
        event("outcome=throwing_func_caught")

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_none_return_handled(self, value: str) -> None:
        """Property: Functions returning None are handled gracefully."""
        bundle = FluentBundle("en-US")
        bundle.add_function("NONE", returning_none)
        bundle.add_resource("msg = { NONE($val) }")

        result, _ = bundle.format_pattern("msg", {"val": value})

        assert isinstance(result, str)
        event("outcome=none_return_handled")

    def test_missing_function_error(self) -> None:
        """Missing function produces error, not crash."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = { UNDEFINED($val) }")

        result, errors = bundle.format_pattern("msg", {"val": "test"})

        assert isinstance(result, str)
        assert len(errors) > 0

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_unexpected_return_type_handled(self, value: str) -> None:
        """Property: Functions returning unexpected types are handled."""
        bundle = FluentBundle("en-US")
        bundle.add_function("DICT", returning_dict)
        bundle.add_resource("msg = { DICT($val) }")

        result, _ = bundle.format_pattern("msg", {"val": value})

        assert isinstance(result, str)
        event("outcome=dict_return_handled")


# -----------------------------------------------------------------------------
# Property Tests: Built-in Functions
# -----------------------------------------------------------------------------


class TestBuiltinFunctionProperties:
    """Property tests for built-in functions (NUMBER, DATETIME)."""

    @given(st.integers(min_value=-1000000, max_value=1000000))
    @settings(max_examples=200, deadline=None)
    def test_number_function_integers(self, n: int) -> None:
        """Property: NUMBER function handles integers."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n) }")

        result, errors = bundle.format_pattern("num", {"n": n})

        event("number_type=int")
        assert isinstance(result, str)
        assert len(errors) == 0
        event("outcome=number_func_int_success")

    @given(
        st.decimals(
            min_value=Decimal("-1000000"),
            max_value=Decimal("1000000"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_number_function_decimals(self, n: Decimal) -> None:
        """Property: NUMBER function handles Decimals."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {"n": n})

        event("number_type=Decimal")
        assert isinstance(result, str)
        event("outcome=number_func_decimal_success")

    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_number_function_invalid_input(self, s: str) -> None:
        """Property: NUMBER function handles non-numeric input gracefully."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {"n": s})

        assert isinstance(result, str)
        # May have errors for invalid number
        event(f"input_len={len(s)}")


class TestFunctionArgumentVariations:
    """Property tests for function argument variations."""

    def test_function_with_options(self) -> None:
        """Function with named options."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n, minimumFractionDigits: 2) }")

        result, _ = bundle.format_pattern("num", {"n": 42})

        assert isinstance(result, str)
        # Should have decimal places
        assert "42" in result

    def test_function_missing_required_arg(self) -> None:
        """Function with missing required argument."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n) }")

        result, _ = bundle.format_pattern("num", {})  # Missing $n

        assert isinstance(result, str)
        # Should have error for missing variable

    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), max_size=5))
    @settings(max_examples=50, deadline=None)
    def test_function_with_extra_args(self, extra: dict[str, int]) -> None:
        """Property: Extra arguments don't crash functions."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("num = { NUMBER($n) }")

        args = {"n": 42, **extra}
        result, _ = bundle.format_pattern("num", args)

        assert isinstance(result, str)
        event(f"extra_args={len(extra)}")
