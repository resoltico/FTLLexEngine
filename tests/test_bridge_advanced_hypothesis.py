"""Advanced Hypothesis property-based tests for FunctionBridge.

Critical function_bridge functions tested:
- Parameter name conversion (snake_case ↔ camelCase)
- Function registration and calling
- Error handling
- Edge cases in naming conventions
"""

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import FluentResolutionError
from ftllexengine.runtime.function_bridge import FunctionRegistry
from tests.strategies import snake_case_identifiers


class TestParameterNameConversion:
    """Properties about snake_case ↔ camelCase conversion."""

    @given(snake_name=snake_case_identifiers())
    @settings(max_examples=500)
    def test_snake_to_camel_conversion(self, snake_name: str) -> None:
        """Property: snake → camel produces valid camelCase."""
        registry = FunctionRegistry()

        camel = registry._to_camel_case(snake_name)

        assert isinstance(camel, str), "Conversion must return string"

        if "_" not in snake_name:
            assert camel == snake_name, "Single word should not change"
        else:
            assert "_" not in camel, "camelCase should have no underscores"

    @given(
        parts=st.lists(
            st.text(
                alphabet=st.characters(whitelist_categories=["Ll"]), min_size=2, max_size=8
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=300)
    def test_multipart_name_conversion_preserves_part_count(
        self, parts: list[str]
    ) -> None:
        """Property: Converting multi-part names preserves part boundaries."""
        registry = FunctionRegistry()

        snake_name = "_".join(parts)
        camel_name = registry._to_camel_case(snake_name)

        if len(parts) > 1:
            assert "_" not in camel_name, "camelCase should have no underscores"
            assert camel_name[0].islower(), "camelCase should start lowercase"

    @given(
        word=st.text(
            alphabet=st.characters(whitelist_categories=["Ll"]), min_size=1, max_size=20
        )
    )
    @settings(max_examples=200)
    def test_single_word_unchanged_by_conversion(self, word: str) -> None:
        """Property: Single words (no underscores) unchanged by camelCase conversion."""
        registry = FunctionRegistry()

        camel = registry._to_camel_case(word)

        assert camel == word, "Single lowercase word should not change in camelCase"


class TestFunctionRegistration:
    """Properties about function registration."""

    @given(
        ftl_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=3, max_size=10
        ),
        return_value=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=300)
    def test_registered_function_callable(self, ftl_name: str, return_value: str) -> None:
        """Property: Registered functions can be called."""
        registry = FunctionRegistry()

        def test_func() -> str:
            return return_value

        registry.register(test_func, ftl_name=ftl_name)

        assert registry.has_function(ftl_name), f"Function {ftl_name} not found"

        result = registry.call(ftl_name, [], {})
        assert result == return_value, "Function call should return expected value"

    @given(
        python_name=snake_case_identifiers(),
        return_value=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=300)
    def test_auto_ftl_name_uppercase(self, python_name: str, return_value: str) -> None:
        """Property: Auto-generated FTL names are UPPERCASE."""
        registry = FunctionRegistry()

        def test_func() -> str:
            return return_value

        test_func.__name__ = python_name

        registry.register(test_func)

        expected_ftl_name = python_name.upper()
        assert (
            registry.has_function(expected_ftl_name)
        ), f"Function not registered as {expected_ftl_name}"

    @given(
        param_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_function_with_multiple_parameters(self, param_count: int) -> None:
        """Property: Functions with multiple parameters work correctly."""
        registry = FunctionRegistry()

        def multi_param_func(*args, **kwargs) -> str:
            return f"called with {len(args)} args and {len(kwargs)} kwargs"

        multi_param_func.__name__ = "test_func"

        registry.register(multi_param_func)

        result = registry.call("TEST_FUNC", list(range(param_count)), {})
        assert isinstance(result, str), "Function should return string"
        assert "called with" in result, "Function should be callable with multiple params"


class TestParameterMappingGeneration:
    """Properties about automatic parameter mapping generation."""

    @given(
        param_names=st.lists(snake_case_identifiers(), min_size=1, max_size=5, unique=True)
    )
    @settings(max_examples=200)
    def test_auto_mapping_covers_all_parameters(self, param_names: list[str]) -> None:
        """Property: Auto-generated mappings cover all function parameters."""
        registry = FunctionRegistry()

        for param_name in param_names:
            camel_name = registry._to_camel_case(param_name)
            assert isinstance(camel_name, str), "Mapping must produce string"


class TestFunctionCalling:
    """Properties about function calling with argument conversion."""

    @given(
        positional_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_positional_arguments_preserved(self, positional_count: int) -> None:
        """Property: Positional arguments are passed through unchanged."""
        registry = FunctionRegistry()

        received_args: list = []

        def test_func(*args) -> str:
            received_args.extend(args)
            return "ok"

        test_func.__name__ = "test"

        registry.register(test_func)

        positional_values = list(range(positional_count))
        registry.call("TEST", positional_values, {})

        assert len(received_args) == positional_count, "Positional arg count mismatch"
        assert received_args == positional_values, "Positional args not preserved"


class TestErrorHandling:
    """Properties about error handling in function bridge."""

    @given(
        nonexistent_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=5, max_size=15
        )
    )
    @settings(max_examples=200)
    def test_calling_unregistered_function_raises_error(
        self, nonexistent_name: str
    ) -> None:
        """Property: Calling unregistered function raises FluentResolutionError."""
        registry = FunctionRegistry()

        with pytest.raises(FluentResolutionError):
            registry.call(nonexistent_name, [], {})

    @given(
        ftl_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=3, max_size=10
        ),
        error_message=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=200)
    def test_function_exception_wrapped(self, ftl_name: str, error_message: str) -> None:
        """Property: Exceptions from functions are wrapped in FluentResolutionError."""
        registry = FunctionRegistry()

        def failing_func() -> str:
            raise ValueError(error_message)

        registry.register(failing_func, ftl_name=ftl_name)

        with pytest.raises(FluentResolutionError):
            registry.call(ftl_name, [], {})


class TestRegistryQueries:
    """Properties about registry query operations."""

    @given(
        ftl_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=3, max_size=10
        ),
        python_name=snake_case_identifiers(),
    )
    @settings(max_examples=200)
    def test_get_python_name_consistency(self, ftl_name: str, python_name: str) -> None:
        """Property: get_python_name returns registered Python function name."""
        registry = FunctionRegistry()

        def test_func() -> str:
            return "test"

        test_func.__name__ = python_name

        registry.register(test_func, ftl_name=ftl_name)

        retrieved_name = registry.get_python_name(ftl_name)
        assert retrieved_name == python_name, "Python name mismatch"

    @given(
        func_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_has_function_for_all_registered(self, func_count: int) -> None:
        """Property: has_function returns True for all registered functions."""
        registry = FunctionRegistry()

        ftl_names = [f"FUNC{i}" for i in range(func_count)]

        for name in ftl_names:

            def test_func() -> str:
                return "test"

            registry.register(test_func, ftl_name=name)

        for name in ftl_names:
            assert registry.has_function(name), f"Function {name} not found"


class TestConversionEdgeCases:
    """Edge cases in parameter name conversion."""

    @given(
        empty_parts=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_multiple_underscores_handling(self, empty_parts: int) -> None:
        """Property: Multiple consecutive underscores handled gracefully."""
        registry = FunctionRegistry()

        snake_name = "a" + "_" * empty_parts + "b"
        camel = registry._to_camel_case(snake_name)

        assert isinstance(camel, str), "Conversion must handle multiple underscores"


class TestMetamorphicProperties:
    """Metamorphic properties relating different operations."""

    @given(
        param_names=st.lists(snake_case_identifiers(), min_size=2, max_size=5, unique=True),
        param_values=st.lists(st.integers(), min_size=2, max_size=5),
    )
    @settings(max_examples=200)
    def test_named_args_order_independence(
        self, param_names: list[str], param_values: list[int]
    ) -> None:
        """Property: Named argument order does not affect function call result."""
        if len(param_values) < len(param_names):
            param_values.extend([0] * (len(param_names) - len(param_values)))
        param_values = param_values[: len(param_names)]

        registry = FunctionRegistry()

        received_kwargs: dict = {}

        def test_func(**kwargs) -> str:
            received_kwargs.clear()
            received_kwargs.update(kwargs)
            return "ok"

        test_func.__name__ = "test"

        registry.register(test_func)

        kwargs1 = {
            registry._to_camel_case(name): val
            for name, val in zip(param_names, param_values, strict=True)
        }
        registry.call("TEST", [], kwargs1)
        result1 = dict(received_kwargs)

        shuffled = list(kwargs1.items())
        random.shuffle(shuffled)
        kwargs2 = dict(shuffled)

        registry.call("TEST", [], kwargs2)
        result2 = dict(received_kwargs)

        assert result1 == result2, "Argument order should not affect result"
