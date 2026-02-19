"""Type aliases for the localization domain.

Provides semantic type aliases used throughout the localization package
and by user code when annotating FluentLocalization call sites.

Python 3.13+. Zero external dependencies.
"""



__all__ = [
    "FTLSource",
    "LocaleCode",
    "MessageId",
    "ResourceId",
]

type MessageId = str
"""Identifier for a Fluent message (e.g., 'welcome', 'error-404')."""

type LocaleCode = str
"""BCP-47 locale code (e.g., 'en', 'lv', 'zh-Hans-CN')."""

type ResourceId = str
"""FTL resource file identifier (e.g., 'main.ftl', 'errors.ftl')."""

type FTLSource = str
"""Raw FTL source text as a Python string."""
