"""Tests for v0.95.0 issue resolutions.

Covers:
- ARCH-RWLOCK-DEAD-004: RWLock write-to-read lock downgrading
- API-CURR-TYPE-003: CURRENCY returns FluentNumber
- FTL-B-001: Identifier and Attribute spans in parser
- FTL-D-001: Message attributes in function arguments
- DOCS-CACHE-WEIGHT-006: IntegrityCache docstring accuracy
- DEBT-PLURAL-ROUND-005: Explicit rounding mode in plural rules
- FTL-C-001: StringLiteral.guard() method
"""

from __future__ import annotations

import inspect
import threading
from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.rwlock import RWLock
from ftllexengine.syntax.ast import (
    Message,
    NumberLiteral,
    Span,
    StringLiteral,
)
from ftllexengine.syntax.parser import FluentParserV1

# ---------------------------------------------------------------------------
# ARCH-RWLOCK-DEAD-004: Write-to-read lock downgrading
# ---------------------------------------------------------------------------


class TestRWLockWriteToReadDowngrade:
    """Write lock holder can acquire nested read locks without deadlock."""

    def test_write_then_read_does_not_deadlock(self) -> None:
        """Thread holding write lock can acquire read lock."""
        lock = RWLock()
        read_acquired = False

        with lock.write(), lock.read():
            read_acquired = True

        assert read_acquired

    def test_multiple_nested_reads_under_write(self) -> None:
        """Multiple nested read acquisitions under write lock."""
        lock = RWLock()
        count = 0

        with lock.write(), lock.read():
            count += 1
            with lock.read():
                count += 1

        assert count == 2

    def test_write_release_converts_held_reads(self) -> None:
        """After write release, writer-held reads become regular reads."""
        lock = RWLock()
        result: list[str] = []
        barrier = threading.Barrier(2, timeout=5)

        def writer() -> None:
            with lock.write(), lock.read():
                result.append("write+read")
            result.append("writer_done")
            barrier.wait()

        def reader() -> None:
            barrier.wait()
            with lock.read():
                result.append("reader")

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert "write+read" in result
        assert "writer_done" in result
        assert "reader" in result

    def test_reentrant_write_with_read_downgrade(self) -> None:
        """Reentrant write lock combined with read downgrade."""
        lock = RWLock()
        acquired = False

        with lock.write(), lock.write(), lock.read():
            acquired = True

        assert acquired


# ---------------------------------------------------------------------------
# API-CURR-TYPE-003: CURRENCY returns FluentNumber
# ---------------------------------------------------------------------------


class TestCurrencyReturnsFluentNumber:
    """CURRENCY built-in returns FluentNumber for selector compatibility."""

    @pytest.fixture(autouse=True)
    def _skip_without_babel(self) -> None:
        pytest.importorskip("babel")

    def test_currency_format_returns_fluent_number(self) -> None:
        """currency_format returns FluentNumber, not str."""
        from ftllexengine.runtime.function_bridge import FluentNumber  # noqa: PLC0415
        from ftllexengine.runtime.functions import currency_format  # noqa: PLC0415

        result = currency_format(123.45, "en-US", currency="USD")
        assert isinstance(result, FluentNumber)

    def test_currency_format_has_precision(self) -> None:
        """FluentNumber from CURRENCY has correct precision."""
        from ftllexengine.runtime.functions import currency_format  # noqa: PLC0415

        result = currency_format(123.45, "en-US", currency="USD")
        assert result.precision == 2

    def test_currency_format_jpy_zero_decimals(self) -> None:
        """JPY has zero decimal places per ISO 4217."""
        from ftllexengine.runtime.functions import currency_format  # noqa: PLC0415

        result = currency_format(12345, "ja-JP", currency="JPY")
        assert result.precision == 0

    def test_currency_format_bhd_three_decimals(self) -> None:
        """BHD has three decimal places per ISO 4217."""
        from ftllexengine.runtime.functions import currency_format  # noqa: PLC0415

        # Use en-US locale to avoid RTL markers in currency symbol
        # that interfere with decimal symbol detection
        result = currency_format(123.456, "en-US", currency="BHD")
        assert result.precision == 3


# ---------------------------------------------------------------------------
# FTL-B-001: Identifier and Attribute spans
# ---------------------------------------------------------------------------


