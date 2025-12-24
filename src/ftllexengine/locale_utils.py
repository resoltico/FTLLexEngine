"""Locale utilities for BCP-47 to POSIX conversion.

Centralizes locale format normalization used throughout the codebase.
Provides canonical locale handling to ensure consistent cache keys and lookups.

Python 3.13+.
"""

from __future__ import annotations

import functools
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babel import Locale

__all__ = [
    "get_babel_locale",
    "get_system_locale",
    "normalize_locale",
]


def normalize_locale(locale_code: str) -> str:
    """Convert BCP-47 locale code to POSIX format for Babel.

    BCP-47 uses hyphens (en-US), while Babel/POSIX uses underscores (en_US).
    This function performs the necessary conversion for Babel API compatibility.

    This is the canonical normalization function. All locale handling should
    normalize at the system boundary (entry point) using this function, then
    use the normalized form for cache keys and lookups.

    Args:
        locale_code: BCP-47 locale code (e.g., "en-US", "pt-BR")

    Returns:
        POSIX-formatted locale code (e.g., "en_US", "pt_BR")

    Example:
        >>> normalize_locale("en-US")
        'en_US'
        >>> normalize_locale("pt-BR")
        'pt_BR'
        >>> normalize_locale("en")  # Already normalized
        'en'
    """
    return locale_code.replace("-", "_")


@functools.lru_cache(maxsize=128)
def get_babel_locale(locale_code: str) -> Locale:
    """Get a Babel Locale object with caching.

    Parses the locale code once and caches the result. This avoids repeated
    parsing overhead in hot paths like plural rule selection.

    Thread-safe via lru_cache internal locking.

    Args:
        locale_code: Locale code (BCP-47 or POSIX format accepted)

    Returns:
        Babel Locale object

    Raises:
        babel.core.UnknownLocaleError: If locale is not recognized
        ValueError: If locale format is invalid

    Example:
        >>> locale = get_babel_locale("en-US")
        >>> locale.language
        'en'
        >>> locale.territory
        'US'
    """
    # Lazy import: Babel loads CLDR data at import time; defer until needed
    from babel import Locale  # noqa: PLC0415

    normalized = normalize_locale(locale_code)
    return Locale.parse(normalized)


def get_system_locale() -> str:
    """Detect system locale from environment variables.

    Checks standard POSIX environment variables in order of precedence:
    1. LC_ALL (overrides all)
    2. LC_MESSAGES (for message catalogs)
    3. LANG (default locale)

    Normalizes the result to POSIX format for Babel compatibility.

    Returns:
        Detected locale code in POSIX format, or "en_US" if not determinable

    Example:
        >>> import os
        >>> os.environ['LANG'] = 'de_DE.UTF-8'
        >>> get_system_locale()
        'de_DE'
    """
    # Check environment variables in order of precedence
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX", ""):
            # Strip encoding suffix (e.g., ".UTF-8")
            locale_code = value.split(".")[0]
            # Normalize to ensure consistent format
            return normalize_locale(locale_code)

    # Default fallback
    return "en_US"
