"""Boundary-contract tests for explicit security limit helpers.

These tests cover the fail-closed limit normalization contract shared by the
parser, loaders, and runtime surfaces.
"""

from __future__ import annotations

import pytest

from ftllexengine.core._limits import UNLIMITED, UnlimitedLimit, resolve_limit_arg


class TestUnlimitedLimit:
    """The unlimited sentinel should be explicit and self-describing."""

    def test_repr_uses_semantic_name(self) -> None:
        """The sentinel repr should surface policy intent in logs and docs."""
        assert repr(UNLIMITED) == "UNLIMITED"
        assert isinstance(UNLIMITED, UnlimitedLimit)


class TestResolveLimitArg:
    """resolve_limit_arg() should reject ambiguous or unsafe inputs."""

    def test_rejects_bool_even_though_bool_is_an_int_subclass(self) -> None:
        """Security limits must not accept booleans as accidental integers."""
        with pytest.raises(TypeError, match="max_source_size must be int, got bool"):
            resolve_limit_arg(True, field_name="max_source_size", default=10)

    def test_rejects_non_int_boundary_values(self) -> None:
        """Arbitrary objects at the limit boundary must fail fast."""
        with pytest.raises(TypeError, match="max_source_size must be int, got str"):
            resolve_limit_arg("10", field_name="max_source_size", default=10)  # type: ignore[arg-type]

    def test_rejects_unlimited_when_owner_disallows_it(self) -> None:
        """Owners can opt out of unlimited mode explicitly."""
        with pytest.raises(
            ValueError,
            match="max_pending_operations does not support unlimited mode",
        ):
            resolve_limit_arg(
                UNLIMITED,
                field_name="max_pending_operations",
                default=16,
                allow_unlimited=False,
            )

    @pytest.mark.parametrize("candidate", [0, -1, -99])
    def test_rejects_non_positive_values(self, candidate: int) -> None:
        """Zero and negatives are ambiguous magic values and are never accepted."""
        with pytest.raises(ValueError, match="must be positive"):
            resolve_limit_arg(candidate, field_name="max_source_size", default=10)
