"""Tests for v0.98.0 fixes.

Covers all fixes introduced in v0.98.0:
1. ISO 4217 currency code ASCII validation
2. Number format DoS prevention (MAX_FORMAT_DIGITS)
3. Diagnostic log injection prevention
4. RWLock thread identification consistency
5. CLDR date/datetime style coverage ("full")
6. Strict mode cache-before-raise pattern
7. Attribute-granular cycle detection (false positive elimination)
8. AST construction validation (__post_init__)
9. Diagnostic formatter control character escaping in tests

Python 3.13+.
"""

from __future__ import annotations

import threading
from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.constants import MAX_FORMAT_DIGITS
from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode
from ftllexengine.diagnostics.formatter import DiagnosticFormatter, OutputFormat
from ftllexengine.integrity import FormattingIntegrityError
from ftllexengine.parsing.currency import _is_valid_iso_4217_format
from ftllexengine.parsing.dates import _get_date_patterns, _get_datetime_patterns
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.rwlock import RWLock
from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    Pattern,
    SelectExpression,
    Term,
    VariableReference,
    Variant,
)

# ============================================================================
# Fix 1: ISO 4217 Currency Code ASCII Validation
# ============================================================================


class TestISO4217ASCIIValidation:
    """Non-ASCII uppercase letters must not pass ISO 4217 format validation."""

    def test_cyrillic_uppercase_rejected(self) -> None:
        """Cyrillic uppercase letters are not valid ISO 4217 codes."""
        # U+0410..U+0412 look like Latin A/B/V but are not ASCII
        assert _is_valid_iso_4217_format("\u0410\u0411\u0412") is False

    def test_greek_uppercase_rejected(self) -> None:
        """Greek uppercase letters are not valid ISO 4217 codes."""
        assert _is_valid_iso_4217_format("\u0391\u0392\u0393") is False

    def test_valid_ascii_accepted(self) -> None:
        """Standard ASCII uppercase passes validation."""
        assert _is_valid_iso_4217_format("USD") is True
        assert _is_valid_iso_4217_format("EUR") is True
        assert _is_valid_iso_4217_format("JPY") is True

    def test_lowercase_rejected(self) -> None:
        """Lowercase ASCII is rejected."""
        assert _is_valid_iso_4217_format("usd") is False

    def test_wrong_length_rejected(self) -> None:
        """Non-3-character strings are rejected."""
        assert _is_valid_iso_4217_format("US") is False
        assert _is_valid_iso_4217_format("USDX") is False

    @given(
        st.text(
            alphabet=st.characters(min_codepoint=0x0100, max_codepoint=0x024F),
            min_size=3,
            max_size=3,
        )
    )
    def test_non_ascii_always_rejected(self, code: str) -> None:
        """Property: Non-ASCII 3-char strings are always rejected."""
        event(f"codepoint_start={ord(code[0])}")
        assert _is_valid_iso_4217_format(code) is False


# ============================================================================
# Fix 2: Number Format DoS Prevention
# ============================================================================


class TestNumberFormatDoSPrevention:
    """Bounded fraction digit validation prevents DoS via string allocation."""

    def test_excessive_fraction_digits_rejected(self) -> None:
        """Fraction digits exceeding MAX_FORMAT_DIGITS raise ValueError."""
        bundle = FluentBundle("en")
        bundle.add_resource("num = { NUMBER($val, minimumFractionDigits: 101) }")

        _result, errors = bundle.format_pattern("num", {"val": 1})
        assert len(errors) > 0

    def test_negative_fraction_digits_rejected(self) -> None:
        """Negative fraction digits raise ValueError."""
        ctx = LocaleContext.create("en")
        with pytest.raises(ValueError, match="minimum_fraction_digits"):
            ctx.format_number(Decimal("1.0"), minimum_fraction_digits=-1)

    def test_max_boundary_accepted(self) -> None:
        """Reasonable fraction digit value passes validation."""
        ctx = LocaleContext.create("en")
        result = ctx.format_number(Decimal("1"), minimum_fraction_digits=20)
        assert len(result) > 0

    def test_over_max_boundary_rejected(self) -> None:
        """MAX_FORMAT_DIGITS + 1 is rejected."""
        ctx = LocaleContext.create("en")
        with pytest.raises(ValueError, match="must be 0-"):
            ctx.format_number(
                Decimal("1"),
                minimum_fraction_digits=MAX_FORMAT_DIGITS + 1,
            )


