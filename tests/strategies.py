"""Hypothesis strategies for generating valid FTL syntax.

Provides custom strategies for property-based testing of the Fluent parser,
serializer, and resolver.

Strategy Categories:
- String strategies: Generate FTL source text (for parsing)
- AST strategies: Generate AST nodes directly (for serialization)
- Edge case strategies: Generate boundary conditions
"""

from __future__ import annotations

import string

from hypothesis import strategies as st
from hypothesis.strategies import composite

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Attribute,
    Comment,
    Identifier,
    Junk,
    Message,
    MessageReference,
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

# =============================================================================
# Constants
# =============================================================================

# FTL identifier character sets per spec: [a-zA-Z][a-zA-Z0-9_-]*
# CRITICAL: Both uppercase AND lowercase letters are valid per FTL specification.
FTL_IDENTIFIER_FIRST_CHARS: str = string.ascii_letters  # [a-zA-Z]
FTL_IDENTIFIER_REST_CHARS: str = string.ascii_letters + string.digits + "-_"

# Common identifier parts for testing
IDENTIFIER_PARTS = ("foo", "bar", "baz", "value", "count", "name", "id", "key")

# FTL-safe alphabet (no special FTL characters)
FTL_SAFE_CHARS = string.ascii_letters + string.digits + " .,!?'-"

# Unicode test characters (various scripts and special chars)
UNICODE_CHARS = (
    "\u4e16\u754c"  # Chinese: world
    "\u0414\u043e\u0431\u0440\u043e"  # Russian: Dobro
    "\u3053\u3093\u306b\u3061\u306f"  # Japanese: konnichiwa
    "\u00e9\u00e0\u00fc\u00f1"  # Latin extended: accents
    "\u2019\u2018\u201c\u201d"  # Smart quotes
)


# =============================================================================
# String Strategies (for parsing)
# =============================================================================


@composite
def ftl_identifiers(draw: st.DrawFn) -> str:
    """Generate valid FTL identifiers.

    FTL spec: [a-zA-Z][a-zA-Z0-9_-]*
    Uses both uppercase AND lowercase per specification.
    """
    first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
    rest = draw(
        st.text(
            alphabet=FTL_IDENTIFIER_REST_CHARS,
            max_size=20,
        )
    )
    return first + rest


@composite
def ftl_simple_text(draw: st.DrawFn) -> str:
    """Generate simple text without special FTL characters.

    Ensures text is not whitespace-only (blank lines are message separators).
    """
    text = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=50))
    # Ensure not whitespace-only
    if text.strip() == "":
        text = draw(st.sampled_from(string.ascii_letters))
    return text


@composite
def ftl_unicode_text(draw: st.DrawFn) -> str:
    """Generate text with Unicode characters."""
    # Mix ASCII and Unicode
    ascii_part = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=20))
    unicode_part = draw(st.text(alphabet=UNICODE_CHARS, min_size=1, max_size=10))

    # Randomly interleave
    if draw(st.booleans()):
        return ascii_part + " " + unicode_part
    return unicode_part + " " + ascii_part


@composite
def ftl_simple_messages(draw: st.DrawFn) -> str:
    """Generate simple FTL messages (ID = value).

    Example: hello = Hello, world!
    """
    msg_id = draw(ftl_identifiers())
    value = draw(ftl_simple_text())
    return f"{msg_id} = {value}"


@composite
def ftl_messages_with_placeables(draw: st.DrawFn) -> str:
    """Generate FTL messages containing placeables.

    Example: greeting = Hello { $name }!
    """
    msg_id = draw(ftl_identifiers())
    var_name = draw(ftl_identifiers())
    prefix = draw(ftl_simple_text())
    suffix = draw(st.text(alphabet=FTL_SAFE_CHARS, max_size=20))

    return f"{msg_id} = {prefix} {{ ${var_name} }}{suffix}"


@composite
def ftl_terms(draw: st.DrawFn) -> str:
    """Generate FTL term definitions.

    Example: -brand = Firefox
    """
    term_id = draw(ftl_identifiers())
    value = draw(ftl_simple_text())
    return f"-{term_id} = {value}"


@composite
def ftl_comments(draw: st.DrawFn) -> str:
    """Generate FTL comments (all types).

    Returns one of: # comment, ## group comment, ### resource comment
    """
    level = draw(st.sampled_from(["#", "##", "###"]))
    content = draw(ftl_simple_text())
    return f"{level} {content}"


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


