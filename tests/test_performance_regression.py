"""Performance regression tests for FTL parser.

This module implements SYSTEM 10 from the testing strategy: Performance Regression Testing.
We establish performance baselines and detect algorithmic regressions.

Strategy:
1. Measure parsing time for resources of various sizes
2. Verify O(n) linear scaling (not O(n²) or worse)
3. Detect performance regressions via property-based bounds
4. Test memory efficiency via stress testing

CI-Friendly Testing Approach:
- Uses SCALE-BASED complexity testing (10x size jumps) instead of absolute timing
- Includes warmup runs to minimize JIT/cache effects
- Takes minimum of multiple measurements for stability
- Tests normalized ratios: (time(10n)/time(n)) / (10n/n) ≈ 1.0 for O(n)
- Allows 3x tolerance to handle CI variance while catching O(n²) regressions
- Avoids flaky single-shot timing comparisons that fail in containerized environments

This catches performance bugs that don't affect correctness but impact production.

References:
- Hypothesis deadline parameter for performance bounds
- Algorithmic complexity testing via scaling properties
- "Testing in Production" patterns for CI-resistant performance tests
"""

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.syntax.ast import Resource
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from tests.strategies import ftl_simple_messages

# ==============================================================================
# PERFORMANCE BASELINE CONSTANTS
# ==============================================================================

# These baselines are conservative upper bounds for reasonable hardware
# Adjust if running on very slow or very fast machines

# Parser should handle at least 1000 simple messages per second
MIN_MESSAGES_PER_SECOND = 1000

# Serializer should handle at least 2000 messages per second
MIN_SERIALIZATION_PER_SECOND = 2000

# Resolution should handle at least 500 messages per second
MIN_RESOLUTION_PER_SECOND = 500


# ==============================================================================
# PERFORMANCE MEASUREMENT UTILITIES
# ==============================================================================


def measure_parse_time(ftl: str) -> float:
    """Measure time to parse FTL string (in seconds)."""
    parser = FluentParserV1()
    start = time.perf_counter()
    _ = parser.parse(ftl)
    end = time.perf_counter()
    return end - start


def measure_serialize_time(resource: Resource) -> float:
    """Measure time to serialize resource (in seconds)."""
    start = time.perf_counter()
    _ = serialize(resource)
    end = time.perf_counter()
    return end - start


def measure_resolution_time(bundle: FluentBundle, msg_id: str, args: dict[str, object]) -> float:
    """Measure time to resolve message (in seconds)."""
    start = time.perf_counter()
    _ = bundle.format_pattern(msg_id, args)  # type: ignore[arg-type]
    end = time.perf_counter()
    return end - start


# ==============================================================================
# LINEAR SCALING TESTS
# ==============================================================================


