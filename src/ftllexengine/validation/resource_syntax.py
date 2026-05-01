"""Syntax-error extraction helpers for resource validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.diagnostics import ValidationError
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax import Junk, Resource

from .resource_common import get_entry_position

__all__ = ["extract_syntax_errors"]

if TYPE_CHECKING:
    from ftllexengine.syntax.cursor import LineOffsetCache


def _annotation_to_diagnostic_code(annotation_code: str) -> DiagnosticCode:
    """Resolve one parser annotation code to the matching diagnostic enum."""
    try:
        return DiagnosticCode[annotation_code]
    except KeyError:
        return DiagnosticCode.PARSE_JUNK


def extract_syntax_errors(
    resource: Resource,
    line_cache: LineOffsetCache,
) -> list[ValidationError]:
    """Convert Junk entries into structured validation errors."""
    errors: list[ValidationError] = []

    for entry in resource.entries:
        if not isinstance(entry, Junk):
            continue

        if entry.annotations:
            for annotation in entry.annotations:
                ann_line: int | None = None
                ann_column: int | None = None
                if annotation.span:
                    ann_line, ann_column = line_cache.get_line_col(annotation.span.start)
                elif entry.span:
                    ann_line, ann_column = get_entry_position(entry, line_cache)

                errors.append(
                    ValidationError(
                        code=_annotation_to_diagnostic_code(annotation.code),
                        message=annotation.message,
                        content=entry.content,
                        line=ann_line,
                        column=ann_column,
                    )
                )
            continue

        line: int | None = None
        column: int | None = None
        if entry.span:
            line, column = get_entry_position(entry, line_cache)

        errors.append(
            ValidationError(
                code=DiagnosticCode.VALIDATION_PARSE_ERROR,
                message="Failed to parse FTL content",
                content=entry.content,
                line=line,
                column=column,
            )
        )

    return errors