# =============================================================================
# Identifier Case Strategies (for function bridge testing)
# =============================================================================


@composite
def snake_case_identifiers(draw: st.DrawFn) -> str:
    """Generate snake_case identifiers."""
    parts = draw(st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3))
    return "_".join(parts)


@composite
def camel_case_identifiers(draw: st.DrawFn) -> str:
    """Generate camelCase identifiers."""
    parts = draw(st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3))
    if not parts:
        return "value"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# =============================================================================
# AST Node Strategies (for serialization testing)
# =============================================================================


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
    expression = draw(ftl_variable_references())
    return Placeable(expression=expression)


@composite
def ftl_patterns(draw: st.DrawFn) -> Pattern:
    """Generate Pattern AST nodes with mixed elements."""
    elements = draw(
        st.lists(
            st.one_of(ftl_text_elements(), ftl_placeables()),
            min_size=1,
            max_size=4,
        )
    )
    return Pattern(elements=tuple(elements))


@composite
def ftl_variants(draw: st.DrawFn) -> Variant:
    """Generate Variant AST nodes for select expressions."""
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
    """Generate SelectExpression AST nodes with valid variants.

    Ensures:
    - Exactly one default variant (per Fluent spec)
    - Unique variant keys (per Fluent spec)
    """
    selector = draw(ftl_variable_references())

    # Generate 2-4 unique variant keys using st.sampled_from predefined set
    # This avoids expensive rejection-based uniqueness while ensuring valid keys
    num_variants = draw(st.integers(min_value=2, max_value=4))

    # Use predefined unique key names (efficient, no rejection needed)
    available_keys = ["one", "two", "three", "four", "five", "other", "zero"]
    key_names = draw(
        st.lists(
            st.sampled_from(available_keys),
            min_size=num_variants,
            max_size=num_variants,
            unique=True,
        )
    )
    unique_keys = [Identifier(name=name) for name in key_names]

    # Generate variant values
    values = [draw(ftl_patterns()) for _ in range(num_variants)]

    # Choose exactly one variant to be the default
    default_index = draw(st.integers(min_value=0, max_value=num_variants - 1))

    variants = tuple(
        Variant(key=unique_keys[i], value=values[i], default=i == default_index)
        for i in range(num_variants)
    )

    return SelectExpression(selector=selector, variants=variants)


@composite
def ftl_message_nodes(draw: st.DrawFn) -> Message:
    """Generate Message AST nodes.

    Messages must have a value (pattern). Messages without values
    are invalid FTL and get parsed as Junk.
    """
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())
    return Message(id=id_val, value=value, attributes=())


@composite
def ftl_comment_nodes(draw: st.DrawFn) -> Comment:
    """Generate Comment AST nodes."""
    content = draw(ftl_simple_text())
    return Comment(content=content, type=CommentType.COMMENT)


@composite
def ftl_junk_nodes(draw: st.DrawFn) -> Junk:
    """Generate Junk AST nodes."""
    content = draw(st.text(min_size=1, max_size=50))
    return Junk(content=content)


@composite
def ftl_term_nodes(draw: st.DrawFn) -> Term:
    """Generate Term AST nodes."""
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())
    return Term(id=id_val, value=value, attributes=())


@composite
def ftl_resources(draw: st.DrawFn) -> Resource:
    """Generate complete Resource AST nodes.

    Generates primarily messages with occasional comments.
    Ensures unique message IDs within a resource.
    """
    entries = draw(
        st.lists(
            st.one_of(
                ftl_message_nodes(),
                ftl_message_nodes(),
                ftl_message_nodes(),
                ftl_comment_nodes(),
            ),
            min_size=1,
            max_size=5,
        )
    )

    # Deduplicate message IDs
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
    """Generate any AST entry type for type guard testing."""
    return draw(
        st.one_of(
            ftl_message_nodes(),
            ftl_term_nodes(),
            ftl_comment_nodes(),
            ftl_junk_nodes(),
        )
    )


@composite
def any_ast_pattern_element(draw: st.DrawFn) -> TextElement | Placeable:
    """Generate any pattern element type for type guard testing."""
    return draw(st.one_of(ftl_text_elements(), ftl_placeables()))


