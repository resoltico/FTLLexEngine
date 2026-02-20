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
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ftllexengine.analysis.graph import detect_cycles, make_cycle_key
from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.introspection import extract_references, extract_references_by_attribute
from ftllexengine.syntax import Attribute, Junk, Message, Resource, Term
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


def _annotation_to_diagnostic_code(annotation_code: str) -> DiagnosticCode:
    """Resolve a parser annotation code string to a DiagnosticCode enum member.

    Parser annotations use DiagnosticCode member names as their code field
    (e.g., "PARSE_JUNK", "PARSE_NESTING_DEPTH_EXCEEDED"). This function
    performs a name-based lookup and falls back to PARSE_JUNK for any
    annotation code that does not match a DiagnosticCode member.

    Args:
        annotation_code: String code from an Annotation (e.g., "PARSE_JUNK")

    Returns:
        Matching DiagnosticCode member, or DiagnosticCode.PARSE_JUNK if unknown
    """
    try:
        return DiagnosticCode[annotation_code]
    except KeyError:
        return DiagnosticCode.PARSE_JUNK


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
                            code=_annotation_to_diagnostic_code(annotation.code),
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
                        code=DiagnosticCode.VALIDATION_PARSE_ERROR,
                        message="Failed to parse FTL content",
                        content=entry.content,
                        line=line,
                        column=column,
                    )
                )

    return errors


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
    """Check a single entry for duplicates, shadows, and attribute issues.

    Shared logic for both Message and Term validation in _collect_entries.

    Args:
        entry: The Message or Term AST node
        kind: Entry kind label ("message" or "term")
        entry_name: The entry identifier name
        attributes: The entry's attributes tuple
        seen_ids: Mutable set of IDs already seen in this namespace
        known_ids: Optional set of IDs already in bundle (for shadow detection)
        line_cache: Shared line offset cache for position lookups
        warnings: Mutable list to append warnings to
    """
    # Check for duplicate IDs within namespace
    if entry_name in seen_ids:
        line, column = _get_entry_position(entry, line_cache)
        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_DUPLICATE_ID,
                message=(
                    f"Duplicate {kind} ID '{entry_name}' "
                    f"(later definition will overwrite earlier)"
                ),
                context=entry_name,
                line=line,
                column=column,
                severity=WarningSeverity.WARNING,
            )
        )
    seen_ids.add(entry_name)

    # Check for shadow conflict with known entries
    if known_ids and entry_name in known_ids:
        line, column = _get_entry_position(entry, line_cache)
        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_SHADOW_WARNING,
                message=(
                    f"{kind.capitalize()} '{entry_name}' shadows "
                    f"existing {kind} "
                    f"(this definition will override the earlier one)"
                ),
                context=entry_name,
                line=line,
                column=column,
                severity=WarningSeverity.WARNING,
            )
        )

    # Check for duplicate attribute IDs within this entry
    seen_attr_ids: set[str] = set()
    for attr in attributes:
        attr_name = attr.id.name
        if attr_name in seen_attr_ids:
            line, column = _get_entry_position(entry, line_cache)
            warnings.append(
                ValidationWarning(
                    code=DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE,
                    message=(
                        f"{kind.capitalize()} '{entry_name}' has "
                        f"duplicate attribute '{attr_name}' "
                        f"(later will override earlier)"
                    ),
                    context=f"{entry_name}.{attr_name}",
                    line=line,
                    column=column,
                    severity=WarningSeverity.WARNING,
                )
            )
        seen_attr_ids.add(attr_name)


