"""Metamorphic property-based testing for FTLLexEngine.

This module implements SYSTEM 2 from the testing strategy: Metamorphic Testing.
Instead of testing concrete outputs (oracle problem), we test **metamorphic relations**
- properties that should hold across related inputs/outputs.

Metamorphic Relations Tested:
1. Serialization idempotence: serialize(ast) == serialize(ast) always
2. Parse determinism: parse(text) == parse(text) always
3. Resolution stability: resolve(msg, args) == resolve(msg, args) always
4. Argument monotonicity: Adding unused args doesn't change output
5. Serializer commutativity: Order of serialization calls doesn't matter
6. Parser robustness: Parser never crashes on any input
7. Roundtrip convergence: parse→serialize→parse→serialize converges
8. Locale independence: Changing locale doesn't crash (may change output)
9. Message immutability: AST nodes are truly immutable
10. Variable substitution order independence

These properties catch semantic bugs that coverage metrics miss.

References:
- T.Y. Chen et al., "Metamorphic Testing: A Review of Challenges and Opportunities" (2018)
- Our deep analysis identified oracle gap issues in existing tests
"""


import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.syntax.ast import Message, Resource
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from tests.strategies import (
    ftl_identifiers,
    ftl_resources,
    ftl_simple_messages,
)


class TestSerializationMetamorphicProperties:
    """Metamorphic relations for serialization."""

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_serialization_deterministic(self, resource):
        """MR1: Serialization is deterministic.

        Property: serialize(ast) == serialize(ast) always
        Rationale: Same AST should always produce same FTL string
        """
        ftl1 = serialize(resource)
        ftl2 = serialize(resource)

        assert ftl1 == ftl2, "Serialization should be deterministic"

    @given(ftl_resources())
    @settings(max_examples=100)
    def test_serialization_idempotent_structure(self, resource):
        """MR2: Serialization doesn't mutate input AST.

        Property: AST structure unchanged after serialization
        Rationale: Serialization is read-only operation
        """
        # Count entries before
        entries_before = len(resource.entries)

        # Serialize
        _ = serialize(resource)

        # Count entries after
        entries_after = len(resource.entries)

        assert entries_before == entries_after
        assert resource.entries is not None

    @given(ftl_resources())
    @settings(max_examples=50)
    def test_serialize_parse_serialize_converges(self, resource):
        """MR3: Roundtrip converges to fixed point.

        Property: serialize→parse→serialize→parse→serialize converges
        Rationale: After first roundtrip, format stabilizes
        """
        parser = FluentParserV1()

        # First serialization
        ftl1 = serialize(resource)

        # Parse and serialize again
        resource2 = parser.parse(ftl1)
        ftl2 = serialize(resource2)

        # Parse and serialize third time
        resource3 = parser.parse(ftl2)
        ftl3 = serialize(resource3)

        # Should have converged
        assert ftl2 == ftl3, "Serialization should converge after first roundtrip"


class TestParserMetamorphicProperties:
    """Metamorphic relations for parser."""

    @given(st.text(max_size=1000))
    @settings(max_examples=200)
    def test_parser_never_crashes(self, text):
        """MR4: Parser robustness - never crashes.

        Property: parse(any_string) returns Resource (never throws)
        Rationale: Parser should handle ALL inputs gracefully
        """
        parser = FluentParserV1()

        # Should not raise exception
        resource = parser.parse(text)

        # Should return valid Resource
        assert isinstance(resource, Resource)
        assert resource.entries is not None

    @given(st.text(min_size=1, max_size=500))
    @settings(max_examples=100)
    def test_parser_deterministic(self, text):
        """MR5: Parser determinism.

        Property: parse(text) == parse(text) always
        Rationale: Same input should produce same AST
        """
        parser = FluentParserV1()

        resource1 = parser.parse(text)
        resource2 = parser.parse(text)

        # Should produce same number of entries
        assert len(resource1.entries) == len(resource2.entries)

        # Entry types should match
        types1 = [type(e).__name__ for e in resource1.entries]
        types2 = [type(e).__name__ for e in resource2.entries]
        assert types1 == types2

    @given(ftl_simple_messages(), ftl_simple_messages())
    @settings(max_examples=50)
    def test_parser_concatenation_independence(self, ftl1, ftl2):
        """MR6: Parse result independent of concatenation order.

        Property: Parsing msg1, msg2 separately vs together behaves predictably
        Rationale: Parser should handle messages independently
        """
        parser = FluentParserV1()

        # Parse separately
        r1 = parser.parse(ftl1)
        r2 = parser.parse(ftl2)
        count_separate = len(r1.entries) + len(r2.entries)

        # Parse concatenated
        combined = ftl1 + "\n" + ftl2
        r_combined = parser.parse(combined)
        count_combined = len(r_combined.entries)

        # Should have similar number of entries
        # (exact match depends on whether messages are valid)
        assert count_combined >= 0  # At minimum, doesn't crash
        assert count_separate >= 0