# =============================================================================
# Edge Case Strategies (boundary testing)
# =============================================================================


@composite
def ftl_boundary_identifiers(draw: st.DrawFn) -> str:
    """Generate boundary-case identifiers.

    Tests: single char, very long, edge characters.
    Uses FTL_IDENTIFIER_FIRST_CHARS per spec (includes uppercase).
    """
    case = draw(st.sampled_from(["single", "long", "numeric", "hyphen", "underscore"]))
    match case:
        case "single":
            return draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
        case "long":
            first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
            return first + "x" * draw(st.integers(50, 100))
        case "numeric":
            first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
            return first + "123456789"
        case "hyphen":
            first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
            return first + "-" + draw(ftl_identifiers())
        case _:  # underscore
            first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
            return first + "_" + draw(ftl_identifiers())


@composite
def ftl_empty_pattern_messages(draw: st.DrawFn) -> str:
    """Generate messages with minimal/empty patterns.

    Edge case: message = (with trailing space only)
    """
    msg_id = draw(ftl_identifiers())
    case = draw(st.sampled_from(["space", "single", "newline"]))
    match case:
        case "space":
            return f"{msg_id} = "
        case "single":
            return f"{msg_id} = x"
        case _:
            return f"{msg_id} =\n"


@composite
def ftl_multiline_messages(draw: st.DrawFn) -> str:
    """Generate multiline FTL messages.

    Tests continuation line handling with various indentation.
    """
    msg_id = draw(ftl_identifiers())
    line1 = draw(ftl_simple_text())
    indent = " " * draw(st.integers(1, 8))
    line2 = draw(ftl_simple_text())

    return f"{msg_id} = {line1}\n{indent}{line2}"


# =============================================================================
# Recursive Strategies (deep nesting tests)
# =============================================================================


def _ensure_unique_variant_keys_with_default(
    variants: list[Variant],
) -> tuple[Variant, ...]:
    """Ensure variants have unique keys and at least one default."""
    seen_keys: set[str] = set()
    unique_variants: list[Variant] = []

    for v in variants:
        key_name = v.key.name if hasattr(v.key, "name") else str(v.key.value)
        if key_name not in seen_keys:
            seen_keys.add(key_name)
            unique_variants.append(v)

    # Ensure at least 2 variants
    if len(unique_variants) < 2:
        unique_variants.append(
            Variant(
                key=Identifier(name="fallback"),
                value=Pattern(elements=(TextElement(value="other"),)),
                default=False,
            )
        )

    # Ensure at least one default
    if not any(v.default for v in unique_variants):
        unique_variants[-1] = Variant(
            key=unique_variants[-1].key,
            value=unique_variants[-1].value,
            default=True,
        )

    return tuple(unique_variants)


def ftl_deeply_nested_selects(
    max_depth: int = 5,
) -> st.SearchStrategy[SelectExpression]:
    """Generate deeply nested select expressions.

    Used for validator stress testing - creates selects with nested selects
    as selectors, up to max_depth levels deep.

    Args:
        max_depth: Maximum nesting depth for select expressions

    Returns:
        Strategy generating SelectExpression with possible nesting
    """
    base_select = st.builds(
        SelectExpression,
        selector=ftl_variable_references(),
        variants=st.lists(ftl_variants(), min_size=2, max_size=4).map(
            _ensure_unique_variant_keys_with_default
        ),
    )

    def extend(
        children: st.SearchStrategy[SelectExpression],
    ) -> st.SearchStrategy[SelectExpression]:
        return st.builds(
            SelectExpression,
            selector=children,
            variants=st.lists(ftl_variants(), min_size=2, max_size=4).map(
                _ensure_unique_variant_keys_with_default
            ),
        )

    return st.recursive(base_select, extend, max_leaves=max_depth)


# =============================================================================
# AST Mutation Strategies
# =============================================================================


@composite
def mutate_identifier(draw: st.DrawFn, identifier: Identifier) -> Identifier:
    """Mutate an identifier by changing its name."""
    mutation_type = draw(st.sampled_from(["prefix", "suffix", "replace", "case"]))

    match mutation_type:
        case "prefix":
            new_name = "mut_" + identifier.name
        case "suffix":
            new_name = identifier.name + "_mut"
        case "replace":
            new_name = draw(ftl_identifiers())
        case _:  # case
            new_name = identifier.name.swapcase()

    return Identifier(name=new_name)


