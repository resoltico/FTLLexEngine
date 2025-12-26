"""Grammar-based property tests for the FTL parser.

Uses Hypothesis to generate valid FTL syntax and verify parser properties:
- Round-trip consistency: parse(serialize(parse(X))) == parse(X)
- Idempotence: serialize(parse(serialize(parse(X)))) == serialize(parse(X))
- Determinism: parse(X) == parse(X) across multiple calls
- Composability: parse(A + B) entries == parse(A) entries + parse(B) entries
- Stability: no crashes on random input
- Performance: linear time complexity

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/run-property-tests.sh or pytest -m fuzz
"""

from __future__ import annotations

import time
from dataclasses import is_dataclass
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings, target
from hypothesis import strategies as st
from hypothesis.strategies import composite

# Mark all tests in this file as fuzzing tests (excluded from normal test runs)
pytestmark = pytest.mark.fuzz

from ftllexengine.syntax.ast import (
    Junk,
    Message,
    Pattern,
    Placeable,
    Resource,
    Span,
    StringLiteral,
    Term,
    TextElement,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer

# -----------------------------------------------------------------------------
# Strategy Builders: Core FTL Constructs
# -----------------------------------------------------------------------------


@composite
def ftl_identifier(draw: st.DrawFn) -> str:
    """Generate valid FTL identifier: [a-zA-Z][a-zA-Z0-9_-]*

    Includes reserved keywords to test keyword handling.
    """
    keywords = [
        "NUMBER",
        "DATETIME",
        "one",
        "other",
        "zero",
        "two",
        "few",
        "many",
    ]
    if draw(st.booleans()):
        return draw(st.sampled_from(keywords))

    first_char = draw(
        st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    )
    rest = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
            min_size=0,
            max_size=64,
        )
    )
    return first_char + rest


@composite
def ftl_identifier_boundary(draw: st.DrawFn) -> str:
    """Generate boundary-case identifiers for edge testing."""
    choice = draw(st.sampled_from(["single", "long", "hyphen", "underscore"]))
    if choice == "single":
        return draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
    if choice == "long":
        # Maximum practical length
        return "a" + draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
                min_size=200,
                max_size=200,
            )
        )
    if choice == "hyphen":
        return "a" + "-" * draw(st.integers(1, 10)) + "b"
    # underscore
    return "a" + "_" * draw(st.integers(1, 10)) + "b"


def ftl_number_literal() -> st.SearchStrategy[str]:
    """Generate FTL number literals (integers and floats)."""
    return st.one_of(
        st.integers(min_value=-2_000_000_000, max_value=2_000_000_000).map(str),
        st.floats(allow_nan=False, allow_infinity=False, width=64).map(
            lambda f: f"{f:.10f}"
        ),
    )


@composite
def ftl_string_literal(draw: st.DrawFn) -> str:
    """Generate FTL string literals with escapes and unicode edge cases."""
    ch_list: list[str] = []
    length = draw(st.integers(0, 256))

    for _ in range(length):
        choice = draw(
            st.sampled_from(["norm", "esc", "u", "U", "zws", "spec", "rtl", "combining"])
        )
        if choice == "norm":
            ch = draw(
                st.characters(
                    blacklist_categories=["Cs", "Cc"], blacklist_characters='"\\{}'
                )
            )
            ch_list.append(ch)
        elif choice == "esc":
            ch_list.append(draw(st.sampled_from([r"\"", r"\\", r"\{"])))
        elif choice == "u":
            ch_list.append(f"\\u{draw(st.integers(0, 0xFFFF)):04X}")
        elif choice == "U":
            v = draw(st.integers(0, 0x10FFFF))
            # Avoid surrogate range
            if 0xD800 <= v <= 0xDFFF:
                v = 0xE000
            ch_list.append(f"\\U{v:06X}")
        elif choice == "zws":
            # Zero-width characters
            ch_list.append(
                draw(st.sampled_from(["\u200B", "\u200C", "\u200D", "\uFEFF"]))
            )
        elif choice == "spec":
            ch_list.append(draw(st.sampled_from(["\n", "\r", "\t", " " * 4])))
        elif choice == "rtl":
            # Right-to-left characters
            ch_list.append(
                draw(st.sampled_from(["\u200F", "\u202B", "\u202E", "\u0627"]))
            )
        else:  # combining
            # Combining diacritical marks
            ch_list.append(
                draw(st.sampled_from(["e\u0301", "n\u0303", "a\u0308", "o\u0302"]))
            )

    return f'"{"".join(ch_list)}"'


