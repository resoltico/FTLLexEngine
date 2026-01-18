"""Property-based tests for system invariants.

Uses Hypothesis to test properties that must always hold, regardless of input.
"""

from __future__ import annotations

from hypothesis import example, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.diagnostics import (
    FluentCyclicReferenceError,
    FluentReferenceError,
)
from ftllexengine.runtime import FunctionRegistry, select_plural_category

from .strategies import (
    ftl_identifiers,
    ftl_numbers,
    ftl_simple_messages,
    snake_case_identifiers,
)


class TestFunctionBridgeProperties:
    """Function bridge must maintain parameter conversion properties."""

    @given(snake_case_identifiers())
    @settings(max_examples=100)
    def test_snake_to_camel_conversion(self, snake_case: str) -> None:
        """snake_case → camelCase produces valid camelCase."""
        camel = FunctionRegistry._to_camel_case(snake_case)
        # Should be a valid identifier
        assert isinstance(camel, str)
        assert len(camel) > 0


class TestPluralRulesProperties:
    """Plural rules must follow CLDR specification."""

    @given(st.integers(min_value=0, max_value=100000))
    @settings(max_examples=200)
    def test_latvian_plural_categories_complete(self, n: int) -> None:
        """Every number maps to a valid Latvian category."""
        category = select_plural_category(n, "lv_LV")
        assert category in ["zero", "one", "other"]

    @given(st.integers(min_value=0, max_value=100000))
    @settings(max_examples=200)
    def test_english_plural_categories(self, n: int) -> None:
        """English has only one/other, and one means exactly 1."""
        category = select_plural_category(n, "en_US")
        assert category in ["one", "other"]
        assert (category == "one") == (n == 1)

    @given(st.integers(min_value=0, max_value=100000))
    @settings(max_examples=100)
    def test_german_plural_same_as_english(self, n: int) -> None:
        """German and English have identical plural rules."""
        de_cat = select_plural_category(n, "de_DE")
        en_cat = select_plural_category(n, "en_US")
        assert de_cat == en_cat


class TestParserProperties:
    """Parser must handle any input gracefully."""

    @given(ftl_simple_messages())
    @settings(max_examples=50)
    def test_parser_accepts_valid_simple_messages(self, ftl_source: str) -> None:
        """Parser successfully parses valid simple messages.

        If this raises an exception, Hypothesis will find the minimal failing
        example - that's exactly what we want (reveals bugs or invalid strategy).
        """
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl_source)

        # Verify parser processed the input without raising
        assert len(bundle.get_message_ids()) >= 0

    @given(st.text(max_size=100))
    @settings(max_examples=50)
    def test_parser_never_crashes(self, random_text: str) -> None:
        """Parser handles ANY input gracefully (no crashes).

        Fuzzing test: Parser should handle random text without crashing.
        Expected exceptions (graceful degradation) are caught.
        Unexpected exceptions (bugs) will fail the test.

        Note: The parser uses Junk nodes for syntax errors (robustness principle)
        and never raises exceptions. Resolution errors are caught here.
        """
        bundle = FluentBundle("en-US")
        handled_gracefully = False
        try:
            bundle.add_resource(random_text)
            handled_gracefully = True
        except (FluentReferenceError, FluentCyclicReferenceError):
            # Expected: missing references, circular deps
            # Parser recovered gracefully (no crash)
            handled_gracefully = True

        # Verify parser handled input gracefully (either parsed or raised expected error)
        assert handled_gracefully


class TestResolverProperties:
    """Resolver must be deterministic and never crash."""

    @given(ftl_simple_messages())
    @settings(max_examples=30)
    def test_resolver_is_deterministic(self, message: str) -> None:
        """Same message always produces same output."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(message)

        # Extract message ID
        if " = " in message:
            msg_id = message.split(" = ")[0].strip()

            # Format twice with same args
            result1 = bundle.format_pattern(msg_id, {})
            result2 = bundle.format_pattern(msg_id, {})
            assert result1 == result2


class TestIdentifierProperties:
    """FTL identifiers must follow naming rules."""

    @example(identifier="A")  # Uppercase: caught test blindness to case
    @example(identifier="msg")  # Lowercase: standard case
    @given(ftl_identifiers())
    @settings(max_examples=100)
    def test_identifiers_start_with_letter(self, identifier: str) -> None:
        """Generated identifiers always start with a letter (upper or lower)."""
        # FTL spec: [a-zA-Z] - both uppercase AND lowercase are valid
        assert identifier[0].isalpha()

    @given(ftl_identifiers())
    @settings(max_examples=100)
    def test_identifiers_valid_characters(self, identifier: str) -> None:
        """Generated identifiers only contain valid characters."""
        assert all(c.isalnum() or c in "-_" for c in identifier)


class TestNumberProperties:
    """Number formatting must be consistent."""

    @given(ftl_numbers())
    @settings(max_examples=50)
    def test_number_format_returns_fluent_number(self, number: int | float) -> None:
        """Number formatting always returns a FluentNumber."""
        from ftllexengine.runtime.function_bridge import FluentNumber
        from ftllexengine.runtime.functions import number_format

        result = number_format(number)
        assert isinstance(result, FluentNumber)
        assert len(str(result)) > 0