@composite
def mutate_text_element(draw: st.DrawFn, element: TextElement) -> TextElement:
    """Mutate a text element's value."""
    mutation_type = draw(st.sampled_from(["append", "prepend", "replace", "empty"]))

    match mutation_type:
        case "append":
            new_value = element.value + draw(ftl_simple_text())
        case "prepend":
            new_value = draw(ftl_simple_text()) + element.value
        case "replace":
            new_value = draw(ftl_simple_text())
        case _:  # empty
            new_value = " "

    return TextElement(value=new_value)


@composite
def mutate_pattern(draw: st.DrawFn, pattern: Pattern) -> Pattern:
    """Mutate a pattern by modifying its elements."""
    if not pattern.elements:
        # Empty pattern - add an element
        new_elements = (draw(ftl_text_elements()),)
        return Pattern(elements=new_elements)

    mutation_type = draw(st.sampled_from(["add", "remove", "modify"]))

    elements = list(pattern.elements)

    match mutation_type:
        case "add":
            new_elem = draw(st.one_of(ftl_text_elements(), ftl_placeables()))
            pos = draw(st.integers(0, len(elements)))
            elements.insert(pos, new_elem)
        case "remove":
            if len(elements) > 1:
                idx = draw(st.integers(0, len(elements) - 1))
                elements.pop(idx)
        case _:  # modify
            if elements:
                idx = draw(st.integers(0, len(elements) - 1))
                if isinstance(elements[idx], TextElement):
                    elem = elements[idx]
                    elements[idx] = draw(mutate_text_element(elem))  # type: ignore[arg-type]

    return Pattern(elements=tuple(elements))


@composite
def mutate_message(draw: st.DrawFn, message: Message) -> Message:
    """Mutate a message (id, value, or attributes)."""
    mutation_type = draw(st.sampled_from(["id", "value", "add_attr", "remove_attr"]))

    new_id = message.id
    new_value = message.value
    new_attrs = list(message.attributes)

    match mutation_type:
        case "id":
            new_id = draw(mutate_identifier(message.id))
        case "value":
            if message.value:
                new_value = draw(mutate_pattern(message.value))
        case "add_attr":
            attr = Attribute(
                id=Identifier(name=draw(ftl_identifiers())),
                value=draw(ftl_patterns()),
            )
            new_attrs.append(attr)
        case _:  # remove_attr
            if new_attrs:
                idx = draw(st.integers(0, len(new_attrs) - 1))
                new_attrs.pop(idx)

    return Message(id=new_id, value=new_value, attributes=tuple(new_attrs))


@composite
def swap_variant_keys(draw: st.DrawFn, select: SelectExpression) -> SelectExpression:
    """Swap variant keys in a select expression."""
    variants = list(select.variants)

    if len(variants) < 2:
        return select

    # Swap two random variants' keys
    idx1, idx2 = draw(st.lists(st.integers(0, len(variants) - 1), min_size=2, max_size=2))
    if idx1 != idx2:
        key1 = variants[idx1].key
        key2 = variants[idx2].key
        variants[idx1] = Variant(
            key=key2, value=variants[idx1].value, default=variants[idx1].default
        )
        variants[idx2] = Variant(
            key=key1, value=variants[idx2].value, default=variants[idx2].default
        )

    return SelectExpression(selector=select.selector, variants=tuple(variants))


# =============================================================================
# Resolver Argument Strategies
# =============================================================================


@composite
def resolver_string_args(draw: st.DrawFn) -> dict[str, str]:
    """Generate string-only resolver arguments."""
    keys = draw(st.lists(ftl_identifiers(), min_size=0, max_size=5, unique=True))
    return {k: draw(ftl_simple_text()) for k in keys}


@composite
def resolver_number_args(draw: st.DrawFn) -> dict[str, int | float]:
    """Generate number-only resolver arguments."""
    keys = draw(st.lists(ftl_identifiers(), min_size=0, max_size=5, unique=True))
    return {k: draw(ftl_numbers()) for k in keys}


