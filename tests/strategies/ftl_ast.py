from tests.strategies.ftl_shared import (
    Attribute,
    CallArguments,
    Comment,
    CommentType,
    Decimal,
    Expression,
    FunctionReference,
    Identifier,
    InlineExpression,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
    composite,
    event,
    st,
)
from tests.strategies.ftl_strings import ftl_identifiers, ftl_numbers, ftl_simple_text


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
    """Generate NumberLiteral AST nodes with valid FTL raw format.

    FTL number syntax: -?[0-9]+(.[0-9]+)?
    No scientific notation allowed. Uses fixed-point notation for Decimals.
    """
    value = draw(ftl_numbers())

    # Ensure raw string uses fixed-point notation (no scientific notation)
    # str(Decimal) may use 'E' notation for very small/large values
    raw = format(value, "f") if isinstance(value, Decimal) else str(value)

    return NumberLiteral(value=value, raw=raw)


@composite
def ftl_string_literals(draw: st.DrawFn) -> StringLiteral:
    """Generate StringLiteral AST nodes."""
    value = draw(ftl_simple_text())
    return StringLiteral(value=value)


@composite
def ftl_named_arguments(draw: st.DrawFn) -> NamedArgument:
    """Generate NamedArgument AST nodes for function calls.

    Named arguments have the form: key: value
    Example: minimumFractionDigits: 2
    """
    name = draw(ftl_identifiers())
    # Per FTL spec EBNF: named-argument ::= identifier ":" literal
    # where literal ::= number-literal | quoted-literal
    # Named argument values are constrained to StringLiteral and NumberLiteral only.
    value = draw(
        st.one_of(
            ftl_string_literals(),
            ftl_number_literals(),
        )
    )
    return NamedArgument(name=Identifier(name=name), value=value)


@composite
def ftl_call_arguments(draw: st.DrawFn) -> CallArguments:
    """Generate CallArguments AST nodes for function/term calls.

    Call arguments consist of positional and named arguments.
    Example: $count, minimumFractionDigits: 2
    """
    # Generate 0-3 positional arguments
    num_positional = draw(st.integers(min_value=0, max_value=3))
    positional = tuple(
        draw(
            st.one_of(
                ftl_variable_references(),
                ftl_string_literals(),
                ftl_number_literals(),
            )
        )
        for _ in range(num_positional)
    )

    # Generate 0-3 named arguments with unique names
    num_named = draw(st.integers(min_value=0, max_value=3))
    named_keys = draw(
        st.lists(
            st.sampled_from([
                "minimumFractionDigits",
                "maximumFractionDigits",
                "useGrouping",
                "style",
                "currency",
                "dateStyle",
                "timeStyle",
            ]),
            min_size=num_named,
            max_size=num_named,
            unique=True,
        )
    )
    named = tuple(
        NamedArgument(
            name=Identifier(name=key),
            value=draw(
                st.one_of(
                    ftl_string_literals(),
                    ftl_number_literals(),
                )
            ),
        )
        for key in named_keys
    )

    return CallArguments(positional=positional, named=named)


@composite
def ftl_function_references(draw: st.DrawFn) -> FunctionReference:
    """Generate FunctionReference AST nodes.

    Function references are UPPERCASE per Fluent convention.
    Example: NUMBER($count, minimumFractionDigits: 2)
    """
    # Use realistic builtin function names
    func_name = draw(
        st.sampled_from([
            "NUMBER",
            "DATETIME",
            "CURRENCY",
            "PLURAL",
            "CUSTOM",
        ])
    )
    arguments = draw(ftl_call_arguments())
    return FunctionReference(
        id=Identifier(name=func_name),
        arguments=arguments,
    )


@composite
def ftl_term_references(draw: st.DrawFn) -> TermReference:
    """Generate TermReference AST nodes.

    Term references start with - and may have attributes and arguments.
    Example: -brand, -brand.short, -term(case: "genitive")
    """
    term_id = draw(ftl_identifiers())
    # Optionally include an attribute reference
    has_attr = draw(st.booleans())
    attribute = Identifier(name=draw(ftl_identifiers())) if has_attr else None
    # Optionally include arguments (for parameterized terms)
    has_args = draw(st.booleans())
    arguments = draw(ftl_call_arguments()) if has_args else None

    return TermReference(
        id=Identifier(name=term_id),
        attribute=attribute,
        arguments=arguments,
    )


