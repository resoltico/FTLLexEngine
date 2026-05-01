from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import atheris
from fuzz_builtins_support import (
    _DATE_STYLES,
    _MAX_TIMESTAMP,
    BuiltinsFuzzError,
    _domain,
    _pick_locale,
)

from ftllexengine.runtime.functions import datetime_format


def _pattern_datetime_styles(fdp: atheris.FuzzedDataProvider) -> None:
    """DATETIME with all style combinations."""
    locale = _pick_locale(fdp)
    # Safe timestamp range
    timestamp = fdp.ConsumeFloat() % _MAX_TIMESTAMP
    if timestamp < 0:
        timestamp = abs(timestamp)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    date_style = fdp.PickValueInList(list(_DATE_STYLES))
    use_time = fdp.ConsumeBool()
    time_style = fdp.PickValueInList(list(_DATE_STYLES)) if use_time else None

    _domain.datetime_calls += 1
    result = datetime_format(
        dt, locale,
        date_style=date_style,
        time_style=time_style,
    )

    # Invariant: result must be non-empty string
    if not isinstance(result, str) or not result:
        msg = (
            f"datetime_format returned empty/non-str: {result!r} "
            f"for locale={locale}, date_style={date_style}"
        )
        raise BuiltinsFuzzError(msg)

def _pattern_datetime_edges(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge timestamps and timezone variations."""
    locale = _pick_locale(fdp)

    # Edge timestamps
    edge_timestamps = [
        0.0,             # Unix epoch
        86400.0,         # One day
        -86400.0,        # Before epoch
        946684800.0,     # Y2K
        _MAX_TIMESTAMP,  # Max safe
    ]
    timestamp = fdp.PickValueInList(edge_timestamps)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    # Test with different timezone offsets
    if fdp.ConsumeBool():
        offset_hours = fdp.ConsumeIntInRange(-12, 14)
        tz = timezone(timedelta(hours=offset_hours))
        dt = dt.astimezone(tz)

    _domain.datetime_calls += 1
    datetime_format(
        dt, locale,
        date_style=fdp.PickValueInList(list(_DATE_STYLES)),
        time_style=fdp.PickValueInList(list(_DATE_STYLES)) if fdp.ConsumeBool() else None,
    )

def _pattern_datetime_timezone_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress-test timezone handling with extreme offsets and DST boundaries.

    Tests the DATETIME function with timezone offsets at the edges of
    the valid range, timestamps near DST transitions, and unusual
    UTC offset values.
    """
    locale = _pick_locale(fdp)

    # Base timestamp: mix of safe values and edge cases
    base_timestamps = [
        0.0,              # Epoch
        1647302400.0,     # March 2022 (DST transition period)
        1667091600.0,     # Nov 2022 (DST fall-back period)
        946684800.0,      # Y2K
        1704067200.0,     # 2024-01-01
        86400.0 * 365,    # One year
    ]
    timestamp = fdp.PickValueInList(base_timestamps)

    # Add fuzzed offset to push near boundaries
    offset_seconds = fdp.ConsumeIntInRange(-43200, 43200)

    try:
        # Create with extreme timezone offset (±12h in 15min increments)
        offset_minutes = fdp.ConsumeIntInRange(-720, 840)
        tz = timezone(timedelta(minutes=offset_minutes))
        dt = datetime.fromtimestamp(timestamp + offset_seconds, tz=tz)
    except (OSError, OverflowError, ValueError):
        return

    _domain.datetime_calls += 1
    result = datetime_format(
        dt, locale,
        date_style=fdp.PickValueInList(list(_DATE_STYLES)),
        time_style=fdp.PickValueInList(list(_DATE_STYLES)) if fdp.ConsumeBool() else None,
    )

    if not isinstance(result, str) or not result:
        msg = f"datetime_format returned empty for tz offset {offset_minutes}min"
        raise BuiltinsFuzzError(msg)
