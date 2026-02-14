"""Hypothesis strategies for FluentLocalization property-based testing.

Provides reusable strategies for generating localization test data:
- Locale chains with fallback configurations
- FTL resource sets with controlled message overlap
- ResourceLoader implementations for testing
- Message ID sets for multi-locale scenarios

Event-Emitting Strategies (HypoFuzz-Optimized):
- locale_chains: Emits locale_chain_size=N
- ftl_resource_sets: Emits resource_overlap=full|partial|disjoint
- resource_loaders: Emits loader_type=dict|failing|empty

Python 3.13+.
"""

from __future__ import annotations

import string
from typing import TYPE_CHECKING

from hypothesis import event
from hypothesis import strategies as st

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hypothesis.strategies import DrawFn, SearchStrategy

# Valid locale codes for FluentLocalization (subset of real BCP 47).
# Uses underscores (Babel-compatible) and hyphens (Fluent-compatible).
_LOCALE_POOL = [
    "en", "en_US", "en_GB",
    "de", "de_DE", "de_AT",
    "fr", "fr_FR", "fr_CA",
    "es", "es_ES", "es_MX",
    "lv", "lv_LV",
    "lt", "lt_LT",
    "et", "et_EE",
    "ja", "ko", "zh",
    "pt", "pt_BR",
    "it", "nl", "ru",
    "ar", "pl", "sv",
]

# FTL message ID alphabet per Fluent spec: [a-zA-Z][a-zA-Z0-9_-]*
_ID_FIRST_CHARS = string.ascii_letters
_ID_REST_CHARS = string.ascii_letters + string.digits + "-_"


@st.composite
def message_ids(draw: DrawFn) -> str:
    """Generate valid FTL message identifiers per Fluent spec.

    Per spec, identifiers must match: [a-zA-Z][a-zA-Z0-9_-]*

    Events emitted:
    - l10n_msg_id_len=short|medium|long
    """
    first = draw(st.sampled_from(list(_ID_FIRST_CHARS)))
    rest_len = draw(st.integers(min_value=0, max_value=30))
    rest = draw(st.text(
        alphabet=_ID_REST_CHARS, min_size=rest_len, max_size=rest_len,
    ))
    result = first + rest
    length_class = (
        "short" if len(result) <= 5
        else "medium" if len(result) <= 15
        else "long"
    )
    event(f"l10n_msg_id_len={length_class}")
    return result


@st.composite
def locale_chains(
    draw: DrawFn,
    min_size: int = 1,
    max_size: int = 5,
) -> list[str]:
    """Generate locale fallback chains (unique, ordered).

    Events emitted:
    - l10n_chain_size=N
    """
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    locales = draw(
        st.lists(
            st.sampled_from(_LOCALE_POOL),
            min_size=size,
            max_size=size,
            unique=True,
        )
    )
    event(f"l10n_chain_size={len(locales)}")
    return locales


@st.composite
def ftl_resource_sets(
    draw: DrawFn,
    locale_chain: list[str] | None = None,
    msg_count: int = 3,
) -> dict[str, str]:
    """Generate FTL resource content for a locale chain.

    Produces a dict mapping locale -> FTL source, with controlled
    message overlap across locales. Primary locale always has all
    messages; fallback locales have partial coverage.

    Args:
        locale_chain: Locale codes to generate resources for.
                     If None, draws a chain of 2-4 locales.
        msg_count: Number of unique message IDs to generate.

    Events emitted:
    - l10n_resource_overlap=full|partial|disjoint
    """
    if locale_chain is None:
        locale_chain = draw(locale_chains(min_size=2, max_size=4))

    # Generate unique message IDs
    ids = [
        draw(message_ids())
        for _ in range(msg_count)
    ]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_ids: list[str] = []
    for mid in ids:
        if mid not in seen:
            seen.add(mid)
            unique_ids.append(mid)
    if not unique_ids:
        unique_ids = ["fallback-msg"]

    resources: dict[str, str] = {}

    # Determine overlap pattern
    overlap = draw(st.sampled_from(["full", "partial", "disjoint"]))
    event(f"l10n_resource_overlap={overlap}")

    match overlap:
        case "full":
            # All locales have all messages
            for locale in locale_chain:
                lines = [
                    f"{mid} = {locale}:{mid}" for mid in unique_ids
                ]
                resources[locale] = "\n".join(lines) + "\n"
        case "partial":
            # Primary has all, fallbacks have subsets
            for idx, locale in enumerate(locale_chain):
                if idx == 0:
                    msgs_for_locale = unique_ids
                else:
                    # Each fallback gets fewer messages
                    cutoff = max(1, len(unique_ids) - idx)
                    msgs_for_locale = unique_ids[:cutoff]
                lines = [
                    f"{mid} = {locale}:{mid}" for mid in msgs_for_locale
                ]
                resources[locale] = "\n".join(lines) + "\n"
        case "disjoint":
            # Each locale has only its own message(s)
            for idx, locale in enumerate(locale_chain):
                msg_idx = idx % len(unique_ids)
                mid = unique_ids[msg_idx]
                resources[locale] = f"{mid} = {locale}:{mid}\n"

    return resources