@composite
def ftl_message_references(draw: st.DrawFn) -> MessageReference:
    """Generate MessageReference AST nodes.

    Message references refer to other messages, optionally with attributes.
    Example: other-message, other-message.title
    """
    msg_id = draw(ftl_identifiers())
    # Optionally include an attribute reference
    has_attr = draw(st.booleans())
    attribute = Identifier(name=draw(ftl_identifiers())) if has_attr else None

    return MessageReference(
        id=Identifier(name=msg_id),
        attribute=attribute,
    )


@composite
def ftl_placeables(draw: st.DrawFn, max_depth: int = 2) -> Placeable:
    """Generate Placeable AST nodes with comprehensive expression coverage.

    Generates all InlineExpression types defined in the Fluent spec:
    - StringLiteral, NumberLiteral, VariableReference (simple)
    - MessageReference, TermReference, FunctionReference (references)
    - Nested Placeable (recursive)

    Uses weighted probability to control explosion while ensuring coverage.

    Events emitted:
    - strategy=placeable_{choice}: Expression type generated (for HypoFuzz guidance)

    Args:
        draw: Hypothesis draw function
        max_depth: Maximum nesting depth (default 2 to avoid explosion)
    """
    expression: Expression
    if max_depth <= 0:
        # Base case: only simple leaf expressions
        choice = draw(st.sampled_from(["variable", "string", "number"]))
        match choice:
            case "variable":
                expression = draw(ftl_variable_references())
            case "string":
                expression = draw(ftl_string_literals())
            case _:  # number
                expression = draw(ftl_number_literals())
        event(f"strategy=placeable_{choice}_leaf")
    else:
        # Choose expression type with weighted probability:
        # - Simple types (variable, string, number): 60% - common cases
        # - References (message, term, function): 30% - complex but important
        # - Nested/select: 10% - recursive, expensive
        choice = draw(
            st.sampled_from([
                # Simple types (6x weight)
                "variable", "variable", "variable",
                "string", "string",
                "number",
                # Reference types (3x weight)
                "message_ref",
                "term_ref",
                "function_ref",
                # Recursive types (1x weight)
                "nested",
            ])
        )

        match choice:
            case "variable":
                expression = draw(ftl_variable_references())
            case "string":
                expression = draw(ftl_string_literals())
            case "number":
                expression = draw(ftl_number_literals())
            case "message_ref":
                expression = draw(ftl_message_references())
            case "term_ref":
                expression = draw(ftl_term_references())
            case "function_ref":
                expression = draw(ftl_function_references())
            case _:  # nested
                inner = draw(ftl_placeables(max_depth=max_depth - 1))
                expression = inner.expression

        # Emit event for HypoFuzz coverage guidance
        event(f"strategy=placeable_{choice}")

    return Placeable(expression=expression)


@composite
def ftl_deep_placeables(draw: st.DrawFn, depth: int = 5) -> Placeable:
    """Generate deeply nested Placeable structures for depth limit testing.

    Creates chains of nested placeables up to the specified depth.
    Used for testing parser/serializer depth guards.

    Events emitted:
    - strategy=deep_placeable_depth={n}: Current nesting depth
    """
    event(f"strategy=deep_placeable_depth={depth}")

    if depth <= 1:
        return Placeable(expression=draw(ftl_variable_references()))

    inner = draw(ftl_deep_placeables(depth=depth - 1))
    return Placeable(expression=inner.expression)


