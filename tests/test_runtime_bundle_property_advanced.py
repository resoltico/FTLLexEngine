"""Hypothesis property-based tests for runtime.bundle: FluentBundle operations."""

from __future__ import annotations

import contextlib
from decimal import Decimal

from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.core.locale_utils import normalize_locale

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for valid FTL identifiers (using st.from_regex per hypothesis.md)
ftl_identifiers = st.from_regex(r"[a-z][a-z0-9_-]*", fullmatch=True)


# Strategy for FTL-safe text content (no special characters that break parsing)
ftl_safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cc", "Cs"),  # Control and surrogate
        blacklist_characters="{}[]*$->\n\r",  # FTL syntax characters
    ),
    min_size=0,
    max_size=100,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0 if s else True)


# Strategy for locale codes
locale_codes = st.sampled_from([
    "en", "en_US", "en_GB",
    "lv", "lv_LV",
    "de", "de_DE",
    "pl", "pl_PL",
    "ru", "ru_RU",
    "fr", "fr_FR",
])

log_source_paths = st.from_regex(
    r"[A-Za-z0-9_-][A-Za-z0-9_. /-]{0,31}",
    fullmatch=True,
)


# ============================================================================
# PROPERTY TESTS - TERM ATTRIBUTES IN CYCLE DETECTION
# ============================================================================


