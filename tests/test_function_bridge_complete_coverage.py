"""Complete coverage tests for runtime/function_bridge.py.

Targets uncovered line to achieve 100% coverage.
Covers:
- FluentNumber.__repr__ method
"""

from __future__ import annotations

from decimal import Decimal

from ftllexengine.runtime.function_bridge import FluentNumber


class TestFluentNumberRepr:
    """Test FluentNumber string representations."""

    def test_fluent_number_repr_integer(self) -> None:
        """FluentNumber.__repr__ returns detailed representation for integers."""
        fn = FluentNumber(value=42, formatted="42.00")

        repr_str = repr(fn)

        assert repr_str == "FluentNumber(value=42, formatted='42.00')"
        assert "value=42" in repr_str
        assert "formatted='42.00'" in repr_str

    def test_fluent_number_repr_float(self) -> None:
        """FluentNumber.__repr__ returns detailed representation for floats."""
        fn = FluentNumber(value=3.14, formatted="3.14")

        repr_str = repr(fn)

        assert repr_str == "FluentNumber(value=3.14, formatted='3.14')"
        assert "value=3.14" in repr_str
        assert "formatted='3.14'" in repr_str

    def test_fluent_number_repr_decimal(self) -> None:
        """FluentNumber.__repr__ returns detailed representation for Decimal."""
        fn = FluentNumber(value=Decimal("123.45"), formatted="123.45")

        repr_str = repr(fn)

        assert "value=Decimal" in repr_str
        assert "formatted='123.45'" in repr_str

    def test_fluent_number_str_vs_repr(self) -> None:
        """FluentNumber __str__ and __repr__ serve different purposes."""
        fn = FluentNumber(value=100, formatted="100.00")

        # __str__ returns formatted string for output
        assert str(fn) == "100.00"

        # __repr__ returns detailed representation for debugging
        assert repr(fn) == "FluentNumber(value=100, formatted='100.00')"
        assert str(fn) != repr(fn)
