"""Grammar rules for Fluent FTL parser.

This module provides all parsing rules for FTL grammar constructs:
- Pattern parsing (variable references, text elements, placeables)
- Expression parsing (inline expressions, select expressions, function calls)
- Entry parsing (messages, terms, attributes, comments)

All grammar rules are co-located in a single module to:
1. Eliminate circular imports between interdependent parsing functions
2. Simplify the import graph
3. Allow direct function calls instead of function-local imports

Lookahead Patterns:
    The parser uses character-based lookahead for disambiguation:
    - `{` starts a Placeable
    - `$` starts a VariableReference
    - `-` followed by identifier starts a TermReference
    - `.` in specific contexts starts an attribute access
    - `*[` marks the default variant in SelectExpression

    These single-character or two-character lookaheads are implemented inline
    using cursor.peek(n) rather than separate Lookahead helper classes. While
    this creates some code duplication, it keeps the parsing logic explicit
    and easy to trace. Future refactoring could extract common patterns into
    a Lookahead utility class if the grammar expands significantly.

Security:
    Includes configurable nesting depth limit to prevent DoS attacks via
    deeply nested placeables (e.g., { { { { ... } } } }).
"""

from dataclasses import dataclass

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    InlineExpression,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    Span,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.cursor import Cursor, ParseResult
from ftllexengine.syntax.parser.primitives import (
    _ASCII_DIGITS,
    is_identifier_char,
    is_identifier_start,
    parse_identifier,
    parse_number,
    parse_number_value,
    parse_string_literal,
)
from ftllexengine.syntax.parser.whitespace import (
    is_indented_continuation,
    skip_blank,
    skip_blank_inline,
    skip_multiline_pattern_start,
)

__all__ = ["ParseContext", "parse_comment", "parse_message", "parse_term"]


@dataclass(slots=True)
class ParseContext:
    """Explicit context for parsing operations.

    Replaces thread-local state with explicit parameter passing for:
    - Thread safety without global state
    - Async framework compatibility
    - Easier testing (no state reset needed)
    - Clear dependency flow

    Attributes:
        max_nesting_depth: Maximum allowed nesting depth for placeables
        current_depth: Current nesting depth (0 = top level)
    """

    max_nesting_depth: int = MAX_DEPTH
    current_depth: int = 0

    def is_depth_exceeded(self) -> bool:
        """Check if maximum nesting depth has been exceeded."""
        return self.current_depth >= self.max_nesting_depth

    def enter_placeable(self) -> "ParseContext":
        """Create new context with incremented depth for entering a placeable."""
        return ParseContext(
            max_nesting_depth=self.max_nesting_depth,
            current_depth=self.current_depth + 1,
        )


# =============================================================================
# Pattern Parsing
# =============================================================================


def parse_variable_reference(cursor: Cursor) -> ParseResult[VariableReference] | None:
    """Parse variable reference: $variable

    Variables start with $ followed by an identifier.

    Examples:
        $name -> VariableReference(Identifier("name"))
        $count -> VariableReference(Identifier("count"))

    Args:
        cursor: Current position in source

    Returns:
        Success(ParseResult(VariableReference, new_cursor)) on success
        Failure(ParseError(...)) if not a variable reference
    """
    # Expect $
    if cursor.is_eof or cursor.current != "$":
        return None  # "Expected variable reference (starts with $)", cursor, expected=["$"]

    cursor = cursor.advance()  # Skip $

    # Parse identifier
    result = parse_identifier(cursor)
    if result is None:
        return result

    parse_result = result
    var_ref = VariableReference(id=Identifier(parse_result.value))
    return ParseResult(var_ref, parse_result.cursor)


def _is_valid_variant_key_char(ch: str, is_first: bool) -> bool:
    """Check if character is valid in a variant key (identifier or number).

    Variant keys are either identifiers or number literals:
    - Identifiers: [a-zA-Z_][a-zA-Z0-9_-]*
    - Numbers: [0-9]+ or [0-9]+.[0-9]+

    Note:
        This helper permits '.' for number literals (e.g., "1.5") but identifiers
        cannot contain '.'. The caller (_is_variant_marker) uses this for lookahead
        scanning, not strict grammar validation. A key like "foo.bar" would pass
        this check but fail later grammar validation as an invalid identifier.

    Args:
        ch: Character to check
        is_first: True if this is the first character

    Returns:
        True if character is valid for variant key content
    """
    if is_first:
        # First char: ASCII letter (for identifiers), underscore, or digit (for numbers)
        # Note: Uses ASCII-only check per Fluent spec for cross-implementation compatibility
        return is_identifier_start(ch) or ch == "_" or ch in _ASCII_DIGITS
    # Subsequent chars: ASCII alphanumeric, underscore, hyphen, or dot (for decimals)
    # Note: '.' is only valid in number literals, not identifiers
    return is_identifier_char(ch) or ch == "."


def _is_variant_marker(cursor: Cursor) -> bool:
    """Check if cursor is at a variant marker using bounded lookahead.

    Distinguishes actual variant syntax from literal text:
    - '*' is a variant marker only if followed by '['
    - '[' is a variant marker only if:
      1. Content is valid identifier/number
      2. Ends with ']'
      3. After ']', no non-whitespace text before newline/variant/end

    Valid variant keys (stop parsing):
    - [one] (followed by newline, }, or another variant)
    - *[other] (default variant)

    NOT variant keys (literal text):
    - [1, 2, 3] - contains comma and spaces
    - [INFO] message - has text after ] on same line
    - [matrix * vector] - contains spaces and operators

    Security:
        Uses bounded lookahead (max 128 chars) to prevent O(N^2) parsing
        on adversarial input like `[[[[...` with many unclosed brackets.
        Variant keys are identifiers/numbers which are always short.

    Args:
        cursor: Current position in source

    Returns:
        True if at variant marker syntax, False if literal text

    Note:
        PLR0911 waiver: Multiple returns are intentional for early-exit
        pattern matching, which is clearer than nested conditionals.
    """
    # Maximum lookahead distance - variant keys are short (identifiers/numbers)
    # This prevents O(N^2) worst-case on adversarial input like [[[[...
    max_lookahead = 128

    if cursor.is_eof:
        return False

    ch = cursor.current

    if ch == "*":
        # '*' is variant marker only if followed by '['
        next_cursor = cursor.advance()
        return not next_cursor.is_eof and next_cursor.current == "["

    if ch == "[":
        # '[' is variant marker only if:
        # 1. Content is valid identifier or number (no spaces, commas, etc.)
        # 2. Ends with ']'
        # 3. After ']', the next thing is whitespace leading to newline, }, [, or *[
        scan = cursor.advance()
        is_first = True
        has_content = False
        lookahead_count = 0

        # Find the closing ] with bounded lookahead
        while not scan.is_eof and lookahead_count < max_lookahead:
            c = scan.current
            lookahead_count += 1

            if c == "]":
                # Found closing bracket - now check what follows
                if not has_content:
                    return False  # Empty [] is not a variant key

                # Check what comes after ]
                after_bracket = scan.advance()

                # Skip whitespace on same line (also bounded)
                ws_count = 0
                while (
                    not after_bracket.is_eof
                    and after_bracket.current in (" ", "\t")
                    and ws_count < max_lookahead
                ):
                    after_bracket = after_bracket.advance()
                    ws_count += 1

                if after_bracket.is_eof:
                    return True  # EOF after ] - valid variant

                # Valid if followed by: newline, }, [, or * (for *[other])
                # Note: Line endings are normalized to LF at parser entry.
                return after_bracket.current in ("\n", "}", "[", "*")

            if c in ("\n", "{", "}", " ", "\t", ",", ":", ";", "=", "+", "*", "/"):
                # Invalid char for variant key - this is literal text
                return False
            if not _is_valid_variant_key_char(c, is_first):
                # Character not valid for identifier/number
                return False
            has_content = True
            is_first = False
            scan = scan.advance()

        # Exceeded lookahead or EOF before ']' - treat as literal text
        return False

    return False


