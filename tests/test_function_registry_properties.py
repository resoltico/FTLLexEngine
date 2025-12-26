"""Property-based tests for FunctionRegistry introspection.

Uses Hypothesis to test invariants and edge cases with generated data.
Critical for financial-grade quality.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.runtime.function_bridge import FunctionRegistry

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


def simple_test_func(value: Any) -> str:
    """Simple function for testing."""
    return str(value)


def func_with_params(value: int, *, min_val: int = 0, max_val: int = 100) -> str:
    """Function with keyword parameters for testing."""
    return f"{value}:{min_val}:{max_val}"


# Strategy for valid FTL function names (UPPERCASE identifiers)
ftl_function_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu",),  # type: ignore[arg-type]
        min_codepoint=65,
        max_codepoint=90,
    ),
    min_size=1,
    max_size=20,
).filter(lambda s: s.isidentifier())


# Strategy for valid Python function names (lowercase identifiers)
python_function_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll",), min_codepoint=97, max_codepoint=122  # type: ignore[arg-type]
    )
    | st.just("_"),
    min_size=1,
    max_size=20,
).filter(lambda s: s.isidentifier() and not s.startswith("__"))


# ============================================================================
# PROPERTY TESTS - LIST AND ITERATION INVARIANTS
# ============================================================================


class TestIntrospectionInvariants:
    """Property-based tests for introspection API invariants."""

    @given(names=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True))
    def test_list_functions_length_matches_registrations(self, names: list[str]) -> None:
        """list_functions length matches number of registrations."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        functions = registry.list_functions()

        assert len(functions) == len(names)
        assert set(functions) == set(names)

    @given(names=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True))
    def test_iter_yields_same_as_list_functions(self, names: list[str]) -> None:
        """Iterating registry yields same names as list_functions."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        list_result = registry.list_functions()
        iter_result = list(registry)

        assert sorted(list_result) == sorted(iter_result)

    @given(names=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True))
    def test_len_equals_list_length(self, names: list[str]) -> None:
        """len() equals length of list_functions."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        assert len(registry) == len(registry.list_functions())

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_all_listed_functions_in_registry(self, names: list[str]) -> None:
        """All functions returned by list_functions are in registry."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        for listed_name in registry.list_functions():
            assert listed_name in registry

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_all_listed_functions_have_info(self, names: list[str]) -> None:
        """All listed functions have retrievable info."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        for listed_name in registry.list_functions():
            info = registry.get_function_info(listed_name)
            assert info is not None
            assert info.ftl_name == listed_name


# ============================================================================
# PROPERTY TESTS - CONTAINS OPERATOR INVARIANTS
# ============================================================================


class TestContainsInvariants:
    """Property-based tests for 'in' operator invariants."""

    @given(
        registered=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True),
        query=ftl_function_names,
    )
    def test_contains_consistent_with_list(
        self, registered: list[str], query: str
    ) -> None:
        """'in' operator consistent with list_functions."""
        registry = FunctionRegistry()

        for name in registered:
            registry.register(simple_test_func, ftl_name=name)

        assert (query in registry) == (query in registry.list_functions())

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_all_registered_functions_in_registry(self, names: list[str]) -> None:
        """All registered functions are in registry."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        for name in names:
            assert name in registry

    @given(
        registered=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True),
        query=ftl_function_names,
    )
    def test_contains_implies_get_info_not_none(
        self, registered: list[str], query: str
    ) -> None:
        """If name in registry, get_function_info returns non-None."""
        registry = FunctionRegistry()

        for name in registered:
            registry.register(simple_test_func, ftl_name=name)

        if query in registry:
            assert registry.get_function_info(query) is not None
        else:
            assert registry.get_function_info(query) is None


# ============================================================================
# PROPERTY TESTS - FUNCTION INFO INVARIANTS
# ============================================================================


class TestFunctionInfoInvariants:
    """Property-based tests for get_function_info invariants."""

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_function_info_ftl_name_matches(self, names: list[str]) -> None:
        """FunctionSignature.ftl_name matches requested name."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        for name in names:
            info = registry.get_function_info(name)
            assert info is not None
            assert info.ftl_name == name

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_function_info_has_callable(self, names: list[str]) -> None:
        """FunctionSignature always has callable."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        for name in names:
            info = registry.get_function_info(name)
            assert info is not None
            assert callable(info.callable)

    @given(names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True))
    def test_function_info_has_param_mapping(self, names: list[str]) -> None:
        """FunctionSignature always has param_mapping dict."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(func_with_params, ftl_name=name)

        for name in names:
            info = registry.get_function_info(name)
            assert info is not None
            # param_mapping is now immutable tuple[tuple[str, str], ...]
            assert isinstance(info.param_mapping, tuple)


# ============================================================================
# PROPERTY TESTS - COPY INVARIANTS
# ============================================================================


