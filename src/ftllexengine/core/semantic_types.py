"""Project-wide semantic type aliases.

These aliases are the canonical low-layer home for semantic string types used
across runtime, localization, and documentation surfaces. Keeping them in the
core layer prevents lower modules from importing higher-level localization
helpers just to annotate identifiers or locale codes.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

__all__ = [
    "FTLSource",
    "LocaleCode",
    "MessageId",
    "ResourceId",
]

type MessageId = str
"""Identifier for a Fluent message (for example ``"welcome"``)."""

type LocaleCode = str
"""Locale identifier in BCP-47 or normalized POSIX form."""

type ResourceId = str
"""Logical Fluent resource identifier (for example ``"main.ftl"``)."""

type FTLSource = str
"""Raw Fluent source text before parsing."""
