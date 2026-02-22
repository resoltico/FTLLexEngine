"""Shared constants for FTLLexEngine.

This module provides centralized configuration constants used across
syntax and runtime packages. Placing constants here avoids circular
imports and provides a single source of truth.

Constants are grouped by domain:
- Depth limits: Recursion protection for parsing/resolution/serialization
- Cache limits: Memory bounds for caching subsystems
- Input limits: DoS prevention via size constraints
- Parser limits: Token length bounds and lookahead distance
- Fallback strings: Error message templates
- ISO 4217: Currency decimal digit specifications

Python 3.13+. Zero external dependencies.
"""

from types import MappingProxyType

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Depth limits
    "MAX_DEPTH",
    # Cache limits
    "MAX_LOCALE_CACHE_SIZE",
    "MAX_TERRITORY_CACHE_SIZE",
    "MAX_CURRENCY_CACHE_SIZE",
    "DEFAULT_CACHE_SIZE",
    "DEFAULT_MAX_ENTRY_WEIGHT",
    # Input limits
    "MAX_SOURCE_SIZE",
    "MAX_LOCALE_CODE_LENGTH",
    "MAX_LOCALE_LENGTH_HARD_LIMIT",
    # Identifier limit (cross-module: parser primitives and core/identifier_validation)
    "MAX_IDENTIFIER_LENGTH",
    # Format limits
    "MAX_FORMAT_DIGITS",
    # Resolution limits
    "DEFAULT_MAX_EXPANSION_SIZE",
    # Fallback strings
    "FALLBACK_INVALID",
    "FALLBACK_MISSING_MESSAGE",
    "FALLBACK_MISSING_VARIABLE",
    "FALLBACK_MISSING_TERM",
    "FALLBACK_FUNCTION_ERROR",
    # ISO 4217 currency data
    "ISO_4217_DECIMAL_DIGITS",
    "ISO_4217_DEFAULT_DECIMALS",
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

# Maximum cached territory-keyed entries (e.g., territory-to-currency mappings).
# ISO 3166-1 defines ~249 alpha-2 territory codes. 300 provides margin for
# complete coverage without cache thrashing when iterating all territories.
# Distinct from MAX_LOCALE_CACHE_SIZE because domain cardinality differs:
# locales are user-controlled (small working set), territories are enumerable (finite set).
MAX_TERRITORY_CACHE_SIZE: int = 300

# Maximum cached currency-keyed entries (e.g., currency name/symbol lookups).
# ISO 4217 defines ~180 active currency codes. 300 provides margin for historical
# currencies and complete coverage without cache thrashing when iterating all currencies.
# Semantically distinct from MAX_TERRITORY_CACHE_SIZE to enable independent tuning
# of currency-specific vs territory-specific caches.
MAX_CURRENCY_CACHE_SIZE: int = 300

# Default maximum cache entries for format results.
# 1000 entries is sufficient for most applications (typical UI has <500 messages).
DEFAULT_CACHE_SIZE: int = 1000

# Default maximum entry weight in characters (~10KB for typical strings).
# Prevents unbounded memory usage when caching very large formatted results.
# Results exceeding this limit are computed but not cached, protecting against
# scenarios where large variable values produce very large formatted strings
# (e.g., 10MB results cached 1000 times would consume 10GB of memory).
DEFAULT_MAX_ENTRY_WEIGHT: int = 10_000

# ============================================================================
# INPUT LIMITS
# ============================================================================

# Default maximum source size in characters (10 million characters).
# Python measures string length in characters (code points), not bytes.
# UTF-8 encoding means 1 character = 1-4 bytes, but len(source) counts characters.
# Prevents DoS attacks via unbounded memory allocation from large FTL files.
MAX_SOURCE_SIZE: int = 10_000_000

# Maximum typical locale code length per BCP 47 / RFC 5646 (35 characters recommended).
# BCP 47 well-formed locale tags are typically <35 characters, including language,
# script, region, and variant subtags (e.g., "zh-Hans-CN-x-private").
# This constant is used by LocaleContext.create() to trigger warnings for unusually
# long locale codes. Locales exceeding this limit are still validated by Babel - if
# Babel accepts them, they are used; if Babel rejects them, fallback to en_US occurs.
# This two-tier validation supports valid extended locales while warning about potential
# misconfiguration or attack attempts.
# Real-world locale codes: typically 2-16 characters (e.g., "en", "en-US", "zh-Hans-CN").
MAX_LOCALE_CODE_LENGTH: int = 35

# Maximum locale code length for DoS prevention (1000 characters).
# This hard limit accepts all BCP 47 private-use extensions while preventing
# memory exhaustion from extremely long locale strings. Used by FluentBundle
# for input validation. MAX_LOCALE_CODE_LENGTH (35) triggers warnings;
# MAX_LOCALE_LENGTH_HARD_LIMIT (1000) triggers rejection.
MAX_LOCALE_LENGTH_HARD_LIMIT: int = 1000

