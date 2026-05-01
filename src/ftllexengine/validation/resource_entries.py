"""Entry collection and reference checks for resource validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.diagnostics import ValidationWarning, WarningSeverity
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax import Attribute, Message, Resource, Term
from ftllexengine.syntax.reference_extraction import extract_references

from .resource_common import get_entry_position

__all__ = ["check_undefined_references", "collect_entries"]

if TYPE_CHECKING:
    from ftllexengine.syntax.cursor import LineOffsetCache


def _check_entry(
    entry: Message | Term,
    *,
    kind: str,
    entry_name: str,
    attributes: tuple[Attribute, ...],
    seen_ids: set[str],
    known_ids: frozenset[str] | None,
    line_cache: LineOffsetCache,
    warnings: list[ValidationWarning],
) -> None:
    """Check one message or term for duplicate, shadow, and attribute issues."""
    if entry_name in seen_ids:
        line, column = get_entry_position(entry, line_cache)
        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_DUPLICATE_ID,
                message=(
                    f"Duplicate {kind} ID '{entry_name}' (later definition will overwrite earlier)"
                ),
                context=entry_name,
                line=line,
                column=column,
                severity=WarningSeverity.WARNING,
            )
        )
    seen_ids.add(entry_name)

    if known_ids and entry_name in known_ids:
        line, column = get_entry_position(entry, line_cache)
        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_SHADOW_WARNING,
                message=(
                    f"{kind.capitalize()} '{entry_name}' shadows existing {kind} "
                    "(this definition will override the earlier one)"
                ),
                context=entry_name,
                line=line,
                column=column,
                severity=WarningSeverity.WARNING,
            )
        )

    seen_attr_ids: set[str] = set()
    for attr in attributes:
        attr_name = attr.id.name
        if attr_name in seen_attr_ids:
            line, column = get_entry_position(entry, line_cache)
            warnings.append(
                ValidationWarning(
                    code=DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE,
                    message=(
                        f"{kind.capitalize()} '{entry_name}' has duplicate attribute "
                        f"'{attr_name}' (later will override earlier)"
                    ),
                    context=f"{entry_name}.{attr_name}",
                    line=line,
                    column=column,
                    severity=WarningSeverity.WARNING,
                )
            )
        seen_attr_ids.add(attr_name)


def collect_entries(
    resource: Resource,
    line_cache: LineOffsetCache,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> tuple[dict[str, Message], dict[str, Term], list[ValidationWarning]]:
    """Collect message and term entries while recording structural warnings."""
    warnings: list[ValidationWarning] = []
    seen_message_ids: set[str] = set()
    seen_term_ids: set[str] = set()
    messages_dict: dict[str, Message] = {}
    terms_dict: dict[str, Term] = {}

    for entry in resource.entries:
        match entry:
            case Message(id=msg_id, value=value, attributes=attributes):
                _check_entry(
                    entry,
                    kind="message",
                    entry_name=msg_id.name,
                    attributes=attributes,
                    seen_ids=seen_message_ids,
                    known_ids=known_messages,
                    line_cache=line_cache,
                    warnings=warnings,
                )
                messages_dict[msg_id.name] = entry

                if value is None and len(attributes) == 0:  # pragma: no cover
                    line, column = get_entry_position(entry, line_cache)  # pragma: no cover
                    warnings.append(  # pragma: no cover
                        ValidationWarning(
                            code=DiagnosticCode.VALIDATION_NO_VALUE_OR_ATTRS,
                            message=(f"Message '{msg_id.name}' has neither value nor attributes"),
                            context=msg_id.name,
                            line=line,
                            column=column,
                            severity=WarningSeverity.WARNING,
                        )
                    )
            case Term(id=term_id, attributes=attributes):
                _check_entry(
                    entry,
                    kind="term",
                    entry_name=term_id.name,
                    attributes=attributes,
                    seen_ids=seen_term_ids,
                    known_ids=known_terms,
                    line_cache=line_cache,
                    warnings=warnings,
                )
                terms_dict[term_id.name] = entry

    return messages_dict, terms_dict, warnings


def _base_reference(ref: str) -> str:
    """Return the entry id portion of a possibly attribute-qualified reference."""
    return ref.split(".", 1)[0] if "." in ref else ref


def _append_missing_reference_warnings(
    refs: frozenset[str] | set[str],
    *,
    owner_label: str,
    target_kind: str,
    available_ids: frozenset[str] | set[str],
    context_prefix: str,
    line: int | None,
    column: int | None,
    warnings: list[ValidationWarning],
) -> None:
    """Append warnings for references that target ids absent from the known set."""
    for ref in refs:
        base_ref = _base_reference(ref)
        if base_ref in available_ids:
            continue

        display_ref = f"{context_prefix}{base_ref}"
        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
                message=(f"{owner_label} references undefined {target_kind} '{display_ref}'"),
                context=display_ref,
                line=line,
                column=column,
                severity=WarningSeverity.CRITICAL,
            )
        )


def check_undefined_references(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    line_cache: LineOffsetCache,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> list[ValidationWarning]:
    """Return warnings for references that point to unknown messages or terms."""
    warnings: list[ValidationWarning] = []

    all_messages = set(messages_dict)
    all_terms = set(terms_dict)
    if known_messages is not None:
        all_messages |= known_messages
    if known_terms is not None:
        all_terms |= known_terms

    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)
        line, column = get_entry_position(message, line_cache)

        _append_missing_reference_warnings(
            msg_refs,
            owner_label=f"Message '{msg_name}'",
            target_kind="message",
            available_ids=all_messages,
            context_prefix="",
            line=line,
            column=column,
            warnings=warnings,
        )
        _append_missing_reference_warnings(
            term_refs,
            owner_label=f"Message '{msg_name}'",
            target_kind="term",
            available_ids=all_terms,
            context_prefix="-",
            line=line,
            column=column,
            warnings=warnings,
        )

    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)
        line, column = get_entry_position(term, line_cache)

        _append_missing_reference_warnings(
            msg_refs,
            owner_label=f"Term '-{term_name}'",
            target_kind="message",
            available_ids=all_messages,
            context_prefix="",
            line=line,
            column=column,
            warnings=warnings,
        )
        _append_missing_reference_warnings(
            term_refs,
            owner_label=f"Term '-{term_name}'",
            target_kind="term",
            available_ids=all_terms,
            context_prefix="-",
            line=line,
            column=column,
            warnings=warnings,
        )

    return warnings
