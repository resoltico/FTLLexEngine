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
    - _detect_long_chains(): Pass 5 - Check for chains exceeding MAX_DEPTH
    - SemanticValidator: Pass 6 - Fluent spec compliance

Python 3.13+.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ftllexengine.analysis.graph import detect_cycles, make_cycle_key
from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import (
    FluentSyntaxError,
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.introspection import extract_references
from ftllexengine.syntax import Junk, Message, Resource, Term
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.syntax.validator import SemanticValidator

if TYPE_CHECKING:
    from ftllexengine.syntax.parser import FluentParserV1

__all__ = ["validate_resource"]

logger = logging.getLogger(__name__)


def _get_entry_position(
    entry: Message | Term,
    line_cache: LineOffsetCache,
) -> tuple[int | None, int | None]:
    """Get line/column from entry's span if available.

    Args:
        entry: Message or Term with optional span
        line_cache: Line offset cache for position lookup

    Returns:
        (line, column) tuple, or (None, None) if no span
    """
    if entry.span:
        return line_cache.get_line_col(entry.span.start)
    return None, None


def _extract_syntax_errors(
    resource: Resource,
    line_cache: LineOffsetCache,
) -> list[ValidationError]:
    """Extract syntax errors from Junk entries.

    Converts Junk AST nodes (unparseable content) to structured
    ValidationError objects with line/column information.

    Propagates annotations from Junk nodes to preserve specific error codes
    and messages from the parser. If a Junk entry has no annotations, falls
    back to a generic parse error.

    Args:
        resource: Parsed Resource AST (may contain Junk entries)
        line_cache: Shared line offset cache for position lookups

    Returns:
        List of ValidationError objects for each Junk entry
    """
    errors: list[ValidationError] = []

    for entry in resource.entries:
        if isinstance(entry, Junk):
            # Propagate annotations from Junk to preserve specific parser errors
            if entry.annotations:
                for annotation in entry.annotations:
                    # Use annotation's span if available, otherwise fall back to Junk span
                    ann_line: int | None = None
                    ann_column: int | None = None
                    if annotation.span:
                        ann_line, ann_column = line_cache.get_line_col(
                            annotation.span.start
                        )
                    elif entry.span:
                        ann_line, ann_column = line_cache.get_line_col(entry.span.start)

                    errors.append(
                        ValidationError(
                            code=annotation.code,
                            message=annotation.message,
                            content=entry.content,
                            line=ann_line,
                            column=ann_column,
                        )
                    )
            else:
                # Fallback for Junk without annotations (shouldn't happen normally)
                line: int | None = None
                column: int | None = None
                if entry.span:
                    line, column = line_cache.get_line_col(entry.span.start)

                errors.append(
                    ValidationError(
                        code=DiagnosticCode.VALIDATION_PARSE_ERROR.name,
                        message="Failed to parse FTL content",
                        content=entry.content,
                        line=line,
                        column=column,
                    )
                )

    return errors


def _collect_entries(
    resource: Resource,
    line_cache: LineOffsetCache,
) -> tuple[dict[str, Message], dict[str, Term], list[ValidationWarning]]:
    """Collect message/term entries and check for structural issues.

    Performs the following checks:
    - Duplicate message IDs (within message namespace)
    - Duplicate term IDs (within term namespace)
    - Messages without values or attributes

    Note: Per Fluent spec, messages and terms have separate namespaces.
    A message named "foo" and a term named "foo" are NOT duplicates.

    Args:
        resource: Parsed Resource AST
        line_cache: Shared line offset cache for position lookups

    Returns:
        Tuple of (messages_dict, terms_dict, warnings)
    """
    warnings: list[ValidationWarning] = []
    # Per Fluent spec, messages and terms have separate namespaces.
    # A message "foo" and a term "-foo" can coexist without conflict.
    seen_message_ids: set[str] = set()
    seen_term_ids: set[str] = set()
    messages_dict: dict[str, Message] = {}
    terms_dict: dict[str, Term] = {}

    for entry in resource.entries:
        match entry:
            case Message(id=msg_id, value=value, attributes=attributes):
                # Check for duplicate message IDs within message namespace
                if msg_id.name in seen_message_ids:
                    line, column = _get_entry_position(entry, line_cache)
                    warnings.append(
                        ValidationWarning(
                            code=DiagnosticCode.VALIDATION_DUPLICATE_ID.name,
                            message=(
                                f"Duplicate message ID '{msg_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=msg_id.name,
                            line=line,
                            column=column,
                            severity=WarningSeverity.WARNING,
                        )
                    )
                seen_message_ids.add(msg_id.name)
                messages_dict[msg_id.name] = entry

                # Check for messages without values (only attributes)
                if value is None and len(attributes) == 0:
                    line, column = _get_entry_position(entry, line_cache)
                    warnings.append(
                        ValidationWarning(
                            code=DiagnosticCode.VALIDATION_NO_VALUE_OR_ATTRS.name,
                            message=f"Message '{msg_id.name}' has neither value nor attributes",
                            context=msg_id.name,
                            line=line,
                            column=column,
                            severity=WarningSeverity.WARNING,
                        )
                    )

            case Term(id=term_id):
                # Check for duplicate term IDs within term namespace
                if term_id.name in seen_term_ids:
                    line, column = _get_entry_position(entry, line_cache)
                    warnings.append(
                        ValidationWarning(
                            code=DiagnosticCode.VALIDATION_DUPLICATE_ID.name,
                            message=(
                                f"Duplicate term ID '{term_id.name}' "
                                f"(later definition will overwrite earlier)"
                            ),
                            context=term_id.name,
                            line=line,
                            column=column,
                            severity=WarningSeverity.WARNING,
                        )
                    )
                seen_term_ids.add(term_id.name)
                terms_dict[term_id.name] = entry

    return messages_dict, terms_dict, warnings


def _check_undefined_references(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    line_cache: LineOffsetCache,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> list[ValidationWarning]:
    """Check for undefined message and term references.

    Validates that all message and term references in the resource
    point to defined entries. Optionally considers entries already
    present in a bundle for cross-resource reference validation.

    Args:
        messages_dict: Map of message IDs to Message nodes from current resource
        terms_dict: Map of term IDs to Term nodes from current resource
        line_cache: Shared line offset cache for position lookups
        known_messages: Optional set of message IDs already in bundle
        known_terms: Optional set of term IDs already in bundle

    Returns:
        List of warnings for undefined references
    """
    warnings: list[ValidationWarning] = []

    # Combine current resource entries with known bundle entries
    all_messages = set(messages_dict.keys())
    all_terms = set(terms_dict.keys())
    if known_messages is not None:
        all_messages |= known_messages
    if known_terms is not None:
        all_terms |= known_terms

    # Check message references
    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)
        line, column = _get_entry_position(message, line_cache)

        for ref in msg_refs:
            if ref not in all_messages:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name,
                        message=f"Message '{msg_name}' references undefined message '{ref}'",
                        context=ref,
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

        for ref in term_refs:
            if ref not in all_terms:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name,
                        message=f"Message '{msg_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

    # Check term references
    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)
        line, column = _get_entry_position(term, line_cache)

        for ref in msg_refs:
            if ref not in all_messages:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name,
                        message=f"Term '-{term_name}' references undefined message '{ref}'",
                        context=ref,
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

        for ref in term_refs:
            if ref not in all_terms:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE.name,
                        message=f"Term '-{term_name}' references undefined term '-{ref}'",
                        context=f"-{ref}",
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
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
                    code=DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE.name,
                    message=msg,
                    context=cycle_str,
                    severity=WarningSeverity.CRITICAL,
                )
            )

    return warnings


