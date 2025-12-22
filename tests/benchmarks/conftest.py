"""pytest-benchmark configuration for FTLLexEngine benchmarks.

Configures benchmark defaults and custom options.

Python 3.13+.
"""

from __future__ import annotations

import pytest


def pytest_benchmark_update_json(config, benchmarks, output_json):  # noqa: ARG001
    """Add FTLLexEngine metadata to benchmark results.

    Args:
        config: pytest config (required by pytest-benchmark hook signature)
        benchmarks: benchmark results (required by pytest-benchmark hook signature)
        output_json: JSON output dict to modify
    """
    output_json["project"] = "FTLLexEngine"
    output_json["python_version"] = "3.13+"


@pytest.fixture(scope="session")
def benchmark_config():
    """Configure pytest-benchmark parameters."""
    return {
        "min_rounds": 5,  # Minimum rounds for stable results
        "min_time": 0.000005,  # 5 μs minimum time per round
        "max_time": 1.0,  # 1 second maximum time
        "warmup": True,  # Warmup before timing
    }
