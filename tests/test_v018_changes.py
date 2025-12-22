"""Tests for v0.18.0 changes.

Tests cover:
- create_default_registry() factory function
- FluentBundle functions parameter
- FUNCTION_REGISTRY removal (no longer available)
- __slots__ on IntrospectionVisitor and ReferenceExtractor
"""

import pytest

from ftllexengine import FluentBundle
from ftllexengine.introspection import IntrospectionVisitor, ReferenceExtractor
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry


class TestCreateDefaultRegistry:
    """Tests for create_default_registry() factory function."""

    def test_returns_function_registry(self) -> None:
        """Factory returns FunctionRegistry instance."""
        registry = create_default_registry()
        assert isinstance(registry, FunctionRegistry)

    def test_contains_number_function(self) -> None:
        """Registry contains NUMBER function."""
        registry = create_default_registry()
        assert "NUMBER" in registry
        assert registry.has_function("NUMBER")

    def test_contains_datetime_function(self) -> None:
        """Registry contains DATETIME function."""
        registry = create_default_registry()
        assert "DATETIME" in registry
        assert registry.has_function("DATETIME")

    def test_contains_currency_function(self) -> None:
        """Registry contains CURRENCY function."""
        registry = create_default_registry()
        assert "CURRENCY" in registry
        assert registry.has_function("CURRENCY")

    def test_returns_isolated_instance(self) -> None:
        """Each call returns new isolated instance."""
        registry1 = create_default_registry()
        registry2 = create_default_registry()

        # Different objects
        assert registry1 is not registry2

        # Modifying one doesn't affect the other
        def custom_func(value: str) -> str:
            return value

        registry1.register(custom_func, ftl_name="CUSTOM")
        assert "CUSTOM" in registry1
        assert "CUSTOM" not in registry2

    def test_registry_is_mutable(self) -> None:
        """Returned registry can be modified."""
        registry = create_default_registry()

        def my_func(value: str) -> str:
            return f"[{value}]"

        # Should not raise
        registry.register(my_func, ftl_name="BRACKET")
        assert "BRACKET" in registry


class TestFluentBundleFunctionsParameter:
    """Tests for FluentBundle functions parameter."""

    def test_default_uses_standard_functions(self) -> None:
        """Default (no functions parameter) includes standard functions."""
        bundle = FluentBundle("en")
        bundle.add_resource("test = { NUMBER(123) }")
        result, errors = bundle.format_pattern("test")
        assert errors == ()
        assert "123" in result

    def test_custom_registry_used(self) -> None:
        """Custom registry is used when provided."""
        registry = create_default_registry()

        def my_number(value: int) -> str:
            return f"NUM:{value}"

        registry.register(my_number, ftl_name="NUMBER")

        bundle = FluentBundle("en", functions=registry, use_isolating=False)
        bundle.add_resource("test = { NUMBER(42) }")
        result, errors = bundle.format_pattern("test")

        assert errors == ()
        assert result == "NUM:42"

    def test_registry_is_copied(self) -> None:
        """Registry is copied, not used directly."""
        registry = create_default_registry()
        bundle = FluentBundle("en", functions=registry)

        # Modify original registry after bundle creation
        def new_func(value: str) -> str:
            return f"NEW:{value}"

        registry.register(new_func, ftl_name="NEWFUNC")

        # Bundle should not have the new function
        bundle.add_resource("test = { NEWFUNC($val) }")
        result, _ = bundle.format_pattern("test", {"val": "test"})

        # Should return error placeholder, not "NEW:test"
        assert "NEWFUNC" in result  # Error placeholder

    def test_for_system_locale_accepts_functions(self) -> None:
        """FluentBundle.for_system_locale() accepts functions parameter."""
        registry = create_default_registry()

        def custom_curr(_value: int, *, currency: str = "USD") -> str:
            return f"${_value} {currency}"

        registry.register(custom_curr, ftl_name="CURRENCY")

        bundle = FluentBundle.for_system_locale(functions=registry)
        bundle.add_resource('test = { CURRENCY(100, currency: "EUR") }')
        result, errors = bundle.format_pattern("test")

        assert errors == ()
        assert "EUR" in result


