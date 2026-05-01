# mypy: ignore-errors
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

import ftllexengine.introspection.message as _introspection_msg_mod
from ftllexengine.introspection import (
    MessageVariableValidationResult,
    clear_introspection_cache,
    introspect_message,
    validate_message_variables,
)
from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    Pattern,
    Placeable,
    Term,
    TextElement,
)
from ftllexengine.syntax.parser import FluentParserV1

# ===========================================================================
# HELPERS
# ===========================================================================


def _parse_message(ftl: str) -> Message:
    """Parse FTL source and return first Message entry."""
    resource = FluentParserV1().parse(ftl)
    entry = resource.entries[0]
    assert isinstance(entry, Message)
    return entry


def _parse_term(ftl: str) -> Term:
    """Parse FTL source and return first Term entry."""
    resource = FluentParserV1().parse(ftl)
    entry = resource.entries[0]
    assert isinstance(entry, Term)
    return entry


def _make_message(
    name: str,
    *,
    value: Pattern | None = None,
    attributes: tuple[Attribute, ...] = (),
) -> Message:
    """Construct a Message programmatically (bypasses parser)."""
    return Message(id=Identifier(name=name), value=value, attributes=attributes)


def _make_pattern(*elements: TextElement | Placeable) -> Pattern:
    """Construct a Pattern from elements."""
    return Pattern(elements=elements)


# ===========================================================================
# VARIABLE EXTRACTION
# ===========================================================================



class TestCacheDoubleCheckHit:
    """Covers introspect_message line 674: the locked double-check cache hit.

    Line 674 fires only when another thread stores the result between step 1
    (initial pre-lock miss check) and step 3 (locked store). The test uses
    a mock lock that pre-fills the cache before the double-check code runs,
    exactly simulating the winning-race scenario.
    """

    def test_double_check_returns_preexisting_result(self) -> None:
        """Line 674: double-check inside lock returns pre-filled entry.

        The mock lock pre-fills _introspection_cache[msg] on __enter__,
        simulating another thread winning the race. introspect_message must
        return the pre-filled result rather than overwriting it.
        """
        msg = _parse_message("dc-test = { $var }")
        clear_introspection_cache()

        # Compute reference result (no cache interaction)
        expected = introspect_message(msg, use_cache=False)
        clear_introspection_cache()

        # Capture original lock before patching
        orig_lock = _introspection_msg_mod._introspection_cache_lock

        class _RaceLock:
            """Simulates a concurrent thread winning the race at Step 3.

            introspect_message acquires the lock TWICE per call with use_cache=True:
            - First acquisition: Step 1 read-check (cache is empty, should miss)
            - Second acquisition: Step 3 write-check (pre-fill simulates the race)
            Pre-filling on the first acquisition would cause an early return at the
            Step 1 hit (line 641), bypassing the double-check at line 674 entirely.
            """

            def __init__(self) -> None:
                self._call_count = 0

            def __enter__(self) -> object:
                orig_lock.acquire()
                self._call_count += 1
                if self._call_count == 2:  # Step 3 write-check only
                    _introspection_msg_mod._introspection_cache[msg] = expected
                return self

            def __exit__(
                self,
                exc_type: type[BaseException] | None,
                exc_val: BaseException | None,
                exc_tb: object,
            ) -> None:
                orig_lock.release()

        with patch.object(
            _introspection_msg_mod, "_introspection_cache_lock", _RaceLock()
        ):
            # Step 1: first __enter__ — cache is empty, miss, continue to Step 2
            # Step 2: computation proceeds normally
            # Step 3: second __enter__ pre-fills cache — double-check hits line 674
            result = introspect_message(msg, use_cache=True)

        assert result.message_id == expected.message_id
        assert result.get_variable_names() == expected.get_variable_names()
        clear_introspection_cache()

class TestMessageVariableValidationResult:
    """Tests for the MessageVariableValidationResult frozen dataclass."""

    def test_immutable(self) -> None:
        """MessageVariableValidationResult is frozen (immutable)."""
        result = MessageVariableValidationResult(
            message_id="greeting",
            is_valid=True,
            declared_variables=frozenset({"name"}),
            missing_variables=frozenset(),
            extra_variables=frozenset(),
        )
        with pytest.raises(AttributeError):
            result.is_valid = False  # type: ignore[misc]

    def test_valid_result_fields(self) -> None:
        """is_valid=True when missing and extra are both empty."""
        result = MessageVariableValidationResult(
            message_id="msg",
            is_valid=True,
            declared_variables=frozenset({"a", "b"}),
            missing_variables=frozenset(),
            extra_variables=frozenset(),
        )
        assert result.is_valid is True
        assert result.declared_variables == frozenset({"a", "b"})
        assert result.missing_variables == frozenset()
        assert result.extra_variables == frozenset()

    def test_invalid_with_missing(self) -> None:
        """is_valid=False when missing_variables is non-empty."""
        result = MessageVariableValidationResult(
            message_id="msg",
            is_valid=False,
            declared_variables=frozenset({"a"}),
            missing_variables=frozenset({"b"}),
            extra_variables=frozenset(),
        )
        assert result.is_valid is False
        assert "b" in result.missing_variables

    def test_hashable(self) -> None:
        """MessageVariableValidationResult is hashable (frozen dataclass)."""
        r1 = MessageVariableValidationResult(
            message_id="greeting",
            is_valid=True,
            declared_variables=frozenset({"name"}),
            missing_variables=frozenset(),
            extra_variables=frozenset(),
        )
        assert hash(r1) is not None
        s: set[MessageVariableValidationResult] = {r1}
        assert len(s) == 1

