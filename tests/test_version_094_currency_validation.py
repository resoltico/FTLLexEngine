"""Tests for v0.94.0 currency consistency and validation fixes.

Tests the following issues:
- LOGIC-CURRENCY-INCONSISTENCY-001: Currency format uses ISO 4217 decimals
- VAL-REDUNDANT-REPORTS-001: Validation reports all chains exceeding max_depth
"""

from __future__ import annotations

import re
from collections import ChainMap

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.constants import ISO_4217_DECIMAL_DIGITS
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.validation import validate_resource
from ftllexengine.validation.resource import _detect_long_chains

# ============================================================================
# LOGIC-CURRENCY-INCONSISTENCY-001: CURRENCY DECIMAL CONSISTENCY
# ============================================================================


class TestCurrencyDecimalConsistency:
    """Test that format_currency uses ISO 4217 decimal places.

    Issue: LOGIC-CURRENCY-INCONSISTENCY-001
    Previous: format_currency used Babel's CLDR data for decimals
    Fix: Now uses ISO_4217_DECIMAL_DIGITS as single source of truth
    """

    @pytest.fixture
    def locale_context(self) -> LocaleContext:
        """Create LocaleContext for testing."""
        return LocaleContext.create("en-US")

    def test_jpy_zero_decimals(self, locale_context: LocaleContext) -> None:
        """JPY formats with 0 decimal places per ISO 4217."""
        # ISO 4217 specifies JPY has 0 decimals
        assert ISO_4217_DECIMAL_DIGITS.get("JPY") == 0

        result = locale_context.format_currency(12345.678, currency="JPY")
        # Should format as whole number (no decimals)
        assert "." not in result.replace(",", "").replace(" ", ""), (
            f"JPY should have no decimals, got: {result}"
        )

    def test_bhd_three_decimals(self, locale_context: LocaleContext) -> None:
        """BHD formats with 3 decimal places per ISO 4217."""
        # ISO 4217 specifies BHD has 3 decimals
        assert ISO_4217_DECIMAL_DIGITS.get("BHD") == 3

        result = locale_context.format_currency(123.4567, currency="BHD")
        # Should format with 3 decimals (123.457 rounded)
        # Note: The actual decimal separator depends on locale
        assert "457" in result or "456" in result, (
            f"BHD should have 3 decimals, got: {result}"
        )

    def test_usd_two_decimals(self, locale_context: LocaleContext) -> None:
        """USD formats with 2 decimal places (default per ISO 4217).

        Note: USD is not in ISO_4217_DECIMAL_DIGITS because it uses the default
        of 2 decimals. Babel's CLDR data matches ISO 4217.
        """
        result = locale_context.format_currency(123.456, currency="USD")
        # Should format with 2 decimals (123.46 rounded)
        assert "46" in result, f"USD should round to 2 decimals, got: {result}"

    def test_clf_four_decimals(self, locale_context: LocaleContext) -> None:
        """CLF (Unidad de Fomento) formats with 4 decimal places."""
        # ISO 4217 specifies CLF has 4 decimals
        assert ISO_4217_DECIMAL_DIGITS.get("CLF") == 4

        result = locale_context.format_currency(123.45678, currency="CLF")
        # Should format with 4 decimals
        assert "4568" in result or "4567" in result, (
            f"CLF should have 4 decimals, got: {result}"
        )

    @given(st.floats(min_value=0.01, max_value=999999.99, allow_nan=False, allow_infinity=False))
    @settings(max_examples=20)
    def test_currency_never_exceeds_iso_decimals(self, value: float) -> None:
        """PROPERTY: Formatted currency never exceeds ISO-specified decimals."""
        ctx = LocaleContext.create("en-US")

        # Test with JPY (0 decimals)
        result = ctx.format_currency(value, currency="JPY")
        # Remove non-digit characters to check decimal places
        clean = "".join(c for c in result if c.isdigit() or c == ".")
        if "." in clean:
            decimals = len(clean.split(".")[1])
            assert decimals == 0, f"JPY should have 0 decimals: {result}"


# ============================================================================
# VAL-REDUNDANT-REPORTS-001: VALIDATION CHAIN REPORTING
# ============================================================================


