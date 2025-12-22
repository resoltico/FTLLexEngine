"""Hypothesis strategies for generating valid FTL syntax.

Provides custom strategies for property-based testing of the Fluent parser,
serializer, and resolver.
"""

from __future__ import annotations

import string

from hypothesis import strategies as st
from hypothesis.strategies import composite

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Comment,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TextElement,
    VariableReference,
    Variant,
)

# Common identifier parts for function bridge testing
IDENTIFIER_PARTS = ["foo", "bar", "baz", "value", "count"]


@composite
def ftl_identifiers(draw: st.DrawFn) -> str:
    """Generate valid FTL identifiers.

    FTL identifiers must start with a letter and contain only letters,
    digits, hyphens, and underscores.
    """
    first = draw(st.sampled_from(string.ascii_lowercase))
    rest = draw(
        st.text(
            alphabet=string.ascii_lowercase + string.digits + "-_",
            max_size=20,
        )
    )
    return first + rest


@composite
def ftl_simple_text(draw: st.DrawFn) -> str:
    """Generate simple text without special FTL characters.

    Note: Ensures text is not whitespace-only, as that confuses the parser
    (blank lines are treated as message separators, not pattern content).
    """
    text = draw(
        st.text(
            alphabet=string.ascii_letters + string.digits + " .,!?",
            min_size=1,
            max_size=50,
        )
    )
    # Ensure not whitespace-only - replace with letter if needed
    if text.strip() == "":
        text = draw(st.sampled_from(string.ascii_letters))
    return text


@composite
def ftl_simple_messages(draw: st.DrawFn) -> str:
    """Generate simple FTL messages (ID = value).

    Example:
        hello = Hello, world!
    """
    msg_id = draw(ftl_identifiers())
    value = draw(ftl_simple_text())
    return f"{msg_id} = {value}"


@composite
def ftl_numbers(draw: st.DrawFn) -> int | float:
    """Generate valid FTL numbers."""
    return draw(
        st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(
                min_value=-1000000.0,
                max_value=1000000.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )


@composite
def snake_case_identifiers(draw: st.DrawFn) -> str:
    """Generate snake_case identifiers for testing function bridge."""
    parts = draw(
        st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3)
    )
    return "_".join(parts)


@composite
def camel_case_identifiers(draw: st.DrawFn) -> str:
    """Generate camelCase identifiers for testing function bridge."""
    parts = draw(
        st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3)
    )
    if not parts:
        return "value"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# ============================================================================
# AST NODE STRATEGIES (for roundtrip testing)
# ============================================================================


@composite
def ftl_text_elements(draw: st.DrawFn) -> TextElement:
    """Generate TextElement AST nodes."""
    value = draw(ftl_simple_text())
    return TextElement(value=value)


@composite
def ftl_variable_references(draw: st.DrawFn) -> VariableReference:
    """Generate VariableReference AST nodes."""
    name = draw(ftl_identifiers())
    return VariableReference(id=Identifier(name=name))


@composite
def ftl_number_literals(draw: st.DrawFn) -> NumberLiteral:
    """Generate NumberLiteral AST nodes."""
    value = draw(ftl_numbers())
    return NumberLiteral(value=value, raw=str(value))


@composite
def ftl_string_literals(draw: st.DrawFn) -> StringLiteral:
    """Generate StringLiteral AST nodes."""
    value = draw(ftl_simple_text())
    return StringLiteral(value=value)


@composite
def ftl_placeables(draw: st.DrawFn) -> Placeable:
    """Generate Placeable AST nodes with simple expressions."""
    # For now, only use VariableReference (simplest placeable)
    expression = draw(ftl_variable_references())
    return Placeable(expression=expression)


@composite
def ftl_patterns(draw: st.DrawFn) -> Pattern:
    """Generate Pattern AST nodes."""
    # Generate mix of TextElement and Placeable
    elements = draw(
        st.lists(
            st.one_of(ftl_text_elements(), ftl_placeables()), min_size=1, max_size=4
        )
    )
    return Pattern(elements=tuple(elements))


@composite
def ftl_variants(draw: st.DrawFn) -> Variant:
    """Generate Variant AST nodes for select expressions."""
    # Key can be Identifier or NumberLiteral
    key = draw(
        st.one_of(
            st.builds(Identifier, name=ftl_identifiers()),
            ftl_number_literals(),
        )
    )
    value = draw(ftl_patterns())
    default = draw(st.booleans())
    return Variant(key=key, value=value, default=default)


@composite
def ftl_select_expressions(draw: st.DrawFn) -> SelectExpression:
    """Generate SelectExpression AST nodes."""
    selector = draw(ftl_variable_references())
    # Ensure at least one variant is default
    variants_list = draw(st.lists(ftl_variants(), min_size=2, max_size=4))
    # Force at least one default
    if not any(v.default for v in variants_list):
        variants_list[-1] = Variant(
            key=variants_list[-1].key, value=variants_list[-1].value, default=True
        )
    return SelectExpression(selector=selector, variants=tuple(variants_list))


@composite
def ftl_messages(draw: st.DrawFn) -> Message:
    """Generate Message AST nodes.

    Note: Messages must have a value (pattern). Messages without values
    are invalid FTL and get parsed as Junk.
    """
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())  # Always generate a pattern (never None)
    # No attributes for now (parser doesn't support them yet)
    return Message(id=id_val, value=value, attributes=())


