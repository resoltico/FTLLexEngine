# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Malformed NumberLiteral in Variant Keys
# ============================================================================


class TestVariantMatchingMalformedNumberLiteral:
    """NumberLiteral.__post_init__ prevents construction with invalid raw strings.

    Previously, programmatically constructed ASTs could contain invalid
    NumberLiteral.raw strings that bypassed the parser. NumberLiteral.__post_init__
    now enforces the invariant at construction time, making the resolver's
    former InvalidOperation handler unreachable via normal API usage.
    """

    def test_malformed_raw_rejected_at_construction(self) -> None:
        """NumberLiteral rejects raw string that does not parse as a number."""
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=42, raw="not_a_number")

    def test_multiple_malformed_raws_all_rejected(self) -> None:
        """NumberLiteral rejects each invalid raw string at construction time."""
        for bad_raw in ("invalid1", "also_invalid", "not-a-number", "[1,2,3]"):
            with pytest.raises(ValueError, match="not a valid number literal"):
                NumberLiteral(value=1, raw=bad_raw)
