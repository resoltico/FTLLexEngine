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
from decimal import Decimal

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import composite

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    Expression,
    FunctionReference,
    Identifier,
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


# Reserved keywords in FTL (for intensive fuzzing of keyword handling)
FTL_RESERVED_KEYWORDS = (
    "NUMBER",
    "DATETIME",
    "one",
    "other",
    "zero",
    "two",
    "few",
    "many",
)


@composite
def ftl_identifiers_with_keywords(draw: st.DrawFn) -> str:
    """Generate FTL identifiers, sometimes using reserved keywords.

    Used for intensive fuzzing to test keyword handling paths.
    50% chance of returning a reserved keyword, otherwise a random identifier.
    """
    if draw(st.booleans()):
        return draw(st.sampled_from(FTL_RESERVED_KEYWORDS))

    first = draw(st.sampled_from(FTL_IDENTIFIER_FIRST_CHARS))
    rest = draw(
        st.text(
            alphabet=FTL_IDENTIFIER_REST_CHARS,
            max_size=64,
        )
    )
    return first + rest


@composite
def ftl_identifier_boundary(draw: st.DrawFn) -> str:
    """Generate boundary-case identifiers for edge testing.

    Tests single-char, long identifiers, and repeated separators.
    """
    choice = draw(st.sampled_from(["single", "long", "hyphen", "underscore"]))
    if choice == "single":
        return draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
    if choice == "long":
        # Maximum practical length
        return "a" + draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=200,
                max_size=200,
            )
        )
    if choice == "hyphen":
        return "a" + "-" * draw(st.integers(1, 10)) + "b"
    # underscore
    return "a" + "_" * draw(st.integers(1, 10)) + "b"


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
    """Generate text with comprehensive Unicode coverage.

    Uses Hypothesis's full Unicode text strategy, filtering only:
    - FTL structural characters: { } [ ] * $ - . #
    - Control characters (Cc category)
    - Newlines (message separators)
    - Surrogates (Cs category)

    This provides much broader Unicode coverage than the limited UNICODE_CHARS
    constant, including non-BMP characters, ZWJ sequences, RTL text, etc.
    (MAINT-FUZZ-UNICODE-UNDEREXPOSURE-001)
    """
    # Full Unicode text with FTL structural chars filtered
    text = draw(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # No control chars or surrogates
                blacklist_characters="{}[]*$-.#\n\r",  # No FTL structural chars
            ),
            min_size=1,
            max_size=30,
        )
    )
    # Ensure non-whitespace content
    if text.strip() == "":
        text = draw(st.sampled_from(list(UNICODE_CHARS)))
    return text


@composite
def ftl_unicode_stress_text(draw: st.DrawFn) -> str:
    """Generate Unicode stress test cases.

    Events emitted:
    - unicode={category}: Unicode stress category (emoji, rtl, combining, etc.)

    Specifically targets edge cases that may cause encoding or display issues:
    - Non-BMP characters (emoji, math symbols)
    - ZWJ sequences
    - RTL markers and bidirectional text
    - Combining characters
    - Rare scripts
    """
    # Stress cases with categories for event emission
    stress_cases = [
        ("\U0001F600", "emoji"),  # Emoji (non-BMP)
        ("\U0001F469\u200D\U0001F4BB", "zwj"),  # ZWJ sequence (woman technologist)
        ("\u202Eevil\u202C", "rtl"),  # RTL override
        ("cafe\u0301", "combining"),  # Combining accent (e as e + combining acute)
        ("\u0627\u0644\u0639\u0631\u0628\u064A\u0629", "arabic"),  # Arabic
        ("\u4E2D\u6587", "cjk"),  # Chinese
        ("\u0928\u092E\u0938\u094D\u0924\u0947", "devanagari"),  # Hindi (Devanagari)
        ("\uFEFF", "bom"),  # BOM
        ("\u200B", "zero_width"),  # Zero-width space
        ("\u00A0", "nbsp"),  # Non-breaking space
        ("\U0001F1FA\U0001F1F8", "flag"),  # Flag emoji (regional indicators)
    ]
    text, category = draw(st.sampled_from(stress_cases))

    # Emit event for HypoFuzz coverage guidance
    event(f"unicode={category}")

    return text


