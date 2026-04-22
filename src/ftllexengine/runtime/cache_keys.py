"""Hashable-key conversion helpers for IntegrityCache."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.value_types import FluentNumber, FluentValue

if TYPE_CHECKING:
    from collections.abc import Callable

    from ftllexengine.runtime.cache_types import HashableValue, _CacheKey

__all__ = ["HASHABLE_NODE_BUDGET", "compute_key_hash", "make_hashable", "make_key"]

HASHABLE_NODE_BUDGET: int = 10_000


def _hashable_decimal(value: Decimal) -> HashableValue:
    if value.is_nan():
        return ("__decimal__", "__NaN__")
    return ("__decimal__", str(value))


def _hashable_datetime(value: datetime) -> HashableValue:
    tz_key = str(value.tzinfo) if value.tzinfo else "__naive__"
    return ("__datetime__", value.isoformat(), tz_key)


def _hashable_mapping(
    tag: str,
    value: Mapping[object, object],
    recurse: Callable[[object], HashableValue],
) -> HashableValue:
    return cast(
        "HashableValue",
        (tag, tuple(sorted((key, recurse(item)) for key, item in value.items()))),
    )


def _hashable_sequence(
    tag: str,
    value: Sequence[object],
    recurse: Callable[[object], HashableValue],
) -> HashableValue:
    return (tag, tuple(recurse(item) for item in value))


def _hashable_set(
    tag: str,
    value: set[object] | frozenset[object],
    recurse: Callable[[object], HashableValue],
) -> HashableValue:
    return (tag, frozenset(recurse(item) for item in value))


def _hashable_scalar_value(
    value: object, recurse: Callable[[object], HashableValue]
) -> HashableValue | None:
    result: HashableValue | None = None
    match value:
        case str() | None:
            result = value
        case bool():
            result = ("__bool__", value)
        case int():
            result = ("__int__", value)
        case Decimal():
            result = _hashable_decimal(value)
        case datetime():
            result = _hashable_datetime(value)
        case date():
            result = ("__date__", value.isoformat())
        case FluentNumber():
            result = (
                "__fluentnumber__",
                type(value.value).__name__,
                recurse(value.value),
                value.formatted,
                value.precision,
            )
        case _:
            pass
    return result


def _hashable_container_value(
    value: object,
    recurse: Callable[[object], HashableValue],
) -> HashableValue | None:
    match value:
        case list():
            return _hashable_sequence("__list__", value, recurse)
        case tuple():
            return _hashable_sequence("__tuple__", value, recurse)
        case dict():
            return _hashable_mapping("__dict__", value, recurse)
        case set():
            return _hashable_set("__set__", value, recurse)
        case frozenset():
            return _hashable_set("__frozenset__", value, recurse)
        case _:
            return None


def make_hashable(value: object, depth: int = MAX_DEPTH) -> HashableValue:
    """Convert potentially unhashable values into a stable hashable form."""
    node_count = 0

    def go(current: object, remaining_depth: int) -> HashableValue:
        nonlocal node_count
        node_count += 1
        if node_count > HASHABLE_NODE_BUDGET:
            msg = "Node budget exceeded in cache key conversion (possible DAG expansion attack)"
            raise TypeError(msg)
        if remaining_depth <= 0:
            msg = "Maximum nesting depth exceeded in cache key conversion"
            raise TypeError(msg)
        if current is None:
            return None

        def recurse(item: object) -> HashableValue:
            return go(item, remaining_depth - 1)

        known_value = _hashable_scalar_value(current, recurse)
        if known_value is not None:
            return known_value

        known_value = _hashable_container_value(current, recurse)
        if known_value is not None:
            return known_value
        if isinstance(current, Mapping):
            return _hashable_mapping("__mapping__", current, recurse)
        if isinstance(current, Sequence):
            return _hashable_sequence("__seq__", current, recurse)

        msg = f"Unknown type in cache key: {type(current).__name__}"
        raise TypeError(msg)

    return go(value, depth)


def compute_key_hash(key: _CacheKey) -> bytes:
    """Compute the 8-byte BLAKE2b key binding used by cache entries."""
    return hashlib.blake2b(
        str(key).encode("utf-8", errors="surrogatepass"),
        digest_size=8,
    ).digest()


def make_key(
    message_id: str,
    args: Mapping[str, FluentValue] | None,
    attribute: str | None,
    locale_code: str,
    *,
    use_isolating: bool,
) -> _CacheKey | None:
    """Create an immutable cache key tuple from formatting arguments."""
    if args is None:
        args_tuple: tuple[tuple[str, HashableValue], ...] = ()
    else:
        try:
            items: list[tuple[str, HashableValue]] = []
            for key, value in args.items():
                items.append((key, make_hashable(value)))
            args_tuple = tuple(sorted(items))
            hash(args_tuple)
        except (TypeError, RecursionError):
            return None

    return (message_id, args_tuple, attribute, locale_code, use_isolating)
