"""Internal helpers for validating explicit security and resource limits.

These helpers centralize the limit contract so parser, runtime, and loader
boundaries do not drift apart. The premise is simple: security limits must be
validated once at the owning boundary and represented consistently everywhere
else.
"""

from __future__ import annotations

from typing import Final, final

__all__ = ["UNLIMITED", "LimitArg", "UnlimitedLimit", "resolve_limit_arg"]


@final
class UnlimitedLimit:
    """Explicit opt-out sentinel for callers that truly want unbounded behavior."""

    __slots__ = ()

    def __repr__(self) -> str:
        """Render the sentinel with its semantic name for debugging and docs."""
        return "UNLIMITED"


UNLIMITED: Final[UnlimitedLimit] = UnlimitedLimit()
"""Canonical explicit opt-out sentinel for security limit configuration."""

type LimitArg = int | UnlimitedLimit | None


def _require_plain_int(value: object, field_name: str) -> int:
    """Reject non-int inputs, including bool, at the configuration boundary."""
    if isinstance(value, bool):
        msg = f"{field_name} must be int, got bool"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def resolve_limit_arg(
    value: LimitArg,
    *,
    field_name: str,
    default: int,
    allow_unlimited: bool = True,
) -> int | None:
    """Resolve one limit argument to a validated integer or ``None`` for unlimited.

    Premise:
        Security limits must fail closed. Invalid negatives and magic zero values
        are rejected instead of silently disabling protection.

    Reason:
        The rest of the system should not have to remember whether ``0`` or
        ``-1`` means "off". Only the explicit ``UNLIMITED`` sentinel may disable
        a limit intentionally.
    """
    if value is None:
        candidate = default
    elif value is UNLIMITED:
        if not allow_unlimited:
            msg = f"{field_name} does not support unlimited mode"
            raise ValueError(msg)
        return None
    else:
        candidate = _require_plain_int(value, field_name)

    if candidate <= 0:
        msg = (
            f"{field_name} must be positive. "
            f"Use UNLIMITED for intentional unbounded operation."
        )
        raise ValueError(msg)
    return candidate
