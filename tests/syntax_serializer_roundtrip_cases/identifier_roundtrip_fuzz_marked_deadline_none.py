# mypy: ignore-errors
"""Split test cases from tests/test_syntax_serializer_roundtrip.py."""

from tests.syntax_serializer_roundtrip_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Identifier Roundtrip (Fuzz-marked: deadline=None)
# ============================================================================


@pytest.mark.fuzz
@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
@settings(max_examples=50, deadline=None)
def test_serialize_parse_identifiers(identifier: str) -> None:
    """Property: valid identifiers survive serialize->parse round-trip.

    FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
    """
    assume(identifier[0].isalpha())
    assume(all(c.isalnum() or c == "-" for c in identifier))

    ftl_source = f"{identifier} = Test value"
    resource = parse(ftl_source)

    assume(len(resource.entries) > 0)
    assume(not isinstance(resource.entries[0], Junk))

    serialized = serialize(resource)
    resource2 = parse(serialized)

    event(f"id_len={len(identifier)}")
    assert resource2 is not None
    assert len(resource2.entries) == len(resource.entries)
    event("outcome=e2e_id_roundtrip_success")