@composite
def resolver_mixed_args(draw: st.DrawFn) -> dict[str, str | int | float]:
    """Generate mixed-type resolver arguments."""
    keys = draw(st.lists(ftl_identifiers(), min_size=0, max_size=5, unique=True))
    result: dict[str, str | int | float] = {}

    for k in keys:
        value: str | int | float = draw(
            st.one_of(
                ftl_simple_text(),
                st.integers(min_value=-1000000, max_value=1000000),
                st.floats(
                    min_value=-1000000,
                    max_value=1000000,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            )
        )
        result[k] = value

    return result


@composite
def resolver_edge_case_args(draw: st.DrawFn) -> dict[str, str | int | float]:
    """Generate edge case resolver arguments."""
    edge_values: list[str | int | float] = [
        "",  # Empty string
        " ",  # Whitespace only
        "0",  # Zero as string
        0,  # Zero
        -1,  # Negative
        0.0,  # Float zero
        0.1,  # Small float
        1e10,  # Large number
        -1e10,  # Large negative
    ]

    keys = draw(st.lists(ftl_identifiers(), min_size=1, max_size=3, unique=True))
    return {k: draw(st.sampled_from(edge_values)) for k in keys}


# =============================================================================
# Deeply Nested AST Strategies
# =============================================================================


@composite
def deeply_nested_placeables(draw: st.DrawFn, depth: int = 10) -> Placeable:
    """Generate deeply nested placeables: { { { ... { $var } ... } } }."""
    # Start with innermost expression
    inner: VariableReference | Placeable = draw(ftl_variable_references())

    # Wrap in placeables
    for _ in range(depth):
        inner = Placeable(expression=inner)

    return inner  # type: ignore[return-value]


@composite
def deeply_nested_message_chain(_draw: st.DrawFn, depth: int = 10) -> Resource:
    """Generate a chain of messages referencing each other."""
    messages: list[Message] = []

    for i in range(depth):
        msg_id = Identifier(name=f"msg{i}")

        if i < depth - 1:
            # Reference next message
            ref = MessageReference(id=Identifier(name=f"msg{i + 1}"), attribute=None)
            pattern = Pattern(elements=(Placeable(expression=ref),))
        else:
            # Terminal message
            pattern = Pattern(elements=(TextElement(value="End of chain"),))

        messages.append(Message(id=msg_id, value=pattern, attributes=()))

    return Resource(entries=tuple(messages))


@composite
def deeply_nested_select(draw: st.DrawFn, depth: int = 5) -> SelectExpression:
    """Generate deeply nested select expressions."""
    # Base case: simple select
    base_selector = draw(ftl_variable_references())
    base_variants = (
        Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=(TextElement(value="One"),)),
            default=False,
        ),
        Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="Other"),)),
            default=True,
        ),
    )

    current = SelectExpression(selector=base_selector, variants=base_variants)

    # Wrap in additional selects
    for i in range(depth - 1):
        # Use current select as value in a variant
        wrapper_variants = (
            Variant(
                key=Identifier(name=f"nested{i}"),
                value=Pattern(elements=(Placeable(expression=current),)),
                default=False,
            ),
            Variant(
                key=Identifier(name="other"),
                value=Pattern(elements=(TextElement(value=f"Fallback {i}"),)),
                default=True,
            ),
        )
        current = SelectExpression(
            selector=draw(ftl_variable_references()),
            variants=wrapper_variants,
        )

    return current


@composite
def wide_resource(_draw: st.DrawFn, width: int = 50) -> Resource:
    """Generate a resource with many messages (width test)."""
    messages: list[Message] = []

    for i in range(width):
        msg = Message(
            id=Identifier(name=f"msg{i}"),
            value=Pattern(elements=(TextElement(value=f"Message {i}"),)),
            attributes=(),
        )
        messages.append(msg)

    return Resource(entries=tuple(messages))


@composite
def message_with_many_attributes(_draw: st.DrawFn, attr_count: int = 20) -> Message:
    """Generate a message with many attributes."""
    attrs: list[Attribute] = []

    for i in range(attr_count):
        attr = Attribute(
            id=Identifier(name=f"attr{i}"),
            value=Pattern(elements=(TextElement(value=f"Attribute {i}"),)),
        )
        attrs.append(attr)

    return Message(
        id=Identifier(name="many_attrs"),
        value=Pattern(elements=(TextElement(value="Main value"),)),
        attributes=tuple(attrs),
    )
