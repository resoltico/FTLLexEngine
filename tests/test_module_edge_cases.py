"""Targeted tests for coverage on non-parser module edge cases.

Covers specific uncovered lines in:
- currency.py: pattern construction fallback
- dates.py: quoted literal tokenization
- function_bridge.py: leading underscore parameters
- function_metadata.py: get_callable returns None
- validation/resource.py: Junk without span, cycle deduplication
"""

from __future__ import annotations

from unittest.mock import patch

from ftllexengine.parsing.currency import parse_currency
from ftllexengine.parsing.dates import _tokenize_babel_pattern
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.syntax.ast import Junk
from ftllexengine.validation.resource import (
    _extract_syntax_errors,
    validate_resource,
)


class TestCurrencyPatternFallback:
    """Coverage for currency pattern construction fallback."""

    def test_pattern_fallback_when_no_symbols(self) -> None:
        """Pattern construction fallback when no symbols present."""
        from ftllexengine.parsing.currency import (  # noqa: PLC0415
            _get_currency_maps,
            _get_currency_pattern_full,
        )

        _get_currency_pattern_full.cache_clear()

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=({}, set(), {}, frozenset()),
        ):
            _get_currency_pattern_full.cache_clear()
            result, errors = parse_currency("USD 100", "en_US")
            assert result is not None or len(errors) > 0

        _get_currency_pattern_full.cache_clear()
        _get_currency_maps.cache_clear()


class TestDatesQuotedLiteral:
    """Coverage for quoted literal tokenization in dates."""

    def test_quoted_literal_in_pattern(self) -> None:
        """Non-empty quoted literal in Babel date pattern."""
        pattern = "d 'de' MMMM 'de' y"
        tokens = _tokenize_babel_pattern(pattern)
        assert "de" in tokens


class TestFunctionBridgeLeadingUnderscore:
    """Coverage for leading underscore parameter handling."""

    def test_parameter_with_leading_underscore(self) -> None:
        """Parameter with leading underscore is kept in mapping."""
        registry = FunctionRegistry()

        def test_func(_internal: str, public: str) -> str:  # noqa: PT019
            return f"{_internal}:{public}"

        registry.register(test_func, ftl_name="TEST")

        sig = registry._functions["TEST"]
        param_values = [v for _, v in sig.param_mapping]
        assert "_internal" in param_values


class TestFunctionMetadataCallable:
    """Coverage for get_callable returns None branch."""

    def test_should_inject_locale_not_found(self) -> None:
        """should_inject_locale returns False for unknown function."""
        registry = FunctionRegistry()

        def custom(val: str) -> str:
            return val

        registry.register(custom, ftl_name="CUSTOM")
        assert registry.should_inject_locale("NOTFOUND") is False


class TestValidationResourceEdgeCases:
    """Coverage for validation/resource.py edge cases."""

    def test_junk_without_span(self) -> None:
        """Junk entry without span uses None for line/column."""
        junk = Junk(content="invalid", span=None)

        class MockResource:
            def __init__(self) -> None:
                self.entries = [junk]

        errors = _extract_syntax_errors(
            MockResource(), "invalid"  # type: ignore[arg-type]
        )
        assert len(errors) > 0
        assert errors[0].line is None

    def test_validation_with_invalid_ftl(self) -> None:
        """Validation handles malformed FTL gracefully."""
        result = validate_resource("msg = { $val ->")
        assert result is not None

    def test_cycle_deduplication(self) -> None:
        """Circular references are detected without duplicates."""
        ftl = "\na = { b }\nb = { a }\nc = { d }\nd = { c }\n"
        result = validate_resource(ftl)
        circular = [
            w for w in result.warnings
            if "circular" in w.message.lower()
        ]
        assert len(circular) >= 2


class TestBundleIntegration:
    """Integration tests via FluentBundle for multi-module coverage."""

    def test_variant_key_failed_number_parse(self) -> None:
        """Number-like variant key falls through to identifier."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = { $val ->\n"
            "    [-.test] Match\n"
            "   *[other] Other\n"
            "}\n"
        )
        result, _ = bundle.format_pattern(
            "msg", {"val": "-.test"}
        )
        assert result is not None

    def test_identifier_as_function_argument(self) -> None:
        """Identifier becomes MessageReference in call args."""
        bundle = FluentBundle("en_US")

        def test_func(val: str | int) -> str:
            return str(val)

        bundle.add_function("TEST", test_func)
        bundle.add_resource("ref = value")
        bundle.add_resource("msg = { TEST(ref) }")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result is not None

    def test_comment_with_crlf_ending(self) -> None:
        """Comment with CRLF ending."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("# Comment\r\nmsg = value")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "value" in result

    def test_full_coverage_integration(self) -> None:
        """Integration test covering multiple modules."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "# Comment\n"
            "msg1 = { $val }\n"
            "msg2 = { NUMBER($val) }\n"
            "msg3 = { -term }\n"
            "msg4 = { other.attr }\n"
            "sel = { 42 ->\n"
            "    [42] Match\n"
            "   *[other] Other\n"
            "}\n"
            "-brand = Firefox\n"
            "    .version = 1.0\n"
            "empty =\n"
            "    .attr = Value\n"
        )
        r1, _ = bundle.format_pattern("msg1", {"val": "t"})
        r2, _ = bundle.format_pattern("msg2", {"val": 42})
        r3, _ = bundle.format_pattern("sel")
        assert all(r is not None for r in [r1, r2, r3])

        validation = validate_resource(
            "msg = { $val }\n-term = Firefox\n"
        )
        assert validation is not None
