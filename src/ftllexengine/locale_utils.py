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


def get_system_locale(*, raise_on_failure: bool = False) -> str:
    """Detect system locale from OS and environment variables.

    Detection order:
    1. Python locale.getlocale() (OS-level locale)
    2. LC_ALL environment variable (overrides all)
    3. LC_MESSAGES environment variable (for message catalogs)
    4. LANG environment variable (default locale)

    Normalizes the result to POSIX format for Babel compatibility.
    Filters out "C" and "POSIX" pseudo-locales.

    Args:
        raise_on_failure: If True, raise RuntimeError when locale cannot be
            determined. If False (default), return "en_US" as fallback.

    Returns:
        Detected locale code in POSIX format.
        Returns "en_US" if not determinable and raise_on_failure is False.

    Raises:
        RuntimeError: If raise_on_failure is True and locale cannot be determined.

    Example:
        >>> import os
        >>> os.environ['LANG'] = 'de_DE.UTF-8'
        >>> get_system_locale()
        'de_DE'

        >>> get_system_locale(raise_on_failure=True)  # May raise if no locale set
        'de_DE'
    """
    import locale as locale_module  # noqa: PLC0415

    # Try OS-level locale detection first
    try:
        system_locale, _ = locale_module.getlocale()
        if system_locale and system_locale not in ("C", "POSIX"):
            # Strip encoding suffix if present
            if "." in system_locale:
                system_locale = system_locale.split(".")[0]
            return normalize_locale(system_locale)
    except (ValueError, AttributeError):
        pass

    # Fall back to environment variables in order of precedence
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX", ""):
            # Strip encoding suffix (e.g., ".UTF-8")
            locale_code = value.split(".")[0]
            # Normalize to ensure consistent format
            return normalize_locale(locale_code)

    # No locale detected
    if raise_on_failure:
        msg = (
            "Could not determine system locale. "
            "Set LC_ALL, LC_MESSAGES, or LANG environment variable."
        )
        raise RuntimeError(msg)

    # Default fallback
    return "en_US"