def _trim_pattern_blank_lines(
    elements: list[TextElement | Placeable],
) -> tuple[TextElement | Placeable, ...]:
    """Trim leading and trailing blank lines from pattern elements.

    Per Fluent spec, patterns should not include leading or trailing blank lines.
    A blank line is defined as a line containing only whitespace.

    This function:
    1. Strips leading whitespace/blank lines from the first TextElement
    2. Strips trailing blank lines from the last TextElement (but preserves
       trailing whitespace on content lines - only removes after last newline)
    3. Removes empty TextElements resulting from stripping

    Args:
        elements: List of pattern elements (TextElement or Placeable)

    Returns:
        Tuple of trimmed pattern elements
    """
    if not elements:
        return ()

    result = list(elements)

    # Trim leading whitespace from first element if it's a TextElement
    while result and isinstance(result[0], TextElement):
        first = result[0]
        stripped = first.value.lstrip()
        if stripped:
            # Keep non-empty content
            result[0] = TextElement(value=stripped)
            break
        # Element was all whitespace - remove it
        result.pop(0)

    # Trim trailing BLANK LINES from last element if it's a TextElement.
    # Per Fluent spec, only trailing blank lines should be removed,
    # NOT trailing whitespace on content lines.
    # Example: "Firefox   " should preserve trailing spaces,
    # but "Firefox\n   \n" should become "Firefox".
    while result and isinstance(result[-1], TextElement):
        last = result[-1]
        text = last.value

        # Find the last newline in the text
        last_newline = text.rfind("\n")

        if last_newline == -1:
            # No newlines - this is a single-line text element.
            # Do NOT strip trailing whitespace (it's significant per Fluent spec).
            break

        # Check if everything after the last newline is whitespace (blank line)
        after_newline = text[last_newline + 1 :]
        if after_newline.strip():
            # Content after last newline - preserve it all (including trailing spaces)
            break

        # Everything after last newline is whitespace - trim this blank line
        trimmed = text[:last_newline]
        if trimmed:
            result[-1] = TextElement(value=trimmed)
            # Continue loop to check for more trailing blank lines
        else:
            # Element was all whitespace - remove it
            result.pop()

    return tuple(result)


def parse_simple_pattern(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Pattern] | None:
    """Parse simple pattern (text with optional placeables).

    Used for parsing variant value patterns within select expressions.
    Stops at variant delimiters to allow proper parsing of inline and
    multiline select expressions.

    Supports multiline continuation: variant values can span multiple lines when
    continuation lines are indented, matching the behavior of top-level patterns.

    Handles:
    - Plain text with multi-line continuation (indented lines)
    - All placeable types: {$var}, {-term}, {NUMBER(...)}, {"string"}, {42}

    Stop conditions:
    - Close brace (}): End of containing select expression
    - Open bracket ([): Start of next variant key (with lookahead)
    - Asterisk (*): Start of default variant marker (only if followed by '[')
    - Newline (\\n): End of variant value UNLESS followed by indented continuation

    Lookahead:
        '*' and '[' are only treated as variant markers when they form valid
        variant syntax. Standalone '*' or '[' without matching pattern are
        treated as literal text, enabling values like "[INFO]" or "3 * 5".

    Examples:
        "Hello"  -> Pattern([TextElement("Hello")])
        "Hi {$name}"  -> Pattern([TextElement("Hi "), Placeable(...)])
        "[INFO] msg"  -> Pattern([TextElement("[INFO] msg")])  # [ is literal
        "3 * 5"  -> Pattern([TextElement("3 * 5")])  # * is literal
        "Line 1\\n    Line 2" -> Pattern with multiline content

    Args:
        cursor: Current position in source
        context: Parse context for depth tracking

    Returns:
        ParseResult(Pattern, new_cursor) on success, None on parse error
    """
    elements: list[TextElement | Placeable] = []

    while not cursor.is_eof:
        ch = cursor.current

        # Stop condition: end of select expression
        if ch == "}":
            break

        # Check variant markers with lookahead
        # - [: start of next variant key (only if followed by text and ])
        # - *: start of default variant marker (only if followed by [)
        if ch in ("[", "*") and _is_variant_marker(cursor):
            break

        # Handle newline - check for indented continuation.
        # Note: Line endings are normalized to LF at parser entry.
        if ch == "\n":
            if is_indented_continuation(cursor):
                # Skip newline and consume indentation
                cursor = cursor.advance()
                # Skip leading spaces (continuation indent)
                cursor = cursor.skip_spaces()
                # Per Fluent spec, continuation lines are joined with newlines.
                # The newline represents the line break in the pattern value.
                if elements and not isinstance(elements[-1], Placeable):
                    # Append newline to previous text element
                    last_elem = elements[-1]
                    elements[-1] = TextElement(value=last_elem.value + "\n")
                else:
                    # Add new text element with newline
                    elements.append(TextElement(value="\n"))
                continue  # Continue parsing on next line
            break  # Not a continuation, stop parsing pattern

        # Parse placeable expression
        if ch == "{":
            cursor = cursor.advance()  # Skip {

            # Use full placeable parser which handles all expression types
            # (variables, terms, functions, strings, numbers, select expressions)
            placeable_result = parse_placeable(cursor, context)
            if placeable_result is None:
                return placeable_result

            placeable_parse = placeable_result
            cursor = placeable_parse.cursor
            elements.append(placeable_parse.value)

        else:
            # Parse text until { or stop condition
            text_start = cursor.pos
            while not cursor.is_eof:  # pragma: no branch
                ch = cursor.current
                # Stop at: placeable start, newline, closing brace
                # Note: Line endings are normalized to LF at parser entry.
                if ch in ("{", "\n", "}"):
                    break
                # Check variant markers with lookahead
                if ch in ("[", "*") and _is_variant_marker(cursor):
                    break
                cursor = cursor.advance()

            if cursor.pos > text_start:  # pragma: no branch
                # Note: This condition is always True because entering the else block
                # at line 355 means ch was not a stop character, so the inner while
                # loop at 358 will always advance at least once before breaking.
                # The False branch (cursor.pos == text_start) is structurally unreachable.
                text = Cursor(cursor.source, text_start).slice_to(cursor.pos)
                elements.append(TextElement(value=text))

    # Per Fluent spec, trim leading and trailing blank lines from patterns
    trimmed_elements = _trim_pattern_blank_lines(elements)
    pattern = Pattern(elements=trimmed_elements)
    return ParseResult(pattern, cursor)


