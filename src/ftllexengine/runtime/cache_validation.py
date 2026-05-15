"""Constructor-boundary validation for cache configuration primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .cache_events import IntegrityEventSink

__all__ = [
    "validate_optional_debug_fingerprint_key",
    "validate_optional_integrity_event_sink",
]


def validate_optional_integrity_event_sink(value: object) -> IntegrityEventSink | None:
    """Validate the optional structured integrity-event sink boundary."""
    if value is None:
        return None
    record = getattr(value, "record", None)
    if not callable(record):
        msg = (
            "integrity_event_sink must implement a callable record(event) method, "
            f"got {type(value).__name__}"
        )
        raise TypeError(msg)
    return cast("IntegrityEventSink", value)


def validate_optional_debug_fingerprint_key(value: object) -> bytes | None:
    """Validate the optional keyed fingerprint secret boundary."""
    if value is None:
        return None
    if not isinstance(value, bytes):
        msg = f"debug_fingerprint_key must be bytes or None, got {type(value).__name__}"
        raise TypeError(msg)
    if len(value) < 16:
        msg = "debug_fingerprint_key must contain at least 16 bytes"
        raise ValueError(msg)
    return value