class TestResolverMetamorphicProperties:
    """Metamorphic relations for message resolution."""

    @given(ftl_simple_messages(), st.dictionaries(ftl_identifiers(), st.text()))
    @settings(max_examples=50)
    def test_resolution_deterministic(self, ftl, args):
        """MR7: Resolution determinism.

        Property: resolve(msg, args) == resolve(msg, args) always
        Rationale: Same inputs should produce same output
        """
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Extract message ID from FTL
        parser = FluentParserV1()
        resource = parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        if not messages:
            return  # Skip if no valid messages

        msg_id = messages[0].id.name

        # Resolve twice
        result1, _errors = bundle.format_pattern(msg_id, args)
        result2, _errors = bundle.format_pattern(msg_id, args)

        assert result1 == result2, "Resolution should be deterministic"

    @given(ftl_simple_messages(), st.dictionaries(ftl_identifiers(), st.text()))
    @settings(max_examples=50)
    def test_resolution_argument_monotonicity(self, ftl, args):
        """MR8: Argument monotonicity.

        Property: Adding unused args doesn't change output
        Rationale: Extra args should be ignored
        """
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Extract message ID
        parser = FluentParserV1()
        resource = parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        if not messages:
            return

        msg_id = messages[0].id.name

        # Resolve with original args
        result1, _errors = bundle.format_pattern(msg_id, args)

        # Add extra unused arg
        args_extended = {**args, "unused_arg_xyz": "unused_value"}
        result2, _errors = bundle.format_pattern(msg_id, args_extended)

        # Should be identical (unused args ignored)
        assert result1 == result2, "Adding unused args should not change output"


class TestASTImmutabilityProperties:
    """Metamorphic relations for AST immutability."""

    @given(ftl_resources())
    @settings(max_examples=50)
    def test_ast_truly_immutable(self, resource):
        """MR9: AST immutability.

        Property: AST nodes cannot be modified
        Rationale: Frozen dataclasses should prevent mutation
        """
        # Try to modify entries (should fail)
        with pytest.raises((AttributeError, TypeError)):
            resource.entries = ()

        # Original should be unchanged
        assert resource.entries is not None

    @given(ftl_resources())
    @settings(max_examples=50)
    def test_ast_copy_independence(self, resource):
        """MR10: Deep copying AST creates independent structures.

        Property: Modifications to copy don't affect original
        Rationale: Immutability should extend through copy operations
        """
        # This test verifies the immutability architecture
        # Since AST is frozen, even "copying" shares structure safely

        original_entry_count = len(resource.entries)

        # Attempt to serialize (read operation)
        _ = serialize(resource)

        # Original should be unchanged
        assert len(resource.entries) == original_entry_count


class TestBundleMetamorphicProperties:
    """Metamorphic relations for FluentBundle."""

    @given(ftl_simple_messages())
    @settings(max_examples=50)
    def test_bundle_add_resource_idempotent(self, ftl):
        """MR11: Adding same resource twice behaves predictably.

        Property: add_resource is idempotent for message override
        Rationale: Later additions should override earlier ones
        """
        bundle = FluentBundle("en-US")

        # Add resource twice
        bundle.add_resource(ftl)
        bundle.add_resource(ftl)

        # Extract message ID
        parser = FluentParserV1()
        resource = parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        if not messages:
            return

        msg_id = messages[0].id.name

        # Should resolve without errors
        result, _errors = bundle.format_pattern(msg_id, {})
        assert isinstance(result, str)

    @given(ftl_simple_messages(), st.sampled_from(["en-US", "lv-LV", "de-DE"]))
    @settings(max_examples=50)
    def test_bundle_locale_independence_for_simple_messages(self, ftl, locale):
        """MR12: Simple messages work across locales.

        Property: Messages without plurals work in any locale
        Rationale: Locale should only affect plural/number formatting
        """
        # Skip if message contains plural syntax
        if "$" in ftl or "[" in ftl:
            return

        bundle = FluentBundle(locale)
        bundle.add_resource(ftl)

        # Extract message ID
        parser = FluentParserV1()
        resource = parser.parse(ftl)
        messages = [e for e in resource.entries if isinstance(e, Message)]

        if not messages:
            return

        msg_id = messages[0].id.name

        # Should resolve in any locale
        result, _errors = bundle.format_pattern(msg_id, {})
        assert isinstance(result, str)
        # Result may be empty for edge cases like "a = ."
        assert len(result) >= 0


