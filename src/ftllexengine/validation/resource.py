"""FTL resource validation.

Provides standalone validation for FTL resources without requiring
a FluentBundle instance. Useful for CI/CD pipelines, linters, and
tooling that needs to validate FTL files without runtime resolution.

Architecture:
    - validate_resource(): Main entry point, orchestrates validation passes
    - _extract_syntax_errors(): Pass 1 - Convert Junk entries to ValidationError
    - _collect_entries(): Pass 2 - Collect messages/terms, check duplicates
    - _check_undefined_references(): Pass 3 - Validate message/term references
    - _detect_circular_references(): Pass 4 - Check for reference cycles

Python 3.13+.
"""

import logging

from ftllexengine.analysis.graph import detect_cycles
from ftllexengine.diagnostics import (
    FluentSyntaxError,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from ftllexengine.introspection import extract_references
from ftllexengine.syntax import Junk, Message, Resource, Term
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser import FluentParserV1

logger = logging.getLogger(__name__)


def _extract_syntax_errors(
    resource: Resource,
    source: str,
) -> list[ValidationError]:
    """Extract syntax errors from Junk entries.

    Converts Junk AST nodes (unparseable content) to structured
    ValidationError objects with line/column information.

    Args:
        resource: Parsed Resource AST (may contain Junk entries)
        source: Original FTL source for position calculation

    Returns:
        List of ValidationError objects for each Junk entry
    """
    errors: list[ValidationError] = []

    for entry in resource.entries:
        if isinstance(entry, Junk):
            line: int | None = None
            column: int | None = None
            if entry.span:
                cursor = Cursor(source, entry.span.start)
                line, column = cursor.compute_line_col()

            errors.append(
                ValidationError(
                    code="parse-error",
                    message="Failed to parse FTL content",
                    content=entry.content,
                    line=line,
                    column=column,
                )
            )

    return errors


def _collect_entries(
    resource: Resource,
) -> tuple[dict[str, Message], dict[str, Term], list[ValidationWarning]]:
    """Collect message/term entries and check for structural issues.

    Performs the following checks:
    - Duplicate message/term IDs
    - Messages without values or attributes

    Args:
        resource: Parsed Resource AST

    Returns:
        Tuple of (messages_dict, terms_dict, warnings)
    """
    warnings: list[ValidationWarning] = []
    seen_ids: set[str] = set()
    messages_dict: dict[str, Message] = {}
    terms_dict: dict[str, Term] = {}

    for entry in resource.entries:
        match entry:
            case Message(id=msg_id, value=value, attributes=attributes):
                # Check for duplicate message IDs
                if msg_id.name in seen_ids:
                    warnings.append(
                        ValidationWarning(
                            code="duplicate-id",
                            message=(
                                f"Duplicate message ID '{msg_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=msg_id.name,
                        )
                    )
                seen_ids.add(msg_id.name)
                messages_dict[msg_id.name] = entry

                # Check for messages without values (only attributes)
                if value is None and len(attributes) == 0:
                    warnings.append(
                        ValidationWarning(
                            code="no-value-or-attributes",
                            message=f"Message '{msg_id.name}' has neither value nor attributes",
                            context=msg_id.name,
                        )
                    )

            case Term(id=term_id):
                # Check for duplicate term IDs
                if term_id.name in seen_ids:
                    warnings.append(
                        ValidationWarning(
                            code="duplicate-id",
                            message=(
                                f"Duplicate term ID '{term_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=term_id.name,
                        )
                    )
                seen_ids.add(term_id.name)
                terms_dict[term_id.name] = entry

    return messages_dict, terms_dict, warnings


def _check_undefined_references(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
) -> list[ValidationWarning]:
    """Check for undefined message and term references.

    Validates that all message and term references in the resource
    point to defined entries.

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes

    Returns:
        List of warnings for undefined references
    """
    warnings: list[ValidationWarning] = []

    # Check message references
    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)

        for ref in msg_refs:
            if ref not in messages_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Message '{msg_name}' references undefined message '{ref}'",
                        context=ref,
                    )
                )

        for ref in term_refs:
            if ref not in terms_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Message '{msg_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                    )
                )

    # Check term references
    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)

        for ref in msg_refs:
            if ref not in messages_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Term '-{term_name}' references undefined message '{ref}'",
                        context=ref,
                    )
                )

        for ref in term_refs:
            if ref not in terms_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Term '-{term_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                    )
                )

    return warnings