def _build_dependency_graph(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
) -> dict[str, set[str]]:
    """Build unified dependency graph for messages and terms.

    Creates a graph with type-prefixed nodes (msg:name, term:name) for
    both cycle detection and chain depth analysis.

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes

    Returns:
        Graph as adjacency list (node -> set of dependencies)
    """
    graph: dict[str, set[str]] = {}

    for msg_name, message in messages_dict.items():
        msg_refs, term_refs = extract_references(message)
        deps: set[str] = set()
        for ref in msg_refs:
            if ref in messages_dict:
                deps.add(f"msg:{ref}")
        for ref in term_refs:
            if ref in terms_dict:
                deps.add(f"term:{ref}")
        graph[f"msg:{msg_name}"] = deps

    for term_name, term in terms_dict.items():
        msg_refs, term_refs = extract_references(term)
        deps = set()
        for ref in msg_refs:
            if ref in messages_dict:
                deps.add(f"msg:{ref}")
        for ref in term_refs:
            if ref in terms_dict:
                deps.add(f"term:{ref}")
        graph[f"term:{term_name}"] = deps

    return graph


def _compute_longest_paths(
    graph: dict[str, set[str]],
) -> dict[str, tuple[int, list[str]]]:
    """Compute longest path from each node using memoized iterative DFS.

    Args:
        graph: Dependency graph as adjacency list

    Returns:
        Map from node to (path_length, path_nodes)
    """
    longest_path: dict[str, tuple[int, list[str]]] = {}
    in_stack: set[str] = set()

    for start in graph:
        if start in longest_path:
            continue

        # Iterative DFS with two-phase processing
        stack: list[tuple[str, int, list[str]]] = [(start, 0, list(graph.get(start, set())))]

        while stack:
            node, phase, children = stack.pop()

            if phase == 0:
                if node in longest_path or node in in_stack:
                    continue

                in_stack.add(node)
                stack.append((node, 1, children))

                for child in children:
                    if child not in longest_path and child not in in_stack:
                        stack.append((child, 0, list(graph.get(child, set()))))
            else:
                in_stack.discard(node)
                best_depth, best_path = 0, []
                for child in children:
                    if child in longest_path:
                        child_depth, child_path = longest_path[child]
                        if child_depth + 1 > best_depth:
                            best_depth = child_depth + 1
                            best_path = child_path
                longest_path[node] = (best_depth, [node, *best_path])

    return longest_path


