"""Tests for FluentBundle.get_all_message_variables().

Tests the batch introspection API for CI/CD validation use cases.
Includes unit tests, integration tests, edge cases, and property-based tests.

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine import FluentBundle


class TestGetAllMessageVariablesBasic:
    """Test basic functionality of get_all_message_variables()."""

    def test_empty_bundle_returns_empty_dict(self) -> None:
        """Empty bundle returns empty dictionary."""
        bundle = FluentBundle("en", use_isolating=False)

        result = bundle.get_all_message_variables()

        assert result == {}
        assert isinstance(result, dict)

    def test_single_message_no_variables(self) -> None:
        """Single message with no variables returns empty frozenset."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("hello = Hello, World!")

        result = bundle.get_all_message_variables()

        assert result == {"hello": frozenset()}

    def test_single_message_one_variable(self) -> None:
        """Single message with one variable."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        result = bundle.get_all_message_variables()

        assert result == {"greeting": frozenset({"name"})}

    def test_single_message_multiple_variables(self) -> None:
        """Single message with multiple variables."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("user = { $firstName } { $lastName } ({ $email })")

        result = bundle.get_all_message_variables()

        assert result == {
            "user": frozenset({"firstName", "lastName", "email"})
        }

    def test_multiple_messages_mixed_variables(self) -> None:
        """Multiple messages with varying numbers of variables."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
simple = No variables
single = Hello, { $name }
double = { $firstName } { $lastName }
none = Just text
""")

        result = bundle.get_all_message_variables()

        assert result == {
            "simple": frozenset(),
            "single": frozenset({"name"}),
            "double": frozenset({"firstName", "lastName"}),
            "none": frozenset(),
        }


class TestGetAllMessageVariablesWithComplexPatterns:
    """Test with complex FTL patterns."""

    def test_message_with_select_expression(self) -> None:
        """Message with select expression variables."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
emails = You have { $count ->
    [one] one email
   *[other] { $count } emails
}.
""")

        result = bundle.get_all_message_variables()

        assert result == {"emails": frozenset({"count"})}

    def test_message_with_function_call(self) -> None:
        """Message with function call extracting variable from argument."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
price = { NUMBER($amount, minimumFractionDigits: 2) }
""")

        result = bundle.get_all_message_variables()

        assert result == {"price": frozenset({"amount"})}

    def test_message_with_attributes(self) -> None:
        """Message with attributes containing variables."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
button-save = Save
    .tooltip = Save { $fileName } to disk
    .aria-label = Save button for { $fileName }
""")

        result = bundle.get_all_message_variables()

        # Both attributes should be included
        assert result == {"button-save": frozenset({"fileName"})}

    def test_message_with_duplicate_variable_usage(self) -> None:
        """Message using same variable multiple times (should appear once)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
repeat = { $name } and { $name } and { $name }
""")

        result = bundle.get_all_message_variables()

        # Variable should appear only once in frozenset
        assert result == {"repeat": frozenset({"name"})}

    def test_message_with_nested_select_expressions(self) -> None:
        """Message with nested select expressions."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
complex = { $gender ->
    [male] { $count ->
        [one] one item
       *[other] { $count } items
    }
   *[female] { $count ->
        [one] one item
       *[other] { $count } items
    }
}
""")

        result = bundle.get_all_message_variables()

        assert result == {"complex": frozenset({"gender", "count"})}


class TestGetAllMessageVariablesConsistency:
    """Test consistency with get_message_variables()."""

    def test_results_match_individual_calls(self) -> None:
        """Batch results match individual get_message_variables() calls."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
msg1 = Hello
msg2 = Hi { $name }
msg3 = Welcome { $firstName } { $lastName }
""")

        # Get batch result
        batch_result = bundle.get_all_message_variables()

        # Get individual results
        individual_results = {
            msg_id: bundle.get_message_variables(msg_id)
            for msg_id in bundle.get_message_ids()
        }

        assert batch_result == individual_results

    def test_batch_is_equivalent_to_manual_dict_comp(self) -> None:
        """Batch method is equivalent to manual dict comprehension."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
a = Test { $x }
b = Another { $y } { $z }
c = No vars
""")

        # Batch method
        batch_result = bundle.get_all_message_variables()

        # Manual dict comprehension (what users would write without batch method)
        manual_result = {
            msg_id: bundle.get_message_variables(msg_id)
            for msg_id in bundle.get_message_ids()
        }

        assert batch_result == manual_result


