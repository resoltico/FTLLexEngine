"""Tests for Decimal variant matching and serializer depth guard.

This module tests:
1. Decimal exact variant matching (fractional Decimals match correctly)
2. Serializer depth guard (SerializationDepthError on deep nesting)
3. Hypothesis property tests for numeric comparison invariants

Python 3.13+.
"""

from decimal import Decimal

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    StringLiteral,
)
from ftllexengine.syntax.serializer import (
    SerializationDepthError,
    serialize,
)


class TestDecimalExactVariantMatching:
    """Tests for Decimal exact variant matching in SelectExpression."""

    def test_decimal_integer_matches_integer_variant(self) -> None:
        """Decimal('1') should match [1] variant."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [1] exactly one
    [one] plural one
   *[other] { $count } items
}
""")
        result, errors = bundle.format_pattern("items", {"count": Decimal("1")})
        assert result == "exactly one"
        assert not errors

    def test_decimal_fractional_matches_fractional_variant(self) -> None:
        """Decimal('1.1') should match [1.1] variant."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
price = { $amount ->
    [1.1] special price
    [2.5] discount price
   *[other] regular price { $amount }
}
""")
        # Decimal comparison implementation handles float/Decimal correctly
        result, errors = bundle.format_pattern("price", {"amount": Decimal("1.1")})
        assert result == "special price"
        assert not errors

    def test_decimal_0_1_matches_variant(self) -> None:
        """Decimal('0.1') should match [0.1] variant."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
rate = { $value ->
    [0.1] ten percent
    [0.5] half
   *[other] { $value }
}
""")
        result, errors = bundle.format_pattern("rate", {"value": Decimal("0.1")})
        assert result == "ten percent"
        assert not errors

    def test_decimal_0_3_matches_variant(self) -> None:
        """Decimal('0.3') should match [0.3] variant (IEEE 754 edge case)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
fraction = { $val ->
    [0.3] one third approx
   *[other] { $val }
}
""")
        # 0.3 is not exactly representable in float, but Decimal('0.3') is exact
        result, errors = bundle.format_pattern("fraction", {"val": Decimal("0.3")})
        assert result == "one third approx"
        assert not errors

    def test_float_still_works_for_binary_exact(self) -> None:
        """Float values exactly representable in binary still match."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
half = { $val ->
    [0.5] exactly half
   *[other] { $val }
}
""")
        # 0.5 = 1/2 is exactly representable in binary
        result, errors = bundle.format_pattern("half", {"val": 0.5})
        assert result == "exactly half"
        assert not errors

    def test_int_matches_decimal_variant(self) -> None:
        """Integer argument should match Decimal-valued variant key."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
count = { $n ->
    [5] five exactly
   *[other] { $n }
}
""")
        result, errors = bundle.format_pattern("count", {"n": 5})
        assert result == "five exactly"
        assert not errors

    def test_plural_category_fallback_still_works(self) -> None:
        """Plural category matching still works when no exact match."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
items = { $count ->
    [one] one item
   *[other] { $count } items
}
""")
        result, errors = bundle.format_pattern("items", {"count": Decimal("1")})
        # Should match [one] via plural category
        assert result == "one item"
        assert not errors


class TestDecimalMatchingHypothesis:
    """Property-based tests for Decimal variant matching."""

    @given(
        numerator=st.integers(min_value=0, max_value=999),
        denominator=st.integers(min_value=1, max_value=99),
    )
    @settings(max_examples=200)
    def test_decimal_matches_its_own_variant(
        self, numerator: int, denominator: int
    ) -> None:
        """Property: Decimal(n/d) matches variant [n/d] when variant exists."""
        # Create a decimal value
        decimal_value = Decimal(numerator) / Decimal(denominator)
        decimal_str = str(decimal_value)
        is_int = decimal_value == int(decimal_value)
        kind = "integer" if is_int else "fractional"
        event(f"outcome={kind}")

        # Skip if string representation is too long (would create invalid FTL)
        if len(decimal_str) > 20:
            return

        bundle = FluentBundle("en", use_isolating=False)
        ftl_source = f"""
test = {{ $val ->
    [{decimal_str}] matched
   *[other] not matched
}}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("test", {"val": decimal_value})
        assert result == "matched", f"Decimal({decimal_str}) should match [{decimal_str}]"
        assert not errors

    @given(n=st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100)
    def test_integer_decimal_matches_integer_variant(self, n: int) -> None:
        """Property: Decimal(n) matches variant [n] for any integer n."""
        sign = "negative" if n < 0 else "non_negative"
        event(f"outcome={sign}")

        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(f"""
