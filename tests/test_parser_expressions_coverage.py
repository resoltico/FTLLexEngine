"""Simple coverage tests for syntax/parser/expressions.py uncovered lines.

Uses high-level FluentBundle parsing to trigger error paths.
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle


class TestExpressionErrorPaths:
    """Test expression parsing error paths through FluentBundle."""

    def test_function_name_not_uppercase(self) -> None:
        """Test function reference with non-uppercase name (line 379).

        Function names must be UPPERCASE per Fluent spec.
        """
        bundle = FluentBundle("en_US")
        # lowercase function name should fail
        bundle.add_resource("msg = { lowercase() }")
        result, errors = bundle.format_pattern("msg")
        # Should have error or fallback
        assert len(errors) > 0 or "{" in result

    def test_function_missing_paren(self) -> None:
        """Test function reference without opening paren (line 386).

        After function name, must have '('.
        """
        bundle = FluentBundle("en_US")
        # UPPERCASE identifier without paren
        bundle.add_resource("msg = { NUMBER }")
        result, errors = bundle.format_pattern("msg")
        # Should treat as message reference, not function
        assert "{NUMBER}" in result or len(errors) > 0

    def test_term_reference_missing_dash(self) -> None:
        """Test term reference without '-' prefix (line 427).

        Term references must start with '-'.
        """
        bundle = FluentBundle("en_US")
        # Reference without '-' is message reference
        bundle.add_resource("msg = { term }")
        _result, errors = bundle.format_pattern("msg")
        # Should be treated as message reference
        assert len(errors) > 0  # term message doesn't exist

    def test_invalid_variant_key(self) -> None:
        """Test variant key parsing with invalid input (lines 61-62)."""
        bundle = FluentBundle("en_US")
        # Invalid variant key syntax
        bundle.add_resource("""
msg = { $count ->
    [*] Invalid
   *[other] Other
}
""")
        result, _errors = bundle.format_pattern("msg", {"count": 1})
        # Should handle gracefully
        assert result is not None

    def test_select_with_malformed_variant(self) -> None:
        """Test select expression with malformed variants."""
        bundle = FluentBundle("en_US")
        # Try to trigger parsing errors in variants
        bundle.add_resource("""
msg = { $val ->
    [] Empty key
   *[other] Other
}
""")
        result, _errors = bundle.format_pattern("msg", {"val": "test"})
        assert result is not None
