"""Core utilities shared across syntax, parsing, and runtime layers.

This package provides foundational utilities that all higher layers depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- parsing <- runtime

Exports (eager — no Babel dependency, no circular import risk):
    FluentNumber: Formatted number preserving numeric identity and precision
    FluentValue: Union of all Fluent-compatible value types
    make_fluent_number: Public helper for manual FluentNumber construction
    FiscalCalendar: Configuration for fiscal year boundaries
    FiscalDelta: Immutable fiscal period delta for date arithmetic
    FiscalPeriod: Immutable fiscal period identifier
    MonthEndPolicy: Enum for month-end date handling in arithmetic
    fiscal_quarter: Convenience function — fiscal quarter for a date
    fiscal_year: Convenience function — fiscal year for a date
    fiscal_month: Convenience function — fiscal month for a date
    fiscal_year_start: Convenience function — first day of a fiscal year
    fiscal_year_end: Convenience function — last day of a fiscal year
    coerce_tuple: Coerce a non-str Sequence to an immutable tuple
    normalize_optional_decimal_range: None passthrough over require_decimal_range
    normalize_optional_str: None passthrough over require_non_empty_str
    require_date: Validate that a boundary value is a date (not datetime)
    require_datetime: Validate that a boundary value is a datetime
    require_decimal_range: Validate that a boundary Decimal is finite and within a range
    require_fiscal_calendar: Validate that a boundary value is a FiscalCalendar
    require_fiscal_period: Validate that a boundary value is a FiscalPeriod
    require_fluent_number: Validate that a boundary value is a FluentNumber
    require_int: Validate that a boundary value is an integer (no range check)
    require_int_in_range: Validate that a boundary integer is within an inclusive range
    require_non_empty_str: Validate that a boundary value is a non-blank string
    require_non_negative_int: Validate that a boundary value is an int >= 0
    require_positive_int: Validate that a boundary value is a positive integer

Exports (lazy — depth_guard is loaded on first access to break circular import):
    DepthGuard: Context manager for recursion depth limiting
    depth_clamp: Utility function for clamping depth values against recursion limit

    Circular import note: depth_guard imports from ftllexengine.diagnostics, which
    imports from ftllexengine.syntax, which imports from ftllexengine.core.depth_guard.
    Eager import of depth_guard here would create a cycle when ftllexengine.__init__
    triggers core.__init__ loading (via fiscal import) before diagnostics is loaded.
    Lazy loading via __getattr__ defers depth_guard until after all modules are
    initialized, at which point sys.modules contains the complete import graph.

Python 3.14+. No external dependencies.
"""

from typing import TYPE_CHECKING, Any

from .fiscal import (
    FiscalCalendar,
    FiscalDelta,
    FiscalPeriod,
    MonthEndPolicy,
    fiscal_month,
    fiscal_quarter,
    fiscal_year,
    fiscal_year_end,
    fiscal_year_start,
)
from .validators import (
    coerce_tuple,
    normalize_optional_decimal_range,
    normalize_optional_str,
    require_date,
    require_datetime,
    require_decimal_range,
    require_fiscal_calendar,
    require_fiscal_period,
    require_fluent_number,
    require_int,
    require_int_in_range,
    require_non_empty_str,
    require_non_negative_int,
    require_positive_int,
)
from .value_types import FluentNumber, FluentValue, make_fluent_number

if TYPE_CHECKING:
    from .depth_guard import DepthGuard, depth_clamp

__all__ = [
    "DepthGuard",
    "FiscalCalendar",
    "FiscalDelta",
    "FiscalPeriod",
    "FluentNumber",
    "FluentValue",
    "MonthEndPolicy",
    "coerce_tuple",
    "depth_clamp",
    "fiscal_month",
    "fiscal_quarter",
    "fiscal_year",
    "fiscal_year_end",
    "fiscal_year_start",
    "make_fluent_number",
    "normalize_optional_decimal_range",
    "normalize_optional_str",
    "require_date",
    "require_datetime",
    "require_decimal_range",
    "require_fiscal_calendar",
    "require_fiscal_period",
    "require_fluent_number",
    "require_int",
    "require_int_in_range",
    "require_non_empty_str",
    "require_non_negative_int",
    "require_positive_int",
]

_LAZY_DEPTH_GUARD = frozenset({"DepthGuard", "depth_clamp"})


def __getattr__(name: str) -> Any:
    """Lazy-load depth_guard symbols to break the circular import.

    depth_guard imports ftllexengine.diagnostics, which imports ftllexengine.syntax,
    which imports ftllexengine.core.depth_guard. Eager loading here during
    ftllexengine package initialization creates a circular dependency. Deferred
    loading via __getattr__ resolves it: by the time any caller requests DepthGuard
    or depth_clamp, sys.modules already contains the full import graph.
    """
    if name in _LAZY_DEPTH_GUARD:
        from .depth_guard import (  # noqa: PLC0415 - lazy load to break circular import; see module docstring
            DepthGuard,
            depth_clamp,
        )
        globals()["DepthGuard"] = DepthGuard
        globals()["depth_clamp"] = depth_clamp
        return globals()[name]
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