class TestGetAllMessageVariablesEdgeCases:
    """Test edge cases and error conditions."""

    def test_large_number_of_messages(self) -> None:
        """Bundle with many messages (performance test)."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add 100 messages
        ftl_source = "\n".join(
            f"msg{i} = Message {i} with {{ $var{i} }}"
            for i in range(100)
        )
        bundle.add_resource(ftl_source)

        result = bundle.get_all_message_variables()

        assert len(result) == 100
        assert all(f"msg{i}" in result for i in range(100))
        assert all(result[f"msg{i}"] == frozenset({f"var{i}"}) for i in range(100))

    def test_messages_added_incrementally(self) -> None:
        """Messages added via multiple add_resource() calls."""
        bundle = FluentBundle("en", use_isolating=False)

        bundle.add_resource("msg1 = Hello { $name }")
        bundle.add_resource("msg2 = Goodbye { $name }")
        bundle.add_resource("msg3 = Welcome { $firstName } { $lastName }")

        result = bundle.get_all_message_variables()

        assert len(result) == 3
        assert result["msg1"] == frozenset({"name"})
        assert result["msg2"] == frozenset({"name"})
        assert result["msg3"] == frozenset({"firstName", "lastName"})

    def test_message_overwriting_updates_result(self) -> None:
        """Overwritten messages reflect latest definition."""
        bundle = FluentBundle("en", use_isolating=False)

        bundle.add_resource("msg = Hello { $oldVar }")
        bundle.add_resource("msg = Hello { $newVar }")  # Overwrites

        result = bundle.get_all_message_variables()

        # Should have latest definition
        assert result == {"msg": frozenset({"newVar"})}

    def test_multiline_message_patterns(self) -> None:
        """Multiline message patterns extract variables correctly."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
multiline = This is line 1 with { $var1 }
    This is line 2 with { $var2 }
    This is line 3 with { $var3 }
""")

        result = bundle.get_all_message_variables()

        assert result == {
            "multiline": frozenset({"var1", "var2", "var3"})
        }


class TestGetAllMessageVariablesReturnType:
    """Test return type guarantees."""

    def test_return_type_is_dict(self) -> None:
        """Return type is dict."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Test")

        result = bundle.get_all_message_variables()

        assert isinstance(result, dict)

    def test_values_are_frozensets(self) -> None:
        """All values in returned dict are frozensets."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
msg1 = Test { $x }
msg2 = Another { $y }
msg3 = No vars
""")

        result = bundle.get_all_message_variables()

        for value in result.values():
            assert isinstance(value, frozenset)

    def test_returned_dict_is_mutable_copy(self) -> None:
        """Returned dict is mutable (user can modify without affecting bundle)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Test { $x }")

        result1 = bundle.get_all_message_variables()
        result2 = bundle.get_all_message_variables()

        # Modifying result1 should not affect result2
        result1["fake"] = frozenset({"fake"})

        assert "fake" not in result2
        assert len(result2) == 1


class TestGetAllMessageVariablesPropertyBased:
    """Property-based tests using Hypothesis."""

    @given(
        num_messages=st.integers(min_value=0, max_value=20),
        num_vars_per_msg=st.integers(min_value=0, max_value=5),
    )
    def test_batch_method_always_returns_dict(
        self, num_messages: int, num_vars_per_msg: int
    ) -> None:
        """Property: batch method always returns dict regardless of input."""
        bundle = FluentBundle("en", use_isolating=False)

        # Generate messages with variables
        messages = []
        for i in range(num_messages):
            vars_part = " ".join(
                f"{{ $var{j} }}"
                for j in range(num_vars_per_msg)
            )
            messages.append(f"msg{i} = Text {vars_part}")

        if messages:
            bundle.add_resource("\n".join(messages))

        result = bundle.get_all_message_variables()

        scale = "empty" if num_messages == 0 else "small"
        event(f"boundary={scale}")
        event(f"vars_per_msg={num_vars_per_msg}")
        assert isinstance(result, dict)
        assert len(result) == num_messages

    @given(
        message_ids=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=10
            ),
            min_size=0,
            max_size=10,
            unique=True
        )
    )
    def test_result_keys_match_message_ids(self, message_ids: list[str]) -> None:
        """Property: returned dict keys exactly match bundle message IDs."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add messages
        for msg_id in message_ids:
            bundle.add_resource(f"{msg_id} = Test message")

        result = bundle.get_all_message_variables()

        event(f"msg_count={len(message_ids)}")
        assert set(result.keys()) == set(message_ids)

    @given(st.integers(min_value=0, max_value=50))
    def test_batch_equals_individual_for_any_count(self, num_messages: int) -> None:
        """Property: batch result equals individual calls for any message count."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add messages
        ftl_source = "\n".join(
            f"msg{i} = Message {{ $var{i} }}"
            for i in range(num_messages)
        )
        if ftl_source:
            bundle.add_resource(ftl_source)

        # Batch result
        batch_result = bundle.get_all_message_variables()

        # Individual results
        individual_results = {
            msg_id: bundle.get_message_variables(msg_id)
            for msg_id in bundle.get_message_ids()
        }

        scale = "empty" if num_messages == 0 else "large"
        event(f"boundary={scale}")
        assert batch_result == individual_results


class TestGetAllMessageVariablesDocumentationExamples:
    """Verify examples from docstring work correctly."""

    def test_docstring_example(self) -> None:
        """Test example from method docstring."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""
greeting = Hello, { $name }!
farewell = Goodbye, { $firstName } { $lastName }!
simple = No variables here
""")

        all_vars = bundle.get_all_message_variables()

        assert all_vars["greeting"] == frozenset({"name"})
        assert all_vars["farewell"] == frozenset({"firstName", "lastName"})
        assert all_vars["simple"] == frozenset()
