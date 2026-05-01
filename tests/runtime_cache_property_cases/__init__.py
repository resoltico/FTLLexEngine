"""Property-based (Hypothesis) tests for FormatCache and IntegrityCache.

All classes are marked with @pytest.mark.fuzz and run only via:
    ./scripts/fuzz_hypofuzz.sh --deep
    pytest -m fuzz

Covers:
- IntegrityCache invariants: maxsize enforced, get-after-put, clear, hit/miss counters
- IntegrityCache LRU eviction patterns
- IntegrityCache key handling: locale, attribute, args dict stability
- IntegrityCache robustness: various arg types, duplicate puts, non-negative stats
- IntegrityCache statistics: hit_rate consistency, size matches entry count
- IntegrityCache init parameters stored correctly
- IntegrityCache primitives: all FluentValue types produce valid cache keys
- FormatCache invariants: transparency, isolation, LRU eviction, stats consistency
- FormatCache invalidation: add_resource, add_function
- FormatCache internals: __len__, properties, key uniqueness, attribute isolation
- FormatCache type collision prevention: bool/int, int/Decimal
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.cache_config import CacheConfig

# ============================================================================
# MODULE-LEVEL STRATEGIES (used by IntegrityCache tests)
# ============================================================================

# Strategy for message IDs - use st.from_regex per hypothesis.md
message_ids = st.from_regex(r"[a-z]+", fullmatch=True)

# Strategy for locale codes
locale_codes = st.sampled_from(["en_US", "de_DE", "lv_LV", "fr_FR", "ja_JP"])

# Strategy for attributes - remove arbitrary max_size
attributes = st.one_of(st.none(), st.text(min_size=1))

# Strategy for cache values (result, errors) - remove arbitrary max_size
cache_values: st.SearchStrategy[tuple[str, tuple[()]]] = st.tuples(
    st.text(min_size=0),
    st.just(()),  # Empty error tuple for simplicity
)

# Strategy for message arguments - keep collection bound, remove text max_size
args_strategy = st.one_of(
    st.none(),
    st.dictionaries(
        st.text(min_size=1),
        st.one_of(
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
            st.text(),
        ),
        max_size=5,  # Keep practical bound for dict size
    ),
)

__all__ = [
    "CacheConfig",
    "Decimal",
    "FluentBundle",
    "IntegrityCache",
    "args_strategy",
    "assume",
    "attributes",
    "cache_values",
    "event",
    "given",
    "locale_codes",
    "message_ids",
    "pytest",
    "settings",
    "st",
]
