"""Property-based tests for caching using Hypothesis.

Validates cache correctness properties under generated scenarios.
"""

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine import FluentBundle


@st.composite
def message_args(draw: st.DrawFn) -> dict[str, str | int]:
    """Generate valid message arguments."""
    num_args = draw(st.integers(min_value=0, max_value=5))
    args = {}
    for _ in range(num_args):
        # pylint: disable=line-too-long
        key = draw(st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=10))
        value = draw(st.one_of(st.text(min_size=0, max_size=20), st.integers()))
        args[key] = value
    return args


class TestCacheProperties:
    """Property-based tests for cache behavior."""

    @given(args=message_args())
    def test_cache_transparency(self, args: dict[str, str | int]) -> None:
        """Cache hit returns same result as cache miss.

        Property: format_pattern(msg, args) with cache enabled should return
        identical results to format_pattern(msg, args) without cache.
        """
        ftl_vars = " ".join([f"{{ ${k} }}" for k in args])
        ftl_source = f"msg = Hello {ftl_vars}!"

        # Bundle without cache
        bundle_no_cache = FluentBundle("en", enable_cache=False, use_isolating=False)
        bundle_no_cache.add_resource(ftl_source)
        result_no_cache, errors_no_cache = bundle_no_cache.format_pattern("msg", args)

        # Bundle with cache
        bundle_with_cache = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle_with_cache.add_resource(ftl_source)

        # First call (cache miss)
        result_miss, errors_miss = bundle_with_cache.format_pattern("msg", args)
        assert result_miss == result_no_cache
        assert len(errors_miss) == len(errors_no_cache)

        # Second call (cache hit)
        result_hit, errors_hit = bundle_with_cache.format_pattern("msg", args)
        assert result_hit == result_no_cache
        assert len(errors_hit) == len(errors_no_cache)

        # Cache hit and miss must return identical results
        assert result_miss == result_hit
        assert len(errors_miss) == len(errors_hit)

    @given(
        args1=message_args(),
        args2=message_args(),
    )
    def test_cache_isolation(
        self, args1: dict[str, str | int], args2: dict[str, str | int]
    ) -> None:
        """Different args produce different cache entries.

        Property: format_pattern(msg, args1) and format_pattern(msg, args2)
        should be cached separately if args differ.
        """
        # Only test if args actually differ
        if args1 == args2:
            return

        ftl_vars = set(args1.keys()) | set(args2.keys())
        ftl_placeholders = " ".join([f"{{ ${k} }}" for k in ftl_vars])
        ftl_source = f"msg = Test {ftl_placeholders}"

        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource(ftl_source)

        # Format with args1
        _result1, _ = bundle.format_pattern("msg", args1)

        # Format with args2
        _result2, _ = bundle.format_pattern("msg", args2)

        # Results should differ if args differ
        # (Unless all placeholders are optional and missing)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2  # Two separate cache entries

    @given(
        cache_size=st.integers(min_value=1, max_value=100),
        num_messages=st.integers(min_value=1, max_value=200),
    )
    def test_lru_eviction_property(self, cache_size: int, num_messages: int) -> None:
        """Cache size never exceeds limit.

        Property: No matter how many format calls, cache size ≤ maxsize.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=cache_size)

        # Add many messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_messages)])
        bundle.add_resource(ftl_source)

        # Format all messages
        for i in range(num_messages):
            bundle.format_pattern(f"msg{i}")

        # Cache size must respect limit
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] <= cache_size
        assert stats["size"] == min(num_messages, cache_size)

    @given(
        num_calls=st.integers(min_value=1, max_value=100),
    )
    def test_stats_consistency_property(self, num_calls: int) -> None:
        """Cache stats are always consistent.

        Property: hits + misses = total calls
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Make num_calls format calls
        for _ in range(num_calls):
            bundle.format_pattern("msg")

        # Stats must be consistent
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] + stats["misses"] == num_calls
        assert stats["hits"] == num_calls - 1  # All but first are hits
        assert stats["misses"] == 1  # Only first is miss