# =============================================================================
# Chaos Mode Strategies (parser stress testing)
# =============================================================================


@composite
def ftl_chaos_text(draw: st.DrawFn) -> str:
    """Generate text WITH FTL structural characters for parser stress testing.

    Unlike ftl_unicode_text() which filters out {}[]*$-.#, this strategy
    INCLUDES these characters to test parser error recovery, escape handling,
    and edge cases where FTL syntax appears in unexpected places.

    WARNING: This generates potentially invalid FTL. Use for:
    - Parser error recovery testing
    - Junk node generation testing
    - Fuzzing edge cases

    Do NOT use for roundtrip testing where valid FTL is required.
    """
    # Include FTL structural characters
    text = draw(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),  # No control chars or surrogates
                blacklist_characters="\n\r",  # Only filter newlines (entry separators)
            ),
            min_size=1,
            max_size=50,
        )
    )
    # Ensure non-whitespace content
    if text.strip() == "":
        text = draw(st.sampled_from(["text", "value", "test"]))
    return text


@composite
def ftl_chaos_source(draw: st.DrawFn) -> str:
    """Generate raw FTL source with chaos text for intensive parser fuzzing.

    Creates FTL-like structures with potentially invalid content to stress
    test parser error handling and recovery mechanisms.

    Events emitted:
    - strategy=chaos_{pattern}: Chaos injection pattern used (for HypoFuzz guidance)

    Generates variations like:
    - msg = { unterminated
    - msg = value { $var } more { unclosed
    - msg = [ bracket ] confusion
    """
    msg_id = draw(ftl_identifiers())
    chaos = draw(ftl_chaos_text())

    # Choose chaos injection pattern
    pattern = draw(
        st.sampled_from([
            "plain",  # msg = <chaos>
            "prefix_brace",  # msg = { <chaos>
            "suffix_brace",  # msg = <chaos> }
            "embedded_dollar",  # msg = text $<chaos> more
            "bracket_noise",  # msg = [ <chaos> ]
            "mixed",  # msg = { $x } <chaos> { more
        ])
    )

    # Emit event for HypoFuzz coverage guidance
    event(f"strategy=chaos_{pattern}")

    match pattern:
        case "plain":
            return f"{msg_id} = {chaos}"
        case "prefix_brace":
            return f"{msg_id} = {{ {chaos}"
        case "suffix_brace":
            return f"{msg_id} = {chaos} }}"
        case "embedded_dollar":
            prefix = draw(ftl_simple_text())
            return f"{msg_id} = {prefix} ${chaos}"
        case "bracket_noise":
            return f"{msg_id} = [ {chaos} ]"
        case _:  # mixed
            var = draw(ftl_identifiers())
            return f"{msg_id} = {{ ${var} }} {chaos} {{ more"


