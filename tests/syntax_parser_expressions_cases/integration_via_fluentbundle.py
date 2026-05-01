# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# INTEGRATION VIA FLUENTBUNDLE
# ============================================================================


class TestExpressionsIntegration:
    """Integration tests via FluentBundle for expression paths."""

    def test_function_name_not_uppercase(self) -> None:
        """Lowercase function name fails, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource("msg = { lowercase() }")
        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0 or "{" in result

    def test_function_missing_paren(self) -> None:
        """UPPERCASE without paren treated as message reference, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource("msg = { NUMBER }")
        result, errors = bundle.format_pattern("msg")
        assert "{NUMBER}" in result or len(errors) > 0

    def test_string_literal_selector(self) -> None:
        """String literal as selector in select expression."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            'msg = {"test" ->\n'
            "    [test] Matched\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert "Matched" in result or "test" in result

    def test_number_literal_selector(self) -> None:
        """Number literal as selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {42 ->\n"
            "    [42] Exact match\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_nested_selects(self) -> None:
        """Nested select expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] {NUMBER(2) ->\n"
            "        [one] One-One\n"
            "        *[other] One-Other\n"
            "    }\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_function_with_multiple_args(self) -> None:
        """Function call with multiple named arguments, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            'msg = {NUMBER(42, style: "percent")}'
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_attribute_access(self) -> None:
        """Message attribute reference in placeable."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "base = Base\n"
            "    .attr = Attribute\n\n"
            "msg = {base.attr}"
        )
        result, _ = bundle.format_pattern("msg")
        assert "Attribute" in result

    def test_term_attribute_selector(self) -> None:
        """Term attribute as selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "-brand = Firefox\n"
            "    .version = 1\n\n"
            "msg = {-brand.version ->\n"
            "    [1] Version One\n"
            "    *[other] Other Version\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_deeply_nested_expressions(self) -> None:
        """Deep nesting of expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] {NUMBER(2) ->\n"
            "        [one] {NUMBER(3) ->\n"
            "            [one] Deep\n"
            "            *[other] Level3\n"
            "        }\n"
            "        *[other] Level2\n"
            "    }\n"
            "    *[other] Level1\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_select_missing_arrow(self) -> None:
        """Select expression without -> operator, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            "msg = {NUMBER(1)\n"
            "    [one] One\n"
            "    *[other] Other\n"
            "}"
        )
        result, _errors = bundle.format_pattern("msg")
        assert result is not None

    def test_select_missing_default_via_bundle(self) -> None:
        """Select without default variant via bundle, soft recovery."""
        bundle = FluentBundle("en_US", strict=False)
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] One\n"
            "    [two] Two\n"
            "}"
        )
        result, _errors = bundle.format_pattern("msg")
        assert result is not None

    def test_unicode_expression(self) -> None:
        """Unicode characters in expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            'msg = {"Hello \\u4E16\\u754C" ->\n'
            "    *[other] Unicode test\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None