class TestCacheInvalidationProperties:
    """Property-based tests for cache invalidation."""

    @given(
        num_resources=st.integers(min_value=1, max_value=10),
    )
    def test_invalidation_on_add_resource(self, num_resources: int) -> None:
        """Cache is cleared every time add_resource is called.

        Property: After add_resource(), cache size = 0 and stats reset.
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")

        # Add resources multiple times
        for i in range(num_resources):
            stats_before = bundle.get_cache_stats()
            assert stats_before is not None

            bundle.add_resource(f"msg{i} = World {i}")

            stats_after = bundle.get_cache_stats()
            assert stats_after is not None
            assert stats_after["size"] == 0  # Cache cleared
            assert stats_after["hits"] == 0  # Stats reset
            assert stats_after["misses"] == 0

    @given(
        num_functions=st.integers(min_value=1, max_value=10),
    )
    def test_invalidation_on_add_function(self, num_functions: int) -> None:
        """Cache is cleared every time add_function is called.

        Property: After add_function(), cache size = 0 and stats reset.
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")

        # Add functions multiple times
        for i in range(num_functions):
            stats_before = bundle.get_cache_stats()
            assert stats_before is not None

            def func(value: str) -> str:
                return value.upper()

            bundle.add_function(f"FUNC{i}", func)

            stats_after = bundle.get_cache_stats()
            assert stats_after is not None
            assert stats_after["size"] == 0  # Cache cleared


class TestCacheInternalProperties:
    """Property-based tests for cache internals."""

    @given(
        cache_size=st.integers(min_value=1, max_value=100),
        num_operations=st.integers(min_value=0, max_value=200),
    )
    def test_cache_len_property(self, cache_size: int, num_operations: int) -> None:
        """Cache __len__ always returns correct size.

        Property: len(cache) ≤ maxsize and len(cache) = stats["size"]
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=cache_size)

        # Add messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_operations)])
        bundle.add_resource(ftl_source)

        # Format messages
        for i in range(num_operations):
            bundle.format_pattern(f"msg{i}")

        # len() should match stats
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert len(cache) == stats["size"]
        assert len(cache) <= cache_size

    @given(
        cache_size=st.integers(min_value=1, max_value=50),
    )
    def test_cache_properties_consistent(self, cache_size: int) -> None:
        """Cache properties (maxsize, hits, misses) are consistent.

        Property: Properties always match internal state.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=cache_size)
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # maxsize property matches constructor
        assert cache.maxsize == cache_size

        # hits and misses start at zero
        assert cache.hits == 0
        assert cache.misses == 0

        # After one call: 1 miss, 0 hits
        bundle.format_pattern("msg")
        assert cache.hits == 0
        assert cache.misses == 1

        # After second call: 1 miss, 1 hit
        bundle.format_pattern("msg")
        assert cache.hits == 1
        assert cache.misses == 1

    @given(
        num_updates=st.integers(min_value=1, max_value=50),
    )
    def test_cache_update_existing_key_property(self, num_updates: int) -> None:
        """Updating existing cache entry doesn't increase size.

        Property: Repeatedly formatting same message keeps cache size at 1.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=10)
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format same message multiple times
        for _ in range(num_updates):
            bundle.format_pattern("msg")

        # Cache size should be 1 (same entry updated)
        assert len(cache) == 1
        assert cache.hits == num_updates - 1
        assert cache.misses == 1

    @given(
        args_list=st.lists(
            st.dictionaries(
                keys=st.text(alphabet="abcdefghij", min_size=1, max_size=3),
                values=st.integers(min_value=0, max_value=100),
                min_size=0,
                max_size=3,
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_cache_key_uniqueness_property(self, args_list: list[dict[str, int]]) -> None:
        """Each unique args dict creates separate cache entry.

        Property: Distinct args → distinct cache keys → separate entries.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=100, use_isolating=False)
        bundle.add_resource("msg = { $a } { $b } { $c }")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format with different args
        for args in args_list:
            bundle.format_pattern("msg", args)

        # Cache size equals number of unique args
        unique_args = len({tuple(sorted(args.items())) for args in args_list})
        assert len(cache) == min(unique_args, 100)  # Min with cache_size

    @given(
        message_ids=st.lists(
            st.text(alphabet="abcdefghij", min_size=3, max_size=10),
            min_size=1,
            max_size=20,
            unique=True,
        )
    )
    def test_cache_message_id_isolation_property(
        self, message_ids: list[str]
    ) -> None:
        """Different message IDs create separate cache entries.

        Property: Each message_id → separate cache entry.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=100)

        # Add all messages
        ftl_source = "\n".join([f"{msg_id} = Message {i}" for i, msg_id in enumerate(message_ids)])
        bundle.add_resource(ftl_source)
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format all messages
        for msg_id in message_ids:
            bundle.format_pattern(msg_id)

        # Cache should have one entry per message
        assert len(cache) == min(len(message_ids), 100)

    @given(
        attributes=st.lists(
            st.one_of(st.none(), st.text(alphabet="abcdefghij", min_size=1, max_size=10)),
            min_size=1,
            max_size=10,
        )
    )
    def test_cache_attribute_isolation_property(
        self, attributes: list[str | None]
    ) -> None:
        """Different attributes create separate cache entries.

        Property: Each attribute → separate cache entry.
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=100, use_isolating=False)

        # Create message with multiple attributes
        attrs_ftl = "\n    ".join([f".{attr} = Attr {attr}" for attr in attributes if attr])
        bundle.add_resource(f"msg = Value\n    {attrs_ftl}")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format with different attributes
        seen_attrs = set()
        for attr in attributes:
            bundle.format_pattern("msg", attribute=attr)
            seen_attrs.add(attr)

        # Cache should have one entry per unique attribute
        assert len(cache) == len(seen_attrs)

    @given(
        num_operations=st.integers(min_value=0, max_value=100),
    )
    def test_cache_size_property_consistency(self, num_operations: int) -> None:
        """Cache size property matches internal state.

        Property: cache.size == len(cache._cache)
        """
        bundle = FluentBundle("en", enable_cache=True, cache_size=100)

        # Add messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_operations)])
        bundle.add_resource(ftl_source)
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format messages
        for i in range(num_operations):
            bundle.format_pattern(f"msg{i}")

        # size property should match len() and stats
        assert cache.size == len(cache)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert cache.size == stats["size"]