@composite
def ftl_pathological_nesting(draw: st.DrawFn) -> str:
    """Generate pathologically nested FTL for parser depth limit testing.

    Creates deeply nested structures that approach or exceed MAX_DEPTH:
    - Nested placeables: { { { { $x } } } }
    - Nested selects: { $a -> [x] { $b -> [y] value } }

    Events emitted:
    - boundary={under|at|over}_max_depth: Depth boundary condition (for HypoFuzz)

    Used for testing:
    - Parser depth guards
    - Stack overflow prevention
    - Error recovery at depth limits
    """
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415

    msg_id = draw(ftl_identifiers())

    # Choose between boundary, at-limit, and over-limit with labels
    depth_choice = draw(
        st.sampled_from([
            (MAX_DEPTH - 5, "under"),  # Safely within limits
            (MAX_DEPTH - 1, "under"),  # Just under limit
            (MAX_DEPTH, "at"),  # At limit
            (MAX_DEPTH + 1, "over"),  # Just over limit
            (MAX_DEPTH + 10, "over"),  # Well over limit
        ])
    )
    depth, boundary_label = depth_choice

    # Emit boundary event for HypoFuzz coverage guidance
    event(f"boundary={boundary_label}_max_depth")
    event(f"depth={depth}")

    # Generate nested braces
    open_braces = "{ " * depth
    close_braces = " }" * depth
    inner_var = draw(ftl_identifiers())

    return f"{msg_id} = {open_braces}${inner_var}{close_braces}"


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
    """Generate valid FTL numbers.

    FTL number literals support format: -?[0-9]+(.[0-9]+)?
    No scientific notation. Subnormal floats are excluded because
    their string representation uses scientific notation (e.g., 1e-308).
    """
    return draw(
        st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.floats(
                min_value=-1000000.0,
                max_value=1000000.0,
                allow_nan=False,
                allow_infinity=False,
                allow_subnormal=False,
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
    """Generate NumberLiteral AST nodes with valid FTL raw format.

    FTL number syntax: -?[0-9]+(.[0-9]+)?
    No scientific notation allowed. Uses fixed-point notation for Decimals.
    """
    value = draw(ftl_numbers())
    # Convert float to Decimal for decimal numbers (financial-grade precision)
    typed_value = Decimal(str(value)) if isinstance(value, float) else value

    # Ensure raw string uses fixed-point notation (no scientific notation)
    # str(Decimal) may use 'E' notation for very small/large values
    raw = format(typed_value, "f") if isinstance(typed_value, Decimal) else str(typed_value)

    return NumberLiteral(value=typed_value, raw=raw)


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
    # Value must be an InlineExpression - use simple types to avoid recursion
    value = draw(
        st.one_of(
            ftl_string_literals(),
            ftl_number_literals(),
            ftl_variable_references(),
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
    """
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
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415

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
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415

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

    Events emitted:
    - strategy=select_variants_{n}: Number of variants generated

    Ensures:
    - Exactly one default variant (per Fluent spec)
    - Unique variant keys (per Fluent spec)
    """
    selector = draw(ftl_variable_references())

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


# =============================================================================
# Whitespace Edge Case Strategies (for fuzzing whitespace handling bugs)
# =============================================================================


# Line ending variations for mixed line ending tests
_LINE_ENDINGS: tuple[str, ...] = ("\n", "\r\n", "\r")


@composite
def blank_line(draw: st.DrawFn) -> str:
    """Generate a blank line containing only spaces.

    Tests blank line handling in patterns and between entries.
    Per FTL spec, blank lines may contain spaces but no other content.
    """
    space_count = draw(st.integers(min_value=0, max_value=8))
    return " " * space_count


@composite
def blank_lines_sequence(draw: st.DrawFn) -> str:
    """Generate a sequence of blank lines with varying whitespace.

    Tests handling of multiple consecutive blank lines, which affects:
    - Comment separation logic
    - Pattern indentation calculation
    - Entry boundary detection
    """
    line_count = draw(st.integers(min_value=1, max_value=5))
    lines: list[str] = []
    for _ in range(line_count):
        spaces = draw(st.integers(min_value=0, max_value=4))
        lines.append(" " * spaces)
    return "\n".join(lines)


@composite
def text_with_trailing_whitespace(draw: st.DrawFn) -> str:
    """Generate text with trailing whitespace (spaces or tabs).

    Tests trailing whitespace handling which can affect:
    - Pattern value boundaries
    - Serializer output normalization
    - Roundtrip consistency
    """
    base_text = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=30))
    # Ensure base has content
    if base_text.strip() == "":
        base_text = draw(st.sampled_from(string.ascii_letters))

    trailing_type = draw(st.sampled_from(["spaces", "tabs", "mixed"]))
    count = draw(st.integers(min_value=1, max_value=4))

    match trailing_type:
        case "spaces":
            trailing = " " * count
        case "tabs":
            trailing = "\t" * count
        case _:  # mixed
            trailing = " \t" * count

    return base_text + trailing


@composite
def text_with_tabs(draw: st.DrawFn) -> str:
    """Generate text containing tab characters.

    Per FTL spec, tabs are NOT valid whitespace and should create Junk
    when appearing in syntactic positions (e.g., indentation, between
    identifier and equals sign). This strategy generates text with
    embedded tabs for rejection testing.
    """
    prefix = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=15))
    if prefix.strip() == "":
        prefix = draw(st.sampled_from(string.ascii_letters))

    tab_position = draw(st.sampled_from(["middle", "start", "end"]))

    match tab_position:
        case "middle":
            suffix = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=15))
            if suffix.strip() == "":
                suffix = draw(st.sampled_from(string.ascii_letters))
            return prefix + "\t" + suffix
        case "start":
            return "\t" + prefix
        case _:  # end
            return prefix + "\t"


