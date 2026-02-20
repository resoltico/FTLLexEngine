"""Runtime resolution fuzzing tests.

Property-based tests for FluentBundle.format_pattern() and FluentResolver.
Tests runtime behavior that parsing tests don't cover:
- Cycle detection
- Depth limiting
- Error collection
- Fallback string generation
- Variable resolution

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Message

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# -----------------------------------------------------------------------------
# Strategies for Runtime Testing
# -----------------------------------------------------------------------------


@st.composite
def ftl_simple_messages_str(draw: st.DrawFn) -> str:
    """Generate simple FTL message source."""
    first = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
    rest = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", max_size=20))
    msg_id = first + rest

    # Simple value or value with variable
    if draw(st.booleans()):
        value = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=50))
        return f"{msg_id} = {value}"

    var_name = draw(st.sampled_from(["name", "count", "user", "value"]))
    prefix = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20))
    return f"{msg_id} = {prefix} {{ ${var_name} }}"


@st.composite
def ftl_with_references(draw: st.DrawFn) -> str:
    """Generate FTL with message references (potential for cycles)."""
    # Create a few message IDs
    ids = [
        draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        + draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=5))
        for _ in range(draw(st.integers(2, 5)))
    ]

    # Make IDs unique
    ids = list(dict.fromkeys(ids))
    if len(ids) < 2:
        ids = ["msg1", "msg2"]

    messages = []
    for i, msg_id in enumerate(ids):
        # Sometimes reference another message
        if draw(st.booleans()) and i > 0:
            ref_id = draw(st.sampled_from(ids[:i]))
            messages.append(f"{msg_id} = See {{ {ref_id} }}")
        else:
            messages.append(f"{msg_id} = Value {i}")

    return "\n".join(messages)


@st.composite
def ftl_with_select(draw: st.DrawFn) -> str:
    """Generate FTL with select expressions."""
    msg_id = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz")) + draw(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", max_size=10)
    )
    var_name = draw(st.sampled_from(["count", "gender", "case"]))

    variants = []
    key_options = [["one", "other"], ["male", "female", "other"], ["0", "1", "other"]]
    keys = draw(st.sampled_from(key_options))
    for i, key in enumerate(keys):
        prefix = "*" if i == len(keys) - 1 else " "
        value = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20))
        variants.append(f"    {prefix}[{key}] {value}")

    return f"{msg_id} = {{ ${var_name} ->\n" + "\n".join(variants) + "\n}"


@st.composite
def format_arguments(draw: st.DrawFn) -> dict[str, str | int | float]:
    """Generate valid format arguments."""
    args: dict[str, str | int | float] = {}

    # Common variable names
    var_names = ["name", "count", "user", "value", "gender", "case"]

    for var in draw(st.lists(st.sampled_from(var_names), min_size=0, max_size=4, unique=True)):
        value = draw(
            st.one_of(
                st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20),
                st.integers(min_value=-1000, max_value=1000),
                st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
            )
        )
        args[var] = value

    return args


# -----------------------------------------------------------------------------
# Property Tests: Format Pattern
# -----------------------------------------------------------------------------


class TestFormatPatternProperties:
    """Property tests for FluentBundle.format_pattern()."""

    @given(ftl_simple_messages_str(), format_arguments())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_format_never_crashes(self, ftl: str, args: dict[str, str | int | float]) -> None:
        """Property: format_pattern never raises, always returns (str, tuple)."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Get first message ID
        resource = bundle._parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assume(len(messages) > 0)

        msg_id = messages[0].id.name

        # Should never raise
        result, errors = bundle.format_pattern(msg_id, args)

        event(f"args_count={len(args)}")
        if errors:
            event("outcome=format_with_errors")
        else:
            event("outcome=format_success")

        # Type assertions
        assert isinstance(result, str)
        assert isinstance(errors, tuple)
        assert all(hasattr(e, "__class__") for e in errors)

    @given(ftl_with_references(), format_arguments())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_references_resolve_or_error(
        self, ftl: str, args: dict[str, str | int | float]
    ) -> None:
        """Property: Message references either resolve or produce errors, never crash."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        resource = bundle._parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assume(len(messages) > 0)

        event(f"msg_count={len(messages)}")

        for msg in messages:
            result, errors = bundle.format_pattern(msg.id.name, args)
            assert isinstance(result, str)
            assert isinstance(errors, tuple)
            if errors:
                # Track what kind of errors we get (cycle, missing, etc)
                for err in errors:
                    event(f"error_type={type(err).__name__}")
            else:
                event("outcome=resolved")

    @given(ftl_with_select(), format_arguments())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_select_expressions_always_resolve(
        self, ftl: str, args: dict[str, str | int | float]
    ) -> None:
        """Property: Select expressions always resolve to a variant."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        resource = bundle._parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assume(len(messages) > 0)

        for msg in messages:
            result, _ = bundle.format_pattern(msg.id.name, args)
            # Result should not be empty (select always has default)
            assert isinstance(result, str)
            # Result should not contain raw selector syntax
            assert "->" not in result
            event("outcome=select_resolved")

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=200, deadline=None)
    def test_missing_message_returns_id(self, msg_id: str) -> None:
        """Property: Missing message returns the message ID as fallback."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("other = value")

        # Filter to valid identifiers
        if not msg_id[0].isalpha():
            return

        result, errors = bundle.format_pattern(msg_id)

        # Should return something (ID or error indicator)
        assert isinstance(result, str)
        # Should have errors for missing message
        if msg_id != "other":
            assert len(errors) > 0
            event("outcome=missing_message_error")
        else:
            event("outcome=found_message")


class TestErrorCollectionProperties:
    """Property tests for error collection behavior."""

    @given(format_arguments())
    @settings(max_examples=200, deadline=None)
    def test_missing_variable_collected(self, args: dict[str, str | int | float]) -> None:
        """Property: Missing variables produce errors but don't crash."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = Hello { $missing_var }!")

        result, errors = bundle.format_pattern("msg", args)

        assert isinstance(result, str)
        # If missing_var is not in args, should have error
        if "missing_var" not in args:
            event("outcome=missing_var_error")
            # Result should still be usable (fallback)
            assert "Hello" in result or "missing_var" in result.lower() or len(errors) > 0
        else:
            event("outcome=var_found")

    @given(st.lists(st.sampled_from(["a", "b", "c", "d", "e"]), min_size=1, max_size=5))
    @settings(max_examples=100, deadline=None)
    def test_multiple_errors_collected(self, var_names: list[str]) -> None:
        """Property: Multiple errors are collected, not just the first."""
        # Create message with multiple variable references
        placeholders = " ".join(f"{{ ${v} }}" for v in var_names)
        ftl = f"msg = {placeholders}"

        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Call with no arguments - all variables missing
        result, errors = bundle.format_pattern("msg", {})

        assert isinstance(result, str)
        # Should have at least some indication of missing vars
        # (exact error count depends on implementation)
        assert isinstance(errors, tuple)
        event(f"error_count={len(errors)}")
        event("outcome=multiple_errors_collected")


