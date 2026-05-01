from tests.strategies.ftl_shared import (
    Identifier,
    Pattern,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
    composite,
    event,
    st,
)
from tests.strategies.ftl_strings import ftl_identifiers, ftl_simple_text


@composite
def ftl_invalid_select_no_default(draw: st.DrawFn) -> str:
    """Generate SelectExpression without default variant (invalid per spec).

    FTL requires exactly one variant to be marked as default with *.
    """
    msg_id = draw(ftl_identifiers())
    selector = f"${ draw(ftl_identifiers()) }"
    variant1 = draw(ftl_identifiers())
    variant2 = draw(ftl_identifiers())

    # No asterisk on any variant - invalid
    return f"{msg_id} = {{ {selector} ->\n    [{variant1}] value1\n    [{variant2}] value2\n}}"


@composite
def ftl_invalid_unclosed_placeable(draw: st.DrawFn) -> str:
    """Generate message with unclosed placeable (invalid syntax)."""
    msg_id = draw(ftl_identifiers())
    var_name = draw(ftl_identifiers())
    return f"{msg_id} = Hello {{ ${var_name}"  # Missing closing }


@composite
def ftl_invalid_unterminated_string(draw: st.DrawFn) -> str:
    """Generate message with unterminated string literal (invalid syntax)."""
    msg_id = draw(ftl_identifiers())
    return f'{msg_id} = {{ "unterminated string }}'  # Missing closing quote


@composite
def ftl_invalid_bad_identifier_start(draw: st.DrawFn) -> str:
    """Generate message with invalid identifier (starts with digit/symbol)."""
    bad_start = draw(st.sampled_from(["0", "1", "_", "-", ".", "@"]))
    rest = draw(ftl_identifiers())
    return f"{bad_start}{rest} = value"


@composite
def ftl_invalid_double_equals(draw: st.DrawFn) -> str:
    """Generate message with double equals sign (invalid syntax)."""
    msg_id = draw(ftl_identifiers())
    return f"{msg_id} == value"


@composite
def ftl_invalid_missing_value(draw: st.DrawFn) -> str:
    """Generate message with missing value (invalid for messages)."""
    msg_id = draw(ftl_identifiers())
    return f"{msg_id} ="  # No value, no attributes


@composite
def ftl_invalid_ftl(draw: st.DrawFn) -> str:
    """Generate any type of invalid FTL for error path testing.

    Events emitted:
    - strategy=invalid_{type}: Type of invalid FTL generated

    Used for testing parser error recovery and diagnostic generation.
    """
    # Choose invalid type explicitly to emit event
    invalid_type = draw(
        st.sampled_from([
            "no_default",
            "unclosed_placeable",
            "unterminated_string",
            "bad_identifier",
            "double_equals",
            "missing_value",
        ])
    )

    # Emit event for HypoFuzz coverage guidance
    event(f"strategy=invalid_{invalid_type}")

    match invalid_type:
        case "no_default":
            return draw(ftl_invalid_select_no_default())
        case "unclosed_placeable":
            return draw(ftl_invalid_unclosed_placeable())
        case "unterminated_string":
            return draw(ftl_invalid_unterminated_string())
        case "bad_identifier":
            return draw(ftl_invalid_bad_identifier_start())
        case "double_equals":
            return draw(ftl_invalid_double_equals())
        case _:  # missing_value
            return draw(ftl_invalid_missing_value())


@composite
def ftl_valid_with_injected_error(draw: st.DrawFn) -> tuple[str, str]:
    """Generate valid FTL then inject an error.

    Returns tuple of (original_valid_ftl, corrupted_ftl).
    Useful for differential testing of error recovery.
    """
    # Generate valid FTL
    msg_id = draw(ftl_identifiers())
    value = draw(ftl_simple_text())
    valid_ftl = f"{msg_id} = {value}"

    # Choose corruption type
    corruption = draw(
        st.sampled_from([
            "remove_equals",
            "add_unclosed_brace",
            "corrupt_identifier",
            "insert_null",
        ])
    )

    match corruption:
        case "remove_equals":
            corrupted = valid_ftl.replace(" = ", " ", 1)
        case "add_unclosed_brace":
            corrupted = valid_ftl.replace(value, f"{{ {value}", 1)
        case "corrupt_identifier":
            corrupted = "0" + valid_ftl
        case _:  # insert_null
            mid = len(valid_ftl) // 2
            corrupted = valid_ftl[:mid] + "\x00" + valid_ftl[mid:]

    return (valid_ftl, corrupted)


# =============================================================================
# Circular Reference Strategies (semantic errors, syntactically valid)
# =============================================================================