@composite
def mixed_line_endings_text(draw: st.DrawFn) -> str:
    """Generate multi-line text with mixed line endings.

    Tests CRLF normalization handling:
    - Unix (LF): \\n
    - Windows (CRLF): \\r\\n
    - Legacy Mac (CR): \\r

    Mixed line endings in the same file is a real-world scenario
    that can occur from cross-platform editing.
    """
    line_count = draw(st.integers(min_value=2, max_value=5))
    lines: list[str] = []

    for _ in range(line_count):
        # Generate line content
        line = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=20))
        if line.strip() == "":
            line = draw(st.sampled_from(string.ascii_letters))
        lines.append(line)

    # Join with random line endings
    result_parts: list[str] = []
    for i, line in enumerate(lines):
        result_parts.append(line)
        if i < len(lines) - 1:
            ending = draw(st.sampled_from(_LINE_ENDINGS))
            result_parts.append(ending)

    return "".join(result_parts)


@composite
def variant_key_with_whitespace(draw: st.DrawFn) -> str:
    """Generate variant key with whitespace inside brackets.

    Tests FTL-GRAMMAR-003 and SPEC-VARIANT-WHITESPACE-001:
    - Spaces after opening bracket: [ one]
    - Spaces before closing bracket: [one ]
    - Newlines inside variant key: [ \\n one \\n ]
    """
    key = draw(ftl_identifiers())

    whitespace_type = draw(
        st.sampled_from(["leading", "trailing", "both", "newlines", "mixed"])
    )

    match whitespace_type:
        case "leading":
            spaces = " " * draw(st.integers(min_value=1, max_value=3))
            return f"[{spaces}{key}]"
        case "trailing":
            spaces = " " * draw(st.integers(min_value=1, max_value=3))
            return f"[{key}{spaces}]"
        case "both":
            leading = " " * draw(st.integers(min_value=1, max_value=2))
            trailing = " " * draw(st.integers(min_value=1, max_value=2))
            return f"[{leading}{key}{trailing}]"
        case "newlines":
            return f"[ \n {key} \n ]"
        case _:  # mixed
            return f"[ \n{key} ]"


@composite
def placeable_with_whitespace(draw: st.DrawFn) -> str:
    """Generate placeable expression with whitespace around braces.

    Tests FTL-STRICT-WHITESPACE-001:
    - Newlines after opening brace: { \\n $var }
    - Newlines before closing brace: { $var \\n }
    - Mixed whitespace around placeables
    """
    var_name = draw(ftl_identifiers())

    whitespace_type = draw(st.sampled_from(["after_open", "before_close", "both"]))

    match whitespace_type:
        case "after_open":
            return f"{{ \n ${var_name} }}"
        case "before_close":
            return f"{{ ${var_name} \n }}"
        case _:  # both
            return f"{{ \n ${var_name} \n }}"


@composite
def variable_indent_multiline_pattern(draw: st.DrawFn) -> str:
    """Generate multiline pattern with DIFFERENT indentation per line.

    Tests common_indent calculation in parse_pattern():
    - Each continuation line has independent indentation
    - Common indent should be minimum of all non-blank lines
    - Blank lines (spaces only) should be skipped in indent calculation

    Addresses FTL-GRAMMAR-001: Blank lines before first content.
    """
    line_count = draw(st.integers(min_value=2, max_value=5))
    lines: list[str] = []

    for _ in range(line_count):
        indent = " " * draw(st.integers(min_value=1, max_value=8))
        content = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=20))
        if content.strip() == "":
            content = draw(st.sampled_from(string.ascii_letters))
        lines.append(indent + content)

    return "\n".join(lines)