class TestCacheTypeCollisionPrevention:
    """Tests for type collision prevention in cache keys.

    Python's hash equality means hash(1) == hash(True) == hash(1.0), which would
    cause cache collisions when these values produce different formatted outputs.
    The cache uses type-tagged tuples to prevent this.
    """

    def test_bool_int_produce_different_cache_entries(self) -> None:
        """Boolean True and integer 1 produce distinct cache entries.

        In Fluent, True formats as "true" while 1 formats as "1". Without type
        tagging, Python's hash equality would cause cache collision.
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format with True first
        result_bool, _ = bundle.format_pattern("msg", {"v": True})
        # Format with 1 (would collide without type tagging)
        result_int, _ = bundle.format_pattern("msg", {"v": 1})

        # Results must differ - bool formats as "true", int as "1"
        assert result_bool == "true"
        assert result_int == "1"

        # Cache should have 2 entries (not 1 due to collision)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_int_float_produce_different_cache_entries(self) -> None:
        """Integer 1 and float 1.0 produce distinct cache entries.

        Without type tagging, hash(1) == hash(1.0) would cause collision.
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format with int first
        _result_int, _ = bundle.format_pattern("msg", {"v": 1})
        # Format with float (would collide without type tagging)
        _result_float, _ = bundle.format_pattern("msg", {"v": 1.0})

        # Cache should have 2 entries
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_bool_false_int_zero_distinct(self) -> None:
        """Boolean False and integer 0 produce distinct cache entries.

        hash(False) == hash(0) in Python.
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        result_bool, _ = bundle.format_pattern("msg", {"v": False})
        result_int, _ = bundle.format_pattern("msg", {"v": 0})

        # bool formats as "false", int as "0"
        assert result_bool == "false"
        assert result_int == "0"

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_cache_hit_returns_correct_typed_value(self) -> None:
        """Cache hit returns value for correct type, not hash-equivalent type.

        This is the critical test: after caching with int 1, looking up with
        bool True must NOT return the cached "1", but cache miss and format "true".
        """
        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Cache with int 1
        bundle.format_pattern("msg", {"v": 1})

        # Look up with bool True - must NOT be a cache hit for the int entry
        result, _ = bundle.format_pattern("msg", {"v": True})

        # If type tagging works, this returns "true" not "1"
        assert result == "true"

    @given(st.booleans(), st.integers())
    def test_bool_int_always_distinct(self, b: bool, i: int) -> None:
        """PROPERTY: Any bool and int pair with same Python hash produce distinct cache entries."""
        # Only test when hash would collide
        if hash(b) != hash(i):
            return

        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format both
        bundle.format_pattern("msg", {"v": b})
        bundle.format_pattern("msg", {"v": i})

        # Should be 2 entries despite hash equality
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    @given(st.integers(), st.floats(allow_nan=False, allow_infinity=False))
    def test_int_float_always_distinct_when_equal(self, i: int, f: float) -> None:
        """PROPERTY: Int and float with same value produce distinct cache entries."""
        # Only test when values are equal (and thus hash-equal)
        if i != f:
            return

        bundle = FluentBundle("en", enable_cache=True, use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format both
        bundle.format_pattern("msg", {"v": i})
        bundle.format_pattern("msg", {"v": f})

        # Should be 2 entries despite equality
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2
