"""Expression-oriented Fluent grammar rules."""

from __future__ import annotations

from typing import cast

from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    InlineExpression,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Placeable,
    SelectExpression,
    SelectorExpression,
    Span,
    StringLiteral,
    TermReference,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult
from ftllexengine.syntax.parser.context import ParseContext
from ftllexengine.syntax.parser.patterns import parse_simple_pattern
from ftllexengine.syntax.parser.primitives import (
    _ASCII_DIGITS,
    is_identifier_start,
    parse_identifier,
    parse_number,
    parse_number_value,
    parse_string_literal,
)
from ftllexengine.syntax.parser.whitespace import skip_blank, skip_blank_inline

__all__ = [
    "parse_argument_expression",
    "parse_call_arguments",
    "parse_function_reference",
    "parse_inline_expression",
    "parse_placeable",
    "parse_select_expression",
    "parse_term_reference",
    "parse_variable_reference",
    "parse_variant",
    "parse_variant_key",
]


def parse_variable_reference(cursor: Cursor) -> ParseResult[VariableReference] | None:
    """Parse variable reference: $variable."""
    start_pos = cursor.pos

    if cursor.is_eof or cursor.current != "$":
        return None

    cursor = cursor.advance()
    id_start_pos = cursor.pos

    result = parse_identifier(cursor)
    if isinstance(result, ParseError):
        return None

    var_ref = VariableReference(
        id=Identifier(
            result.value,
            span=Span(start=id_start_pos, end=result.cursor.pos),
        ),
        span=Span(start=start_pos, end=result.cursor.pos),
    )
    return ParseResult(var_ref, result.cursor)


def parse_variant_key(cursor: Cursor) -> ParseResult[Identifier | NumberLiteral] | None:
    """Parse variant key (identifier or number)."""
    start_pos = cursor.pos

    if not cursor.is_eof and (cursor.current in _ASCII_DIGITS or cursor.current == "-"):
        num_result = parse_number(cursor)
        if not isinstance(num_result, ParseError):
            num_str = num_result.value
            num_value = parse_number_value(num_str)
            return ParseResult(
                NumberLiteral(value=num_value, raw=num_str), num_result.cursor
            )

        id_result = parse_identifier(cursor)
        if isinstance(id_result, ParseError):
            return None

        return ParseResult(
            Identifier(id_result.value, span=Span(start=start_pos, end=id_result.cursor.pos)),
            id_result.cursor,
        )

    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    return ParseResult(
        Identifier(id_result.value, span=Span(start=start_pos, end=id_result.cursor.pos)),
        id_result.cursor,
    )


def parse_variant(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Variant] | None:
    """Parse variant: [key] pattern or *[key] pattern."""
    is_default = False
    if not cursor.is_eof and cursor.current == "*":
        is_default = True
        cursor = cursor.advance()

    if cursor.is_eof or cursor.current != "[":
        return None

    cursor = cursor.advance()
    cursor = skip_blank(cursor)
    key_result = parse_variant_key(cursor)
    if key_result is None:
        return key_result

    cursor = skip_blank(key_result.cursor)
    if cursor.is_eof or cursor.current != "]":
        return None

    cursor = cursor.advance()
    cursor = skip_blank_inline(cursor)
    pattern_result = parse_simple_pattern(cursor, context)
    if pattern_result is None:
        return pattern_result

    variant = Variant(key=key_result.value, value=pattern_result.value, default=is_default)
    return ParseResult(variant, pattern_result.cursor)


def parse_select_expression(
    cursor: Cursor,
    selector: SelectorExpression,
    start_pos: int,
    context: ParseContext | None = None,
) -> ParseResult[SelectExpression] | None:
    """Parse select expression after seeing selector and ->."""
    cursor = skip_blank(cursor)
    variants: list[Variant] = []

    while not cursor.is_eof:
        cursor = skip_blank(cursor)

        if cursor.is_eof or cursor.current == "}":
            break

        variant_result = parse_variant(cursor, context)
        if variant_result is None:
            return variant_result

        variants.append(variant_result.value)
        cursor = variant_result.cursor

    if not variants:
        return None

    default_count = sum(1 for variant in variants if variant.default)
    if default_count != 1:
        return None

    span = Span(start=start_pos, end=cursor.pos)
    select_expr = SelectExpression(selector=selector, variants=tuple(variants), span=span)
    return ParseResult(select_expr, cursor)


