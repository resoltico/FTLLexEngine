"""Hypothesis property-based tests for syntax.cursor module.

Tests cursor immutability, EOF handling, navigation, and ParseResult/ParseError
properties. Combines targeted property tests with comprehensive contract verification.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for source text - keep max_size for performance
source_text = st.text(
    alphabet=st.characters(blacklist_categories=["Cc"], blacklist_characters=["\x00"]),
    min_size=0,
    max_size=200,  # Keep practical bound for performance
)

# Strategy for positions (will be constrained by source length)
positions = st.integers(min_value=0, max_value=500)

__all__ = [
    "Cursor",
    "ParseError",
    "ParseResult",
    "assume",
    "event",
    "given",
    "positions",
    "pytest",
    "settings",
    "source_text",
    "st",
]
