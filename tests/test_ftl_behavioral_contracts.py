"""Behavioral contract tests for the FTLLexEngine core API.

Verifies fundamental behavioral contracts of parsing, resolution,
validation, and bundle operations — invariants that must hold regardless
of input shape or content. These tests define the observable API
guarantees that all FTLLexEngine consumers can rely on.

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings

from ftllexengine import FluentBundle
from ftllexengine.syntax.ast import Junk, Message
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.parser.primitives import _MAX_IDENTIFIER_LENGTH
from ftllexengine.validation import validate_resource

from .strategies import (
    ftl_chaos_source,
    ftl_simple_messages,
    resolver_mixed_args,
    validation_resource_sources,
)


class TestParserBehavioralContracts:
    """Parser behavioral contracts: invariants for valid and invalid inputs."""

    def test_empty_source_produces_empty_resource(self) -> None:
        """Empty source produces zero entries."""
        parser = FluentParserV1()
        resource = parser.parse("")
        assert len(resource.entries) == 0

    def test_whitespace_only_source_does_not_crash(self) -> None:
        """Whitespace-only source is processed without raising an exception."""
        parser = FluentParserV1()
        resource = parser.parse("   \n\t\n   ")
        assert resource is not None

    def test_single_newline_produces_empty_resource(self) -> None:
        """Single newline is a valid empty source with zero entries."""
        parser = FluentParserV1()
        resource = parser.parse("\n")
        assert len(resource.entries) == 0

    def test_identifier_within_max_length_parses_as_message(self) -> None:
        """Identifier within the length limit produces a valid Message entry."""
        parser = FluentParserV1()
        valid_id = "a" * 200
        resource = parser.parse(f"{valid_id} = Value")
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Message)
        assert entry.id.name == valid_id

    def test_identifier_exceeding_max_length_produces_junk(self) -> None:
        """Identifiers exceeding the length limit are rejected as Junk.

        Denial-of-service prevention: unbounded token scanning is blocked.
        """
        parser = FluentParserV1()
        over_limit_id = "a" * (_MAX_IDENTIFIER_LENGTH + 100)
        resource = parser.parse(f"{over_limit_id} = Value")
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Junk)

    def test_very_long_value_is_preserved_verbatim(self) -> None:
        """Very long message values are not truncated or modified."""
        bundle = FluentBundle("en")
        long_value = "x" * 10000
        bundle.add_resource(f"msg = {long_value}")
        result, errors = bundle.format_pattern("msg")
        assert result == long_value
        assert errors == ()

    def test_message_with_fifty_attributes_parses_fully(self) -> None:
        """Messages with many attributes parse without truncation."""
        parser = FluentParserV1()
        attrs = "\n".join(f"    .attr{i} = Value {i}" for i in range(50))
        source = f"msg = Base\n{attrs}"
        resource = parser.parse(source)
        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert isinstance(entry, Message)
        assert len(entry.attributes) == 50

    def test_nested_placeables_within_depth_limit_resolve(self) -> None:
        """Nested placeables within the depth limit resolve without errors."""
        bundle = FluentBundle("en", max_nesting_depth=10)
        bundle.add_resource("msg = { { { { { $var } } } } }")
        result, errors = bundle.format_pattern("msg", {"var": "value"})
        assert not errors
        assert "value" in result

    def test_comment_only_file_produces_only_comment_entries(self) -> None:
        """Files containing only comments produce only Comment-typed entries."""
        parser = FluentParserV1()
        resource = parser.parse(
            "# Comment 1\n## Group comment\n### Resource comment\n# Another comment\n"
        )
        assert all(
            entry.__class__.__name__ == "Comment"
            for entry in resource.entries
        )

    @given(source=ftl_chaos_source())
    @settings(max_examples=50)
    def test_parser_never_raises_on_any_input(self, source: str) -> None:
        """Property: parser always returns a Resource, never raises an exception."""
        has_crlf = chr(13) in source
        event(f"has_crlf={'crlf' if has_crlf else 'lf_only'}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None

    @given(source=ftl_simple_messages())
    @settings(max_examples=50)
    def test_valid_simple_message_always_produces_message_entry(self, source: str) -> None:
        """Property: valid simple messages always yield at least one Message entry."""
        event(f"source_len_bucket={len(source) // 20 * 20}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1


class TestResolutionBehavioralContracts:
    """Resolution behavioral contracts: format_pattern output invariants."""

    def test_self_referencing_message_produces_errors(self) -> None:
        """Self-referencing message is cycle-detected and produces errors."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { msg }")
        _result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0

    def test_select_with_no_matching_variant_uses_default(self) -> None:
        """Select expression with no matching variant falls through to default."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "msg = { $type ->\n    [a] Option A\n   *[other] Default\n}\n"
        )
        result, _errors = bundle.format_pattern("msg", {"type": "unknown"})
        assert "Default" in result

    def test_missing_variables_produce_errors_and_fallback_text(self) -> None:
        """All missing variables produce per-variable errors and fallback text."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $a } { $b } { $c }")
        result, errors = bundle.format_pattern("msg", {})
        assert len(errors) == 3
        assert "{$a}" in result
        assert "{$b}" in result
        assert "{$c}" in result

    def test_variable_with_none_value_does_not_crash(self) -> None:
        """None variable value is formatted without raising an exception."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Value: { $var }")
        result, errors = bundle.format_pattern("msg", {"var": None})
        assert not errors
        assert "Value:" in result

    def test_term_with_no_matching_variant_uses_default(self) -> None:
        """Term with selector: no match falls back to the default variant."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "-brand = { $case ->\n    [nominative] Firefox\n   *[other] Firefox\n}\n"
            "msg = { -brand }\n"
        )
        result, _errors = bundle.format_pattern("msg")
        assert "Firefox" in result

    @given(args=resolver_mixed_args())
    @settings(max_examples=50)
    def test_format_pattern_always_returns_str_tuple(
        self, args: dict[str, str | int | float]
    ) -> None:
        """Property: format_pattern always returns (str, tuple), never raises."""
        has_numeric = any(isinstance(v, (int, float)) for v in args.values())
        arg_kind = "numeric" if has_numeric else "strings"
        event(f"arg_kind={arg_kind}")
        bundle = FluentBundle("en")
        bundle.add_resource("msg = { $x } and { $y }\n")
        result, errors = bundle.format_pattern("msg", args)
        assert isinstance(result, str)
        assert isinstance(errors, tuple)