class TestIdentifierAndAttributeSpans:
    """Parser populates span for Identifier and Attribute nodes."""

    def test_message_identifier_has_span(self) -> None:
        """Message identifier has non-None span."""
        parser = FluentParserV1()
        resource = parser.parse("hello = World")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.span is not None
        assert isinstance(msg.id.span, Span)
        assert msg.id.span.start == 0
        assert msg.id.span.end == 5  # "hello" is 5 chars

    def test_attribute_identifier_has_span(self) -> None:
        """Attribute identifier has span."""
        parser = FluentParserV1()
        resource = parser.parse("msg =\n    .attr = Value")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.attributes
        attr = msg.attributes[0]
        assert attr.id.span is not None

    @given(
        name=st.from_regex(r"[a-z][a-z0-9\-]*", fullmatch=True).filter(
            lambda s: len(s) <= 50
        )
    )
    @settings(max_examples=50)
    def test_identifier_span_length_matches_name(self, name: str) -> None:
        """Identifier span length equals identifier string length."""
        parser = FluentParserV1()
        resource = parser.parse(f"{name} = value")
        if resource.entries:
            msg = resource.entries[0]
            if hasattr(msg, "id") and msg.id.span is not None:
                assert msg.id.span.end - msg.id.span.start == len(name)


# ---------------------------------------------------------------------------
# FTL-D-001: Message attributes in function arguments
# ---------------------------------------------------------------------------


class TestMessageAttributeInArguments:
    """Parser accepts message.attribute as function argument."""

    def test_message_reference_with_attribute_in_argument(self) -> None:
        """Message reference with .attr parsed in function call arguments."""
        parser = FluentParserV1()
        source = "msg = { NUMBER(other.attr) }"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # The message should parse without junk
        assert msg.value.elements

    def test_plain_message_reference_in_argument(self) -> None:
        """Plain message reference (no attribute) still works in arguments."""
        parser = FluentParserV1()
        source = "msg = { NUMBER(other) }"
        resource = parser.parse(source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


# ---------------------------------------------------------------------------
# DEBT-PLURAL-ROUND-005: Explicit rounding mode
# ---------------------------------------------------------------------------


class TestPluralRoundingMode:
    """Plural rule uses explicit ROUND_HALF_EVEN."""

    @pytest.fixture(autouse=True)
    def _skip_without_babel(self) -> None:
        pytest.importorskip("babel")

    def test_rounding_mode_is_explicit(self) -> None:
        """Verify quantize call uses ROUND_HALF_EVEN."""
        from ftllexengine.runtime import plural_rules  # noqa: PLC0415

        source = inspect.getsource(plural_rules.select_plural_category)
        assert "ROUND_HALF_EVEN" in source

    def test_bankers_rounding_applied(self) -> None:
        """Banker's rounding: 0.5 rounds to even."""
        # 2.5 should round to 2 (even), not 3
        d = Decimal("2.5")
        result = d.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        assert result == Decimal("2")

        # 3.5 should round to 4 (even)
        d = Decimal("3.5")
        result = d.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        assert result == Decimal("4")


# ---------------------------------------------------------------------------
# FTL-C-001: StringLiteral.guard()
# ---------------------------------------------------------------------------


class TestStringLiteralGuard:
    """StringLiteral has guard() method for type narrowing."""

    def test_guard_returns_true_for_string_literal(self) -> None:
        """guard() returns True for StringLiteral instances."""
        sl = StringLiteral(value="hello")
        assert StringLiteral.guard(sl) is True

    def test_guard_returns_false_for_other_types(self) -> None:
        """guard() returns False for non-StringLiteral objects."""
        nl = NumberLiteral(value=42, raw="42")
        assert StringLiteral.guard(nl) is False
        assert StringLiteral.guard("hello") is False
        assert StringLiteral.guard(42) is False

    def test_guard_consistency_with_number_literal(self) -> None:
        """StringLiteral.guard and NumberLiteral.guard are consistent."""
        sl = StringLiteral(value="test")
        nl = NumberLiteral(value=1, raw="1")

        assert StringLiteral.guard(sl) is True
        assert NumberLiteral.guard(sl) is False
        assert StringLiteral.guard(nl) is False
        assert NumberLiteral.guard(nl) is True


# ---------------------------------------------------------------------------
# DOCS-CACHE-WEIGHT-006: Docstring accuracy
# ---------------------------------------------------------------------------


class TestIntegrityCacheDocstring:
    """IntegrityCache docstring matches implementation."""

    def test_docstring_mentions_content_based_weight(self) -> None:
        """Docstring describes content-based weight, not fixed 200."""
        docstring = IntegrityCache.__init__.__doc__
        assert docstring is not None
        # Should NOT contain the old incorrect formula
        assert "(len(errors) * 200)" not in docstring
        # Should mention content-based weight
        assert "content-based" in docstring.lower() or "error_weight" in docstring.lower()