@composite
def ftl_circular_message_2way(draw: st.DrawFn) -> str:
    """Generate 2-message circular reference: A -> B -> A.

    Syntactically valid FTL that causes infinite loop at resolution time.
    Tests resolver cycle detection.
    """
    # D6 fix: Use st.lists(unique=True) instead of rejection loop
    ids = draw(st.lists(ftl_identifiers(), min_size=2, max_size=2, unique=True))
    id_a, id_b = ids

    return f"{id_a} = {{ {id_b} }}\n{id_b} = {{ {id_a} }}"


@composite
def ftl_circular_message_3way(draw: st.DrawFn) -> str:
    """Generate 3-message circular reference: A -> B -> C -> A.

    Tests transitive cycle detection in resolver.
    """
    # D6 fix: Use st.lists(unique=True) instead of rejection loop
    ids = draw(st.lists(ftl_identifiers(), min_size=3, max_size=3, unique=True))
    id_a, id_b, id_c = ids

    return f"{id_a} = {{ {id_b} }}\n{id_b} = {{ {id_c} }}\n{id_c} = {{ {id_a} }}"


@composite
def ftl_circular_self_reference(draw: st.DrawFn) -> str:
    """Generate self-referencing message: A -> A.

    Simplest form of circular reference.
    """
    msg_id = draw(ftl_identifiers())
    return f"{msg_id} = Value {{ {msg_id} }}"


@composite
def ftl_circular_term_2way(draw: st.DrawFn) -> str:
    """Generate 2-term circular reference: -A -> -B -> -A.

    Tests cycle detection in term resolution.
    """
    # D6 fix: Use st.lists(unique=True) instead of rejection loop
    ids = draw(st.lists(ftl_identifiers(), min_size=2, max_size=2, unique=True))
    id_a, id_b = ids

    return f"-{id_a} = {{ -{id_b} }}\n-{id_b} = {{ -{id_a} }}"


@composite
def ftl_circular_mixed(draw: st.DrawFn) -> str:
    """Generate circular reference mixing messages and terms.

    msg -> -term -> msg creates cross-namespace cycle.
    """
    msg_id = draw(ftl_identifiers())
    term_id = draw(ftl_identifiers())

    return f"{msg_id} = {{ -{term_id} }}\n-{term_id} = {{ {msg_id} }}"


@composite
def ftl_circular_via_attribute(draw: st.DrawFn) -> str:
    """Generate circular reference through attributes.

    msg.attr -> other -> msg.attr
    """
    # D6 fix: Use st.lists(unique=True) instead of rejection loop
    ids = draw(st.lists(ftl_identifiers(), min_size=2, max_size=2, unique=True))
    id_a, id_b = ids
    attr = draw(ftl_identifiers())

    return f"""{id_a} = Base
    .{attr} = {{ {id_b} }}
{id_b} = {{ {id_a}.{attr} }}"""


@composite
def ftl_circular_deep(draw: st.DrawFn) -> str:
    """Generate circular reference with N messages in chain.

    msg0 -> msg1 -> ... -> msgN -> msg0
    """
    chain_length = draw(st.integers(min_value=3, max_value=10))
    ids = [f"msg{i}" for i in range(chain_length)]

    lines = []
    for i, msg_id in enumerate(ids):
        next_id = ids[(i + 1) % chain_length]
        lines.append(f"{msg_id} = {{ {next_id} }}")

    return "\n".join(lines)


@composite
def ftl_circular_references(draw: st.DrawFn) -> str:
    """Generate any type of circular reference for cycle detection testing.

    Events emitted:
    - strategy=circular_{type}: Type of circular reference generated

    Combined strategy for comprehensive cycle detection fuzzing.
    """
    # Map circular types to their generator strategies
    generators = {
        "2way": ftl_circular_message_2way,
        "3way": ftl_circular_message_3way,
        "self": ftl_circular_self_reference,
        "term_2way": ftl_circular_term_2way,
        "mixed": ftl_circular_mixed,
        "via_attr": ftl_circular_via_attribute,
        "deep": ftl_circular_deep,
    }

    # Choose circular reference type explicitly to emit event
    circular_type = draw(st.sampled_from(list(generators.keys())))

    # Emit event for HypoFuzz coverage guidance
    event(f"strategy=circular_{circular_type}")

    return draw(generators[circular_type]())


# =============================================================================
# Semantically Broken Strategies (valid syntax, runtime errors)
# =============================================================================


@composite
def ftl_undefined_reference(draw: st.DrawFn) -> str:
    """Generate message referencing undefined message/term.

    Syntactically valid but will fail at resolution time.
    """
    # D6 fix: Use st.lists(unique=True) instead of rejection loop
    ids = draw(st.lists(ftl_identifiers(), min_size=2, max_size=2, unique=True))
    msg_id, undefined_id = ids

    ref_type = draw(st.sampled_from(["message", "term", "attribute"]))

    match ref_type:
        case "message":
            return f"{msg_id} = {{ {undefined_id} }}"
        case "term":
            return f"{msg_id} = {{ -{undefined_id} }}"
        case _:  # attribute
            return f"{msg_id} = {{ {undefined_id}.nonexistent }}"


