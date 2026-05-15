# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 4: MAKE KEY INTEGRATION
# ============================================================================


class TestMakeKey:
    """Test _make_key integration with _make_hashable.

    _make_key builds a cache key tuple from (message_id, args, attribute,
    locale_code, use_isolating, function_generation). Returns None on hashing
    failure so the cache layer can raise one typed boundary error instead of
    performing a partial lookup.
    """

    def test_make_key_with_none_args(self) -> None:
        """_make_key with None args returns key with empty tuple for args component."""
        key = IntegrityCache._make_key("msg-id", None, None, "en-US", use_isolating=True)
        assert key is not None
        assert key == ("msg-id", (), None, "en-US", True, 0)

    def test_make_key_with_simple_args(self) -> None:
        """_make_key handles simple string/int arguments."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={"name": "Alice", "count": 42},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_nested_args(self) -> None:
        """_make_key handles nested list arguments via _make_hashable."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={"items": [1, 2, 3]},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_all_fluent_value_types(self) -> None:
        """_make_key accepts all valid FluentValue types."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={
                "string": "hello",
                "int": 42,
                "decimal": Decimal("3.14"),
                "decimal2": Decimal("99.99"),
                "datetime": datetime(2024, 1, 1, tzinfo=UTC),
                "date": date(2024, 1, 1),
                "fluent_number": FluentNumber(value=100, formatted="100"),
            },
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_deeply_nested_returns_none(self) -> None:
        """_make_key returns None for excessively nested args (graceful bypass)."""
        deep: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            deep = {"nested": deep}
        key = IntegrityCache._make_key(
            message_id="test",
            args={"deep": deep},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is None  # Cache bypass, not a crash

    def test_make_key_with_unknown_type_returns_none(self) -> None:
        """_make_key returns None for unknown types (graceful bypass)."""

        class CustomObject:
            pass

        key = IntegrityCache._make_key(
            message_id="test",
            args={"custom": CustomObject()},  # type: ignore[dict-item]
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is None

    def test_make_key_catches_recursion_error(self) -> None:
        """_make_key returns None when RecursionError occurs (circular reference)."""
        circular_list: list[object] = []
        circular_list.append(circular_list)
        args: dict[str, object] = {"data": circular_list}
        result = IntegrityCache._make_key(
            "msg", args, None, "en", use_isolating=True  # type: ignore[arg-type]
        )
        assert result is None

    def test_make_key_catches_type_error_in_hash(self) -> None:
        """_make_key returns None when TypeError occurs during hash verification."""

        class UnhashableAfterConversion:
            """Passes _make_hashable type dispatch but fails hash()."""

            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "cannot hash"
                raise TypeError(msg)

        args: dict[str, object] = {"data": UnhashableAfterConversion()}
        result = IntegrityCache._make_key(
            "msg", args, None, "en", use_isolating=True  # type: ignore[arg-type]
        )
        assert result is None