class TestCopyInvariants:
    """Property-based tests for registry copying."""

    @given(names=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True))
    def test_copy_preserves_length(self, names: list[str]) -> None:
        """Copied registry has same length."""
        original = FunctionRegistry()

        for name in names:
            original.register(simple_test_func, ftl_name=name)

        copied = original.copy()

        assert len(original) == len(copied)

    @given(names=st.lists(ftl_function_names, min_size=0, max_size=20, unique=True))
    def test_copy_preserves_function_names(self, names: list[str]) -> None:
        """Copied registry has same function names."""
        original = FunctionRegistry()

        for name in names:
            original.register(simple_test_func, ftl_name=name)

        copied = original.copy()

        assert set(original.list_functions()) == set(copied.list_functions())

    @given(
        original_names=st.lists(ftl_function_names, min_size=1, max_size=10, unique=True),
        new_name=ftl_function_names,
    )
    def test_copy_isolation(self, original_names: list[str], new_name: str) -> None:
        """Modifying copy doesn't affect original."""
        original = FunctionRegistry()

        for name in original_names:
            original.register(simple_test_func, ftl_name=name)

        original_len = len(original)
        copied = original.copy()

        # Modify copy
        copied.register(simple_test_func, ftl_name=new_name)

        # Original unchanged
        assert len(original) == original_len
        assert len(copied) >= original_len


# ============================================================================
# PROPERTY TESTS - OVERWRITE BEHAVIOR
# ============================================================================


class TestOverwriteInvariants:
    """Property-based tests for function overwriting behavior."""

    @given(
        name=ftl_function_names,
        count=st.integers(min_value=2, max_value=10),
    )
    def test_overwrite_maintains_single_entry(self, name: str, count: int) -> None:
        """Overwriting same name maintains single entry."""
        registry = FunctionRegistry()

        for _ in range(count):
            registry.register(simple_test_func, ftl_name=name)

        assert len(registry) == 1
        assert registry.list_functions() == [name]

    @given(
        names=st.lists(ftl_function_names, min_size=2, max_size=10, unique=True),
    )
    def test_overwrite_preserves_other_functions(
        self, names: list[str]
    ) -> None:
        """Overwriting one function doesn't affect others."""
        # Pick a valid index from the generated list (middle element)
        overwrite_index = len(names) // 2

        registry = FunctionRegistry()

        # Register all functions
        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        initial_count = len(registry)

        # Overwrite one function
        registry.register(func_with_params, ftl_name=names[overwrite_index])

        # Count unchanged
        assert len(registry) == initial_count
        # Same names present
        assert set(registry.list_functions()) == set(names)


# ============================================================================
# PROPERTY TESTS - EMPTY REGISTRY BEHAVIOR
# ============================================================================


class TestEmptyRegistryInvariants:
    """Property-based tests for empty registry behavior."""

    @given(query=ftl_function_names)
    def test_empty_registry_contains_nothing(self, query: str) -> None:
        """Empty registry contains no functions."""
        registry = FunctionRegistry()

        assert query not in registry

    @given(query=ftl_function_names)
    def test_empty_registry_get_info_returns_none(self, query: str) -> None:
        """Empty registry returns None for all queries."""
        registry = FunctionRegistry()

        assert registry.get_function_info(query) is None

    def test_empty_registry_has_zero_length(self) -> None:
        """Empty registry has length 0."""
        registry = FunctionRegistry()

        assert len(registry) == 0

    def test_empty_registry_lists_nothing(self) -> None:
        """Empty registry lists no functions."""
        registry = FunctionRegistry()

        assert registry.list_functions() == []

    def test_empty_registry_iteration_yields_nothing(self) -> None:
        """Empty registry iteration yields nothing."""
        registry = FunctionRegistry()

        assert list(registry) == []


# ============================================================================
# PROPERTY TESTS - FINANCIAL GRADE EDGE CASES
# ============================================================================


class TestFinancialGradeEdgeCases:
    """Financial-grade edge case testing with Hypothesis.

    These tests ensure robustness for financial applications where
    correctness is critical.
    """

    @given(
        names=st.lists(
            ftl_function_names,
            min_size=100,
            max_size=1000,
            unique=True,
        )
    )
    def test_large_registry_performance_invariants(self, names: list[str]) -> None:
        """Large registries maintain invariants."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        # All invariants hold even with large registry
        assert len(registry) == len(names)
        assert len(registry.list_functions()) == len(names)
        assert len(list(registry)) == len(names)

        # Spot check some entries
        for name in names[:10]:
            assert name in registry
            assert registry.get_function_info(name) is not None

    @given(
        register_names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True),
        query_names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True),
    )
    def test_contains_never_false_positive(
        self, register_names: list[str], query_names: list[str]
    ) -> None:
        """'in' operator never returns false positives."""
        registry = FunctionRegistry()

        for name in register_names:
            registry.register(simple_test_func, ftl_name=name)

        for query in query_names:
            if query in registry:
                # Must be in registered set
                assert query in register_names

    @given(
        names=st.lists(ftl_function_names, min_size=1, max_size=20, unique=True),
        iterations=st.integers(min_value=1, max_value=5),
    )
    def test_iteration_deterministic(self, names: list[str], iterations: int) -> None:
        """Multiple iterations yield consistent results."""
        registry = FunctionRegistry()

        for name in names:
            registry.register(simple_test_func, ftl_name=name)

        results = []
        for _ in range(iterations):
            results.append(set(registry))

        # All iterations yield same set
        first_result = results[0]
        for result in results[1:]:
            assert result == first_result