@composite
def ftl_reference_placeables(draw: st.DrawFn) -> Placeable:
    """Generate placeables with reference expressions only.

    Targeted strategy for fuzzing the previously-underexposed reference types:
    - FunctionReference: { NUMBER($x) }
    - TermReference: { -brand }
    - MessageReference: { other-message }

    Used for intensive coverage of function/term/message reference parsing
    and resolution paths.
    """
    expression = draw(
        st.one_of(
            ftl_function_references(),
            ftl_term_references(),
            ftl_message_references(),
        )
    )
    return Placeable(expression=expression)


@composite
def ftl_boundary_depth_placeables(draw: st.DrawFn) -> Placeable:
    """Generate placeables at MAX_DEPTH boundary for limit testing.

    Events emitted:
    - boundary={under|at|over}_max_depth: Depth boundary condition

    Specifically targets the boundary conditions around MAX_DEPTH:
    - MAX_DEPTH - 1: Just under limit (should succeed)
    - MAX_DEPTH: At limit (should succeed or fail cleanly)
    - MAX_DEPTH + 1: Just over limit (should fail cleanly)

    Used for testing:
    - Parser depth guards
    - Serializer depth guards
    - Resolver depth tracking
    """
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415 - import inside function

    # Choose boundary point
    boundary = draw(
        st.sampled_from([
            ("under", MAX_DEPTH - 1),
            ("at", MAX_DEPTH),
            ("over", MAX_DEPTH + 1),
        ])
    )
    label, depth = boundary

    # Emit boundary event for HypoFuzz coverage guidance
    event(f"boundary={label}_max_depth")

    # Generate nested placeable at chosen depth
    return draw(ftl_deep_placeables(depth=min(depth, 150)))  # Cap at 150 for safety


