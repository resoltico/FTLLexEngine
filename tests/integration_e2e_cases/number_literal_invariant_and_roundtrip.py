# mypy: ignore-errors
"""Split test cases from tests/test_integration_e2e.py."""

from tests.integration_e2e_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# NumberLiteral Invariant and Roundtrip
# =============================================================================


class TestNumberLiteralInvariant:
    """NumberLiteral enforces raw/value consistency and rejects bool."""

    def test_bool_value_rejected(self) -> None:
        """NumberLiteral rejects bool for value (bool is int subclass, not a number literal)."""
        with pytest.raises(TypeError, match="must be int or Decimal, not bool"):
            NumberLiteral(value=True, raw="1")

    def test_raw_value_inconsistency_rejected(self) -> None:
        """NumberLiteral rejects raw that parses to a different value than the value field."""
        with pytest.raises(ValueError, match=r"parses to.*but value is"):
            NumberLiteral(value=Decimal("1.5"), raw="9.9")

    def test_integer_variant_key_exact_match_roundtrip(self) -> None:
        """Integer number variant keys select the correct variant."""
        ftl = """
rating = { $stars ->
    [1] Poor
    [3] Good
    [5] Excellent
   *[other] Unknown
}
"""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(ftl)

        poor, err1 = bundle.format_pattern("rating", {"stars": 1})
        excellent, err2 = bundle.format_pattern("rating", {"stars": 5})
        fallback, err3 = bundle.format_pattern("rating", {"stars": 99})

        assert not err1
        assert not err2
        assert not err3
        assert poor == "Poor"
        assert excellent == "Excellent"
        assert fallback == "Unknown"

    def test_decimal_variant_key_roundtrip(self) -> None:
        """Decimal number variant keys in serialized FTL survive parse->format roundtrip."""
        ftl = """
precision = { $level ->
    [0.5] Half
    [1.0] Full
   *[other] Custom
}
"""
        resource = parse_ftl(ftl)
        serialized = serialize_ftl(resource)
        resource2 = parse_ftl(serialized)

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(serialize_ftl(resource2))

        # Default variant (string selector won't match numeric keys)
        result, _ = bundle.format_pattern("precision", {"level": "other"})
        assert result == "Custom"
