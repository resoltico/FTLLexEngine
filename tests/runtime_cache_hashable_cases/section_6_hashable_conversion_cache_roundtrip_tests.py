# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 6: HASHABLE CONVERSION - CACHE ROUNDTRIP TESTS
# ============================================================================


class TestCacheHashableConversion:  # pylint: disable=too-many-public-methods
    """Test IntegrityCache automatic conversion of unhashable args to hashable keys.

    Lists, dicts, sets, and tuples are converted to hashable equivalents
    (type-tagged tuples, sorted tuples, frozensets) enabling caching for these
    types without requiring callers to pre-convert their arguments.
    """

    def test_get_with_list_value_now_cacheable(self) -> None:
        """get() with list args succeeds: lists are converted to type-tagged tuples."""
        cache = IntegrityCache(maxsize=100)
        args = {"key": [1, 2, 3]}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_dict_value_now_cacheable(self) -> None:
        """get() with nested dict args succeeds: dicts are converted to sorted tuples."""
        cache = IntegrityCache(maxsize=100)
        args = {"key": {"nested": "value"}}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_set_value_now_cacheable(self) -> None:
        """get() with set args succeeds: sets are converted to type-tagged frozensets."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, object] = {"key": {1, 2, 3}}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_put_with_list_value_now_caches(self) -> None:
        """put() with list args stores entry: lists are converted at key build time."""
        cache = IntegrityCache(maxsize=100)
        cache.put("msg-id", {"items": [1, 2, 3]}, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_put_with_dict_value_now_caches(self) -> None:
        """put() with nested dict args stores entry: dicts are converted at key build."""
        cache = IntegrityCache(maxsize=100)
        cache.put("msg-id", {"config": {"option": "value"}}, None, "en-US", use_isolating=True, formatted="fmt", errors=())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_make_key_converts_list_to_valid_key(self) -> None:
        """_make_key returns a non-None key when args contain lists."""
        args: dict[str, object] = {"list_value": [1, 2, 3]}
        key = IntegrityCache._make_key(
            "msg-id", args, None, "en-US", use_isolating=True  # type: ignore[arg-type]
        )
        assert key is not None

    def test_make_key_converts_nested_structures_to_valid_key(self) -> None:
        """_make_key returns a non-None key when args contain nested structures."""
        args: dict[str, object] = {"list": [1, 2], "dict": {"nested": "value"}}
        key = IntegrityCache._make_key(
            "msg-id", args, None, "en-US", use_isolating=True  # type: ignore[arg-type]
        )
        assert key is not None

    def test_get_with_tuple_value_cacheable(self) -> None:
        """get() caches tuple-valued args correctly via type-tagged conversion."""
        cache = IntegrityCache(maxsize=100)
        args = {"coords": (10, 20, 30)}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_tuple_containing_list_cacheable(self) -> None:
        """get() caches tuple-with-nested-list args: nested list is converted."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, object] = {"data": (1, [2, 3], 4)}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    @given(st.tuples(st.integers(), st.integers(), st.integers()))
    def test_get_with_various_tuples_cacheable(
        self, tuple_value: tuple[int, int, int]
    ) -> None:
        """PROPERTY: Tuple-valued args cache and retrieve correctly."""
        cache = IntegrityCache(maxsize=100)
        args = {"tuple_arg": tuple_value}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0
        event(f"tuple_len={len(tuple_value)}")

    @given(st.lists(st.integers(), min_size=1, max_size=10))
    def test_get_with_various_lists_cacheable(self, list_value: list[int]) -> None:
        """PROPERTY: List-valued args cache and retrieve correctly."""
        cache = IntegrityCache(maxsize=100)
        args = {"list_arg": list_value}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0
        event(f"list_len={len(list_value)}")

    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=10), st.integers(), min_size=1, max_size=5
        )
    )
    def test_put_with_various_dicts_cacheable(self, dict_value: dict[str, int]) -> None:
        """PROPERTY: Dict-valued args cache correctly."""
        cache = IntegrityCache(maxsize=100)
        args = {"dict_arg": dict_value}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0
        event(f"dict_len={len(dict_value)}")

    def test_mixed_hashable_and_convertible_args(self) -> None:
        """Cache handles mixed hashable/convertible args in the same call."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, object] = {
            "str_arg": "value",
            "int_arg": 42,
            "list_arg": [1, 2, 3],
        }
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0

    def test_empty_list_cacheable(self) -> None:
        """Empty lists are converted and cached correctly."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, list[object]] = {"empty_list": []}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1

    def test_empty_dict_cacheable(self) -> None:
        """Empty dicts are converted and cached correctly."""
        cache = IntegrityCache(maxsize=100)
        args: dict[str, dict[object, object]] = {"empty_dict": {}}
        cache.put("msg-id", args, None, "en-US", use_isolating=True, formatted="formatted", errors=())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", use_isolating=True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
