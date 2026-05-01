"""Tests for IntegrityCache hashable key construction, NaN normalization, and
unhashable argument handling.

Covers:
- __init__ parameter validation
- _make_hashable type-tagged conversions (bool/int/Decimal/datetime/date/
  FluentNumber/list/dict/set/tuple) for collision-free cache keys
- Depth limiting to prevent O(N) key computation on adversarial inputs
- _make_key integration and error recovery (RecursionError, TypeError)
- NaN normalization (Decimal) to prevent cache pollution DoS vectors
- Hashable conversion of list/dict/set/tuple args for full cache coverage
- Unhashable argument graceful bypass (skips caching, increments counter)
- Error bloat protection (max_entry_weight, max_errors_per_entry)
- LRU eviction and move-to-end behavior
- Property accessors (size, hits, misses, unhashable_skips, oversize_skips)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, NoReturn

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue

__all__ = [
    "MAX_DEPTH",
    "UTC",
    "Any",
    "Decimal",
    "ErrorCategory",
    "FluentNumber",
    "FluentValue",
    "FrozenFluentError",
    "IntegrityCache",
    "NoReturn",
    "date",
    "datetime",
    "event",
    "example",
    "given",
    "pytest",
    "settings",
    "st",
]
