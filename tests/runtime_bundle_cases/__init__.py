"""Tests for runtime.bundle: FluentBundle resource loading, formatting, branch coverage."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import Mock, patch

import pytest
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_LENGTH_HARD_LIMIT, MAX_SOURCE_SIZE
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError, ValidationError
from ftllexengine.integrity import FormattingIntegrityError, SyntaxIntegrityError
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.validation.resource import validate_resource

__all__ = [
    "MAX_LOCALE_LENGTH_HARD_LIMIT", "MAX_SOURCE_SIZE", "Any", "CacheConfig",
    "ErrorCategory", "FluentBundle", "FormattingIntegrityError", "FrozenFluentError",
    "FunctionRegistry", "Mock", "SyntaxIntegrityError", "ValidationError",
    "assume", "create_default_registry", "event", "example", "given", "logging",
    "normalize_locale", "patch", "pytest", "st", "validate_resource",
]
