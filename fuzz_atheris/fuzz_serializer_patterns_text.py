from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import atheris
from fuzz_common import gen_ftl_value
from fuzz_serializer_support import (
    _FTL_SYNTAX_CHARS,
    _mk_attr,
    _mk_id,
    _mk_message,
    _mk_pattern,
    _mk_term,
    _verify_serializer_roundtrip,
)

from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)


def _pattern_leading_whitespace(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values with leading whitespace.

    Targets BUG-SERIALIZER-LEADING-WS-001: the parser consumes post-=
    whitespace as syntax, so leading spaces in TextElement values must
    be wrapped in StringLiteral placeables by the serializer.
    """
    num_spaces = fdp.ConsumeIntInRange(1, 8)
    base_value = gen_ftl_value(fdp)
    value_text = " " * num_spaces + base_value

    # Message with leading-whitespace value
    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

    # Attribute with leading-whitespace value
    attr = _mk_attr(fdp, value_text)
    msg2 = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=(attr,),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg2,)), pattern)

def _pattern_trailing_whitespace(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values with trailing whitespace."""
    num_spaces = fdp.ConsumeIntInRange(1, 8)
    base_value = gen_ftl_value(fdp)
    value_text = base_value + " " * num_spaces

    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_syntax_chars_value(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """TextElement values containing FTL syntax characters.

    Tests that the serializer correctly escapes or wraps braces,
    dots, hash, asterisk, and brackets at various positions.
    """
    base_value = gen_ftl_value(fdp)
    char = _FTL_SYNTAX_CHARS[
        fdp.ConsumeIntInRange(0, len(_FTL_SYNTAX_CHARS) - 1)
    ]
    pos = fdp.ConsumeIntInRange(0, len(base_value))
    value_text = base_value[:pos] + char + base_value[pos:]

    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

    # Also test in attribute value
    attr = _mk_attr(fdp, value_text)
    msg2 = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=(attr,),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg2,)), pattern)

def _pattern_simple_message(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Baseline: simple message with clean text value."""
    value = gen_ftl_value(fdp)
    msg = _mk_message(fdp, value=_mk_pattern(value))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_string_literal_placeable(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Patterns with StringLiteral placeables containing edge-case content."""
    literal_value = gen_ftl_value(fdp, max_length=20)

    # Optionally inject special content
    special = fdp.ConsumeIntInRange(0, 3)
    match special:
        case 0:
            literal_value = " " * fdp.ConsumeIntInRange(1, 5)
        case 1:
            literal_value = "\\" + literal_value
        case 2:
            literal_value = '"' + literal_value + '"'

    placeable = Placeable(expression=StringLiteral(value=literal_value))
    text_before = TextElement(value=gen_ftl_value(fdp, max_length=15))
    elements: tuple[TextElement | Placeable, ...] = (text_before, placeable)
    pat = Pattern(elements=elements)

    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_attribute_edge_cases(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Attributes with edge-case values: leading/trailing spaces, syntax chars."""
    num_attrs = fdp.ConsumeIntInRange(1, 4)
    attrs: list[Attribute] = []
    for _ in range(num_attrs):
        edge_type = fdp.ConsumeIntInRange(0, 3)
        base = gen_ftl_value(fdp)
        match edge_type:
            case 0:
                val = " " * fdp.ConsumeIntInRange(1, 5) + base
            case 1:
                val = base + " " * fdp.ConsumeIntInRange(1, 5)
            case 2:
                ch = _FTL_SYNTAX_CHARS[
                    fdp.ConsumeIntInRange(
                        0, len(_FTL_SYNTAX_CHARS) - 1,
                    )
                ]
                val = ch + base
            case _:
                val = base
        attrs.append(_mk_attr(fdp, val))

    msg = _mk_message(
        fdp,
        value=_mk_pattern(gen_ftl_value(fdp)),
        attributes=tuple(attrs),
    )
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_term_edge_cases(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Terms with edge-case attribute and value content."""
    num_spaces = fdp.ConsumeIntInRange(0, 5)
    base = gen_ftl_value(fdp)
    value_text = " " * num_spaces + base if num_spaces > 0 else base

    attrs: tuple[Attribute, ...] = ()
    if fdp.ConsumeBool():
        attr_val = " " * fdp.ConsumeIntInRange(1, 3) + gen_ftl_value(fdp)
        attrs = (_mk_attr(fdp, attr_val),)

    term = _mk_term(fdp, value=_mk_pattern(value_text), attributes=attrs)
    _verify_serializer_roundtrip(Resource(entries=(term,)), pattern)

def _pattern_select_expression(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Select expressions constructed from AST nodes."""
    var_id = _mk_id(fdp)
    selector = VariableReference(id=var_id)

    num_variants = fdp.ConsumeIntInRange(1, 4)
    variants: list[Variant] = []
    for _ in range(num_variants):
        key_is_number = fdp.ConsumeBool()
        if key_is_number:
            num = fdp.ConsumeIntInRange(0, 99)
            key: Identifier | NumberLiteral = NumberLiteral(
                value=num, raw=str(num),
            )
        else:
            key = _mk_id(fdp)

        val = gen_ftl_value(fdp)
        # Optionally add leading whitespace to variant value
        if fdp.ConsumeBool():
            val = " " + val
        variants.append(Variant(key=key, value=_mk_pattern(val)))

    # Ensure exactly one default
    variants.append(
        Variant(
            key=Identifier(name="other"),
            value=_mk_pattern(gen_ftl_value(fdp)),
            default=True,
        ),
    )

    sel = SelectExpression(
        selector=selector, variants=tuple(variants),
    )
    pat = Pattern(elements=(Placeable(expression=sel),))
    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_mixed_elements(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Patterns with interleaved TextElement and Placeable nodes."""
    num_elements = fdp.ConsumeIntInRange(2, 6)
    elements: list[TextElement | Placeable] = []

    for _ in range(num_elements):
        is_placeable = fdp.ConsumeBool()
        if is_placeable:
            expr_type = fdp.ConsumeIntInRange(0, 2)
            match expr_type:
                case 0:
                    expr: Any = StringLiteral(
                        value=gen_ftl_value(fdp, max_length=10),
                    )
                case 1:
                    expr = VariableReference(id=_mk_id(fdp))
                case _:
                    expr = TermReference(id=_mk_id(fdp))
            elements.append(Placeable(expression=expr))
        else:
            val = gen_ftl_value(fdp, max_length=15)
            # Optionally inject leading space
            if fdp.ConsumeBool() and elements:
                val = " " + val
            elements.append(TextElement(value=val))

    pat = Pattern(elements=tuple(elements))
    msg = _mk_message(fdp, value=pat)
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)

def _pattern_multiline_value(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """Multi-line TextElement values with newlines and indentation."""
    num_lines = fdp.ConsumeIntInRange(2, 5)
    lines: list[str] = []
    for _ in range(num_lines):
        line = gen_ftl_value(fdp, max_length=30)
        # Optionally add leading spaces
        if fdp.ConsumeBool():
            line = " " * fdp.ConsumeIntInRange(1, 4) + line
        lines.append(line)

    # Join with newlines and indentation (4 spaces for FTL continuation)
    value_text = ("\n    ").join(lines)
    msg = _mk_message(fdp, value=_mk_pattern(value_text))
    _verify_serializer_roundtrip(Resource(entries=(msg,)), pattern)
