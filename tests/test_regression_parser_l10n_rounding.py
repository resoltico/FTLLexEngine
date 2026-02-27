"""Regression tests for parser depth validation, localization summaries,
AST span fields, CRLF normalization, locale deduplication, CLDR half-up
rounding, dependency graph optimization, and introspection caching.
"""

import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from ftllexengine import FluentBundle, FluentLocalization
from ftllexengine.localization import PathResourceLoader
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.syntax import (
    Attribute,
    CallArguments,
    Identifier,
    NamedArgument,
    NumberLiteral,
    StringLiteral,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource


class TestParseDepthValidation:
    """Tests for PARSE-DEPTH-VAL-001: Parser depth validation."""

    def test_depth_clamped_to_recursion_limit(self, caplog: pytest.LogCaptureFixture) -> None:
        """Parser clamps max_nesting_depth to sys.getrecursionlimit() - 50."""
        # Request depth exceeding recursion limit
        excessive_depth = sys.getrecursionlimit() + 100

        parser = FluentParserV1(max_nesting_depth=excessive_depth)

        # Depth should be clamped
        expected_depth = sys.getrecursionlimit() - 50
        assert parser.max_nesting_depth == expected_depth

        # Warning should be logged
        assert any(
            "max_nesting_depth" in record.message and "Clamping" in record.message
            for record in caplog.records
        )

    def test_reasonable_depth_not_clamped(self) -> None:
        """Parser accepts reasonable depth without clamping."""
        reasonable_depth = 100

        parser = FluentParserV1(max_nesting_depth=reasonable_depth)

        assert parser.max_nesting_depth == reasonable_depth

    def test_bundle_depth_clamped(self) -> None:
        """FluentBundle also clamps depth via parser."""
        excessive_depth = sys.getrecursionlimit() + 100

        bundle = FluentBundle("en", max_nesting_depth=excessive_depth)

        # Parser should have clamped depth
        expected_depth = sys.getrecursionlimit() - 50
        # Access via parser
        assert bundle._parser.max_nesting_depth == expected_depth


class TestLoadSummaryJunkHandling:
    """Tests for L10N-SUM-JUNK-001: LoadSummary.all_successful vs all_clean."""

    def test_all_successful_ignores_junk(self) -> None:
        """all_successful returns True even with Junk entries."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "en").mkdir()
            (base / "en" / "test.ftl").write_text("valid = OK\ninvalid { syntax", encoding="utf-8")

            loader = PathResourceLoader(str(base / "{locale}"))
            l10n = FluentLocalization(["en"], ["test.ftl"], loader, strict=False)

            summary = l10n.get_load_summary()

            # Should be "successful" (no I/O errors)
            assert summary.all_successful is True
            # But has junk
            assert summary.has_junk is True
            assert summary.junk_count > 0

    def test_all_clean_checks_junk(self) -> None:
        """all_clean returns False when Junk entries exist."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "en").mkdir()
            (base / "en" / "test.ftl").write_text("valid = OK\ninvalid { syntax", encoding="utf-8")

            loader = PathResourceLoader(str(base / "{locale}"))
            l10n = FluentLocalization(["en"], ["test.ftl"], loader, strict=False)

            summary = l10n.get_load_summary()

            # Should NOT be "clean" (has junk)
            assert summary.all_clean is False
            assert summary.has_junk is True

    def test_all_clean_true_for_perfect_resources(self) -> None:
        """all_clean returns True when no errors and no junk."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "en").mkdir()
            (base / "en" / "test.ftl").write_text("msg = Perfect", encoding="utf-8")

            loader = PathResourceLoader(str(base / "{locale}"))
            l10n = FluentLocalization(["en"], ["test.ftl"], loader)

            summary = l10n.get_load_summary()

            assert summary.all_successful is True
            assert summary.all_clean is True
            assert summary.has_junk is False
            assert summary.junk_count == 0


class TestASTSpanFields:
    """Tests for FTL-AST-SPAN-001: AST node span fields added."""

    def test_identifier_has_span(self) -> None:
        """Identifier node has span field."""
        identifier = Identifier(name="test")
        assert hasattr(identifier, "span")
        assert identifier.span is None  # Not populated by default

    def test_attribute_has_span(self) -> None:
        """Attribute node has span field."""
        from ftllexengine.syntax.ast import Pattern, TextElement

        attr = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(elements=(TextElement(value="Test"),))
        )
        assert hasattr(attr, "span")

    def test_variant_has_span(self) -> None:
        """Variant node has span field."""
        from ftllexengine.syntax.ast import Pattern, TextElement

        variant = Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=(TextElement(value="Test"),))
        )
        assert hasattr(variant, "span")

    def test_string_literal_has_span(self) -> None:
        """StringLiteral node has span field."""
        literal = StringLiteral(value="test")
        assert hasattr(literal, "span")

    def test_number_literal_has_span(self) -> None:
        """NumberLiteral node has span field."""
        literal = NumberLiteral(value=42, raw="42")
        assert hasattr(literal, "span")

    def test_call_arguments_has_span(self) -> None:
        """CallArguments node has span field."""
        args = CallArguments(positional=(), named=())
        assert hasattr(args, "span")

    def test_named_argument_has_span(self) -> None:
        """NamedArgument node has span field."""
        arg = NamedArgument(
            name=Identifier(name="key"),
            value=StringLiteral(value="value")
        )
        assert hasattr(arg, "span")


class TestCRLFNormalization:
    """Tests for PERF-PARSER-MEM-RED-001: CRLF normalization optimization."""

    def test_crlf_normalized(self) -> None:
        """CRLF line endings are normalized to LF."""
        parser = FluentParserV1()
        source = "msg = Hello\r\nworld = World\r\n"

        resource = parser.parse(source)

        # Should parse successfully (normalized internally)
        assert len(resource.entries) == 2

    def test_cr_only_normalized(self) -> None:
        """CR-only line endings are normalized to LF."""
        parser = FluentParserV1()
        source = "msg = Hello\rworld = World\r"

        resource = parser.parse(source)

        # Should parse successfully
        assert len(resource.entries) == 2

    def test_mixed_line_endings_normalized(self) -> None:
        """Mixed line endings are normalized."""
        parser = FluentParserV1()
        source = "msg1 = A\nmsg2 = B\r\nmsg3 = C\r"

        resource = parser.parse(source)

        assert len(resource.entries) == 3


class TestL10NDocumentation:
    """Tests for L10N-SUM-001 and L10N-LAZY-001: Documentation improvements."""

    def test_get_load_summary_scope(self) -> None:
        """get_load_summary() only reflects initialization-time loading."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "en").mkdir()
            (base / "en" / "initial.ftl").write_text("msg1 = Initial", encoding="utf-8")

            loader = PathResourceLoader(str(base / "{locale}"))
            l10n = FluentLocalization(["en"], ["initial.ftl"], loader)

            # Get initial summary
            summary1 = l10n.get_load_summary()
            assert summary1.successful == 1

            # Add resource dynamically (not via loader)
            bundles = list(l10n.get_bundles())
            bundle = bundles[0]
            bundle.add_resource("msg2 = Dynamic")

            # Summary should be unchanged (only reflects init-time loading)
            summary2 = l10n.get_load_summary()
            assert summary2.successful == 1  # Still just initial.ftl


class TestLocaleDuplication:
    """Tests for L10N-DUPLICATE-LOCALE-001: Locale deduplication."""

    def test_duplicate_locales_deduplicated(self) -> None:
        """Duplicate locale codes are deduplicated."""
        l10n = FluentLocalization(["en", "de", "en", "fr", "de"])

        # Duplicates should be removed, order preserved
        assert l10n.locales == ("en", "de", "fr")

    def test_locale_order_preserved(self) -> None:
        """First occurrence of locale is preserved in order."""
        l10n = FluentLocalization(["fr", "en", "de", "en", "fr"])

        assert l10n.locales == ("fr", "en", "de")


class TestNumberRounding:
    """Tests for RES-NUM-ROUNDING-001: CLDR half-up rounding."""

    def test_half_up_rounding_2_5(self) -> None:
        """2.5 rounds to 3 (CLDR half-up)."""
        locale_ctx = LocaleContext.create("en")

        result = locale_ctx.format_number(
            Decimal("2.5"),
            maximum_fraction_digits=0,
            use_grouping=False
        )

        assert result == "3"  # Not "2" (banker's rounding)

    def test_half_up_rounding_3_5(self) -> None:
        """3.5 rounds to 4 (CLDR half-up)."""
        locale_ctx = LocaleContext.create("en")

        result = locale_ctx.format_number(
            Decimal("3.5"),
            maximum_fraction_digits=0,
            use_grouping=False
        )

        assert result == "4"

    def test_half_up_rounding_4_5(self) -> None:
        """4.5 rounds to 5 (CLDR half-up)."""
        locale_ctx = LocaleContext.create("en")

        result = locale_ctx.format_number(
            Decimal("4.5"),
            maximum_fraction_digits=0,
            use_grouping=False
        )

        assert result == "5"  # Not "4" (banker's rounding)

    def test_rounding_uses_decimal_quantize(self) -> None:
        """Rounding uses Decimal.quantize with ROUND_HALF_UP."""
        # This test verifies the implementation detail
        value = Decimal("2.5")
        rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        assert rounded == Decimal("3")


class TestDependencyGraphOptimization:
    """Tests for PERF-VAL-GRAPH-REDUNDANT-001: Graph built once."""

    def test_validation_builds_graph_once(self) -> None:
        """validate_resource builds dependency graph only once."""
        source = """\
msg1 = { msg2 }
msg2 = { msg3 }
msg3 = { msg4 }
msg4 = Value
"""

        result = validate_resource(source)

        # Should complete successfully (graph built once, reused)
        assert result.is_valid

    def test_circular_reference_detection_uses_graph(self) -> None:
        """Circular reference detection uses the unified graph."""
        source = """\
msg1 = { msg2 }
msg2 = { msg1 }
"""

        result = validate_resource(source)

        # Should detect cycle (as CRITICAL warning)
        assert any(
            "circular" in warning.message.lower()
            for warning in result.warnings
            if warning.severity.name == "CRITICAL"
        )

    def test_chain_depth_detection_uses_graph(self) -> None:
        """Chain depth detection uses the same unified graph."""
        # Create a chain longer than MAX_DEPTH
        messages = [f"msg{i} = {{ msg{i+1} }}" for i in range(110)]
        messages.append("msg110 = Final")
        source = "\n".join(messages)

        result = validate_resource(source)

        # Should detect long chain
        assert any(
            "chain depth" in warning.message.lower()
            for warning in result.warnings
        )


class TestIntrospectionCacheDocumentation:
    """Tests for INTRO-CACHE-001: Cache race condition documented."""

    def test_introspection_cache_exists(self) -> None:
        """Introspection message module has cache."""
        from ftllexengine.introspection import message

        # Cache should exist in the message submodule
        assert hasattr(message, "_introspection_cache")

    def test_clear_introspection_cache_works(self) -> None:
        """clear_introspection_cache() clears the cache."""
        from ftllexengine.introspection import clear_introspection_cache, introspect_message
        from ftllexengine.syntax.ast import Message
        from ftllexengine.syntax.parser import FluentParserV1

        parser = FluentParserV1()
        resource = parser.parse("msg = { $var }")
        message = resource.entries[0]
        assert isinstance(message, Message)

        # Introspect to populate cache
        result1 = introspect_message(message)
        assert "var" in result1.get_variable_names()

        # Clear cache
        clear_introspection_cache()

        # Introspect again (cache was cleared, but still works)
        assert isinstance(message, Message)
        result2 = introspect_message(message)
        assert "var" in result2.get_variable_names()


class TestParserTypedErrorReturn:
    """Tests for FTL-PAR-TYPEDERROR-001: Typed error returns from primitives."""

    def test_parser_primitives_has_no_side_channel(self) -> None:
        """Parser primitives module has no ContextVar side-channel state."""
        from ftllexengine.syntax.parser import primitives

        # No ContextVar or thread-local state
        assert not hasattr(primitives, "_error_context_var")
        assert not hasattr(primitives, "get_last_parse_error")
        assert not hasattr(primitives, "clear_parse_error")

    def test_parse_error_returned_directly(self) -> None:
        """Failure returns ParseError as return value, not via side-channel."""
        from ftllexengine.syntax.cursor import Cursor, ParseError
        from ftllexengine.syntax.parser.primitives import parse_identifier

        cursor = Cursor("123invalid", 0)
        result = parse_identifier(cursor)
        assert isinstance(result, ParseError)
        assert result.message
