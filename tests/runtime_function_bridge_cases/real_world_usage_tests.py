# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# REAL-WORLD USAGE TESTS
# ============================================================================


class TestRealWorldUsage:
    """Test realistic usage scenarios."""

    def test_number_formatting_function(self) -> None:
        """Test NUMBER-like function with real parameters."""
        registry = FunctionRegistry()

        def number_format(
            value: object,
            *,
            minimum_fraction_digits: int = 0,  # noqa: ARG001 - unused
            maximum_fraction_digits: int = 3,
            use_grouping: bool = False,
        ) -> str:
            formatted = f"{Decimal(str(value)):.{maximum_fraction_digits}f}"
            if use_grouping:
                # Simple grouping simulation
                parts = formatted.split(".")
                parts[0] = f"{int(parts[0]):,}"
                formatted = ".".join(parts)
            return formatted

        registry.register(number_format, ftl_name="NUMBER")

        # FTL: { NUMBER($price, minimumFractionDigits: 2, useGrouping: true) }
        result = registry.call(
            "NUMBER",
            [Decimal("1234.5")],
            {"minimumFractionDigits": 2, "useGrouping": True},
        )
        assert isinstance(result, str)
        assert "1,234" in result

    def test_datetime_formatting_function(self) -> None:
        """Test DATETIME-like function with style parameters."""
        registry = FunctionRegistry()

        def datetime_format(
            value: str, *, date_style: str = "short", time_style: str = "short"
        ) -> str:
            return f"{value} ({date_style}/{time_style})"

        registry.register(datetime_format, ftl_name="DATETIME")

        # FTL: { DATETIME($date, dateStyle: "long", timeStyle: "medium") }
        result = registry.call(
            "DATETIME",
            ["2024-01-15"],
            {"dateStyle": "long", "timeStyle": "medium"},
        )

        assert result == "2024-01-15 (long/medium)"