@composite
def _ftl_terminal_expression(draw: st.DrawFn) -> str:
    """Generate terminal (non-recursive) FTL expressions."""
    choice = draw(st.sampled_from(["var", "num", "str", "msg", "term"]))
    match choice:
        case "var":
            return f"${draw(ftl_identifier())}"
        case "num":
            return draw(ftl_number_literal())
        case "str":
            return draw(ftl_string_literal())
        case "msg":
            return draw(ftl_identifier())
        case _:  # term
            return f"-{draw(ftl_identifier())}"


@composite
def _ftl_recursive_expression(draw: st.DrawFn, depth: int) -> str:
    """Generate recursive FTL expressions (call, select, nested)."""
    choice = draw(st.sampled_from(["msg_attr", "term_full", "call", "select", "nested"]))
    match choice:
        case "msg_attr":
            id_ = draw(ftl_identifier())
            attr = f".{draw(ftl_identifier())}" if draw(st.booleans()) else ""
            return f"{id_}{attr}"
        case "term_full":
            id_ = f"-{draw(ftl_identifier())}"
            attr = f".{draw(ftl_identifier())}" if draw(st.booleans()) else ""
            args = f"({draw(ftl_call_args(depth + 1))})" if draw(st.booleans()) else ""
            return f"{id_}{attr}{args}"
        case "call":
            func = draw(ftl_identifier()).upper()
            return f"{func}({draw(ftl_call_args(depth + 1))})"
        case "select":
            return draw(ftl_select_expr_str(depth + 1))
        case _:  # nested
            return f"{{ {draw(ftl_expression(depth + 1))} }}"


@composite
def ftl_expression(draw: st.DrawFn, depth: int = 0) -> str:
    """Generate FTL expressions with controlled recursion depth."""
    # At max depth, only generate terminal expressions
    if depth > 5:
        return draw(_ftl_terminal_expression())

    # Mix terminal and recursive expressions
    if draw(st.booleans()):
        return draw(_ftl_terminal_expression())
    return draw(_ftl_recursive_expression(depth))


@composite
def ftl_call_args(draw: st.DrawFn, depth: int) -> str:
    """Generate function call arguments."""
    pos_args = draw(st.lists(ftl_expression(depth + 1), min_size=0, max_size=5))
    named_args: list[str] = []
    for _ in range(draw(st.integers(0, 5))):
        named_args.append(f"{draw(ftl_identifier())}: {draw(ftl_expression(depth + 1))}")

    all_args = pos_args + named_args
    return ", ".join(all_args)


@composite
def ftl_select_expr_str(draw: st.DrawFn, depth: int) -> str:
    """Generate SELECT expression syntax."""
    selector = draw(ftl_expression(depth + 1))
    num_variants = draw(st.integers(1, 8))
    variants: list[str] = []
    default_idx = draw(st.integers(0, num_variants - 1))

    for i in range(num_variants):
        prefix = "*" if i == default_idx else " "
        key = draw(
            st.sampled_from(
                ["one", "other", "42", "0.0", "3.14159", draw(ftl_identifier())]
            )
        )
        val = draw(ftl_pattern(depth + 1, simple=True))
        variants.append(f"{prefix}[{key}] {val}")

    return f"{selector} ->\n    " + "\n    ".join(variants)


@composite
def ftl_text_element(draw: st.DrawFn, simple: bool = False) -> str:
    """Generate plain text with parser-stressing special characters."""
    alphabet = st.characters(blacklist_categories=["Cs", "Cc"], blacklist_characters="\n\r")
    text = draw(st.text(alphabet=alphabet, min_size=1, max_size=200))

    if simple:
        # Simple mode: just plain text without noise
        return text

    # Lookahead stressors that might confuse the parser
    noise = draw(
        st.sampled_from(
            ["", "* ", "[", "]", " *", " [", ". ", " .", "{", "}", "{-", "{$", '{"', "..."]
        )
    )
    return noise + text


@composite
def ftl_pattern(draw: st.DrawFn, depth: int = 0, simple: bool = False) -> str:
    """Generate FTL patterns (text + placeables, possibly multiline)."""
    parts: list[str] = []
    num_parts = draw(st.integers(1, 8))

    for _ in range(num_parts):
        if draw(st.booleans()):
            parts.append(draw(ftl_text_element(simple)))
        else:
            parts.append(f"{{ {draw(ftl_expression(depth))} }}")

    # Add multiline continuation with variable indentation
    if not simple and draw(st.booleans()):
        indent = " " * draw(st.integers(1, 16))
        parts.append(f"\n{indent}" + draw(ftl_text_element(simple)))

    return "".join(parts)


