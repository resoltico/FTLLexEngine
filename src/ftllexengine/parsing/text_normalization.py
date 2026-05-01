"""Helpers for normalizing human-entered parsing inputs."""

from __future__ import annotations

_BIDI_FORMAT_TRANSLATION = str.maketrans(
    "",
    "",
    (
        "\u061c"  # ARABIC LETTER MARK
        "\u200e"  # LEFT-TO-RIGHT MARK
        "\u200f"  # RIGHT-TO-LEFT MARK
        "\u202a"  # LEFT-TO-RIGHT EMBEDDING
        "\u202b"  # RIGHT-TO-LEFT EMBEDDING
        "\u202c"  # POP DIRECTIONAL FORMATTING
        "\u202d"  # LEFT-TO-RIGHT OVERRIDE
        "\u202e"  # RIGHT-TO-LEFT OVERRIDE
        "\u2066"  # LEFT-TO-RIGHT ISOLATE
        "\u2067"  # RIGHT-TO-LEFT ISOLATE
        "\u2068"  # FIRST STRONG ISOLATE
        "\u2069"  # POP DIRECTIONAL ISOLATE
    ),
)


def strip_bidi_format_chars(value: str) -> str:
    """Remove invisible bidi-format controls from user-facing strings.

    Locale renderers and Fluent's isolation mode can legitimately inject
    formatting-only directionality marks around otherwise parseable content.
    Parsing APIs normalize them away so users can roundtrip copied UI text
    without having to pre-clean invisible characters themselves.
    """
    return value.translate(_BIDI_FORMAT_TRANSLATION)