def parse_pattern(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Pattern] | None:
    """Parse full pattern with multi-line continuation support.

    Use this for top-level message/attribute patterns. For variant patterns
    inside select expressions, use parse_simple_pattern() which has simpler
    stop conditions (no multi-line continuation).

    Handles:
    - Plain text with multi-line continuation (indented lines)
    - All placeable types: {$var}, {-term}, {NUMBER(...)}, {"string"}, {42}
    - Select expressions: {$var -> [key] value}

    Args:
        cursor: Current position in source
        context: Parse context for depth tracking

    Returns:
        ParseResult with Pattern on success, None on parse error
    """
    elements: list[TextElement | Placeable] = []

    while not cursor.is_eof:
        ch = cursor.current

        # Handle newline - check for indented continuation.
        # Note: Line endings are normalized to LF at parser entry.
        if ch == "\n":
            if is_indented_continuation(cursor):
                # Skip newline and consume indentation
                cursor = cursor.advance()
                # Skip leading spaces (continuation indent)
                cursor = cursor.skip_spaces()
                # Per Fluent spec, continuation lines are joined with newlines.
                # The newline represents the line break in the pattern value.
                if elements and not isinstance(elements[-1], Placeable):
                    # Append newline to previous text element
                    last_elem = elements[-1]
                    elements[-1] = TextElement(value=last_elem.value + "\n")
                else:
                    # Add new text element with newline
                    elements.append(TextElement(value="\n"))
                continue  # Continue parsing on next line
            break  # Not a continuation, stop parsing pattern

        # Note: '.' is removed from stop conditions here.
        # Per Fluent spec, '.' only starts an attribute when it appears at the
        # beginning of a NEW LINE (after newline + optional indentation).
        # A '.' on the same line as '=' is valid text content.
        # Attributes are detected in message/term parsing after pattern completes.

        # Placeable: {$var} or {$var -> ...}
        if ch == "{":
            cursor = cursor.advance()  # Skip {

            # Use helper method to parse placeable (reduces nesting!)
            placeable_result = parse_placeable(cursor, context)
            if placeable_result is None:
                return placeable_result

            placeable_parse = placeable_result
            elements.append(placeable_parse.value)
            cursor = placeable_parse.cursor

        else:
            # Parse text until { or stop condition
            text_start = cursor.pos
            while not cursor.is_eof:
                ch = cursor.current
                # Stop at: placeable start or newline only.
                # Note: '}', '[', '*' are valid text in top-level patterns.
                # They only have special meaning inside select expressions (handled
                # by parse_simple_pattern). An unescaped '}' is technically invalid
                # FTL syntax, but treating it as text is more robust than skipping.
                # Note: Line endings are normalized to LF at parser entry.
                if ch in ("{", "\n"):
                    break
                cursor = cursor.advance()

            if cursor.pos > text_start:  # pragma: no branch
                # Note: False branch (cursor.pos == text_start) occurs when inner loop
                # breaks immediately without consuming text. This happens when cursor
                # starts on a stop char ('{', '\n'). However, outer loop checks for '\n'
                # before text parsing, and '{' enters placeable parsing, so this condition
                # is always True when reached.
                text = Cursor(cursor.source, text_start).slice_to(cursor.pos)
                elements.append(TextElement(value=text))

    # Per Fluent spec, trim leading and trailing blank lines from patterns
    trimmed_elements = _trim_pattern_blank_lines(elements)
    pattern = Pattern(elements=trimmed_elements)
    return ParseResult(pattern, cursor)


# =============================================================================
# Expression Parsing
# =============================================================================


