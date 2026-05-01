# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# API BOUNDARY VALIDATION: TypeError for Non-String Input
# ============================================================================


class TestAPIBoundaryValidation:
    """Test API boundary validation for validate_resource.

    Tests defensive type checking at API boundaries (lines 760-764).
    """

    def test_validate_resource_raises_typeerror_for_bytes(self) -> None:
        """Test validate_resource raises TypeError when passed bytes instead of str.

        Type hints are not enforced at runtime. Users may incorrectly pass bytes
        when the API expects str. The function defensively checks and raises
        TypeError with a helpful message.

        Covers lines 760-764 and branch [759, 760].
        """
        import pytest

        # Pass bytes instead of str (common mistake when reading files)
        source_bytes = b"msg = Hello"

        with pytest.raises(
            TypeError,
            match=r"source must be str, not bytes.*Decode bytes to str",
        ):
            validate_resource(source_bytes)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_none(self) -> None:
        """Test validate_resource raises TypeError when passed None."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not NoneType",
        ):
            validate_resource(None)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_int(self) -> None:
        """Test validate_resource raises TypeError when passed int."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not int",
        ):
            validate_resource(42)  # type: ignore[arg-type]

    def test_validate_resource_raises_typeerror_for_list(self) -> None:
        """Test validate_resource raises TypeError when passed list."""
        import pytest

        with pytest.raises(
            TypeError,
            match=r"source must be str, not list",
        ):
            validate_resource(["msg = Hello"])  # type: ignore[arg-type]

    @given(
        st.one_of(
            st.binary(min_size=1, max_size=50),
            st.integers(),
            st.lists(st.text()),
            st.none(),
        )
    )
    def test_validate_resource_rejects_non_string_types_property(
        self, invalid_input: bytes | int | list[str] | None
    ) -> None:
        """PROPERTY: validate_resource rejects all non-string types with TypeError.

        Events emitted:
        - input_type={type}: Type of invalid input tested
        """
        import pytest

        # Emit event for input type diversity
        event(f"input_type={type(invalid_input).__name__}")

        with pytest.raises(TypeError, match=r"source must be str"):
            validate_resource(invalid_input)  # type: ignore[arg-type]
