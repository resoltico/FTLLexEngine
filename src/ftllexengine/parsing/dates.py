"""Date and datetime parsing functions with locale awareness.

- parse_date() returns tuple[date | None, tuple[FluentParseError, ...]]
- parse_datetime() returns tuple[datetime | None, tuple[FluentParseError, ...]]
- Removed `strict` parameter - functions NEVER raise, errors returned in tuple
- Consistent with format_*() "never raise" philosophy
- Fixed: Date pattern tokenizer replaces regex word boundary approach
- Optimized: Pattern generation is cached per locale

Timezone Handling:
    UTC offset patterns (Z, ZZ, ZZZ, ZZZZ, ZZZZZ, x, xx, xxx, xxxx, xxxxx,
    X, XX, XXX, XXXX, XXXXX) are fully supported via strptime %z.

    Timezone NAME patterns (z, zz, zzz, zzzz, v, vvvv, V, VV, VVV, VVVV, O, OOOO)
    are NOT supported for parsing. These tokens are stripped from the pattern,
    but the input is NOT pre-processed. Users must pre-strip timezone names
    from input or use UTC offset patterns instead.

    This limitation exists because timezone names are locale-specific (e.g.,
    "Pacific Standard Time" in English vs "Heure normale du Pacifique" in French)
    and Python's strptime has no built-in timezone name parsing.

Hour-24 Limitation:
    CLDR patterns using k/kk tokens (hour 1-24) are mapped to Python's %H (0-23).
    Input "24:00" will fail to parse. Users needing hour-24 support must
    preprocess input to normalize "24:00" to "00:00" with day increment.

Thread-safe. Uses Python 3.13 stdlib + Babel CLDR patterns.

Python 3.13+.
"""

from datetime import date, datetime, timezone
from functools import cache

from babel import Locale, UnknownLocaleError

from ftllexengine.diagnostics import FluentParseError
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.locale_utils import normalize_locale

__all__ = ["parse_date", "parse_datetime"]

# CLDR date format styles used for parsing.
# Both date and datetime use the same styles for consistency.
_DATE_PARSE_STYLES: tuple[str, ...] = ("short", "medium", "long")
_DATETIME_PARSE_STYLES: tuple[str, ...] = ("short", "medium", "long")

# Default separator between date and time components (fallback only).
# Used when locale-specific dateTimeFormat pattern extraction fails.
_DATETIME_SEPARATOR_FALLBACK: str = " "


def parse_date(
    value: str,
    locale_code: str,
) -> tuple[date | None, tuple[FluentParseError, ...]]:
    """Parse locale-aware date string to date object.

    No longer raises exceptions. Errors are returned in tuple.
    The `strict` parameter has been removed.

    Only ISO 8601 and locale-specific CLDR patterns are supported.
    Ambiguous formats like "1/2/25" will ONLY match if locale CLDR pattern matches.

    Args:
        value: Date string (e.g., "28.01.25" for lv_LV, "2025-01-28" for ISO 8601)
        locale_code: BCP 47 locale identifier (e.g., "en_US", "lv_LV", "de_DE")

    Returns:
        Tuple of (result, errors):
        - result: Parsed date object, or None if parsing failed
        - errors: Tuple of FluentParseError (empty tuple on success)

    Examples:
        >>> result, errors = parse_date("2025-01-28", "en_US")  # ISO 8601
        >>> result
        datetime.date(2025, 1, 28)
        >>> errors
        ()

        >>> result, errors = parse_date("1/28/25", "en_US")  # US locale format
        >>> result
        datetime.date(2025, 1, 28)

        >>> result, errors = parse_date("invalid", "en_US")
        >>> result is None
        True
        >>> len(errors)
        1

    Thread Safety:
        Thread-safe. Uses Babel + stdlib (no global state).
    """
    errors: list[FluentParseError] = []

    # Type check: value must be string (runtime defense for untyped callers)
    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_date_failed(  # type: ignore[unreachable]
            str(value), locale_code, f"Expected string, got {type(value).__name__}"
        )
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=str(value),
                locale_code=locale_code,
                parse_type="date",
            )
        )
        return (None, tuple(errors))

    # Try ISO 8601 first (fastest path)
    try:
        return (datetime.fromisoformat(value).date(), tuple(errors))
    except ValueError:
        pass

    # Try locale-specific CLDR patterns
    patterns = _get_date_patterns(locale_code)
    if not patterns:
        # Unknown locale
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="date",
            )
        )
        return (None, tuple(errors))

    for pattern, has_era, _has_timezone in patterns:
        try:
            # Preprocess for era tokens before strptime
            parse_value = _preprocess_datetime_input(value, has_era)
            return (datetime.strptime(parse_value, pattern).date(), tuple(errors))
        except ValueError:
            continue

    # All patterns failed
    diagnostic = ErrorTemplate.parse_date_failed(
        value, locale_code, "No matching date pattern found"
    )
    errors.append(
        FluentParseError(
            diagnostic,
            input_value=value,
            locale_code=locale_code,
            parse_type="date",
        )
    )
    return (None, tuple(errors))


