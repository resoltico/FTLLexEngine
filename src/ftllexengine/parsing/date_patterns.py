"""Cached CLDR pattern extraction and conversion helpers for date parsing."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.babel_compat import (
    get_locale_class,
    get_unknown_locale_error_class,
    is_babel_available,
    require_babel,
)
from ftllexengine.core.locale_utils import normalize_locale

__all__ = [
    "_babel_to_strptime",
    "_get_date_patterns",
    "_get_datetime_patterns",
    "_is_word_boundary",
    "_preprocess_datetime_input",
    "_strip_era",
    "_tokenize_babel_pattern",
    "clear_date_caches",
]

# CLDR date format styles used for parsing.
# Both date and datetime use the same styles for consistency.
_DATE_PARSE_STYLES: tuple[str, ...] = ("short", "medium", "long", "full")
_DATETIME_PARSE_STYLES: tuple[str, ...] = ("short", "medium", "long", "full")

# Default separator between date and time components (fallback only).
# Used when locale-specific dateTimeFormat pattern extraction fails.
_DATETIME_SEPARATOR_FALLBACK: str = " "


def _extract_cldr_patterns(
    format_dict: Any,
    styles: tuple[str, ...],
) -> list[tuple[str, bool]]:
    """Extract strptime patterns from a Babel CLDR format dictionary."""
    patterns: list[tuple[str, bool]] = []
    for style in styles:
        try:
            fmt = format_dict[style]
            babel_pattern = fmt.pattern if hasattr(fmt, "pattern") else str(fmt)
            strptime_pattern, has_era = _babel_to_strptime(babel_pattern)
            patterns.append((strptime_pattern, has_era))
            if "%y" in strptime_pattern:
                patterns.append((strptime_pattern.replace("%y", "%Y"), has_era))
        except (AttributeError, KeyError):
            pass
    return patterns


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _get_date_patterns(locale_code: str) -> tuple[tuple[str, bool], ...]:
    """Get cached strptime date patterns for one locale."""
    require_babel("parse_date")
    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()

    try:
        locale = locale_class.parse(normalize_locale(locale_code))
        return tuple(_extract_cldr_patterns(locale.date_formats, _DATE_PARSE_STYLES))
    except (unknown_locale_error_class, ValueError, RuntimeError, AttributeError):
        return ()


def _extract_datetime_separator(locale: Any, style: str = "medium") -> tuple[str, bool]:
    """Extract the locale-specific separator and ordering for date-time formats."""
    try:
        datetime_format = locale.datetime_formats.get(style)
        if datetime_format is None:
            return _DATETIME_SEPARATOR_FALLBACK, False

        pattern = str(datetime_format)
        date_placeholder = "{1}"
        time_placeholder = "{0}"

        date_idx = pattern.find(date_placeholder)
        time_idx = pattern.find(time_placeholder)

        if date_idx == -1 or time_idx == -1:
            return _DATETIME_SEPARATOR_FALLBACK, False

        is_time_first = time_idx < date_idx

        if date_idx < time_idx:
            sep_start = date_idx + len(date_placeholder)
            sep_end = time_idx
        else:
            sep_start = time_idx + len(time_placeholder)
            sep_end = date_idx

        if sep_start < sep_end:
            return pattern[sep_start:sep_end], is_time_first

        return _DATETIME_SEPARATOR_FALLBACK, is_time_first
    except (AttributeError, TypeError, ValueError):
        return _DATETIME_SEPARATOR_FALLBACK, False


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _get_datetime_patterns(locale_code: str) -> tuple[tuple[str, bool], ...]:
    """Get cached strptime datetime patterns for one locale."""
    require_babel("parse_datetime")
    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()

    try:
        locale = locale_class.parse(normalize_locale(locale_code))
        patterns = _extract_cldr_patterns(locale.datetime_formats, _DATETIME_PARSE_STYLES)
        date_patterns = _get_date_patterns(locale_code)
        sep, is_time_first = _extract_datetime_separator(locale)

        time_formats = [
            "%H:%M:%S",
            "%H:%M",
            "%I:%M:%S %p",
            "%I:%M %p",
        ]

        for date_pat, has_era in date_patterns:
            for time_pat in time_formats:
                combined = (
                    f"{time_pat}{sep}{date_pat}" if is_time_first else f"{date_pat}{sep}{time_pat}"
                )
                patterns.append((combined, has_era))

        return tuple(patterns)
    except (unknown_locale_error_class, ValueError, RuntimeError, AttributeError):
        return ()


# ==============================================================================
# TOKEN-BASED BABEL-TO-STRPTIME CONVERTER
# ==============================================================================


_BABEL_TOKEN_MAP: dict[str, str | None] = {
    "yyyy": "%Y",
    "yy": "%y",
    "y": "%Y",
    "MMMM": "%B",
    "MMM": "%b",
    "MM": "%m",
    "M": "%m",
    "LLLL": "%B",
    "LLL": "%b",
    "LL": "%m",
    "L": "%m",
    "dd": "%d",
    "d": "%d",
    "EEEE": "%A",
    "EEE": "%a",
    "E": "%a",
    "cccc": "%A",
    "ccc": "%a",
    "cc": "%w",
    "c": "%w",
    "GGGG": None,
    "GGG": None,
    "GG": None,
    "G": None,
    "HH": "%H",
    "H": "%H",
    "hh": "%I",
    "h": "%I",
    "mm": "%M",
    "m": "%M",
    "ss": "%S",
    "s": "%S",
    "SSSSSS": "%f",
    "SSSSS": "%f",
    "SSSS": "%f",
    "SSS": "%f",
    "SS": "%f",
    "S": "%f",
    "a": "%p",
    "kk": "%H",
    "k": "%H",
    "KK": "%I",
    "K": "%I",
    "ZZZZZ": "%z",
    "ZZZZ": None,
    "ZZZ": "%z",
    "ZZ": "%z",
    "Z": "%z",
    "xxxxx": "%z",
    "xxxx": "%z",
    "xxx": "%z",
    "xx": "%z",
    "x": "%z",
    "XXXXX": "%z",
    "XXXX": "%z",
    "XXX": "%z",
    "XX": "%z",
    "X": "%z",
    "zzzz": None,
    "zzz": None,
    "zz": None,
    "z": None,
    "vvvv": None,
    "v": None,
    "VVVV": None,
    "VVV": None,
    "VV": None,
    "V": None,
    "OOOO": None,
    "O": None,
}

_ERA_STRINGS: tuple[str, ...] = (
    "Anno Domini",
    "Before Christ",
    "Common Era",
    "Before Common Era",
    "A.D.",
    "B.C.",
    "C.E.",
    "BCE",
    "AD",
    "BC",
    "CE",
)


def _is_word_boundary(text: str, idx: int, *, is_start: bool) -> bool:
    """Check whether a position is a word boundary."""
    if is_start:
        return idx == 0 or not text[idx - 1].isalnum()
    return idx >= len(text) or not text[idx].isalnum()


def _extract_era_strings_from_babel_locale(babel_locale: Any) -> list[str]:
    """Extract localized era strings from one Babel locale."""
    localized_eras: list[str] = []
    if not hasattr(babel_locale, "eras") or not babel_locale.eras:
        return localized_eras

    for width_key in ("wide", "abbreviated", "narrow"):
        era_dict = babel_locale.eras.get(width_key, {})
        for era_idx in (0, 1):
            era_text = era_dict.get(era_idx)
            if era_text and era_text not in localized_eras:
                localized_eras.append(era_text)
    return localized_eras


@lru_cache(maxsize=64)
def _get_localized_era_strings(locale_code: str) -> tuple[str, ...]:
    """Get cached localized era strings for one locale."""
    if not is_babel_available():
        return ()

    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()

    try:
        babel_locale = locale_class.parse(locale_code)
        return tuple(_extract_era_strings_from_babel_locale(babel_locale))
    except (unknown_locale_error_class, ValueError):
        return ()


def _strip_era(value: str, locale_code: str | None = None) -> str:
    """Strip era designations from a date string."""
    era_strings: list[str] = list(_ERA_STRINGS)

    if locale_code is not None:
        localized = _get_localized_era_strings(locale_code)
        for era_text in localized:
            if era_text not in era_strings:
                era_strings.append(era_text)

    result = value
    for era in era_strings:
        upper_result = result.upper()
        upper_era = era.upper()
        idx = upper_result.find(upper_era)
        if idx != -1:
            end_idx = idx + len(era)
            if _is_word_boundary(result, idx, is_start=True) and _is_word_boundary(
                result, end_idx, is_start=False
            ):
                result = result[:idx] + result[end_idx:]
    return " ".join(result.split())


def _preprocess_datetime_input(
    value: str, locale_code: str | None = None, *, has_era: bool
) -> str:
    """Strip era text when a pattern requires era preprocessing."""
    if has_era:
        return _strip_era(value, locale_code)
    return value


def _tokenize_babel_pattern(pattern: str) -> list[str]:
    """Tokenize a CLDR pattern into atomic tokens."""
    tokens: list[str] = []
    i = 0
    n = len(pattern)

    while i < n:
        char = pattern[i]

        if char == "'":
            if i + 1 < n and pattern[i + 1] == "'":
                tokens.append("'")
                i += 2
                continue

            i += 1
            literal_chars: list[str] = []

            while i < n:
                if pattern[i] == "'":
                    if i + 1 < n and pattern[i + 1] == "'":
                        literal_chars.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    literal_chars.append(pattern[i])
                    i += 1

            if literal_chars:
                tokens.append("".join(literal_chars))
            continue

        if char.isalpha():
            j = i + 1
            while j < n and pattern[j] == char:
                j += 1
            tokens.append(pattern[i:j])
            i = j
            continue

        tokens.append(char)
        i += 1

    return tokens


def _babel_to_strptime(babel_pattern: str) -> tuple[str, bool]:
    """Convert one CLDR date/time pattern to a Python strptime pattern."""
    tokens = _tokenize_babel_pattern(babel_pattern)
    result_parts: list[str] = []
    has_era = False

    for token in tokens:
        if token in _BABEL_TOKEN_MAP:
            mapped = _BABEL_TOKEN_MAP[token]
            if mapped is None:
                if token.startswith("G"):
                    has_era = True
                if result_parts and result_parts[-1].strip() == "":
                    result_parts.pop()
            else:
                result_parts.append(mapped)
        else:
            result_parts.append(token)

    return ("".join(result_parts).strip(), has_era)


def clear_date_caches() -> None:
    """Clear cached locale-specific date and datetime parsing patterns."""
    _get_date_patterns.cache_clear()
    _get_datetime_patterns.cache_clear()
    _get_localized_era_strings.cache_clear()
