from tests.strategies.ftl_ast import (
    ftl_patterns,
    ftl_placeables,
    ftl_text_elements,
    ftl_variable_references,
    ftl_variants,
)
from tests.strategies.ftl_shared import (
    FTL_IDENTIFIER_FIRST_CHARS,
    Attribute,
    Decimal,
    Identifier,
    Message,
    MessageReference,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
    composite,
    event,
    st,
)
from tests.strategies.ftl_strings import ftl_identifiers, ftl_numbers, ftl_simple_text


@composite
def ftl_boundary_identifiers(draw: st.DrawFn) -> str:
    """Generate boundary-case identifiers.

    Tests: single char, very long, edge characters.
    Uses FTL_IDENTIFIER_FIRST_CHARS per spec (includes uppercase).
    """
    case = draw(st.sampled_from(["single", "long", "numeric", "hyphen", "underscore"]))
    event(f"strategy=boundary_identifier_{case}")
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
    event(f"strategy=empty_pattern_{case}")
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
    event(f"strategy=multiline_indent_{len(indent)}")

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

    # Ensure exactly one default variant (required by SelectExpression.__post_init__)
    # First, strip all defaults
    unique_variants = [
        Variant(key=v.key, value=v.value, default=False) for v in unique_variants
    ]
    # Then set exactly the last one as default
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
    event(f"strategy=mutate_identifier_{mutation_type}")

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
    event(f"strategy=mutate_text_{mutation_type}")

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
        event("strategy=mutate_pattern_seed")
        new_elements = (draw(ftl_text_elements()),)
        return Pattern(elements=new_elements)

    mutation_type = draw(st.sampled_from(["add", "remove", "modify"]))
    event(f"strategy=mutate_pattern_{mutation_type}")

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
    event(f"strategy=mutate_message_{mutation_type}")

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
        event("strategy=swap_variant_keys_noop")
        return select

    # Swap two random variants' keys
    idx1, idx2 = draw(st.lists(st.integers(0, len(variants) - 1), min_size=2, max_size=2))
    event("strategy=swap_variant_keys_attempt")
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
    event(f"strategy=resolver_string_args_{len(keys)}")
    return {k: draw(ftl_simple_text()) for k in keys}


@composite
def resolver_number_args(draw: st.DrawFn) -> dict[str, int | Decimal]:
    """Generate number-only resolver arguments."""
    keys = draw(st.lists(ftl_identifiers(), min_size=0, max_size=5, unique=True))
    event(f"strategy=resolver_number_args_{len(keys)}")
    return {k: draw(ftl_numbers()) for k in keys}


@composite
def resolver_mixed_args(draw: st.DrawFn) -> dict[str, str | int | Decimal]:
    """Generate mixed-type resolver arguments."""
    keys = draw(st.lists(ftl_identifiers(), min_size=0, max_size=5, unique=True))
    event(f"strategy=resolver_mixed_args_{len(keys)}")
    result: dict[str, str | int | Decimal] = {}

    for k in keys:
        value: str | int | Decimal = draw(
            st.one_of(
                ftl_simple_text(),
                st.integers(min_value=-1000000, max_value=1000000),
                st.decimals(
                    min_value=Decimal(-1000000),
                    max_value=Decimal(1000000),
                    allow_nan=False,
                    allow_infinity=False,
                ),
            )
        )
        result[k] = value

    return result


@composite
def resolver_edge_case_args(draw: st.DrawFn) -> dict[str, str | int | Decimal]:
    """Generate edge case resolver arguments."""
    edge_values: list[str | int | Decimal] = [
        "",  # Empty string
        " ",  # Whitespace only
        "0",  # Zero as string
        0,  # Zero
        -1,  # Negative
        Decimal(0),  # Decimal zero
        Decimal("0.1"),  # Small decimal
        Decimal(10000000000),  # Large number
        Decimal(-10000000000),  # Large negative
    ]

    keys = draw(st.lists(ftl_identifiers(), min_size=1, max_size=3, unique=True))
    event(f"strategy=resolver_edge_args_{len(keys)}")
    return {k: draw(st.sampled_from(edge_values)) for k in keys}


# =============================================================================
# Deeply Nested AST Strategies
# =============================================================================


@composite
def deeply_nested_placeables(draw: st.DrawFn, depth: int = 10) -> Placeable:
    """Generate deeply nested placeables: { { { ... { $var } ... } } }."""
    event(f"strategy=deep_placeable_depth={depth}")
    # Start with innermost expression
    inner: VariableReference | Placeable = draw(ftl_variable_references())

    # Wrap in placeables
    for _ in range(depth):
        inner = Placeable(expression=inner)

    return inner  # type: ignore[return-value]


def deeply_nested_message_chain(depth: int = 10) -> st.SearchStrategy[Resource]:
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

    return st.just(Resource(entries=tuple(messages)))


@composite
def deeply_nested_select(draw: st.DrawFn, depth: int = 5) -> SelectExpression:
    """Generate deeply nested select expressions."""
    event(f"strategy=deep_select_depth={depth}")
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


def wide_resource(width: int = 50) -> st.SearchStrategy[Resource]:
    """Generate a resource with many messages (width test)."""
    messages: list[Message] = []

    for i in range(width):
        msg = Message(
            id=Identifier(name=f"msg{i}"),
            value=Pattern(elements=(TextElement(value=f"Message {i}"),)),
            attributes=(),
        )
        messages.append(msg)

    return st.just(Resource(entries=tuple(messages)))


def message_with_many_attributes(attr_count: int = 20) -> st.SearchStrategy[Message]:
    """Generate a message with many attributes."""
    attrs: list[Attribute] = []

    for i in range(attr_count):
        attr = Attribute(
            id=Identifier(name=f"attr{i}"),
            value=Pattern(elements=(TextElement(value=f"Attribute {i}"),)),
        )
        attrs.append(attr)

    return st.just(
        Message(
            id=Identifier(name="many_attrs"),
            value=Pattern(elements=(TextElement(value="Main value"),)),
            attributes=tuple(attrs),
        )
    )