def parse_datetime(
    value: str,
    locale_code: str,
    *,
    tzinfo: timezone | None = None,
) -> tuple[datetime | None, tuple[FluentParseError, ...]]:
    """Parse locale-aware datetime string to datetime object.

    No longer raises exceptions. Errors are returned in tuple.
    The `strict` parameter has been removed.

    Only ISO 8601 and locale-specific CLDR patterns are supported.

    Args:
        value: DateTime string (e.g., "2025-01-28 14:30" for ISO 8601)
        locale_code: BCP 47 locale identifier (e.g., "en_US", "lv_LV", "de_DE")
        tzinfo: Timezone to assign if not in string (default: None - naive datetime)

    Returns:
        Tuple of (result, errors):
        - result: Parsed datetime object, or None if parsing failed
        - errors: Tuple of FluentParseError (empty tuple on success)

    Examples:
        >>> result, errors = parse_datetime("2025-01-28 14:30", "en_US")  # ISO 8601
        >>> result
        datetime.datetime(2025, 1, 28, 14, 30)
        >>> errors
        ()

        >>> result, errors = parse_datetime("1/28/25 2:30 PM", "en_US")  # US locale
        >>> result
        datetime.datetime(2025, 1, 28, 14, 30)

        >>> result, errors = parse_datetime("invalid", "en_US")
        >>> result is None
        True
        >>> len(errors)
        1

    Thread Safety:
        Thread-safe. Uses Babel + stdlib (no global state).
    """
    errors: list[FluentParseError] = []

    # Type check: value must be string (runtime defense for untyped callers)
    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_datetime_failed(  # type: ignore[unreachable]
            str(value), locale_code, f"Expected string, got {type(value).__name__}"
        )
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=str(value),
                locale_code=locale_code,
                parse_type="datetime",
            )
        )
        return (None, tuple(errors))

    # Try ISO 8601 first (fastest path)
    try:
        parsed = datetime.fromisoformat(value)
        if tzinfo is not None and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tzinfo)
        return (parsed, tuple(errors))
    except (ValueError, TypeError):
        pass

    # Try locale-specific CLDR patterns
    patterns = _get_datetime_patterns(locale_code)
    if not patterns:
        # Unknown locale
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="datetime",
            )
        )
        return (None, tuple(errors))

    for pattern, has_era, _has_timezone in patterns:
        try:
            # Preprocess for era tokens before strptime
            parse_value = _preprocess_datetime_input(value, has_era)
            parsed = datetime.strptime(parse_value, pattern)
            if tzinfo is not None and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=tzinfo)
            return (parsed, tuple(errors))
        except ValueError:
            continue

    # All patterns failed
    diagnostic = ErrorTemplate.parse_datetime_failed(
        value, locale_code, "No matching datetime pattern found"
    )
    errors.append(
        FluentParseError(
            diagnostic,
            input_value=value,
            locale_code=locale_code,
            parse_type="datetime",
        )
    )
    return (None, tuple(errors))


