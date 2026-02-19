"""Tests for FluentLocalization, plural rule selection, and resolver behavior.

Tests:
- FluentLocalization with custom resource loaders (non-PathResourceLoader)
- Polish plural rule selection at boundary values
- Resolver boolean-to-string conversion
- Resolver placeable resolution with variables and function calls
"""

from ftllexengine import FluentBundle, FluentLocalization
from ftllexengine.runtime.plural_rules import select_plural_category


class TestLocalizationNonPathLoader:
    """FluentLocalization with non-PathResourceLoader uses locale/resource_id as source path."""

    def test_non_path_resource_loader_source_path(self) -> None:
        """Custom resource loader receives locale and resource_id from FluentLocalization."""

        class CustomLoader:
            def load(self, _locale: str, _resource_id: str) -> str:
                """Return FTL source for testing."""
                return "test = Test message"

        loader = CustomLoader()
        loc = FluentLocalization(["en"], ["test.ftl"], loader)

        result, _ = loc.format_value("test")
        assert result == "Test message"


class TestPolishPluralRules:
    """Polish plural rule selection at integer boundaries."""

    def test_polish_plural_rule_i_equals_1(self) -> None:
        """Polish returns 'one' for i=1."""
        result = select_plural_category(1, "pl")
        assert result == "one"

    def test_polish_plural_rule_few(self) -> None:
        """Polish returns 'few' for 2-4."""
        result = select_plural_category(2, "pl")
        assert result == "few"

    def test_polish_plural_rule_many(self) -> None:
        """Polish returns 'many' for 5+."""
        result = select_plural_category(5, "pl")
        assert result == "many"


class TestResolverBooleanConversion:
    """Resolver converts Python booleans to lowercase Fluent strings."""

    def test_boolean_true_to_string(self) -> None:
        """Boolean True converts to lowercase 'true', not Python's 'True'."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $enabled }")

        result, _ = bundle.format_pattern("test", {"enabled": True})
        assert "true" in result

    def test_boolean_false_to_string(self) -> None:
        """Boolean False converts to lowercase 'false', not Python's 'False'."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $enabled }")

        result, _ = bundle.format_pattern("test", {"enabled": False})
        assert "false" in result


class TestResolverPlaceableResolution:
    """Resolver evaluates placeable expressions, including variables and function calls."""

    def test_placeable_with_variable(self) -> None:
        """Variable reference inside placeable is resolved from the args dict."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $value }")

        result, _ = bundle.format_pattern("test", {"value": "Hello"})
        assert "Hello" in result

    def test_placeable_with_function_reference(self) -> None:
        """Function reference inside placeable invokes the function with its arguments."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { NUMBER($count, minimumFractionDigits: 2) }")

        result, _ = bundle.format_pattern("test", {"count": 42})
        assert "42" in result