def _collect_entries(
    resource: Resource,
    line_cache: LineOffsetCache,
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
) -> tuple[dict[str, Message], dict[str, Term], list[ValidationWarning]]:
    """Collect message/term entries and check for structural issues.

    Performs the following checks:
    - Duplicate message IDs (within message namespace)
    - Duplicate term IDs (within term namespace)
    - Messages without values or attributes
    - Duplicate attribute IDs within entries
    - Shadow warnings when entry ID conflicts with known entry

    Note: Per Fluent spec, messages and terms have separate namespaces.
    A message named "foo" and a term named "foo" are NOT duplicates.

    Args:
        resource: Parsed Resource AST
        line_cache: Shared line offset cache for position lookups
        known_messages: Optional set of message IDs already in bundle
        known_terms: Optional set of term IDs already in bundle

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
            case Message(
                id=msg_id, value=value, attributes=attributes
            ):
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

                # Messages without values (defense-in-depth)
                # NOTE: Unreachable - parser/AST prevent this.
                # Kept for external AST construction scenarios.
                if (  # pragma: no cover
                    value is None and len(attributes) == 0
                ):
                    line, column = _get_entry_position(  # pragma: no cover
                        entry, line_cache
                    )
                    warnings.append(  # pragma: no cover
                        ValidationWarning(
                            code=DiagnosticCode.VALIDATION_NO_VALUE_OR_ATTRS,
                            message=(
                                f"Message '{msg_id.name}' has "
                                f"neither value nor attributes"
                            ),
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
            # Strip attribute qualification for existence check
            # "msg.tooltip" -> check if "msg" exists
            base_ref = ref.split(".", 1)[0] if "." in ref else ref
            if base_ref not in all_messages:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
                        message=f"Message '{msg_name}' references undefined message '{base_ref}'",
                        context=base_ref,
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

        for ref in term_refs:
            # Strip attribute qualification for existence check
            # "term.attr" -> check if "term" exists
            base_ref = ref.split(".", 1)[0] if "." in ref else ref
            if base_ref not in all_terms:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
                        message=f"Message '{msg_name}' references undefined term '-{base_ref}'",
                        context=f"-{base_ref}",
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
            # Strip attribute qualification for existence check
            base_ref = ref.split(".", 1)[0] if "." in ref else ref
            if base_ref not in all_messages:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
                        message=f"Term '-{term_name}' references undefined message '{base_ref}'",
                        context=base_ref,
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

        for ref in term_refs:
            # Strip attribute qualification for existence check
            base_ref = ref.split(".", 1)[0] if "." in ref else ref
            if base_ref not in all_terms:
                warnings.append(
                    ValidationWarning(
                        code=DiagnosticCode.VALIDATION_UNDEFINED_REFERENCE,
                        message=f"Term '-{term_name}' references undefined term '-{base_ref}'",
                        context=f"-{base_ref}",
                        line=line,
                        column=column,
                        severity=WarningSeverity.CRITICAL,
                    )
                )

    return warnings


def _detect_circular_references(
    graph: dict[str, set[str]],
) -> list[ValidationWarning]:
    """Detect circular dependencies in messages and terms.

    Uses iterative DFS via analysis.graph module to avoid stack overflow
    on deep dependency chains.

    Accepts a unified dependency graph with type-prefixed nodes to detect:
    - Message-only cycles (msg:A -> msg:B -> msg:A)
    - Term-only cycles (term:A -> term:B -> term:A)
    - Cross-type cycles (msg:A -> term:B -> msg:A)
    - Cross-resource cycles (current resource -> known entry -> current resource)

    Args:
        graph: Unified dependency graph with type-prefixed nodes (msg:name, term:name)

    Returns:
        List of warnings for circular references
    """
    warnings: list[ValidationWarning] = []
    seen_cycle_keys: set[str] = set()

    # Detect all cycles in the unified graph
    for cycle in detect_cycles(graph):
        cycle_key = make_cycle_key(cycle)
        if cycle_key not in seen_cycle_keys:
            seen_cycle_keys.add(cycle_key)

            # Format cycle for human-readable output
            # Convert "msg:foo" -> "foo", "msg:foo.bar" -> "foo.bar",
            # "term:baz" -> "-baz", "term:baz.attr" -> "-baz.attr"
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
                    code=DiagnosticCode.VALIDATION_CIRCULAR_REFERENCE,
                    message=msg,
                    context=cycle_str,
                    severity=WarningSeverity.CRITICAL,
                )
            )

    return warnings


def _resolve_reference(
    ref: str,
    prefix: str,
    local_entries: dict[str, Message] | dict[str, Term],
    known_ids: frozenset[str] | None,
) -> str | None:
    """Resolve a reference string to a graph node key.

    Shared logic for both message and term reference resolution.
    References may be attribute-qualified ("name.attr") or bare ("name").

    Args:
        ref: Reference string (possibly attribute-qualified)
        prefix: Graph node prefix ("msg" or "term")
        local_entries: Local entries dict for this namespace
        known_ids: Optional set of IDs already in bundle

    Returns:
        Prefixed graph node key, or None if reference is unknown
    """
    if "." in ref:
        base, attr = ref.split(".", 1)
        if base in local_entries or (known_ids and base in known_ids):
            return f"{prefix}:{base}.{attr}"
    elif ref in local_entries or (known_ids and ref in known_ids):
        return f"{prefix}:{ref}"
    return None


def _add_entry_nodes(
    entries: dict[str, Message] | dict[str, Term],
    prefix: str,
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    known_messages: frozenset[str] | None,
    known_terms: frozenset[str] | None,
    graph: dict[str, set[str]],
) -> None:
    """Add nodes and edges for a set of entries to the dependency graph.

    Shared logic for both message and term node building.

    Args:
        entries: The entries to process (messages or terms)
        prefix: Graph node prefix ("msg" or "term")
        messages_dict: All local messages (for reference resolution)
        terms_dict: All local terms (for reference resolution)
        known_messages: Optional set of message IDs already in bundle
        known_terms: Optional set of term IDs already in bundle
        graph: Mutable graph to add nodes to
    """
    for name, entry in entries.items():
        refs_by_attr = extract_references_by_attribute(entry)

        for attr_name, (msg_refs, term_refs) in refs_by_attr.items():
            node_key = (
                f"{prefix}:{name}"
                if attr_name is None
                else f"{prefix}:{name}.{attr_name}"
            )
            deps: set[str] = set()
            for ref in msg_refs:
                resolved = _resolve_reference(
                    ref, "msg", messages_dict, known_messages
                )
                if resolved is not None:
                    deps.add(resolved)
            for ref in term_refs:
                resolved = _resolve_reference(
                    ref, "term", terms_dict, known_terms
                )
                if resolved is not None:
                    deps.add(resolved)
            graph[node_key] = deps


def _add_known_entries(
    known_ids: frozenset[str] | None,
    prefix: str,
    known_deps: Mapping[str, frozenset[str]] | None,
    graph: dict[str, set[str]],
) -> None:
    """Add known (pre-existing) entries to the graph.

    Args:
        known_ids: Set of known entry IDs
        prefix: Graph node prefix ("msg" or "term")
        known_deps: Optional dependency map for known entries
        graph: Mutable graph to add nodes to
    """
    if not known_ids:
        return
    for known_id in known_ids:
        node_key = f"{prefix}:{known_id}"
        if node_key not in graph:
            if known_deps and known_id in known_deps:
                graph[node_key] = set(known_deps[known_id])
            else:
                graph[node_key] = set()


def _build_dependency_graph(
    messages_dict: dict[str, Message],
    terms_dict: dict[str, Term],
    *,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, set[str]]:
    """Build unified dependency graph for messages and terms.

    Creates a graph with type-prefixed nodes (msg:name, term:name) for
    both cycle detection and chain depth analysis.

    Args:
        messages_dict: Map of message IDs to Message nodes from current resource
        terms_dict: Map of term IDs to Term nodes from current resource
        known_messages: Optional set of message IDs already in bundle
        known_terms: Optional set of term IDs already in bundle
        known_msg_deps: Optional dependency map for known messages. Maps message ID
            to frozenset of prefixed dependencies (e.g., {"msg:foo", "term:bar"}).
        known_term_deps: Optional dependency map for known terms.

    Returns:
        Graph as adjacency list (node -> set of dependencies)
    """
    graph: dict[str, set[str]] = {}

    # Add entry nodes with attribute-granular dependencies.
    # Each attribute gets its own node to avoid false positive cycles
    # when msg.a references msg.b (non-cyclic intra-entry reference).
    _add_entry_nodes(
        messages_dict, "msg",
        messages_dict, terms_dict,
        known_messages, known_terms, graph,
    )
    _add_entry_nodes(
        terms_dict, "term",
        messages_dict, terms_dict,
        known_messages, known_terms, graph,
    )

    # Add known entries with their dependencies for cross-resource
    # cycle detection.
    _add_known_entries(
        known_messages, "msg", known_msg_deps, graph,
    )
    _add_known_entries(
        known_terms, "term", known_term_deps, graph,
    )

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
    graph: dict[str, set[str]],
    max_depth: int = MAX_DEPTH,
) -> list[ValidationWarning]:
    """Detect ALL reference chains that exceed maximum depth.

    Computes longest path from each node and reports ALL chains exceeding
    max_depth. This allows users to see and fix all depth violations in a
    single validation pass rather than iteratively discovering them.

    Args:
        graph: Unified dependency graph with type-prefixed nodes (msg:name, term:name)
        max_depth: Maximum allowed chain depth (default: MAX_DEPTH)

    Returns:
        List of warnings for ALL chains exceeding max_depth, sorted by depth
        (deepest first) for prioritized remediation
    """
    if not graph:
        return []

    longest_paths = _compute_longest_paths(graph)

    # Collect ALL chains exceeding max_depth
    exceeding_chains: list[tuple[int, list[str], str]] = []
    for node, (depth, path) in longest_paths.items():
        # Only report chains starting from their origin (first node in path)
        # to avoid duplicate warnings for the same chain from different nodes
        if depth > max_depth and path and path[0] == node:
            exceeding_chains.append((depth, path, node))

    if not exceeding_chains:
        return []

    # Sort by depth descending (deepest chains first) for prioritized remediation
    exceeding_chains.sort(key=lambda x: x[0], reverse=True)

    warnings: list[ValidationWarning] = []
    for chain_depth, chain_path, _origin in exceeding_chains:
        # Format path for human-readable output
        formatted = [
            node[4:] if node.startswith("msg:") else f"-{node[5:]}"
            for node in chain_path[:10]
        ]
        chain_str = " -> ".join(formatted)
        if len(chain_path) > 10:
            chain_str += f" -> ... ({len(chain_path)} total)"

        warnings.append(
            ValidationWarning(
                code=DiagnosticCode.VALIDATION_CHAIN_DEPTH_EXCEEDED,
                message=(
                    f"Reference chain depth ({chain_depth}) exceeds maximum ({max_depth}); "
                    f"will fail at runtime with MAX_DEPTH_EXCEEDED"
                ),
                context=chain_str,
                severity=WarningSeverity.WARNING,
            )
        )

    return warnings


def validate_resource(
    source: str,
    *,
    parser: FluentParserV1 | None = None,
    known_messages: frozenset[str] | None = None,
    known_terms: frozenset[str] | None = None,
    known_msg_deps: Mapping[str, frozenset[str]] | None = None,
    known_term_deps: Mapping[str, frozenset[str]] | None = None,
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
        known_msg_deps: Optional dependency graph for known messages. Maps message
            ID to frozenset of dependencies (prefixed: "msg:name", "term:name").
            Enables detection of cross-resource cycles involving dependencies OF
            known entries.
        known_term_deps: Optional dependency graph for known terms. Maps term ID
            to frozenset of dependencies (prefixed: "msg:name", "term:name").

    Returns:
        ValidationResult with parse errors and semantic warnings

    Raises:
        TypeError: If source is not a string (e.g., bytes were passed).

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
    # Type validation at API boundary - type hints are not enforced at runtime.
    # Defensive check: users may pass bytes despite str annotation.
    if not isinstance(source, str):
        msg = (  # type: ignore[unreachable]
            f"source must be str, not {type(source).__name__}. "
            "Decode bytes to str (e.g., source.decode('utf-8')) before calling validate_resource()."
        )
        raise TypeError(msg)

    if parser is None:
        # Local import to avoid import-time overhead for callers not providing parser
        from ftllexengine.syntax.parser import (  # noqa: PLC0415 - circular
            FluentParserV1 as ParserClass,
        )

        parser = ParserClass()

    # Normalize line endings to match parser behavior (CRLF/CR -> LF).
    # The parser normalizes internally before creating AST spans, so we must
    # use the same normalized source for LineOffsetCache to ensure position
    # lookups match AST span positions correctly.
    normalized_source = re.sub(r"\r\n?", "\n", source)

    resource = parser.parse(source)

    # Build line offset cache once for all validation passes (O(n))
    # Uses normalized_source to match AST span positions
    line_cache = LineOffsetCache(normalized_source)

    # Pass 1: Extract syntax errors from Junk entries
    errors = _extract_syntax_errors(resource, line_cache)

    # Pass 2: Collect entries and check structural issues
    messages_dict, terms_dict, structure_warnings = _collect_entries(
        resource,
        line_cache,
        known_messages=known_messages,
        known_terms=known_terms,
    )

    # Pass 3: Check undefined references (with bundle context if provided)
    ref_warnings = _check_undefined_references(
        messages_dict,
        terms_dict,
        line_cache,
        known_messages=known_messages,
        known_terms=known_terms,
    )

    # Build unified dependency graph once for both cycle and chain detection
    # Avoids redundant graph construction (important for large resources)
    dependency_graph = _build_dependency_graph(
        messages_dict,
        terms_dict,
        known_messages=known_messages,
        known_terms=known_terms,
        known_msg_deps=known_msg_deps,
        known_term_deps=known_term_deps,
    )

    # Pass 4: Detect circular dependencies
    cycle_warnings = _detect_circular_references(dependency_graph)

    # Pass 5: Detect long reference chains (would fail at runtime)
    chain_warnings = _detect_long_chains(dependency_graph)

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