# ============================================================================
# IDENTIFIER LENGTH LIMIT
# ============================================================================
#
# Cross-module constant used by:
# - syntax/parser/primitives.py (parse_identifier DoS guard)
# - core/identifier_validation.py (is_valid_identifier length check)
#
# Parser-local limits (_MAX_NUMBER_LENGTH, _MAX_STRING_LITERAL_LENGTH) and
# parser-only limits (MAX_LOOKAHEAD_CHARS, MAX_PARSE_ERRORS) are defined in
# the parser modules that own them, per the locality principle.

# Maximum identifier length (256 chars).
# Real-world identifiers rarely exceed 50 characters. 256 provides ample margin
# while preventing memory exhaustion from million-character "identifiers".
MAX_IDENTIFIER_LENGTH: int = 256

# ============================================================================
# FORMAT LIMITS
# ============================================================================

# Maximum number of fraction/integer digits in number formatting.
# Prevents DoS via unbounded string allocation ("0" * N) when processing
# minimumFractionDigits or maximumFractionDigits from FTL NUMBER() calls.
# 100 digits exceeds any real-world financial requirement:
# - IEEE 754 decimal128: 34 significant digits
# - Largest real-world precision (cryptocurrency): ~18 digits
# - Scientific notation: rarely exceeds 30 digits
MAX_FORMAT_DIGITS: int = 100

# ============================================================================
# RESOLUTION LIMITS
# ============================================================================

# Maximum total characters produced during message resolution.
# Prevents exponential expansion attacks (Billion Laughs) where a small FTL
# resource expands to gigabytes of output via nested self-referencing messages
# (e.g., m0={m1}{m1}, m1={m2}{m2}, ...). The resolver tracks depth but without
# an expansion budget, 25 levels of binary fan-out produce 2^25 = 33M copies.
# 1MB character budget is generous for legitimate use (typical messages <1KB)
# while preventing resource exhaustion from adversarial input.
DEFAULT_MAX_EXPANSION_SIZE: int = 1_000_000

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

# ============================================================================
# ISO 4217 CURRENCY DECIMAL DIGITS
# ============================================================================
#
# ISO 4217 specifies the number of decimal digits for each currency.
# Most currencies use 2 decimal places. Exceptions:
# - Zero decimals: JPY, KRW, VND (no subunits or subunits not used)
# - Three decimals: TND, KWD, BHD, JOD, OMR (1/1000 subunits)
# - Four decimals: CLF, UYW (accounting units)
#
# Source: ISO 4217:2015 and subsequent amendments
# https://www.iso.org/iso-4217-currency-codes.html
#
# Babel exposes decimal digits via babel.numbers.get_currency_precision(),
# but its CLDR data may differ from ISO 4217 for specific currencies (e.g.,
# IQD: Babel reports 0 decimals, ISO 4217 specifies 3). This hardcoded
# constant is the authoritative source for ISO 4217 decimal precision.
# Used by both the introspection module and parser-only installations.
#
# ============================================================================

# Currencies with non-standard decimal digits (0, 3, or 4).
# All currencies not listed here default to 2 decimal digits.
ISO_4217_DECIMAL_DIGITS: MappingProxyType[str, int] = MappingProxyType({
    # Zero decimal currencies (no minor unit or minor unit not used)
    "BIF": 0,  # Burundian Franc
    "CLP": 0,  # Chilean Peso
    "DJF": 0,  # Djiboutian Franc
    "GNF": 0,  # Guinean Franc
    "ISK": 0,  # Icelandic Krona
    "JPY": 0,  # Japanese Yen
    "KMF": 0,  # Comorian Franc
    "KRW": 0,  # South Korean Won
    "PYG": 0,  # Paraguayan Guarani
    "RWF": 0,  # Rwandan Franc
    "UGX": 0,  # Ugandan Shilling
    "UYI": 0,  # Uruguay Peso en Unidades Indexadas (accounting)
    "VND": 0,  # Vietnamese Dong
    "VUV": 0,  # Vanuatu Vatu
    "XAF": 0,  # Central African CFA Franc
    "XOF": 0,  # West African CFA Franc
    "XPF": 0,  # CFP Franc (Pacific)
    # Three decimal currencies (1/1000 minor unit)
    "BHD": 3,  # Bahraini Dinar
    "IQD": 3,  # Iraqi Dinar
    "JOD": 3,  # Jordanian Dinar
    "KWD": 3,  # Kuwaiti Dinar
    "LYD": 3,  # Libyan Dinar
    "OMR": 3,  # Omani Rial
    "TND": 3,  # Tunisian Dinar
    # Four decimal currencies (accounting/indexing units)
    "CLF": 4,  # Unidad de Fomento (Chile)
    "UYW": 4,  # Unidad Previsional (Uruguay)
})

# Default decimal digits for currencies not in ISO_4217_DECIMAL_DIGITS.
# Per ISO 4217, the vast majority of currencies use 2 decimal places.
ISO_4217_DEFAULT_DECIMALS: int = 2
