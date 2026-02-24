"""FTL message introspection for variable, function, and reference extraction.

This module provides introspection capabilities for analyzing FTL message patterns
and extracting metadata about variable usage, function calls, and message references.

Key features:
- Type-safe results using Python 3.13's TypeIs for runtime narrowing
- Memory-efficient frozen dataclasses with slots for reduced overhead
- Pattern matching for elegant AST traversal
- Comprehensive variable, function, and reference extraction
- Depth limiting to prevent stack overflow on adversarial ASTs

Python 3.13+.
"""

from __future__ import annotations

import threading
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, assert_never

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.enums import ReferenceKind, VariableContext
from ftllexengine.syntax.ast import (
    FunctionReference,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    SelectExpression,
    Span,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.visitor import ASTVisitor

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import Expression, InlineExpression, PatternElement

__all__ = [
    # Public API
    "FunctionCallInfo",
    "MessageIntrospection",
    "ReferenceInfo",
    "VariableInfo",
    "clear_introspection_cache",
    "extract_references",
    "extract_references_by_attribute",
    "extract_variables",
    "introspect_message",
    # Internal (accessible for testing, not re-exported from package)
    "IntrospectionVisitor",
    "ReferenceExtractor",
]

# ==============================================================================
# MODULE-LEVEL CACHE
# ==============================================================================

# WeakKeyDictionary allows automatic cleanup when Message/Term objects are garbage
# collected. This avoids the id() reuse problem of regular dicts and provides
# proper cache invalidation without manual management.
#
# Thread Safety:
# All accesses to _introspection_cache are protected by _introspection_cache_lock.
# This is required for correctness under Python 3.13+ free-threaded builds
# (--disable-gil, PEP 703): without the lock, concurrent writes can corrupt
# WeakKeyDictionary's internal state.
#
# Performance design (check-compute-store):
# 1. Lock briefly to check cache (fast path: O(1), returns immediately on hit).
# 2. Compute introspection result WITHOUT holding the lock (expensive AST traversal
#    can run concurrently across threads without interference because introspection
#    is a pure read on immutable AST nodes).
# 3. Lock briefly to store result.
#
# A second thread may compute the same result concurrently between steps 1 and 3.
# On store, a re-check discards redundant computation. Worst case: one redundant
# traversal per concurrent pair; no data corruption, no inconsistency.
#
# Lock granularity: threading.Lock (non-reentrant) is sufficient. No code path
# acquires the lock and then re-acquires it from the same thread. Lock overhead
# is minimal for the fast-path check and store operations.
_introspection_cache: weakref.WeakKeyDictionary[Message | Term, MessageIntrospection] = (
    weakref.WeakKeyDictionary()
)
_introspection_cache_lock: threading.Lock = threading.Lock()


def clear_introspection_cache() -> None:
    """Clear the introspection cache.

    Useful for testing or when memory pressure is a concern. In normal usage,
    the WeakKeyDictionary automatically cleans up entries when Message/Term
    objects are garbage collected.

    Thread-safe. Acquires the cache lock before clearing.
    """
    with _introspection_cache_lock:
        _introspection_cache.clear()


# ==============================================================================
# INTROSPECTION METADATA (Frozen Dataclasses with Slots)
# ==============================================================================


@dataclass(frozen=True, slots=True)
class VariableInfo:
    """Immutable metadata about a variable reference in a message.

    Uses Python 3.13's frozen dataclass with slots for low memory overhead.
    """

    name: str
    """Variable name (without $ prefix)."""

    context: VariableContext
    """Context where variable appears."""

    span: Span | None = None
    """Source position span for IDE integration."""


@dataclass(frozen=True, slots=True)
class FunctionCallInfo:
    """Immutable metadata about a function call in a message."""

    name: str
    """Function name (e.g., 'NUMBER', 'DATETIME')."""

    positional_arg_vars: tuple[str, ...]
    """Variable names used as positional arguments.

    Contains only the names of VariableReference nodes passed as positional
    arguments. Literal values, message references, and other expression types
    are not included in this tuple.

    Example:
        FTL: { NUMBER($count, "literal", $extra) }
        positional_arg_vars: ("count", "extra")  # literals not included
    """

    named_args: frozenset[str]
    """Named argument keys."""

    span: Span | None = None
    """Source position span for IDE integration."""


@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    """Immutable metadata about message/term references.

    Tracks cross-message and term references for dependency analysis,
    cycle detection, and impact assessment. Each reference captures
    what is being referenced and how.

    Examples:
        - { msg } -> ReferenceInfo(id="msg", kind=MESSAGE, attribute=None)
        - { -term } -> ReferenceInfo(id="term", kind=TERM, attribute=None)
        - { msg.attr } -> ReferenceInfo(id="msg", kind=MESSAGE, attribute="attr")
    """

    id: str
    """Referenced message or term ID (without - prefix for terms)."""

    kind: ReferenceKind
    """Reference type: MESSAGE or TERM."""

    attribute: str | None
    """Attribute name if accessing .attr syntax, otherwise None."""

    span: Span | None = None
    """Source position span for IDE integration."""


@dataclass(frozen=True, slots=True)
class MessageIntrospection:
    """Complete introspection result for a message.

    This is the primary result type returned by the introspection API.
    All fields are immutable and use slots for optimal memory usage.
    """

    message_id: str
    """Message identifier."""

    variables: frozenset[VariableInfo]
    """All variables referenced in the message."""

    functions: frozenset[FunctionCallInfo]
    """All function calls in the message."""

    references: frozenset[ReferenceInfo]
    """All message/term references."""

    has_selectors: bool
    """Whether message uses select expressions."""

    # Pre-computed name caches for O(1) accessor performance.
    # Derived from variables/functions in __post_init__. Using field(init=False)
    # keeps these internal caches out of the public constructor signature and
    # guarantees consistency — they cannot diverge from their source fields.
    _variable_names: frozenset[str] = field(init=False, repr=False, compare=False, hash=False)
    """Cached variable names for O(1) lookup."""

    _function_names: frozenset[str] = field(init=False, repr=False, compare=False, hash=False)
    """Cached function names for O(1) lookup."""

    def __post_init__(self) -> None:
        """Compute derived name caches from public fields.

        Uses object.__setattr__ to initialize slots on the frozen dataclass.
        This is the documented Python pattern for computed fields in frozen
        dataclasses: __post_init__ runs inside __init__, before the frozen
        restriction is enforced externally.
        """
        object.__setattr__(self, "_variable_names", frozenset(v.name for v in self.variables))
        object.__setattr__(self, "_function_names", frozenset(f.name for f in self.functions))

    def get_variable_names(self) -> frozenset[str]:
        """Get set of variable names.

        Convenience method extracting names from VariableInfo objects.

        Returns:
            Frozen set of variable names without $ prefix.
        """
        return self._variable_names

    def requires_variable(self, name: str) -> bool:
        """Check if message requires a specific variable.

        Args:
            name: Variable name (without $ prefix)

        Returns:
            True if variable is used in the message
        """
        # O(1) frozenset membership test vs O(N) any() iteration
        return name in self._variable_names

    def get_function_names(self) -> frozenset[str]:
        """Get set of function names used in the message.

        Returns:
            Frozen set of function names (e.g., {'NUMBER', 'DATETIME'})
        """
        return self._function_names


# ==============================================================================
# AST VISITOR FOR VARIABLE EXTRACTION
# ==============================================================================


class IntrospectionVisitor(ASTVisitor[None]):
    """AST visitor that extracts variables, functions, and references from messages.

    Uses Python 3.13's pattern matching for elegant AST traversal and TypeIs
    for type-safe runtime narrowing.

    Note on Traversal:
        This visitor intentionally overrides pattern traversal instead of calling
        super().visit_Pattern(). The FTL specification's Pattern structure is stable
        (elements only), and our introspection logic requires specific handling
        of each element type. Calling super() would invoke generic_visit() which
        is a no-op for this visitor pattern.

    Depth Limiting:
        Includes DepthGuard to prevent stack overflow on adversarial or
        programmatically constructed deeply nested ASTs. While parser-produced
        ASTs have implicit limits, programmatic construction bypasses the parser.

    Memory Optimization:
        Uses __slots__ to restrict attribute creation and reduce memory overhead
        when introspecting large ASTs with many visitor instances.
    """

    __slots__ = (
        "_context",
        "functions",
        "has_selectors",
        "references",
        "variables",
    )

    def __init__(self, *, max_depth: int = MAX_DEPTH) -> None:
        """Initialize visitor with empty result sets.

        Args:
            max_depth: Maximum expression nesting depth (default: MAX_DEPTH).
                       Prevents stack overflow on adversarial ASTs.
        """
        super().__init__(max_depth=max_depth)
        self.variables: set[VariableInfo] = set()
        self.functions: set[FunctionCallInfo] = set()
        self.references: set[ReferenceInfo] = set()
        self.has_selectors: bool = False
        self._context: VariableContext = VariableContext.PATTERN

    def visit_Pattern(self, node: Pattern) -> None:
        """Visit pattern and extract variables from all elements.

        Note: Intentionally does NOT call super().visit_Pattern(node) as this
        visitor implements custom traversal logic. The Pattern node structure
        is stable per FTL specification (only has 'elements' children).
        """
        for element in node.elements:
            self._visit_pattern_element(element)

    def _visit_pattern_element(self, element: PatternElement) -> None:
        """Visit a pattern element (TextElement or Placeable)."""
        match element:
            case TextElement():
                pass  # No variables in text
            case Placeable(expression=expr):
                # Track depth to prevent stack overflow on deep nesting
                with self._depth_guard:
                    self._visit_expression(expr)
            case _ as unreachable:
                # PatternElement is a closed union: TextElement | Placeable.
                # This branch is unreachable for FTL spec-compliant ASTs;
                # assert_never() provides a type-checked exhaustiveness guard.
                assert_never(unreachable)

    def _visit_expression(self, expr: Expression | InlineExpression) -> None:
        """Visit an expression and extract metadata using structural pattern matching.

        Spans are propagated from AST expression nodes to Info objects for IDE integration.
        StringLiteral and NumberLiteral are leaf nodes with no sub-expressions; they
        fall through to the default case intentionally.
        """
        match expr:
            case VariableReference(id=var_id, span=span):
                self.variables.add(
                    VariableInfo(name=var_id.name, context=self._context, span=span)
                )

            case FunctionReference() as func_ref:
                self._extract_function_call(func_ref)

            case MessageReference(id=msg_id, attribute=attribute, span=span):
                attr_name = attribute.name if attribute else None
                self.references.add(
                    ReferenceInfo(
                        id=msg_id.name,
                        kind=ReferenceKind.MESSAGE,
                        attribute=attr_name,
                        span=span,
                    )
                )

            case TermReference(id=term_id, attribute=attribute, arguments=arguments, span=span):
                attr_name = attribute.name if attribute else None
                self.references.add(
                    ReferenceInfo(
                        id=term_id.name,
                        kind=ReferenceKind.TERM,
                        attribute=attr_name,
                        span=span,
                    )
                )
                # Visit term arguments to extract nested dependencies
                # Term arguments like -term(case: $var) contain expressions
                if arguments:
                    for pos_arg in arguments.positional:
                        with self._depth_guard:
                            self._visit_expression(pos_arg)
                    for named_arg in arguments.named:
                        with self._depth_guard:
                            self._visit_expression(named_arg.value)

            case SelectExpression(selector=selector, variants=variants):
                self.has_selectors = True
                old_context = self._context
                try:
                    self._context = VariableContext.SELECTOR
                    with self._depth_guard:
                        self._visit_expression(selector)
                finally:
                    self._context = old_context
                for variant in variants:
                    self._visit_variant(variant)

            case Placeable(expression=inner_expr):
                # Handle nested Placeables (e.g., { { $var } })
                with self._depth_guard:
                    self._visit_expression(inner_expr)

            case _:
                # StringLiteral | NumberLiteral: leaf nodes with no sub-expressions.
                pass

    def _extract_function_call(self, func: FunctionReference) -> None:
        """Extract function call information including arguments.

        Recursively visits all argument expressions to extract nested dependencies
        (variables, message references, term references, and nested function calls).
        Context is saved once before argument traversal and restored in a finally
        block to guarantee exception safety even if DepthGuard fires mid-traversal.
        """
        positional: list[str] = []
        named: set[str] = set()

        old_context = self._context
        try:
            self._context = VariableContext.FUNCTION_ARG

            # Extract positional arguments - recursively visit all expression types
            for pos_arg in func.arguments.positional:
                # Unwrap Placeable if present (handles {$var} in function args)
                unwrapped_arg = pos_arg.expression if Placeable.guard(pos_arg) else pos_arg

                # Track variable names for positional args metadata
                if VariableReference.guard(unwrapped_arg):
                    positional.append(unwrapped_arg.id.name)

                # Recursively visit to extract all nested dependencies
                # This handles: VariableReference, MessageReference, TermReference,
                # nested FunctionReference, SelectExpression, etc.
                with self._depth_guard:
                    self._visit_expression(pos_arg)

            # Extract named argument keys and recursively visit values
            for named_arg in func.arguments.named:
                named.add(named_arg.name.name)
                # Recursively visit value expression for all nested dependencies
                with self._depth_guard:
                    self._visit_expression(named_arg.value)
        finally:
            self._context = old_context

        func_info = FunctionCallInfo(
            name=func.id.name,
            positional_arg_vars=tuple(positional),
            named_args=frozenset(named),
            span=func.span,
        )
        self.functions.add(func_info)

    def _visit_variant(self, variant: Variant) -> None:
        """Visit a select variant and extract variables from its pattern."""
        old_context = self._context
        try:
            self._context = VariableContext.VARIANT
            self.visit(variant.value)
        finally:
            self._context = old_context


# ==============================================================================
# REFERENCE EXTRACTION (Specialized Visitor)
# ==============================================================================


class ReferenceExtractor(ASTVisitor[MessageReference | TermReference]):
    """Extract message and term references from AST for validation.

    Specialized visitor that collects only MessageReference and TermReference
    nodes. Used by validation tools to build dependency graphs for circular
    reference detection.

    This is intentionally simpler than IntrospectionVisitor - it does one thing
    well: extract reference IDs for dependency analysis.

    Depth Limiting:
        Includes DepthGuard to prevent stack overflow on adversarial or
        programmatically constructed deeply nested ASTs.

    Memory Optimization:
        Uses __slots__ to restrict attribute creation and reduce memory overhead.
    """

    __slots__ = ("message_refs", "term_refs")

    def __init__(self, *, max_depth: int = MAX_DEPTH) -> None:
        """Initialize reference collector.

        Args:
            max_depth: Maximum expression nesting depth (default: MAX_DEPTH).
                       Prevents stack overflow on adversarial ASTs.
        """
        super().__init__(max_depth=max_depth)
        self.message_refs: set[str] = set()
        self.term_refs: set[str] = set()

    def visit_MessageReference(self, node: MessageReference) -> MessageReference:
        """Collect message reference ID with optional attribute qualification.

        Stores attribute-qualified references ("msg.attr") when the reference
        targets a specific attribute, or unqualified ("msg") for base message
        references. This enables attribute-granular cycle detection.

        MessageReference contains only Identifier children (leaf nodes with
        just name: str). No nested references are possible, so generic_visit()
        is unnecessary and would waste cycles traversing leaf nodes.
        """
        if node.attribute is not None:
            self.message_refs.add(f"{node.id.name}.{node.attribute.name}")
        else:
            self.message_refs.add(node.id.name)
        return node

    def visit_TermReference(self, node: TermReference) -> TermReference:
        """Collect term reference with depth tracking.

        Unlike MessageReference, TermReference has arguments: CallArguments | None
        which CAN contain nested expressions (including MessageReference,
        TermReference, VariableReference). Must traverse children to find all
        nested references.
        """
        if node.attribute is not None:
            self.term_refs.add(f"{node.id.name}.{node.attribute.name}")
        else:
            self.term_refs.add(node.id.name)
        with self._depth_guard:
            self.generic_visit(node)
        return node


def extract_references(entry: Message | Term) -> tuple[frozenset[str], frozenset[str]]:
    """Extract message and term references from an AST entry.

    Traverses the entry's value pattern and all attribute patterns to collect
    all referenced message and term IDs. References include attribute
    qualification: "msg.attr" for attribute references, "msg" for base
    message references.

    Args:
        entry: Message or Term AST node to analyze

    Returns:
        Tuple of (message_refs, term_refs) as frozen sets of IDs.
        - message_refs: Set of referenced message IDs, possibly attribute-qualified
          (e.g., {"welcome", "msg.tooltip"})
        - term_refs: Set of referenced term IDs (e.g., {"brand", "app-name"})

    Example:
        >>> from ftllexengine import parse_ftl
        >>> resource = parse_ftl("msg = { welcome } uses { -brand }")
        >>> message = resource.entries[0]
        >>> msg_refs, term_refs = extract_references(message)
        >>> assert "welcome" in msg_refs
        >>> assert "brand" in term_refs
    """
    extractor = ReferenceExtractor()

    # Visit value pattern (Message.value can be None, Term.value is always present)
    if entry.value is not None:
        extractor.visit(entry.value)

    # Visit all attribute patterns
    for attr in entry.attributes:
        extractor.visit(attr.value)

    return frozenset(extractor.message_refs), frozenset(extractor.term_refs)


def extract_references_by_attribute(
    entry: Message | Term,
) -> dict[str | None, tuple[frozenset[str], frozenset[str]]]:
    """Extract references per source attribute for attribute-granular cycle detection.

    Returns a mapping from source attribute name (None for value pattern) to
    the (message_refs, term_refs) found in that attribute's pattern.

    Args:
        entry: Message or Term AST node to analyze

    Returns:
        Dict mapping attribute name (or None for value) to (message_refs, term_refs).
    """
    result: dict[str | None, tuple[frozenset[str], frozenset[str]]] = {}

    # Extract from value pattern
    if entry.value is not None:
        extractor = ReferenceExtractor()
        extractor.visit(entry.value)
        result[None] = (frozenset(extractor.message_refs), frozenset(extractor.term_refs))

    # Extract from each attribute pattern separately
    for attr in entry.attributes:
        extractor = ReferenceExtractor()
        extractor.visit(attr.value)
        result[attr.id.name] = (frozenset(extractor.message_refs), frozenset(extractor.term_refs))

    return result


# ==============================================================================
# PUBLIC API
# ==============================================================================


def introspect_message(
    message: Message | Term,
    *,
    use_cache: bool = True,
) -> MessageIntrospection:
    """Introspect a message or term and extract all metadata.

    This is the primary entry point for message/term introspection.

    Args:
        message: Message or Term AST node to introspect
        use_cache: If True (default), use WeakKeyDictionary cache for repeated
            introspection of the same Message/Term. Disable for benchmarking or
            when cache invalidation is needed.

    Returns:
        Complete introspection result with variables, functions, and references

    Raises:
        TypeError: If message is not a Message or Term AST node

    Example:
        >>> from ftllexengine.syntax.parser import FluentParserV1
        >>> parser = FluentParserV1()
        >>> resource = parser.parse("greeting = Hello, { $name }!")
        >>> msg = resource.entries[0]
        >>> info = introspect_message(msg)
        >>> print(info.get_variable_names())
        frozenset({'name'})
    """
    # Validate input type at API boundary (runtime check for callers ignoring type hints)
    if not isinstance(message, (Message, Term)):
        msg = f"Expected Message or Term, got {type(message).__name__}"  # type: ignore[unreachable]
        raise TypeError(msg)

    # Step 1: Check cache (lock briefly — O(1) dict lookup).
    if use_cache:
        with _introspection_cache_lock:
            cached = _introspection_cache.get(message)
        if cached is not None:
            return cached

    # Step 2: Compute WITHOUT holding the lock.
    # Introspection is a pure read on immutable AST nodes; concurrent traversal
    # of the same node is safe. Two threads may compute simultaneously on a cache
    # miss — the redundant result is discarded in step 3.
    visitor = IntrospectionVisitor()

    # Visit message value pattern via proper dispatch
    # (allows subclass customization via visit() override)
    if message.value is not None:
        visitor.visit(message.value)

    # Visit attribute patterns via proper dispatch
    for attr in message.attributes:
        visitor.visit(attr.value)

    result = MessageIntrospection(
        message_id=message.id.name,
        variables=frozenset(visitor.variables),
        functions=frozenset(visitor.functions),
        references=frozenset(visitor.references),
        has_selectors=visitor.has_selectors,
    )

    # Step 3: Store result (lock briefly — O(1) dict write).
    # Re-check before storing: another thread may have stored the same result
    # between step 1 and now. Discard redundant result; return whichever was
    # stored first (both are identical since inputs are immutable).
    if use_cache:
        with _introspection_cache_lock:
            existing = _introspection_cache.get(message)
            if existing is not None:
                return existing
            _introspection_cache[message] = result

    return result


def extract_variables(message: Message | Term) -> frozenset[str]:
    """Extract variable names from a message or term (simplified API).

    This is a convenience function for the most common use case.

    Args:
        message: Message or Term AST node

    Returns:
        Frozen set of variable names (without $ prefix)

    Example:
        >>> vars = extract_variables(msg)
        >>> assert 'name' in vars
    """
    return introspect_message(message).get_variable_names()