def _detect_circular_references(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
) -> list[ValidationWarning]:
    """Detect circular dependencies in messages and terms.

    Uses iterative DFS via analysis.graph module to avoid stack overflow
    on deep dependency chains.

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes

    Returns:
        List of warnings for circular references
    """
    warnings: list[ValidationWarning] = []
    seen_cycle_keys: set[str] = set()

    # Build dependency graph for messages
    message_deps: dict[str, set[str]] = {}
    for msg_name, message in messages_dict.items():
        msg_refs, _ = extract_references(message)
        message_deps[msg_name] = set(msg_refs)

    # Build dependency graph for terms
    term_deps: dict[str, set[str]] = {}
    for term_name, term in terms_dict.items():
        _, term_refs = extract_references(term)
        term_deps[term_name] = set(term_refs)

    # Detect message cycles
    for cycle in detect_cycles(message_deps):
        cycle_key = " -> ".join(sorted(set(cycle)))
        if cycle_key not in seen_cycle_keys:
            seen_cycle_keys.add(cycle_key)
            cycle_str = " -> ".join(cycle)
            warnings.append(
                ValidationWarning(
                    code="circular-reference",
                    message=f"Circular message reference: {cycle_str}",
                    context=cycle_str,
                )
            )

    # Detect term cycles
    for cycle in detect_cycles(term_deps):
        cycle_key = " -> ".join(sorted(set(cycle)))
        if cycle_key not in seen_cycle_keys:
            seen_cycle_keys.add(cycle_key)
            cycle_str = " -> ".join([f"-{t}" for t in cycle])
            warnings.append(
                ValidationWarning(
                    code="circular-reference",
                    message=f"Circular term reference: {cycle_str}",
                    context=cycle_str,
                )
            )

    return warnings


def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
) -> ValidationResult:
    """Validate FTL resource without adding to a bundle.

    Standalone validation function for CI/CD pipelines and tooling.
    Performs syntax validation (errors) and semantic validation (warnings).

    Validation passes:
    1. Syntax errors: Parse failures (Junk entries)
    2. Structural: Duplicate IDs, messages without values
    3. References: Undefined message/term references
    4. Cycles: Circular dependency detection

    Args:
        source: FTL file content
        parser: Optional parser instance (creates default if not provided)

    Returns:
        ValidationResult with parse errors and semantic warnings

    Example:
        >>> from ftllexengine.validation import validate_resource
        >>> result = validate_resource(ftl_source)
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(f"Error [{error.code}]: {error.message}")
        >>> for warning in result.warnings:
        ...     print(f"Warning [{warning.code}]: {warning.message}")

    Thread Safety:
        Thread-safe. Creates isolated parser if not provided.
    """
    if parser is None:
        parser = FluentParserV1()

    try:
        resource = parser.parse(source)

        # Pass 1: Extract syntax errors from Junk entries
        errors = _extract_syntax_errors(resource, source)

        # Pass 2: Collect entries and check structural issues
        messages_dict, terms_dict, structure_warnings = _collect_entries(resource)

        # Pass 3: Check undefined references
        ref_warnings = _check_undefined_references(messages_dict, terms_dict)

        # Pass 4: Detect circular dependencies
        cycle_warnings = _detect_circular_references(messages_dict, terms_dict)

        # Combine all warnings
        all_warnings = structure_warnings + ref_warnings + cycle_warnings

        logger.debug(
            "Validated resource: %d errors, %d warnings",
            len(errors),
            len(all_warnings),
        )

        return ValidationResult(
            errors=tuple(errors),
            warnings=tuple(all_warnings),
            annotations=(),
        )

    except FluentSyntaxError as e:
        logger.error("Critical validation error: %s", e)
        error = ValidationError(
            code="critical-parse-error",
            message=str(e),
            content=str(e),
        )
        return ValidationResult(errors=(error,), warnings=(), annotations=())