@composite
def pattern_with_leading_blank_lines(draw: st.DrawFn) -> str:
    """Generate pattern with blank lines before first content line.

    Tests FTL-GRAMMAR-001: Parser must skip blank lines before
    measuring common_indent in multiline patterns.

    Example: msg =\\n\\n    value
    Should produce "value", not "    value".
    """
    blank_count = draw(st.integers(min_value=1, max_value=3))
    indent = " " * draw(st.integers(min_value=1, max_value=8))
    content = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=20))
    if content.strip() == "":
        content = draw(st.sampled_from(string.ascii_letters))

    blank_lines = "\n" * blank_count
    return f"{blank_lines}{indent}{content}"


@composite
def ftl_message_with_whitespace_edge_cases(draw: st.DrawFn) -> str:
    """Generate FTL message exercising whitespace edge cases.

    Combines multiple whitespace edge cases into complete messages
    for comprehensive fuzzing of whitespace handling.
    """
    msg_id = draw(ftl_identifiers())

    case_type = draw(
        st.sampled_from([
            "trailing_ws",
            "multiline_varied_indent",
            "leading_blanks",
            "placeable_ws",
        ])
    )

    match case_type:
        case "trailing_ws":
            value = draw(text_with_trailing_whitespace())
            return f"{msg_id} = {value}"
        case "multiline_varied_indent":
            pattern = draw(variable_indent_multiline_pattern())
            return f"{msg_id} =\n{pattern}"
        case "leading_blanks":
            pattern = draw(pattern_with_leading_blank_lines())
            return f"{msg_id} ={pattern}"
        case _:  # placeable_ws
            placeable = draw(placeable_with_whitespace())
            return f"{msg_id} = Hello {placeable} World"


@composite
def ftl_select_with_whitespace_variants(draw: st.DrawFn) -> str:
    """Generate select expression with whitespace edge cases in variants.

    Tests variant key whitespace handling and variant value patterns
    with whitespace edge cases.
    """
    msg_id = draw(ftl_identifiers())
    selector_var = draw(ftl_identifiers())

    num_variants = draw(st.integers(min_value=2, max_value=4))
    default_idx = draw(st.integers(min_value=0, max_value=num_variants - 1))

    variant_keys = ["one", "two", "few", "many", "other", "zero"]
    used_keys = draw(
        st.lists(
            st.sampled_from(variant_keys),
            min_size=num_variants,
            max_size=num_variants,
            unique=True,
        )
    )

    variants: list[str] = []
    for i, key in enumerate(used_keys):
        prefix = "*" if i == default_idx else " "

        # Randomly add whitespace to variant key
        if draw(st.booleans()):
            key_str = draw(variant_key_with_whitespace())
            # Replace the generated key with our unique key
            key_str = key_str.replace(key_str[1:-1].strip(), key)
        else:
            key_str = f"[{key}]"

        value = draw(st.text(alphabet=FTL_SAFE_CHARS, min_size=1, max_size=15))
        if value.strip() == "":
            value = "value"
        variants.append(f"{prefix}{key_str} {value}")

    variants_str = "\n    ".join(variants)
    return f"{msg_id} = {{ ${selector_var} ->\n    {variants_str}\n}}"


def _generate_unique_id(draw: st.DrawFn, seen_ids: set[str]) -> str:
    """Generate a unique FTL identifier not already in seen_ids."""
    msg_id = draw(ftl_identifiers())
    while msg_id in seen_ids:
        msg_id = draw(ftl_identifiers())
    seen_ids.add(msg_id)
    return msg_id