@composite
def ftl_undefined_variable(draw: st.DrawFn) -> str:
    """Generate message using undefined variable.

    Variables are provided at format time, so this tests resolver
    behavior when required variables are missing.
    """
    msg_id = draw(ftl_identifiers())
    var_name = draw(ftl_identifiers())

    return f"{msg_id} = Hello {{ ${var_name} }}!"


@composite
def ftl_function_arity_mismatch(draw: st.DrawFn) -> str:
    """Generate function call with wrong number of arguments.

    Tests function argument validation at resolution time.
    """
    msg_id = draw(ftl_identifiers())
    func_name = draw(st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]))

    # NUMBER/DATETIME require at least one positional arg
    arity = draw(st.sampled_from(["zero_args", "too_many_args"]))

    match arity:
        case "zero_args":
            return f"{msg_id} = {{ {func_name}() }}"
        case _:  # too_many_args
            vars_list = ", ".join(f"${draw(ftl_identifiers())}" for _ in range(5))
            return f"{msg_id} = {{ {func_name}({vars_list}) }}"


@composite
def ftl_select_missing_variant(draw: st.DrawFn) -> str:
    """Generate select expression where runtime selector matches no variant.

    Valid syntax but may produce fallback behavior at runtime.
    """
    msg_id = draw(ftl_identifiers())
    var_name = draw(ftl_identifiers())

    # Define variants that won't match most runtime values
    return f"""{msg_id} = {{ ${var_name} ->
    [impossiblevalue1] Value 1
    [impossiblevalue2] Value 2
   *[other] Default
}}"""


@composite
def ftl_semantically_broken(draw: st.DrawFn) -> str:
    """Generate any semantically broken (but syntactically valid) FTL.

    Events emitted:
    - strategy=semantic_{type}: Type of semantic error generated

    Combined strategy for resolver error handling testing.
    """
    # Choose semantic error type explicitly to emit event
    semantic_type = draw(
        st.sampled_from([
            "undefined_ref",
            "undefined_var",
            "arity_mismatch",
            "missing_variant",
            "circular",
        ])
    )

    # Emit event for HypoFuzz coverage guidance
    event(f"strategy=semantic_{semantic_type}")

    match semantic_type:
        case "undefined_ref":
            return draw(ftl_undefined_reference())
        case "undefined_var":
            return draw(ftl_undefined_variable())
        case "arity_mismatch":
            return draw(ftl_function_arity_mismatch())
        case "missing_variant":
            return draw(ftl_select_missing_variant())
        case _:  # circular
            return draw(ftl_circular_references())


# =============================================================================
# Invalid AST Construction Helpers (for validation testing)
# =============================================================================


def build_invalid_select_no_defaults(
    selector: VariableReference | None = None,
) -> SelectExpression:
    """Build SelectExpression with NO default variants (invalid).

    Bypasses __post_init__ validation to test serializer validation layer.
    This is defense-in-depth testing: programmatically constructed ASTs
    might bypass parser validation.

    Returns:
        SelectExpression with all variants having default=False
    """
    if selector is None:
        selector = VariableReference(id=Identifier(name="count"))

    variants = (
        Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=(TextElement(value="One"),)),
            default=False,
        ),
        Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="Other"),)),
            default=False,
        ),
    )

    # Bypass __post_init__ validation using object.__setattr__
    # This creates an invalid AST for testing serializer validation
    obj = object.__new__(SelectExpression)
    object.__setattr__(obj, "selector", selector)
    object.__setattr__(obj, "variants", variants)
    object.__setattr__(obj, "span", None)

    return obj


def build_invalid_select_multiple_defaults(
    selector: VariableReference | None = None,
) -> SelectExpression:
    """Build SelectExpression with MULTIPLE default variants (invalid).

    Bypasses __post_init__ validation to test serializer validation layer.

    Returns:
        SelectExpression with all variants having default=True
    """
    if selector is None:
        selector = VariableReference(id=Identifier(name="count"))

    variants = (
        Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=(TextElement(value="One"),)),
            default=True,
        ),
        Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="Other"),)),
            default=True,
        ),
    )

    # Bypass __post_init__ validation using object.__setattr__
    obj = object.__new__(SelectExpression)
    object.__setattr__(obj, "selector", selector)
    object.__setattr__(obj, "variants", variants)
    object.__setattr__(obj, "span", None)

    return obj
