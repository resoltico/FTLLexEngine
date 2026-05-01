# mypy: ignore-errors
"""Split test cases from tests/test_integration_e2e.py."""

from tests.integration_e2e_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Intensive Round-trip Tests (Fuzz-marked, run with pytest -m fuzz)
# =============================================================================


class TestSerializeParseRoundtrip:
    """Example-based tests for AST serialization round-trips."""

    def test_serialize_parse_simple_message(self) -> None:
        """Serialize->parse round-trip preserves simple messages."""
        ftl_source = "hello = Hello, World!"

        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)
        resource2 = parse_ftl(serialized)

        assert len(resource.entries) == len(resource2.entries)

    def test_serialize_parse_with_variables(self) -> None:
        """Serialize->parse round-trip preserves variables."""
        ftl_source = "greeting = Hello, { $name }!"

        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle1 = FluentBundle("en-US", use_isolating=False)
        bundle1.add_resource(ftl_source)

        bundle2 = FluentBundle("en-US", use_isolating=False)
        bundle2.add_resource(serialized)

        result1, _ = bundle1.format_pattern("greeting", {"name": "Test"})
        result2, _ = bundle2.format_pattern("greeting", {"name": "Test"})

        assert result1 == result2

    def test_serialize_preserves_select_expressions(self) -> None:
        """Serialize->parse preserves select expression structure."""
        ftl_source = """
count = { $n ->
    [one] One
   *[other] Many
}
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        one, _ = bundle.format_pattern("count", {"n": 1})
        many, _ = bundle.format_pattern("count", {"n": 5})

        assert "One" in one
        assert "Many" in many

    def test_serialize_preserves_term_attributes(self) -> None:
        """Serialize->parse preserves term attributes."""
        ftl_source = """
-brand = Firefox
    .short = Fx
    .full = Mozilla Firefox
msg = { -brand.short }
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        result, _ = bundle.format_pattern("msg")
        assert "Fx" in result

    def test_serialize_preserves_message_attributes(self) -> None:
        """Serialize->parse preserves message attributes."""
        ftl_source = """
button = Click me
    .accesskey = C
    .title = Submit
"""
        resource = parse_ftl(ftl_source)
        serialized = serialize_ftl(resource)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialized)

        accesskey, _ = bundle.format_pattern("button", attribute="accesskey")
        title, _ = bundle.format_pattern("button", attribute="title")

        assert accesskey == "C"
        assert title == "Submit"