def _generate_whitespace_message_entry(draw: st.DrawFn, msg_id: str) -> str:
    """Generate a message entry with whitespace edge cases."""
    ws_case = draw(st.sampled_from(["trailing", "multiline", "leading_blank"]))
    match ws_case:
        case "trailing":
            value = draw(text_with_trailing_whitespace())
            return f"{msg_id} = {value}"
        case "multiline":
            pattern = draw(variable_indent_multiline_pattern())
            return f"{msg_id} =\n{pattern}"
        case _:
            pattern = draw(pattern_with_leading_blank_lines())
            return f"{msg_id} ={pattern}"


@composite
def ftl_resource_with_whitespace_chaos(draw: st.DrawFn) -> str:
    """Generate FTL resource with mixed whitespace edge cases.

    Events emitted:
    - strategy=ws_chaos_entry_{type}: Entry type in whitespace chaos resource

    Combines multiple entry types with various whitespace edge cases
    for comprehensive cross-contamination testing.
    """
    num_entries = draw(st.integers(min_value=2, max_value=8))
    entries: list[str] = []
    seen_ids: set[str] = set()

    # Track entry types for event emission
    entry_types_used: list[str] = []

    for _ in range(num_entries):
        entry_type = draw(
            st.sampled_from([
                "simple",
                "whitespace_message",
                "select_whitespace",
                "term",
                "comment",
                "blank_lines",
            ])
        )
        entry_types_used.append(entry_type)

        match entry_type:
            case "simple":
                msg_id = _generate_unique_id(draw, seen_ids)
                value = draw(ftl_simple_text())
                entries.append(f"{msg_id} = {value}")

            case "whitespace_message":
                msg_id = _generate_unique_id(draw, seen_ids)
                entries.append(_generate_whitespace_message_entry(draw, msg_id))

            case "select_whitespace":
                entry = draw(ftl_select_with_whitespace_variants())
                entry_id = entry.split(" = ")[0]
                if entry_id not in seen_ids:
                    seen_ids.add(entry_id)
                    entries.append(entry)

            case "term":
                term_id = draw(ftl_identifiers())
                value = draw(ftl_simple_text())
                entries.append(f"-{term_id} = {value}")

            case "comment":
                level = draw(st.sampled_from(["#", "##", "###"]))
                content = draw(ftl_simple_text())
                entries.append(f"{level} {content}")

            case _:  # blank_lines
                blanks = draw(blank_lines_sequence())
                entries.append(blanks)

    # Emit events for entry type diversity
    for et in set(entry_types_used):
        event(f"strategy=ws_chaos_entry_{et}")

    return "\n\n".join(entries)


# =============================================================================
# Negative Oracle Strategies (intentionally invalid FTL)
# =============================================================================
# (MAINT-FUZZ-NEGATIVE-ORACLE-MISSING-001)


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
    id_a = draw(ftl_identifiers())
    id_b = draw(ftl_identifiers())

    # Ensure distinct IDs
    while id_b == id_a:
        id_b = draw(ftl_identifiers())

    return f"{id_a} = {{ {id_b} }}\n{id_b} = {{ {id_a} }}"


@composite
def ftl_circular_message_3way(draw: st.DrawFn) -> str:
    """Generate 3-message circular reference: A -> B -> C -> A.

    Tests transitive cycle detection in resolver.
    """
    id_a = draw(ftl_identifiers())
    id_b = draw(ftl_identifiers())
    id_c = draw(ftl_identifiers())

    # Ensure distinct IDs
    ids = {id_a}
    while id_b in ids:
        id_b = draw(ftl_identifiers())
    ids.add(id_b)
    while id_c in ids:
        id_c = draw(ftl_identifiers())

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
    id_a = draw(ftl_identifiers())
    id_b = draw(ftl_identifiers())

    while id_b == id_a:
        id_b = draw(ftl_identifiers())

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
    id_a = draw(ftl_identifiers())
    id_b = draw(ftl_identifiers())
    attr = draw(ftl_identifiers())

    while id_b == id_a:
        id_b = draw(ftl_identifiers())

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
    msg_id = draw(ftl_identifiers())
    undefined_id = draw(ftl_identifiers())

    # Ensure the undefined ID is different from the message ID
    while undefined_id == msg_id:
        undefined_id = draw(ftl_identifiers())

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
