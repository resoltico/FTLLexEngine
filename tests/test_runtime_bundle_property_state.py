"""Hypothesis property-based tests for runtime.bundle: FluentBundle operations."""

from __future__ import annotations

import contextlib
from decimal import Decimal

from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from tests.strategies import ftl_simple_text

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


class TestLocaleFallbackBehavior:
    """Property tests for locale fallback behavior."""

    @given(
        locale=locale_codes,
        msg_id=ftl_identifiers,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_bundle_respects_locale(
        self, locale: str, msg_id: str
    ) -> None:
        """PROPERTY: Bundle respects specified locale."""
        bundle = FluentBundle(locale)
        bundle.add_resource(f"{msg_id} = Value")

        assert bundle.locale == normalize_locale(locale)

        event(f"locale={locale}")
        # After formatting, locale should remain
        bundle.format_pattern(msg_id)
        assert bundle.locale == normalize_locale(locale)

    def test_locale_specific_number_formatting(self) -> None:
        """Locale-specific number formatting works."""
        bundle_en = FluentBundle("en_US")
        bundle_de = FluentBundle("de_DE")

        ftl = "msg = { NUMBER($num) }"
        bundle_en.add_resource(ftl)
        bundle_de.add_resource(ftl)

        result_en, _ = bundle_en.format_pattern("msg", {"num": Decimal("1234.56")})
        result_de, _ = bundle_de.format_pattern("msg", {"num": Decimal("1234.56")})

        # Both should format, potentially differently
        assert isinstance(result_en, str)
        assert isinstance(result_de, str)

    @given(
        locale1=locale_codes,
        locale2=locale_codes,
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_locale_isolation_between_bundles(
        self, locale1: str, locale2: str
    ) -> None:
        """PROPERTY: Locales are isolated between bundles."""
        bundle1 = FluentBundle(locale1)
        bundle2 = FluentBundle(locale2)

        bundle1.add_resource("msg = Bundle 1")
        bundle2.add_resource("msg = Bundle 2")

        event(f"locale1={locale1}")
        event(f"locale2={locale2}")
        # Locales should remain distinct
        assert bundle1.locale == normalize_locale(locale1)
        assert bundle2.locale == normalize_locale(locale2)


# ============================================================================
# RESOURCE ORDERING
# ============================================================================

class TestResourceOrdering:
    """Property tests for resource ordering and priority."""

    @given(
        msg_id=ftl_identifiers,
        values=st.lists(ftl_safe_text, min_size=2, max_size=5, unique=True),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_last_resource_wins(
        self, msg_id: str, values: list[str]
    ) -> None:
        """PROPERTY: Last added resource wins for same message ID."""
        assume(all(len(v) > 0 for v in values))

        bundle = FluentBundle("en")

        # Add same message multiple times with different values
        for value in values:
            bundle.add_resource(f"{msg_id} = {value}")

        result, _ = bundle.format_pattern(msg_id)

        event(f"override_count={len(values)}")
        # Last value should win
        assert values[-1] in result

    @given(
        msg_count=st.integers(min_value=2, max_value=10),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_resource_accumulation_order(self, msg_count: int) -> None:
        """PROPERTY: Resources accumulate in order."""
        bundle = FluentBundle("en")

        # Add messages one by one
        for i in range(msg_count):
            bundle.add_resource(f"msg{i} = Value {i}")

        # All messages should be accessible
        for i in range(msg_count):
            result, errors = bundle.format_pattern(f"msg{i}")
            assert errors == ()
            assert f"Value {i}" in result

        event(f"msg_count={msg_count}")

    def test_partial_override_preserves_others(self) -> None:
        """Partial resource override preserves other messages."""
        bundle = FluentBundle("en")

        # Add initial messages
        bundle.add_resource(
            """
msg1 = Value 1
msg2 = Value 2
msg3 = Value 3
"""
        )

        # Override only msg2
        bundle.add_resource("msg2 = New Value 2")

        # msg1 and msg3 should be unchanged
        result1, _ = bundle.format_pattern("msg1")
        result2, _ = bundle.format_pattern("msg2")
        result3, _ = bundle.format_pattern("msg3")

        assert "Value 1" in result1
        assert "New Value 2" in result2
        assert "Value 3" in result3


# ============================================================================
# ADDITIONAL ROBUSTNESS TESTS
# ============================================================================

class TestAdditionalRobustness:
    """Additional property tests for bundle robustness."""

    @given(
        msg_id=ftl_identifiers,
        whitespace=st.sampled_from([" ", "\t", "  ", "\t\t"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_various_whitespace_types(
        self, msg_id: str, whitespace: str
    ) -> None:
        """PROPERTY: Various whitespace types are handled."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} ={whitespace}Value")

        result, errors = bundle.format_pattern(msg_id)

        event(f"whitespace_repr={whitespace!r}")
        assert errors == ()
        assert "Value" in result

    @given(
        msg_id=ftl_identifiers,
        special_char=st.sampled_from(["@", "#", "%", "&"]),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_special_characters_in_text(
        self, msg_id: str, special_char: str
    ) -> None:
        """PROPERTY: Special characters in text are preserved."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = Text {special_char} more")

        result, errors = bundle.format_pattern(msg_id)

        event(f"special_char={special_char}")
        assert errors == ()
        assert special_char in result

    def test_empty_message_value(self) -> None:
        """Empty message values are handled."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource("msg = ")

        result, _errors = bundle.format_pattern("msg")

        # Empty value should work
        assert isinstance(result, str)

    @given(
        msg_id=ftl_identifiers,
        number=st.integers(min_value=-2147483648, max_value=2147483647),
    )
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_integer_boundary_values(
        self, msg_id: str, number: int
    ) -> None:
        """PROPERTY: Integer boundary values work."""
        bundle = FluentBundle("en")
        bundle.add_resource(f"{msg_id} = {{ ${msg_id} }}")

        result, errors = bundle.format_pattern(msg_id, {msg_id: number})

        event(f"number={number}")
        assert errors == ()
        assert str(number) in result

    def test_resource_with_only_comments(self) -> None:
        """Resource with only comments is handled."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
# This is a comment
## Another comment
### More comments
"""
        )

        # Should not crash
        bundle.add_resource("msg = Works")
        _result, errors = bundle.format_pattern("msg")
        assert errors == ()


# ============================================================================
# ADVANCED BUNDLE PROPERTIES (from test_bundle_advanced_hypothesis.py)
# ============================================================================

class TestBundleMessageRegistry:
    """Properties about message registration and retrieval."""

    @given(
        locale=locale_codes,
        msg_id=ftl_identifiers,
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_registered_message_retrievable(
        self, locale: str, msg_id: str, msg_value: str
    ) -> None:
        """Property: Registered messages can be retrieved."""
        event(f"locale={locale}")
        bundle = FluentBundle(locale)

        ftl_source = f"{msg_id} = {msg_value}"
        bundle.add_resource(ftl_source)

        assert bundle.has_message(msg_id), f"Message {msg_id} not found after registration"

        result, errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "format_pattern must return string"
        assert len(result) > 0, "Formatted message should not be empty"
        assert errors == (), f"No errors expected for simple message, got {errors}"

    @given(
        msg_id=ftl_identifiers,
    )
    @settings(max_examples=300)
    def test_unregistered_message_raises_error(self, msg_id: str) -> None:
        """Property: Accessing unregistered message raises FrozenFluentError."""
        event(f"msg_id_len={len(msg_id)}")
        bundle = FluentBundle("en_US", strict=False)

        nonexistent_id = f"never_registered_{msg_id}"

        result, errors = bundle.format_pattern(nonexistent_id)
        assert len(errors) == 1, f"Expected 1 error for nonexistent message, got {len(errors)}"
        assert isinstance(errors[0], FrozenFluentError), (
            f"Expected FrozenFluentError, got {type(errors[0])}"
        )
        assert errors[0].category == ErrorCategory.REFERENCE
        assert result == f"{{{nonexistent_id}}}", f"Expected fallback, got {result}"

    @given(
        msg_id=ftl_identifiers,
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_message_override_behavior(
        self, msg_id: str, value1: str, value2: str
    ) -> None:
        """Property: Later messages override earlier ones with same ID."""
        values_equal = value1.strip() == value2.strip()
        event(f"values_equal={values_equal}")
        bundle = FluentBundle("en_US")

        bundle.add_resource(f"{msg_id} = {value1}")
        bundle.add_resource(f"{msg_id} = {value2}")

        result, errors = bundle.format_pattern(msg_id)

        assert (
            value2.strip() in result or result.strip() == value2.strip()
        ), "Later message should override earlier"
        assert errors == (), f"No errors expected for override, got {errors}"

class TestBundleVariableInterpolation:
    """Properties about variable interpolation in messages."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        var_value=st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=500)
    def test_variable_interpolation_preserves_value(
        self, msg_id: str, var_name: str, var_value: str | int | Decimal
    ) -> None:
        """Property: Variable values appear in formatted output."""
        var_type = type(var_value).__name__
        event(f"var_type={var_type}")
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"{msg_id} = Value: {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {var_name: var_value})

        assert str(var_value) in result, f"Variable value {var_value} not in result: {result}"
        assert errors == (), f"No errors expected for variable interpolation, got {errors}"

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
    )
    @settings(max_examples=300)
    def test_missing_variable_graceful_degradation(
        self, msg_id: str, var_name: str
    ) -> None:
        """Property: Missing variables cause graceful degradation, not crash."""
        event(f"var_name_len={len(var_name)}")
        bundle = FluentBundle("en_US", strict=False)

        ftl_source = f"{msg_id} = Value: {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {})

        assert isinstance(result, str), "Must return string even on error"
        error_count = len(errors)
        event(f"error_count={error_count}")
        assert error_count > 0, "Missing variable should generate error"

    @given(
        msg_id=ftl_identifiers,
        var_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_multiple_variable_interpolation(self, msg_id: str, var_count: int) -> None:
        """Property: Messages with multiple variables interpolate all."""
        bundle = FluentBundle("en_US", use_isolating=False)

        var_names = [f"var{i}" for i in range(var_count)]
        placeholders = " ".join(f"{{ ${vn} }}" for vn in var_names)
        ftl_source = f"{msg_id} = {placeholders}"
        bundle.add_resource(ftl_source)

        args = {vn: str(i) for i, vn in enumerate(var_names)}
        result, errors = bundle.format_pattern(msg_id, args)

        event(f"var_count={var_count}")
        for value in args.values():
            assert value in result, f"Variable value {value} missing from result"
        assert errors == (), f"No errors expected for multiple variables, got {errors}"

class TestBundleLocaleHandling:
    """Properties about locale-specific behavior."""

    @given(
        locale=st.sampled_from(["en_US", "lv_LV", "pl_PL", "de_DE", "fr_FR", "ru_RU"]),
        msg_id=ftl_identifiers,
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_locale_preserved_in_bundle(
        self, locale: str, msg_id: str, msg_value: str
    ) -> None:
        """Property: Bundle canonicalizes and preserves locale configuration."""
        bundle = FluentBundle(locale)

        assert bundle.locale == normalize_locale(locale), "Bundle locale mismatch"

        ftl_source = f"{msg_id} = {msg_value}"
        bundle.add_resource(ftl_source)

        event(f"locale={locale}")
        result, errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "Locale should not affect basic formatting"
        assert errors == (), f"No errors expected for simple message, got {errors}"

class TestBundleIsolatingMarks:
    """Properties about Unicode bidi isolation marks."""

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_isolating_marks_with_use_isolating_true(
        self, msg_id: str, var_name: str, var_value: str
    ) -> None:
        """Property: use_isolating=True adds FSI/PDI marks around interpolated values."""
        bundle = FluentBundle("en_US", use_isolating=True)

        ftl_source = f"{msg_id} = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {var_name: var_value})

        event("use_isolating=True")
        assert "\u2068" in result, "FSI mark missing with use_isolating=True"
        assert "\u2069" in result, "PDI mark missing with use_isolating=True"
        assert errors == (), f"No errors expected for isolating marks, got {errors}"

    @given(
        msg_id=ftl_identifiers,
        var_name=ftl_identifiers,
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_no_isolating_marks_with_use_isolating_false(
        self, msg_id: str, var_name: str, var_value: str
    ) -> None:
        """Property: use_isolating=False omits FSI/PDI marks."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"{msg_id} = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {var_name: var_value})

        event("use_isolating=False")
        assert "\u2068" not in result, "FSI mark present with use_isolating=False"
        assert "\u2069" not in result, "PDI mark present with use_isolating=False"
        assert errors == (), f"No errors expected without isolating marks, got {errors}"

class TestBundleValidation:
    """Properties about resource validation."""

    @given(
        msg_id=ftl_identifiers,
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_valid_resource_validation(self, msg_id: str, msg_value: str) -> None:
        """Property: Valid FTL passes validation."""
        bundle = FluentBundle("en_US")

        ftl_source = f"{msg_id} = {msg_value}"
        result = bundle.validate_resource(ftl_source)

        event(f"id_len={len(msg_id)}")
        assert result.is_valid, f"Valid FTL failed validation: {ftl_source}"
        assert result.error_count == 0, "Valid FTL should have no errors"

    @given(
        invalid_syntax=st.text(
            alphabet=st.characters(whitelist_categories=["Cc"]), min_size=1, max_size=50
        ),
    )
    @settings(max_examples=200)
    def test_invalid_resource_validation(self, invalid_syntax: str) -> None:
        """Property: Invalid FTL is detected by validation."""
        bundle = FluentBundle("en_US")

        result = bundle.validate_resource(invalid_syntax)

        event(f"syntax_len={len(invalid_syntax)}")
        assert isinstance(result.error_count, int), "error_count must be integer"

class TestBundleStateConsistency:
    """Properties about bundle internal state consistency."""

    @given(
        msg_count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=200)
    def test_message_count_consistency(self, msg_count: int) -> None:
        """Property: get_message_ids returns all registered messages."""
        bundle = FluentBundle("en_US")

        msg_ids = [f"msg{i}" for i in range(msg_count)]
        for msg_id in msg_ids:
            bundle.add_resource(f"{msg_id} = value")

        retrieved_ids = bundle.get_message_ids()

        event(f"msg_count={msg_count}")
        assert len(retrieved_ids) == msg_count, "Message count mismatch"
        for msg_id in msg_ids:
            assert msg_id in retrieved_ids, f"Message {msg_id} missing from get_message_ids()"

    @given(
        msg_id=ftl_identifiers,
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_has_message_consistency_with_format(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Property: has_message returns True iff format_pattern succeeds."""
        bundle = FluentBundle("en_US")

        bundle.add_resource(f"{msg_id} = {msg_value}")

        has_msg = bundle.has_message(msg_id)
        assert has_msg, f"has_message returned False for registered message {msg_id}"

        event(f"id_len={len(msg_id)}")
        result, errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "format_pattern should succeed when has_message=True"
        assert errors == (), f"No errors expected when has_message=True, got {errors}"

class TestBundleErrorHandling:
    """Properties about error handling and recovery."""

    @given(
        invalid_ftl=st.text(min_size=0, max_size=100),
        valid_msg=ftl_identifiers.flatmap(
            lambda mid: ftl_simple_text().map(lambda val: f"{mid} = {val}")
        ),
    )
    @settings(max_examples=200)
    def test_bundle_continues_after_parse_errors(
        self, invalid_ftl: str, valid_msg: str
    ) -> None:
        """Property: Bundle continues accepting resources after parse errors."""
        bundle = FluentBundle("en_US")

        with contextlib.suppress(Exception):
            bundle.add_resource(invalid_ftl)

        bundle.add_resource(valid_msg)

        msg_ids = bundle.get_message_ids()
        event(f"msg_count_after_error={len(msg_ids)}")
        assert len(msg_ids) > 0, "Bundle should accept valid resources after errors"

    @given(
        msg_id=ftl_identifiers,
        exception_message=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_format_pattern_never_crashes_application(
        self, msg_id: str, exception_message: str
    ) -> None:
        """Property: format_pattern never raises unexpected exceptions."""
        bundle = FluentBundle("en_US", strict=False)

        def failing_function() -> str:
            raise ValueError(exception_message)

        bundle.add_function("FAIL", failing_function)
        bundle.add_resource(f"{msg_id} = {{ FAIL() }}")

        result, errors = bundle.format_pattern(msg_id)

        event(f"error_count={len(errors)}")
        assert isinstance(
            result, str
        ), "format_pattern must return string even when function raises"
        assert len(errors) > 0, "Function exception should generate error"

class TestBundleMetamorphicProperties:
    """Metamorphic properties: relations between different operations."""

    @given(
        resource_order=st.permutations(list(range(3))),
    )
    @settings(max_examples=200)
    def test_addition_order_independence_without_conflicts(
        self, resource_order: list[int]
    ) -> None:
        """Property: Adding non-conflicting resources in different orders gives same result."""
        bundle1 = FluentBundle("en_US")
        bundle2 = FluentBundle("en_US")

        resources = [f"m{i} = value{i}" for i in range(3)]

        for i in range(3):
            bundle1.add_resource(resources[i])

        for idx in resource_order:
            bundle2.add_resource(resources[idx])

        ids1 = sorted(bundle1.get_message_ids())
        ids2 = sorted(bundle2.get_message_ids())

        event(f"resource_order={resource_order}")
        assert ids1 == ids2, "Resource addition order should not affect final state"