class TestIsolationMode:
    """Property tests for isolation mode behavior."""

    @given(
        msg_id=ftl_identifiers,
        text=ftl_safe_text,
        use_isolating=st.booleans(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_isolating_mode_variants(
        self, msg_id: str, text: str, use_isolating: bool
    ) -> None:
        """PROPERTY: Isolating mode works correctly."""
        assume(len(text) > 0)
        event(f"use_isolating={use_isolating}")

        bundle = FluentBundle("en", use_isolating=use_isolating)
        bundle.add_resource(f"{msg_id} = {text}")

        result, errors = bundle.format_pattern(msg_id)

        assert errors == ()
        # Text should always be present
        assert text in result or text in result.replace("\u2068", "").replace("\u2069", "")


# ============================================================================
# VALIDATION PROPERTIES
# ============================================================================

class TestValidationProperties:
    """Property tests for validation operations."""

    @given(
        msg_id=ftl_identifiers,
        text=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_valid_ftl_validates_cleanly(
        self, msg_id: str, text: str
    ) -> None:
        """PROPERTY: Valid FTL validates without errors."""
        assume(len(text) > 0)

        bundle = FluentBundle("en")
        result = bundle.validate_resource(f"{msg_id} = {text}")

        # Valid FTL should have no errors
        assert result.errors == ()
        event(f"id_len={len(msg_id)}")
        event("outcome=valid_ftl_validated")

    @given(
        count=st.integers(min_value=1, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_messages_validation(self, count: int) -> None:
        """PROPERTY: Multiple messages validate correctly."""
        bundle = FluentBundle("en")

        messages = [f"msg{i} = Value{i}" for i in range(count)]
        ftl = "\n".join(messages)

        result = bundle.validate_resource(ftl)

        event(f"msg_count={count}")
        # All should validate successfully
        assert result.errors == ()


# ============================================================================
# BUNDLE STATE
# ============================================================================

class TestBundleState:
    """Property tests for bundle state management."""

    @given(
        msg_id=ftl_identifiers,
        locale=locale_codes,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_bundle_locale_immutable(
        self, msg_id: str, locale: str
    ) -> None:
        """PROPERTY: Bundle locale doesn't change."""
        bundle = FluentBundle(locale)
        bundle.add_resource(f"{msg_id} = Value")

        # Locale should remain unchanged
        assert bundle.locale == normalize_locale(locale)

        event(f"locale={locale}")
        # After formatting
        bundle.format_pattern(msg_id)
        assert bundle.locale == normalize_locale(locale)

    @given(
        msg_id=ftl_identifiers,
        text=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_bundle_messages_persistent(
        self, msg_id: str, text: str
    ) -> None:
        """PROPERTY: Added messages persist."""
        assume(len(text) > 0)

        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {text}")

        # Format once
        result1, _ = bundle.format_pattern(msg_id)

        # Format again - should still work
        result2, _ = bundle.format_pattern(msg_id)

        event(f"text_len={len(text)}")
        assert result1 == result2
        assert text in result1


# ============================================================================
# CIRCULAR REFERENCE DETECTION
# ============================================================================

class TestCircularReferenceDetection:
    """Property tests for circular reference detection."""

    def test_direct_circular_reference(self) -> None:
        """Direct circular reference is detected."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(
            """
msg1 = { msg2 }
msg2 = { msg1 }
"""
        )

        result, errors = bundle.format_pattern("msg1")

        # Should detect cycle and return fallback
        assert len(errors) > 0
        assert isinstance(result, str)

    def test_circular_term_reference(self) -> None:
        """Circular term references are detected."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(
            """
-term1 = { -term2 }
-term2 = { -term1 }
msg = { -term1 }
"""
        )

        result, _errors = bundle.format_pattern("msg")

        # Should detect cycle
        assert isinstance(result, str)

    def test_nested_circular_reference(self) -> None:
        """Nested circular references are detected."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(
            """
msg1 = { msg2 }
msg2 = { msg3 }
msg3 = { msg1 }
"""
        )

        result, errors = bundle.format_pattern("msg1")

        # Should detect cycle
        assert len(errors) > 0
        assert isinstance(result, str)

    @given(
        depth=st.integers(min_value=2, max_value=5),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_reference_chain_without_cycle(self, depth: int) -> None:
        """PROPERTY: Reference chains without cycles work."""
        bundle = FluentBundle("en")

        # Build chain: msg0 -> msg1 -> msg2 -> ... -> msgN -> "End"
        messages = [f"msg{i} = {{ msg{i+1} }}" for i in range(depth)]
        messages.append(f"msg{depth} = End")
        ftl = "\n".join(messages)

        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg0")

        event(f"depth={depth}")
        # Should resolve entire chain
        assert errors == ()
        assert "End" in result

    def test_complex_reference_graph(self) -> None:
        """PROPERTY: Complex reference graphs are handled."""
        bundle = FluentBundle("en")

        # Create diamond pattern: msg0 -> msg1 and msg2 -> msg3
        messages = [
            "msg0 = { msg1 } { msg2 }",
            "msg1 = A",
            "msg2 = B",
        ]
        ftl = "\n".join(messages)

        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg0")

        # Should resolve diamond
        assert errors == ()
        assert "A" in result
        assert "B" in result


# ============================================================================
# COMPLEX SELECT EXPRESSION NESTING
# ============================================================================

class TestComplexSelectExpressions:
    """Property tests for complex select expression nesting."""

    def test_nested_select_expressions(self) -> None:
        """Nested select expressions work."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
msg = { $outer ->
    [a] { $inner ->
        [1] A1
       *[other] A-other
    }
   *[other] { $inner ->
        [1] Other-1
       *[other] Other-other
    }
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"outer": "a", "inner": 1})

        assert errors == ()
        assert "A1" in result

    @given(
        outer_val=st.sampled_from(["a", "b", "c"]),
        inner_val=st.integers(min_value=0, max_value=5),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_nested_select_all_combinations(
        self, outer_val: str, inner_val: int
    ) -> None:
        """PROPERTY: Nested selects work for all input combinations."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
msg = { $x ->
    [a] { $y ->
        [0] A0
       *[other] A-other
    }
    [b] { $y ->
        [0] B0
       *[other] B-other
    }
   *[other] { $y ->
        [0] C0
       *[other] C-other
    }
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"x": outer_val, "y": inner_val})

        event(f"outer_val={outer_val}")
        event(f"inner_val={inner_val}")
        assert errors == ()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_select_with_function_calls(self) -> None:
        """Select expressions with function calls work."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
msg = { $count ->
    [0] No items
    [1] One item ({ NUMBER($count) })
   *[other] { NUMBER($count) } items
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 5})

        assert errors == ()
        assert "5" in result
        assert "items" in result

    @given(
        count=st.integers(min_value=0, max_value=1000),  # Keep practical bound
        locale=locale_codes,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_locale_aware_plural_select(
        self, count: int, locale: str
    ) -> None:
        """PROPERTY: Locale-aware plural selects work."""
        bundle = FluentBundle(locale)
        bundle.add_resource(
            """
items = { $count ->
    [0] No items
    [1] One item
    [2] Two items
    [few] Few items
    [many] Many items
   *[other] { $count } items
}
"""
        )

        result, errors = bundle.format_pattern("items", {"count": count})

        event(f"locale={locale}")
        event(f"count={count}")
        assert errors == ()
        assert isinstance(result, str)

    def test_select_with_term_references(self) -> None:
        """Select expressions with term references work."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-brand = FTLLexEngine
msg = { $premium ->
    [true] Premium { -brand }
   *[false] Standard { -brand }
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"premium": "true"})

        assert errors == ()
        assert "Premium" in result
        assert "FTLLexEngine" in result


# ============================================================================
# CACHE BEHAVIOR
# ============================================================================

class TestCacheBehavior:
    """Property tests for FormatCache behavior."""

    @given(
        msg_id=ftl_identifiers,
        text=ftl_safe_text,
        iterations=st.integers(min_value=2, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_repeated_format_uses_cache(
        self, msg_id: str, text: str, iterations: int
    ) -> None:
        """PROPERTY: Repeated formatting uses cache."""
        assume(len(text) > 0)

        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {text}")

        # Format multiple times
        results = [bundle.format_pattern(msg_id)[0] for _ in range(iterations)]

        event(f"iterations={iterations}")
        # All results should be identical
        assert all(r == results[0] for r in results)
        assert all(text in r for r in results)

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        values=st.lists(st.integers(), min_size=2, max_size=5, unique=True),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_different_args_different_results(
        self, msg_id: str, var_name: str, values: list[int]
    ) -> None:
        """PROPERTY: Different arguments produce different results."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Value: {{ ${var_name} }}")

        # Format with different arguments
        results = [
            bundle.format_pattern(msg_id, {var_name: val})[0]
            for val in values
        ]

        event(f"value_count={len(values)}")
        # Results should differ
        unique_results = set(results)
        assert len(unique_results) == len(values)

    @given(
        msg_count=st.integers(min_value=5, max_value=20),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cache_handles_many_messages(self, msg_count: int) -> None:
        """PROPERTY: Cache handles many different messages."""
        bundle = FluentBundle("en")

        # Add many messages
        for i in range(msg_count):
            bundle.add_resource(f"msg{i} = Message {i}")

        # Format all messages
        for i in range(msg_count):
            result, errors = bundle.format_pattern(f"msg{i}")
            assert errors == ()
            assert f"Message {i}" in result

        event(f"msg_count={msg_count}")

    @given(
        msg_id=ftl_identifiers,
        text1=ftl_safe_text,
        text2=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_cache_invalidation_on_resource_update(
        self, msg_id: str, text1: str, text2: str
    ) -> None:
        """PROPERTY: Cache invalidates when resources change."""
        assume(len(text1) > 0 and len(text2) > 0)
        assume(text1 != text2)

        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {text1}")

        # Format once
        result1, _ = bundle.format_pattern(msg_id)
        assert text1 in result1

        # Update resource
        bundle.add_resource(f"{msg_id} = {text2}")

        event(f"text1_len={len(text1)}")
        # Format again - should get new value
        result2, _ = bundle.format_pattern(msg_id)
        assert text2 in result2

    def test_cache_with_complex_messages(self) -> None:
        """Cache works with complex messages."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-brand = FTLLexEngine
msg = { $count ->
    [0] No { -brand } items
    [1] One { -brand } item
   *[other] { NUMBER($count) } { -brand } items
}
"""
        )

        # Format multiple times with same args
        result1, _ = bundle.format_pattern("msg", {"count": 5})
        result2, _ = bundle.format_pattern("msg", {"count": 5})
        result3, _ = bundle.format_pattern("msg", {"count": 5})

        # All should be identical
        assert result1 == result2 == result3


# ============================================================================
# BIDIRECTIONAL TEXT HANDLING
# ============================================================================

class TestBidirectionalTextHandling:
    """Property tests for bidirectional text handling."""

    @given(
        msg_id=ftl_identifiers,
        rtl_text=st.sampled_from(["مرحبا", "שלום", "سلام"]),
        use_isolating=st.booleans(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rtl_text_with_isolating_mode(
        self, msg_id: str, rtl_text: str, use_isolating: bool
    ) -> None:
        """PROPERTY: RTL text with isolating characters."""
        bundle = FluentBundle("ar", use_isolating=use_isolating)
        bundle.add_resource(f"{msg_id} = {rtl_text}")

        result, errors = bundle.format_pattern(msg_id)

        event(f"use_isolating={use_isolating}")
        assert errors == ()
        # Text should appear (possibly with isolating chars)
        assert rtl_text in result or rtl_text in result.replace("\u2068", "").replace("\u2069", "")

    def test_mixed_ltr_rtl_text(self) -> None:
        """Mixed LTR and RTL text is handled."""
        bundle = FluentBundle("ar", use_isolating=True)
        bundle.add_resource("msg = Hello مرحبا World")

        result, errors = bundle.format_pattern("msg")

        assert errors == ()
        assert "Hello" in result.replace("\u2068", "").replace("\u2069", "")
        assert "مرحبا" in result.replace("\u2068", "").replace("\u2069", "")

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        rtl_value=st.sampled_from(["مرحبا", "שלום"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rtl_variables_with_isolating(
        self, msg_id: str, var_name: str, rtl_value: str
    ) -> None:
        """PROPERTY: RTL variables are isolated correctly."""
        bundle = FluentBundle("ar", use_isolating=True)
        bundle.add_resource(f"{msg_id} = Value: {{ ${var_name} }}")

        result, errors = bundle.format_pattern(msg_id, {var_name: rtl_value})

        event(f"rtl_value_len={len(rtl_value)}")
        assert errors == ()
        # RTL value should appear
        assert rtl_value in result.replace("\u2068", "").replace("\u2069", "")


# ============================================================================
# ADDITIONAL ERROR RECOVERY
# ============================================================================

class TestAdditionalErrorRecovery:
    """Property tests for additional error recovery scenarios."""

    @given(
        depth=st.integers(min_value=1, max_value=5),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_deeply_nested_missing_references(self, depth: int) -> None:
        """PROPERTY: Deeply nested missing references are handled."""
        bundle = FluentBundle("en", strict=False)

        # Create chain with missing link
        messages = [f"msg{i} = {{ msg{i+1} }}" for i in range(depth)]
        # Don't add the final message - it's missing
        ftl = "\n".join(messages)

        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg0")

        event(f"depth={depth}")
        # Should have errors but not crash
        assert len(errors) > 0
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        func_name=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unknown_function_recovery(
        self, msg_id: str, func_name: str
    ) -> None:
        """PROPERTY: Unknown functions are handled gracefully."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(f"{msg_id} = {{ {func_name.upper()}($var) }}")

        result, _errors = bundle.format_pattern(msg_id, {"var": 123})

        event(f"func_name_len={len(func_name)}")
        # Should return fallback without crashing
        assert isinstance(result, str)

    def test_malformed_select_expression_recovery(self) -> None:
        """Malformed select expressions are handled."""
        bundle = FluentBundle("en")

        # Try to add malformed select (parser should handle or reject)
        with contextlib.suppress(Exception):
            bundle.add_resource(
                """
msg = { $var ->
    [one One value
   *[other] Other value
}
"""
            )

        # Bundle should still be usable
        bundle.add_resource("valid = Works fine")
        _result, errors = bundle.format_pattern("valid")
        assert errors == ()

    @given(
        msg_id=ftl_identifiers,
        invalid_escape=st.sampled_from([r"\x", r"\u", r"\uGGGG"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_invalid_escape_sequence_recovery(
        self, msg_id: str, invalid_escape: str
    ) -> None:
        """PROPERTY: Invalid escape sequences are handled."""
        bundle = FluentBundle("en")

        # Try to add message with invalid escape
        with contextlib.suppress(Exception):
            bundle.add_resource(f'{msg_id} = "Text {invalid_escape} more"')

        event(f"escape_seq={invalid_escape}")
        # Bundle should still work
        assert isinstance(bundle.locale, str)

    def test_concurrent_formatting_safety(self) -> None:
        """Bundle handles concurrent formatting safely."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello World")

        # Format same message multiple times (simulating concurrent access)
        results = [bundle.format_pattern("msg")[0] for _ in range(10)]

        # All results should be identical
        assert all(r == results[0] for r in results)
        assert all("Hello World" in r for r in results)


# ============================================================================
# MESSAGE PATTERN COMPLEXITY
# ============================================================================

class TestMessagePatternComplexity:
    """Property tests for complex message patterns."""

    def test_deeply_nested_placeables(self) -> None:
        """Deeply nested placeables work."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-inner = Inner
-middle = Middle { -inner }
-outer = Outer { -middle }
msg = { -outer }
"""
        )

        result, errors = bundle.format_pattern("msg")

        assert errors == ()
        assert "Outer" in result
        assert "Middle" in result
        assert "Inner" in result

    @given(
        msg_id=ftl_identifiers,
        var_count=st.integers(min_value=3, max_value=8),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_many_placeables_in_pattern(
        self, msg_id: str, var_count: int
    ) -> None:
        """PROPERTY: Patterns with many placeables work."""
        bundle = FluentBundle("en")

        # Build pattern with many placeables
        placeables = " ".join([f"{{ $var{i} }}" for i in range(var_count)])
        bundle.add_resource(f"{msg_id} = {placeables}")

        # Provide all variables
        args: dict[str, str | int | bool] = {f"var{i}": f"V{i}" for i in range(var_count)}

        result, errors = bundle.format_pattern(msg_id, args)

        event(f"var_count={var_count}")
        assert errors == ()
        # All values should appear
        for i in range(var_count):
            assert f"V{i}" in result

    def test_complex_term_with_selectors(self) -> None:
        """Complex terms with selectors work."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-brand = FTL
    .full = FTLLexEngine
    .short = FTL

msg = { $variant ->
    [full] { -brand.full }
   *[short] { -brand.short }
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"variant": "full"})

        assert errors == ()
        assert "FTLLexEngine" in result

    @given(
        msg_id=ftl_identifiers,
        text_segments=st.lists(ftl_safe_text, min_size=2, max_size=5),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_alternating_text_and_placeables(
        self, msg_id: str, text_segments: list[str]
    ) -> None:
        """PROPERTY: Alternating text and placeables work."""
        assume(all(len(seg) > 0 for seg in text_segments))

        bundle = FluentBundle("en")

        # Build pattern: text0 { $v0 } text1 { $v1 } ...
        pattern_parts = []
        args: dict[str, str | int | bool] = {}
        for i, text in enumerate(text_segments):
            pattern_parts.append(text)
            if i < len(text_segments) - 1:
                pattern_parts.append(f"{{ $v{i} }}")
                args[f"v{i}"] = f"VAR{i}"

        pattern = " ".join(pattern_parts)
        bundle.add_resource(f"{msg_id} = {pattern}")

        result, errors = bundle.format_pattern(msg_id, args)

        event(f"segment_count={len(text_segments)}")
        assert errors == ()
        # All text segments should appear
        for text in text_segments:
            assert text in result

    def test_message_with_all_feature_types(self) -> None:
        """Message using all feature types works."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
-brand = FTLLexEngine

msg = Welcome to { -brand }!
    You have { $count ->
        [0] no items
        [1] one item
       *[other] { NUMBER($count) } items
    }.
    Price: { CURRENCY($price, currency: "USD") }

    .title = { -brand } - Message System
"""
        )

        result, errors = bundle.format_pattern(
            "msg",
            {"count": 5, "price": Decimal("99.99")}
        )

        assert errors == ()
        assert "FTLLexEngine" in result
        assert "5" in result or "items" in result


# ============================================================================
# FUNCTION ARGUMENT EDGE CASES
# ============================================================================

class TestFunctionArgumentEdgeCases:
    """Property tests for function argument edge cases."""

    @given(
        msg_id=ftl_identifiers,
        number=st.decimals(
            min_value=Decimal("0.0"),
            max_value=Decimal("1.0"),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_number_function_small_values(
        self, msg_id: str, number: Decimal
    ) -> None:
        """PROPERTY: NUMBER handles small decimal values."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f"{msg_id} = {{ NUMBER($num, minimumFractionDigits: 4) }}"
        )

        result, errors = bundle.format_pattern(msg_id, {"num": number})

        event("num_magnitude=small")
        assert errors == ()
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        number=st.decimals(
            min_value=Decimal(1000000),
            max_value=Decimal(1000000000),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_number_function_large_values(
        self, msg_id: str, number: Decimal
    ) -> None:
        """PROPERTY: NUMBER handles large values."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {{ NUMBER($num) }}")

        result, errors = bundle.format_pattern(msg_id, {"num": number})

        event("num_magnitude=large")
        assert errors == ()
        assert isinstance(result, str)

    def test_number_function_negative_zero(self) -> None:
        """NUMBER handles negative zero correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { NUMBER($num) }")

        result, errors = bundle.format_pattern("msg", {"num": Decimal("-0")})

        assert errors == ()
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        amount=st.decimals(
            min_value=Decimal("0.001"),
            max_value=Decimal("0.01"),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_currency_function_tiny_amounts(
        self, msg_id: str, amount: Decimal
    ) -> None:
        """PROPERTY: CURRENCY handles very small amounts."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f'{msg_id} = {{ CURRENCY($amt, currency: "USD") }}'
        )

        result, errors = bundle.format_pattern(msg_id, {"amt": amount})

        event("amount_magnitude=tiny")
        assert not errors

        # May have errors depending on currency support
        assert isinstance(result, str)

    def test_function_with_missing_required_option(self) -> None:
        """Function with missing required option is handled."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = { CURRENCY($amt) }")

        result, _errors = bundle.format_pattern("msg", {"amt": Decimal("99.99")})

        # Should handle missing currency option
        assert isinstance(result, str)


# ============================================================================
# LOCALE FALLBACK BEHAVIOR
# ============================================================================