def _detect_long_chains(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    max_depth: int = MAX_DEPTH,
) -> list[ValidationWarning]:
    """Detect reference chains that exceed maximum depth.

    Computes the longest reference chain path in the dependency graph.
    Warns if any chain exceeds max_depth (would fail at runtime).

    Args:
        messages_dict: Map of message IDs to Message nodes
        terms_dict: Map of term IDs to Term nodes
        max_depth: Maximum allowed chain depth (default: MAX_DEPTH)

    Returns:
        List of warnings for chains exceeding max_depth
    """
    graph = _build_dependency_graph(messages_dict, terms_dict)
    if not graph:
        return []

    longest_paths = _compute_longest_paths(graph)

    # Find the longest chain
    max_chain_depth, max_chain_path = 0, []
    for _node, (_, path) in longest_paths.items():
        if len(path) > max_chain_depth:
            max_chain_depth = len(path)
            max_chain_path = path

    if max_chain_depth <= max_depth:
        return []

    # Format path for human-readable output
    formatted = [
        node[4:] if node.startswith("msg:") else f"-{node[5:]}"
        for node in max_chain_path[:10]
    ]
    chain_str = " -> ".join(formatted)
    if len(max_chain_path) > 10:
        chain_str += f" -> ... ({len(max_chain_path)} total)"

    return [
        ValidationWarning(
            code=DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED.name,
            message=(
                f"Reference chain depth ({max_chain_depth}) exceeds maximum ({max_depth}); "
                f"will fail at runtime with MAX_DEPTH_EXCEEDED"
            ),
            context=chain_str,
            severity=WarningSeverity.WARNING,
        )
    ]


def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> ValidationResult:
    """Validate FTL resource without adding to a bundle.

    Standalone validation function for CI/CD pipelines and tooling.
    Performs syntax validation (errors) and semantic validation (warnings).

    Validation passes:
    1. Syntax errors: Parse failures (Junk entries)
    2. Structural: Duplicate IDs, messages without values
    3. References: Undefined message/term references
    4. Cycles: Circular dependency detection
    5. Chain depth: Reference chains exceeding MAX_DEPTH
    6. Semantic: Fluent spec compliance (E0001-E0013)

    Args:
        source: FTL file content
        parser: Optional parser instance (creates default if not provided)
        known_messages: Optional set of message IDs already in bundle (for
            cross-resource reference validation)
        known_terms: Optional set of term IDs already in bundle (for
            cross-resource reference validation)

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
        # Local import to avoid import-time overhead for callers not providing parser
        from ftllexengine.syntax.parser import (  # noqa: PLC0415
            FluentParserV1 as ParserClass,
        )

        parser = ParserClass()

    try:
        resource = parser.parse(source)

        # Build line offset cache once for all validation passes (O(n))
        line_cache = LineOffsetCache(source)

        # Pass 1: Extract syntax errors from Junk entries
        errors = _extract_syntax_errors(resource, line_cache)

        # Pass 2: Collect entries and check structural issues
        messages_dict, terms_dict, structure_warnings = _collect_entries(resource, line_cache)

        # Pass 3: Check undefined references (with bundle context if provided)
        ref_warnings = _check_undefined_references(
            messages_dict,
            terms_dict,
            line_cache,
            known_messages=known_messages,
            known_terms=known_terms,
        )

        # Pass 4: Detect circular dependencies
        cycle_warnings = _detect_circular_references(messages_dict, terms_dict)

        # Pass 5: Detect long reference chains (would fail at runtime)
        chain_warnings = _detect_long_chains(messages_dict, terms_dict)

        # Pass 6: Fluent spec compliance (E0001-E0013)
        semantic_validator = SemanticValidator()
        semantic_result = semantic_validator.validate(resource)
        semantic_annotations = semantic_result.annotations

        # Combine all warnings
        all_warnings = structure_warnings + ref_warnings + cycle_warnings + chain_warnings

        logger.debug(
            "Validated resource: %d errors, %d warnings, %d annotations",
            len(errors),
            len(all_warnings),
            len(semantic_annotations),
        )

        return ValidationResult(
            errors=tuple(errors),
            warnings=tuple(all_warnings),
            annotations=semantic_annotations,
        )

    except FluentSyntaxError as e:
        logger.error("Critical validation error: %s", e)
        error = ValidationError(
            code=DiagnosticCode.VALIDATION_CRITICAL_PARSE_ERROR.name,
            message=str(e),
            content=str(e),
        )
        return ValidationResult(errors=(error,), warnings=(), annotations=())