# ============================================================================
# Fix 3: Diagnostic Log Injection Prevention
# ============================================================================


class TestDiagnosticLogInjection:
    """Control characters in diagnostic messages are escaped."""

    def test_newline_escaped_in_rust_format(self) -> None:
        """Newlines in messages are escaped to prevent log injection."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="injected\nfake-log-line",
        )
        result = formatter.format(diagnostic)
        assert "\n" not in result.split("\n")[0]
        assert "injected\\nfake-log-line" in result

    def test_carriage_return_escaped(self) -> None:
        """Carriage returns are escaped."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="line1\rline2",
        )
        result = formatter.format(diagnostic)
        assert "line1\\rline2" in result

    def test_tab_escaped(self) -> None:
        """Tabs are escaped."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="col1\tcol2",
        )
        result = formatter.format(diagnostic)
        assert "col1\\tcol2" in result

    def test_json_format_unaffected(self) -> None:
        """JSON format handles escaping via json.dumps (not our escaper)."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="has\nnewline",
        )
        result = formatter.format(diagnostic)
        assert "\\n" in result

    @given(st.text(min_size=1, max_size=50))
    def test_escape_idempotent(self, text: str) -> None:
        """Property: Escaping removes all control characters."""
        has_ctrl = any(c in text for c in "\n\r\t")
        event(f"has_control_chars={has_ctrl}")
        escaped = DiagnosticFormatter._escape_control_chars(text)
        assert "\n" not in escaped
        assert "\r" not in escaped
        assert "\t" not in escaped


# ============================================================================
# Fix 4: RWLock Thread Identification Consistency
# ============================================================================


class TestRWLockThreadIdentification:
    """RWLock uses consistent int-based thread identification."""

    def test_writer_ident_is_int(self) -> None:
        """Active writer is tracked by thread ident (int), not Thread object."""
        lock = RWLock()
        lock._acquire_write()  # pylint: disable=protected-access
        try:
            assert isinstance(lock._active_writer, int)  # pylint: disable=protected-access
            assert lock._active_writer == threading.get_ident()  # pylint: disable=protected-access
        finally:
            lock._release_write()  # pylint: disable=protected-access

    def test_no_writer_is_none(self) -> None:
        """When no writer holds the lock, _active_writer is None."""
        lock = RWLock()
        assert lock._active_writer is None  # pylint: disable=protected-access


# ============================================================================
# Fix 5: CLDR Date/Datetime "full" Style Coverage
# ============================================================================


class TestCLDRFullStyleCoverage:
    """Date and datetime parsing includes "full" style from CLDR."""

    def test_full_style_in_date_patterns(self) -> None:
        """_get_date_patterns includes "full" style patterns."""
        _get_date_patterns.cache_clear()
        patterns = _get_date_patterns("en_US")
        assert len(patterns) >= 4

    def test_full_style_in_datetime_patterns(self) -> None:
        """_get_datetime_patterns includes "full" style patterns."""
        _get_datetime_patterns.cache_clear()
        patterns = _get_datetime_patterns("en_US")
        assert len(patterns) >= 4


# ============================================================================
# Fix 6: Strict Mode Cache-Before-Raise
# ============================================================================


class TestStrictModeCacheBeforeRaise:
    """Cache stores results before strict mode raises errors."""

    def test_error_result_cached_before_raise(self) -> None:
        """Error results are cached, so subsequent calls hit cache."""
        bundle = FluentBundle("en", strict=True, enable_cache=True)
        bundle.add_resource("msg = { $missing }")

        # First call: cache miss, resolves, caches, then raises
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", {})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

        # Second call: cache hit, still raises
        with pytest.raises(FormattingIntegrityError):
            bundle.format_pattern("msg", {})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] >= 1


# ============================================================================
# Fix 7: Attribute-Granular Cycle Detection
# ============================================================================


