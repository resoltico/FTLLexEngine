"""Hypothesis strategies for validation domain testing.

Provides event-emitting strategies for generating FTL validation scenarios
covering all six validation passes in validate_resource() and the semantic
checks in SemanticValidator.

Event-Emitting Strategies (HypoFuzz-Optimized):
    - val_scenario={variant}: FTL source scenario for validate_resource()
    - val_entry_kind={kind}: Entry type composition in generated FTL
    - val_semantic_variant={variant}: AST scenario for SemanticValidator
    - val_ref_kind={kind}: Reference type in dependency graph scenarios

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import event
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
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

__all__ = [
    "semantic_validation_resources",
    "validation_resource_sources",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FTL_IDENT_ALPHABET = st.characters(
    whitelist_categories=("Ll", "Lu"),
    whitelist_characters="-",
    blacklist_characters="-",
)
_ftl_identifiers = st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True)


def _make_identifier(name: str) -> Identifier:
    return Identifier(name)


def _text_pattern(text: str) -> Pattern:
    return Pattern(elements=(TextElement(value=text),))


def _ref_pattern_message(ref_name: str) -> Pattern:
    return Pattern(
        elements=(Placeable(expression=MessageReference(id=Identifier(ref_name))),)
    )


def _ref_pattern_term(ref_name: str) -> Pattern:
    return Pattern(
        elements=(Placeable(expression=TermReference(id=Identifier(ref_name))),)
    )


# ---------------------------------------------------------------------------
# validate_resource() scenario strategies
# ---------------------------------------------------------------------------


@st.composite
def validation_resource_sources(draw: st.DrawFn) -> str:  # noqa: PLR0911,PLR0912,PLR0915
    """Generate FTL source strings covering all validate_resource() passes.

    Generates semantically diverse FTL content across six categories,
    targeting all validation passes: syntax, structure, references,
    cycles, chain depth, and semantic validation.

    Events emitted:
    - val_scenario={variant}: Which validation scenario was generated
    - val_entry_kind={kind}: Entry composition in the generated FTL
    """
    scenario = draw(
        st.sampled_from([
            "valid",
            "syntax_error",
            "duplicate_id",
            "undefined_ref",
            "circular",
            "deep_chain",
            "mixed_issues",
        ])
    )
    event(f"val_scenario={scenario}")

    match scenario:
        case "valid":
            # Valid FTL with messages and optional terms
            entry_kind = draw(st.sampled_from(["msg_only", "term_only", "mixed"]))
            event(f"val_entry_kind={entry_kind}")
            names = draw(
                st.lists(
                    _ftl_identifiers,
                    min_size=1,
                    max_size=5,
                    unique=True,
                )
            )
            lines: list[str] = []
            match entry_kind:
                case "msg_only":
                    for name in names:
                        lines.append(f"{name} = Value for {name}")
                case "term_only":
                    for name in names:
                        lines.append(f"-{name} = Term {name}")
                case _:  # mixed
                    for i, name in enumerate(names):
                        if i % 2 == 0:
                            lines.append(f"{name} = Value {name}")
                        else:
                            lines.append(f"-{name} = Term {name}")
            return "\n".join(lines)

        case "syntax_error":
            event("val_entry_kind=junk")
            # Raw text without '=' that the parser treats as Junk
            return draw(
                st.text(
                    alphabet=st.characters(
                        blacklist_characters="=\r\n\t",
                        blacklist_categories=("Cc",),  # type: ignore[arg-type]
                    ),
                    min_size=3,
                    max_size=30,
                ).filter(lambda s: s.strip() and not s.strip().startswith("#"))
            )

        case "duplicate_id":
            event("val_entry_kind=duplicate")
            name = draw(_ftl_identifiers)
            count = draw(st.integers(min_value=2, max_value=4))
            lines = [f"{name} = Value {i}" for i in range(count)]
            return "\n".join(lines)

        case "undefined_ref":
            entry_kind = draw(st.sampled_from(["msg_ref", "term_ref", "both"]))
            event(f"val_entry_kind={entry_kind}")
            msg_name = draw(_ftl_identifiers)
            ref_name = draw(_ftl_identifiers.filter(lambda s: s != msg_name))
            match entry_kind:
                case "msg_ref":
                    return f"{msg_name} = {{ {ref_name} }}"
                case "term_ref":
                    return f"{msg_name} = {{ -{ref_name} }}"
                case _:  # both
                    ref2 = draw(_ftl_identifiers.filter(
                        lambda s: s not in (msg_name, ref_name)
                    ))
                    return (
                        f"{msg_name} = {{ {ref_name} }} and {{ -{ref2} }}"
                    )

        case "circular":
            entry_kind = draw(st.sampled_from(["msg_cycle", "term_cycle", "cross_cycle"]))
            event(f"val_entry_kind={entry_kind}")
            a = draw(_ftl_identifiers)
            b = draw(_ftl_identifiers.filter(lambda s: s != a))
            match entry_kind:
                case "msg_cycle":
                    return f"{a} = {{ {b} }}\n{b} = {{ {a} }}"
                case "term_cycle":
                    return f"-{a} = {{ -{b} }}\n-{b} = {{ -{a} }}"
                case _:  # cross_cycle: msg -> term -> msg
                    return f"{a} = {{ -{b} }}\n-{b} = {{ {a} }}"

        case "deep_chain":
            event("val_entry_kind=chain")
            from ftllexengine.constants import MAX_DEPTH  # noqa: PLC0415

            depth = draw(
                st.integers(min_value=MAX_DEPTH + 1, max_value=MAX_DEPTH + 5)
            )
            # Build chain: msg0 -> msg1 -> ... -> msg_depth-1 (no value)
            lines = ["msg0 = Base value"]
            for i in range(1, depth):
                lines.append(f"msg{i} = {{ msg{i - 1} }}")
            return "\n".join(lines)

        case _:  # mixed_issues
            event("val_entry_kind=mixed")
            a = draw(_ftl_identifiers)
            b = draw(_ftl_identifiers.filter(lambda s: s != a))
            parts = [
                "# Valid entry",
                f"{a} = Good value",
                "# Duplicate",
                f"{a} = Second value",
                "# Undefined reference",
                f"{b} = {{ undefined-missing }}",
                "# Circular",
                "c1 = { c2 }",
                "c2 = { c1 }",
            ]
            return "\n".join(parts)


# ---------------------------------------------------------------------------
# SemanticValidator scenario strategies
# ---------------------------------------------------------------------------


@st.composite
def semantic_validation_resources(draw: st.DrawFn) -> Resource:  # noqa: PLR0911
    """Generate AST Resource instances for SemanticValidator testing.

    Covers all semantic check paths in SemanticValidator: term without
    value, select expression variants, duplicate named arguments, and
    term reference positional argument warnings.

    Events emitted:
    - val_semantic_variant={variant}: Which semantic scenario was generated
    """
    variant = draw(
        st.sampled_from([
            "valid_message",
            "valid_term",
            "valid_select",
            "select_duplicate_key_numeric",
            "select_duplicate_key_identifier",
            "function_dup_named_arg",
            "term_positional_args",
            "term_named_args_only",
            "nested_placeable",
            "empty_resource",
        ])
    )
    event(f"val_semantic_variant={variant}")

    match variant:
        case "valid_message":
            msg = Message(
                id=Identifier("msg"),
                value=_text_pattern("Simple message"),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case "valid_term":
            term = Term(
                id=Identifier("brand"),
                value=_text_pattern("Acme Corp"),
                attributes=(),
            )
            return Resource(entries=(term,))

        case "valid_select":
            selector = VariableReference(id=Identifier("count"))
            variants: tuple[Variant, ...] = (
                Variant(
                    key=Identifier("one"),
                    value=_text_pattern("One item"),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=_text_pattern("Many items"),
                    default=True,
                ),
            )
            select = SelectExpression(selector=selector, variants=variants)
            msg = Message(
                id=Identifier("count-msg"),
                value=Pattern(elements=(Placeable(expression=select),)),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case "select_duplicate_key_numeric":
            # Duplicate numeric variant keys (e.g., [1] and [1.0])
            selector = VariableReference(id=Identifier("n"))
            # Use values that Decimal.normalize() maps to the same form
            raw_val = draw(
                st.sampled_from(["1", "1.0", "1.00", "2", "2.0"])
            )
            variants = (
                Variant(
                    key=NumberLiteral(value=Decimal(raw_val), raw=raw_val),
                    value=_text_pattern("First"),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal(raw_val), raw=raw_val),
                    value=_text_pattern("Duplicate"),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=_text_pattern("Default"),
                    default=True,
                ),
            )
            select = SelectExpression(selector=selector, variants=variants)
            msg = Message(
                id=Identifier("dup-numeric"),
                value=Pattern(elements=(Placeable(expression=select),)),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case "select_duplicate_key_identifier":
            # Duplicate identifier variant keys
            selector = VariableReference(id=Identifier("gender"))
            key_name = draw(st.sampled_from(["male", "female", "one", "few"]))
            variants = (
                Variant(
                    key=Identifier(key_name),
                    value=_text_pattern("First"),
                    default=False,
                ),
                Variant(
                    key=Identifier(key_name),
                    value=_text_pattern("Duplicate"),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=_text_pattern("Default"),
                    default=True,
                ),
            )
            select = SelectExpression(selector=selector, variants=variants)
            msg = Message(
                id=Identifier("dup-ident"),
                value=Pattern(elements=(Placeable(expression=select),)),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case "function_dup_named_arg":
            # Function with duplicate named argument names
            arg_name = draw(st.sampled_from(["style", "currency", "unit", "x"]))
            dup_named_args = (
                NamedArgument(
                    name=Identifier(arg_name),
                    value=StringLiteral(value="first"),
                ),
                NamedArgument(
                    name=Identifier(arg_name),
                    value=StringLiteral(value="second"),
                ),
            )
            func_ref = FunctionReference(
                id=Identifier("NUMBER"),
                arguments=CallArguments(
                    positional=(VariableReference(id=Identifier("count")),),
                    named=dup_named_args,
                ),
            )
            msg = Message(
                id=Identifier("dup-named"),
                value=Pattern(elements=(Placeable(expression=func_ref),)),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case "term_positional_args":
            # Term reference with positional arguments (invalid per spec)
            term_ref = TermReference(
                id=Identifier("brand"),
                attribute=None,
                arguments=CallArguments(
                    positional=(VariableReference(id=Identifier("case")),),
                    named=(),
                ),
            )
            msg = Message(
                id=Identifier("msg"),
                value=Pattern(elements=(Placeable(expression=term_ref),)),
                attributes=(),
            )
            term = Term(
                id=Identifier("brand"),
                value=_text_pattern("Acme"),
                attributes=(),
            )
            return Resource(entries=(msg, term))

        case "term_named_args_only":
            # Term reference with ONLY named arguments (valid per spec)
            term_ref = TermReference(
                id=Identifier("brand"),
                attribute=None,
                arguments=CallArguments(
                    positional=(),
                    named=(
                        NamedArgument(
                            name=Identifier("case"),
                            value=StringLiteral(value="nominative"),
                        ),
                    ),
                ),
            )
            msg = Message(
                id=Identifier("msg"),
                value=Pattern(elements=(Placeable(expression=term_ref),)),
                attributes=(),
            )
            term = Term(
                id=Identifier("brand"),
                value=_text_pattern("Acme"),
                attributes=(),
            )
            return Resource(entries=(msg, term))

        case "nested_placeable":
            # Nested placeables to exercise depth guard in validator
            depth = draw(st.integers(min_value=1, max_value=3))
            inner: Placeable = Placeable(
                expression=StringLiteral(value="inner")
            )
            for _ in range(depth - 1):
                inner = Placeable(expression=inner)
            msg = Message(
                id=Identifier("nested"),
                value=Pattern(elements=(inner,)),
                attributes=(),
            )
            return Resource(entries=(msg,))

        case _:  # empty_resource
            return Resource(entries=())
