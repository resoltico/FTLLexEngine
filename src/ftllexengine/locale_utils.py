"""Locale utilities for BCP-47 to POSIX conversion.

Centralizes locale format normalization used throughout the codebase.
Python 3.13+.
"""


def normalize_locale(locale_code: str) -> str:
    """Convert BCP-47 locale code to POSIX format for Babel.

    BCP-47 uses hyphens (en-US), while Babel/POSIX uses underscores (en_US).
    This function performs the necessary conversion for Babel API compatibility.

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
