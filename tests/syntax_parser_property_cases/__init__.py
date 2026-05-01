"""Hypothesis property-based tests for Fluent parser invariants and robustness."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Comment, Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer
from tests.strategies import ftl_identifiers as shared_ftl_identifiers
from tests.strategies import ftl_simple_text

ftl_identifiers = shared_ftl_identifiers()
variable_names = ftl_identifiers
safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=["Cc"],
        blacklist_characters=["{", "}", "[", "]", "$", "-", "*", ".", "#", "\n"],
    ),
    min_size=1,
).filter(str.strip)
numbers = st.integers()
decimals = st.decimals(allow_nan=False, allow_infinity=False)
attribute_names = ftl_identifiers
variant_keys = st.from_regex(r"[a-z][a-z0-9]*", fullmatch=True)

__all__ = [
    "Comment", "Decimal", "FluentParserV1", "FluentSerializer", "Junk", "Message",
    "Resource", "Term", "assume", "attribute_names", "decimals", "event",
    "example", "ftl_identifiers", "ftl_simple_text", "given", "numbers", "safe_text",
    "settings", "shared_ftl_identifiers", "st", "variable_names", "variant_keys",
]