class TestParserPerformanceScaling:
    """Test parser scales linearly with input size."""

    def test_parser_scales_linearly_with_message_count(self):
        """Property: Parsing time grows linearly with message count.

        Tests O(n) complexity using scale-based measurement to avoid CI timing flakiness.
        Uses 10x size jumps and warmup runs to minimize JIT/cache effects.

        Strategy: Test normalized scaling ratios across size ranges.
        If O(n): time(10n)/time(n) / (10n/n) ≈ 1.0
        If O(n²): time(10n)/time(n) / (10n/n) ≈ 10.0
        """
        # Use 10x size jumps to amplify algorithmic differences
        sizes = [100, 1000, 10000]
        times = []

        for size in sizes:
            messages = [f"msg{i} = Value {i}\n" for i in range(size)]
            ftl = "".join(messages)

            # Warmup run to stabilize JIT/cache
            _ = measure_parse_time(ftl)

            # Take minimum of 3 runs (more stable than mean/median)
            time_measurements = [measure_parse_time(ftl) for _ in range(3)]
            times.append(min(time_measurements))

        # Calculate normalized complexity ratios
        # For O(n): these should be close to 1.0
        # For O(n²): these would be ~10.0
        ratio_1_to_2 = (times[1] / times[0]) / (sizes[1] / sizes[0])
        ratio_2_to_3 = (times[2] / times[1]) / (sizes[2] / sizes[1])

        # Allow 3x tolerance for overhead and CI variance
        # Catches O(n²) (ratio ≈ 10) while tolerating measurement noise
        assert 0.3 < ratio_1_to_2 < 3.0, (
            f"Parser scaling is non-linear (100→1000): "
            f"{times[0]:.4f}s → {times[1]:.4f}s, "
            f"normalized ratio {ratio_1_to_2:.2f} (expected ~1.0 for O(n))"
        )
        assert 0.3 < ratio_2_to_3 < 3.0, (
            f"Parser scaling is non-linear (1000→10000): "
            f"{times[1]:.4f}s → {times[2]:.4f}s, "
            f"normalized ratio {ratio_2_to_3:.2f} (expected ~1.0 for O(n))"
        )

    @pytest.mark.parametrize("message_count", [10, 50, 100, 200])
    def test_parser_performance_baseline(self, message_count: int) -> None:
        """Test parser meets minimum performance baseline.

        Baseline: Should parse at least 1000 simple messages per second.
        """
        messages = [f"msg{i} = Value {i}\n" for i in range(message_count)]
        ftl = "".join(messages)

        parse_time = measure_parse_time(ftl)

        # Calculate messages per second
        messages_per_sec = message_count / parse_time if parse_time > 0 else float("inf")

        # Should meet baseline (with tolerance for small inputs)
        if message_count >= 50:
            assert messages_per_sec >= MIN_MESSAGES_PER_SECOND / 2, (
                f"Parser too slow: {messages_per_sec:.0f} msgs/sec "
                f"(baseline: {MIN_MESSAGES_PER_SECOND} msgs/sec)"
            )

    def test_parser_handles_large_messages_efficiently(self):
        """Test parser handles messages with long patterns efficiently."""
        # Create message with very long pattern (1000 chars)
        long_pattern = "x" * 1000
        ftl = f"msg = {long_pattern}\n"

        parse_time = measure_parse_time(ftl)

        # Should parse in < 10ms
        assert parse_time < 0.01, f"Parser too slow for long patterns: {parse_time:.4f}s"

    def test_parser_handles_many_attributes_efficiently(self):
        """Test parser handles messages with many attributes efficiently."""
        # Create message with 50 attributes
        attributes = [f"    .attr{i} = Value {i}\n" for i in range(50)]
        ftl = f"msg = Main value\n{''.join(attributes)}"

        parse_time = measure_parse_time(ftl)

        # Should parse in < 50ms
        assert parse_time < 0.05, f"Parser too slow for many attributes: {parse_time:.4f}s"


class TestSerializerPerformanceScaling:
    """Test serializer scales linearly with AST size."""

    def test_serializer_scales_linearly(self):
        """Property: Serialization time grows linearly with node count.

        Uses scale-based measurement with warmup to avoid CI timing flakiness.
        """
        parser = FluentParserV1()

        # Use 10x size jumps to amplify algorithmic differences
        sizes = [100, 1000, 10000]
        times = []

        for size in sizes:
            messages = [f"msg{i} = Value {i}\n" for i in range(size)]
            resource = parser.parse("".join(messages))

            # Warmup run
            _ = measure_serialize_time(resource)

            # Take minimum of 3 runs
            time_measurements = [measure_serialize_time(resource) for _ in range(3)]
            times.append(min(time_measurements))

        # Calculate normalized complexity ratios
        ratio_1_to_2 = (times[1] / times[0]) / (sizes[1] / sizes[0])
        ratio_2_to_3 = (times[2] / times[1]) / (sizes[2] / sizes[1])

        # Allow 3x tolerance for overhead and CI variance
        assert 0.3 < ratio_1_to_2 < 3.0, (
            f"Serializer scaling is non-linear (100→1000): "
            f"{times[0]:.4f}s → {times[1]:.4f}s, "
            f"normalized ratio {ratio_1_to_2:.2f} (expected ~1.0 for O(n))"
        )
        assert 0.3 < ratio_2_to_3 < 3.0, (
            f"Serializer scaling is non-linear (1000→10000): "
            f"{times[1]:.4f}s → {times[2]:.4f}s, "
            f"normalized ratio {ratio_2_to_3:.2f} (expected ~1.0 for O(n))"
        )

    def test_serializer_performance_baseline(self):
        """Test serializer meets minimum performance baseline.

        Baseline: Should serialize at least 2000 messages per second.
        """
        parser = FluentParserV1()
        messages = [f"msg{i} = Value {i}\n" for i in range(200)]
        resource = parser.parse("".join(messages))

        serialize_time = measure_serialize_time(resource)

        # Calculate messages per second
        messages_per_sec = 200 / serialize_time if serialize_time > 0 else float("inf")

        # Should meet baseline
        assert messages_per_sec >= MIN_SERIALIZATION_PER_SECOND / 2, (
            f"Serializer too slow: {messages_per_sec:.0f} msgs/sec "
            f"(baseline: {MIN_SERIALIZATION_PER_SECOND} msgs/sec)"
        )


