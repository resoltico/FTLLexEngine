"""Shared serialization helpers for FluentSerializer."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from .ast import (
    CallArguments,
    Expression,
    FunctionReference,
    Identifier,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TermReference,
    TextElement,
    VariableReference,
)
from .serializer_lines import (
    _CHAR_PLACEABLE,
    _CONT_INDENT,
    _VARIANT_INDENT,
    _classify_line,
    _escape_text,
    _LineKind,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ftllexengine.core.depth_guard import DepthGuard

__all__ = [
    "emit_classified_line",
    "pattern_needs_separate_line",
    "serialize_call_arguments",
    "serialize_expression",
    "serialize_pattern",
    "serialize_select_expression",
]


def pattern_needs_separate_line(pattern: Pattern) -> bool:
    """Return True when separate-line mode is required for roundtrip safety."""
    prev_ends_newline = False
    for elem in pattern.elements:
        if isinstance(elem, TextElement):
            if prev_ends_newline and elem.value and elem.value[0] == " ":
                first_nl = elem.value.find("\n")
                first_line = elem.value[:first_nl] if first_nl != -1 else elem.value
                kind, _ = _classify_line(first_line)
                if kind is _LineKind.NORMAL:
                    return True
            value = elem.value
            idx = value.find("\n")
            while idx != -1 and idx + 1 < len(value):
                if value[idx + 1] == " ":
                    next_nl = value.find("\n", idx + 1)
                    line = value[idx + 1 : next_nl] if next_nl != -1 else value[idx + 1 :]
                    kind, _ = _classify_line(line)
                    if kind is _LineKind.NORMAL:
                        return True
                idx = value.find("\n", idx + 1)
            prev_ends_newline = value.endswith("\n")
        else:
            prev_ends_newline = False
    return False


def serialize_pattern(  # noqa: C901, PLR0912 - FTL pattern grammar needs explicit branching.
    pattern: Pattern,
    output: list[str],
    depth_guard: DepthGuard,
    *,
    pattern_needs_separate_line_fn: Callable[[Pattern], bool],
    emit_classified_line_fn: Callable[[str, list[str]], None],
    serialize_expression_fn: Callable[[Expression, list[str], DepthGuard], None],
) -> None:
    """Serialize Pattern elements with line and character ambiguity handling."""
    needs_separate_line = pattern_needs_separate_line_fn(pattern)
    if needs_separate_line:
        output.append("\n" + _CONT_INDENT)

    leading_ws_len = 0
    if (
        pattern.elements
        and isinstance(pattern.elements[0], TextElement)
        and pattern.elements[0].value
        and pattern.elements[0].value[0] == " "
    ):
        first_value = pattern.elements[0].value
        stripped = first_value.lstrip(" ")
        leading_ws_len = len(first_value) - len(stripped)
        output.append('{ "')
        output.append(" " * leading_ws_len)
        output.append('" }')

    at_line_start = needs_separate_line

    for element in pattern.elements:
        if isinstance(element, TextElement):
            text = element.value

            if leading_ws_len > 0:
                text = text[leading_ws_len:]
                leading_ws_len = 0
                if not text:
                    at_line_start = False
                    continue

            if "\n" in text:
                lines = text.split("\n")
                if at_line_start:
                    emit_classified_line_fn(lines[0], output)
                else:
                    _escape_text(lines[0], output)
                for line in lines[1:]:
                    output.append("\n    ")
                    emit_classified_line_fn(line, output)
                at_line_start = not lines[-1]
            else:
                if at_line_start:
                    emit_classified_line_fn(text, output)
                else:
                    _escape_text(text, output)
                at_line_start = False

        else:
            output.append("{ ")
            with depth_guard:
                serialize_expression_fn(element.expression, output, depth_guard)
            output.append(" }")
            at_line_start = False


def emit_classified_line(line: str, output: list[str]) -> None:
    """Emit one continuation line using the classifier's single dispatch point."""
    kind, ws_len = _classify_line(line)
    match kind:
        case _LineKind.EMPTY:
            pass
        case _LineKind.WHITESPACE_ONLY:
            output.append('{ "')
            output.append(line)
            output.append('" }')
        case _LineKind.SYNTAX_LEADING:
            if ws_len:
                output.append('{ "')
                output.append(line[:ws_len])
                output.append('" }')
            output.append(_CHAR_PLACEABLE[line[ws_len]])
            remaining = line[ws_len + 1 :]
            if remaining:
                _escape_text(remaining, output)
        case _LineKind.NORMAL:
            _escape_text(line, output)
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def serialize_expression(  # noqa: C901, PLR0912 - Expression union dispatch is intentionally explicit.
    expr: Expression,
    output: list[str],
    depth_guard: DepthGuard,
    *,
    serialize_call_arguments_fn: Callable[[CallArguments, list[str], DepthGuard], None],
    serialize_expression_fn: Callable[[Expression, list[str], DepthGuard], None],
    serialize_select_expression_fn: Callable[[SelectExpression, list[str], DepthGuard], None],
) -> None:
    """Serialize one Expression union member."""
    match expr:
        case StringLiteral(value=value):
            result: list[str] = []
            for char in value:
                code = ord(char)
                if char == "\\":
                    result.append("\\\\")
                elif char == '"':
                    result.append('\\"')
                elif code < 0x20 or code == 0x7F:
                    result.append(f"\\u{code:04X}")
                else:
                    result.append(char)
            output.append(f'"{"".join(result)}"')
        case NumberLiteral(raw=raw):
            output.append(raw)
        case VariableReference(id=Identifier(name=name)):
            output.append(f"${name}")
        case MessageReference(id=Identifier(name=name), attribute=attr):
            output.append(name)
            if attr:
                output.append(f".{attr.name}")
        case TermReference(id=Identifier(name=name), attribute=attr, arguments=args):
            output.append(f"-{name}")
            if attr:
                output.append(f".{attr.name}")
            if args:
                serialize_call_arguments_fn(args, output, depth_guard)
        case FunctionReference(id=Identifier(name=name), arguments=args):
            output.append(name)
            serialize_call_arguments_fn(args, output, depth_guard)
        case Placeable(expression=inner):
            output.append("{ ")
            with depth_guard:
                serialize_expression_fn(inner, output, depth_guard)
            output.append(" }")
        case SelectExpression():
            serialize_select_expression_fn(expr, output, depth_guard)
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def serialize_call_arguments(
    args: CallArguments,
    output: list[str],
    depth_guard: DepthGuard,
    *,
    serialize_expression_fn: Callable[[Expression, list[str], DepthGuard], None],
) -> None:
    """Serialize positional and named call arguments with depth protection."""
    output.append("(")

    for i, arg in enumerate(args.positional):
        if i > 0:
            output.append(", ")
        with depth_guard:
            serialize_expression_fn(arg, output, depth_guard)

    named_arg: NamedArgument
    for i, named_arg in enumerate(args.named):
        if i > 0 or args.positional:
            output.append(", ")
        output.append(f"{named_arg.name.name}: ")
        with depth_guard:
            serialize_expression_fn(named_arg.value, output, depth_guard)

    output.append(")")


def serialize_select_expression(
    expr: SelectExpression,
    output: list[str],
    depth_guard: DepthGuard,
    *,
    serialize_expression_fn: Callable[[Expression, list[str], DepthGuard], None],
    serialize_pattern_fn: Callable[[Pattern, list[str], DepthGuard], None],
) -> None:
    """Serialize a SelectExpression and its variants."""
    with depth_guard:
        serialize_expression_fn(expr.selector, output, depth_guard)
    output.append(" ->")

    for variant in expr.variants:
        output.append(_VARIANT_INDENT)
        if variant.default:
            output.append("*")
        output.append("[")

        match variant.key:
            case Identifier(name=name):
                output.append(name)
            case NumberLiteral(raw=raw):
                output.append(raw)
            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

        output.append("] ")
        serialize_pattern_fn(variant.value, output, depth_guard)

    output.append("\n")
