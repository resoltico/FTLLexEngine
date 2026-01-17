"""Performance benchmarks for FTL parser.

Measures parsing speed for various FTL patterns to detect regressions.

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine import parse_ftl


class TestParserBenchmarks:
    """Benchmark FTL parser performance."""

    def test_parse_simple_message(self, benchmark) -> None:
        """Benchmark parsing simple message without variables."""
        ftl_source = "hello = Hello, World!"

        result = benchmark(parse_ftl, ftl_source)

        # Verify correctness
        assert len(result.entries) == 1
        assert result.entries[0].id.name == "hello"

    def test_parse_message_with_variables(self, benchmark) -> None:
        """Benchmark parsing message with variable interpolation."""
        ftl_source = "greeting = Hello, { $name }!"

        result = benchmark(parse_ftl, ftl_source)

        assert len(result.entries) == 1

    def test_parse_select_expression(self, benchmark) -> None:
        """Benchmark parsing plural select expression."""
        ftl_source = """
entries-count = {$count ->
    [zero] { $count } entries
    [one] { $count } entry
   *[other] { $count } entries
}
"""

        result = benchmark(parse_ftl, ftl_source)

        assert len(result.entries) == 1

    def test_parse_large_resource(self, benchmark) -> None:
        """Benchmark parsing large FTL resource (100+ messages)."""
        # Generate 100 messages
        messages = [f"msg-{i} = Message {i}" for i in range(100)]
        ftl_source = "\n".join(messages)

        result = benchmark(parse_ftl, ftl_source)

        assert len(result.entries) == 100

    def test_parse_complex_nested(self, benchmark) -> None:
        """Benchmark parsing deeply nested placeables."""
        ftl_source = """
complex = { $name } has { $count ->
    [one] { $count } item
   *[other] { $count } items
} in { CURRENCY($price, currency: "EUR") }
"""

        result = benchmark(parse_ftl, ftl_source)

        assert len(result.entries) == 1