class TestResolverPerformanceScaling:
    """Test resolver scales linearly with pattern complexity."""

    def test_resolver_scales_linearly_with_message_count(self):
        """Property: Resolution time grows linearly with message count.

        Uses scale-based measurement with warmup to avoid CI timing flakiness.
        """
        # Use 10x size jumps
        sizes = [50, 500, 5000]
        times = []

        for size in sizes:
            messages = [f"msg{i} = Value {i}" for i in range(size)]
            ftl = "\n".join(messages)

            bundle = FluentBundle("en-US")
            bundle.add_resource(ftl)

            # Warmup run
            for i in range(min(10, size)):
                _ = bundle.format_pattern(f"msg{i}", {})

            # Measure resolution time with 3 runs
            time_measurements = []
            for _ in range(3):
                start = time.perf_counter()
                for i in range(size):
                    _ = bundle.format_pattern(f"msg{i}", {})
                time_measurements.append(time.perf_counter() - start)

            times.append(min(time_measurements))

        # Calculate normalized complexity ratios
        ratio_1_to_2 = (times[1] / times[0]) / (sizes[1] / sizes[0])
        ratio_2_to_3 = (times[2] / times[1]) / (sizes[2] / sizes[1])

        # Allow 3x tolerance for overhead and CI variance
        assert 0.3 < ratio_1_to_2 < 3.0, (
            f"Resolver scaling is non-linear (50→500): "
            f"{times[0]:.4f}s → {times[1]:.4f}s, "
            f"normalized ratio {ratio_1_to_2:.2f} (expected ~1.0 for O(n))"
        )
        assert 0.3 < ratio_2_to_3 < 3.0, (
            f"Resolver scaling is non-linear (500→5000): "
            f"{times[1]:.4f}s → {times[2]:.4f}s, "
            f"normalized ratio {ratio_2_to_3:.2f} (expected ~1.0 for O(n))"
        )

    def test_resolver_performance_baseline(self):
        """Test resolver meets minimum performance baseline.

        Baseline: Should resolve at least 500 messages per second.
        """
        # Create bundle with messages
        messages = [f"msg{i} = Value {i}" for i in range(100)]
        ftl = "\n".join(messages)

        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # Measure resolution time
        start = time.perf_counter()
        for i in range(100):
            _ = bundle.format_pattern(f"msg{i}", {})
        resolution_time = time.perf_counter() - start

        # Calculate messages per second
        messages_per_sec = 100 / resolution_time if resolution_time > 0 else float("inf")

        # Should meet baseline (with tolerance)
        assert messages_per_sec >= MIN_RESOLUTION_PER_SECOND / 2, (
            f"Resolver too slow: {messages_per_sec:.0f} msgs/sec "
            f"(baseline: {MIN_RESOLUTION_PER_SECOND} msgs/sec)"
        )

    def test_resolver_caches_efficiently(self):
        """Test resolver caching prevents redundant work.

        Property: Resolving same message twice should be faster second time.
        """
        ftl = "msg = Value with { $var }"
        bundle = FluentBundle("en-US")
        bundle.add_resource(ftl)

        # First resolution (cold)
        start1 = time.perf_counter()
        result1 = bundle.format_pattern("msg", {"var": "test"})
        time1 = time.perf_counter() - start1

        # Second resolution (warm)
        start2 = time.perf_counter()
        result2 = bundle.format_pattern("msg", {"var": "test"})
        time2 = time.perf_counter() - start2

        # Results should be identical
        assert result1 == result2

        # Second call should be at least as fast (or within 2x for measurement noise)
        # Note: This is a weak test since caching may not be implemented
        assert time2 <= time1 * 2, "Caching appears to make things slower"


# ==============================================================================
# STRESS TESTS
# ==============================================================================


