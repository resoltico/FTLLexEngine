"""Performance benchmarks for FluentBundle formatting.

Measures formatting speed to detect runtime performance regressions.

Python 3.13+.
"""

from __future__ import annotations

from typing import Any

import pytest

from ftllexengine import FluentBundle


class TestBundleFormattingBenchmarks:
    """Benchmark FluentBundle formatting performance."""

    @pytest.fixture
    def bundle(self) -> FluentBundle:
        """Create FluentBundle with common messages."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
hello = Hello, World!
greeting = Hello, { $name }!
user-info = { $firstName } { $lastName } (Age: { $age })
entries-count = {$count ->
    [zero] { $count } entries
    [one] { $count } entry
   *[other] { $count } entries
}
"""
        )
        return bundle

    def test_format_simple_message(self, benchmark: Any, bundle: FluentBundle) -> None:
        """Benchmark formatting simple message without variables."""
        result, errors = benchmark(bundle.format_pattern, "hello")

        assert result == "Hello, World!"
        assert errors == ()

    def test_format_message_with_variable(
        self, benchmark: Any, bundle: FluentBundle
    ) -> None:
        """Benchmark formatting message with single variable."""
        result, errors = benchmark(
            bundle.format_pattern, "greeting", {"name": "Anna"}
        )

        assert "Anna" in result
        assert errors == ()

    def test_format_message_with_multiple_variables(
        self, benchmark: Any, bundle: FluentBundle
    ) -> None:
        """Benchmark formatting message with multiple variables."""
        args = {"firstName": "John", "lastName": "Doe", "age": 30}

        result, errors = benchmark(bundle.format_pattern, "user-info", args)

        assert "John" in result
        assert errors == ()

    def test_format_select_expression(
        self, benchmark: Any, bundle: FluentBundle
    ) -> None:
        """Benchmark formatting plural select expression."""
        result, errors = benchmark(
            bundle.format_pattern, "entries-count", {"count": 5}
        )

        assert "5 entries" in result
        assert errors == ()