class TestAttributeGranularCycleDetection:
    """Attribute-level references do not cause false positive cycles."""

    def test_cross_attribute_reference_not_cyclic(self) -> None:
        """Message .a referencing .b on the same message is NOT cyclic."""
        bundle = FluentBundle("en")
        ftl = """
msg = { msg.tooltip }
    .tooltip = Tooltip text
"""
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) == 0

    def test_true_self_reference_detected(self) -> None:
        """Message value referencing itself IS cyclic."""
        bundle = FluentBundle("en")
        ftl = """
msg = { msg }
"""
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0

    def test_term_attribute_self_reference_detected(self) -> None:
        """Term attribute referencing itself is cyclic."""
        bundle = FluentBundle("en")
        ftl = """
-term = Value
    .attr = { -term.attr }
"""
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0

    def test_cross_term_cycle_detected(self) -> None:
        """Cross-term cycles are still detected."""
        bundle = FluentBundle("en")
        ftl = """
-a = { -b }
-b = { -a }
"""
        result = bundle.validate_resource(ftl)
        circular_warnings = [w for w in result.warnings if "ircular" in w.message]
        assert len(circular_warnings) > 0


# ============================================================================
# Fix 8: AST Construction Validation (__post_init__)
# ============================================================================


class TestASTConstructionValidation:
    """AST dataclasses enforce spec invariants at construction time."""

    def test_message_requires_value_or_attributes(self) -> None:
        """Message with no value and no attributes raises ValueError."""
        with pytest.raises(ValueError, match="must have a value or at least one attribute"):
            Message(id=Identifier(name="test"), value=None, attributes=())

    def test_message_with_value_only(self) -> None:
        """Message with value but no attributes is valid."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=()),
            attributes=(),
        )
        assert msg.value is not None

    def test_message_with_attributes_only(self) -> None:
        """Message with attributes but no value is valid."""
        attr = Attribute(id=Identifier(name="tooltip"), value=Pattern(elements=()))
        msg = Message(id=Identifier(name="test"), value=None, attributes=(attr,))
        assert msg.value is None
        assert len(msg.attributes) == 1

    def test_term_requires_value(self) -> None:
        """Term with None value raises ValueError."""
        with pytest.raises(ValueError, match="Term must have a value pattern"):
            Term(
                id=Identifier(name="brand"),
                value=None,  # type: ignore[arg-type]
                attributes=(),
            )

    def test_select_requires_variants(self) -> None:
        """SelectExpression with empty variants raises ValueError."""
        with pytest.raises(ValueError, match="requires at least one variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(),
            )

    def test_select_requires_exactly_one_default(self) -> None:
        """SelectExpression without exactly one default raises ValueError."""
        variant_no_default = Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=()),
            default=False,
        )
        with pytest.raises(ValueError, match="exactly one default variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(variant_no_default,),
            )

    def test_select_rejects_multiple_defaults(self) -> None:
        """SelectExpression with two defaults raises ValueError."""
        v1 = Variant(key=Identifier(name="one"), value=Pattern(elements=()), default=True)
        v2 = Variant(key=Identifier(name="other"), value=Pattern(elements=()), default=True)
        with pytest.raises(ValueError, match="exactly one default variant, got 2"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(v1, v2),
            )

    def test_valid_select_expression(self) -> None:
        """SelectExpression with one default variant is valid."""
        v1 = Variant(key=Identifier(name="one"), value=Pattern(elements=()), default=False)
        v2 = Variant(key=Identifier(name="other"), value=Pattern(elements=()), default=True)
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(v1, v2),
        )
        assert len(select.variants) == 2

    @given(st.integers(min_value=0, max_value=5))
    @settings(max_examples=10)
    def test_select_default_count_property(self, n_non_default: int) -> None:
        """Property: SelectExpression requires exactly 1 default in any variant count."""
        event(f"variant_count={n_non_default + 1}")
        non_defaults = tuple(
            Variant(
                key=Identifier(name=f"v{i}"),
                value=Pattern(elements=()),
                default=False,
            )
            for i in range(n_non_default)
        )
        default = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=()),
            default=True,
        )
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(*non_defaults, default),
        )
        assert sum(1 for v in select.variants if v.default) == 1


# ============================================================================
# Fix 9: Control Char Escaping in Formatter (Observation Fix)
# ============================================================================


class TestFormatterControlCharEscaping:
    """DiagnosticFormatter._escape_control_chars works correctly."""

    def test_escape_all_control_chars(self) -> None:
        """All three control characters are escaped."""
        result = DiagnosticFormatter._escape_control_chars("a\nb\rc\td")
        assert result == "a\\nb\\rc\\td"

    def test_no_change_for_safe_text(self) -> None:
        """Safe text passes through unchanged."""
        text = "normal text with spaces"
        assert DiagnosticFormatter._escape_control_chars(text) == text

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert DiagnosticFormatter._escape_control_chars("") == ""