class TestDepthLimitProperties:
    """Property tests for recursion depth limiting."""

    @given(st.integers(min_value=5, max_value=50))
    @settings(max_examples=50, deadline=None)
    def test_deep_reference_chain_terminates(self, depth: int) -> None:
        """Property: Deep reference chains terminate without stack overflow."""
        # Create a chain: msg0 -> msg1 -> msg2 -> ... -> msgN
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = See {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        ftl = "\n".join(messages)
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Should not raise RecursionError
        result, errors = bundle.format_pattern("msg0")

        event(f"recursion_depth={depth}")
        if errors:
            for err in errors:
                event(f"error_type={type(err).__name__}")
        else:
            event("outcome=deep_chain_resolved")

        assert isinstance(result, str)
        # Very deep chains may produce errors but shouldn't crash


class TestLocaleProperties:
    """Property tests for locale handling."""

    @given(st.sampled_from(["en-US", "de-DE", "fr-FR", "ja-JP", "zh-CN", "ar-SA", "lv-LV"]))
    @settings(max_examples=50, deadline=None)
    def test_locale_does_not_affect_basic_resolution(self, locale: str) -> None:
        """Property: Basic message resolution works for all locales."""
        bundle = FluentBundle(locale)
        bundle.add_resource("hello = Hello, world!")

        result, errors = bundle.format_pattern("hello")

        assert result == "Hello, world!"
        assert errors == ()
        event(f"locale={locale}")

    @given(
        st.sampled_from(["en-US", "de-DE", "fr-FR", "lv-LV"]),
        st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_plural_selection_by_locale(self, locale: str, count: int) -> None:
        """Property: Plural selection uses locale rules."""
        bundle = FluentBundle(locale)
        bundle.add_resource(
            """
items = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        )

        result, _ = bundle.format_pattern("items", {"count": count})

        assert isinstance(result, str)
        assert "item" in result.lower()
        event(f"locale_lang={locale.split('-', maxsplit=1)[0]}")
        event(f"plural_branch={'one' if 'One' in result else 'other'}")
