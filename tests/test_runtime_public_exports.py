"""Tests for public runtime/localization re-export surfaces."""

from __future__ import annotations

from decimal import Decimal

from ftllexengine.localization import CacheAuditLogEntry as LocalizationCacheAuditLogEntry
from ftllexengine.runtime import (
    CacheAuditLogEntry,
    FluentNumber,
    WriteLogEntry,
    fluent_function,
)


def test_runtime_fluent_number_export_is_constructible() -> None:
    """FluentNumber is importable from the public runtime facade."""
    value = FluentNumber(value=Decimal("12.34"), formatted="12.34", precision=2)

    assert value.value == Decimal("12.34")
    assert str(value) == "12.34"


def test_runtime_fluent_function_export_marks_locale_injection() -> None:
    """fluent_function is importable from the public runtime facade."""

    @fluent_function(inject_locale=True)
    def format_amount(value: int, locale_code: str) -> str:
        return f"{value}:{locale_code}"

    assert getattr(format_amount, "_ftl_requires_locale", False) is True


def test_cache_audit_log_entry_public_alias_matches_write_log_entry() -> None:
    """Public audit-log alias resolves to the immutable runtime dataclass."""
    assert CacheAuditLogEntry is WriteLogEntry
    assert LocalizationCacheAuditLogEntry is WriteLogEntry