def parse_variant_key(cursor: Cursor) -> ParseResult[Identifier | NumberLiteral] | None:
    """Parse variant key (identifier or number).

    Helper method extracted from parse_variant to reduce complexity.

    Args:
        cursor: Current position in source

    Returns:
        Success(ParseResult(Identifier | NumberLiteral, cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Try number first (ASCII digits only, not Unicode like 2)
    if not cursor.is_eof and (cursor.current in _ASCII_DIGITS or cursor.current == "-"):
        num_result = parse_number(cursor)
        if num_result is not None:
            num_parse = num_result
            num_str = num_parse.value
            num_value = parse_number_value(num_str)
            return ParseResult(
                NumberLiteral(value=num_value, raw=num_str), num_parse.cursor
            )

        # Failed to parse as number, try identifier
        id_result = parse_identifier(cursor)
        if id_result is None:
            # Both failed - return parse error
            return None  # "Expected variant key (identifier or number)", cursor

        id_parse = id_result
        return ParseResult(Identifier(id_parse.value), id_parse.cursor)

    # Parse as identifier
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    return ParseResult(Identifier(id_parse.value), id_parse.cursor)


def parse_variant(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Variant] | None:
    """Parse variant: [key] pattern or *[key] pattern

    Variants are the cases in a select expression.

    Examples:
        [zero] no items
        *[other] many items

    Args:
        cursor: Current position in source
        context: Parse context for depth tracking

    Returns:
        Success(ParseResult(Variant, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Check for default marker *
    is_default = False
    if not cursor.is_eof and cursor.current == "*":
        is_default = True
        cursor = cursor.advance()

    # Expect [
    if cursor.is_eof or cursor.current != "[":
        return None  # "Expected '[' at start of variant", cursor

    cursor = cursor.advance()  # Skip [

    # Parse variant key (identifier or number) using extracted helper
    # Per spec: VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"
    cursor = skip_blank_inline(cursor)
    key_result = parse_variant_key(cursor)
    if key_result is None:
        return key_result

    key_parse = key_result
    variant_key = key_parse.value
    cursor = skip_blank_inline(key_parse.cursor)

    # Expect ]
    if cursor.is_eof or cursor.current != "]":
        return None  # "Expected ']' after variant key", cursor

    cursor = cursor.advance()  # Skip ]
    # After ], before pattern: blank_inline (same line) or newline+indent
    cursor = skip_blank_inline(cursor)

    # Parse pattern (on same line or next line with indent)
    # Simplified: parse until newline that's not indented
    pattern_result = parse_simple_pattern(cursor, context)
    if pattern_result is None:
        return pattern_result

    pattern_parse = pattern_result

    # Don't skip trailing whitespace - let select expression parser handle it
    variant = Variant(key=variant_key, value=pattern_parse.value, default=is_default)
    return ParseResult(variant, pattern_parse.cursor)


def parse_select_expression(
    cursor: Cursor,
    selector: InlineExpression,
    _start_pos: int,
    context: ParseContext | None = None,
) -> ParseResult[SelectExpression] | None:
    """Parse select expression after seeing selector and ->

    Format: {$var -> [key1] value1 *[key2] value2}

    The selector has already been parsed.

    Example:
        After parsing {$count and seeing ->, we parse:
        [zero] {$count} items
        [one] {$count} item
        *[other] {$count} items
        }

    Args:
        cursor: Current position (should be after ->)
        selector: The selector expression (e.g., VariableReference($count))
        _start_pos: Start position of the selector (reserved for future span tracking)
        context: Parse context for depth tracking

    Returns:
        Success(ParseResult(SelectExpression, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Per spec: SelectExpression ::= InlineExpression blank? "->" blank_inline? variant_list
    # After ->, we need blank_inline before variant list starts (could be on next line)
    # variant_list allows line_end, so use skip_blank to handle newlines
    cursor = skip_blank(cursor)

    # Parse variants
    variants: list[Variant] = []

    while not cursor.is_eof:
        # Within variant_list, allow blank (spaces and newlines)
        cursor = skip_blank(cursor)

        # Check for end of select }
        if cursor.current == "}":
            break

        # Parse variant (pass context for nested placeable depth tracking)
        variant_result = parse_variant(cursor, context)
        if variant_result is None:
            return variant_result

        variant_parse = variant_result
        variants.append(variant_parse.value)
        cursor = variant_parse.cursor

    if not variants:
        return None  # "Select expression must have at least one variant", cursor

    # Validate exactly one default variant (FTL spec requirement)
    default_count = sum(1 for v in variants if v.default)
    if default_count == 0:
        return None  # "Select expression must have exactly one default variant (marked with *)"
    if default_count > 1:
        return None  # "Select expression must have exactly one default variant, found multiple"

    select_expr = SelectExpression(selector=selector, variants=tuple(variants))
    return ParseResult(select_expr, cursor)


def parse_argument_expression(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[InlineExpression] | None:
    """Parse a single argument expression per FTL spec.

    FTL Argument Grammar:
        InlineExpression ::= StringLiteral | NumberLiteral | FunctionReference
                           | MessageReference | TermReference | VariableReference
                           | inline_placeable

    This handles all valid positional argument types including:
    - Variable references: $var
    - String literals: "text"
    - Number literals: 42, -123
    - Term references: -brand
    - Function references: NUMBER($val)
    - Inline placeables: { expr }
    - Message references: identifier

    Args:
        cursor: Current position in source
        context: Parse context for nested placeable depth tracking

    Returns:
        Success(ParseResult(InlineExpression, cursor)) on success
        None on parse error
    """
    if cursor.is_eof:
        return None

    ch = cursor.current

    # Variable reference: $var
    if ch == "$":
        var_result = parse_variable_reference(cursor)
        if var_result is None:
            return None
        return ParseResult(var_result.value, var_result.cursor)

    # String literal: "text"
    if ch == '"':
        str_result = parse_string_literal(cursor)
        if str_result is None:
            return None
        return ParseResult(StringLiteral(value=str_result.value), str_result.cursor)

    # Hyphen: could be TermReference (-brand) or negative number (-123)
    if ch == "-":
        next_cursor = cursor.advance()
        if not next_cursor.is_eof and is_identifier_start(next_cursor.current):
            # Term reference: -brand (ASCII letter after hyphen)
            term_result = parse_term_reference(cursor, context)
            if term_result is None:
                return None
            return ParseResult(term_result.value, term_result.cursor)
        # Negative number: -123
        num_result = parse_number(cursor)
        if num_result is None:
            return None
        num_value = parse_number_value(num_result.value)
        return ParseResult(
            NumberLiteral(value=num_value, raw=num_result.value), num_result.cursor
        )

    # Positive number: 42
    if ch in _ASCII_DIGITS:
        num_result = parse_number(cursor)
        if num_result is None:
            return None
        num_value = parse_number_value(num_result.value)
        return ParseResult(
            NumberLiteral(value=num_value, raw=num_result.value), num_result.cursor
        )

    # Inline placeable: { expr }
    if ch == "{":
        cursor = cursor.advance()  # Skip opening {
        placeable_result = parse_placeable(cursor, context)
        if placeable_result is None:
            return None
        return ParseResult(placeable_result.value, placeable_result.cursor)

    # Identifier: function call (UPPERCASE) or message reference
    # Note: ASCII letter check per Fluent spec for identifier start
    if is_identifier_start(ch) or ch == "_":
        id_result = parse_identifier(cursor)
        if id_result is None:
            return None

        name = id_result.value
        cursor_after_id = id_result.cursor

        # Check if uppercase identifier followed by '(' -> function call
        if name.isupper():
            lookahead = skip_blank_inline(cursor_after_id)
            if not lookahead.is_eof and lookahead.current == "(":
                func_result = parse_function_reference(cursor, context)
                if func_result is None:
                    return None
                return ParseResult(func_result.value, func_result.cursor)

        # Message reference (or identifier for named argument name)
        return ParseResult(
            MessageReference(id=Identifier(name)), cursor_after_id
        )

    return None  # "Expected argument expression"


def parse_call_arguments(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[CallArguments] | None:
    """Parse function call arguments: (pos1, pos2, name1: val1, name2: val2)

    Arguments consist of positional arguments followed by named arguments.
    Positional arguments must come before named arguments.
    Named argument names must be unique.

    Examples:
        ($value) -> CallArguments(positional=[$value], named=[])
        ($value, minimumFractionDigits: 2) -> CallArguments with both types

    Args:
        cursor: Position AFTER the opening '('
        context: Parse context for nested placeable depth tracking

    Returns:
        Success(ParseResult(CallArguments, cursor_after_))) on success
        Failure(ParseError(...)) on parse error
    """
    # Per spec: CallArguments ::= blank? "(" blank? argument_list blank? ")"
    cursor = skip_blank_inline(cursor)

    positional: list[InlineExpression] = []
    named: list[NamedArgument] = []
    seen_named_arg_names: set[str] = set()
    seen_named = False  # Track if we've seen any named args

    # Parse comma-separated arguments
    while not cursor.is_eof:
        cursor = skip_blank_inline(cursor)

        # Check for end of arguments
        if cursor.current == ")":
            break

        # Parse the argument expression using extracted helper
        arg_result = parse_argument_expression(cursor, context)
        if arg_result is None:
            return arg_result

        arg_parse = arg_result
        arg_expr = arg_parse.value
        cursor = skip_blank_inline(arg_parse.cursor)

        # Check if this is a named argument (followed by :)
        if not cursor.is_eof and cursor.current == ":":
            # This is a named argument
            cursor = cursor.advance()  # Skip :
            cursor = skip_blank_inline(cursor)

            # The argument expression must be an identifier (MessageReference)
            if not isinstance(arg_expr, MessageReference):
                return None  # "Named argument name must be an identifier", cursor

            arg_name = arg_expr.id.name

            # Check for duplicate named argument names
            if arg_name in seen_named_arg_names:
                return None  # f"Duplicate named argument: '{arg_name}'", cursor
            seen_named_arg_names.add(arg_name)

            # Parse the value (must be inline expression)
            if cursor.is_eof:
                return None  # "Expected value after ':'", cursor

            # Parse value expression using extracted helper
            value_result = parse_argument_expression(cursor, context)
            if value_result is None:
                return value_result

            value_parse = value_result
            value_expr = value_parse.value
            cursor = value_parse.cursor

            # Per FTL spec: NamedArgument ::= Identifier ":" (StringLiteral | NumberLiteral)
            # Named argument values MUST be literals, NOT references or variables
            if not isinstance(value_expr, (StringLiteral, NumberLiteral)):
                # Named argument values must be literals per FTL spec
                # This restriction enables static analysis by translation tools
                return None  # f"Named argument '{arg_name}' requires a literal value", cursor

            named.append(NamedArgument(name=Identifier(arg_name), value=value_expr))
            seen_named = True

        else:
            # This is a positional argument
            if seen_named:
                return None  # "Positional arguments must come before named arguments", cursor
            positional.append(arg_expr)

        cursor = skip_blank_inline(cursor)

        # Check for comma (optional before closing paren)
        if not cursor.is_eof and cursor.current == ",":
            cursor = cursor.advance()  # Skip comma
            cursor = skip_blank_inline(cursor)

    call_args = CallArguments(positional=tuple(positional), named=tuple(named))
    return ParseResult(call_args, cursor)


def parse_function_reference(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[FunctionReference] | None:
    """Parse function reference: FUNCTION(args)

    Function names must be uppercase identifiers.

    Examples:
        NUMBER($value)
        NUMBER($value, minimumFractionDigits: 2)
        DATETIME($date, dateStyle: "full")

    Args:
        cursor: Position at start of function name
        context: Parse context for nested placeable depth tracking

    Returns:
        Success(ParseResult(FunctionReference, cursor_after_))) on success
        Failure(ParseError(...)) on parse error
    """
    # Parse function name (must be uppercase identifier)
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    func_name = id_parse.value

    # Validate function name is uppercase
    if not func_name.isupper():
        return None  # f"Function name must be uppercase: '{func_name}'", id_parse.cursor

    # Per spec: FunctionReference uses blank? before "("
    cursor = skip_blank_inline(id_parse.cursor)

    # Expect opening parenthesis
    if cursor.is_eof or cursor.current != "(":
        return None  # "Expected '(' after function name", cursor

    cursor = cursor.advance()  # Skip (

    # Parse arguments
    args_result = parse_call_arguments(cursor, context)
    if args_result is None:
        return args_result

    args_parse = args_result
    cursor = skip_blank_inline(args_parse.cursor)

    # Expect closing parenthesis
    if cursor.is_eof or cursor.current != ")":
        return None  # "Expected ')' after function arguments"

    cursor = cursor.advance()  # Skip )

    func_ref = FunctionReference(id=Identifier(func_name), arguments=args_parse.value)
    return ParseResult(func_ref, cursor)


def parse_term_reference(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[TermReference] | None:
    """Parse term reference in inline expression (-term-id or -term.attr).

    FTL syntax:
        { -brand }
        { -brand.short }
        { -brand(case: "nominative") }

    Term references can have optional attribute access and arguments.

    Args:
        cursor: Current position (should be at '-')
        context: Parse context for nested placeable depth tracking

    Returns:
        Success(ParseResult(TermReference, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Expect '-' prefix
    if cursor.is_eof or cursor.current != "-":
        return None  # "Expected '-' at start of term reference", cursor, expected=["-"]

    cursor = cursor.advance()  # Skip '-'

    # Parse identifier
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    cursor = id_parse.cursor

    # Check for optional attribute access (.attribute)
    attribute: Identifier | None = None
    if not cursor.is_eof and cursor.current == ".":
        cursor = cursor.advance()  # Skip '.'

        attr_id_result = parse_identifier(cursor)
        if attr_id_result is None:
            return attr_id_result

        attr_id_parse = attr_id_result
        attribute = Identifier(attr_id_parse.value)
        cursor = attr_id_parse.cursor

    # Check for optional arguments (case: "nominative")
    # Per spec: TermReference uses blank? before "("
    cursor = skip_blank_inline(cursor)

    arguments: CallArguments | None = None
    if not cursor.is_eof and cursor.current == "(":
        # Parse call arguments (reuse function argument parsing)
        cursor = cursor.advance()  # Skip '('
        args_result = parse_call_arguments(cursor, context)
        if args_result is None:
            return args_result

        args_parse = args_result
        cursor = skip_blank_inline(args_parse.cursor)

        # Expect closing parenthesis
        if cursor.is_eof or cursor.current != ")":
            return None  # "Expected ')' after term arguments"

        cursor = cursor.advance()  # Skip ')'
        arguments = args_parse.value

    term_ref = TermReference(
        id=Identifier(id_parse.value), attribute=attribute, arguments=arguments
    )

    return ParseResult(term_ref, cursor)


def _parse_inline_string_literal(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse string literal inline expression."""
    str_result = parse_string_literal(cursor)
    if str_result is None:
        return None
    return ParseResult(StringLiteral(value=str_result.value), str_result.cursor)


def _parse_inline_number_literal(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse number literal inline expression."""
    num_result = parse_number(cursor)
    if num_result is None:
        return None
    num_str = num_result.value
    num_value = parse_number_value(num_str)
    return ParseResult(NumberLiteral(value=num_value, raw=num_str), num_result.cursor)


def _parse_inline_hyphen(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse hyphen-prefixed expression: term reference (-brand) or negative number (-123)."""
    next_cursor = cursor.advance()
    if not next_cursor.is_eof and is_identifier_start(next_cursor.current):
        # Term reference: -brand (ASCII letter after hyphen)
        term_result = parse_term_reference(cursor)
        if term_result is None:
            return None
        return ParseResult(term_result.value, term_result.cursor)
    # Negative number: -123
    return _parse_inline_number_literal(cursor)


def _parse_message_attribute(cursor: Cursor) -> tuple[Identifier | None, Cursor]:
    """Parse optional .attribute suffix on message/function references."""
    if cursor.is_eof or cursor.current != ".":
        return None, cursor
    cursor = cursor.advance()  # Skip '.'
    attr_id_result = parse_identifier(cursor)
    if attr_id_result is None:
        return None, cursor
    return Identifier(attr_id_result.value), attr_id_result.cursor


def _parse_inline_identifier(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse identifier-based expression: function call or message reference."""
    id_result = parse_identifier(cursor)
    if id_result is None:
        return None

    name = id_result.value
    cursor_after_id = id_result.cursor

    # Check if uppercase identifier followed by '(' -> function call
    if name.isupper():
        lookahead = skip_blank_inline(cursor_after_id)
        if not lookahead.is_eof and lookahead.current == "(":
            func_result = parse_function_reference(cursor)
            if func_result is None:
                return None
            return ParseResult(func_result.value, func_result.cursor)

    # Message reference with optional attribute
    attribute, final_cursor = _parse_message_attribute(cursor_after_id)
    return ParseResult(
        MessageReference(id=Identifier(name), attribute=attribute),
        final_cursor,
    )


def parse_inline_expression(
    cursor: Cursor,
) -> ParseResult[InlineExpression] | None:
    """Parse inline expression (variable, string, number, function, message, or term reference).

    Uses character-based dispatch for efficient parsing. Each expression type
    has a dedicated handler function.

    Handles:
    - Variable references: $var
    - String literals: "text"
    - Number literals: 42 or -123
    - Function calls: NUMBER(args)
    - Message references: identifier or identifier.attribute
    - Term references: -term-id or -term-id.attribute

    Args:
        cursor: Current position in source

    Returns:
        ParseResult with InlineExpression on success, None on parse error
    """
    if cursor.is_eof:
        return None

    ch = cursor.current

    # Dispatch based on first character
    match ch:
        case "$":
            var_result = parse_variable_reference(cursor)
            if var_result is None:
                return None
            return ParseResult(var_result.value, var_result.cursor)

        case '"':
            return _parse_inline_string_literal(cursor)

        case "-":
            return _parse_inline_hyphen(cursor)

        case _ if ch in _ASCII_DIGITS:
            return _parse_inline_number_literal(cursor)

        case _ if is_identifier_start(ch) or ch == "_":
            # ASCII letter check per Fluent spec for identifier start
            return _parse_inline_identifier(cursor)

        case _:
            return None


def parse_placeable(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Placeable] | None:
    """Parse placeable expression: {$var}, {"\\n"}, {$var -> [key] value}, or {FUNC()}.

    Parser combinator helper that reduces nesting in parse_pattern().

    Handles:
    - Variable references: {$var}
    - String literals: {"\\n"}
    - Number literals: {42}
    - Select expressions: {$var -> [one] item *[other] items}
    - Function calls: {NUMBER($value, minimumFractionDigits: 2)}

    Security:
        Enforces maximum nesting depth to prevent DoS attacks via deeply
        nested placeables. Configure via max_nesting_depth on FluentParserV1.

    Args:
        cursor: Position AFTER the opening '{'
        context: Parse context for depth tracking. If None, creates fresh context.

    Returns:
        Success(ParseResult(Placeable, cursor_after_})) on success
        None on parse error or nesting depth exceeded

    Example:
        cursor at: "$var}"  -> parses to Placeable(VariableReference("var"))
        cursor at: "\"\\n\"}" -> parses to Placeable(StringLiteral("\\n"))
        cursor at: "$n -> [one] 1 *[other] N}" -> parses to Placeable(SelectExpression(...))
        cursor at: "NUMBER($val)}" -> parses to Placeable(FunctionReference(...))
    """
    # Create default context if not provided
    if context is None:
        context = ParseContext()

    # Check nesting depth limit (DoS prevention)
    if context.is_depth_exceeded():
        # Nesting depth exceeded - return None to signal parse failure
        # This prevents stack overflow from deeply nested { { { ... } } }
        return None

    # Create child context with incremented depth for nested parsing
    nested_context = context.enter_placeable()

    # Per spec: inline_placeable ::= "{" blank? (SelectExpression | InlineExpression) blank? "}"
    cursor = skip_blank_inline(cursor)

    # Capture start position before parsing expression (for select expression span)
    expr_start_pos = cursor.pos

    # Parse the inline expression using extracted helper
    expr_result = parse_inline_expression(cursor)
    if expr_result is None:
        return expr_result

    expr_parse = expr_result
    expression = expr_parse.value
    parse_result_cursor = expr_parse.cursor

    cursor = skip_blank_inline(parse_result_cursor)

    # Check for select expression (->)
    # Per FTL 1.0 spec: SelectExpression ::= InlineExpression blank? "->" ...
    # Valid selectors (any InlineExpression):
    #   - VariableReference: { $var -> ... }
    #   - StringLiteral: { "foo" -> ... }
    #   - NumberLiteral: { 42 -> ... }
    #   - FunctionReference: { NUMBER($x) -> ... }
    #   - MessageReference: { msg -> ... } or { msg.attr -> ... }
    #   - TermReference: { -term -> ... } or { -term.attr -> ... }
    is_valid_selector = isinstance(
        expression,
        (
            VariableReference,
            StringLiteral,
            NumberLiteral,
            FunctionReference,
            MessageReference,
            TermReference,
        ),
    )

    if is_valid_selector and not cursor.is_eof and cursor.current == "-":
        # Peek ahead for ->
        next_cursor = cursor.advance()
        if not next_cursor.is_eof and next_cursor.current == ">":
            # It's a select expression!
            cursor = next_cursor.advance()  # Skip ->

            select_result = parse_select_expression(
                cursor, expression, expr_start_pos, nested_context
            )
            if select_result is None:
                return select_result

            select_parse = select_result
            cursor = skip_blank_inline(select_parse.cursor)

            # Expect }
            if cursor.is_eof or cursor.current != "}":
                return None  # "Expected '}' after select expression", cursor

            cursor = cursor.advance()  # Skip }
            return ParseResult(Placeable(expression=select_parse.value), cursor)

    # Just a simple inline expression {$var}, {"\n"}, or {42}
    # Expect }
    if cursor.is_eof or cursor.current != "}":
        return None  # "Expected '}'", cursor

    cursor = cursor.advance()  # Skip }
    return ParseResult(Placeable(expression=expression), cursor)


# =============================================================================
# Entry Parsing
# =============================================================================


def parse_message_header(cursor: Cursor) -> ParseResult[str] | None:
    """Parse message header: Identifier "="

    Returns identifier string and cursor after '='.
    """
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    # Per spec: Message ::= Identifier blank_inline? "=" ...
    cursor = skip_blank_inline(id_parse.cursor)

    if cursor.is_eof or cursor.current != "=":
        return None  # "Expected '=' after message ID", cursor

    cursor = cursor.advance()  # Skip =
    return ParseResult(id_parse.value, cursor)


def parse_message_attributes(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[list[Attribute]] | None:
    """Parse zero or more message attributes.

    Attributes must appear on new lines starting with '.'.

    Args:
        cursor: Current position in source
        context: Parse context for depth tracking
    """
    attributes: list[Attribute] = []

    while not cursor.is_eof:
        # Advance to next line.
        # Note: Line endings are normalized to LF at parser entry.
        if cursor.current == "\n":
            cursor = cursor.advance()
        else:
            break  # No newline, done with attributes

        # Check if line starts with '.' (attribute marker)
        # Per spec: Attribute ::= line_end blank? "." ...
        # blank allows spaces and newlines, but NOT tabs
        saved_cursor = cursor
        # Skip leading spaces on this line (NOT tabs per spec)
        cursor = cursor.skip_spaces()

        if cursor.is_eof or cursor.current != ".":
            cursor = saved_cursor
            break  # Not an attribute

        # Parse attribute
        attr_result = parse_attribute(saved_cursor, context)
        if attr_result is None:
            cursor = saved_cursor
            break  # Invalid attribute syntax

        attr_parse = attr_result
        attributes.append(attr_parse.value)
        cursor = attr_parse.cursor

    return ParseResult(attributes, cursor)


def validate_message_content(pattern: Pattern | None, attributes: list[Attribute]) -> bool:
    """Validate message has either pattern or attributes.

    Per Fluent spec: Message ::= ID "=" ((Pattern Attribute*) | (Attribute+))

    Args:
        pattern: Message value pattern (may be None)
        attributes: List of message attributes

    Returns:
        True if validation passed, False if validation failed
    """
    has_pattern = pattern is not None and len(pattern.elements) > 0
    has_attributes = len(attributes) > 0

    # Message must have either value or attributes
    return has_pattern or has_attributes


def parse_message(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Message] | None:
    """Parse message with full support for select expressions.

    Examples:
        "hello = World"
        "welcome = Hello, {$name}!"
        "count = {$num -> [one] item *[other] items}"

    Args:
        cursor: Current position in source
        context: Parse context for depth tracking

    Returns:
        Success(ParseResult(Message, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    start_pos = cursor.pos

    # Parse: Identifier "="
    id_result = parse_message_header(cursor)
    if id_result is None:
        return id_result
    id_parse = id_result
    cursor = id_parse.cursor

    # Parse pattern (message value)
    cursor = skip_multiline_pattern_start(cursor)
    pattern_result = parse_pattern(cursor, context)
    if pattern_result is None:
        return pattern_result
    pattern_parse = pattern_result
    cursor = pattern_parse.cursor

    # Parse: Attribute* (zero or more attributes)
    attributes_result = parse_message_attributes(cursor, context)
    if attributes_result is None:
        return attributes_result
    attributes_parse = attributes_result
    cursor = attributes_parse.cursor

    # Validate: Per spec, Message must have Pattern OR Attribute
    is_valid = validate_message_content(pattern_parse.value, attributes_parse.value)
    if not is_valid:
        return None  # Validation failed

    # Construct Message node
    message = Message(
        id=Identifier(id_parse.value),
        value=pattern_parse.value,
        attributes=tuple(attributes_parse.value),
        span=Span(start=start_pos, end=cursor.pos),
    )

    return ParseResult(message, cursor)


def parse_attribute(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Attribute] | None:
    """Parse message attribute (.attribute = pattern).

    FTL syntax:
        button = Save
            .tooltip = Click to save changes
            .aria-label = Save button

    Attributes are indented and start with a dot followed by an identifier.

    Args:
        cursor: Current position in source (should be at start of line with '.')
        context: Parse context for depth tracking

    Returns:
        Success(ParseResult(Attribute, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Skip leading whitespace (ONLY spaces per spec, NOT tabs or newlines)
    # Per spec: Attribute ::= line_end blank? "." ...
    # blank can contain spaces but NOT tabs
    cursor = skip_blank_inline(cursor)

    # Check for '.' at start
    if cursor.is_eof or cursor.current != ".":
        return None  # "Expected '.' at start of attribute", cursor, expected=["."]

    cursor = cursor.advance()  # Skip '.'

    # Parse identifier after '.'
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    # Per spec: Attribute ::= line_end blank? "." Identifier blank_inline? "=" ...
    cursor = skip_blank_inline(id_parse.cursor)

    # Expect '='
    if cursor.is_eof or cursor.current != "=":
        return None  # "Expected '=' after attribute identifier", cursor, expected=["="]

    cursor = cursor.advance()  # Skip '='
    # After '=', handle multiline pattern start (same as messages)
    # Per spec: Attribute ::= ... blank_inline? "=" blank_inline? Pattern
    # Pattern can start on same line or next line with indentation
    cursor = skip_multiline_pattern_start(cursor)

    # Parse pattern
    pattern_result = parse_pattern(cursor, context)
    if pattern_result is None:
        return pattern_result

    pattern_parse = pattern_result

    attribute = Attribute(id=Identifier(id_parse.value), value=pattern_parse.value)

    return ParseResult(attribute, pattern_parse.cursor)


def parse_term(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Term] | None:
    """Parse term definition (-term-id = pattern).

    FTL syntax:
        -brand = Firefox
        -brand-version = 3.0
            .tooltip = Current version

    Terms are private definitions prefixed with '-' and can have attributes.

    Args:
        cursor: Current position in source (should be at '-')
        context: Parse context for depth tracking

    Returns:
        Success(ParseResult(Term, new_cursor)) on success
        Failure(ParseError(...)) on parse error
    """
    # Capture start position for span
    start_pos = cursor.pos

    # Expect '-' prefix
    if cursor.is_eof or cursor.current != "-":
        return None  # "Expected '-' at start of term", cursor, expected=["-"]

    cursor = cursor.advance()  # Skip '-'

    # Parse identifier
    id_result = parse_identifier(cursor)
    if id_result is None:
        return id_result

    id_parse = id_result
    # Per spec: Term ::= "-" Identifier blank_inline? "=" ...
    cursor = skip_blank_inline(id_parse.cursor)

    # Expect '='
    if cursor.is_eof or cursor.current != "=":
        return None  # "Expected '=' after term ID", cursor, expected=["="]

    cursor = cursor.advance()  # Skip '='

    # After '=', skip inline whitespace (per spec: blank_inline, space only)
    cursor = skip_blank_inline(cursor)

    # Check for pattern starting on next line (multiline value pattern)
    # Example: -term =\n    value
    # Note: Line endings are normalized to LF at parser entry.
    if not cursor.is_eof and cursor.current == "\n":  # noqa: SIM102
        # Check if next line is indented (valid multiline pattern)
        if is_indented_continuation(cursor):
            # Multiline pattern - skip newline and leading indentation
            cursor = cursor.advance()
            # Skip leading indentation before parsing
            # parse_pattern will handle continuation lines itself
            cursor = cursor.skip_spaces()
        # Else: Empty pattern - leave cursor at newline, parse_pattern will handle it

    # Parse pattern
    pattern_result = parse_pattern(cursor, context)
    if pattern_result is None:
        return pattern_result

    pattern_parse = pattern_result
    cursor = pattern_parse.cursor

    # Validate term has non-empty value (FTL spec requirement)
    if not pattern_parse.value.elements:
        return None  # f'Expected term "-{id_parse.value}" to have a value'

    # Parse attributes (reuse attribute parsing logic)
    attributes: list[Attribute] = []
    while not cursor.is_eof:
        # Skip to next line.
        # Note: Line endings are normalized to LF at parser entry.
        if cursor.current == "\n":
            cursor = cursor.advance()
        else:
            # No newline, done with attributes
            break

        # Check if next line starts with whitespace followed by '.'
        # Per spec: Attribute ::= line_end blank? "." ...
        # blank can contain spaces, but NOT tabs
        saved_cursor = cursor
        cursor = cursor.skip_spaces()

        if cursor.is_eof or cursor.current != ".":
            # Not an attribute, restore cursor and break
            cursor = saved_cursor
            break

        # Parse attribute
        attr_result = parse_attribute(saved_cursor, context)
        if attr_result is None:
            # Not a valid attribute, restore and break
            cursor = saved_cursor
            break

        attr_parse = attr_result
        attributes.append(attr_parse.value)
        cursor = attr_parse.cursor

    # Create span from start to current position
    span = Span(start=start_pos, end=cursor.pos)

    term = Term(
        id=Identifier(id_parse.value),
        value=pattern_parse.value,
        attributes=tuple(attributes),
        span=span,
    )

    return ParseResult(term, cursor)


def parse_comment(cursor: Cursor) -> ParseResult[Comment] | None:
    """Parse comment line per Fluent spec.

    Per spec, comments come in three types:
    - # (single-line comment)
    - ## (group comment)
    - ### (resource comment)

    Adjacent comment lines of the same type are joined during AST construction.

    EBNF:
        CommentLine ::= ("###" | "##" | "#") ("\u0020" comment_char*)? line_end

    Args:
        cursor: Current parse position (must be at '#')

    Returns:
        Success with Comment node or Failure with ParseError
    """
    start_pos = cursor.pos

    # Determine comment type by counting '#' characters
    hash_count = 0
    temp_cursor = cursor
    while not temp_cursor.is_eof and temp_cursor.current == "#":
        hash_count += 1
        temp_cursor = temp_cursor.advance()

    # Validate comment type (1, 2, or 3 hashes)
    if hash_count > 3:
        return None  # f"Invalid comment: expected 1-3 '#' characters, found {hash_count}"

    # Map hash count to comment type
    comment_type = {
        1: CommentType.COMMENT,
        2: CommentType.GROUP,
        3: CommentType.RESOURCE,
    }.get(hash_count, CommentType.COMMENT)

    # Advance cursor past the '#' characters
    cursor = temp_cursor

    # Per spec: optional space after '#'
    if not cursor.is_eof and cursor.current == " ":
        cursor = cursor.advance()

    # Collect comment content (everything until line end)
    content_start = cursor.pos
    cursor = cursor.skip_to_line_end()

    # Extract comment text
    content = cursor.source[content_start : cursor.pos]

    # Advance past line ending (handles LF, CRLF, CR)
    cursor = cursor.skip_line_end()

    # Create Comment node with span
    comment_node = Comment(
        content=content,
        type=comment_type,
        span=Span(start=start_pos, end=cursor.pos),
    )

    return ParseResult(comment_node, cursor)
