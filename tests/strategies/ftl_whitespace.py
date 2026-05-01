from tests.strategies.ftl_shared import FTL_SAFE_CHARS, composite, event, st, string
from tests.strategies.ftl_strings import ftl_identifiers, ftl_simple_text

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