@cache
def _get_date_patterns(locale_code: str) -> tuple[tuple[str, bool, bool], ...]:
    """Get strptime date patterns for locale with era and timezone flags.

    Uses ONLY Babel CLDR date format patterns specific to the locale.
    No fallback patterns to avoid ambiguous date interpretation.

    Results are cached per locale_code for performance.

    Returns 3-tuples with separate era and timezone flags.

    Args:
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (strptime_pattern, has_era, has_timezone) triples to try.
        has_era is True if the pattern contains era tokens requiring preprocessing.
        has_timezone is True if the pattern contains timezone tokens.
        Empty tuple if locale parsing fails.
    """
    try:
        locale = Locale.parse(normalize_locale(locale_code))

        # Get CLDR date patterns
        patterns: list[tuple[str, bool, bool]] = []

        # Try CLDR format styles
        for style in _DATE_PARSE_STYLES:
            try:
                babel_pattern = locale.date_formats[style].pattern
                strptime_pattern, has_era, has_timezone = _babel_to_strptime(babel_pattern)
                patterns.append((strptime_pattern, has_era, has_timezone))
            except (AttributeError, KeyError):
                pass

        return tuple(patterns)

    except (UnknownLocaleError, ValueError, RuntimeError):
        return ()


def _extract_datetime_separator(locale: Locale, style: str = "medium") -> str:
    """Extract the date-time separator from locale's CLDR dateTimeFormat.

    CLDR dateTimeFormat patterns use {0} for time and {1} for date, e.g.:
    - en_US: "{1}, {0}" -> separator is ", "
    - ja_JP: "{1} {0}" -> separator is " "
    - fr_FR medium: "{1}, {0}" -> separator is ", "

    Args:
        locale: Babel Locale object
        style: Format style to extract from ("short" or "medium")

    Returns:
        The separator string between date and time components.
        Falls back to space if extraction fails.
    """
    try:
        datetime_format = locale.datetime_formats.get(style)
        if datetime_format is None:
            return _DATETIME_SEPARATOR_FALLBACK

        # Get the pattern string - may be str or DateTimePattern object
        pattern = str(datetime_format)

        # Pattern format: "{1}<separator>{0}" where {1}=date, {0}=time
        # Find the text between {1} and {0}
        date_placeholder = "{1}"
        time_placeholder = "{0}"

        date_idx = pattern.find(date_placeholder)
        time_idx = pattern.find(time_placeholder)

        if date_idx == -1 or time_idx == -1:
            return _DATETIME_SEPARATOR_FALLBACK

        # Handle both "{1}<sep>{0}" and "{0}<sep>{1}" orderings
        if date_idx < time_idx:
            # Normal order: date first, then time
            sep_start = date_idx + len(date_placeholder)
            sep_end = time_idx
        else:
            # Reversed order: time first, then date
            sep_start = time_idx + len(time_placeholder)
            sep_end = date_idx

        if sep_start < sep_end:
            return pattern[sep_start:sep_end]

        return _DATETIME_SEPARATOR_FALLBACK

    except (AttributeError, TypeError, ValueError):
        return _DATETIME_SEPARATOR_FALLBACK


@cache
def _get_datetime_patterns(locale_code: str) -> tuple[tuple[str, bool, bool], ...]:
    """Get strptime datetime patterns for locale with era and timezone flags.

    Uses ONLY Babel CLDR datetime format patterns specific to the locale.
    No fallback patterns to avoid ambiguous datetime interpretation.

    Results are cached per locale_code for performance.

    Returns 3-tuples with separate era and timezone flags.

    Args:
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (strptime_pattern, has_era, has_timezone) triples to try.
        has_era is True if the pattern contains era tokens requiring preprocessing.
        has_timezone is True if the pattern contains timezone tokens.
        Empty tuple if locale parsing fails.
    """
    try:
        locale = Locale.parse(normalize_locale(locale_code))

        # Get CLDR datetime patterns
        patterns: list[tuple[str, bool, bool]] = []

        # Try CLDR format styles for datetime
        for style in _DATETIME_PARSE_STYLES:
            try:
                babel_pattern = locale.datetime_formats[style].pattern
                strptime_pattern, has_era, has_timezone = _babel_to_strptime(babel_pattern)
                patterns.append((strptime_pattern, has_era, has_timezone))
            except (AttributeError, KeyError):
                pass

        # Get date patterns and add time components for locale
        date_patterns = _get_date_patterns(locale_code)

        # Get locale-specific separator from CLDR dateTimeFormat
        sep = _extract_datetime_separator(locale)
        for date_pat, has_era, has_timezone in date_patterns:
            # Time components don't have era/timezone, inherit from date pattern
            patterns.extend(
                [
                    (f"{date_pat}{sep}%H:%M:%S", has_era, has_timezone),  # 24-hour with seconds
                    (f"{date_pat}{sep}%H:%M", has_era, has_timezone),  # 24-hour without seconds
                    (f"{date_pat}{sep}%I:%M:%S %p", has_era, has_timezone),  # 12-hour with seconds
                    (f"{date_pat}{sep}%I:%M %p", has_era, has_timezone),  # 12-hour without seconds
                ]
            )

        return tuple(patterns)

    except (UnknownLocaleError, ValueError, RuntimeError):
        return ()


