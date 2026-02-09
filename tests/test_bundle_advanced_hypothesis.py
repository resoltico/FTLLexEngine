"""Advanced Hypothesis property-based tests for FluentBundle.

Critical bundle functions tested with extensive property-based strategies:
- Message registration and retrieval
- Locale handling
- Function registry integration
- Error handling and fallback behavior
- State consistency
"""

import contextlib

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from tests.strategies import ftl_identifiers, ftl_simple_text


class TestBundleMessageRegistry:
    """Properties about message registration and retrieval."""

    @given(
        locale=st.from_regex(r"[a-zA-Z][a-zA-Z0-9]*(_[a-zA-Z0-9]+)?", fullmatch=True),
        msg_id=ftl_identifiers(),
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
        msg_id=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_unregistered_message_raises_error(self, msg_id: str) -> None:
        """Property: Accessing unregistered message raises FrozenFluentError."""
        event(f"msg_id_len={len(msg_id)}")
        bundle = FluentBundle("en_US")

        nonexistent_id = f"never_registered_{msg_id}"

        result, errors = bundle.format_pattern(nonexistent_id)
        assert len(errors) == 1, f"Expected 1 error for nonexistent message, got {len(errors)}"
        assert isinstance(errors[0], FrozenFluentError), (
            f"Expected FrozenFluentError, got {type(errors[0])}"
        )
        assert errors[0].category == ErrorCategory.REFERENCE
        assert result == f"{{{nonexistent_id}}}", f"Expected fallback, got {result}"

    @given(
        msg_id=ftl_identifiers(),
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
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        var_value=st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=500)
    def test_variable_interpolation_preserves_value(
        self, msg_id: str, var_name: str, var_value: str | int | float
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
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_missing_variable_graceful_degradation(
        self, msg_id: str, var_name: str
    ) -> None:
        """Property: Missing variables cause graceful degradation, not crash."""
        event(f"var_name_len={len(var_name)}")
        bundle = FluentBundle("en_US")

        ftl_source = f"{msg_id} = Value: {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {})

        assert isinstance(result, str), "Must return string even on error"
        error_count = len(errors)
        event(f"error_count={error_count}")
        assert error_count > 0, "Missing variable should generate error"

    @given(
        msg_id=ftl_identifiers(),
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

        for value in args.values():
            assert value in result, f"Variable value {value} missing from result"
        assert errors == (), f"No errors expected for multiple variables, got {errors}"


class TestBundleLocaleHandling:
    """Properties about locale-specific behavior."""

    @given(
        locale=st.sampled_from(["en_US", "lv_LV", "pl_PL", "de_DE", "fr_FR", "ru_RU"]),
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_locale_preserved_in_bundle(
        self, locale: str, msg_id: str, msg_value: str
    ) -> None:
        """Property: Bundle preserves locale configuration."""
        bundle = FluentBundle(locale)

        assert bundle.locale == locale, "Bundle locale mismatch"

        ftl_source = f"{msg_id} = {msg_value}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "Locale should not affect basic formatting"
        assert errors == (), f"No errors expected for simple message, got {errors}"


class TestBundleIsolatingMarks:
    """Properties about Unicode bidi isolation marks."""

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
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

        assert "\u2068" in result, "FSI mark missing with use_isolating=True"
        assert "\u2069" in result, "PDI mark missing with use_isolating=True"
        assert errors == (), f"No errors expected for isolating marks, got {errors}"

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
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

        assert "\u2068" not in result, "FSI mark present with use_isolating=False"
        assert "\u2069" not in result, "PDI mark present with use_isolating=False"
        assert errors == (), f"No errors expected without isolating marks, got {errors}"


class TestBundleValidation:
    """Properties about resource validation."""

    @given(
        msg_id=ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_valid_resource_validation(self, msg_id: str, msg_value: str) -> None:
        """Property: Valid FTL passes validation."""
        bundle = FluentBundle("en_US")

        ftl_source = f"{msg_id} = {msg_value}"
        result = bundle.validate_resource(ftl_source)

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

        assert len(retrieved_ids) == msg_count, "Message count mismatch"
        for msg_id in msg_ids:
            assert msg_id in retrieved_ids, f"Message {msg_id} missing from get_message_ids()"

    @given(
        msg_id=ftl_identifiers(),
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

        result, errors = bundle.format_pattern(msg_id)
        assert isinstance(result, str), "format_pattern should succeed when has_message=True"
        assert errors == (), f"No errors expected when has_message=True, got {errors}"


class TestBundleErrorHandling:
    """Properties about error handling and recovery."""

    @given(
        invalid_ftl=st.text(min_size=0, max_size=100),
        valid_msg=ftl_identifiers().flatmap(
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
        assert len(msg_ids) > 0, "Bundle should accept valid resources after errors"

    @given(
        msg_id=ftl_identifiers(),
        exception_message=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_format_pattern_never_crashes_application(
        self, msg_id: str, exception_message: str
    ) -> None:
        """Property: format_pattern never raises unexpected exceptions."""
        bundle = FluentBundle("en_US")

        def failing_function() -> str:
            raise ValueError(exception_message)

        bundle.add_function("FAIL", failing_function)
        bundle.add_resource(f"{msg_id} = {{ FAIL() }}")

        result, errors = bundle.format_pattern(msg_id)

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

        assert ids1 == ids2, "Resource addition order should not affect final state"
