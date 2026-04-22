"""Vendored Fluent.js structure fixtures for offline spec-conformance tests.

The FTL payloads below are copied from the Fluent.js reference implementation's
``fluent-syntax/test/fixtures_structure`` directory. The expected structural
counts come from the corresponding upstream JSON AST fixtures, so the tests
remain deterministic without depending on live network fetches.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SOURCE_BASE_URL", "STRUCTURE_FIXTURES", "StructureFixture"]

SOURCE_BASE_URL = (
    "https://github.com/projectfluent/fluent.js/tree/main/"
    "fluent-syntax/test/fixtures_structure"
)


@dataclass(frozen=True, slots=True)
class StructureFixture:
    """Vendored Fluent.js structure fixture plus derived reference counts."""

    description: str
    ftl: str
    expected_messages: int
    expected_terms: int


STRUCTURE_FIXTURES: dict[str, StructureFixture] = {
    "simple_message": StructureFixture(
        description="Basic message",
        ftl="foo = Foo\n",
        expected_messages=1,
        expected_terms=0,
    ),
    "multiline_pattern": StructureFixture(
        description="Multiline pattern",
        ftl=(
            "key01 = Value\n"
            "    Continued here.\n\n"
            "key02 =\n"
            "    Value\n"
            "    Continued here.\n\n"
            '# ERROR "Continued" looks like a new message.\n'
            '# key03 parses fine with just "Value".\n'
            "key03 =\n"
            "    Value\n"
            "Continued here\n"
            "    and here.\n\n"
            '# ERROR "Continued" and "and" look like new messages\n'
            '# key04 parses fine with just "Value".\n'
            "key04 =\n"
            "    Value\n"
            "Continued here\n"
            "and even here.\n"
        ),
        expected_messages=4,
        expected_terms=0,
    ),
    "multiline_with_placeables": StructureFixture(
        description="Pattern with placeables",
        ftl=(
            "key =\n"
            "    Foo { bar }\n"
            "    Baz\n"
        ),
        expected_messages=1,
        expected_terms=0,
    ),
    "select_expressions": StructureFixture(
        description="Select expressions",
        ftl=(
            "# ERROR No blanks are allowed between * and [.\n"
            "err01 = { $sel ->\n"
            "    *  [key] Value\n"
            "}\n\n"
            "# ERROR Missing default variant.\n"
            "err02 = { $sel ->\n"
            "    [key] Value\n"
            "}\n"
        ),
        expected_messages=0,
        expected_terms=0,
    ),
    "blank_lines": StructureFixture(
        description="Blank lines handling",
        ftl=(
            "### NOTE: Disable final newline insertion and trimming when editing this file.\n\n"
            "key01 = Value 01\n\n"
            "key02 = Value 02\n\n\n"
            "key03 =\n\n"
            "    Value 03\n\n"
            "    Continued\n\n"
            '# There are four spaces on the line between "Value 04" and "Continued".\n'
            "key04 =\n\n"
            "    Value 04\n"
            "    \n"
            "    Continued\n\n"
            '# There are four spaces on the line following "Value 05".\n'
            "key05 =\n"
            "    Value 05\n"
            "    \n"
            '# There are four spaces on the line following "Value 06".\n'
            "key06 = Value 06\n"
            "    "
        ),
        expected_messages=6,
        expected_terms=0,
    ),
    "term": StructureFixture(
        description="Simple term",
        ftl=(
            "-term =\n"
            "    { $case ->\n"
            "       *[uppercase] Term\n"
            "        [lowercase] term\n"
            "    }\n"
            "    .attr = a\n\n"
            "key01 = {-term}\n"
            "key02 = {-term()}\n"
            'key03 = {-term(case: "uppercase")}\n\n\n'
            "key04 =\n"
            "    { -term.attr ->\n"
            "        [a] { -term } A\n"
            "        [b] { -term() } B\n"
            "       *[x] X\n"
            "    }\n\n"
            "-err1 =\n"
            "-err2 =\n"
            "    .attr = Attribute\n"
            "--err3 = Error\n"
            "err4 = { --err4 }\n"
        ),
        expected_messages=4,
        expected_terms=1,
    ),
    "empty_resource": StructureFixture(
        description="Empty FTL file",
        ftl="",
        expected_messages=0,
        expected_terms=0,
    ),
}
