"""Locale utilities for BCP-47 to POSIX conversion.

Centralizes locale format normalization used throughout the codebase.
Provides canonical locale handling to ensure consistent cache keys and lookups.

Babel Import Pattern:
    Babel imports are handled through ftllexengine.core.babel_compat for
    consistency. This ensures parser-only installations work without Babel
    while providing clear error messages when Babel features are needed.

    Functions that do NOT require Babel:
    - normalize_locale() - Pure string manipulation
    - get_system_locale() - Uses only stdlib locale module

    Functions that REQUIRE Babel:
    - get_babel_locale() - Creates Babel Locale objects via babel_compat

Python 3.13+.
"""

from __future__ import annotations

import functools
import os
import re
from typing import TYPE_CHECKING

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE, MAX_LOCALE_LENGTH_HARD_LIMIT
from ftllexengine.core.babel_compat import get_locale_class, require_babel

if TYPE_CHECKING:
    from babel import Locale

    from ftllexengine.localization.types import LocaleCode

__all__ = [
    "clear_locale_cache",
    "get_babel_locale",
    "get_system_locale",
    "is_structurally_valid_locale_code",
    "normalize_locale",
    "require_locale_code",
]


# BCP-47 locale codes consist of ASCII alphanumeric subtags joined by hyphens
# or underscores. The first subtag must start with a letter. Characters outside
# this set (e.g. '/', '\x00', unicode) are never valid and can cause Babel to
# silently create a Locale object with default settings instead of raising
# UnknownLocaleError or ValueError.
_VALID_LOCALE_CODE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*([_-][a-zA-Z0-9]+)*\Z")


def is_structurally_valid_locale_code(locale_code: str) -> bool:
    """Return True if locale_code contains only BCP-47-valid characters.

    Validates structure only; does NOT verify that the locale exists in
    Babel's CLDR database. Use this as a fast pre-filter before calling
    Babel's Locale.parse() to avoid silent acceptance of malformed codes.

    Args:
        locale_code: Raw locale code string to validate.

    Returns:
        True if the code begins with an ASCII letter and then contains only
        ASCII alphanumerics joined by hyphen/underscore separators; False
        otherwise.
    """
    return bool(_VALID_LOCALE_CODE_RE.match(locale_code))


def normalize_locale(locale_code: str) -> str:
    """Convert BCP-47 locale code to canonical lowercase POSIX format for Babel.

    BCP-47 uses hyphens (en-US), while Babel/POSIX uses underscores (en_US).
    BCP-47 is case-insensitive, so this function lowercases for consistent
    cache keys and comparisons.

    This is the canonical normalization function. All locale handling should
    normalize at the system boundary (entry point) using this function, then
    use the normalized form for cache keys and lookups.

    Note:
        This function does NOT require Babel. It performs pure string manipulation.

    Args:
        locale_code: BCP-47 locale code (e.g., "en-US", "pt-BR", "EN-US")

    Returns:
        Lowercase POSIX-formatted locale code (e.g., "en_us", "pt_br")

    Example:
        >>> normalize_locale("en-US")
        'en_us'
        >>> normalize_locale("EN-US")
        'en_us'
        >>> normalize_locale("pt-BR")
        'pt_br'
        >>> normalize_locale("en")  # Already normalized
        'en'
    """
    return locale_code.replace("-", "_").lower()