num = {{ $val ->
    [{n}] matched
   *[other] not matched
}}
""")
        result, errors = bundle.format_pattern("num", {"val": Decimal(n)})
        assert result == "matched"
        assert not errors

    @given(
        whole=st.integers(min_value=0, max_value=99),
        frac=st.integers(min_value=1, max_value=9),
    )
    @settings(max_examples=100)
    @example(whole=1, frac=1)  # Regression test for 1.1 case
    @example(whole=0, frac=1)  # Regression test for 0.1 case
    @example(whole=0, frac=3)  # Regression test for 0.3 case
    def test_single_decimal_place_matches(self, whole: int, frac: int) -> None:
        """Property: Decimal('X.Y') matches [X.Y] for single decimal place."""
        lead = "zero_whole" if whole == 0 else "nonzero"
        event(f"outcome={lead}")

        decimal_str = f"{whole}.{frac}"
        decimal_value = Decimal(decimal_str)

        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(f"""
val = {{ $x ->
    [{decimal_str}] yes
   *[other] no
}}
""")
        result, errors = bundle.format_pattern("val", {"x": decimal_value})
        assert result == "yes", f"Decimal('{decimal_str}') should match [{decimal_str}]"
        assert not errors


class TestSerializerDepthGuard:
    """Tests for serializer depth limiting."""

    @staticmethod
    def _make_nested_placeable(depth: int) -> Placeable:
        """Create a deeply nested Placeable structure iteratively."""
        current: Placeable = Placeable(expression=StringLiteral(value="leaf"))
        for _ in range(depth):
            current = Placeable(expression=current)
        return current

    def test_normal_serialization_works(self) -> None:
        """Normal AST serialization should work without issues."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=StringLiteral(value="hello")),)
            ),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert "hello" in result
        assert result.startswith("test = ")

    def test_depth_limit_enforced(self) -> None:
        """Serialization should raise SerializationDepthError on deep nesting."""
        nested = self._make_nested_placeable(150)
        msg = Message(
            id=Identifier(name="deep"),
            value=Pattern(elements=(nested,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError) as exc_info:
            serialize(resource)

        # Check for depth limit error message
        error_msg = str(exc_info.value).lower()
        assert "depth limit exceeded" in error_msg or "maximum" in error_msg
        assert "100" in str(exc_info.value)

    def test_custom_max_depth(self) -> None:
        """Custom max_depth parameter should be respected."""
        nested = self._make_nested_placeable(150)
        msg = Message(
            id=Identifier(name="deep"),
            value=Pattern(elements=(nested,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        # Should succeed with higher limit
        result = serialize(resource, max_depth=200)
        assert "leaf" in result

    def test_depth_exactly_at_limit(self) -> None:
        """Depth exactly at limit should work."""
        nested = self._make_nested_placeable(99)  # 99 + 1 for pattern = 100
        msg = Message(
            id=Identifier(name="edge"),
            value=Pattern(elements=(nested,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        # Should succeed at exactly the limit
        result = serialize(resource)
        assert "leaf" in result

    def test_depth_one_over_limit_fails(self) -> None:
        """Depth one over limit should fail."""
        nested = self._make_nested_placeable(101)
        msg = Message(
            id=Identifier(name="over"),
            value=Pattern(elements=(nested,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource)

    def test_validate_still_works_with_depth_guard(self) -> None:
        """Validation should still work alongside depth guard."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=StringLiteral(value="ok")),)
            ),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        assert "ok" in result


class TestSerializerDepthGuardHypothesis:
    """Property-based tests for serializer depth guard."""

    @given(depth=st.integers(min_value=1, max_value=50))
    @settings(max_examples=50)
    def test_serialization_succeeds_within_limit(self, depth: int) -> None:
        """Property: Serialization succeeds for depth within limit."""
        event(f"depth={depth}")

        current: Placeable = Placeable(expression=StringLiteral(value="inner"))
        for _ in range(depth):
            current = Placeable(expression=current)

        msg = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(current,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        # Should succeed for reasonable depth
        result = serialize(resource)
        assert "inner" in result

    @given(depth=st.integers(min_value=101, max_value=150))
    @settings(max_examples=20)
    def test_serialization_fails_over_limit(self, depth: int) -> None:
        """Property: Serialization fails for depth over limit."""
        event(f"depth={depth}")

        current: Placeable = Placeable(expression=StringLiteral(value="deep"))
        for _ in range(depth):
            current = Placeable(expression=current)

        msg = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(current,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource)

    @given(
        depth=st.integers(min_value=50, max_value=150),
        max_depth=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=50)
    def test_custom_depth_limit_property(self, depth: int, max_depth: int) -> None:
        """Property: Serialization respects custom max_depth parameter."""
        result_kind = "success" if depth < max_depth else "failure"
        event(f"outcome={result_kind}")

        current: Placeable = Placeable(expression=StringLiteral(value="x"))
        for _ in range(depth):
            current = Placeable(expression=current)

        msg = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(current,)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(msg,))

        if depth < max_depth:
            # Should succeed
            result = serialize(resource, max_depth=max_depth)
            assert "x" in result
        else:
            # Should fail
            with pytest.raises(SerializationDepthError):
                serialize(resource, max_depth=max_depth)