class TestFunctionRegistryRemoval:
    """Tests verifying FUNCTION_REGISTRY is removed."""

    def test_function_registry_not_in_module(self) -> None:
        """FUNCTION_REGISTRY is no longer available in functions module."""
        from ftllexengine.runtime import functions  # noqa: PLC0415

        assert not hasattr(functions, "FUNCTION_REGISTRY")

    def test_function_registry_import_raises(self) -> None:
        """Importing FUNCTION_REGISTRY raises ImportError/AttributeError."""
        # Cannot use direct import as it causes lint errors
        # Use getattr() to simulate dynamic attribute access
        import importlib  # noqa: PLC0415

        module = importlib.import_module("ftllexengine.runtime.functions")
        with pytest.raises(AttributeError):
            getattr(module, "FUNCTION_REGISTRY")  # noqa: B009

    def test_create_default_registry_is_replacement(self) -> None:
        """create_default_registry() is the replacement for FUNCTION_REGISTRY."""
        registry = create_default_registry()
        # Same content as old FUNCTION_REGISTRY
        assert "NUMBER" in registry
        assert "DATETIME" in registry
        assert "CURRENCY" in registry
        assert len(registry) == 3


class TestIntrospectionSlots:
    """Tests for __slots__ on introspection visitor classes."""

    def test_introspection_visitor_has_slots(self) -> None:
        """IntrospectionVisitor has __slots__ defined."""
        assert hasattr(IntrospectionVisitor, "__slots__")
        slots = IntrospectionVisitor.__slots__
        assert "_context" in slots
        assert "functions" in slots
        assert "has_selectors" in slots
        assert "references" in slots
        assert "variables" in slots

    def test_reference_extractor_has_slots(self) -> None:
        """ReferenceExtractor has __slots__ defined."""
        assert hasattr(ReferenceExtractor, "__slots__")
        slots = ReferenceExtractor.__slots__
        assert "message_refs" in slots
        assert "term_refs" in slots

    def test_introspection_visitor_no_dict(self) -> None:
        """IntrospectionVisitor instances don't have __dict__."""
        visitor = IntrospectionVisitor()
        # Instances with __slots__ and no __dict__ slot should not have __dict__
        # Note: Parent class ASTVisitor also uses slots
        assert not hasattr(visitor, "__dict__") or visitor.__dict__ == {}

    def test_reference_extractor_no_dict(self) -> None:
        """ReferenceExtractor instances don't have __dict__."""
        extractor = ReferenceExtractor()
        assert not hasattr(extractor, "__dict__") or extractor.__dict__ == {}

    def test_cannot_add_arbitrary_attributes_to_visitor(self) -> None:
        """Cannot add arbitrary attributes to IntrospectionVisitor."""
        visitor = IntrospectionVisitor()
        with pytest.raises(AttributeError):
            # pylint: disable=assigning-non-slot
            visitor.arbitrary_attribute = "test"  # type: ignore[attr-defined]

    def test_cannot_add_arbitrary_attributes_to_extractor(self) -> None:
        """Cannot add arbitrary attributes to ReferenceExtractor."""
        extractor = ReferenceExtractor()
        with pytest.raises(AttributeError):
            # pylint: disable=assigning-non-slot
            extractor.arbitrary_attribute = "test"  # type: ignore[attr-defined]


class TestCreateDefaultRegistryIntegration:
    """Integration tests for create_default_registry() with FluentBundle."""

    def test_number_formatting_works(self) -> None:
        """NUMBER function works with create_default_registry()."""
        registry = create_default_registry()
        bundle = FluentBundle("en", functions=registry)
        bundle.add_resource("amount = { NUMBER($value, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("amount", {"value": 1234.5})

        assert errors == ()
        assert "1,234.50" in result or "1234.50" in result

    def test_datetime_formatting_works(self) -> None:
        """DATETIME function works with create_default_registry()."""
        from datetime import UTC, datetime  # noqa: PLC0415

        registry = create_default_registry()
        bundle = FluentBundle("en", functions=registry)
        bundle.add_resource('date = { DATETIME($d, dateStyle: "short") }')

        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"d": dt})

        assert errors == ()
        assert "2025" in result or "25" in result or "1/15" in result

    def test_currency_formatting_works(self) -> None:
        """CURRENCY function works with create_default_registry()."""
        registry = create_default_registry()
        bundle = FluentBundle("en", functions=registry)
        bundle.add_resource('price = { CURRENCY($amount, currency: "USD") }')
        result, errors = bundle.format_pattern("price", {"amount": 99.99})

        assert errors == ()
        assert "$" in result or "USD" in result
        assert "99" in result
