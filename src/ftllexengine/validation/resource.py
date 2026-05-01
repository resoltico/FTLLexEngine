"""FTL resource validation orchestration.

Coordinates the validation passes used by CI/CD pipelines, linters, and
tooling that need resource checks without booting a full runtime bundle.
Focused helper modules own syntax extraction, entry collection, dependency
graph analysis, and undefined-reference checks.

Python 3.13+.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.reference_graph import detect_cycles, make_cycle_key
from ftllexengine.diagnostics import ValidationResult, ValidationWarning
from ftllexengine.syntax.cursor import LineOffsetCache
from ftllexengine.syntax.validator import SemanticValidator
from ftllexengine.validation.resource_entries import (
    check_undefined_references as _check_undefined_references,
)
from ftllexengine.validation.resource_entries import collect_entries as _collect_entries
from ftllexengine.validation.resource_graph import (
    build_dependency_graph,
    detect_long_chains,
)
from ftllexengine.validation.resource_graph import (
    detect_circular_references as _detect_circular_references_impl,
)
from ftllexengine.validation.resource_syntax import (
    extract_syntax_errors as _extract_syntax_errors,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.syntax.parser import FluentParserV1

__all__ = ["validate_resource"]

logger = logging.getLogger(__name__)


def _detect_circular_references(graph: dict[str, set[str]]) -> list[ValidationWarning]:
    """Compatibility wrapper preserving patch points for cycle tests."""
    return _detect_circular_references_impl(
        graph,
        detect_cycles_fn=detect_cycles,
        make_cycle_key_fn=make_cycle_key,
    )


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
        >>> from ftllexengine.validation import validate_resource  # doctest: +SKIP
        >>> result = validate_resource(ftl_source)  # doctest: +SKIP
        >>> if not result.is_valid:  # doctest: +SKIP
        ...     for error in result.errors:
        ...         print(f"Error [{error.code}]: {error.message}")
        >>> for warning in result.warnings:  # doctest: +SKIP
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
    dependency_graph = build_dependency_graph(
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
    chain_warnings = detect_long_chains(dependency_graph, max_depth=MAX_DEPTH)

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
