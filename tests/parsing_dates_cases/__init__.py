"""Tests for date and datetime parsing functions.

Core parsing tests, internal function edge cases, tokenizer, separator
extraction, BabelImportError paths, datetime ordering, and property-based
roundtrip tests for parse_date() and parse_datetime().

Functions return tuple[value, errors]:
- parse_date() returns tuple[date | None, list[FluentParseError]]
- parse_datetime() returns tuple[datetime | None, list[FluentParseError]]
- Functions never raise exceptions; errors returned in list

Python 3.13+.
"""

from __future__ import annotations

import builtins
import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from babel import Locale
from hypothesis import event, given
from hypothesis import strategies as st

import ftllexengine.core.babel_compat as _bc
from ftllexengine.parsing.dates import (
    _babel_to_strptime,
    _extract_datetime_separator,
    _get_date_patterns,
    _get_datetime_patterns,
    _preprocess_datetime_input,
    _tokenize_babel_pattern,
    parse_date,
    parse_datetime,
)

__all__ = [
    "UTC",
    "Locale",
    "MagicMock",
    "Mock",
    "_babel_to_strptime",
    "_bc",
    "_extract_datetime_separator",
    "_get_date_patterns",
    "_get_datetime_patterns",
    "_preprocess_datetime_input",
    "_tokenize_babel_pattern",
    "builtins",
    "date",
    "datetime",
    "event",
    "given",
    "parse_date",
    "parse_datetime",
    "patch",
    "pytest",
    "st",
    "sys",
]