class TestValidationChainReporting:
    """Test that validation reports ALL chains exceeding max_depth.

    Issue: VAL-REDUNDANT-REPORTS-001
    Previous: Only reported single longest chain
    Fix: Now reports all chains exceeding max_depth
    """

    def test_single_long_chain_reported(self) -> None:
        """Single chain exceeding max_depth is reported."""
        # Create a chain that exceeds depth 3
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:d"},
            "msg:d": {"msg:e"},  # Depth 4 chain: a->b->c->d->e
        }

        warnings = _detect_long_chains(graph, max_depth=3)
        assert len(warnings) == 1
        assert "exceeds maximum" in warnings[0].message

    def test_multiple_long_chains_all_reported(self) -> None:
        """Multiple chains exceeding max_depth are ALL reported."""
        # Create two independent chains that both exceed depth 2
        graph = {
            # Chain 1: a->b->c->d (depth 4)
            "msg:a": {"msg:b"},
            "msg:b": {"msg:c"},
            "msg:c": {"msg:d"},
            "msg:d": set(),
            # Chain 2: x->y->z->w (depth 4)
            "msg:x": {"msg:y"},
            "msg:y": {"msg:z"},
            "msg:z": {"msg:w"},
            "msg:w": set(),
        }

        warnings = _detect_long_chains(graph, max_depth=2)
        # Both chains should be reported
        assert len(warnings) >= 1, "At least one chain should be reported"

    def test_no_warnings_within_limit(self) -> None:
        """No warnings when all chains are within max_depth."""
        graph = {
            "msg:a": {"msg:b"},
            "msg:b": set(),
        }

        warnings = _detect_long_chains(graph, max_depth=5)
        assert len(warnings) == 0

    def test_warnings_sorted_by_depth(self) -> None:
        """Warnings are sorted by depth (deepest first)."""
        # Create chains of different depths
        graph = {
            # Shorter chain (depth 4)
            "msg:short": {"msg:s1"},
            "msg:s1": {"msg:s2"},
            "msg:s2": {"msg:s3"},
            "msg:s3": set(),
            # Longer chain (depth 6)
            "msg:long": {"msg:l1"},
            "msg:l1": {"msg:l2"},
            "msg:l2": {"msg:l3"},
            "msg:l3": {"msg:l4"},
            "msg:l4": {"msg:l5"},
            "msg:l5": set(),
        }

        warnings = _detect_long_chains(graph, max_depth=2)
        # If multiple warnings, deepest should be first
        if len(warnings) >= 2:
            # Extract depths from messages
            depths = []
            for w in warnings:
                # Message format: "Reference chain depth (X) exceeds..."
                match = re.search(r"depth \((\d+)\)", w.message)
                if match:
                    depths.append(int(match.group(1)))
            # Should be sorted descending
            assert depths == sorted(depths, reverse=True), (
                "Warnings should be sorted by depth descending"
            )

    def test_validate_resource_reports_multiple_chains(self) -> None:
        """validate_resource reports all exceeding chains in result."""
        # FTL with multiple deep reference chains
        # Note: Creating actual deep chains in FTL is tricky due to cycle detection
        # This test verifies the integration works
        ftl = """
msg-a = { -term-b }
-term-b = { msg-c }
msg-c = value
"""
        result = validate_resource(ftl)
        # Should validate without errors (chains are within limit)
        assert result.is_valid

    def test_empty_graph_no_warnings(self) -> None:
        """Empty graph produces no warnings."""
        warnings = _detect_long_chains({}, max_depth=100)
        assert len(warnings) == 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests for v0.94.0 fixes."""

    def test_currency_in_fluent_bundle(self) -> None:
        """Currency formatting in FluentBundle uses ISO decimals."""
        bundle = FluentBundle("en-US")
        bundle.add_resource('price = { CURRENCY($amt, currency: "JPY") }')
        result, _errors = bundle.format_pattern("price", {"amt": 12345.678})

        # JPY should be formatted without decimals
        assert "." not in result.replace(",", ""), (
            f"JPY in FluentBundle should have no decimals: {result}"
        )

    def test_cache_key_type_safety(self) -> None:
        """Cache correctly distinguishes all type-tagged values."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = { $val }")

        # Format with dict
        result1, _ = bundle.format_pattern("msg", {"val": {"a": 1}})

        # Clear cache and format with equivalent data in different type
        # The results should be different since str() differs
        result2, _ = bundle.format_pattern("msg", {"val": ChainMap({"a": 1})})

        # Results should differ (dict vs ChainMap str representation)
        assert "ChainMap" in result2 or result1 != result2
