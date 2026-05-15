# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 7: UNHASHABLE ARGUMENT HANDLING
# ============================================================================


class TestUnhashableHandling:
    """Test fail-closed handling for arguments that cannot be keyed.

    Covers three rejection mechanisms:
    1. Unknown type in _make_hashable (case _ branch)
    2. Python's hash() raising TypeError
    3. RecursionError from circular references
    In all cases: the cache rejects the operation and records one
    ``unhashable_skips`` integrity counter increment.
    """

    def test_get_with_unknown_type_raises_key_contract_error(self) -> None:
        """get() rejects unknown-type args and increments unhashable_skips.

        UnknownType is not recognized by the canonical key encoder, so the cache
        raises ``CacheKeySerializationError`` instead of pretending the lookup
        was an ordinary miss.
        """
        cache = IntegrityCache()

        class UnknownType:
            pass

        args: dict[str, object] = {"data": UnknownType()}
        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", args, None, "en", use_isolating=True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1
        assert cache.misses == 0
        assert cache.hits == 0

    def test_put_with_unhashable_hash_raises_key_contract_error(self) -> None:
        """put() rejects arg values that cannot be encoded into the cache key."""
        cache = IntegrityCache()

        class CustomObject:
            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "unhashable"
                raise TypeError(msg)

        args: dict[str, object] = {"obj": CustomObject()}
        with pytest.raises(CacheKeySerializationError):
            cache.put(
                "msg",
                args,
                None,
                "en",
                use_isolating=True,
                formatted="result",
                errors=(),
            )  # type: ignore[arg-type]
        assert cache.size == 0
        assert cache.unhashable_skips == 1

    def test_unhashable_custom_object_in_get_raises(self) -> None:
        """Custom unhashable objects in get() args are rejected explicitly."""
        cache = IntegrityCache(maxsize=100)

        class UnhashableClass:
            def __init__(self) -> None:
                self.data = [1, 2, 3]

            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        custom_args: dict[str, object] = {"custom": UnhashableClass()}
        with pytest.raises(CacheKeySerializationError):
            cache.get("msg-id", custom_args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1

    def test_unhashable_skips_not_incremented_for_convertible_types(self) -> None:
        """unhashable_skips only counts truly unhashable objects; lists/dicts do not."""
        cache = IntegrityCache(maxsize=100)
        assert cache.unhashable_skips == 0

        cache.get("msg1", {"list": [1]}, None, "en-US", use_isolating=True)
        assert cache.unhashable_skips == 0  # Lists are convertible, not skipped

        cache.put("msg2", {"dict": {}}, None, "en-US", use_isolating=True, formatted="result", errors=())
        assert cache.unhashable_skips == 0  # Dicts are convertible, not skipped

    def test_unhashable_skips_preserved_on_clear(self) -> None:
        """clear() does not reset unhashable_skips; counter is cumulative."""
        cache = IntegrityCache(maxsize=100)

        class UnhashableClass:
            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", {"obj": UnhashableClass()}, None, "en-US", use_isolating=True)  # type: ignore[dict-item]
        assert cache.unhashable_skips == 1
        # clear() removes entries but preserves cumulative observability metrics.
        cache.clear()
        assert cache.unhashable_skips == 1

    def test_get_stats_includes_unhashable_skips(self) -> None:
        """get_stats() reflects unhashable bypasses in unhashable_skips, not misses.

        Unhashable args bypass the cache entirely; no key lookup occurs.
        misses counts only true cache misses (key looked up, not found).
        """
        cache = IntegrityCache(maxsize=100)

        class UnhashableClass:
            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", {"obj": UnhashableClass()}, None, "en-US", use_isolating=True)  # type: ignore[dict-item]
        stats = cache.get_stats()
        assert "unhashable_skips" in stats
        assert stats["unhashable_skips"] == 1
        assert stats["misses"] == 0

    def test_hashable_args_do_not_increment_unhashable_skips(self) -> None:
        """Fully hashable primitive args never increment unhashable_skips."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, FluentValue] = {"str": "value", "int": 42, "decimal": Decimal("3.14")}
        cache.get("msg1", args, None, "en-US", use_isolating=True)
        cache.put("msg2", args, None, "en-US", use_isolating=True, formatted="result", errors=())
        assert cache.unhashable_skips == 0

    def test_put_with_circular_reference_raises(self) -> None:
        """Circular reference in args raises and increments unhashable_skips."""
        cache = IntegrityCache(maxsize=100)
        circular: dict[str, object] = {}
        circular["self"] = circular  # Circular reference
        assert cache.unhashable_skips == 0
        with pytest.raises(CacheKeySerializationError):
            cache.put(
                message_id="test",
                args=circular,  # type: ignore[arg-type]
                attribute=None,
                locale_code="en",
                use_isolating=True,
                formatted="output",
                errors=(),
            )
        assert cache.unhashable_skips == 1
        assert len(cache) == 0

    def test_put_with_nested_circular_reference_raises(self) -> None:
        """Nested circular reference also triggers explicit rejection."""
        cache = IntegrityCache(maxsize=50)
        nested: dict[str, object] = {"level1": {}}
        nested["level1"]["back"] = nested  # type: ignore[index]
        initial_skips = cache.unhashable_skips
        with pytest.raises(CacheKeySerializationError):
            cache.put(
                message_id="nested_test",
                args=nested,  # type: ignore[arg-type]
                attribute=None,
                locale_code="lv",
                use_isolating=True,
                formatted="result",
                errors=(),
            )
        assert cache.unhashable_skips == initial_skips + 1
        assert len(cache) == 0

    def test_put_with_custom_unhashable_in_args_dict_raises(self) -> None:
        """Custom unhashable object as a dict value raises fail-closed."""
        cache = IntegrityCache(maxsize=100)

        class UnhashableObject:
            __hash__ = None  # type: ignore[assignment]

        unhashable_args = {"obj": UnhashableObject()}
        initial_skips = cache.unhashable_skips
        with pytest.raises(CacheKeySerializationError):
            cache.put(
                message_id="custom_obj",
                args=unhashable_args,  # type: ignore[arg-type]
                attribute="attr",
                locale_code="en_US",
                use_isolating=True,
                formatted="value",
                errors=(),
            )
        assert cache.unhashable_skips == initial_skips + 1
        assert len(cache) == 0