@composite
def ftl_resource(draw: st.DrawFn) -> str:
    """Generate complete FTL resource with messages, terms, and comments."""
    entries: list[str] = []
    num_entries = draw(st.integers(1, 20))

    for _ in range(num_entries):
        choice = draw(st.sampled_from(["msg", "term", "comment", "junk", "blank"]))
        id_ = draw(ftl_identifier())

        if choice == "msg":
            comment = (
                f"### {draw(ftl_text_element(simple=True))}\n"
                if draw(st.booleans())
                else ""
            )
            # Messages must have either a value or attributes (or both)
            has_value = draw(st.booleans())
            num_attrs = draw(st.integers(0, 5))

            # Ensure at least value or one attribute
            if not has_value and num_attrs == 0:
                has_value = True

            val = f" = {draw(ftl_pattern())}" if has_value else ""
            attrs: list[str] = []
            for _ in range(num_attrs):
                attrs.append(
                    f"\n    .{draw(ftl_identifier())} = {draw(ftl_pattern())}"
                )
            entries.append(f"{comment}{id_}{val}{''.join(attrs)}")

        elif choice == "term":
            entries.append(f"-{id_} = {draw(ftl_pattern())}")

        elif choice == "comment":
            lvl = draw(st.sampled_from(["#", "##", "###"]))
            entries.append(f"{lvl} {draw(ftl_text_element(simple=True))}")

        elif choice == "junk":
            # Intentionally invalid syntax for error recovery testing
            entries.append(
                f"!invalid {draw(ftl_identifier())} = {draw(st.text(min_size=1, max_size=100))}"
            )

        else:  # blank
            entries.append("\n")

    return "\n\n".join(entries).replace("\t", " ")


# -----------------------------------------------------------------------------
# Boundary Testing Strategies
# -----------------------------------------------------------------------------


@composite
def ftl_deeply_nested_expression(draw: st.DrawFn, target_depth: int = 10) -> str:
    """Generate deeply nested expressions to test recursion limits."""
    expr = f"${draw(ftl_identifier())}"
    for _ in range(target_depth):
        expr = f"{{ {expr} }}"
    return f"test = {expr}"


@composite
def ftl_empty_pattern_message(draw: st.DrawFn) -> str:
    """Generate messages with minimal/empty-like patterns."""
    id_ = draw(ftl_identifier())
    # Pattern with just whitespace-ish content
    pattern = draw(st.sampled_from([" ", "  ", "x", " x ", "{ $v }"]))
    return f"{id_} = {pattern}"


@composite
def ftl_unicode_stress(draw: st.DrawFn) -> str:
    """Generate FTL with Unicode edge cases."""
    id_ = draw(ftl_identifier())
    # Various Unicode challenges
    content = draw(
        st.sampled_from(
            [
                "Hello \u200B World",  # Zero-width space
                "\u202E reversed",  # RTL override
                "cafe\u0301",  # Combining accent
                "\U0001F600 emoji",  # Emoji
                "\u0627\u0644\u0639\u0631\u0628\u064A\u0629",  # Arabic
                "\u4E2D\u6587",  # Chinese
                "\uFEFF BOM",  # Byte order mark
            ]
        )
    )
    return f"{id_} = {content}"


# -----------------------------------------------------------------------------
# AST Normalization (for semantic comparison)
# -----------------------------------------------------------------------------


def flatten_pattern(pattern: Pattern) -> list[Any]:
    """Flatten pattern elements into comparable form."""
    flat: list[Any] = []
    for elem in pattern.elements:
        if isinstance(elem, TextElement):
            val = elem.value
            if flat and isinstance(flat[-1], str):
                flat[-1] += val
            else:
                flat.append(val)
        elif isinstance(elem, Placeable):
            if isinstance(elem.expression, StringLiteral):
                val = elem.expression.value
                if flat and isinstance(flat[-1], str):
                    flat[-1] += val
                else:
                    flat.append(val)
            else:
                flat.append(normalize_ast(elem.expression))
    return flat


def normalize_ast(obj: Any) -> Any:
    """Normalize AST for semantic comparison (strips spans and raw values)."""
    if isinstance(obj, (list, tuple)):
        return [normalize_ast(x) for x in obj]

    if isinstance(obj, Pattern):
        return flatten_pattern(obj)

    if is_dataclass(obj):
        processed: dict[str, Any] = {}
        for field in obj.__dataclass_fields__:
            if field in ("span", "raw", "annotations"):
                continue
            val = getattr(obj, field)
            processed[field] = normalize_ast(val)
        return processed

    return obj


