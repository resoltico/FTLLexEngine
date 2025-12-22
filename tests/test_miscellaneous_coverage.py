"""Quick coverage wins for multiple files.

Targets easy-to-hit uncovered lines:
- localization.py line 212: non-PathResourceLoader source_path
- plural_rules.py lines 223-224: Polish pl i=1 case
- resolver.py line 330: boolean to string conversion
- resolver.py line 190: Placeable resolution
"""

from ftllexengine import FluentBundle, FluentLocalization
from ftllexengine.runtime.plural_rules import select_plural_category


class TestLocalizationNonPathLoader:
    """Test localization.py line 212 (non-PathResourceLoader)."""

    def test_non_path_resource_loader_source_path(self) -> None:
        """When using non-PathResourceLoader, source_path format is different."""
        # Create a custom resource loader (not PathResourceLoader)
        class CustomLoader:
            def load(self, _locale: str, _resource_id: str) -> str:
                """Return FTL source for testing."""
                return "test = Test message"

        loader = CustomLoader()
        loc = FluentLocalization(["en"], ["test.ftl"], loader)

        # This should hit line 212: source_path = f"{locale}/{resource_id}"
        # (instead of PathResourceLoader's base_path.format)
        result, _ = loc.format_value("test")
        assert result == "Test message"


class TestPolishPluralRules:
    """Test plural_rules.py lines 223-224 (Polish i=1 case)."""

    def test_polish_plural_rule_i_equals_1(self) -> None:
        """Polish has special 'one' rule for i=1."""
        # Polish (pl) uses Slavic East rule
        result = select_plural_category(1, "pl")

        # Should return "one" for i=1 (hits lines 223-224)
        assert result == "one"

    def test_polish_plural_rule_i_not_1(self) -> None:
        """Polish uses regular Slavic rules for i!=1."""
        # i=2 should hit "few" category
        result = select_plural_category(2, "pl")
        assert result == "few"

        # i=5 should hit "many" category
        result = select_plural_category(5, "pl")
        assert result == "many"


class TestResolverBooleanConversion:
    """Test resolver.py line 330 (boolean to string)."""

    def test_boolean_true_to_string(self) -> None:
        """Boolean True should be converted to string (hits resolver.py:330)."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $enabled }")

        result, _ = bundle.format_pattern("test", {"enabled": True})

        # Should hit line 330: return "true" if value else "false"
        # Line 330 returns lowercase "true", not str(True) which would be "True"
        assert "true" in result

    def test_boolean_false_to_string(self) -> None:
        """Boolean False should be converted to string (hits resolver.py:330)."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { $enabled }")

        result, _ = bundle.format_pattern("test", {"enabled": False})

        # Should hit line 330: return "true" if value else "false"
        # Line 330 returns lowercase "false", not str(False) which would be "False"
        assert "false" in result


class TestResolverPlaceableResolution:
    """Test resolver.py line 190 (Placeable resolution)."""

    def test_placeable_with_nested_expression(self) -> None:
        """Placeable containing expression should resolve inner expression."""
        bundle = FluentBundle("en")
        # Placeable: { $var }
        bundle.add_resource("test = { $value }")

        result, _ = bundle.format_pattern("test", {"value": "Hello"})

        # Should hit line 190: _resolve_expression on Placeable's inner expression
        # (Note: BIDI isolation characters may be added)
        assert "Hello" in result

    def test_placeable_with_function_reference(self) -> None:
        """Placeable containing function should resolve function."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { NUMBER($count, minimumFractionDigits: 2) }")

        result, _ = bundle.format_pattern("test", {"count": 42})

        # Should hit line 190 with FunctionReference inside Placeable
        assert "42" in result
