from tests.strategies.ftl_shared import (
    FTL_IDENTIFIER_FIRST_CHARS,
    FTL_IDENTIFIER_REST_CHARS,
    FTL_SAFE_CHARS,
    IDENTIFIER_PARTS,
    UNICODE_CHARS,
    Decimal,
    FluentNumber,
    composite,
    event,
    st,
    string,
)


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
    from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415 - import inside function

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
def ftl_multiline_chaos_source(draw: st.DrawFn) -> str:
    """Generate multi-entry chaos FTL with line breaks at invalid positions.

    Events emitted:
    - strategy=multiline_chaos_{pattern}: Chaos injection pattern (for HypoFuzz)

    D7 fix: Tests parser error recovery for multiline malformed input.
    Real-world malformed FTL often involves:
    - Continuation lines without proper indentation
    - Entries split across unexpected boundaries
    - CRLF mid-token
    - Unclosed structures spanning multiple lines
    """
    num_entries = draw(st.integers(min_value=2, max_value=4))
    entries: list[str] = []

    pattern = draw(
        st.sampled_from([
            "mid_identifier",  # Line break inside identifier
            "mid_placeable",  # Line break inside placeable
            "between_eq_value",  # Line break between = and value
            "unclosed_multiline",  # Unclosed brace spanning lines
            "bad_continuation",  # Bad indentation on continuation
        ])
    )
    event(f"strategy=multiline_chaos_{pattern}")

    for i in range(num_entries):
        msg_id = f"msg{i}"
        match pattern:
            case "mid_identifier":
                # Break identifier across lines (invalid)
                entries.append(f"ms\ng{i} = value{i}")
            case "mid_placeable":
                # Break placeable across lines
                entries.append(f"{msg_id} = text {{ $va\nr{i} }} more")
            case "between_eq_value":
                # Line break between = and value
                entries.append(f"{msg_id} =\nvalue{i}")
            case "unclosed_multiline":
                # Unclosed brace spanning to next entry
                if i < num_entries - 1:
                    entries.append(f"{msg_id} = {{ $var{i}")
                else:
                    entries.append(f"{msg_id} = closed }}")
            case _:  # bad_continuation
                # Tab indentation (invalid per FTL spec)
                entries.append(f"{msg_id} = first line\n\tcontinuation")

    return "\n".join(entries)


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
def ftl_numbers(draw: st.DrawFn) -> int | Decimal:
    """Generate valid FTL numbers.

    FTL number literals support format: -?[0-9]+(.[0-9]+)?
    No scientific notation. Subnormal values are excluded because
    their string representation uses scientific notation (e.g., 1e-308).
    """
    return draw(
        st.one_of(
            st.integers(min_value=-1000000, max_value=1000000),
            st.decimals(
                min_value=Decimal(-1000000),
                max_value=Decimal(1000000),
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )


@composite
def ftl_financial_numbers(draw: st.DrawFn) -> Decimal:
    """Generate financial-scale numbers for financial application testing.

    Events emitted:
    - strategy=financial_{magnitude}: Number magnitude category (for HypoFuzz)
    - strategy=financial_decimals_{n}: Decimal places (for ISO 4217 coverage)

    Financial applications handle amounts in billions (GDP, fund values,
    transaction volumes). This strategy generates numbers across the full range
    needed for financial formatting tests.

    Magnitude ranges:
    - small: < 1,000 (retail transactions)
    - medium: 1,000 - 1,000,000 (business transactions)
    - large: 1M - 1B (enterprise, fund values)
    - huge: > 1B (national accounts, GDP)

    Decimal places aligned with ISO 4217:
    - 0 decimals: JPY, KRW, VND
    - 2 decimals: USD, EUR, GBP (standard)
    - 3 decimals: KWD, BHD, OMR
    - 4 decimals: CLF, UYW (accounting units)
    """
    magnitude = draw(st.sampled_from(["small", "medium", "large", "huge"]))
    decimals = draw(st.sampled_from([0, 2, 3, 4]))

    match magnitude:
        case "small":
            base = draw(st.integers(min_value=-999, max_value=999))
        case "medium":
            base = draw(st.integers(min_value=-999999, max_value=999999))
        case "large":
            base = draw(st.integers(min_value=-999999999, max_value=999999999))
        case _:  # huge
            base = draw(st.integers(min_value=-999999999999, max_value=999999999999))

    event(f"strategy=financial_{magnitude}")
    event(f"strategy=financial_decimals_{decimals}")

    if decimals == 0:
        return Decimal(base)

    # Add decimal component based on ISO 4217 decimal places using exact arithmetic.
    divisor = 10 ** decimals
    fraction = draw(st.integers(min_value=0, max_value=divisor - 1))
    return Decimal(base) + Decimal(fraction) / Decimal(divisor)


# =============================================================================
# Identifier Case Strategies (for function bridge testing)
# =============================================================================


@composite
def snake_case_identifiers(draw: st.DrawFn) -> str:
    """Generate snake_case identifiers.

    Events emitted:
    - bridge_id_parts={n}: Number of identifier parts
    """
    parts = draw(st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3))
    event(f"bridge_id_parts={len(parts)}")
    return "_".join(parts)


@composite
def camel_case_identifiers(draw: st.DrawFn) -> str:
    """Generate camelCase identifiers.

    Events emitted:
    - bridge_id_parts={n}: Number of identifier parts
    """
    parts = draw(st.lists(st.sampled_from(IDENTIFIER_PARTS), min_size=1, max_size=3))
    event(f"bridge_id_parts={len(parts)}")
    if not parts:
        return "value"
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


# =============================================================================
# Function Bridge Strategies
# =============================================================================


@composite
def ftl_function_names(draw: st.DrawFn) -> str:
    """Generate valid FTL function names (UPPERCASE identifiers).

    Events emitted:
    - bridge_fname_len={n}: Length category of generated name
    """
    name = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu",),  # type: ignore[arg-type]
                min_codepoint=65,
                max_codepoint=90,
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda s: s.isidentifier())
    )
    length = "short" if len(name) <= 5 else "long"
    event(f"bridge_fname_len={length}")
    return name