def _parse_message_attribute(cursor: Cursor) -> tuple[Identifier | None, Cursor]:
    """Parse optional .attribute suffix on message/function references."""
    if cursor.is_eof or cursor.current != ".":
        return None, cursor
    cursor = cursor.advance()
    attr_start = cursor.pos
    attr_id_result = parse_identifier(cursor)
    if isinstance(attr_id_result, ParseError):
        return None, cursor
    attr_id = Identifier(
        attr_id_result.value,
        span=Span(start=attr_start, end=attr_id_result.cursor.pos),
    )
    return attr_id, attr_id_result.cursor


def parse_argument_expression(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[InlineExpression] | None:
    """Parse a single argument expression per FTL spec."""
    if cursor.is_eof:
        return None

    start_pos = cursor.pos
    ch = cursor.current

    if ch == "$":
        var_result = parse_variable_reference(cursor)
        if var_result is None:
            return None
        return ParseResult(var_result.value, var_result.cursor)

    if ch == '"':
        str_result = parse_string_literal(cursor)
        if isinstance(str_result, ParseError):
            return None
        return ParseResult(StringLiteral(value=str_result.value), str_result.cursor)

    if ch == "-":
        next_cursor = cursor.advance()
        if not next_cursor.is_eof and is_identifier_start(next_cursor.current):
            term_result = parse_term_reference(cursor, context)
            if term_result is None:
                return None
            return ParseResult(term_result.value, term_result.cursor)

        num_result = parse_number(cursor)
        if isinstance(num_result, ParseError):
            return None
        num_value = parse_number_value(num_result.value)
        return ParseResult(
            NumberLiteral(value=num_value, raw=num_result.value), num_result.cursor
        )

    if ch in _ASCII_DIGITS:
        num_result = parse_number(cursor)
        if isinstance(num_result, ParseError):
            return None
        num_value = parse_number_value(num_result.value)
        return ParseResult(
            NumberLiteral(value=num_value, raw=num_result.value), num_result.cursor
        )

    if ch == "{":
        cursor = cursor.advance()
        placeable_result = parse_placeable(cursor, context)
        if placeable_result is None:
            return None
        return ParseResult(placeable_result.value, placeable_result.cursor)

    if is_identifier_start(ch) or ch == "_":
        id_result = parse_identifier(cursor)
        if isinstance(id_result, ParseError):
            return None

        name = id_result.value
        cursor_after_id = id_result.cursor
        lookahead = skip_blank_inline(cursor_after_id)
        if not lookahead.is_eof and lookahead.current == "(":
            func_result = parse_function_reference(cursor, context)
            if func_result is None:
                return None
            return ParseResult(func_result.value, func_result.cursor)

        attribute, final_cursor = _parse_message_attribute(cursor_after_id)
        return ParseResult(
            MessageReference(
                id=Identifier(name, span=Span(start=start_pos, end=cursor_after_id.pos)),
                attribute=attribute,
                span=Span(start=start_pos, end=final_cursor.pos),
            ),
            final_cursor,
        )

    return None


def parse_call_arguments(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[CallArguments] | None:
    """Parse function call arguments: (pos1, pos2, name1: val1, name2: val2)."""
    cursor = skip_blank(cursor)

    positional: list[InlineExpression] = []
    named: list[NamedArgument] = []
    seen_named_arg_names: set[str] = set()
    seen_named = False

    while not cursor.is_eof:
        cursor = skip_blank(cursor)
        if cursor.current == ")":
            break

        arg_result = parse_argument_expression(cursor, context)
        if arg_result is None:
            return arg_result

        arg_expr = arg_result.value
        cursor = skip_blank(arg_result.cursor)

        if not cursor.is_eof and cursor.current == ":":
            cursor = cursor.advance()
            cursor = skip_blank(cursor)

            if not isinstance(arg_expr, MessageReference):
                return None

            arg_name = arg_expr.id.name
            if arg_name in seen_named_arg_names:
                return None
            seen_named_arg_names.add(arg_name)

            if cursor.is_eof:
                return None

            value_result = parse_argument_expression(cursor, context)
            if value_result is None:
                return value_result

            value_expr = value_result.value
            cursor = value_result.cursor
            if not isinstance(value_expr, (StringLiteral, NumberLiteral)):
                return None

            named.append(
                NamedArgument(
                    name=Identifier(arg_name, span=arg_expr.id.span),
                    value=value_expr,
                )
            )
            seen_named = True
        else:
            if seen_named:
                return None
            positional.append(arg_expr)

        cursor = skip_blank(cursor)
        if not cursor.is_eof and cursor.current == ",":
            cursor = cursor.advance()
            cursor = skip_blank(cursor)

    call_args = CallArguments(positional=tuple(positional), named=tuple(named))
    return ParseResult(call_args, cursor)


def parse_function_reference(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[FunctionReference] | None:
    """Parse function reference: identifier(args)."""
    if context is None:
        context = ParseContext()

    if context.is_depth_exceeded():
        return None

    start_pos = cursor.pos
    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    func_name = id_result.value
    cursor = skip_blank_inline(id_result.cursor)
    if cursor.is_eof or cursor.current != "(":
        return None

    cursor = cursor.advance()
    nested_context = context.enter_nesting()
    args_result = parse_call_arguments(cursor, nested_context)
    if args_result is None:
        return args_result

    cursor = skip_blank_inline(args_result.cursor)
    if cursor.is_eof or cursor.current != ")":
        return None

    cursor = cursor.advance()
    func_ref = FunctionReference(
        id=Identifier(func_name, span=Span(start=start_pos, end=id_result.cursor.pos)),
        arguments=args_result.value,
        span=Span(start=start_pos, end=cursor.pos),
    )
    return ParseResult(func_ref, cursor)


def parse_term_reference(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[TermReference] | None:
    """Parse term reference in inline expression (-term-id or -term.attr)."""
    if context is None:
        context = ParseContext()

    start_pos = cursor.pos
    if cursor.is_eof or cursor.current != "-":
        return None

    cursor = cursor.advance()
    id_start = cursor.pos
    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    cursor = id_result.cursor
    attribute: Identifier | None = None
    if not cursor.is_eof and cursor.current == ".":
        cursor = cursor.advance()
        attr_start = cursor.pos
        attr_id_result = parse_identifier(cursor)
        if isinstance(attr_id_result, ParseError):
            return None
        attribute = Identifier(
            attr_id_result.value,
            span=Span(start=attr_start, end=attr_id_result.cursor.pos),
        )
        cursor = attr_id_result.cursor

    cursor = skip_blank_inline(cursor)
    arguments: CallArguments | None = None
    if not cursor.is_eof and cursor.current == "(":
        if context.is_depth_exceeded():
            return None

        cursor = cursor.advance()
        nested_context = context.enter_nesting()
        args_result = parse_call_arguments(cursor, nested_context)
        if args_result is None:
            return args_result

        cursor = skip_blank_inline(args_result.cursor)
        if cursor.is_eof or cursor.current != ")":
            return None

        cursor = cursor.advance()
        arguments = args_result.value

    term_ref = TermReference(
        id=Identifier(id_result.value, span=Span(start=id_start, end=id_result.cursor.pos)),
        attribute=attribute,
        arguments=arguments,
        span=Span(start=start_pos, end=cursor.pos),
    )
    return ParseResult(term_ref, cursor)


def _parse_inline_string_literal(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse string literal inline expression."""
    str_result = parse_string_literal(cursor)
    if isinstance(str_result, ParseError):
        return None
    return ParseResult(StringLiteral(value=str_result.value), str_result.cursor)


def _parse_inline_number_literal(cursor: Cursor) -> ParseResult[InlineExpression] | None:
    """Parse number literal inline expression."""
    num_result = parse_number(cursor)
    if isinstance(num_result, ParseError):
        return None
    num_str = num_result.value
    num_value = parse_number_value(num_str)
    return ParseResult(NumberLiteral(value=num_value, raw=num_str), num_result.cursor)


def _parse_inline_hyphen(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[InlineExpression] | None:
    """Parse hyphen-prefixed expression."""
    next_cursor = cursor.advance()
    if not next_cursor.is_eof and is_identifier_start(next_cursor.current):
        term_result = parse_term_reference(cursor, context)
        if term_result is None:
            return None
        return ParseResult(term_result.value, term_result.cursor)
    return _parse_inline_number_literal(cursor)


def _parse_inline_identifier(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[InlineExpression] | None:
    """Parse identifier-based expression: function call or message reference."""
    start_pos = cursor.pos
    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    name = id_result.value
    cursor_after_id = id_result.cursor
    lookahead = skip_blank_inline(cursor_after_id)
    if not lookahead.is_eof and lookahead.current == "(":
        func_result = parse_function_reference(cursor, context)
        if func_result is None:
            return None
        return ParseResult(func_result.value, func_result.cursor)

    attribute, final_cursor = _parse_message_attribute(cursor_after_id)
    return ParseResult(
        MessageReference(
            id=Identifier(name, span=Span(start=start_pos, end=cursor_after_id.pos)),
            attribute=attribute,
            span=Span(start=start_pos, end=final_cursor.pos),
        ),
        final_cursor,
    )


def parse_inline_expression(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[InlineExpression] | None:
    """Parse inline expression per Fluent spec."""
    if cursor.is_eof:
        return None

    ch = cursor.current
    match ch:
        case "$":
            var_result = parse_variable_reference(cursor)
            if var_result is None:
                return None
            return ParseResult(var_result.value, var_result.cursor)
        case '"':
            return _parse_inline_string_literal(cursor)
        case "-":
            return _parse_inline_hyphen(cursor, context)
        case "{":
            placeable_result = parse_placeable(cursor.advance(), context)
            if placeable_result is None:
                return None
            return ParseResult(placeable_result.value, placeable_result.cursor)
        case _ if ch in _ASCII_DIGITS:
            return _parse_inline_number_literal(cursor)
        case _ if is_identifier_start(ch):
            return _parse_inline_identifier(cursor, context)
        case _:
            return None


def parse_placeable(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Placeable] | None:
    """Parse placeable expression."""
    if context is None:
        context = ParseContext()

    if context.is_depth_exceeded():
        context.mark_depth_exceeded()
        return None

    nested_context = context.enter_nesting()
    cursor = skip_blank(cursor)
    expr_start_pos = cursor.pos

    expr_result = parse_inline_expression(cursor, nested_context)
    if expr_result is None:
        return expr_result

    expression = expr_result.value
    cursor = skip_blank(expr_result.cursor)

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
        next_cursor = cursor.advance()
        if not next_cursor.is_eof and next_cursor.current == ">":
            cursor = next_cursor.advance()
            select_result = parse_select_expression(
                cursor,
                cast("SelectorExpression", expression),
                expr_start_pos,
                nested_context,
            )
            if select_result is None:
                return select_result

            cursor = skip_blank(select_result.cursor)
            if cursor.is_eof or cursor.current != "}":
                return None

            cursor = cursor.advance()
            return ParseResult(Placeable(expression=select_result.value), cursor)

    if cursor.is_eof or cursor.current != "}":
        return None

    cursor = cursor.advance()
    return ParseResult(Placeable(expression=expression), cursor)
