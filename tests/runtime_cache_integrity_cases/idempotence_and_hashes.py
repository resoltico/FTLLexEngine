# mypy: ignore-errors
from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.integrity import WriteConflictError
from ftllexengine.runtime.cache import IntegrityCache

_FG = 0


def _put(
    cache: IntegrityCache,
    message_id: str,
    formatted: str,
    *,
    args: dict[str, object] | None = None,
) -> None:
    cache.put(
        message_id,
        args,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
        formatted=formatted,
        errors=(),
    )


def _get(cache: IntegrityCache, message_id: str, *, args: dict[str, object] | None = None):
    return cache.get(
        message_id,
        args,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
    )


class TestWriteOnceIdempotence:
    """Write-once mode should distinguish benign duplicate writes from conflicts."""

    def test_idempotent_duplicate_write_is_accepted(self) -> None:
        cache = IntegrityCache(write_once=True)

        _put(cache, "msg", "Hello")
        _put(cache, "msg", "Hello")

        stats = cache.get_stats()
        assert stats["idempotent_writes"] == 1
        assert stats["write_once_conflicts"] == 0
        assert _get(cache, "msg").formatted == "Hello"

    def test_conflicting_duplicate_write_raises(self) -> None:
        cache = IntegrityCache(write_once=True)

        _put(cache, "msg", "Hello")

        with pytest.raises(WriteConflictError, match="already cached"):
            _put(cache, "msg", "World")

        stats = cache.get_stats()
        assert stats["write_once_conflicts"] == 1


class TestHashableValueNormalization:
    """Canonical hashable conversion should preserve semantic distinctions."""

    def test_bool_and_int_do_not_collide(self) -> None:
        cache = IntegrityCache(maxsize=10)
        _put(cache, "msg", "bool", args={"value": True})
        _put(cache, "msg", "int", args={"value": 1})

        assert _get(cache, "msg", args={"value": True}).formatted == "bool"
        assert _get(cache, "msg", args={"value": 1}).formatted == "int"

    def test_nan_decimal_values_share_one_stable_key(self) -> None:
        cache = IntegrityCache(maxsize=10)
        first = Decimal("NaN")
        second = Decimal("NaN")

        _put(cache, "msg", "nan", args={"value": first})
        assert _get(cache, "msg", args={"value": second}).formatted == "nan"

    def test_fluent_number_is_keyed_by_value_and_formatting_metadata(self) -> None:
        cache = IntegrityCache(maxsize=10)
        left = FluentNumber(Decimal("1.20"), "1.20", precision=2)
        right = FluentNumber(Decimal("1.2"), "1.2", precision=1)

        _put(cache, "msg", "left", args={"value": left})
        _put(cache, "msg", "right", args={"value": right})

        assert _get(cache, "msg", args={"value": left}).formatted == "left"
        assert _get(cache, "msg", args={"value": right}).formatted == "right"