@composite
def fluent_numbers(draw: st.DrawFn) -> FluentNumber:
    """Generate FluentNumber instances with diverse value/format combos.

    FluentNumber.value is int | Decimal (never float — precision requirement).

    Events emitted:
    - bridge_fnum_type={type}: Value type (int, decimal)
    - bridge_fnum_precision={n}: Precision category (none, 0, low, high)
    """
    value_type = draw(st.sampled_from(["int", "decimal"]))
    event(f"bridge_fnum_type={value_type}")

    # Draw precision category first for bucket-first uniform distribution.
    # "none" represents FluentNumber.precision=None (unspecified precision).
    prec_cat = draw(st.sampled_from(["none", "0", "low", "high"]))

    precision: int | None
    places: int
    if prec_cat == "none":
        precision = None
        places = 0
    elif prec_cat == "0":
        precision = 0
        places = 0
    elif prec_cat == "low":
        precision = draw(st.integers(min_value=1, max_value=2))
        places = precision
    else:  # high
        precision = draw(st.integers(min_value=3, max_value=6))
        places = precision

    value: int | Decimal
    int_part = draw(st.integers(min_value=-999999, max_value=999999))
    if value_type == "int":
        value = int_part
        formatted = str(value)
    elif places > 0:
        frac = draw(
            st.integers(min_value=0, max_value=10**places - 1)
        )
        frac_str = str(frac).zfill(places)
        value = Decimal(f"{int_part}.{frac_str}")
        formatted = str(value)
    else:
        value = Decimal(int_part)
        formatted = str(value)

    event(f"bridge_fnum_precision={prec_cat}")

    return FluentNumber(
        value=value, formatted=formatted, precision=precision
    )
