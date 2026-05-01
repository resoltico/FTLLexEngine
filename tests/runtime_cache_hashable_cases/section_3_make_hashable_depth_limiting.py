# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 3: MAKE HASHABLE - DEPTH LIMITING
# ============================================================================


class TestMakeHashableDepth:
    """Test depth limiting in _make_hashable.

    Prevents O(N) key computation on adversarially nested inputs and guards
    against stack overflow via RecursionError transformation.
    """

    def test_shallow_nesting_succeeds(self) -> None:
        """Shallow nested structures convert successfully."""
        shallow = {"a": [1, 2, {"b": 3}]}
        result = IntegrityCache._make_hashable(shallow)
        assert result is not None

    def test_moderate_nesting_succeeds(self) -> None:
        """Moderately nested structures (50 levels) convert successfully."""
        # 50 levels well under MAX_DEPTH
        value: dict[str, Any] | int = 42
        for _ in range(50):
            value = {"nested": value}
        result = IntegrityCache._make_hashable(value)
        assert result is not None

    def test_excessive_nesting_raises_type_error(self) -> None:
        """Excessively nested structures raise TypeError with descriptive message."""
        value: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = {"nested": value}
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_custom_depth_parameter_respected(self) -> None:
        """Custom depth parameter overrides default MAX_DEPTH."""
        value: dict[str, Any] | int = 42
        for _ in range(15):
            value = {"nested": value}

        # Should fail at depth=10
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value, depth=10)

        # Should succeed at depth=20
        result = IntegrityCache._make_hashable(value, depth=20)
        assert result is not None

    def test_list_nesting_depth_limited(self) -> None:
        """List nesting respects depth limit."""
        value: list[Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = [value]
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_set_nesting_handled(self) -> None:
        """Sets with simple values are converted; they cannot nest further.

        Sets cannot contain other sets (sets are unhashable), so depth is
        naturally bounded. Simple sets should convert correctly.
        """
        result = IntegrityCache._make_hashable({1, 2, 3})
        assert isinstance(result, tuple)
        assert result[0] == "__set__"
        assert isinstance(result[1], frozenset)

    def test_mixed_nesting_depth_limited(self) -> None:
        """Mixed dict/list alternating nesting respects depth limit."""
        value: dict[str, Any] | list[Any] | int = 42
        for i in range(MAX_DEPTH + 10):
            value = {"nested": value} if i % 2 == 0 else [value]
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)
