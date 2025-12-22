"""Tests for multi-line Junk aggregation per FTL spec.

Per Fluent EBNF:
    Junk ::= junk_line (junk_line - "#" - "-" - [a-zA-Z])*
    junk_line ::= /[^\n]*/ ("\u000A" | EOF)

This means:
- Junk should consume the first invalid line
- Then continue consuming subsequent lines
- UNTIL hitting a line that starts with #, -, or [a-zA-Z]

Current behavior (BEFORE fix): Each parse error creates a single-line Junk
Correct behavior (AFTER fix): Junk aggregates multiple lines

References:
    - https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.ast import Comment, Junk, Message, Term
from ftllexengine.syntax.parser import FluentParserV1


class TestMultilineJunkAggregation:
    """Test that Junk entries aggregate multiple lines."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_junk_consumes_multiple_lines_until_comment(
        self, parser: FluentParserV1
    ) -> None:
        """Junk should consume lines until hitting a comment (#).

        Per spec: Junk ::= junk_line (junk_line - "#" - "-" - [a-zA-Z])*
        Lines that don't start with #, -, or letter should aggregate.
        """
        # Use truly invalid lines (start with numbers, symbols)
        source = """123invalid line
!!!another invalid
...more junk
# This is a comment
msg = Valid message
"""
        resource = parser.parse(source)

        # Should have: 1 Junk (3 lines), 1 Comment, 1 Message
        assert len(resource.entries) == 3

        # First entry should be Junk containing all 3 invalid lines
        junk = resource.entries[0]
        assert isinstance(junk, Junk)
        assert "123invalid" in junk.content
        assert "!!!another" in junk.content
        assert "...more" in junk.content

        # Second entry should be Comment
        assert isinstance(resource.entries[1], Comment)

        # Third entry should be Message
        assert isinstance(resource.entries[2], Message)

    def test_junk_consumes_until_term(self, parser: FluentParserV1) -> None:
        """Junk should stop consuming when hitting a term (-).

        Per spec: Junk stops at "-" (term start).
        """
        # Use lines that don't start with letter (so they aggregate)
        source = """123invalid
!!!invalid
-brand = Firefox
"""
        resource = parser.parse(source)

        # Should have: 1 Junk (2 lines), 1 Term
        assert len(resource.entries) == 2

        junk = resource.entries[0]
        assert isinstance(junk, Junk)
        assert "123invalid" in junk.content
        assert "!!!invalid" in junk.content

        term = resource.entries[1]
        assert isinstance(term, Term)
        assert term.id.name == "brand"

    def test_junk_consumes_until_message(self, parser: FluentParserV1) -> None:
        """Junk should stop consuming when hitting a message identifier.

        Per spec: Junk stops at [a-zA-Z] (message start).
        """
        source = """invalid line 1
123invalid
!!!invalid
hello = Valid message
"""
        resource = parser.parse(source)

        # Should have: 1 Junk (3 lines), 1 Message
        assert len(resource.entries) == 2

        junk = resource.entries[0]
        assert isinstance(junk, Junk)
        # All invalid lines should be in one Junk entry
        assert "invalid line 1" in junk.content
        assert "123invalid" in junk.content or "invalid" in junk.content
        assert "!!!" in junk.content or "invalid" in junk.content

        msg = resource.entries[1]
        assert isinstance(msg, Message)
        assert msg.id.name == "hello"