def require_locale_code(value: object, field_name: str) -> LocaleCode:
    """Validate and canonicalize a locale code at a system boundary.

    Accepts only non-blank strings containing structurally valid BCP-47 / POSIX
    locale identifiers, trims surrounding whitespace, and returns the canonical
    normalized locale code used internally by FTLLexEngine.

    Args:
        value: Raw locale boundary value.
        field_name: Field name used in validation error messages.

    Returns:
        Canonical lowercase POSIX locale code.

    Raises:
        TypeError: If value is not a string.
        ValueError: If the value is blank, excessively long, or structurally invalid.
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)

    locale_code = value.strip()
    if locale_code == "":
        msg = f"{field_name} cannot be blank"
        raise ValueError(msg)

    if len(locale_code) > MAX_LOCALE_LENGTH_HARD_LIMIT:
        msg = (
            f"{field_name} exceeds maximum length of "
            f"{MAX_LOCALE_LENGTH_HARD_LIMIT} characters: "
            f"{locale_code[:50]!r}... ({len(locale_code)} characters)"
        )
        raise ValueError(msg)

    if not is_structurally_valid_locale_code(locale_code):
        msg = (
            f"Invalid {field_name}: {locale_code!r}. "
            "Locale must be ASCII alphanumeric with optional underscore or "
            "hyphen separators, beginning with a letter. "
            "Use BCP 47 format (e.g., 'en-US', 'de-DE', 'zh-Hans-CN'). "
            "Strip charset suffixes such as '.UTF-8' from POSIX locale strings."
        )
        raise ValueError(msg)

    return normalize_locale(locale_code)


def _is_pseudo_locale(locale_code: str) -> bool:
    """Return True for C/POSIX pseudo-locales, including encoded variants."""
    base = locale_code.split(".", 1)[0].split("@", 1)[0]
    return base.upper() in {"C", "POSIX"}


@functools.lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _get_babel_locale_normalized(normalized_code: str) -> Locale:
    """Get a Babel Locale object from a pre-normalized locale code with caching.

    Cache key is normalized (lowercase, underscores) so all equivalent locale
    codes map to a single cache entry. Called exclusively by get_babel_locale().

    Thread-safe via lru_cache internal locking.

    Args:
        normalized_code: Locale code already in canonical POSIX form (lowercase, underscores)

    Returns:
        Babel Locale object

    Raises:
        BabelImportError: If Babel is not installed
        babel.core.UnknownLocaleError: If locale is not recognized
        ValueError: If locale format is invalid
    """
    require_babel("get_babel_locale")
    BabelLocale = get_locale_class()  # noqa: N806 - class alias, PascalCase by convention
    return BabelLocale.parse(normalized_code)


def get_babel_locale(locale_code: str) -> Locale:
    """Get a Babel Locale object with caching.

    Normalizes the locale code before cache lookup so that "en-US", "en_US",
    and "EN-US" all resolve to a single cached Babel Locale object.

    Thread-safe via lru_cache internal locking in _get_babel_locale_normalized.

    Note:
        This function REQUIRES the optional Babel dependency.
        Install with: pip install ftllexengine[babel]

    Args:
        locale_code: Locale code (BCP-47 or POSIX format accepted)

    Returns:
        Babel Locale object

    Raises:
        BabelImportError: If Babel is not installed
        babel.core.UnknownLocaleError: If locale is not recognized
        ValueError: If locale format is invalid

    Example:
        >>> locale = get_babel_locale("en-US")
        >>> locale.language
        'en'
        >>> locale.territory
        'US'
    """
    normalized_code = require_locale_code(locale_code, "locale_code")
    return _get_babel_locale_normalized(normalized_code)


def get_system_locale(*, raise_on_failure: bool = False) -> str:
    """Detect system locale from OS and environment variables.

    Detection order:
    1. Python locale.getlocale() (OS-level locale)
    2. LC_ALL environment variable (overrides all)
    3. LC_MESSAGES environment variable (for message catalogs)
    4. LANG environment variable (default locale)

    Normalizes the result to POSIX format for Babel compatibility.
    Filters out "C" and "POSIX" pseudo-locales.

    Note:
        This function does NOT require Babel. It uses only stdlib modules.

    Args:
        raise_on_failure: If True, raise RuntimeError when locale cannot be
            determined. If False (default), return "en_us" as fallback.

    Returns:
        Detected locale code in POSIX format (lowercase, underscores).
        Returns "en_us" if not determinable and raise_on_failure is False.

    Raises:
        RuntimeError: If raise_on_failure is True and locale cannot be determined.

    Example:
        >>> import os
        >>> os.environ['LANG'] = 'de_DE.UTF-8'
        >>> get_system_locale()
        'de_de'

        >>> get_system_locale(raise_on_failure=True)  # May raise if no locale set
        'de_de'
    """
    # stdlib locale module deferred: has significant initialization overhead
    # (~5ms on some platforms). Deferring to call-time avoids penalizing the
    # parser-only import path which never calls get_system_locale().
    import locale as locale_module  # noqa: PLC0415 - deferred; stdlib locale has ~5ms init cost

    # Try OS-level locale detection first
    try:
        system_locale, _ = locale_module.getlocale()
        if system_locale:
            locale_code = system_locale.split(".", 1)[0]
            if not _is_pseudo_locale(locale_code):
                return normalize_locale(locale_code)
    except (ValueError, AttributeError):
        pass

    # Fall back to environment variables in order of precedence
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value != "":
            locale_code = value.split(".", 1)[0]
            if _is_pseudo_locale(locale_code):
                continue
            # Normalize to ensure consistent format
            return normalize_locale(locale_code)

    # No locale detected
    if raise_on_failure:
        msg = (
            "Could not determine system locale. "
            "Set LC_ALL, LC_MESSAGES, or LANG environment variable."
        )
        raise RuntimeError(msg)

    # Default fallback — normalized for consistent cache keys
    return normalize_locale("en_US")


def clear_locale_cache() -> None:
    """Clear the Babel locale cache.

    Clears all cached Babel Locale objects from get_babel_locale().
    Useful for:
    - Memory reclamation in long-running applications
    - Testing scenarios requiring fresh cache state
    - After Babel locale data updates

    Thread-safe via lru_cache internal locking.

    Note:
        This function does NOT require Babel. It clears the cache
        regardless of whether Babel is installed.

    Example:
        >>> from ftllexengine.core.locale_utils import clear_locale_cache
        >>> clear_locale_cache()  # Clears all cached Locale objects
    """
    _get_babel_locale_normalized.cache_clear()
