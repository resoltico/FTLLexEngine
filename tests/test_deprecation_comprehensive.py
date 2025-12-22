"""Comprehensive test coverage for deprecation utilities.

Tests all code paths in deprecation.py using Hypothesis-based property testing
and explicit unit tests for deterministic scenarios.

Coverage targets:
- warn_deprecated(): with/without alternative, stacklevel variations
- deprecated(): decorator application, docstring modification, function preservation
- deprecated_parameter(): parameter detection, warning emission, function passthrough
"""

import warnings
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.deprecation import deprecated, deprecated_parameter, warn_deprecated


class TestWarnDeprecatedFunction:
    """Test suite for warn_deprecated() function."""

    def test_warn_deprecated_basic_message_format(self) -> None:
        """Verify basic deprecation warning format without alternative."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_deprecated(
                "old_function()",
                removal_version="2.0.0",
                stacklevel=2,
            )

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            expected_msg = (
                "old_function() is deprecated and will be removed in version 2.0.0."
            )
            assert str(w[0].message) == expected_msg

    def test_warn_deprecated_with_alternative(self) -> None:
        """Verify deprecation warning includes alternative when provided."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_deprecated(
                "legacy_api()",
                removal_version="3.0.0",
                alternative="new_api()",
                stacklevel=2,
            )

            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            expected_msg = (
                "legacy_api() is deprecated and will be removed in version 3.0.0. "
                "Use new_api() instead."
            )
            assert str(w[0].message) == expected_msg

    def test_warn_deprecated_stacklevel_propagation(self) -> None:
        """Verify stacklevel parameter is correctly passed to warnings.warn()."""

        def outer_function() -> None:
            """Outer wrapper to test stacklevel."""
            inner_function()

        def inner_function() -> None:
            """Inner function that issues deprecation warning."""
            warn_deprecated(
                "test_feature",
                removal_version="1.0.0",
                stacklevel=3,
            )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            outer_function()

            assert len(w) == 1
            assert w[0].category is FutureWarning

    @given(
        feature=st.text(min_size=1, max_size=100),
        version=st.from_regex(r"\d+\.\d+\.\d+", fullmatch=True),
    )
    def test_warn_deprecated_property_message_contains_inputs(
        self, feature: str, version: str
    ) -> None:
        """Property: Warning message always contains feature name and version."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_deprecated(feature, removal_version=version)

            assert len(w) == 1
            message = str(w[0].message)
            assert feature in message
            assert version in message
            assert "deprecated" in message.lower()


class TestDeprecatedDecorator:
    """Test suite for @deprecated decorator."""

    def test_deprecated_decorator_emits_warning_on_call(self) -> None:
        """Verify decorated function emits FutureWarning when called."""

        @deprecated(removal_version="1.0.0")
        def old_function(x: int) -> int:
            """Multiply by two."""
            return x * 2

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = old_function(5)

            assert result == 10
            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "old_function()" in str(w[0].message)
            assert "1.0.0" in str(w[0].message)

    def test_deprecated_decorator_preserves_function_signature(self) -> None:
        """Verify decorator preserves original function's name and module."""

        @deprecated(removal_version="2.0.0")
        def example_function(a: int, b: str) -> str:
            """Example docstring."""
            return f"{a}{b}"

        assert example_function.__name__ == "example_function"
        assert "Example docstring." in (example_function.__doc__ or "")

    def test_deprecated_decorator_modifies_docstring_without_alternative(self) -> None:
        """Verify docstring is updated with deprecation notice (no alternative)."""

        @deprecated(removal_version="1.5.0")
        def legacy_func() -> str:
            """Original documentation."""
            return "result"

        assert legacy_func.__doc__ is not None
        assert "Original documentation." in legacy_func.__doc__
        assert ".. deprecated::" in legacy_func.__doc__
        assert "1.5.0" in legacy_func.__doc__

    def test_deprecated_decorator_modifies_docstring_with_alternative(self) -> None:
        """Verify docstring includes alternative when provided."""

        @deprecated(removal_version="2.0.0", alternative="new_function()")
        def old_method() -> None:
            """Old method docs."""

        assert old_method.__doc__ is not None
        assert "Old method docs." in old_method.__doc__
        assert ".. deprecated::" in old_method.__doc__
        assert "new_function()" in old_method.__doc__

    def test_deprecated_decorator_handles_missing_docstring(self) -> None:
        """Verify decorator creates docstring if original function has none."""

        @deprecated(removal_version="1.0.0", alternative="replacement()")
        def no_docs():
            return 42

        docstring = no_docs.__doc__
        assert docstring is not None
        # Type narrowed by assertion above - docstring is str, not None
        assert ".. deprecated::" in docstring  # pylint: disable=unsupported-membership-test
        assert "1.0.0" in docstring  # pylint: disable=unsupported-membership-test
        assert "replacement()" in docstring  # pylint: disable=unsupported-membership-test

    def test_deprecated_decorator_function_still_executes(self) -> None:
        """Verify decorated function executes normally despite warning."""

        @deprecated(removal_version="3.0.0")
        def compute(x: int, y: int) -> int:
            """Sum two numbers."""
            return x + y

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = compute(10, 20)

            assert result == 30

    def test_deprecated_decorator_multiple_calls_emit_multiple_warnings(self) -> None:
        """Verify each function call emits a separate warning."""

        @deprecated(removal_version="1.0.0")
        def repeated_call() -> str:
            """Test function."""
            return "value"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            repeated_call()
            repeated_call()
            repeated_call()

            assert len(w) == 3
            assert all(issubclass(warning.category, FutureWarning) for warning in w)

    @given(
        removal_version=st.text(min_size=5, max_size=20),
        return_value=st.integers(),
    )
    def test_deprecated_decorator_property_preserves_return_value(
        self, removal_version: str, return_value: int
    ) -> None:
        """Property: Decorator never alters function return value."""

        @deprecated(removal_version=removal_version)
        def get_value() -> int:
            """Return constant."""
            return return_value

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = get_value()

            assert result == return_value

    def test_deprecated_decorator_with_args_and_kwargs(self) -> None:
        """Verify decorator works with functions accepting *args and **kwargs."""

        @deprecated(removal_version="1.0.0")
        def flexible_func(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Flexible signature."""
            return {"args": args, "kwargs": kwargs}

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = flexible_func(1, 2, 3, key="value", other=42)

            assert result["args"] == (1, 2, 3)
            assert result["kwargs"] == {"key": "value", "other": 42}


class TestDeprecatedParameterDecorator:
    """Test suite for @deprecated_parameter decorator."""

    def test_deprecated_parameter_warns_when_parameter_used(self) -> None:
        """Verify warning is emitted when deprecated parameter is passed."""

        @deprecated_parameter("old_param", removal_version="1.0.0")
        def example_func(x: int, old_param: bool = False) -> int:  # noqa: ARG001
            """Example function."""
            return x * 2

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = example_func(5, old_param=True)

            assert result == 10
            assert len(w) == 1
            assert issubclass(w[0].category, FutureWarning)
            assert "old_param" in str(w[0].message)
            assert "1.0.0" in str(w[0].message)

    def test_deprecated_parameter_no_warning_when_not_used(self) -> None:
        """Verify no warning when deprecated parameter is not passed."""

        @deprecated_parameter("legacy_flag", removal_version="2.0.0")
        def safe_func(x: int, legacy_flag: bool = False) -> int:  # noqa: ARG001
            """Safe function."""
            return x + 1

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = safe_func(10)

            assert result == 11
            assert len(w) == 0

    def test_deprecated_parameter_with_alternative(self) -> None:
        """Verify warning includes alternative parameter when provided."""

        @deprecated_parameter(
            "old_name",
            removal_version="1.5.0",
            alternative="new_name",
        )
        def migrate_params(value: str, old_name: str = "", new_name: str = "") -> str:
            """Migration example."""
            return old_name or new_name or value

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = migrate_params("test", old_name="legacy")

            assert result == "legacy"
            assert len(w) == 1
            assert "old_name" in str(w[0].message)
            assert "'new_name'" in str(w[0].message)

    def test_deprecated_parameter_preserves_function_behavior(self) -> None:
        """Verify decorated function executes normally."""

        @deprecated_parameter("deprecated_arg", removal_version="1.0.0")
        def process(x: int, y: int, deprecated_arg: int | None = None) -> int:
            """Process values."""
            if deprecated_arg is not None:
                return x + y + deprecated_arg
            return x + y

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result1 = process(5, 10)
            result2 = process(5, 10, deprecated_arg=3)

            assert result1 == 15
            assert result2 == 18

    def test_deprecated_parameter_multiple_deprecated_params(self) -> None:
        """Verify multiple @deprecated_parameter decorators can be stacked."""

        @deprecated_parameter("param_a", removal_version="1.0.0")
        @deprecated_parameter("param_b", removal_version="1.0.0")
        def multi_deprecated(
            x: int,
            param_a: bool = False,  # noqa: ARG001
            param_b: bool = False,  # noqa: ARG001
        ) -> int:
            """Multiple deprecated parameters."""
            return x

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            multi_deprecated(42, param_a=True, param_b=True)

            assert len(w) == 2
            messages = [str(warning.message) for warning in w]
            assert any("param_a" in msg for msg in messages)
            assert any("param_b" in msg for msg in messages)

    def test_deprecated_parameter_only_kwargs_trigger_warning(self) -> None:
        """Verify warning only emitted when parameter passed as keyword argument."""

        @deprecated_parameter("old_flag", removal_version="1.0.0")
        def keyword_only_check(x: int, old_flag: bool = False) -> int:  # noqa: ARG001
            """Keyword check."""
            return x

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Positional argument doesn't trigger (not in kwargs dict)
            _ = keyword_only_check(10, False)

            # Only keyword argument triggers
            assert len(w) == 0

    @given(
        param_name=st.text(
            min_size=2,
            max_size=50,
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        ).filter(lambda x: x not in ("x", "kwargs")),  # Exclude conflicting names
        removal_version=st.from_regex(r"\d+\.\d+\.\d+", fullmatch=True),
    )
    def test_deprecated_parameter_property_warning_contains_metadata(
        self, param_name: str, removal_version: str
    ) -> None:
        """Property: Warning always contains parameter name and version."""

        def create_decorated_func(name: str, version: str) -> Callable[[int], int]:
            """Factory to create decorated function with specific metadata."""

            @deprecated_parameter(name, removal_version=version)
            def func(x: int, **kwargs: Any) -> int:  # noqa: ARG001
                """Dynamic test function."""
                return x

            return func

        test_func = create_decorated_func(param_name, removal_version)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Pass the parameter as a keyword argument
            test_func(42, **{param_name: True})

            assert len(w) == 1
            message = str(w[0].message)
            assert param_name in message
            assert removal_version in message


class TestDeprecationIntegration:
    """Integration tests for complete deprecation workflow."""

    def test_complete_api_migration_scenario(self) -> None:
        """Test realistic API migration scenario with multiple deprecations."""

        @deprecated(removal_version="2.0.0", alternative="new_api_v2()")
        @deprecated_parameter("legacy_format", removal_version="2.0.0", alternative="output_format")
        def old_api(
            data: str,
            legacy_format: bool = False,
            output_format: str = "json",
        ) -> str:
            """Legacy API method."""
            if legacy_format:
                return f"LEGACY:{data}"
            return f"{output_format.upper()}:{data}"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Using both deprecated function and deprecated parameter
            result = old_api("test_data", legacy_format=True)

            assert result == "LEGACY:test_data"
            assert len(w) == 2  # One for function, one for parameter

            # Verify both warnings are FutureWarning
            assert all(issubclass(warning.category, FutureWarning) for warning in w)

            # Verify warning messages contain expected content
            messages = [str(warning.message) for warning in w]
            assert any("old_api()" in msg for msg in messages)
            assert any("legacy_format" in msg for msg in messages)

    def test_deprecation_warnings_respect_filter_settings(self) -> None:
        """Verify deprecation warnings respect Python's warning filter."""

        @deprecated(removal_version="1.0.0")
        def filtered_func() -> str:
            """Test function."""
            return "result"

        # Test with warnings ignored
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("ignore")
            filtered_func()
            assert len(w) == 0

        # Test with warnings set to error (should raise)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(FutureWarning):
                filtered_func()

    def test_nested_deprecated_functions(self) -> None:
        """Verify deprecation warnings work correctly in nested calls."""

        @deprecated(removal_version="1.0.0")
        def outer_deprecated() -> str:
            """Outer deprecated function."""
            return inner_deprecated()

        @deprecated(removal_version="1.0.0")
        def inner_deprecated() -> str:
            """Inner deprecated function."""
            return "nested_result"

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = outer_deprecated()

            assert result == "nested_result"
            assert len(w) == 2  # Both functions emit warnings
