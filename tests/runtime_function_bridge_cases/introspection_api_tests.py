# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# INTROSPECTION API TESTS
# ============================================================================


class TestFunctionRegistryIntrospection:
    """Test FunctionRegistry introspection methods."""

    def test_list_functions_empty_registry(self) -> None:
        """list_functions returns empty list for empty registry."""
        registry = FunctionRegistry()

        functions = registry.list_functions()

        assert functions == []

    def test_list_functions_single_function(self) -> None:
        """list_functions returns single function name."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        functions = registry.list_functions()

        assert functions == ["UPPER"]

    def test_list_functions_multiple_functions(self) -> None:
        """list_functions returns all registered function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")
        registry.register(positional_only_function, ftl_name="FUNC3")

        functions = registry.list_functions()

        assert set(functions) == {"FUNC1", "FUNC2", "FUNC3"}
        assert len(functions) == 3

    def test_get_function_info_existing_function(self) -> None:
        """get_function_info returns metadata for registered function."""
        registry = FunctionRegistry()
        registry.register(sample_function, ftl_name="FORMAT")

        info = registry.get_function_info("FORMAT")

        assert info is not None
        assert info.python_name == "sample_function"
        assert info.ftl_name == "FORMAT"
        assert isinstance(info.param_mapping, tuple)
        assert "minimumFractionDigits" in info.param_dict
        assert info.param_dict["minimumFractionDigits"] == "minimum_fraction_digits"
        assert callable(info.callable)

    def test_get_function_info_nonexistent_function(self) -> None:
        """get_function_info returns None for unregistered function."""
        registry = FunctionRegistry()

        info = registry.get_function_info("NONEXISTENT")

        assert info is None

    def test_iter_empty_registry(self) -> None:
        """Iterating empty registry yields no names."""
        registry = FunctionRegistry()

        names = list(registry)

        assert names == []

    def test_iter_single_function(self) -> None:
        """Iterating registry yields function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        names = list(registry)

        assert names == ["UPPER"]

    def test_iter_multiple_functions(self) -> None:
        """Iterating registry yields all function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")
        registry.register(positional_only_function, ftl_name="FUNC3")

        names = list(registry)

        assert set(names) == {"FUNC1", "FUNC2", "FUNC3"}

    def test_iter_for_loop(self) -> None:
        """Can iterate registry in for loop."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="A")
        registry.register(sample_function, ftl_name="B")

        collected_names = []
        for name in registry:
            collected_names.append(name)

        assert set(collected_names) == {"A", "B"}

    def test_len_empty_registry(self) -> None:
        """len() returns 0 for empty registry."""
        registry = FunctionRegistry()

        assert len(registry) == 0

    def test_len_single_function(self) -> None:
        """len() returns 1 for registry with one function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC")

        assert len(registry) == 1

    def test_len_multiple_functions(self) -> None:
        """len() returns correct count for multiple functions."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="F1")
        registry.register(sample_function, ftl_name="F2")
        registry.register(positional_only_function, ftl_name="F3")

        assert len(registry) == 3

    def test_len_after_overwrite(self) -> None:
        """len() doesn't double-count after overwriting function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC")
        registry.register(sample_function, ftl_name="FUNC")

        assert len(registry) == 1

    def test_contains_registered_function(self) -> None:
        """'in' operator returns True for registered function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert "UPPER" in registry

    def test_contains_unregistered_function(self) -> None:
        """'in' operator returns False for unregistered function."""
        registry = FunctionRegistry()

        assert "NONEXISTENT" not in registry

    def test_contains_case_sensitive(self) -> None:
        """'in' operator is case-sensitive."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert "UPPER" in registry
        assert "upper" not in registry
        assert "Upper" not in registry

    def test_introspection_integration(self) -> None:
        """Combine introspection methods for function discovery."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")

        # Check count
        assert len(registry) == 2

        # List all functions
        functions = registry.list_functions()
        assert len(functions) == 2

        # Iterate and inspect each function
        for name in registry:
            assert name in registry
            info = registry.get_function_info(name)
            assert info is not None
            assert info.ftl_name == name

    def test_copy_preserves_introspection(self) -> None:
        """Copied registry preserves introspection capabilities."""
        original = FunctionRegistry()
        original.register(simple_function, ftl_name="FUNC1")
        original.register(sample_function, ftl_name="FUNC2")

        copied = original.copy()

        # Both registries have same functions
        assert len(original) == len(copied)
        assert set(original) == set(copied)
        assert original.list_functions() == copied.list_functions()

        # Modifying copy doesn't affect original
        copied.register(positional_only_function, ftl_name="FUNC3")
        assert len(copied) == 3
        assert len(original) == 2
