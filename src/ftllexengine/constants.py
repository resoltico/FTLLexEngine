"""Shared constants for FTLLexEngine.

This module provides centralized configuration constants used across
syntax and runtime packages. Placing constants here avoids circular
imports and provides a single source of truth.

Constants are grouped by domain:
- Depth limits: Recursion protection for parsing/resolution/serialization
- Cache limits: Memory bounds for caching subsystems
- Input limits: DoS prevention via size constraints

Python 3.13+. Zero external dependencies.
"""

# ============================================================================
# DEPTH LIMITS
# ============================================================================

# Unified maximum depth for recursion protection.
# Used by: parser (nesting), resolver (message/expression), serializer, validators.
# 100 levels of nesting is almost certainly adversarial or malformed input.
# This limit prevents RecursionError while allowing reasonable nesting.
MAX_DEPTH: int = 100

# ============================================================================
# CACHE LIMITS
# ============================================================================

# Maximum cached LocaleContext instances.
# Prevents unbounded memory growth in multi-locale applications.
# 128 covers typical multi-region applications (major locales + variants).
MAX_LOCALE_CACHE_SIZE: int = 128

# Default maximum cache entries for format results.
# 1000 entries is sufficient for most applications (typical UI has <500 messages).
DEFAULT_CACHE_SIZE: int = 1000

# ============================================================================
# INPUT LIMITS
# ============================================================================

# Default maximum source size in bytes (10 MB).
# Prevents DoS attacks via unbounded memory allocation from large FTL files.
MAX_SOURCE_SIZE: int = 10 * 1024 * 1024

# ============================================================================
# FALLBACK STRINGS
# ============================================================================

# Unified fallback string patterns for error conditions.
# Using consistent patterns helps users identify and debug issues.

# Truly invalid/unknown (e.g., invalid message ID format)
FALLBACK_INVALID: str = "{???}"

# Template patterns for contextual fallbacks (preserve what was expected)
# These are format strings - use .format(name=...) or f-string equivalent
FALLBACK_MISSING_MESSAGE: str = "{{{id}}}"  # e.g., {my-message}
FALLBACK_MISSING_VARIABLE: str = "{{${name}}}"  # e.g., {$username}
FALLBACK_MISSING_TERM: str = "{{-{name}}}"  # e.g., {-brand}
FALLBACK_FUNCTION_ERROR: str = "{{!{name}}}"  # e.g., {!NUMBER}