@composite
def ftl_boundary_depth_messages(draw: st.DrawFn) -> Message:
    """Generate Message AST nodes with boundary-depth patterns.

    Creates complete Message nodes containing deeply nested structures
    at the MAX_DEPTH boundary for integration testing.
    """
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415 - import inside function

    msg_id = Identifier(name=draw(ftl_identifiers()))

    # Choose depth relative to MAX_DEPTH
    depth_offset = draw(st.sampled_from([-1, 0, 1]))
    depth = MAX_DEPTH + depth_offset

    # Generate pattern with deeply nested placeable
    deep_placeable = draw(ftl_deep_placeables(depth=min(depth, 150)))
    pattern = Pattern(elements=(TextElement(value="Prefix "), deep_placeable))

    return Message(id=msg_id, value=pattern, attributes=())


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
    """Generate individual Variant AST nodes for select expressions.

    WARNING: This strategy generates variants with RANDOM default flags.
    FTL SelectExpression requires EXACTLY ONE default variant (marked with *).
    Using this strategy directly to build SelectExpression will likely fail
    validation in SelectExpression.__post_init__.

    For valid SelectExpression generation, use ftl_select_expressions() which
    properly manages the exactly-one-default invariant.

    This strategy is intended for:
    - Testing individual variant serialization
    - Type guard testing
    - Low-level AST manipulation tests
    """
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

    Events emitted:
    - strategy=select_selector_{type}: Selector expression type (for HypoFuzz)
    - strategy=select_variants_{n}: Number of variants generated

    Ensures:
    - Exactly one default variant (per Fluent spec)
    - Unique variant keys (per Fluent spec)

    D3 fix: Selector can be any InlineExpression, not just VariableReference.
    Per FTL spec, common patterns include NUMBER($count) for locale-aware plurals.
    """
    # D3 fix: Generate diverse selector types with weighted probability
    selector_type = draw(
        st.sampled_from([
            "variable", "variable", "variable", "variable",  # 40% variable
            "number", "number",  # 20% number literal
            "function", "function",  # 20% function (e.g., NUMBER($x))
            "string",  # 10% string literal
            "term_ref",  # 10% term reference
        ])
    )

    selector: InlineExpression
    match selector_type:
        case "variable":
            selector = draw(ftl_variable_references())
        case "number":
            selector = draw(ftl_number_literals())
        case "function":
            selector = draw(ftl_function_references())
        case "string":
            selector = draw(ftl_string_literals())
        case _:  # term_ref
            selector = draw(ftl_term_references())

    event(f"strategy=select_selector_{selector_type}")

    # Generate 2-4 unique variant keys using st.sampled_from predefined set
    # This avoids expensive rejection-based uniqueness while ensuring valid keys
    num_variants = draw(st.integers(min_value=2, max_value=4))

    # Emit event for HypoFuzz coverage guidance
    event(f"strategy=select_variants_{num_variants}")

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
def ftl_select_expressions_with_number_keys(draw: st.DrawFn) -> SelectExpression:
    """Generate SelectExpression with NumberLiteral variant keys.

    Events emitted:
    - strategy=select_number_keys: SelectExpression with numeric keys

    Used to test serialization branch for NumberLiteral variant keys.
    Per Fluent spec, variant keys can be either Identifier or NumberLiteral.
    """
    selector = draw(ftl_variable_references())

    # Generate 2-4 numeric variant keys
    num_variants = draw(st.integers(min_value=2, max_value=4))

    # Emit event for HypoFuzz coverage guidance
    event("strategy=select_number_keys")

    # Generate unique numeric keys (0, 1, 2, etc.)
    numeric_keys = [NumberLiteral(value=Decimal(str(i)), raw=str(i)) for i in range(num_variants)]

    # Generate variant values
    values = [draw(ftl_patterns()) for _ in range(num_variants)]

    # Choose exactly one variant to be the default
    default_index = draw(st.integers(min_value=0, max_value=num_variants - 1))

    variants = tuple(
        Variant(key=numeric_keys[i], value=values[i], default=i == default_index)
        for i in range(num_variants)
    )

    return SelectExpression(selector=selector, variants=variants)


@composite
def ftl_function_references_no_args(draw: st.DrawFn) -> FunctionReference:
    """Generate FunctionReference without arguments.

    Events emitted:
    - strategy=function_no_args: FunctionReference with empty arguments

    Used to test serialization branch for FunctionReference without arguments.
    While uncommon in practice, the AST structure permits CallArguments with
    empty positional and named tuples.
    """
    # Use realistic builtin function names
    func_name = draw(
        st.sampled_from([
            "NUMBER",
            "DATETIME",
            "CURRENCY",
            "PLURAL",
            "CUSTOM",
        ])
    )

    # Emit event for HypoFuzz coverage guidance
    event("strategy=function_no_args")

    # Create CallArguments with no arguments
    arguments = CallArguments(positional=(), named=())

    return FunctionReference(
        id=Identifier(name=func_name),
        arguments=arguments,
    )


@composite
def ftl_attribute_nodes(draw: st.DrawFn) -> Attribute:
    """Generate Attribute AST nodes for messages and terms.

    Events emitted:
    - strategy=attribute: Attribute node generated (for HypoFuzz guidance)

    Attributes are key-value pairs attached to messages/terms:
    - .title = Button Title
    - .aria-label = Accessible label
    - .accesskey = B
    """
    attr_id = Identifier(name=draw(ftl_identifiers()))
    attr_value = draw(ftl_patterns())

    event("strategy=attribute")
    return Attribute(id=attr_id, value=attr_value)


@composite
def ftl_message_nodes(draw: st.DrawFn, *, include_attributes: bool = True) -> Message:
    """Generate Message AST nodes.

    Events emitted:
    - strategy=message_{with|no}_attrs: Message attribute presence (for HypoFuzz)

    Messages must have a value (pattern). Messages without values
    are invalid FTL and get parsed as Junk.

    Args:
        include_attributes: If True, 30% chance of generating attributes.
    """
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())

    # 30% chance of attributes when enabled (D1 fix)
    attributes: tuple[Attribute, ...] = ()
    if include_attributes and draw(st.integers(min_value=0, max_value=9)) < 3:
        num_attrs = draw(st.integers(min_value=1, max_value=3))
        # Generate unique attribute names
        attr_names = draw(
            st.lists(ftl_identifiers(), min_size=num_attrs, max_size=num_attrs, unique=True)
        )
        attributes = tuple(
            Attribute(id=Identifier(name=name), value=draw(ftl_patterns()))
            for name in attr_names
        )
        event("strategy=message_with_attrs")
    else:
        event("strategy=message_no_attrs")

    return Message(id=id_val, value=value, attributes=attributes)


@composite
def ftl_comment_nodes(draw: st.DrawFn) -> Comment:
    """Generate Comment AST nodes of all types.

    Events emitted:
    - strategy=comment_{type}: Comment type generated (for HypoFuzz guidance)

    Generates all three FTL comment types per spec:
    - COMMENT: # Single comment
    - GROUP: ## Group comment (applies to following entries)
    - RESOURCE: ### Resource comment (file-level)
    """
    content = draw(ftl_simple_text())
    # D5 fix: Generate all comment types with weighted probability
    comment_type = draw(
        st.sampled_from([
            CommentType.COMMENT,
            CommentType.COMMENT,
            CommentType.COMMENT,  # 60% regular
            CommentType.GROUP,  # 20% group
            CommentType.RESOURCE,  # 20% resource
        ])
    )
    event(f"strategy=comment_{comment_type.name.lower()}")
    return Comment(content=content, type=comment_type)


@composite
def ftl_junk_nodes(draw: st.DrawFn) -> Junk:
    """Generate Junk AST nodes."""
    content = draw(st.text(min_size=1, max_size=50))
    return Junk(content=content)


@composite
def ftl_term_nodes(draw: st.DrawFn, *, include_attributes: bool = True) -> Term:
    """Generate Term AST nodes.

    Events emitted:
    - strategy=term_{with|no}_attrs: Term attribute presence (for HypoFuzz)

    Args:
        include_attributes: If True, 30% chance of generating attributes.
    """
    id_val = Identifier(name=draw(ftl_identifiers()))
    value = draw(ftl_patterns())

    # 30% chance of attributes when enabled (D1 fix)
    attributes: tuple[Attribute, ...] = ()
    if include_attributes and draw(st.integers(min_value=0, max_value=9)) < 3:
        num_attrs = draw(st.integers(min_value=1, max_value=3))
        attr_names = draw(
            st.lists(ftl_identifiers(), min_size=num_attrs, max_size=num_attrs, unique=True)
        )
        attributes = tuple(
            Attribute(id=Identifier(name=name), value=draw(ftl_patterns()))
            for name in attr_names
        )
        event("strategy=term_with_attrs")
    else:
        event("strategy=term_no_attrs")

    return Term(id=id_val, value=value, attributes=attributes)


@composite
def ftl_resources(draw: st.DrawFn) -> Resource:
    """Generate complete Resource AST nodes with messages, terms, and comments.

    Events emitted:
    - strategy=resource_entry_{type}: Entry types included (for HypoFuzz guidance)

    Generates mixed entry types reflecting real FTL files:
    - 60% messages (primary content)
    - 20% terms (reusable snippets)
    - 20% comments (documentation)

    Ensures unique IDs within each namespace (messages vs terms are separate).
    """
    entries = draw(
        st.lists(
            st.one_of(
                # D2 fix: Include terms in resource generation
                ftl_message_nodes(),  # 60% messages (3x weight)
                ftl_message_nodes(),
                ftl_message_nodes(),
                ftl_term_nodes(),  # 20% terms
                ftl_comment_nodes(),  # 20% comments
            ),
            min_size=1,
            max_size=5,
        )
    )

    # Deduplicate IDs within each namespace (messages and terms are separate)
    seen_message_ids: set[str] = set()
    seen_term_ids: set[str] = set()
    unique_entries: list[Message | Term | Comment] = []

    for entry in entries:
        match entry:
            case Message(id=ident):
                if ident.name not in seen_message_ids:
                    seen_message_ids.add(ident.name)
                    unique_entries.append(entry)
                    event("strategy=resource_entry_message")
            case Term(id=ident):
                if ident.name not in seen_term_ids:
                    seen_term_ids.add(ident.name)
                    unique_entries.append(entry)
                    event("strategy=resource_entry_term")
            case Comment():
                unique_entries.append(entry)
                event("strategy=resource_entry_comment")

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