# ==============================================================================
# TOKEN-BASED BABEL-TO-STRPTIME CONVERTER
# ==============================================================================
# ruff: noqa: ERA001 - Documentation table is not commented-out code
#
# ARCHITECTURAL OVERVIEW:
#
# The Unicode CLDR (Common Locale Data Repository) defines locale-specific date
# patterns using a standardized format. Babel provides access to CLDR data.
# Python's strptime uses a different directive syntax. This module bridges them.
#
# CLDR Pattern Syntax (subset relevant to parsing):
#   Pattern | Meaning                | Example
#   --------|------------------------|--------
#   y/yy    | 2-digit year           | 25
#   yyyy    | 4-digit year           | 2025
#   M/MM    | Month (numeric)        | 1, 01
#   MMM     | Month (short name)     | Jan
#   MMMM    | Month (full name)      | January
#   d/dd    | Day of month           | 5, 05
#   E/EEE   | Weekday (short)        | Mon
#   EEEE    | Weekday (full)         | Monday
#   G       | Era (AD/BC)            | AD (no strptime equivalent)
#   H/HH    | Hour (0-23)            | 14
#   h/hh    | Hour (1-12)            | 2
#   m/mm    | Minute                 | 30
#   s/ss    | Second                 | 45
#   a       | AM/PM marker           | PM
#   S+      | Fractional seconds     | 123
#
# CONVERSION STRATEGY:
# 1. Tokenize: Split CLDR pattern into tokens (letters, literals, quotes)
# 2. Map: Convert each token using _BABEL_TOKEN_MAP
# 3. Handle special cases:
#    - Era tokens (G): Mark pattern for preprocessing, strip era from input
#    - Timezone names (z): Cannot be parsed by strptime, marked for skip
#    - Stand-alone month/weekday (L/c): Map to format context equivalents
#
# QUOTE ESCAPING (CLDR):
#   - Single quotes delimit literal text: 'at' -> "at"
#   - Double single quotes escape: '' -> "'"
#   - Example: "h 'o''clock' a" -> "2 o'clock PM"
#
# ERA HANDLING:
#   Python's strptime has no era support. Patterns containing G tokens are
#   marked with has_era=True. At parse time, _strip_era() removes era text
#   from input before parsing. See _ERA_STRINGS for supported designations.
#
# KNOWN LIMITATIONS:
#   - Fractional seconds: CLDR uses S/SS/SSS for 1-3 digits, strptime %f
#     expects 6 digits (microseconds). Best-effort mapping is applied.
#   - Timezone names: strptime cannot parse "PST" or "America/Los_Angeles".
#     These tokens are marked for skip.
#   - Hour 1-24 (k) and 0-11 (K): Mapped to closest strptime equivalent
#     with potential off-by-one at midnight/noon boundaries.
#
# ==============================================================================

