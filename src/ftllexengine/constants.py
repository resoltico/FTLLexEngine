"""Shared constants for FTLLexEngine.

This module provides centralized configuration constants used across
syntax and runtime packages. Placing constants here avoids circular
imports and provides a single source of truth.

Constants are grouped by domain:
- Depth limits: Recursion protection for parsing/resolution/serialization
- Cache limits: Memory bounds for caching subsystems
- Input limits: DoS prevention via size constraints
- Parser limits: Token length bounds and lookahead distance

Python 3.13+. Zero external dependencies.
"""

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Depth limits
    "MAX_DEPTH",
    # Cache limits
    "MAX_LOCALE_CACHE_SIZE",
    "DEFAULT_CACHE_SIZE",
    "DEFAULT_MAX_ENTRY_SIZE",
    # Input limits
    "MAX_SOURCE_SIZE",
    "MAX_LOCALE_CODE_LENGTH",
    # Parser limits
    "MAX_LOOKAHEAD_CHARS",
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

# Default maximum entry size in characters (~10KB for typical strings).
# Prevents unbounded memory usage when caching very large formatted results.
# Results exceeding this limit are computed but not cached, protecting against
# scenarios where large variable values produce very large formatted strings
# (e.g., 10MB results cached 1000 times would consume 10GB of memory).
DEFAULT_MAX_ENTRY_SIZE: int = 10_000

# ============================================================================
# INPUT LIMITS
# ============================================================================

# Default maximum source size in characters (10 million characters).
# Python measures string length in characters (code points), not bytes.
# UTF-8 encoding means 1 character = 1-4 bytes, but len(source) counts characters.
# Prevents DoS attacks via unbounded memory allocation from large FTL files.
MAX_SOURCE_SIZE: int = 10 * 1024 * 1024

# Maximum locale code length per BCP 47 / RFC 5646 (35 characters recommended).
# BCP 47 well-formed locale tags are typically <35 characters, including language,
# script, region, and variant subtags (e.g., "zh-Hans-CN-x-private").
# This constant is used by LocaleContext.create() to trigger warnings for unusually
# long locale codes, which may indicate misconfiguration or attack attempts.
# Real-world locale codes: typically 2-16 characters (e.g., "en", "en-US", "zh-Hans-CN").
# FluentBundle accepts locales up to 1000 characters for BCP 47 private-use extensions.
MAX_LOCALE_CODE_LENGTH: int = 35

# ============================================================================
# PARSER LIMITS
# ============================================================================

# Maximum lookahead distance for variant marker detection.
# Used by _is_variant_marker() to distinguish variant keys [x] from literal text.
# Bounded lookahead prevents O(N^2) parsing on pathological inputs.
# 128 characters is ample for any legitimate variant key (identifier + number).
MAX_LOOKAHEAD_CHARS: int = 128

# ----------------------------------------------------------------------------
# Token Length Limits (DoS Prevention)
# ----------------------------------------------------------------------------
# Maximum lengths prevent denial-of-service attacks via extremely long tokens.
# These limits are intentionally generous for legitimate use while blocking abuse.
# Private (not exported) - used only by parser primitives.

# Maximum identifier length (256 chars).
# Real-world identifiers rarely exceed 50 characters. 256 provides ample margin
# while preventing memory exhaustion from million-character "identifiers".
_MAX_IDENTIFIER_LENGTH: int = 256

# Maximum number literal length (1000 chars including sign and decimal point).
# Covers any practical numeric value (Python's arbitrary precision int/float).
# A 1000-digit number is ~3KB and already beyond practical use.
_MAX_NUMBER_LENGTH: int = 1000

# Maximum string literal length (1 million chars).
# FTL strings may contain long text blocks (e.g., legal disclaimers, terms).
# 1M characters (~2-4MB with Unicode) is generous while preventing abuse.
_MAX_STRING_LITERAL_LENGTH: int = 1_000_000

# ============================================================================
# FALLBACK STRINGS
# ============================================================================

# Unified fallback string patterns for error conditions.
# Using consistent patterns helps users identify and debug issues.

# Truly invalid/unknown (e.g., invalid message ID format)
FALLBACK_INVALID: str = "{???}"

# Template patterns for contextual fallbacks (preserve what was expected)
# These are Python format strings - use .format(name=...) or f-string equivalent.
#
# ESCAPING EXPLANATION:
# Python format strings use {} for interpolation, so literal braces need escaping:
#   {{ = literal {
#   }} = literal }
#   {var} = interpolated variable
#
# Examples after .format():
#   "{{{id}}}".format(id="msg")      -> "{msg}"      (message fallback)
#   "{{${name}}}".format(name="x")   -> "{$x}"       (variable fallback)
#   "{{-{name}}}".format(name="term") -> "{-term}"   (term fallback)
#   "{{!{name}}}".format(name="NUM")  -> "{!NUM}"    (function fallback)
#
FALLBACK_MISSING_MESSAGE: str = "{{{id}}}"  # -> {my-message}
FALLBACK_MISSING_VARIABLE: str = "{{${name}}}"  # -> {$username}
FALLBACK_MISSING_TERM: str = "{{-{name}}}"  # -> {-brand}
# Uses "!" prefix (not valid FTL syntax) to visually distinguish function errors
# from message references like {msg}. This intentional deviation from FTL syntax
# makes function errors immediately identifiable in output without ambiguity.
FALLBACK_FUNCTION_ERROR: str = "{{!{name}}}"  # -> {!NUMBER}
