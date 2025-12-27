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

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Depth limits
    "MAX_DEPTH",
    # Cache limits
    "MAX_LOCALE_CACHE_SIZE",
    "DEFAULT_CACHE_SIZE",
    # Input limits
    "MAX_SOURCE_SIZE",
    # Fallback strings
    "FALLBACK_INVALID",
    "FALLBACK_MISSING_MESSAGE",
    "FALLBACK_MISSING_VARIABLE",
    "FALLBACK_MISSING_TERM",
    "FALLBACK_FUNCTION_ERROR",
]

# ============================================================================
# DEPTH LIMITS
# ============================================================================
#
# ARCHITECTURAL DECISION: Unified vs. Semantic-Specific Limits
#
# FTLLexEngine uses a UNIFIED depth limit (MAX_DEPTH=100) across all subsystems
# rather than subsystem-specific limits. This is intentional:
#
# 1. PARSER (syntax/parser/core.py):
#    - Tracks: Syntactic nesting depth (nested patterns, selectors, attributes)
#    - Purpose: Prevent stack overflow during recursive descent parsing
#    - Example: Deeply nested select expressions { $a -> [x] { $b -> [...] } }
#
# 2. RESOLVER (runtime/resolver.py):
#    - Tracks: Reference resolution depth (message -> term -> message chains)
#    - Purpose: Detect circular references, prevent infinite loops
#    - Example: -term = { -other-term } where -other-term references -term
#
# 3. SERIALIZER (syntax/serializer.py):
#    - Tracks: AST traversal depth during serialization
#    - Purpose: Prevent stack overflow when serializing deeply nested ASTs
#
# 4. VALIDATORS (syntax/validator.py, analysis modules):
#    - Tracks: Validation tree depth during AST analysis
#    - Purpose: Prevent stack overflow during validation passes
#
# WHY UNIFIED?
# - Simplicity: One constant to configure for defense-in-depth
# - Consistency: Same limit across all attack surfaces
# - Sufficient: 100 levels exceeds any legitimate use case
#
# WHY NOT SEMANTIC-SPECIFIC?
# - Complexity: 4+ constants to tune with subtle interactions
# - No practical benefit: Real-world FTL files rarely exceed 10 levels
# - Same failure mode: All subsystems fail-safe on limit breach
#
# The value 100 was chosen empirically:
# - Python default recursion limit: 1000 (ample margin)
# - Legitimate FTL files: typically 1-5 levels, rarely >10
# - Adversarial input: >100 levels is clearly malformed
#
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
