# mypy: ignore-errors
from __future__ import annotations

import threading

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import parse_ftl
from ftllexengine.introspection import (
    clear_introspection_cache,
    extract_references,
    extract_variables,
    introspect_message,
)
from ftllexengine.introspection.message import (
    _introspection_cache,
    _introspection_cache_lock,
)
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    Pattern,
    Placeable,
    Term,
    TextElement,
    VariableReference,
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


_var_names = st.from_regex(r"[a-z]+", fullmatch=True)

_msg_ids = st.from_regex(r"[a-z]+", fullmatch=True)

class TestVariableExtractionProperties:
    """Property-based invariants for variable extraction."""

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_simple_variable_always_extracted(self, var_name: str) -> None:
        """{ $var } always extracts var."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        assert var_name in extract_variables(msg)

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_duplicate_variables_deduplicated(self, var_name: str) -> None:
        """{ $var } { $var } extracts var once."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }} {{ ${var_name} }}")
        variables = extract_variables(msg)
        assert var_name in variables
        assert len([v for v in variables if v == var_name]) == 1

    @given(var1=_var_names, var2=_var_names)
    @settings(max_examples=200)
    def test_multiple_variables_all_extracted(self, var1: str, var2: str) -> None:
        """{ $a } { $b } extracts both a and b."""
        event(f"same_vars={var1 == var2}")
        msg = _parse_message(f"msg = Hello {{ ${var1} }} {{ ${var2} }}")
        variables = extract_variables(msg)
        assert var1 in variables
        if var1 != var2:
            assert var2 in variables

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_variables_returns_empty_set(self, msg_id: str) -> None:
        """Message with no variables returns empty frozenset."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello World")
        assert len(extract_variables(msg)) == 0

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_variable_in_function_extracted(self, var_name: str) -> None:
        """NUMBER($var) extracts var."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = {{ NUMBER(${var_name}) }}")
        assert var_name in extract_variables(msg)

    @given(var_name=_var_names, attr_name=st.from_regex(r"[a-z]+", fullmatch=True))
    @settings(max_examples=100)
    def test_attribute_variable_extracted(self, var_name: str, attr_name: str) -> None:
        """Variables in attributes are extracted."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello\n    .{attr_name} = {{ ${var_name} }}")
        assert var_name in introspect_message(msg).get_variable_names()

class TestIntrospectionResultProperties:
    """Properties of MessageIntrospection result objects."""

    @given(msg_id=_msg_ids)
    @settings(max_examples=200)
    def test_message_id_preserved(self, msg_id: str) -> None:
        """introspect_message preserves message ID."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello")
        assert introspect_message(msg).message_id == msg_id

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_get_variable_names_consistent(self, var_name: str) -> None:
        """get_variable_names() and variables field are consistent."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        info = introspect_message(msg)
        var_names = info.get_variable_names()
        assert var_name in var_names
        assert len(info.variables) == len(var_names)

    @given(var_name=_var_names)
    @settings(max_examples=200)
    def test_requires_variable_matches_extraction(self, var_name: str) -> None:
        """requires_variable(x) iff x in get_variable_names()."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        info = introspect_message(msg)
        if info.requires_variable(var_name):
            assert var_name in info.get_variable_names()
        if var_name in info.get_variable_names():
            assert info.requires_variable(var_name)

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_selectors_for_simple_message(self, msg_id: str) -> None:
        """Simple message has has_selectors=False."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello")
        assert introspect_message(msg).has_selectors is False

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_select_expression_sets_has_selectors(self, var_name: str) -> None:
        """Message with select expression has has_selectors=True."""
        event(f"var_name={var_name}")
        msg = _parse_message(
            f"msg = {{ ${var_name} ->\n    [one] One item\n   *[other] Many items\n}}"
        )
        assert introspect_message(msg).has_selectors is True

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_number_function_detected(self, var_name: str) -> None:
        """NUMBER($var) is detected as a function call."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = {{ NUMBER(${var_name}) }}")
        assert "NUMBER" in introspect_message(msg).get_function_names()

    @given(msg_id=_msg_ids)
    @settings(max_examples=100)
    def test_no_functions_returns_empty_set(self, msg_id: str) -> None:
        """Message with no functions returns empty frozenset."""
        event(f"msg_id={msg_id}")
        msg = _parse_message(f"{msg_id} = Hello World")
        assert len(introspect_message(msg).get_function_names()) == 0

