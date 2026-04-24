"""Shared helpers for diagnostic template builders."""

from __future__ import annotations

_DOCS_BASE = "https://projectfluent.org/fluent/guide"


def docs_url(path: str) -> str:
    """Build a stable documentation URL for one Fluent guide page."""
    return f"{_DOCS_BASE}/{path}"