@st.composite
def ftl_message_values(draw: DrawFn) -> str:
    """Generate safe FTL message values (no special syntax chars).

    Events emitted:
    - l10n_value_type=simple|with_variable|numeric
    """
    value_type = draw(st.sampled_from(
        ["simple", "with_variable", "numeric"]
    ))
    event(f"l10n_value_type={value_type}")
    match value_type:
        case "simple":
            return draw(st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "Zs"),
                    blacklist_characters="\n\r{}",
                ),
                min_size=1, max_size=50,
            ))
        case "with_variable":
            var = draw(st.text(
                alphabet=_ID_REST_CHARS,
                min_size=1, max_size=10,
            ))
            # Ensure first char is a letter
            if var[0] not in _ID_FIRST_CHARS:
                var = "x" + var
            return "{ $" + var + " }"
        case "numeric":
            n = draw(st.integers(min_value=-999999, max_value=999999))
            return str(n)
        case _:
            return "default"


@st.composite
def ftl_messages_with_attributes(draw: DrawFn) -> str:
    """Generate FTL message with optional attributes.

    Events emitted:
    - l10n_attr_count=0|1|2|3
    """
    mid = draw(message_ids())
    value = draw(st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
        ),
        min_size=1, max_size=20,
    ))
    attr_count = draw(st.integers(min_value=0, max_value=3))
    event(f"l10n_attr_count={attr_count}")

    lines = [f"{mid} = {value}"]
    for i in range(attr_count):
        attr_name = f"attr{i}"
        attr_val = draw(st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
            ),
            min_size=1, max_size=15,
        ))
        lines.append(f"    .{attr_name} = {attr_val}")

    return "\n".join(lines) + "\n"


@st.composite
def ftl_messages_with_terms(draw: DrawFn) -> str:
    """Generate FTL resource with messages and terms.

    Events emitted:
    - l10n_term_count=1|2|3
    """
    term_count = draw(st.integers(min_value=1, max_value=3))
    event(f"l10n_term_count={term_count}")

    lines: list[str] = []
    term_ids: list[str] = []
    for i in range(term_count):
        tid = f"term{i}"
        term_ids.append(tid)
        val = draw(st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1, max_size=10,
        ))
        lines.append(f"-{tid} = {val}")

    # Add a message referencing a term
    ref_term = draw(st.sampled_from(term_ids))
    lines.append(f"msg-with-term = Uses {{ -{ref_term} }}")

    return "\n".join(lines) + "\n"


class DictResourceLoader:
    """In-memory resource loader for testing.

    Implements ResourceLoader protocol using a dict of dicts.
    """

    def __init__(self, resources: Mapping[str, Mapping[str, str]]) -> None:
        self._resources = resources

    def load(self, locale: str, resource_id: str) -> str:
        """Load FTL resource from in-memory dict.

        Raises:
            FileNotFoundError: If locale/resource_id not in dict.
        """
        if locale not in self._resources:
            msg = f"Locale '{locale}' not found"
            raise FileNotFoundError(msg)
        locale_resources = self._resources[locale]
        if resource_id not in locale_resources:
            msg = f"Resource '{resource_id}' not found for '{locale}'"
            raise FileNotFoundError(msg)
        return locale_resources[resource_id]


class FailingResourceLoader:
    """Resource loader that raises errors for testing error paths."""

    def __init__(
        self,
        error_type: type[Exception] = OSError,
        message: str = "Simulated load failure",
    ) -> None:
        self._error_type = error_type
        self._message = message

    def load(self, locale: str, resource_id: str) -> str:  # noqa: ARG002
        """Always raises the configured error type."""
        raise self._error_type(self._message)


@st.composite
def resource_loaders(
    draw: DrawFn,
    locale_chain: list[str] | None = None,
) -> tuple[
    DictResourceLoader | FailingResourceLoader,
    list[str],
    list[str],
]:
    """Generate a ResourceLoader with locale chain and resource IDs.

    Returns a tuple of (loader, locales, resource_ids).

    Events emitted:
    - l10n_loader_type=dict|failing|empty
    """
    if locale_chain is None:
        locale_chain = draw(locale_chains(min_size=1, max_size=3))

    loader_type = draw(st.sampled_from(["dict", "failing", "empty"]))
    event(f"l10n_loader_type={loader_type}")

    resource_ids = ["main.ftl"]

    match loader_type:
        case "dict":
            resources: dict[str, dict[str, str]] = {}
            for locale in locale_chain:
                resources[locale] = {
                    "main.ftl": f"msg = Hello from {locale}\n",
                }
            loader: DictResourceLoader | FailingResourceLoader = (
                DictResourceLoader(resources)
            )
        case "failing":
            loader = FailingResourceLoader()
        case "empty":
            loader = DictResourceLoader({})
        case _:
            loader = DictResourceLoader({})

    return (loader, locale_chain, resource_ids)


# Re-export convenience aliases
l10n_locale_chains: SearchStrategy[list[str]] = locale_chains()
l10n_message_ids: SearchStrategy[str] = message_ids()
