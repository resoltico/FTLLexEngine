"""Canonical serialization for cache keys and keyed fingerprints.

The cache owns one versioned binary encoding for lookup keys so that:

- entry key binding and debug fingerprints cannot drift independently;
- hash inputs are explicit data structures rather than ``str(key)`` display
  strings;
- future format changes can bump one codec version consciously.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from ftllexengine.core.value_types import FluentNumber

if TYPE_CHECKING:
    from .cache_types import HashableValue, _CacheKey

__all__ = [
    "compute_debug_key_fingerprint",
    "compute_key_binding_digest",
    "encode_cache_key",
]

_CACHE_KEY_CODEC_VERSION: bytes = b"FTLLexEngineCacheKey\x01"


def _encode_int(value: int) -> bytes:
    """Encode one arbitrary-precision Python integer canonically.

    Premise:
        ``FluentValue`` accepts Python ``int``, whose precision is unbounded.

    Reason:
        The cache key codec must preserve that contract instead of silently
        truncating to 64-bit integers or crashing on large values. A sign byte
        plus a length-prefixed magnitude gives one canonical binary encoding for
        every integer representable by Python.
    """
    magnitude = abs(value)
    magnitude_bytes = magnitude.to_bytes(
        max(1, (magnitude.bit_length() + 7) // 8),
        "big",
    )
    sign_byte = b"\x01" if value < 0 else b"\x00"
    return sign_byte + len(magnitude_bytes).to_bytes(4, "big") + magnitude_bytes


def _encode_bool(*, value: bool) -> bytes:
    return b"\x01" if value else b"\x00"


def _encode_text(value: str) -> bytes:
    encoded = value.encode("utf-8", errors="surrogatepass")
    return len(encoded).to_bytes(4, "big") + encoded


def _encode_decimal(value: Decimal) -> bytes:
    if value.is_nan():
        return b"D" + _encode_text("NaN")
    return b"D" + _encode_text(str(value))


def _encode_datetime(value: datetime) -> bytes:
    tz_key = str(value.tzinfo) if value.tzinfo is not None else "__naive__"
    return b"T" + _encode_text(value.isoformat()) + _encode_text(tz_key)


def _encode_fluent_number(value: FluentNumber) -> bytes:
    return (
        b"F"
        + _encode_text(type(value.value).__name__)
        + _encode_hashable_value(cast("HashableValue", value.value))
        + _encode_text(value.formatted)
        + _encode_hashable_value(cast("HashableValue", value.precision))
    )


def _encode_tuple(value: tuple[HashableValue, ...]) -> bytes:
    return (
        b"Q"
        + len(value).to_bytes(4, "big")
        + b"".join(_encode_hashable_value(item) for item in value)
    )


def _encode_frozenset(value: frozenset[HashableValue]) -> bytes:
    encoded_items = sorted(_encode_hashable_value(item) for item in value)
    return b"R" + len(encoded_items).to_bytes(4, "big") + b"".join(encoded_items)


def _encode_basic_scalar_value(value: HashableValue) -> bytes | None:
    if value is None:
        return b"N"
    if isinstance(value, str):
        return b"S" + _encode_text(value)
    if isinstance(value, bool):
        return b"B" + _encode_bool(value=value)
    if isinstance(value, int):
        return b"I" + _encode_int(value)
    return None


def _encode_extended_scalar_value(value: HashableValue) -> bytes | None:
    if isinstance(value, Decimal):
        return _encode_decimal(value)
    if isinstance(value, datetime):
        return _encode_datetime(value)
    if isinstance(value, date):
        return b"d" + _encode_text(value.isoformat())
    if isinstance(value, FluentNumber):
        return _encode_fluent_number(value)
    return None


def _encode_scalar_value(value: HashableValue) -> bytes | None:
    encoded_basic = _encode_basic_scalar_value(value)
    if encoded_basic is not None:
        return encoded_basic
    return _encode_extended_scalar_value(value)


def _encode_collection_value(value: HashableValue) -> bytes | None:
    if isinstance(value, tuple):
        return _encode_tuple(value)
    if isinstance(value, frozenset):
        return _encode_frozenset(value)
    return None


def _encode_hashable_value(value: HashableValue) -> bytes:
    encoded_scalar = _encode_scalar_value(value)
    if encoded_scalar is not None:
        return encoded_scalar

    encoded_collection = _encode_collection_value(value)
    if encoded_collection is not None:
        return encoded_collection

    msg = f"Unsupported cache key value type: {type(value).__name__}"
    raise TypeError(msg)


def encode_cache_key(key: _CacheKey) -> bytes:
    """Return the one canonical binary encoding for one cache key.

    Premise:
        Cache-key hashing is a contract fact shared across integrity checks,
        debug logs, and any external correlation tooling.

    Reason:
        One versioned encoder prevents accidental drift between the key binding
        digest stored inside entries and the keyed fingerprints exposed through
        observability surfaces.
    """
    message_id, args_tuple, attribute, locale_code, use_isolating, function_generation = key

    encoded_args = bytearray()
    encoded_args.extend(len(args_tuple).to_bytes(4, "big"))
    for arg_name, arg_value in args_tuple:
        encoded_args.extend(_encode_text(arg_name))
        encoded_args.extend(_encode_hashable_value(arg_value))

    return b"".join(
        (
            _CACHE_KEY_CODEC_VERSION,
            _encode_text(message_id),
            bytes(encoded_args),
            b"\x01" + _encode_text(attribute) if attribute is not None else b"\x00",
            _encode_text(locale_code),
            _encode_bool(value=use_isolating),
            _encode_int(function_generation),
        )
    )


def compute_key_binding_digest(key: _CacheKey) -> bytes:
    """Compute the internal key-binding digest stored in cache entries."""
    return hashlib.blake2b(encode_cache_key(key), digest_size=16).digest()


def compute_debug_key_fingerprint(key: _CacheKey, *, secret: bytes) -> str:
    """Compute the keyed fingerprint exposed to debug and event surfaces."""
    return hashlib.blake2b(
        encode_cache_key(key),
        key=secret,
        digest_size=12,
    ).hexdigest()
