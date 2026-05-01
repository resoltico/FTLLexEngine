# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSER INTEGRATION SUITE
# ============================================================================


class TestParserIntegration:
    """Integration tests combining multiple edge cases."""

    def test_complex_resource(self) -> None:
        """FTL resource exercising multiple edge cases."""
        parser = FluentParserV1()
        res = parser.parse(
            "# Comment\n"
            "msg = Value\n"
            "    .a = Short attr\n"
            "\n"
            "-t = Term\n"
            "\n"
            "select = { $n ->\n"
            "    [0] Zero\n"
            "    [1] One\n"
            "   *[other] Other\n"
            "}\n"
            "\n"
            "func = { FUNC() }\n"
            "\n"
            "complex = { $a }{ $b } text { UPPER($c) }\n"
        )
        assert len(res.entries) >= 5

    def test_select_with_number_and_identifier_keys(self) -> None:
        """Select with both number and identifier variant keys."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c ->\n"
            "    [0] Zero\n"
            "    [1] One\n"
            "    [42] Forty-two\n"
            "   *[other] Other\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_select_identifier_keys(self) -> None:
        """Select with identifier variant keys."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $v ->\n"
            "    [yes] Affirmative\n"
            "   *[no] Negative\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_variant_key_negative_hyphen_not_number(self) -> None:
        """Variant key starts with - but isn't a number."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $s ->\n"
            "    [-not-a-number] Value\n"
            "   *[default] Default\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_term_attribute_selection(self) -> None:
        """Select on term attribute."""
        parser = FluentParserV1()
        res = parser.parse(
            "-term = Term\n"
            "    .attr = a\n"
            "msg = { -term.attr -> *[a] Value }\n"
        )
        assert len(res.entries) >= 1

    def test_term_reference_arguments_via_parser(self) -> None:
        """Term reference with arguments."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { -term(case: 'accusative') }"
        )
        assert len(res.entries) >= 1

    def test_pattern_with_only_placeables(self) -> None:
        """Pattern with adjacent placeables."""
        parser = FluentParserV1()
        res = parser.parse("msg = { $a }{ $b }{ $c }")
        assert len(res.entries) > 0

    def test_function_variations(self) -> None:
        """Function with various argument combinations."""
        parser = FluentParserV1()
        for src in [
            "m = { FUNC() }",
            "m = { FUNC($a, $b, $c) }",
            'm = { FUNC(key: "value", ot: "data") }',
            'm = { FUNC($p1, $p2, named: "value") }',
        ]:
            res = parser.parse(src)
            assert len(res.entries) > 0, f"Failed: {src}"
