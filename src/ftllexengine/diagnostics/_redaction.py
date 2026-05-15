"""Internal helpers for redacting sensitive diagnostic payloads by default.

The library handles untrusted localization content and user input. The owning
rule here is that diagnostics should preserve enough evidence to debug safely
without copying raw payloads into logs, exceptions, or cached error objects.
"""

from __future__ import annotations

import hashlib

__all__ = [
    "fingerprint_text",
    "redacted_custom_function_failure",
    "redacted_loader_snippet",
    "redacted_parse_failure",
]

_FINGERPRINT_HEX_LEN = 16


def _fingerprint_bytes(value: str) -> tuple[int, str]:
    """Return UTF-8 byte length plus a short stable fingerprint."""
    encoded = value.encode("utf-8", errors="surrogatepass")
    digest = hashlib.blake2b(encoded, digest_size=12).hexdigest()
    return (len(encoded), digest[:_FINGERPRINT_HEX_LEN])


def fingerprint_text(value: object, *, label: str) -> str:
    """Summarize arbitrary text-like data without exposing the raw payload."""
    rendered = str(value)
    byte_length, digest = _fingerprint_bytes(rendered)
    return f"{label}[bytes={byte_length}, blake2b={digest}]"


def redacted_parse_failure(value: object, *, parse_type: str) -> str:
    """Produce a stable redacted identifier for parse failure context."""
    return fingerprint_text(value, label=f"{parse_type}_input")


def redacted_loader_snippet(value: str) -> str:
    """Summarize a malformed resource chunk without logging its content.

    Premise:
        Resource text often contains customer-visible or regulated content.

    Reason:
        Structured fingerprints let operators correlate repeated failures
        without the library becoming the leak point for the original text.
    """
    return fingerprint_text(value, label="resource_snippet")


def redacted_custom_function_failure(error: BaseException) -> str:
    """Describe a custom-function crash without disclosing exception text."""
    if error.args:
        detail = fingerprint_text(" ".join(str(arg) for arg in error.args), label="detail")
        return f"uncaught {type(error).__name__} ({detail})"
    return f"uncaught {type(error).__name__}"