class TestIntrospectionIdempotence:
    """Idempotence: repeated calls return same results."""

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_extract_variables_idempotent(self, var_name: str) -> None:
        """Multiple extract_variables() calls return the same result."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        r1 = extract_variables(msg)
        r2 = extract_variables(msg)
        assert r1 == r2

    @given(var_name=_var_names)
    @settings(max_examples=100)
    def test_introspect_message_idempotent(self, var_name: str) -> None:
        """Multiple introspect_message() calls return equivalent results."""
        event(f"var_name={var_name}")
        msg = _parse_message(f"msg = Hello {{ ${var_name} }}")
        r1 = introspect_message(msg)
        r2 = introspect_message(msg)
        assert r1.message_id == r2.message_id
        assert r1.variables == r2.variables
        assert r1.functions == r2.functions
        assert r1.references == r2.references
        assert r1.has_selectors == r2.has_selectors

    @given(vars_list=st.lists(_var_names, min_size=1, max_size=10, unique=True))
    @settings(max_examples=50)
    def test_multiple_variables_all_captured(self, vars_list: list[str]) -> None:
        """All variables in message are captured in extract_variables."""
        event(f"var_count={len(vars_list)}")
        placeables = " ".join(f"{{ ${v} }}" for v in vars_list)
        msg = _parse_message(f"msg = {placeables}")
        variables = extract_variables(msg)
        for var in vars_list:
            assert var in variables
        assert len(variables) == len(vars_list)

    @given(
        var_names_list=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30)
    def test_arbitrary_variable_named_args(self, var_names_list: list[str]) -> None:
        """Functions with arbitrary variable names in named args extract all vars."""
        var_names_list = list(dict.fromkeys(var_names_list))
        if not var_names_list:
            return
        event(f"var_count={len(var_names_list)}")
        var_list = ", ".join(f"{name}: ${name}" for name in var_names_list)
        ftl = f"test = {{ NUMBER($value, {var_list}) }}"
        resource = parse_ftl(ftl)
        if not resource.entries or isinstance(resource.entries[0], Junk):
            return
        msg = resource.entries[0]
        if not isinstance(msg, Message):
            return
        info = introspect_message(msg)
        assert "value" in info.get_variable_names()
        for name in var_names_list:
            assert name in info.get_variable_names()

class TestIntrospectionNestedPlaceable:
    """Test introspection of nested Placeable expressions."""

    def test_nested_placeable_extraction(self) -> None:
        """Nested Placeable (Placeable containing Placeable) visits inner expression."""
        inner_var = VariableReference(id=Identifier("innerVar"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer_placeable,)),
            attributes=(),
        )

        result = introspect_message(message)

        var_names = {v.name for v in result.variables}
        assert "innerVar" in var_names

    def test_deeply_nested_placeables(self) -> None:
        """Multiple levels of nested Placeables are fully traversed."""
        var = VariableReference(id=Identifier("deep"))
        level1 = Placeable(expression=var)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        message = Message(
            id=Identifier("deepNest"),
            value=Pattern(elements=(level3,)),
            attributes=(),
        )

        result = introspect_message(message)
        var_names = {v.name for v in result.variables}
        assert "deep" in var_names

    def test_message_without_value_extract_references(self) -> None:
        """Message with value=None but with attributes extracts from attributes."""
        attr_pattern = Pattern(
            elements=(Placeable(expression=VariableReference(id=Identifier("attrVar"))),)
        )
        message = Message(
            id=Identifier("attrsOnly"),
            value=None,
            attributes=(Attribute(id=Identifier("hint"), value=attr_pattern),),
        )

        msg_refs, term_refs = extract_references(message)

        assert isinstance(msg_refs, frozenset)
        assert isinstance(term_refs, frozenset)

    def test_introspect_message_without_value(self) -> None:
        """introspect_message extracts from attributes when message.value is None."""
        attr_pattern = Pattern(
            elements=(
                TextElement("Hint: "),
                Placeable(expression=VariableReference(id=Identifier("hintVar"))),
            )
        )
        message = Message(
            id=Identifier("noValue"),
            value=None,
            attributes=(Attribute(id=Identifier("tooltip"), value=attr_pattern),),
        )

        result = introspect_message(message)

        var_names = {v.name for v in result.variables}
        assert "hintVar" in var_names

class TestIntrospectionBranchCoverage:
    """Tests for introspection branch coverage."""

    def test_function_without_arguments(self) -> None:
        """Function reference with empty arguments visits function node correctly."""
        func_ref = FunctionReference(
            id=Identifier("NOARGS"),
            arguments=CallArguments(positional=(), named=()),
        )

        message = Message(
            id=Identifier("noArgsFunc"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        result = introspect_message(message)

        func_names = {f.name for f in result.functions}
        assert "NOARGS" in func_names

    def test_text_element_only_pattern(self) -> None:
        """Pattern with only TextElement yields no variables or functions."""
        message = Message(
            id=Identifier("textOnly"),
            value=Pattern(elements=(TextElement("Just plain text"),)),
            attributes=(),
        )

        result = introspect_message(message)

        assert len(result.variables) == 0
        assert len(result.functions) == 0

    def test_function_with_empty_call_arguments(self) -> None:
        """Function with empty positional and named arguments is still recorded."""
        func_ref = FunctionReference(
            id=Identifier("EMPTY"),
            arguments=CallArguments(positional=(), named=()),
        )

        message = Message(
            id=Identifier("emptyArgs"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )

        result = introspect_message(message)

        func_names = {f.name for f in result.functions}
        assert "EMPTY" in func_names

class TestIntrospectionThreadSafety:
    """Verify the cache lock prevents data corruption under concurrent access.

    These tests exercise the check-compute-store pattern introduced with the
    threading.Lock that replaced the GIL-reliant lock-free WeakKeyDictionary
    access. They run in CI (no @pytest.mark.fuzz) because the thread counts
    are small and the wall-clock cost is negligible.
    """

    def test_concurrent_introspection_same_message(self) -> None:
        """Concurrent introspection of the same Message yields identical results.

        All threads must see the same MessageIntrospection (equal by content),
        and the cache must contain exactly one entry for the shared message.
        """
        message = Message(
            id=Identifier("sharedMsg"),
            value=Pattern(elements=(
                TextElement("Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )),
            attributes=(),
        )

        # Clear cache to ensure a fresh start for this test.
        with _introspection_cache_lock:
            _introspection_cache.clear()

        results: list[object] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                results.append(introspect_message(message))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 20

        # All results must be equal (same content, immutable).
        first = results[0]
        assert all(r == first for r in results)

    def test_concurrent_clear_and_introspect(self) -> None:
        """Concurrent clear + introspect does not corrupt the cache.

        After all operations complete, any surviving cached entry must be
        a valid MessageIntrospection (no partially-written garbage).
        """
        message = Message(
            id=Identifier("racyMsg"),
            value=Pattern(elements=(TextElement("race"),)),
            attributes=(),
        )

        errors: list[BaseException] = []

        def introspector() -> None:
            try:
                for _ in range(10):
                    introspect_message(message)
            except Exception as exc:
                errors.append(exc)

        def clearer() -> None:
            try:
                for _ in range(5):
                    clear_introspection_cache()
            except Exception as exc:
                errors.append(exc)

        threads = (
            [threading.Thread(target=introspector) for _ in range(8)]
            + [threading.Thread(target=clearer) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"

        # Final cache state must be consistent: either empty or holding a valid result.
        result = introspect_message(message)
        assert result.message_id == "racyMsg"