def verify_spans(node: Any, source: str) -> None:
    """Verify span bounds and non-overlapping for pattern elements."""
    if is_dataclass(node):
        node_span = getattr(node, "span", None)
        if node_span is not None:
            span: Span = node_span
            assert (
                0 <= span.start <= span.end <= len(source)
            ), f"Span out of bounds: {span} in {len(source)}"

        if isinstance(node, Pattern) and node.elements:
            last_end = -1
            for elem in node.elements:
                elem_span = getattr(elem, "span", None)
                if elem_span:
                    if last_end != -1:
                        assert (
                            elem_span.start >= last_end
                        ), f"Overlapping spans: {last_end} -> {elem_span.start}"
                    last_end = elem_span.end

        for field in node.__dataclass_fields__:
            val = getattr(node, field)
            if isinstance(val, (list, tuple)):
                for item in val:
                    verify_spans(item, source)
            elif is_dataclass(val):
                verify_spans(val, source)


def has_junk(resource: Resource) -> bool:
    """Check if resource contains any Junk entries."""
    return any(isinstance(e, Junk) for e in resource.entries)


def get_entry_keys(resource: Resource) -> list[str]:
    """Extract message and term identifiers from resource."""
    return [e.id.name for e in resource.entries if isinstance(e, (Message, Term))]


# -----------------------------------------------------------------------------
# Property Tests
# -----------------------------------------------------------------------------