# Token mapping: Babel CLDR pattern -> Python strptime directive
# None values indicate tokens that require preprocessing (e.g., era stripping)
_BABEL_TOKEN_MAP: dict[str, str | None] = {
    # Year
    "yyyy": "%Y",  # 4-digit year
    "yy": "%y",  # 2-digit year
    "y": "%Y",  # Year (default to 4-digit)
    # Month (format context)
    "MMMM": "%B",  # Full month name
    "MMM": "%b",  # Short month name
    "MM": "%m",  # 2-digit month
    "M": "%m",  # Month
    # Month (stand-alone context) - used in some locales for headers/labels
    "LLLL": "%B",  # Full month name (stand-alone)
    "LLL": "%b",  # Short month name (stand-alone)
    "LL": "%m",  # 2-digit month (stand-alone)
    "L": "%m",  # Month (stand-alone)
    # Day
    "dd": "%d",  # 2-digit day
    "d": "%d",  # Day
    # Weekday (format context)
    "EEEE": "%A",  # Full weekday name
    "EEE": "%a",  # Short weekday name
    "E": "%a",  # Weekday
    # Weekday (stand-alone context) - used in some locales for headers/labels
    "cccc": "%A",  # Full weekday name (stand-alone)
    "ccc": "%a",  # Short weekday name (stand-alone)
    "cc": "%w",  # Numeric weekday (stand-alone)
    "c": "%w",  # Numeric weekday (stand-alone)
    # Era (AD/BC) - strptime doesn't support era
    # Map to None to signal that era stripping is needed
    # See _ERA_STRINGS and _strip_era() for runtime handling
    "GGGG": None,  # Full era name (Anno Domini)
    "GGG": None,  # Abbreviated era (AD)
    "GG": None,  # Abbreviated era (AD)
    "G": None,  # Era abbreviation (AD)
    # Hour
    "HH": "%H",  # 2-digit hour (0-23)
    "H": "%H",  # Hour (0-23)
    "hh": "%I",  # 2-digit hour (1-12)
    "h": "%I",  # Hour (1-12)
    # Minute
    "mm": "%M",  # 2-digit minute
    "m": "%M",  # Minute
    # Second
    "ss": "%S",  # 2-digit second
    "s": "%S",  # Second
    # Fractional seconds
    # Python's %f expects 6 digits (microseconds); CLDR uses variable precision
    # Map to %f and accept precision mismatch as best-effort
    "SSSSSS": "%f",  # Microseconds (6 digits)
    "SSSSS": "%f",  # 5 fractional digits
    "SSSS": "%f",  # 4 fractional digits
    "SSS": "%f",  # Milliseconds (3 digits)
    "SS": "%f",  # 2 fractional digits
    "S": "%f",  # 1 fractional digit
    # AM/PM
    "a": "%p",  # AM/PM marker
    # Hour (1-24 and 0-11 variants)
    # Python doesn't have direct equivalents; map to closest
    "kk": "%H",  # Hour 1-24 -> 0-23 (off-by-one at midnight)
    "k": "%H",  # Hour 1-24 -> 0-23
    "KK": "%I",  # Hour 0-11 -> 1-12 (off-by-one at noon)
    "K": "%I",  # Hour 0-11 -> 1-12
    # Timezone tokens
    # Python strptime has limited timezone support; map what's possible
    "ZZZZZ": "%z",  # Extended offset (e.g., +01:00) -> +HHMM
    "ZZZZ": "%z",  # Localized GMT (e.g., GMT+01:00) -> +HHMM (partial)
    "ZZZ": "%z",  # RFC 822 offset (e.g., +0100)
    "ZZ": "%z",  # RFC 822 offset
    "Z": "%z",  # Basic offset
    "xxxxx": "%z",  # ISO 8601 extended (+01:00:00)
    "xxxx": "%z",  # ISO 8601 basic (+0100)
    "xxx": "%z",  # ISO 8601 extended (+01:00)
    "xx": "%z",  # ISO 8601 basic (+01)
    "x": "%z",  # ISO 8601 basic (+01)
    "XXXXX": "%z",  # ISO 8601 extended with Z
    "XXXX": "%z",  # ISO 8601 basic with Z
    "XXX": "%z",  # ISO 8601 extended with Z
    "XX": "%z",  # ISO 8601 basic with Z
    "X": "%z",  # ISO 8601 basic with Z
    # Timezone names - strptime has limited support
    # These often fail in strptime; map to None like era tokens
    "zzzz": None,  # Full timezone name (e.g., Pacific Standard Time)
    "zzz": None,  # Abbreviated timezone (e.g., PST)
    "zz": None,  # Abbreviated timezone
    "z": None,  # Abbreviated timezone
    "vvvv": None,  # Generic non-location timezone
    "v": None,  # Generic non-location timezone short
    "VVVV": None,  # Generic location timezone
    "VVV": None,  # City timezone
    "VV": None,  # Timezone ID (e.g., America/Los_Angeles)
    "V": None,  # Short timezone ID
    "OOOO": None,  # Localized GMT long
    "O": None,  # Localized GMT short
}