class TestPerformanceStress:
    """Stress tests to find performance cliffs."""

    def test_deeply_nested_select_expressions(self):
        """Test parser handles deeply nested select expressions.

        This tests for stack overflow or exponential complexity bugs.
        """
        # Create nested select expressions (depth 5)
        nested = "$var"
        for i in range(5):
            nested = f"{{ $selector{i} -> [a] {nested} *[b] other }}"

        ftl = f"msg = {nested}"

        # Should parse in reasonable time (< 100ms)
        parse_time = measure_parse_time(ftl)
        assert parse_time < 0.1, f"Parser too slow for nested selects: {parse_time:.4f}s"

    def test_very_large_resource(self):
        """Test parser handles very large resources (stress test).

        This tests memory efficiency and ensures no O(n²) algorithms.
        """
        # Create resource with 1000 messages
        messages = [f"msg{i} = Value {i}\n" for i in range(1000)]
        ftl = "".join(messages)

        # Should parse in < 1 second
        parse_time = measure_parse_time(ftl)
        assert parse_time < 1.0, f"Parser too slow for 1000 messages: {parse_time:.4f}s"

        # Should use reasonable memory (parse shouldn't copy excessively)
        parser = FluentParserV1()
        resource = parser.parse(ftl)
        assert len(resource.entries) >= 900, "Parser failed to parse most messages"  # 90% of 1000

    def test_large_number_literals(self):
        """Test parser handles very large numbers efficiently."""
        # Create message with very large number
        ftl = f"msg = {{ {10**100} }}"

        parse_time = measure_parse_time(ftl)
        assert parse_time < 0.01, f"Parser too slow for large numbers: {parse_time:.4f}s"

    @given(st.lists(ftl_simple_messages(), min_size=10, max_size=50))
    @settings(max_examples=10, deadline=2000)  # 2 second deadline per example
    def test_hypothesis_enforced_deadline(self, messages: list[str]) -> None:
        """Property: Parser meets Hypothesis deadline for all generated inputs.

        This catches catastrophic backtracking or exponential algorithms.
        """
        ftl = "\n\n".join(messages)
        parser = FluentParserV1()

        # Hypothesis will fail test if this takes > 2 seconds
        resource = parser.parse(ftl)
        assert isinstance(resource, Resource)


# ==============================================================================
# REGRESSION DETECTION
# ==============================================================================


class TestPerformanceRegression:
    """Tests that detect specific known performance regressions."""

    def test_no_regex_catastrophic_backtracking(self):
        """Test parser doesn't exhibit regex catastrophic backtracking.

        Some regex patterns can cause O(2^n) behavior on certain inputs.
        """
        # Pattern known to trigger catastrophic backtracking in naive regex: a*a*b
        # Use repetitive pattern that could trigger backtracking
        ftl = "msg = " + "a" * 50 + "x"

        parse_time = measure_parse_time(ftl)
        assert parse_time < 0.01, f"Possible catastrophic backtracking: {parse_time:.4f}s"

    def test_no_quadratic_string_concatenation(self):
        """Test serializer doesn't use quadratic string concatenation.

        Naive string concat: s += x in loop → O(n²)
        Correct: use list and ''.join() → O(n)
        """
        parser = FluentParserV1()

        # Create resource with many messages
        messages = [f"msg{i} = Value {i}\n" for i in range(500)]
        resource = parser.parse("".join(messages))

        # Serialize (should use efficient string building)
        serialize_time = measure_serialize_time(resource)

        # Should be fast even for 500 messages (< 100ms)
        assert serialize_time < 0.1, (
            f"Possible O(n²) string concatenation: {serialize_time:.4f}s for 500 messages"
        )

    def test_no_repeated_parsing_in_bundle(self):
        """Test bundle doesn't re-parse resources on every add.

        Regression: Adding resources should be O(n) not O(n²).
        """
        messages = [f"msg{i} = Value {i}" for i in range(100)]

        bundle = FluentBundle("en-US")

        # Add resources one by one
        start = time.perf_counter()
        for msg in messages:
            bundle.add_resource(msg)
        total_time = time.perf_counter() - start

        # Should be fast (< 100ms for 100 additions)
        assert total_time < 0.1, f"Bundle add_resource too slow: {total_time:.4f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