@composite
def ftl_comments(draw: st.DrawFn) -> Comment:
    """Generate Comment AST nodes."""
    content = draw(ftl_simple_text())
    return Comment(content=content, type=CommentType.COMMENT)


@composite
def ftl_junk(draw: st.DrawFn) -> Junk:
    """Generate Junk AST nodes."""
    content = draw(st.text(min_size=1, max_size=50))
    return Junk(content=content)


@composite
def ftl_terms(draw: st.DrawFn) -> Term:
    """Generate Term AST nodes.

    Terms are like messages but with leading hyphen in ID.
    """
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())
    return Term(id=id_val, value=value, attributes=())


@composite
def ftl_resources(draw: st.DrawFn) -> Resource:
    """Generate complete Resource AST nodes.

    Note: For roundtrip testing, we generate mostly messages since the parser
    does not yet support standalone comments. Comments and junk are included
    occasionally to test serializer robustness.

    Message IDs are ensured to be unique within a resource (as duplicate IDs
    would cause the last one to overwrite earlier ones during parsing).
    """
    # Generate primarily messages (for roundtrip testing)
    # Occasionally include comments (to test serializer)
    entries = draw(
        st.lists(
            st.one_of(
                ftl_messages(),  # Most common
                ftl_messages(),  # Weighted toward messages
                ftl_messages(),
                ftl_comments(),  # Occasional comment
            ),
            min_size=1,
            max_size=5,
        )
    )
    # Filter out None values
    entries = [e for e in entries if e is not None]

    # Ensure unique message IDs (deduplicate by ID, keep first occurrence)
    seen_ids: set[str] = set()
    unique_entries: list[Message | Comment] = []
    for entry in entries:
        if isinstance(entry, Message):
            if entry.id.name not in seen_ids:
                seen_ids.add(entry.id.name)
                unique_entries.append(entry)
        else:
            unique_entries.append(entry)

    return Resource(entries=tuple(unique_entries))


@composite
def any_ast_entry(draw: st.DrawFn) -> Message | Term | Comment | Junk:
    """Generate any AST entry type.

    Used for testing type guards - ensures all entry types are covered.
    """
    return draw(
        st.one_of(
            ftl_messages(),
            ftl_terms(),
            ftl_comments(),
            ftl_junk(),
        )
    )


@composite
def any_ast_pattern_element(draw: st.DrawFn) -> TextElement | Placeable:
    """Generate any pattern element type.

    Used for testing type guards on pattern elements.
    """
    return draw(st.one_of(ftl_text_elements(), ftl_placeables()))


# ============================================================================
# RECURSIVE STRATEGIES (for validator deep nesting tests)
# ============================================================================


def _ensure_unique_variant_keys_with_default(variants: list[Variant]) -> tuple[Variant, ...]:
    """Ensure variants have unique keys and at least one default.

    Helper for recursive strategy generation.
    """
    # Deduplicate by key (keep first occurrence)
    seen_keys: set[str] = set()
    unique_variants: list[Variant] = []

    for v in variants:
        # Get key name
        key_name = v.key.name if hasattr(v.key, "name") else str(v.key.value)

        if key_name not in seen_keys:
            seen_keys.add(key_name)
            unique_variants.append(v)

    # Ensure at least 2 variants (select expressions need at least 2)
    if len(unique_variants) < 2:
        # Add a second variant with different key
        unique_variants.append(
            Variant(
                key=Identifier(name="fallback"),
                value=Pattern(elements=(TextElement(value="other"),)),
                default=False,
            )
        )

    # Ensure at least one default
    if not any(v.default for v in unique_variants):
        # Make last variant default
        unique_variants[-1] = Variant(
            key=unique_variants[-1].key,
            value=unique_variants[-1].value,
            default=True,
        )

    return tuple(unique_variants)


def ftl_deeply_nested_selects(max_depth: int = 5) -> st.SearchStrategy[SelectExpression]:
    """Generate deeply nested select expressions using st.recursive().

    Used for validator stress testing - creates selects with nested selects
    as selectors, up to max_depth levels deep.

    Args:
        max_depth: Maximum nesting depth for select expressions

    Returns:
        Strategy generating SelectExpression with possible nesting

    Example:
        { { $a -> *[x] 1 } -> *[y] 2 }  # depth 2
    """
    # Base case: use SelectExpression instead of VariableReference to match recursive type
    # This avoids mypy arg-type error with st.recursive
    base_select = st.builds(
        SelectExpression,
        selector=ftl_variable_references(),
        variants=st.lists(ftl_variants(), min_size=2, max_size=4).map(
            lambda vs: _ensure_unique_variant_keys_with_default(vs)
        ),
    )

    # Recursive case: select expression with possibly nested selector
    def extend(
        children: st.SearchStrategy[SelectExpression],
    ) -> st.SearchStrategy[SelectExpression]:
        # Selector can be the nested child
        # Variants use simple patterns (not nested)
        return st.builds(
            SelectExpression,
            selector=children,
            variants=st.lists(ftl_variants(), min_size=2, max_size=4).map(
                lambda vs: _ensure_unique_variant_keys_with_default(vs)
            ),
        )

    return st.recursive(base_select, extend, max_leaves=max_depth)
