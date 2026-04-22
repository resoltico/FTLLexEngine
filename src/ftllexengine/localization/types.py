"""Compatibility re-export facade for localization semantic aliases.

The canonical definitions live in ``ftllexengine.core.semantic_types`` so lower
layers can annotate locale and resource boundaries without importing the
localization package. This module remains as the stable localization namespace
for callers that prefer ``ftllexengine.localization``-scoped imports.
"""

from __future__ import annotations

from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId, ResourceId

__all__ = ["FTLSource", "LocaleCode", "MessageId", "ResourceId"]
