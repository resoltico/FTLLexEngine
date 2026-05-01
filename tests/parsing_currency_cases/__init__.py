"""Tests for currency parsing: parse_currency(), symbol resolution, CLDR maps.

Property-based tests using Hypothesis cover:
- Roundtrip: format -> parse -> verify for unambiguous/ISO inputs
- Locale resilience: arbitrary locales never crash
- Invalid input: no-digit strings always fail
- Ambiguous resolution: locale-aware symbol disambiguation
- CLDR map integrity: type contracts and coverage invariants

Unit tests cover specification examples and targeted edge cases.

parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]].
Functions never raise exceptions (errors returned in tuple) except
BabelImportError when Babel is not installed.

Python 3.13+.
"""

from __future__ import annotations

import builtins
import re
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from babel import UnknownLocaleError
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import currency as currency_module
from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    parse_currency,
    resolve_ambiguous_symbol,
)
from tests.strategies.currency import (
    ambiguous_currency_inputs,
    invalid_currency_inputs,
    iso_code_currency_inputs,
    unambiguous_currency_inputs,
)

__all__ = [
    "Any",
    "Decimal",
    "MagicMock",
    "UnknownLocaleError",
    "_build_currency_maps_from_cldr",
    "_get_currency_maps",
    "ambiguous_currency_inputs",
    "builtins",
    "currency_module",
    "event",
    "given",
    "invalid_currency_inputs",
    "iso_code_currency_inputs",
    "parse_currency",
    "patch",
    "pytest",
    "re",
    "resolve_ambiguous_symbol",
    "settings",
    "st",
    "unambiguous_currency_inputs",
]