class TestParserProperties:
    """Property-based tests for the FTL parser."""

    @given(ftl_resource())
    @settings(
        max_examples=1500,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
        deadline=None,
    )
    def test_roundtrip_consistency(self, source: str) -> None:
        """Property: parse(serialize(parse(X))) == parse(X) semantically."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast_1 = parser.parse(source)
        verify_spans(ast_1, source)

        # Skip inputs that produce parse errors (Junk)
        assume(not has_junk(ast_1))

        ser_1 = serializer.serialize(ast_1)
        ast_2 = parser.parse(ser_1)
        ser_2 = serializer.serialize(ast_2)

        assert normalize_ast(ast_1) == normalize_ast(ast_2), (
            f"Round-trip mismatch!\nOriginal: {source}\nReserialized: {ser_1}"
        )
        assert ser_1 == ser_2

    @given(ftl_resource())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
        deadline=None,
    )
    def test_idempotence(self, source: str) -> None:
        """Property: serialize(parse(serialize(parse(X)))) == serialize(parse(X))."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast_1 = parser.parse(source)
        assume(not has_junk(ast_1))

        # First roundtrip
        ser_1 = serializer.serialize(ast_1)

        # Second roundtrip
        ast_2 = parser.parse(ser_1)
        ser_2 = serializer.serialize(ast_2)

        # Third roundtrip
        ast_3 = parser.parse(ser_2)
        ser_3 = serializer.serialize(ast_3)

        # After first roundtrip, output must stabilize
        assert ser_2 == ser_3, f"Not idempotent!\nAfter 2: {ser_2}\nAfter 3: {ser_3}"

    @given(ftl_resource())
    @settings(max_examples=200, deadline=None)
    def test_determinism(self, source: str) -> None:
        """Property: Multiple parses of same input produce identical AST."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        # Parse multiple times
        ast_1 = parser.parse(source)
        ast_2 = parser.parse(source)
        ast_3 = parser.parse(source)

        # Serialize for comparison
        ser_1 = serializer.serialize(ast_1)
        ser_2 = serializer.serialize(ast_2)
        ser_3 = serializer.serialize(ast_3)

        assert ser_1 == ser_2 == ser_3, "Parser is non-deterministic"
        assert normalize_ast(ast_1) == normalize_ast(ast_2) == normalize_ast(ast_3)

    @given(ftl_resource(), ftl_resource())
    @settings(
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
        deadline=None,
    )
    def test_composability(self, res1: str, res2: str) -> None:
        """Property: parse(A + B) contains entries from both A and B."""
        parser = FluentParserV1()
        source = res1 + "\n\n" + res2

        ast_merged = parser.parse(source)
        ast1 = parser.parse(res1)
        ast2 = parser.parse(res2)

        keys_merged = get_entry_keys(ast_merged)
        keys1 = get_entry_keys(ast1)
        keys2 = get_entry_keys(ast2)

        # Use target for Hypothesis optimization
        target(len(keys_merged), label="merged_entries")

        # All keys from both should appear in merged (order preserved)
        assert keys_merged == keys1 + keys2, (
            f"Composability violation!\n"
            f"Keys 1: {keys1}\nKeys 2: {keys2}\nMerged: {keys_merged}"
        )

    @given(st.text(min_size=1, max_size=20000))
    @settings(max_examples=1000, deadline=None)
    def test_random_input_stability(self, noise: str) -> None:
        """Property: Parser never crashes, only raises ValueError on invalid input."""
        parser = FluentParserV1()
        try:
            parser.parse(noise)
        except ValueError:
            # Expected for invalid input
            pass
        except RecursionError:
            # Expected for deeply nested input
            pass
        except MemoryError:
            # Expected for extremely large input
            pass
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentional: test verifies parser exception contract (only
            # ValueError/RecursionError/MemoryError allowed on invalid input)
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    @given(ftl_identifier())
    def test_namespace_isolation(self, name: str) -> None:
        """Property: Messages and terms with same name coexist."""
        parser = FluentParserV1()
        source = (
            f"{name} = val1\n"
            f"-{name} = val2\n"
            f"#{name}\n"
            f"_ref = {{{name}}}\n"
            f"_ref2 = {{{{-{name}}}}}"
        )
        ast = parser.parse(source)

        msgs = [e for e in ast.entries if isinstance(e, Message) and e.id.name == name]
        terms = [e for e in ast.entries if isinstance(e, Term) and e.id.name == name]
        assert len(msgs) == 1, f"Expected 1 message named {name}, got {len(msgs)}"
        assert len(terms) == 1, f"Expected 1 term named {name}, got {len(terms)}"

    @given(ftl_resource())
    @settings(max_examples=200, deadline=None)
    def test_linear_time_parsing(self, ftl: str) -> None:
        """Property: Parsing time is O(N) - linear with input size."""
        parser = FluentParserV1()

        # Warmup to avoid JIT/cache effects
        parser.parse("warmup = value")
        parser.parse("warmup = value")

        # Size-scaled threshold: 50ms base + 5ms per KB
        threshold = 0.05 + (len(ftl) / 1000) * 0.005

        # Multiple samples for stability
        times: list[float] = []
        for _ in range(3):
            start = time.perf_counter()
            parser.parse(ftl)
            duration = time.perf_counter() - start
            times.append(duration)

        avg_time = sum(times) / len(times)
        assert avg_time < threshold, (
            f"Slow parsing: {avg_time:.5f}s avg (threshold: {threshold:.5f}s)"
        )


class TestBoundaryConditions:
    """Tests for boundary conditions and edge cases."""

    @given(ftl_identifier_boundary())
    def test_boundary_identifiers(self, identifier: str) -> None:
        """Test parsing of boundary-case identifiers."""
        parser = FluentParserV1()
        source = f"{identifier} = value"
        ast = parser.parse(source)
        assert isinstance(ast, Resource)

    @given(ftl_deeply_nested_expression(target_depth=15))
    def test_deep_nesting(self, source: str) -> None:
        """Test handling of deeply nested expressions."""
        parser = FluentParserV1()
        try:
            ast = parser.parse(source)
            assert isinstance(ast, Resource)
        except (RecursionError, ValueError):
            # Expected for very deep nesting
            pass

    @given(ftl_empty_pattern_message())
    def test_minimal_patterns(self, source: str) -> None:
        """Test parsing of minimal/sparse patterns."""
        parser = FluentParserV1()
        ast = parser.parse(source)
        assert isinstance(ast, Resource)
        assert len(ast.entries) >= 1

    @given(ftl_unicode_stress())
    def test_unicode_edge_cases(self, source: str) -> None:
        """Test parsing of Unicode edge cases."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast = parser.parse(source)
        assert isinstance(ast, Resource)

        # Should be serializable without crash
        if not has_junk(ast):
            output = serializer.serialize(ast)
            assert isinstance(output, str)


class TestErrorHandling:
    """Tests for error handling and recovery."""

    @given(st.text(min_size=1, max_size=500))
    @settings(max_examples=500, deadline=None)
    def test_always_returns_resource(self, text: str) -> None:
        """Property: Parser always returns Resource, never crashes."""
        parser = FluentParserV1()
        result = parser.parse(text)
        assert isinstance(result, Resource)
        assert hasattr(result, "entries")

    @given(ftl_resource(), st.integers(min_value=0, max_value=100))
    @settings(max_examples=200, deadline=None)
    def test_truncation_recovery(self, ftl: str, truncate_pos: int) -> None:
        """Property: Truncated input is handled gracefully."""
        if len(ftl) == 0:
            return

        truncate_pos = min(truncate_pos, len(ftl))
        truncated = ftl[:truncate_pos]

        parser = FluentParserV1()
        result = parser.parse(truncated)

        # Should not crash, should return Resource
        assert isinstance(result, Resource)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
