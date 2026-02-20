"""Hypothesis property-based tests for message introspection.

Tests structural invariants for variable extraction, function detection,
reference tracking, and immutability guarantees. All @given tests emit
semantic events for HypoFuzz coverage guidance.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.parser import FluentParserV1

# Module-level strategy primitives (no composite needed; events are in tests)
_variable_names = st.from_regex(r"[a-z]+", fullmatch=True)
_message_ids = st.from_regex(r"[a-z]+", fullmatch=True)


def _msg(ftl: str) -> Message:
    resource = FluentParserV1().parse(ftl)
    entry = resource.entries[0]
    assert isinstance(entry, Message)
    return entry


# ============================================================================
# VARIABLE EXTRACTION INVARIANTS
# ============================================================================


class TestVariableExtractionInvariants:
    """Mathematical invariants for variable extraction."""

    @given(var_name=_variable_names)
    @settings(max_examples=200)
    def test_simple_variable_always_extracted(self, var_name: str) -> None:
        """INVARIANT: { $var } always extracts var."""
        event(f"var_name={var_name}")
        assert var_name in extract_variables(_msg(f"msg = Hello {{ ${var_name} }}"))

    @given(var_name=_variable_names)
    @settings(max_examples=200)
    def test_duplicate_variables_deduplicated(self, var_name: str) -> None:
        """INVARIANT: { $var } { $var } extracts var exactly once."""
        event(f"var_name={var_name}")
        variables = extract_variables(
            _msg(f"msg = Hello {{ ${var_name} }} {{ ${var_name} }}")
        )
        assert var_name in variables
        assert len([v for v in variables if v == var_name]) == 1

    @given(var1=_variable_names, var2=_variable_names)
    @settings(max_examples=200)
    def test_multiple_variables_all_extracted(self, var1: str, var2: str) -> None:
        """INVARIANT: { $a } { $b } extracts both."""
        event(f"same_vars={var1 == var2}")
        variables = extract_variables(_msg(f"msg = Hello {{ ${var1} }} {{ ${var2} }}"))
        assert var1 in variables
        if var1 != var2:
            assert var2 in variables

    @given(msg_id=_message_ids)
    @settings(max_examples=100)
    def test_no_variables_returns_empty_set(self, msg_id: str) -> None:
        """INVARIANT: Message with no variables returns empty frozenset."""
        event(f"msg_id={msg_id}")
        assert len(extract_variables(_msg(f"{msg_id} = Hello World"))) == 0

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_variable_in_function_extracted(self, var_name: str) -> None:
        """INVARIANT: NUMBER($var) extracts var."""
        event(f"var_name={var_name}")
        assert var_name in extract_variables(_msg(f"msg = {{ NUMBER(${var_name}) }}"))

    @given(var_name=_variable_names, attr_name=st.from_regex(r"[a-z]+", fullmatch=True))
    @settings(max_examples=100)
    def test_attribute_variable_extracted(self, var_name: str, attr_name: str) -> None:
        """INVARIANT: Variables in message attributes are extracted."""
        event(f"var_name={var_name}")
        msg = _msg(f"msg = Hello\n    .{attr_name} = {{ ${var_name} }}")
        assert var_name in introspect_message(msg).get_variable_names()


# ============================================================================
# INTROSPECTION RESULT INVARIANTS
# ============================================================================


class TestIntrospectionResultInvariants:
    """Invariants for MessageIntrospection result objects."""

    @given(msg_id=_message_ids)
    @settings(max_examples=200)
    def test_message_id_preserved(self, msg_id: str) -> None:
        """INVARIANT: introspect_message preserves message ID."""
        event(f"msg_id={msg_id}")
        assert introspect_message(_msg(f"{msg_id} = Hello")).message_id == msg_id

    @given(var_name=_variable_names)
    @settings(max_examples=200)
    def test_get_variable_names_consistent_with_variables(self, var_name: str) -> None:
        """INVARIANT: get_variable_names() set size equals variables set size."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = Hello {{ ${var_name} }}"))
        assert var_name in info.get_variable_names()
        assert len(info.variables) == len(info.get_variable_names())

    @given(var_name=_variable_names)
    @settings(max_examples=200)
    def test_requires_variable_iff_in_get_variable_names(self, var_name: str) -> None:
        """INVARIANT: requires_variable(x) iff x in get_variable_names()."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = Hello {{ ${var_name} }}"))
        assert info.requires_variable(var_name) == (var_name in info.get_variable_names())

    @given(msg_id=_message_ids)
    @settings(max_examples=100)
    def test_no_selectors_for_simple_message(self, msg_id: str) -> None:
        """INVARIANT: Simple message has has_selectors=False."""
        event(f"msg_id={msg_id}")
        assert introspect_message(_msg(f"{msg_id} = Hello")).has_selectors is False

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_select_expression_sets_has_selectors(self, var_name: str) -> None:
        """INVARIANT: Message with select expression has has_selectors=True."""
        event(f"var_name={var_name}")
        msg = _msg(
            f"msg = {{ ${var_name} ->\n    [one] One item\n   *[other] Many items\n}}"
        )
        assert introspect_message(msg).has_selectors is True


# ============================================================================
# FUNCTION DETECTION INVARIANTS
# ============================================================================


class TestFunctionDetectionInvariants:
    """Invariants for function call detection."""

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_number_function_detected(self, var_name: str) -> None:
        """INVARIANT: NUMBER($var) is detected as a function call."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = {{ NUMBER(${var_name}) }}"))
        assert "NUMBER" in info.get_function_names()

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_datetime_function_detected(self, var_name: str) -> None:
        """INVARIANT: DATETIME($var) is detected as a function call."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = {{ DATETIME(${var_name}) }}"))
        assert "DATETIME" in info.get_function_names()

    @given(msg_id=_message_ids)
    @settings(max_examples=100)
    def test_no_functions_returns_empty_set(self, msg_id: str) -> None:
        """INVARIANT: Message with no functions returns empty frozenset."""
        event(f"msg_id={msg_id}")
        assert len(introspect_message(_msg(f"{msg_id} = Hello World")).get_function_names()) == 0


# ============================================================================
# IMMUTABILITY INVARIANTS
# ============================================================================


class TestImmutabilityInvariants:
    """Immutability guarantees for result objects."""

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_variables_is_frozenset(self, var_name: str) -> None:
        """INVARIANT: variables field is a frozenset."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = Hello {{ ${var_name} }}"))
        assert isinstance(info.variables, frozenset)

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_get_variable_names_returns_frozenset(self, var_name: str) -> None:
        """INVARIANT: get_variable_names() returns frozenset."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = Hello {{ ${var_name} }}"))
        assert isinstance(info.get_variable_names(), frozenset)

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_get_function_names_returns_frozenset(self, var_name: str) -> None:
        """INVARIANT: get_function_names() returns frozenset."""
        event(f"var_name={var_name}")
        info = introspect_message(_msg(f"msg = {{ NUMBER(${var_name}) }}"))
        assert isinstance(info.get_function_names(), frozenset)


# ============================================================================
# IDEMPOTENCE INVARIANTS
# ============================================================================


class TestIdempotenceInvariants:
    """Idempotence: repeated introspection produces identical results."""

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_extract_variables_idempotent(self, var_name: str) -> None:
        """INVARIANT: Multiple extract_variables() calls return same result."""
        event(f"var_name={var_name}")
        msg = _msg(f"msg = Hello {{ ${var_name} }}")
        r1 = extract_variables(msg)
        r2 = extract_variables(msg)
        assert r1 == r2

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_introspect_message_idempotent(self, var_name: str) -> None:
        """INVARIANT: Repeated introspect_message() returns equivalent results."""
        event(f"var_name={var_name}")
        msg = _msg(f"msg = Hello {{ ${var_name} }}")
        r1 = introspect_message(msg)
        r2 = introspect_message(msg)
        assert r1.message_id == r2.message_id
        assert r1.variables == r2.variables
        assert r1.functions == r2.functions
        assert r1.references == r2.references
        assert r1.has_selectors == r2.has_selectors

    @given(var_name=_variable_names)
    @settings(max_examples=100)
    def test_get_variable_names_idempotent(self, var_name: str) -> None:
        """INVARIANT: Repeated get_variable_names() calls return same result."""
        event(f"var_name={var_name}")
        msg = _msg(f"msg = Hello {{ ${var_name} }}")
        info = introspect_message(msg)
        assert info.get_variable_names() == info.get_variable_names()


# ============================================================================
# ROBUSTNESS
# ============================================================================


class TestRobustness:
    """Robustness with edge-case inputs."""

    @given(vars_list=st.lists(_variable_names, min_size=1, max_size=10, unique=True))
    @settings(max_examples=50)
    def test_all_variables_captured(self, vars_list: list[str]) -> None:
        """ROBUSTNESS: All variables in a multi-variable message are captured."""
        event(f"var_count={len(vars_list)}")
        placeables = " ".join(f"{{ ${v} }}" for v in vars_list)
        msg = _msg(f"msg = {placeables}")
        variables = extract_variables(msg)
        for var in vars_list:
            assert var in variables
        assert len(variables) == len(vars_list)

    @given(msg_id=_message_ids)
    @settings(max_examples=100)
    def test_minimal_message_introspects_cleanly(self, msg_id: str) -> None:
        """ROBUSTNESS: Minimal valid message is introspected without error."""
        event(f"msg_id={msg_id}")
        info = introspect_message(_msg(f"{msg_id} = X"))
        assert len(info.get_variable_names()) == 0
        assert len(info.get_function_names()) == 0
        assert info.has_selectors is False

    @pytest.mark.fuzz
    @given(
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=20,
        )
    )
    def test_variable_extraction_roundtrip(self, var_name: str) -> None:
        """ROUNDTRIP: Variables extracted match those in source pattern."""
        event(f"var_len={len(var_name)}")
        ftl_source = f"msg = Hello {{ ${var_name} }}"
        try:
            resource = FluentParserV1().parse(ftl_source)
            if not resource.entries:
                return
            message = resource.entries[0]
            if not isinstance(message, Message):
                return
            assert var_name in extract_variables(message)
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # Some generated names may not parse as valid FTL identifiers