# Era strings to strip from input when pattern contains era tokens
# Sorted by length descending to match longer strings first
# Covers common English and Latin era designations
_ERA_STRINGS: tuple[str, ...] = (
    "Anno Domini",  # GGGG full form
    "Before Christ",  # GGGG full form (BC)
    "Common Era",  # CE variant
    "Before Common Era",  # BCE variant
    "A.D.",  # With periods
    "B.C.",  # With periods
    "C.E.",  # Common Era with periods
    "BCE",  # Before Common Era
    "AD",  # Standard abbreviation
    "BC",  # Standard abbreviation
    "CE",  # Common Era
)

# NOTE: Timezone name stripping is not implemented.
# English-only timezone stripping would be incomplete:
# - Only worked for English timezone names (PST, EST, etc.)
# - Failed for localized timezone names (French, Spanish, etc.)
# - Created inconsistent behavior across locales
#
# Timezone name tokens (z, zz, zzz, zzzz, v, V, O) are now:
# - Stripped from the pattern (mapped to None in _BABEL_TOKEN_MAP)
# - NOT stripped from input (users must pre-strip or use UTC offset patterns)
#
# Supported timezone patterns:
# - UTC offset patterns: Z, ZZ, ZZZ, ZZZZ, ZZZZZ, x, xx, xxx, xxxx, xxxxx, X, XX, XXX, XXXX, XXXXX
# - These are locale-agnostic and fully supported via strptime %z
#
# Unsupported timezone patterns (input must be pre-stripped by caller):
# - Timezone name patterns: z, zz, zzz, zzzz, v, vvvv, V, VV, VVV, VVVV, O, OOOO


def _strip_era(value: str) -> str:
    """Strip era designations from date string.

    Used when pattern contains era tokens (G/GG/GGG/GGGG) since Python's
    strptime doesn't support era parsing.

    Args:
        value: Date string potentially containing era text

    Returns:
        Date string with era text removed and whitespace normalized
    """
    result = value
    for era in _ERA_STRINGS:
        # Case-insensitive replacement
        idx = result.upper().find(era.upper())
        if idx != -1:
            result = result[:idx] + result[idx + len(era) :]
    # Normalize whitespace (collapse multiple spaces)
    return " ".join(result.split())


def _preprocess_datetime_input(value: str, has_era: bool) -> str:
    """Preprocess datetime input by stripping unsupported tokens.

    Currently only handles era tokens. Timezone name tokens (z, zz, zzz, zzzz,
    v, V, O series) are stripped from the pattern but NOT from the input.
    Users must pre-strip timezone text from input or use UTC offset patterns
    (Z, x, X series) which are locale-agnostic.

    Args:
        value: Date/datetime string to preprocess
        has_era: True if pattern contained era tokens (G/GG/GGG/GGGG)

    Returns:
        Preprocessed string with era text removed
    """
    if has_era:
        return _strip_era(value)
    return value


