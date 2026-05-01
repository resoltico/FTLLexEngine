from __future__ import annotations

import random
from dataclasses import replace as dc_replace
from typing import Any

import atheris
from fuzz_serializer_support import (
    _FTL_SYNTAX_CHARS,
    _parser,
    _state,
)

from ftllexengine.syntax.ast import (
    Junk,
    Message,
    Placeable,
    Resource,
    StringLiteral,
    Term,
    TextElement,
)
from ftllexengine.syntax.serializer import serialize


def _mutate_constructed_ast(ast: Resource, seed: int) -> Resource:
    """Apply mutations targeting serializer edge cases.

    Mutations focus on whitespace injection and syntax character
    insertion -- the exact bug classes that text-based fuzzers miss.
    """
    rng = random.Random(seed)
    entries = list(ast.entries)
    if not entries:
        return ast

    mut_type = rng.randint(0, 3)

    match mut_type:
        case 0:
            entries = _mut_add_leading_spaces(entries, rng)
        case 1:
            entries = _mut_add_syntax_char(entries, rng)
        case 2:
            entries = _mut_add_attribute_ws(entries, rng)
        case 3:
            entries = _mut_nest_placeable(entries, rng)

    return Resource(entries=tuple(entries))

def _mut_add_leading_spaces(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Inject leading spaces into the first TextElement of a pattern."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        elements = list(entry.value.elements)
        for idx, elem in enumerate(elements):
            if isinstance(elem, TextElement) and elem.value:
                n = rng.randint(1, 6)
                elements[idx] = dc_replace(
                    elem, value=" " * n + elem.value,
                )
                new_pat = dc_replace(
                    entry.value, elements=tuple(elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries

def _mut_add_syntax_char(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Insert a syntax character at a random position in a TextElement."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        elements = list(entry.value.elements)
        for idx, elem in enumerate(elements):
            if isinstance(elem, TextElement) and elem.value:
                ch = rng.choice(_FTL_SYNTAX_CHARS)
                pos = rng.randint(0, len(elem.value))
                new_val = elem.value[:pos] + ch + elem.value[pos:]
                elements[idx] = dc_replace(elem, value=new_val)
                new_pat = dc_replace(
                    entry.value, elements=tuple(elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries

def _mut_add_attribute_ws(
    entries: list[Any],
    rng: random.Random,
) -> list[Any]:
    """Add leading whitespace to an attribute value."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or not entry.attributes:
            continue
        attr = rng.choice(entry.attributes)
        if attr.value and attr.value.elements:
            elem = attr.value.elements[0]
            if isinstance(elem, TextElement) and elem.value:
                n = rng.randint(1, 5)
                new_elem = dc_replace(
                    elem, value=" " * n + elem.value,
                )
                new_elements = (new_elem, *attr.value.elements[1:])
                new_pat = dc_replace(
                    attr.value, elements=new_elements,
                )
                new_attr = dc_replace(attr, value=new_pat)
                new_attrs = tuple(
                    new_attr if a is attr else a
                    for a in entry.attributes
                )
                entries[i] = dc_replace(entry, attributes=new_attrs)
                return entries
    return entries

def _mut_nest_placeable(
    entries: list[Any],
    _rng: random.Random,
) -> list[Any]:
    """Wrap a StringLiteral in an additional Placeable layer."""
    for i, entry in enumerate(entries):
        if not isinstance(entry, (Message, Term)) or entry.value is None:
            continue
        for idx, elem in enumerate(entry.value.elements):
            if (
                isinstance(elem, Placeable)
                and isinstance(elem.expression, StringLiteral)
            ):
                inner = Placeable(expression=elem.expression)
                new_elem = dc_replace(elem, expression=inner)
                new_elements = list(entry.value.elements)
                new_elements[idx] = new_elem
                new_pat = dc_replace(
                    entry.value, elements=tuple(new_elements),
                )
                entries[i] = dc_replace(entry, value=new_pat)
                return entries
    return entries

def _custom_mutator(data: bytes, max_size: int, seed: int) -> bytes:
    """Structure-aware mutator for AST-constructed inputs.

    Parses the serialized output, applies AST-level mutations targeting
    serializer edge cases, re-serializes, then applies byte-level mutation.
    """
    try:
        source = data.decode("utf-8", errors="replace")
        ast = _parser.parse(source)

        if ast.entries and not any(
            isinstance(e, Junk) for e in ast.entries
        ):
            mutated = _mutate_constructed_ast(ast, seed)
            serialized = serialize(mutated, validate=False)
            result = serialized.encode("utf-8")
            if len(result) <= max_size:
                return atheris.Mutate(result, max_size)
    except KeyboardInterrupt:
        _state.status = "stopped"
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return atheris.Mutate(data, max_size)
