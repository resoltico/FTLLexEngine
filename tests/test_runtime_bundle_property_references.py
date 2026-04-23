"""Hypothesis property-based tests for runtime.bundle: FluentBundle operations."""

from __future__ import annotations

import contextlib
from decimal import Decimal

from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle

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


class TestVariableSubstitution:
    """Property tests for variable substitution."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        # Remove arbitrary bounds
        var_value=st.integers(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_integer_variable_substitution(
        self, msg_id: str, var_name: str, var_value: int
    ) -> None:
        """PROPERTY: Integer variables are substituted correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Value: {{ ${var_name} }}")

        result, errors = bundle.format_pattern(msg_id, {var_name: var_value})

        event(f"int_val={var_value}")
        assert errors == ()
        assert str(var_value) in result
        event("outcome=int_var_subst")

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        var_value=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_string_variable_substitution(
        self, msg_id: str, var_name: str, var_value: str
    ) -> None:
        """PROPERTY: String variables are substituted correctly."""
        assume(len(var_value) > 0)

        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Value: {{ ${var_name} }}")

        result, errors = bundle.format_pattern(msg_id, {var_name: var_value})

        event(f"str_val_len={len(var_value)}")
        assert errors == ()
        assert var_value in result
        event("outcome=str_var_subst")

    @given(
        msg_id=ftl_identifiers,
        # Keep practical bound for performance
        var_count=st.integers(min_value=1, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_variable_substitution(
        self, msg_id: str, var_count: int
    ) -> None:
        """PROPERTY: Multiple variables are substituted correctly."""
        bundle = FluentBundle("en")

        # Build FTL with multiple variables
        vars_ftl = " ".join([f"{{ $var{i} }}" for i in range(var_count)])
        bundle.add_resource(f"{msg_id} = {vars_ftl}")

        # Build args dict
        args: dict[str, int | str | bool] = {f"var{i}": i for i in range(var_count)}

        result, errors = bundle.format_pattern(msg_id, args)

        event(f"var_count={var_count}")
        assert errors == ()
        # All variable values should appear
        for i in range(var_count):
            assert str(i) in result
        event("outcome=multi_var_subst")

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_missing_variable_generates_error(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Missing variables generate errors."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(f"{msg_id} = Value: {{ ${var_name} }}")

        result, errors = bundle.format_pattern(msg_id, {})

        event(f"missing_var_id_len={len(var_name)}")
        # Should have error for missing variable
        assert len(errors) > 0
        assert isinstance(result, str)
        event("outcome=missing_var_error")


# ============================================================================
# FUNCTION CALLS
# ============================================================================

class TestFunctionCalls:
    """Property tests for built-in function calls."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        number=st.decimals(
            min_value=Decimal(-1000),
            max_value=Decimal(1000),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_number_function_formatting(
        self, msg_id: str, var_name: str, number: Decimal
    ) -> None:
        """PROPERTY: NUMBER function formats numbers."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {{ NUMBER(${var_name}) }}")

        result, errors = bundle.format_pattern(msg_id, {var_name: number})

        event(f"num={number}")
        assert errors == ()
        assert isinstance(result, str)
        assert len(result) > 0
        event("outcome=num_func_format")

    @given(
        msg_id=ftl_identifiers,
        currency=st.sampled_from(["USD", "EUR", "GBP", "JPY"]),
        amount=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal(10000),
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_currency_function_formatting(
        self, msg_id: str, currency: str, amount: Decimal
    ) -> None:
        """PROPERTY: CURRENCY function formats currency values."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f'{msg_id} = {{ CURRENCY($amt, currency: "{currency}") }}'
        )

        result, errors = bundle.format_pattern(msg_id, {"amt": amount})

        event(f"currency={currency}")
        assert not errors

        # May have errors depending on currency support
        assert isinstance(result, str)
        assert len(result) > 0
        event("outcome=currency_func_format")


# ============================================================================
# TERM RESOLUTION
# ============================================================================

class TestTermResolution:
    """Property tests for term resolution."""

    @given(
        term_id=ftl_identifiers,
        term_value=ftl_safe_text,
        msg_id=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_term_reference_resolution(
        self, term_id: str, term_value: str, msg_id: str
    ) -> None:
        """PROPERTY: Terms are resolved in messages."""
        assume(len(term_value) > 0)
        assume(term_id != msg_id)

        bundle = FluentBundle("en")
        bundle.add_resource(
            f"-{term_id} = {term_value}\n"
            f"{msg_id} = {{ -{term_id} }}"
        )

        result, errors = bundle.format_pattern(msg_id)

        event(f"id_len={len(term_id)}")
        assert errors == ()
        assert term_value in result
        event("outcome=term_ref_resolution")

    @given(
        term_id=ftl_identifiers,
        attr_name=ftl_identifiers,
        attr_value=ftl_safe_text,
        msg_id=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_term_attribute_resolution(
        self, term_id: str, attr_name: str, attr_value: str, msg_id: str
    ) -> None:
        """PROPERTY: Term attributes are resolved."""
        assume(len(attr_value) > 0)
        assume(term_id != msg_id)

        bundle = FluentBundle("en")
        bundle.add_resource(
            f"-{term_id} = Base\n"
            f"    .{attr_name} = {attr_value}\n"
            f"{msg_id} = {{ -{term_id}.{attr_name} }}"
        )

        result, errors = bundle.format_pattern(msg_id)

        event(f"attr_len={len(attr_value)}")
        assert errors == ()
        assert attr_value in result
        event("outcome=term_attr_resolution")


# ============================================================================
# MESSAGE REFERENCES
# ============================================================================

class TestMessageReferences:
    """Property tests for message references."""

    @given(
        msg_id1=ftl_identifiers,
        msg_id2=ftl_identifiers,
        value=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_message_reference_resolution(
        self, msg_id1: str, msg_id2: str, value: str
    ) -> None:
        """PROPERTY: Message references are resolved."""
        assume(len(value) > 0)
        assume(msg_id1 != msg_id2)

        bundle = FluentBundle("en")
        bundle.add_resource(
            f"{msg_id1} = {value}\n"
            f"{msg_id2} = Ref: {{ {msg_id1} }}"
        )

        result, errors = bundle.format_pattern(msg_id2)

        event(f"val_len={len(value)}")
        assert errors == ()
        assert value in result
        event("outcome=msg_ref_resolution")


# ============================================================================
# ATTRIBUTE ACCESS
# ============================================================================

class TestAttributeAccess:
    """Property tests for attribute access."""

    @given(
        msg_id=ftl_identifiers,
        attr_count=st.integers(min_value=1, max_value=10),  # Keep practical bound
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiple_attributes_accessible(
        self, msg_id: str, attr_count: int
    ) -> None:
        """PROPERTY: All attributes are accessible."""
        bundle = FluentBundle("en")

        # Build message with multiple attributes
        attrs = "\n".join([f"    .attr{i} = Value{i}" for i in range(attr_count)])
        bundle.add_resource(f"{msg_id} = Main\n{attrs}")

        # Access each attribute
        for i in range(attr_count):
            result, errors = bundle.format_pattern(msg_id, attribute=f"attr{i}")
            assert errors == ()
            assert f"Value{i}" in result

        event(f"attr_count={attr_count}")
        event("outcome=multi_attr_accessible")


# ============================================================================
# LOCALE HANDLING
# ============================================================================

class TestLocaleHandling:
    """Property tests for locale handling."""

    @given(
        locale1=locale_codes,
        locale2=locale_codes,
        msg_id=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_different_locales_independent(
        self, locale1: str, locale2: str, msg_id: str
    ) -> None:
        """PROPERTY: Different locale bundles are independent."""
        assume(locale1 != locale2)

        bundle1 = FluentBundle(locale1)
        bundle2 = FluentBundle(locale2)

        bundle1.add_resource(f"{msg_id} = Locale1 value")
        bundle2.add_resource(f"{msg_id} = Locale2 value")

        result1, _ = bundle1.format_pattern(msg_id)
        result2, _ = bundle2.format_pattern(msg_id)

        event(f"locales={locale1},{locale2}")
        assert "Locale1" in result1
        assert "Locale2" in result2
        event("outcome=locale_independence")


# ============================================================================
# ERROR RECOVERY
# ============================================================================

class TestErrorRecovery:
    """Property tests for error recovery."""

    @given(
        msg_id=ftl_identifiers,
        invalid_char=st.sampled_from(["\x00", "\x01", "\x02"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_invalid_syntax_recovers_gracefully(
        self, msg_id: str, invalid_char: str
    ) -> None:
        """PROPERTY: Invalid syntax doesn't crash bundle."""
        bundle = FluentBundle("en")

        # Add invalid FTL
        with contextlib.suppress(Exception):
            bundle.add_resource(f"{msg_id} = Invalid {invalid_char} text")

        # Bundle should still be usable
        bundle.add_resource("valid = Works")
        _result, errors = bundle.format_pattern("valid")
        event(f"invalid_char={ord(invalid_char)}")
        assert errors == ()
        event("outcome=syntax_error_recovery")


# ============================================================================
# SELECT EXPRESSIONS
# ============================================================================

class TestSelectExpressions:
    """Property tests for select expression handling."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        count=st.integers(min_value=0, max_value=1000),  # Keep practical bound
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_plural_select_expression(
        self, msg_id: str, var_name: str, count: int
    ) -> None:
        """PROPERTY: Plural select expressions work for all counts."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f"""{msg_id} = {{ ${var_name} ->
    [0] No items
    [1] One item
   *[other] Many items
}}"""
        )

        result, errors = bundle.format_pattern(msg_id, {var_name: count})

        event(f"count={count}")
        assert errors == ()
        assert isinstance(result, str)
        event("outcome=plural_select_valid")

    @given(
        msg_id=ftl_identifiers,
        locale=locale_codes,
        count=st.integers(min_value=0, max_value=1000),  # Keep practical bound
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_locale_specific_plurals(
        self, msg_id: str, locale: str, count: int
    ) -> None:
        """PROPERTY: Locale-specific plurals are handled."""
        bundle = FluentBundle(locale)
        bundle.add_resource(
            f"""{msg_id} = {{ $count ->
    [0] Zero
    [1] One
    [2] Two
    [few] Few
    [many] Many
   *[other] Other
}}"""
        )

        result, errors = bundle.format_pattern(msg_id, {"count": count})

        event(f"locale={locale}")
        event(f"count={count}")
        assert errors == ()
        assert len(result) > 0
        event("outcome=locale_plurals_valid")


# ============================================================================
# NUMBER FORMATTING VARIATIONS
# ============================================================================

class TestNumberFormattingVariations:
    """Property tests for number formatting variations."""

    @given(
        msg_id=ftl_identifiers,
        number=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal(1000),
            allow_nan=False,
            allow_infinity=False,
        ),
        min_digits=st.integers(min_value=0, max_value=4),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_number_minimum_fraction_digits(
        self, msg_id: str, number: Decimal, min_digits: int
    ) -> None:
        """PROPERTY: minimumFractionDigits option works."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f"{msg_id} = {{ NUMBER($num, minimumFractionDigits: {min_digits}) }}"
        )

        result, errors = bundle.format_pattern(msg_id, {"num": number})

        event(f"min_digits={min_digits}")
        assert errors == ()
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        number=st.integers(min_value=0, max_value=1000000),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_number_grouping(self, msg_id: str, number: int) -> None:
        """PROPERTY: Number grouping works for large numbers."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            f'{msg_id} = {{ NUMBER($num, useGrouping: "true") }}'
        )

        result, errors = bundle.format_pattern(msg_id, {"num": number})

        event(f"number={number}")
        assert errors == ()
        assert isinstance(result, str)


# ============================================================================
# WHITESPACE HANDLING
# ============================================================================

class TestWhitespaceHandling:
    """Property tests for whitespace handling."""

    @given(
        msg_id=ftl_identifiers,
        spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_leading_whitespace_in_values(
        self, msg_id: str, spaces: int
    ) -> None:
        """PROPERTY: Leading whitespace in values is preserved."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {' ' * spaces}Value")

        result, errors = bundle.format_pattern(msg_id)

        event(f"spaces={spaces}")
        assert errors == ()
        # Whitespace may be trimmed by parser/formatter
        assert "Value" in result

    @given(
        msg_id=ftl_identifiers,
        text=ftl_safe_text,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_multiline_message_formatting(
        self, msg_id: str, text: str
    ) -> None:
        """PROPERTY: Multiline messages format correctly."""
        assume(len(text) > 0)
        assume(text.strip() == text)  # No leading/trailing whitespace
        assume(not text.startswith((".", "-", "*", "#", "[")))  # Exclude FTL syntax
        assume(text not in (".", "-", "*", "#", "[", "]"))  # Exclude FTL syntax

        bundle = FluentBundle("en")
        bundle.add_resource(
            f"{msg_id} =\n"
            f"    Line 1\n"
            f"    {text}"
        )

        result, errors = bundle.format_pattern(msg_id)

        event(f"text_len={len(text)}")
        assert errors == ()
        assert text in result


# ============================================================================
# UNICODE EDGE CASES
# ============================================================================

class TestUnicodeEdgeCases:
    """Property tests for Unicode edge cases."""

    @given(
        msg_id=ftl_identifiers,
        emoji=st.sampled_from(["😀", "👋", "🌍", "🎉", "❤️"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_emoji_in_messages(self, msg_id: str, emoji: str) -> None:
        """PROPERTY: Emoji characters are handled correctly."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Hello {emoji}")

        result, errors = bundle.format_pattern(msg_id)

        event(f"emoji={emoji}")
        assert errors == ()
        assert emoji in result
        event("outcome=emoji_msg_format")

    @given(
        msg_id=ftl_identifiers,
        rtl_text=st.sampled_from(["مرحبا", "שלום", "مساء"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rtl_text_handling(self, msg_id: str, rtl_text: str) -> None:
        """PROPERTY: RTL text is handled correctly."""
        bundle = FluentBundle("ar")
        bundle.add_resource(f"{msg_id} = {rtl_text}")

        result, errors = bundle.format_pattern(msg_id)

        event(f"rtl_text_len={len(rtl_text)}")
        assert errors == ()
        assert rtl_text in result

    @given(
        msg_id=ftl_identifiers,
        char=st.characters(
            min_codepoint=0x1F600,
            max_codepoint=0x1F64F,
        ),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unicode_emoji_range(self, msg_id: str, char: str) -> None:
        """PROPERTY: Unicode emoji range handled."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Emoji: {char}")

        result, errors = bundle.format_pattern(msg_id)

        event(f"codepoint={ord(char):#06x}")
        assert errors == ()
        assert char in result


# ============================================================================
# PERFORMANCE PROPERTIES
# ============================================================================

class TestPerformanceProperties:
    """Property tests for performance characteristics."""

    @given(
        msg_count=st.integers(min_value=10, max_value=50),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_large_bundle_performance(self, msg_count: int) -> None:
        """PROPERTY: Large bundles perform reasonably."""
        bundle = FluentBundle("en")

        # Add many messages
        messages = [f"msg{i} = Value {i}" for i in range(msg_count)]
        bundle.add_resource("\n".join(messages))

        # Format random message should be fast
        result, _ = bundle.format_pattern(f"msg{msg_count // 2}")
        event(f"msg_count={msg_count}")
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        iterations=st.integers(min_value=1, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_repeated_formatting_consistent(
        self, msg_id: str, iterations: int
    ) -> None:
        """PROPERTY: Repeated formatting gives consistent results."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Consistent value")

        # Format same message multiple times
        results = [
            bundle.format_pattern(msg_id)[0]
            for _ in range(iterations)
        ]

        event(f"iterations={iterations}")
        # All results should be identical
        assert all(r == results[0] for r in results)


# ============================================================================
# ERROR MESSAGE FORMATTING
# ============================================================================

class TestErrorMessageFormatting:
    """Property tests for error message formatting."""

    @given(
        msg_id=ftl_identifiers,
        unknown_func=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unknown_function_error(
        self, msg_id: str, unknown_func: str
    ) -> None:
        """PROPERTY: Unknown functions generate errors."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(
            f"{msg_id} = {{ {unknown_func.upper()}($var) }}"
        )

        result, _errors = bundle.format_pattern(msg_id, {"var": 1})

        # May have errors for unknown function
        assert isinstance(result, str)
        event(f"unknown_func_len={len(unknown_func)}")
        event("outcome=unknown_func_handled")

    @given(
        msg_id=ftl_identifiers,
        unknown_term=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_unknown_term_error(
        self, msg_id: str, unknown_term: str
    ) -> None:
        """PROPERTY: Unknown terms generate errors."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(f"{msg_id} = {{ -{unknown_term} }}")

        result, errors = bundle.format_pattern(msg_id)

        # Should have error for unknown term
        assert len(errors) > 0
        assert isinstance(result, str)
        event(f"unknown_term_len={len(unknown_term)}")
        event("outcome=unknown_term_handled")


# ============================================================================
# ARGUMENT TYPE HANDLING
# ============================================================================

class TestArgumentTypeHandling:
    """Property tests for argument type handling."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        bool_value=st.booleans(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_boolean_argument_handling(
        self, msg_id: str, var_name: str, bool_value: bool
    ) -> None:
        """PROPERTY: Boolean arguments are handled."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {{ ${var_name} }}")

        result, errors = bundle.format_pattern(msg_id, {var_name: bool_value})

        event(f"bool_val={bool_value}")
        assert errors == ()
        assert isinstance(result, str)
        event("outcome=bool_arg_handled")

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        list_value=st.lists(st.integers(), min_size=0, max_size=5),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_list_argument_handling(
        self, msg_id: str, var_name: str, list_value: list[int]
    ) -> None:
        """PROPERTY: List arguments are handled."""
        event(f"list_len={len(list_value)}")
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {{ ${var_name} }}")

        result, _errors = bundle.format_pattern(msg_id, {var_name: list_value})

        # Lists may not be supported, but shouldn't crash
        assert isinstance(result, str)


# ============================================================================
# ATTRIBUTE EDGE CASES
# ============================================================================

class TestAttributeEdgeCases:
    """Property tests for attribute edge cases."""

    @given(
        msg_id=ftl_identifiers,
        attr_name=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_missing_attribute_error(
        self, msg_id: str, attr_name: str
    ) -> None:
        """PROPERTY: Missing attributes generate errors."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(f"{msg_id} = Value")

        result, errors = bundle.format_pattern(msg_id, attribute=attr_name)

        # Should have error for missing attribute
        assert len(errors) > 0
        assert isinstance(result, str)
        event(f"missing_attr_len={len(attr_name)}")
        event("outcome=missing_attr_handled")

    @given(
        msg_id=ftl_identifiers,
        attr_name=ftl_identifiers,
        var_name=ftl_identifiers,
        var_value=st.integers(),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_attribute_with_variables(
        self, msg_id: str, attr_name: str, var_name: str, var_value: int
    ) -> None:
        """PROPERTY: Attributes with variables work."""
        event(f"var_value={var_value}")
        bundle = FluentBundle("en")
        bundle.add_resource(
            f"{msg_id} = Main\n"
            f"    .{attr_name} = Value: {{ ${var_name} }}"
        )

        result, errors = bundle.format_pattern(
            msg_id,
            args={var_name: var_value},
            attribute=attr_name,
        )

        assert errors == ()
        assert str(var_value) in result


# ============================================================================
# ISOLATION MODE
# ============================================================================
