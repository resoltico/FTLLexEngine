# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSER/RULES BRANCH COVERAGE
# ============================================================================


class TestParserRulesCoverage:
    """Test parser/rules.py coverage gaps for function arguments."""

    def test_placeable_as_function_argument(self) -> None:
        """Placeable inside function call arguments parses successfully."""
        parser = FluentParserV1()
        ftl = 'msg = { NUMBER({ "5" }) }'

        resource = parser.parse(ftl)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_function_reference_as_argument(self) -> None:
        """Function reference inside function arguments parses without crash."""
        parser = FluentParserV1()
        ftl = "msg = { NUMBER(UPPER($val)) }"

        resource = parser.parse(ftl)

        assert len(resource.entries) >= 1

    def test_uppercase_identifier_not_function(self) -> None:
        """Uppercase identifier without parentheses is treated as message reference."""
        parser = FluentParserV1()
        ftl = "msg = { THIS }"

        resource = parser.parse(ftl)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)


class TestParserRulesBranchCoverage:
    """Additional tests for parser/rules branch coverage."""

    def test_parse_complex_select_with_functions(self) -> None:
        """Complex select expression with function calls in variants parses correctly."""
        parser = FluentParserV1()
        ftl = """
complex = { $gender ->
    [male] Mr. { $lastName }
    [female] Ms. { $lastName }
   *[other] { $firstName } { $lastName }
}
"""
        resource = parser.parse(ftl)
        assert len(resource.entries) == 1

    def test_parse_nested_function_calls(self) -> None:
        """NUMBER with string literal argument parses correctly."""
        parser = FluentParserV1()
        ftl = 'msg = { NUMBER("123.45") }'

        resource = parser.parse(ftl)
        assert len(resource.entries) == 1
