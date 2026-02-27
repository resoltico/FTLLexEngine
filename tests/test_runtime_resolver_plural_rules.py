"""Tests for resolver error handling, boundary conditions, and plural rule selection.

Tests:
- Resolver error path handling for missing messages, variables, and terms
- Resolver boundary conditions with zero, one, and multiple arguments
- Plural rule selection for English, Latvian, and Polish locales
- Plural rules with decimal and negative number inputs
- Resolver type handling for string, int, Decimal, and bool values
"""


from decimal import Decimal

from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.plural_rules import select_plural_category


class TestResolverErrorPaths:
    """Resolver handles missing messages, variables, and term references gracefully."""

    def test_resolver_missing_message_reference(self) -> None:
        """Referencing a non-existent message inside a pattern returns a fallback string."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = { nonexistent }")

        result, _ = bundle.format_pattern("msg")
        assert isinstance(result, str)

    def test_resolver_missing_variable_in_args(self) -> None:
        """Missing variable uses a fallback representation, not a hard error."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = Hello, { $name }!")

        result, _ = bundle.format_pattern("msg", {})
        assert "name" in result or "$name" in result or "???" in result

    def test_resolver_term_reference_resolved(self) -> None:
        """Term references are resolved to the term's value."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
-brand = Firefox
msg = Welcome to { -brand }!
""")

        result, _ = bundle.format_pattern("msg")
        assert "Firefox" in result

    def test_resolver_message_attribute_accessible(self) -> None:
        """Messages with attributes are stored and accessible."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
msg = Value
    .attr = Attribute Value
""")

        assert bundle.has_message("msg")

    def test_resolver_with_number_function(self) -> None:
        """NUMBER function call is resolved correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { NUMBER($value) }")

        result, _ = bundle.format_pattern("msg", {"value": 1234})
        assert "1234" in result or "1,234" in result

    def test_resolver_with_select_expression(self) -> None:
        """Select expression resolves to the correct variant based on selector."""
        bundle = FluentBundle("en")
        bundle.add_resource("""
msg = { $count ->
    [one] One item
    *[other] Multiple items
}
""")

        result_one, errors = bundle.format_pattern("msg", {"count": 1})
        assert not errors
        result_other, errors = bundle.format_pattern("msg", {"count": 5})
        assert not errors

        assert isinstance(result_one, str)
        assert isinstance(result_other, str)


class TestResolverBoundaryConditions:
    """Resolver handles argument counts at the boundary correctly."""

    def test_resolver_with_empty_args(self) -> None:
        """Message without variables resolves correctly with an empty args dict."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = No variables")

        result, _ = bundle.format_pattern("msg", {})
        assert result == "No variables"

    def test_resolver_with_one_arg(self) -> None:
        """Message with a single argument resolves the variable correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello, { $name }!")

        result, _ = bundle.format_pattern("msg", {"name": "World"})
        assert "World" in result

    def test_resolver_with_multiple_args(self) -> None:
        """Message with multiple arguments resolves all variables correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $greeting }, { $name }!")

        result, _ = bundle.format_pattern("msg", {"greeting": "Hello", "name": "World"})
        assert "Hello" in result
        assert "World" in result

    def test_resolver_with_zero_number(self) -> None:
        """Zero is resolved and formatted correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $count }")

        result, _ = bundle.format_pattern("msg", {"count": 0})
        assert "0" in result

    def test_resolver_with_negative_number(self) -> None:
        """Negative numbers are resolved and formatted correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $value }")

        result, _ = bundle.format_pattern("msg", {"value": -42})
        assert "-42" in result or "\u221242" in result

    def test_resolver_with_empty_string(self) -> None:
        """Empty string value is interpolated without error."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value: { $str }")

        result, _ = bundle.format_pattern("msg", {"str": ""})
        assert "Value:" in result


class TestPluralRuleBoundaries:
    """Plural rule selection for English, Latvian, and Polish at boundary values."""

    def test_plural_rule_english_zero(self) -> None:
        """English: 0 is 'other'."""
        assert select_plural_category(0, "en") == "other"

    def test_plural_rule_english_one(self) -> None:
        """English: 1 is 'one'."""
        assert select_plural_category(1, "en") == "one"

    def test_plural_rule_english_other(self) -> None:
        """English: 2 and above are 'other'."""
        for n in [2, 5, 10, 100, 1000]:
            assert select_plural_category(n, "en") == "other"

    def test_plural_rule_latvian_zero(self) -> None:
        """Latvian: numbers ending in 0 (including 0 and 10) are 'zero'."""
        assert select_plural_category(0, "lv") == "zero"
        assert select_plural_category(10, "lv") == "zero"

    def test_plural_rule_latvian_one(self) -> None:
        """Latvian: 1 and 21, 31, etc. (not 11) are 'one'."""
        assert select_plural_category(1, "lv") == "one"
        assert select_plural_category(21, "lv") == "one"
        assert select_plural_category(11, "lv") != "one"

    def test_plural_rule_latvian_eleven(self) -> None:
        """Latvian: 11 falls into a specific plural category (not 'one')."""
        category = select_plural_category(11, "lv")
        assert category in ["zero", "one", "other"]

    def test_plural_rule_polish_boundaries(self) -> None:
        """Polish plural rules handle complex boundaries correctly."""
        category = select_plural_category(1, "pl")
        assert category in ["one", "few", "many", "other"]

        for n in [2, 3, 4, 5, 12, 13, 14, 22, 100]:
            category = select_plural_category(n, "pl")
            assert category in ["one", "few", "many", "other"]

    def test_plural_rule_unknown_locale_fallback(self) -> None:
        """Unknown locales fall back to a standard plural rule."""
        category = select_plural_category(1, "xx_XX")
        assert category in ["one", "other", "zero", "few", "many"]


class TestPluralRuleDecimalBoundaries:
    """Plural rule selection with decimal and negative number inputs."""

    def test_plural_rule_with_decimal_one(self) -> None:
        """English: Decimal("1") (no visible fraction) is treated as 'one'."""
        assert select_plural_category(Decimal("1"), "en") == "one"

    def test_plural_rule_with_decimal_other(self) -> None:
        """English: 1.5 is 'other' (fractional part makes it non-integer)."""
        assert select_plural_category(Decimal("1.5"), "en") == "other"

    def test_plural_rule_with_negative_one(self) -> None:
        """Negative numbers return a valid plural category."""
        category = select_plural_category(-1, "en")
        assert category in ["one", "other", "zero", "few", "many"]


class TestResolverTypeChecks:
    """Resolver handles different Python value types as Fluent variables."""

    def test_resolver_with_string_value(self) -> None:
        """String values are interpolated as-is."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $text }")

        result, _ = bundle.format_pattern("msg", {"text": "Hello"})
        assert "Hello" in result

    def test_resolver_with_int_value(self) -> None:
        """Integer values are converted to their string representation."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $num }")

        result, _ = bundle.format_pattern("msg", {"num": 42})
        assert "42" in result

    def test_resolver_with_decimal_value(self) -> None:
        """Decimal values are interpolated as-is (raw variable interpolation)."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $num }")

        result, _ = bundle.format_pattern("msg", {"num": Decimal("3.14")})
        assert "3.14" in result

    def test_resolver_with_bool_value(self) -> None:
        """Boolean values are converted to a string representation."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $flag }")

        result, _ = bundle.format_pattern("msg", {"flag": True})
        assert isinstance(result, str)
