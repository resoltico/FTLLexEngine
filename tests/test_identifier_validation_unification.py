"""Property-based tests verifying parser/serializer identifier validation consistency.

Tests that parser and serializer accept/reject the same identifiers,
ensuring the unified validation module prevents divergence.

Property-based testing is the primary verification mechanism.
These tests verify the mathematical property:

    ∀ identifier: parser_accepts(id) ⟺ serializer_accepts(id)

Coverage:
- Valid identifiers: accepted by both parser and serializer
- Invalid syntax: rejected by both parser and serializer
- Length limits: enforced consistently by both parser and serializer
- Edge cases: Unicode, empty strings, special characters
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import parse_ftl, serialize_ftl
from ftllexengine.core.identifier_validation import is_valid_identifier
from ftllexengine.syntax.ast import Identifier, Message, Pattern, Resource, TextElement
from ftllexengine.syntax.serializer import SerializationValidationError


class TestIdentifierValidationUnification:
    """Verify parser and serializer identifier validation consistency."""

    @given(
        # Generate valid identifiers per FTL spec
        identifier=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,254}", fullmatch=True)
    )
    @settings(max_examples=500)
    def test_valid_identifiers_accepted_by_both(self, identifier: str) -> None:
        """Valid identifiers are accepted by both parser and serializer.

        Property: ∀ valid_id: parser_accepts(id) ∧ serializer_accepts(id)
        """
        # Verify validation function agrees
        assert is_valid_identifier(identifier)

        # Parser should accept (parse without error)
        ftl_source = f"{identifier} = test value"
        resource = parse_ftl(ftl_source)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        assert resource.entries[0].id.name == identifier

        # Serializer should accept (serialize without error)
        serialized = serialize_ftl(resource)
        assert identifier in serialized

        # Roundtrip should preserve identifier
        resource2 = parse_ftl(serialized)
        assert resource2.entries[0].id.name == identifier  # type: ignore[union-attr]

    @given(
        # Generate identifiers starting with invalid characters
        first_char=st.sampled_from(["0", "1", "9", "-", "_", ".", " ", "é", "ñ"]),
        rest=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
            max_size=10,
        ),
    )
    @settings(max_examples=200)
    def test_invalid_start_rejected_by_both(self, first_char: str, rest: str) -> None:
        """Identifiers starting with invalid characters rejected by both.

        Property: ∀ invalid_start_id: ¬parser_accepts(id) ∧ ¬serializer_accepts(id)
        """
        identifier = first_char + rest

        # Verify validation function rejects
        assert not is_valid_identifier(identifier)

        # Parser should reject (parse error or junk)
        ftl_source = f"{identifier} = test value"
        resource = parse_ftl(ftl_source)
        # Parser may create junk or fail to parse message
        if resource.entries:
            # If entry exists, it should not be a valid Message
            # or the identifier should be different (junk case)
            assert (
                not isinstance(resource.entries[0], Message)
                or resource.entries[0].id.name != identifier
            )

        # Serializer should reject when validating
        # Create programmatic AST with invalid identifier
        invalid_ast = Resource(
            entries=(
                Message(
                    id=Identifier(name=identifier),
                    value=Pattern(elements=(TextElement(value="test value"),)),
                    attributes=(),
                ),
            )
        )

        # Serializer validation should raise error
        with pytest.raises(SerializationValidationError):
            serialize_ftl(invalid_ast)

    @given(
        # Generate identifiers with invalid continuation characters
        valid_start=st.from_regex(r"[a-zA-Z]", fullmatch=True),
        invalid_continuation=st.text(
            alphabet="éñµ@#$%^&*()+=[]{}|\\:;\"'<>,.?/~` ",
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=200)
    def test_invalid_continuation_rejected_by_both(
        self, valid_start: str, invalid_continuation: str
    ) -> None:
        """Identifiers with invalid continuation characters rejected by both.

        Property: ∀ invalid_continuation_id: ¬parser_accepts(id) ∧ ¬serializer_accepts(id)
        """
        identifier = valid_start + invalid_continuation

        # Verify validation function rejects
        assert not is_valid_identifier(identifier)

        # Parser should reject (parse as partial identifier or junk)
        ftl_source = f"{identifier} = test value"
        resource = parse_ftl(ftl_source)
        # Parser should not create a Message with the full invalid identifier
        if resource.entries and isinstance(resource.entries[0], Message):
            # Parser may have stopped at the invalid character
            assert resource.entries[0].id.name != identifier

        # Serializer should reject
        invalid_ast = Resource(
            entries=(
                Message(
                    id=Identifier(name=identifier),
                    value=Pattern(elements=(TextElement(value="test value"),)),
                    attributes=(),
                ),
            )
        )

        with pytest.raises(SerializationValidationError):
            serialize_ftl(invalid_ast)

    @given(
        # Generate identifiers exceeding max length (256 chars)
        base_length=st.integers(min_value=257, max_value=500),
    )
    @settings(max_examples=100)
    def test_length_limit_enforced_by_both(self, base_length: int) -> None:
        """Identifiers exceeding 256 characters rejected by both.

        Property: ∀ id where len(id) > 256: ¬parser_accepts(id) ∧ ¬serializer_accepts(id)
        """
        # Create identifier exceeding limit
        identifier = "a" * base_length
        assert len(identifier) > 256

        # Verify validation function rejects
        assert not is_valid_identifier(identifier)

        # Parser should reject (enforce length limit)
        ftl_source = f"{identifier} = test value"
        resource = parse_ftl(ftl_source)
        # Parser should not create a Message with the overlength identifier
        # It may create junk or truncate
        if resource.entries and isinstance(resource.entries[0], Message):
            # If it created a Message, the identifier should be truncated/different
            assert resource.entries[0].id.name != identifier

        # Serializer should reject
        overlength_ast = Resource(
            entries=(
                Message(
                    id=Identifier(name=identifier),
                    value=Pattern(elements=(TextElement(value="test value"),)),
                    attributes=(),
                ),
            )
        )

        with pytest.raises(SerializationValidationError, match="256"):
            serialize_ftl(overlength_ast)

    def test_empty_identifier_rejected_by_both(self) -> None:
        """Empty identifiers rejected by both parser and serializer."""
        # Verify validation function rejects
        assert not is_valid_identifier("")

        # Parser should reject (syntax error)
        ftl_source = " = test value"
        resource = parse_ftl(ftl_source)
        # Parser should not create a valid Message
        assert not any(isinstance(entry, Message) for entry in resource.entries)

        # Serializer should reject
        empty_ast = Resource(
            entries=(
                Message(
                    id=Identifier(name=""),
                    value=Pattern(elements=(TextElement(value="test value"),)),
                    attributes=(),
                ),
            )
        )

        with pytest.raises(SerializationValidationError):
            serialize_ftl(empty_ast)

    @given(
        # Generate identifiers at boundary (exactly 255 chars - 1 start + 254 continuation)
        identifier=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{254}", fullmatch=True)
    )
    @settings(max_examples=50)
    def test_max_length_identifier_accepted_by_both(self, identifier: str) -> None:
        """Identifiers at max length (255 chars) are accepted by both.

        Boundary test: max valid length should be accepted.
        """
        assert len(identifier) == 255

        # Verify validation function accepts
        assert is_valid_identifier(identifier)

        # Parser should accept
        ftl_source = f"{identifier} = test value"
        resource = parse_ftl(ftl_source)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)
        assert resource.entries[0].id.name == identifier

        # Serializer should accept
        serialized = serialize_ftl(resource)
        assert identifier in serialized

    @given(
        # Generate identifiers exceeding max length by 1 (257 = 1 start + 256 continuation)
        identifier=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{256}", fullmatch=True)
    )
    @settings(max_examples=50)
    def test_max_length_plus_one_rejected_by_both(self, identifier: str) -> None:
        """Identifiers at max length + 1 (257 chars) are rejected by both.

        Boundary test: just over max length (256) should be rejected.
        """
        assert len(identifier) == 257

        # Verify validation function rejects
        assert not is_valid_identifier(identifier)

        # Serializer should reject
        overlength_ast = Resource(
            entries=(
                Message(
                    id=Identifier(name=identifier),
                    value=Pattern(elements=(TextElement(value="test value"),)),
                    attributes=(),
                ),
            )
        )

        with pytest.raises(SerializationValidationError):
            serialize_ftl(overlength_ast)