def _tokenize_babel_pattern(pattern: str) -> list[str]:
    """Tokenize Babel CLDR pattern into individual tokens.

    This correctly handles patterns like "d.MM.yyyy" where "d" is adjacent
    to punctuation without word boundaries.

    CLDR quote escaping rules:
    - Single quotes delimit literal text: 'at' produces "at"
    - Two consecutive single quotes '' produce a literal single quote
    - '' inside quoted text also produces a literal single quote

    Examples:
        "h 'o''clock' a" -> ["h", " ", "o'clock", " ", "a"]
        "yyyy-MM-dd" -> ["yyyy", "-", "MM", "-", "dd"]
        "d.MM.yyyy" -> ["d", ".", "MM", ".", "yyyy"]

    Args:
        pattern: Babel CLDR date pattern (e.g., "d.MM.yyyy")

    Returns:
        List of tokens (e.g., ["d", ".", "MM", ".", "yyyy"])
    """
    tokens: list[str] = []
    i = 0
    n = len(pattern)

    while i < n:
        char = pattern[i]

        # Check for quoted literal (single quotes in CLDR patterns)
        if char == "'":
            # Check for escaped quote '' (produces literal single quote)
            if i + 1 < n and pattern[i + 1] == "'":
                # '' outside quoted section -> literal single quote
                tokens.append("'")
                i += 2
                continue

            # Start of quoted literal section
            i += 1  # Skip opening quote
            literal_chars: list[str] = []

            while i < n:
                if pattern[i] == "'":
                    # Check for escaped quote '' inside quoted section
                    if i + 1 < n and pattern[i + 1] == "'":
                        # '' inside quoted section -> literal single quote
                        literal_chars.append("'")
                        i += 2
                    else:
                        # Closing quote found
                        i += 1
                        break
                else:
                    literal_chars.append(pattern[i])
                    i += 1

            # Add collected literal as single token
            if literal_chars:
                tokens.append("".join(literal_chars))
            continue

        # Check for pattern letter sequences (a-zA-Z)
        if char.isalpha():
            # Collect consecutive same letters (e.g., "yyyy", "MM", "dd")
            j = i + 1
            while j < n and pattern[j] == char:
                j += 1
            tokens.append(pattern[i:j])
            i = j
            continue

        # Everything else is a literal (punctuation, spaces, etc.)
        tokens.append(char)
        i += 1

    return tokens


def _babel_to_strptime(babel_pattern: str) -> tuple[str, bool, bool]:
    """Convert Babel CLDR pattern to Python strptime format.

    Fixes edge cases with word boundaries in patterns like "d.MM.yyyy".

    Babel uses Unicode CLDR date pattern syntax, Python uses strptime directives.

    Returns separate flags for era and timezone tokens. Era tokens (G/GG/GGG/GGGG)
    require preprocessing to strip era text. Timezone name tokens are tracked
    separately but not stripped from input.

    Returns:
        Tuple of (strptime_pattern, has_era, has_timezone) where:
        - has_era indicates era tokens requiring _strip_era() preprocessing
        - has_timezone indicates timezone tokens requiring _strip_timezone()

    Babel Patterns:
        y, yy      = 2-digit year
        yyyy       = 4-digit year
        M, MM      = month (1-12)
        MMM        = short month name (Jan, Feb)
        MMMM       = full month name (January, February)
        d, dd      = day of month
        E, EEE     = short weekday (Mon)
        EEEE       = full weekday (Monday)
        H, HH      = hour 0-23
        h, hh      = hour 1-12
        m, mm      = minute
        s, ss      = second
        a          = AM/PM

    Python strptime:
        %y  = 2-digit year
        %Y  = 4-digit year
        %m  = month (01-12)
        %b  = short month name
        %B  = full month name
        %d  = day of month
        %a  = short weekday
        %A  = full weekday
        %H  = hour 0-23
        %I  = hour 1-12
        %M  = minute
        %S  = second
        %p  = AM/PM

    Args:
        babel_pattern: Babel CLDR date pattern

    Returns:
        Tuple of (strptime_pattern, has_era, has_timezone):
        - strptime_pattern: Python strptime pattern
        - has_era: True if pattern contained era tokens (G/GG/GGG/GGGG)
        - has_timezone: True if pattern contained timezone tokens (z/v/V/O)
    """
    tokens = _tokenize_babel_pattern(babel_pattern)
    result_parts: list[str] = []
    has_era = False
    has_timezone = False

    # Timezone token prefixes (tokens that map to None and need timezone stripping)
    timezone_prefixes = ("z", "v", "V", "O")

    for token in tokens:
        # Check if token is a Babel pattern token
        if token in _BABEL_TOKEN_MAP:
            mapped = _BABEL_TOKEN_MAP[token]
            if mapped is None:
                # Token maps to None - determine if era or timezone
                if token.startswith("G"):
                    has_era = True
                elif token.startswith(timezone_prefixes):
                    has_timezone = True
            else:
                result_parts.append(mapped)
        else:
            # Literal: pass through (punctuation, spaces, etc.)
            result_parts.append(token)

    return ("".join(result_parts), has_era, has_timezone)
