"""Systems-based tests for API consistency contracts.

Tests patterns that prevent recurring issues:
1. Type guard None-acceptance - all guards must handle None uniformly
2. Thread-local cleanup - parse functions must clear stale error context
3. Exception specificity - broad catches must not mask unexpected errors

These tests verify structural properties of the API rather than specific behaviors.
They catch regressions where new code violates established patterns.

Compliance:
- Hypothesis-first for property verification
- Tests architectural invariants, not just behavior
- Prevents future regressions through systematic coverage
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, get_type_hints

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

if TYPE_CHECKING:
    from collections.abc import Iterator


# =============================================================================
# TEST INFRASTRUCTURE
# =============================================================================


def get_module_functions(module_path: Path) -> Iterator[tuple[str, ast.FunctionDef]]:
    """Extract function definitions from a module file."""
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            yield node.name, node


def get_exception_handlers(func_node: ast.FunctionDef) -> list[ast.ExceptHandler]:
    """Extract all exception handlers from a function AST."""
    handlers = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.ExceptHandler):
            handlers.append(node)
    return handlers


def get_handler_exception_type(handler: ast.ExceptHandler) -> str | None:
    """Get the exception type name from an ExceptHandler."""
    if handler.type is None:
        return "bare"
    if isinstance(handler.type, ast.Name):
        return handler.type.id
    if isinstance(handler.type, ast.Tuple):
        # Multiple exception types - return first for identification
        names = []
        for elt in handler.type.elts:
            if isinstance(elt, ast.Name):
                names.append(elt.id)
        return f"({', '.join(names)})"
    return None


# =============================================================================
# CONTRACT 1: TYPE GUARD NONE-ACCEPTANCE
# =============================================================================


class TestTypeGuardNoneAcceptanceContract:
    """Verify all type guards accept None and return False.

    Pattern: Type guards that validate parse results MUST:
    1. Accept None in their signature (result | None)
    2. Return False when given None
    3. Never raise exceptions on None input

    This enables the simplified pattern: if is_valid_X(result): ...
    Instead of: if not errors and is_valid_X(result): ...
    """

    def test_all_type_guards_accept_none(self) -> None:
        """CONTRACT: All is_valid_* guards accept None without raising."""
        from ftllexengine.parsing.guards import (
            is_valid_currency,
            is_valid_date,
            is_valid_datetime,
            is_valid_decimal,
            is_valid_number,
        )

        guards: list[Callable[..., bool]] = [
            is_valid_decimal,
            is_valid_number,
            is_valid_currency,
            is_valid_date,
            is_valid_datetime,
        ]

        for guard in guards:
            # Must not raise
            result = guard(None)
            # Must return False
            assert result is False, f"{guard.__name__} should return False for None"

    def test_type_guard_signatures_include_none(self) -> None:
        """CONTRACT: Type guard signatures must include None in union."""
        from ftllexengine.parsing import guards

        guard_names = [
            "is_valid_decimal",
            "is_valid_number",
            "is_valid_currency",
            "is_valid_date",
            "is_valid_datetime",
        ]

        for name in guard_names:
            guard = getattr(guards, name)
            hints = get_type_hints(guard)

            # Get the first parameter type (value)
            params = list(hints.keys())
            assert len(params) >= 1, f"{name} must have at least one parameter"

            value_type = hints[params[0]]
            type_str = str(value_type)

            # Must include None in the union
            assert "None" in type_str, (
                f"{name} signature must include None: got {type_str}"
            )

    @given(st.none())
    @settings(max_examples=10)
    def test_none_input_property(self, value: None) -> None:
        """PROPERTY: None input always yields False for all guards."""
        from ftllexengine.parsing.guards import (
            is_valid_currency,
            is_valid_date,
            is_valid_datetime,
            is_valid_decimal,
            is_valid_number,
        )

        assert is_valid_decimal(value) is False
        assert is_valid_number(value) is False
        assert is_valid_currency(value) is False
        assert is_valid_date(value) is False
        assert is_valid_datetime(value) is False


# =============================================================================
# CONTRACT 2: THREAD-LOCAL CLEANUP
# =============================================================================


class TestThreadLocalCleanupContract:
    """Verify parse functions clear stale error context.

    Pattern: Parse functions using thread-local error storage MUST:
    1. Clear error context at function start
    2. Not leak errors from previous parse attempts
    3. Return None error after successful parse

    This prevents stale error data from confusing error handling.
    """

    def test_successful_parse_clears_stale_error(self) -> None:
        """CONTRACT: Successful parse clears any stale error context."""
        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser.primitives import (
            get_last_parse_error,
            parse_identifier,
            parse_number,
        )

        # Create stale error by failing a parse
        cursor1 = Cursor(source="-invalid", pos=0)
        parse_number(cursor1)
        stale_error = get_last_parse_error()
        assert stale_error is not None, "Setup: should have stale error"

        # Successful parse must clear the stale error
        cursor2 = Cursor(source="validIdentifier", pos=0)
        result = parse_identifier(cursor2)
        assert result is not None, "Parse should succeed"

        # Error context should be cleared
        error_after = get_last_parse_error()
        assert error_after is None, "Stale error should be cleared after success"

    def test_all_primitive_parsers_clear_error(self) -> None:
        """CONTRACT: All primitive parsers clear error context on success."""
        from ftllexengine.syntax.cursor import Cursor
        from ftllexengine.syntax.parser.primitives import (
            clear_parse_error,
            get_last_parse_error,
            parse_identifier,
            parse_number,
            parse_string_literal,
        )

        # Test cases: (parser_func, valid_input)
        test_cases = [
            (parse_identifier, "validId"),
            (parse_number, "123"),
            (parse_number, "-456"),
            (parse_number, "78.9"),
            (parse_string_literal, '"hello"'),
        ]

        for parser_func, valid_input in test_cases:
            # Create stale error
            bad_cursor = Cursor(source="!!!", pos=0)
            parse_identifier(bad_cursor)
            assert get_last_parse_error() is not None

            # Parse valid input
            good_cursor = Cursor(source=valid_input, pos=0)
            result = parser_func(good_cursor)

            if result is not None:
                # Successful parse must clear error
                error = get_last_parse_error()
                assert error is None, (
                    f"{parser_func.__name__}({valid_input!r}) "
                    "should clear stale error on success"
                )

            clear_parse_error()  # Clean up for next iteration


# =============================================================================
# CONTRACT 3: EXCEPTION SPECIFICITY
# =============================================================================


class TestExceptionSpecificityContract:
    """Verify exception handlers use specific types.

    Pattern: Exception handlers in production code MUST:
    1. NOT use bare except:
    2. NOT use except Exception: without justification
    3. Use specific exception types (ValueError, TypeError, etc.)

    This ensures unexpected errors propagate for debugging.
    """

    def test_no_bare_except_in_parsing_modules(self) -> None:
        """CONTRACT: No bare except: in parsing modules."""
        src_dir = Path(__file__).parent.parent / "src" / "ftllexengine" / "parsing"

        violations = []
        for py_file in src_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            for func_name, func_node in get_module_functions(py_file):
                for handler in get_exception_handlers(func_node):
                    exc_type = get_handler_exception_type(handler)
                    if exc_type == "bare":
                        violations.append(
                            f"{py_file.name}:{handler.lineno} "
                            f"in {func_name}: bare except"
                        )

        assert not violations, (
            "Found bare except handlers:\n" + "\n".join(violations)
        )

    def test_no_broad_exception_in_runtime_modules(self) -> None:
        """CONTRACT: No except Exception: in runtime modules without comment."""
        src_dir = Path(__file__).parent.parent / "src" / "ftllexengine" / "runtime"

        violations = []
        for py_file in src_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            source_lines = py_file.read_text(encoding="utf-8").splitlines()

            for func_name, func_node in get_module_functions(py_file):
                for handler in get_exception_handlers(func_node):
                    exc_type = get_handler_exception_type(handler)

                    if exc_type == "Exception":
                        # Check if there's a justifying comment
                        line_text = source_lines[handler.lineno - 1]
                        has_comment = "#" in line_text

                        if not has_comment:
                            violations.append(
                                f"{py_file.name}:{handler.lineno} "
                                f"in {func_name}: except Exception without comment"
                            )

        assert not violations, (
            "Found unjustified broad exception handlers:\n" + "\n".join(violations)
        )

    def test_currency_module_uses_specific_exceptions(self) -> None:
        """CONTRACT: currency.py uses specific exception types."""
        from ftllexengine.parsing import currency

        source = inspect.getsource(currency)

        # Should NOT have bare "except Exception:"
        assert "except Exception:" not in source, (
            "currency.py should not use bare 'except Exception:'"
        )

        # Should have specific exception tuples
        assert "UnknownLocaleError" in source or "ValueError" in source, (
            "currency.py should catch specific exceptions"
        )


# =============================================================================
# CONTRACT 4: API RETURN TYPE CONSISTENCY
# =============================================================================


class TestApiReturnTypeConsistency:
    """Verify parse functions return consistent tuple types.

    Pattern: All parse_* functions MUST:
    1. Return tuple[result | None, tuple[Error, ...]]
    2. Use immutable error tuples (not lists)
    3. Return None result on error (not raise)
    """

    def test_parse_functions_return_tuples(self) -> None:
        """CONTRACT: All parse functions return (result, errors) tuples."""
        from ftllexengine.parsing import (
            parse_currency,
            parse_date,
            parse_datetime,
            parse_decimal,
            parse_number,
        )

        parse_funcs = [
            (parse_decimal, "invalid", "en_US"),
            (parse_number, "invalid", "en_US"),
            (parse_currency, "invalid", "en_US"),
            (parse_date, "invalid", "en_US"),
            (parse_datetime, "invalid", "en_US"),
        ]

        for func, test_input, locale in parse_funcs:
            result = func(test_input, locale)  # type: ignore[operator]

            # Must return tuple
            assert isinstance(result, tuple), (
                f"{func.__name__} must return tuple, got {type(result)}"
            )

            # Must have exactly 2 elements
            assert len(result) == 2, (
                f"{func.__name__} must return 2-tuple, got {len(result)}"
            )

            _value, errors = result

            # Errors must be tuple (immutable)
            assert isinstance(errors, tuple), (
                f"{func.__name__} errors must be tuple, got {type(errors)}"
            )

    def test_parse_errors_are_immutable(self) -> None:
        """CONTRACT: Parse error tuples are immutable."""
        from ftllexengine.parsing import parse_decimal

        _, errors = parse_decimal("invalid", "en_US")

        # Errors tuple should be immutable
        assert isinstance(errors, tuple)
        assert len(errors) > 0, "Need at least one error for immutability test"

        # Attempting to modify should raise TypeError
        with pytest.raises(TypeError):
            errors[0] = "modified"  # type: ignore[index]  # pylint: disable=unsupported-assignment-operation


# =============================================================================
# CONTRACT 5: FUNCTION SIGNATURE STABILITY
# =============================================================================


class TestFunctionSignatureStability:
    """Verify public API signatures remain stable.

    Pattern: Public API functions MUST:
    1. Maintain parameter order
    2. Keep required parameters required
    3. Not remove parameters without major version bump
    """

    def test_parse_decimal_signature(self) -> None:
        """CONTRACT: parse_decimal(value, locale_code) signature stable."""
        from ftllexengine.parsing import parse_decimal

        sig = inspect.signature(parse_decimal)
        params = list(sig.parameters.keys())

        assert params[0] == "value", "First param must be 'value'"
        assert params[1] == "locale_code", "Second param must be 'locale_code'"

    def test_type_guard_signatures(self) -> None:
        """CONTRACT: Type guard signatures take single 'value' param."""
        from ftllexengine.parsing.guards import (
            is_valid_currency,
            is_valid_date,
            is_valid_datetime,
            is_valid_decimal,
            is_valid_number,
        )

        guards = [
            is_valid_decimal,
            is_valid_number,
            is_valid_currency,
            is_valid_date,
            is_valid_datetime,
        ]

        for guard in guards:
            sig = inspect.signature(guard)  # type: ignore[arg-type]
            params = list(sig.parameters.keys())

            assert len(params) == 1, (
                f"{guard.__name__} must have exactly 1 param, got {len(params)}"
            )
            assert params[0] == "value", (
                f"{guard.__name__} param must be 'value', got {params[0]}"
            )
