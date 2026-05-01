# mypy: ignore-errors
"""Split test cases from tests/test_integration_e2e.py."""

from tests.integration_e2e_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Multi-Module Pipeline Tests
# =============================================================================


class TestMultiModuleIntegration:
    """Integration tests exercising parse->validate->serialize->introspect pipeline."""

    def test_parse_validate_serialize_roundtrip(self) -> None:
        """Complete roundtrip: parse -> validate -> serialize -> re-parse preserves structure."""
        ftl = """
msg = Hello { $name }
    .title = Title

-brand = Firefox

plural = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        result = validate_resource(ftl)
        assert result.is_valid

        serialized = serialize(resource)
        resource2 = parser.parse(serialized)

        assert len(resource2.entries) == len(resource.entries)

    def test_introspect_complex_message(self) -> None:
        """Introspect message with select expression, term reference, and function call."""
        ftl = """
complex = { NUMBER($count) ->
    [one] { -brand } has { $count } item
   *[other] { -brand } has { NUMBER($count) } items
}
    .hint = { $hint }
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        info = introspect_message(msg)

        var_names = {v.name for v in info.variables}
        func_names = {f.name for f in info.functions}
        assert "count" in var_names
        assert "hint" in var_names
        assert info.has_selectors
        assert "NUMBER" in func_names


class TestValidationRuntimeConsistency:
    """Validation warnings predict runtime resolution failures."""

    def test_chain_depth_warning_matches_runtime_error(self) -> None:
        """VALIDATION_CHAIN_DEPTH_EXCEEDED warning implies MAX_DEPTH_EXCEEDED at runtime."""
        chain_length = MAX_DEPTH + 5
        messages = ["msg-0 = Base"]
        for i in range(1, chain_length):
            messages.append(f"msg-{i} = {{ msg-{i - 1} }}")

        ftl_source = "\n".join(messages)

        result = validate_resource(ftl_source)
        has_chain_warning = any(
            w.code == DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED
            for w in result.warnings
        )
        assert has_chain_warning

        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(ftl_source)
        _, errors = bundle.format_pattern(f"msg-{chain_length - 1}")
        has_depth_error = any(
            e.diagnostic is not None
            and e.diagnostic.code.name == "MAX_DEPTH_EXCEEDED"
            for e in errors
        )
        assert has_depth_error