class TestValidateMessageVariables:
    """Tests for validate_message_variables()."""

    def test_exact_match_is_valid(self) -> None:
        """Message declaring exactly the expected variables returns is_valid=True."""
        msg = _parse_message("greeting = Hello, { $name }! You have { $count } items.")
        result = validate_message_variables(msg, {"name", "count"})
        assert result.is_valid is True
        assert result.declared_variables == frozenset({"name", "count"})
        assert result.missing_variables == frozenset()
        assert result.extra_variables == frozenset()

    def test_missing_variable_detected(self) -> None:
        """Expected variable absent from FTL message is reported in missing_variables."""
        msg = _parse_message("greeting = Hello, { $name }!")
        result = validate_message_variables(msg, {"name", "count"})
        assert result.is_valid is False
        assert result.missing_variables == frozenset({"count"})
        assert result.extra_variables == frozenset()

    def test_extra_variable_detected(self) -> None:
        """Variable declared in FTL but absent from expected is reported in extra_variables."""
        msg = _parse_message("greeting = Hello, { $name }! You have { $count } items.")
        result = validate_message_variables(msg, {"name"})
        assert result.is_valid is False
        assert result.extra_variables == frozenset({"count"})
        assert result.missing_variables == frozenset()

    def test_both_missing_and_extra_detected(self) -> None:
        """Both missing and extra variables reported independently."""
        msg = _parse_message("msg = { $actual } value")
        result = validate_message_variables(msg, {"expected"})
        assert result.is_valid is False
        assert "expected" in result.missing_variables
        assert "actual" in result.extra_variables

    def test_empty_expected_all_extra(self) -> None:
        """Expected set is empty: all declared variables are extra."""
        msg = _parse_message("msg = Hello { $name }!")
        result = validate_message_variables(msg, frozenset())
        assert result.is_valid is False
        assert result.extra_variables == frozenset({"name"})
        assert result.missing_variables == frozenset()

    def test_message_with_no_variables_and_empty_expected(self) -> None:
        """Static message with no variables and empty expected is valid."""
        msg = _parse_message("static = Hello World")
        result = validate_message_variables(msg, frozenset())
        assert result.is_valid is True
        assert result.declared_variables == frozenset()

    def test_message_id_extracted_from_ast_node(self) -> None:
        """result.message_id matches the FTL message identifier."""
        msg = _parse_message("my-message = { $var }")
        result = validate_message_variables(msg, {"var"})
        assert result.message_id == "my-message"

    def test_frozenset_and_set_expected_equivalent(self) -> None:
        """frozenset and set inputs for expected_variables produce identical results."""
        msg = _parse_message("greeting = Hello, { $name }!")
        result_set = validate_message_variables(msg, {"name"})
        result_frozen = validate_message_variables(msg, frozenset({"name"}))
        assert result_set.is_valid == result_frozen.is_valid
        assert result_set.declared_variables == result_frozen.declared_variables
        assert result_set.missing_variables == result_frozen.missing_variables
        assert result_set.extra_variables == result_frozen.extra_variables

    def test_validate_term(self) -> None:
        """validate_message_variables works on Term AST nodes."""
        resource = FluentParserV1().parse("-brand = { $edition } Edition")
        term = next(e for e in resource.entries if isinstance(e, Term))
        result = validate_message_variables(term, {"edition"})
        assert result.is_valid is True
        assert result.message_id == "brand"

    @given(
        var_names=st.frozensets(
            st.from_regex(r"[a-z][a-z]{0,9}", fullmatch=True),
            min_size=0,
            max_size=5,
        ),
        extra_vars=st.frozensets(
            st.from_regex(r"[a-z][a-z]{0,9}", fullmatch=True),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=200)
    def test_property_validity_iff_exact_match(
        self, var_names: frozenset[str], extra_vars: frozenset[str]
    ) -> None:
        """is_valid iff declared == expected (exact set equality).

        Constructs a message with exactly var_names as variables, validates
        against expected = var_names | extra_vars. Result is valid only when
        extra_vars is empty.
        """
        event(f"declared_count={len(var_names)}")
        event(f"extra_count={len(extra_vars)}")

        # Filter out names that overlap between the two sets
        safe_names = list(var_names)
        safe_extra = [n for n in extra_vars if n not in var_names]

        if not safe_names and not safe_extra:
            event("outcome=empty_skip")
            return

        placeable_ftl = " ".join(f"{{ ${n} }}" for n in safe_names)
        ftl_source = f"msg = {placeable_ftl or 'static'}"

        resource = FluentParserV1().parse(ftl_source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        if not messages:
            event("outcome=parse_failed")
            return

        declared = frozenset(safe_names)
        expected = declared | frozenset(safe_extra)
        result = validate_message_variables(messages[0], expected)

        assert result.declared_variables == declared
        assert result.missing_variables == frozenset(safe_extra)
        assert result.extra_variables == frozenset()

        if safe_extra:
            event("outcome=missing_detected")
            assert result.is_valid is False
        else:
            event("outcome=exact_match")
            assert result.is_valid is True
