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

from ftllexengine.analysis.graph import detect_cycles, make_cycle_key
from ftllexengine.diagnostics import (
    FluentSyntaxError,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from ftllexengine.introspection import extract_references
from ftllexengine.syntax import Junk, Message, Resource, Term
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.syntax.parser import FluentParserV1

logger = logging.getLogger(__name__)


def _extract_syntax_errors(
    resource: Resource,
    source: str,
) -> list[ValidationError]:
    """Extract syntax errors from Junk entries.

    Converts Junk AST nodes (unparseable content) to structured
    ValidationError objects with line/column information.

    Uses LineOffsetCache for O(n + M log n) total complexity instead of
    O(M*N) when using Cursor.compute_line_col() for each entry.

    Args:
        resource: Parsed Resource AST (may contain Junk entries)
        source: Original FTL source for position calculation

    Returns:
        List of ValidationError objects for each Junk entry
    """
    errors: list[ValidationError] = []

    # Build line offset cache once (O(n)) for efficient position lookups (O(log n) each)
    line_cache: LineOffsetCache | None = None

    for entry in resource.entries:
        if isinstance(entry, Junk):
            line: int | None = None
            column: int | None = None
            if entry.span:
                # Lazy initialization of cache - only create if we have Junk entries
                if line_cache is None:
                    line_cache = LineOffsetCache(source)
                line, column = line_cache.get_line_col(entry.span.start)

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
    source: str,
) -> tuple[dict[str, Message], dict[str, Term], list[ValidationWarning]]:
    """Collect message/term entries and check for structural issues.

    Performs the following checks:
    - Duplicate message/term IDs
    - Messages without values or attributes

    Args:
        resource: Parsed Resource AST
        source: Original FTL source for position calculation

    Returns:
        Tuple of (messages_dict, terms_dict, warnings)
    """
    warnings: list[ValidationWarning] = []
    seen_ids: set[str] = set()
    messages_dict: dict[str, Message] = {}
    terms_dict: dict[str, Term] = {}

    # Build line offset cache once for efficient position lookups
    line_cache: LineOffsetCache | None = None

    def _get_position(entry: Message | Term) -> tuple[int | None, int | None]:
        """Get line/column from entry's span if available."""
        nonlocal line_cache
        if entry.span:
            if line_cache is None:
                line_cache = LineOffsetCache(source)
            return line_cache.get_line_col(entry.span.start)
        return None, None

    for entry in resource.entries:
        match entry:
            case Message(id=msg_id, value=value, attributes=attributes):
                # Check for duplicate message IDs
                if msg_id.name in seen_ids:
                    line, column = _get_position(entry)
                    warnings.append(
                        ValidationWarning(
                            code="duplicate-id",
                            message=(
                                f"Duplicate message ID '{msg_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=msg_id.name,
                            line=line,
                            column=column,
                        )
                    )
                seen_ids.add(msg_id.name)
                messages_dict[msg_id.name] = entry

                # Check for messages without values (only attributes)
                if value is None and len(attributes) == 0:
                    line, column = _get_position(entry)
                    warnings.append(
                        ValidationWarning(
                            code="no-value-or-attributes",
                            message=f"Message '{msg_id.name}' has neither value nor attributes",
                            context=msg_id.name,
                            line=line,
                            column=column,
                        )
                    )

            case Term(id=term_id):
                # Check for duplicate term IDs
                if term_id.name in seen_ids:
                    line, column = _get_position(entry)
                    warnings.append(
                        ValidationWarning(
                            code="duplicate-id",
                            message=(
                                f"Duplicate term ID '{term_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=term_id.name,
                            line=line,
                            column=column,
                        )
                    )
                seen_ids.add(term_id.name)
                terms_dict[term_id.name] = entry

    return messages_dict, terms_dict, warnings


def _check_undefined_references(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    source: str,
) -> list[ValidationWarning]:
    """Check for undefined message and term references.

    Validates that all message and term references in the resource
    point to defined entries.

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes
        source: Original FTL source for position calculation

    Returns:
        List of warnings for undefined references
    """
    warnings: list[ValidationWarning] = []

    # Build line offset cache once for efficient position lookups
    line_cache: LineOffsetCache | None = None

    def _get_position(entry: Message | Term) -> tuple[int | None, int | None]:
        """Get line/column from entry's span if available."""
        nonlocal line_cache
        if entry.span:
            if line_cache is None:
                line_cache = LineOffsetCache(source)
            return line_cache.get_line_col(entry.span.start)
        return None, None

    # Check message references
    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)
        line, column = _get_position(message)

        for ref in msg_refs:
            if ref not in messages_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Message '{msg_name}' references undefined message '{ref}'",
                        context=ref,
                        line=line,
                        column=column,
                    )
                )

        for ref in term_refs:
            if ref not in terms_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Message '{msg_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                        line=line,
                        column=column,
                    )
                )

    # Check term references
    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)
        line, column = _get_position(term)

        for ref in msg_refs:
            if ref not in messages_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Term '-{term_name}' references undefined message '{ref}'",
                        context=ref,
                        line=line,
                        column=column,
                    )
                )

        for ref in term_refs:
            if ref not in terms_dict:
                warnings.append(
                    ValidationWarning(
                        code="undefined-reference",
                        message=f"Term '-{term_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                        line=line,
                        column=column,
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

    Builds a unified dependency graph with type-prefixed nodes to detect:
    - Message-only cycles (msg:A -> msg:B -> msg:A)
    - Term-only cycles (term:A -> term:B -> term:A)
    - Cross-type cycles (msg:A -> term:B -> msg:A)

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes

    Returns:
        List of warnings for circular references
    """
    warnings: list[ValidationWarning] = []
    seen_cycle_keys: set[str] = set()

    # Build unified dependency graph with type-prefixed nodes
    # This enables detection of cross-type cycles (message -> term -> message)
    unified_deps: dict[str, set[str]] = {}

    # Add message nodes with all their dependencies (both message and term refs)
    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)
        node_key = f"msg:{msg_name}"
        deps: set[str] = set()
        # Message references: only add if target exists
        for ref in msg_refs:
            if ref in messages_dict:
                deps.add(f"msg:{ref}")
        # Term references: only add if target exists
        for ref in term_refs:
            if ref in terms_dict:
                deps.add(f"term:{ref}")
        unified_deps[node_key] = deps

    # Add term nodes with all their dependencies (both message and term refs)
    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)
        node_key = f"term:{term_name}"
        deps = set()
        # Message references: only add if target exists
        for ref in msg_refs:
            if ref in messages_dict:
                deps.add(f"msg:{ref}")
        # Term references: only add if target exists
        for ref in term_refs:
            if ref in terms_dict:
                deps.add(f"term:{ref}")
        unified_deps[node_key] = deps

    # Detect all cycles in the unified graph
    for cycle in detect_cycles(unified_deps):
        cycle_key = make_cycle_key(cycle)
        if cycle_key not in seen_cycle_keys:
            seen_cycle_keys.add(cycle_key)

            # Format cycle for human-readable output
            # Convert "msg:foo" -> "foo", "term:bar" -> "-bar"
            formatted_parts: list[str] = []
            for node in cycle:
                if node.startswith("msg:"):
                    formatted_parts.append(node[4:])  # Strip "msg:" prefix
                elif node.startswith("term:"):
                    formatted_parts.append(f"-{node[5:]}")  # Strip "term:", add "-"

            cycle_str = " -> ".join(formatted_parts)

            # Determine cycle type for appropriate message
            has_messages = any(n.startswith("msg:") for n in cycle)
            has_terms = any(n.startswith("term:") for n in cycle)

            if has_messages and has_terms:
                msg = f"Circular cross-reference: {cycle_str}"
            elif has_terms:
                msg = f"Circular term reference: {cycle_str}"
            else:
                msg = f"Circular message reference: {cycle_str}"

            warnings.append(
                ValidationWarning(
                    code="circular-reference",
                    message=msg,
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
        messages_dict, terms_dict, structure_warnings = _collect_entries(resource, source)

        # Pass 3: Check undefined references
        ref_warnings = _check_undefined_references(messages_dict, terms_dict, source)

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