class TestValidationBehavioralContracts:
    """Validation behavioral contracts: validate_resource output invariants."""

    def test_empty_source_is_valid(self) -> None:
        """Empty source produces a valid validation result."""
        result = validate_resource("")
        assert result.is_valid

    def test_message_with_only_attributes_is_valid(self) -> None:
        """Message with only attributes and no inline value is valid."""
        result = validate_resource("msg =\n    .attr = Value")
        assert result.error_count == 0

    def test_duplicate_messages_produce_warning(self) -> None:
        """Duplicate message keys produce at least one Duplicate warning."""
        result = validate_resource("msg = First\nmsg = Second\n")
        assert result.warning_count > 0
        assert any("Duplicate" in w.message for w in result.warnings)

    def test_undefined_message_reference_produces_warning(self) -> None:
        """Referencing an undefined message produces an 'undefined' warning."""
        result = validate_resource("msg = { undefined }")
        assert result.warning_count > 0
        assert any("undefined" in w.message.lower() for w in result.warnings)

    def test_undefined_term_reference_produces_warning(self) -> None:
        """Referencing an undefined term produces an 'undefined' warning."""
        result = validate_resource("msg = { -undefined }")
        assert result.warning_count > 0
        assert any("undefined" in w.message.lower() for w in result.warnings)

    @given(source=validation_resource_sources())
    @settings(max_examples=50)
    def test_validate_never_raises(self, source: str) -> None:
        """Property: validate_resource never raises; always returns a ValidationResult."""
        has_refs = "{" in source
        has_attrs = ".attr" in source
        source_kind = "with_refs" if has_refs else "with_attrs" if has_attrs else "plain"
        event(f"source_kind={source_kind}")
        result = validate_resource(source)
        assert result is not None
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.error_count, int)
        assert isinstance(result.warning_count, int)


class TestBundleBehavioralContracts:
    """FluentBundle API behavioral contracts."""

    def test_format_nonexistent_message_returns_fallback(self) -> None:
        """Nonexistent message produces bracketed key fallback with one error."""
        bundle = FluentBundle("en")
        result, errors = bundle.format_pattern("nonexistent")
        assert "{nonexistent}" in result
        assert len(errors) == 1

    def test_format_nonexistent_attribute_returns_non_empty(self) -> None:
        """Nonexistent attribute on existing message returns a non-empty result."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Base value")
        result, _errors = bundle.format_pattern("msg", attribute="nonexistent")
        assert len(result) > 0

    def test_add_empty_resource_produces_no_messages(self) -> None:
        """Adding empty resource produces no junk entries and no messages."""
        bundle = FluentBundle("en")
        junk = bundle.add_resource("")
        assert junk == ()
        assert len(bundle.get_message_ids()) == 0

    def test_multiple_resources_accumulate_all_messages(self) -> None:
        """Messages from all added resources are registered in the bundle."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg1 = First")
        bundle.add_resource("msg2 = Second")
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")

    def test_later_definition_overwrites_earlier_same_key(self) -> None:
        """A later definition of the same key overwrites the earlier definition."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = First")
        bundle.add_resource("msg = Second")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Second"

    def test_static_message_reports_empty_variable_set(self) -> None:
        """Static (non-parametric) message reports no variable names."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Static text")
        info = bundle.introspect_message("msg")
        assert info.get_variable_names() == frozenset()

    def test_select_expression_variables_are_extracted(self) -> None:
        """Variables inside select expressions are included in the variable set."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            "msg = { $count ->\n"
            "    [one] { $name } has one item\n"
            "   *[other] { $name } has { $count } items\n"
            "}\n"
        )
        variables = bundle.get_message_variables("msg")
        assert "count" in variables
        assert "name" in variables


class TestLocaleHandlingContracts:
    """Locale handling behavioral contracts."""

    def test_two_letter_locale_is_accepted(self) -> None:
        """Two-letter locale code is accepted and produces correct output."""
        bundle = FluentBundle("en")
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Hello"

    def test_underscore_separated_locale_is_accepted(self) -> None:
        """Underscore-separated locale code (ll_CC) is accepted."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Hello"

    def test_bcp47_hyphenated_locale_is_accepted(self) -> None:
        """BCP 47 hyphenated locale code (ll-CC) is accepted."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = Hello")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Hello"

    def test_empty_locale_raises_value_error(self) -> None:
        """Empty locale code raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            FluentBundle("")

    def test_locale_with_path_separator_raises_value_error(self) -> None:
        """Locale code containing '/' raises ValueError."""
        with pytest.raises(ValueError, match="Invalid locale code"):
            FluentBundle("en/US")