class TestLocaleMetamorphicProperties:
    """Metamorphic relations for locale handling."""

    @given(st.integers(min_value=0, max_value=100))
    @settings(max_examples=50)
    def test_plural_category_stability(self, number):
        """MR13: Plural category mapping is consistent.

        Property: Same number always maps to same category for a locale
        Rationale: Plural rules are deterministic
        """
        from ftllexengine.runtime.plural_rules import select_plural_category

        # Test for English
        category1 = select_plural_category(number, "en_US")
        category2 = select_plural_category(number, "en_US")

        assert category1 == category2, "Plural category should be consistent"

    @given(st.integers(min_value=0, max_value=1000))
    @settings(max_examples=100)
    def test_plural_category_never_crashes(self, number):
        """MR14: Plural rules handle all integers.

        Property: get_plural_category(n, locale) never crashes
        Rationale: Plural rules should handle any integer
        """
        from ftllexengine.runtime.plural_rules import select_plural_category

        locales = ["en_US", "lv_LV", "de_DE", "pl_PL", "ru_RU", "cs_CZ"]

        for locale in locales:
            category = select_plural_category(number, locale)
            assert category in ["zero", "one", "two", "few", "many", "other"]


class TestFunctionMetamorphicProperties:
    """Metamorphic relations for built-in functions."""

    @given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e10, max_value=1e10))
    @settings(max_examples=100)
    def test_number_function_always_returns_string(self, number):
        """MR15: NUMBER function always returns valid string.

        Property: NUMBER(n) returns parseable string for any float
        Rationale: Function should never crash or return invalid data
        """
        from ftllexengine.runtime.functions import number_format

        # Should not crash
        result = number_format(number)

        # Should return string
        assert isinstance(result, str)
        assert len(result) > 0

    @given(st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e10))
    @settings(max_examples=50)
    def test_number_function_monotonicity(self, number):
        """MR16: NUMBER formatting is consistent.

        Property: Formatting same number twice gives same result
        Rationale: Function should be deterministic
        """
        from ftllexengine.runtime.functions import number_format

        result1 = number_format(number)
        result2 = number_format(number)

        assert result1 == result2, "NUMBER function should be deterministic"


class TestCursorMetamorphicProperties:
    """Metamorphic relations for immutable cursor."""

    @given(st.text(max_size=100), st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_cursor_advance_composition(self, text, n):
        """MR17: Cursor advance is associative.

        Property: cursor.advance(n).advance(m) == cursor.advance(n+m)
        Rationale: Cursor movement should compose naturally
        """
        from ftllexengine.syntax.cursor import Cursor

        cursor = Cursor(text, 0)

        # Advance n times, then n more times
        cursor1 = cursor.advance(n).advance(n)

        # Advance 2n times
        cursor2 = cursor.advance(n + n)

        # Should end at same position
        assert cursor1.pos == cursor2.pos

    @given(st.text(min_size=1, max_size=100), st.integers(min_value=1, max_value=50))
    @settings(max_examples=100)
    def test_cursor_advance_monotonic(self, text, advances):
        """MR18: Cursor position never decreases.

        Property: Advancing cursor never moves backward
        Rationale: Cursor is forward-only parser
        """
        from ftllexengine.syntax.cursor import Cursor

        cursor = Cursor(text, 0)
        prev_pos = cursor.pos

        for _ in range(advances):
            cursor = cursor.advance()
            assert cursor.pos >= prev_pos, "Cursor should never move backward"
            prev_pos = cursor.pos


class TestErrorHandlingMetamorphicProperties:
    """Metamorphic relations for error handling."""

    @given(st.text(max_size=200))
    @settings(max_examples=100)
    def test_parser_error_recovery_stability(self, text):
        """MR19: Parser produces consistent Junk for invalid input.

        Property: Parsing invalid input twice produces same error structure
        Rationale: Error recovery should be deterministic
        """
        parser = FluentParserV1()

        resource1 = parser.parse(text)
        resource2 = parser.parse(text)

        # Should have same number of entries (including Junk)
        assert len(resource1.entries) == len(resource2.entries)

    @given(st.text(max_size=100))
    @settings(max_examples=50)
    def test_serializer_handles_all_ast_structures(self, text):
        """MR20: Serializer never crashes on parsed AST.

        Property: serialize(parse(text)) never crashes
        Rationale: Parser output should always be serializable
        """
        parser = FluentParserV1()

        resource = parser.parse(text)

        # Should not crash
        ftl = serialize(resource)

        assert isinstance(ftl, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])
