"""Integration tests for camelCase function parameters (FTL spec compliance).

Verifies that NUMBER and DATETIME functions accept camelCase parameter names
per ECMA-402 specification, with automatic conversion to Python snake_case.
"""

from datetime import UTC, datetime

from ftllexengine import FluentBundle


class TestNumberCamelCase:
    """Test NUMBER function with camelCase parameters."""

    def test_minimum_fraction_digits_camelcase(self) -> None:
        """NUMBER accepts minimumFractionDigits in camelCase."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("price", {"amount": 19.5})
        assert "19.50" in result
        assert errors == ()

    def test_minimum_fraction_digits_snakecase(self) -> None:
        """NUMBER accepts minimum_fraction_digits in snake_case (backward compat)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("price = { NUMBER($amount, minimum_fraction_digits: 2) }")
        result, errors = bundle.format_pattern("price", {"amount": 19.5})
        assert "19.50" in result
        assert errors == ()

    def test_maximum_fraction_digits_camelcase(self) -> None:
        """NUMBER accepts maximumFractionDigits in camelCase."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("percent = { NUMBER($ratio, maximumFractionDigits: 0) }")
        result, errors = bundle.format_pattern("percent", {"ratio": 42.789})
        assert "43" in result or "42" in result
        assert errors == ()

    def test_multiple_camelcase_params(self) -> None:
        """NUMBER accepts multiple camelCase parameters."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            "val = { NUMBER($n, minimumFractionDigits: 2, maximumFractionDigits: 4) }"
        )
        result, errors = bundle.format_pattern("val", {"n": 123.456})
        assert "123.456" in result or "123.46" in result
        assert errors == ()


class TestDateTimeCamelCase:
    """Test DATETIME function with camelCase parameters."""

    def test_date_style_camelcase(self) -> None:
        """DATETIME accepts dateStyle in camelCase."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource('date = { DATETIME($time, dateStyle: "short") }')

        dt = datetime(2025, 1, 15, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"time": dt})

        # Should contain date components
        assert "1" in result
        assert "15" in result
        assert "25" in result
        assert errors == ()

    def test_date_style_snakecase(self) -> None:
        """DATETIME accepts date_style in snake_case (backward compat)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource('date = { DATETIME($time, date_style: "short") }')

        dt = datetime(2025, 1, 15, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"time": dt})

        assert "1" in result
        assert "15" in result
        assert "25" in result
        assert errors == ()

    def test_time_style_camelcase(self) -> None:
        """DATETIME accepts timeStyle in camelCase."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            'timestamp = { DATETIME($time, dateStyle: "short", timeStyle: "short") }'
        )

        dt = datetime(2025, 1, 15, 14, 30, tzinfo=UTC)
        result, errors = bundle.format_pattern("timestamp", {"time": dt})

        # Should contain time component
        assert ":" in result
        assert errors == ()


class TestMixedCasing:
    """Test that both styles work in same bundle."""

    def test_mixed_styles_same_resource(self) -> None:
        """camelCase and snake_case can coexist in same resource."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
price1 = { NUMBER($val, minimumFractionDigits: 2) }
price2 = { NUMBER($val, minimum_fraction_digits: 2) }
        """.strip())

        result1, errors1 = bundle.format_pattern("price1", {"val": 42.5})
        result2, errors2 = bundle.format_pattern("price2", {"val": 42.5})

        # Both should produce identical output
        assert "42.50" in result1
        assert "42.50" in result2
        assert result1.strip() == result2.strip()
        assert errors1 == ()
        assert errors2 == ()


class TestLocales:
    """Test camelCase params work across locales."""

    def test_camelcase_german_locale(self) -> None:
        """camelCase params work with German locale."""
        bundle = FluentBundle("de_DE", use_isolating=False)
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("price", {"amount": 1234.5})

        # German formatting
        assert "1" in result
        assert "234" in result
        assert "5" in result
        assert errors == ()

    def test_camelcase_latvian_locale(self) -> None:
        """camelCase params work with Latvian locale."""
        bundle = FluentBundle("lv_LV", use_isolating=False)
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("price", {"amount": 1234.5})

        assert "1" in result
        assert "234" in result
        assert "5" in result
        assert errors == ()


class TestCustomFunctions:
    """Test custom functions receive camelCase conversion."""

    def test_custom_function_camelcase(self) -> None:
        """Custom functions receive camelCase parameter conversion."""

        def format_currency(
            amount: float,
            *,
            currency_code: str = "USD",
        ) -> str:
            """Format currency."""
            symbols = {"USD": "$", "EUR": "€"}
            return f"{symbols.get(currency_code, currency_code)}{amount:.2f}"

        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_function("CURRENCY", format_currency)
        bundle.add_resource('price = { CURRENCY($amt, currencyCode: "EUR") }')

        result, errors = bundle.format_pattern("price", {"amt": 123.45})
        assert "€123.45" in result
        assert errors == ()


class TestEdgeCases:
    """Test edge cases."""

    def test_number_no_params(self) -> None:
        """NUMBER works without parameters."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("val = { NUMBER($amount) }")
        result, errors = bundle.format_pattern("val", {"amount": 1234.5})
        assert "1" in result
        assert "234" in result
        assert errors == ()

    def test_datetime_no_params(self) -> None:
        """DATETIME works without parameters."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("date = { DATETIME($time) }")

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"time": dt})

        assert "2025" in result
        assert errors == ()
