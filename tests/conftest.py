"""Pytest configuration for FTLLexEngine test suite.

Single Source of Truth for Hypothesis max_examples:
- dev: Local development with 500 examples (thorough property testing)
- ci: GitHub Actions with 50 examples (fast CI feedback)
- verbose: Debug mode with progress output (100 examples)

Profile auto-detection:
- CI=true environment variable -> "ci" profile (GitHub Actions sets this)
- HYPOTHESIS_PROFILE env var -> explicit override
- Otherwise -> "dev" profile (local development)

Override manually: HYPOTHESIS_PROFILE=verbose pytest tests/

Fuzzing Test Separation:
Tests marked with @pytest.mark.fuzz are excluded from normal test runs.
These are intensive property tests designed for fuzzing, not unit testing.
Run them via: ./scripts/run-property-tests.sh or pytest -m fuzz
"""

import pytest
from hypothesis import Phase, Verbosity, settings

# =============================================================================
# HYPOTHESIS PROFILES - SINGLE SOURCE OF TRUTH
# =============================================================================

# Development profile: thorough local testing (500 examples, silent)
settings.register_profile(
    "dev",
    max_examples=500,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=False,
)

# CI profile: fast feedback for GitHub Actions (50 examples)
settings.register_profile(
    "ci",
    max_examples=50,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=True,
    print_blob=True,
)

# Verbose profile: debug mode with progress visibility (100 examples)
settings.register_profile(
    "verbose",
    max_examples=100,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=False,
    verbosity=Verbosity.verbose,
)


# =============================================================================
# AUTO-DETECT EXECUTION CONTEXT
# =============================================================================


def _detect_profile() -> str:
    """Detect appropriate Hypothesis profile based on execution context.

    Priority:
    1. HYPOTHESIS_PROFILE env var (explicit override)
    2. CI=true env var (GitHub Actions auto-detection)
    3. Default to "dev" (local development)
    """
    import os

    # Explicit override via env var
    explicit = os.environ.get("HYPOTHESIS_PROFILE")
    if explicit in ("dev", "ci", "verbose"):
        return explicit

    # GitHub Actions sets CI=true automatically
    if os.environ.get("CI") == "true":
        return "ci"

    # Local development
    return "dev"


# Load appropriate profile automatically
settings.load_profile(_detect_profile())


# =============================================================================
# FUZZING TEST SEPARATION
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register the 'fuzz' marker for intensive property tests."""
    config.addinivalue_line(
        "markers",
        "fuzz: Intensive property tests for fuzzing (excluded from normal test runs)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip fuzz-marked tests unless explicitly requested.

    Fuzz tests are intensive property tests designed for dedicated fuzzing runs,
    not for inclusion in the regular test suite. They typically have high
    max_examples values (500-1500) and can take 10+ minutes to complete.

    Behavior:
    - Normal test run (pytest tests/): Fuzz tests are SKIPPED
    - Explicit fuzz run (pytest -m fuzz): Fuzz tests run, others skipped
    - Specific file (pytest tests/test_grammar_based_fuzzing.py): Runs as specified

    This ensures `uv run scripts/test.sh` completes quickly while dedicated
    fuzzing scripts can still exercise the full property test suite.
    """
    # Check if user explicitly requested fuzz tests via -m marker
    marker_expr = config.getoption("-m", default="")

    # If user explicitly requested fuzz tests, don't skip them
    if "fuzz" in str(marker_expr):
        return

    # Check if user is running a specific file (not the full test suite)
    # In this case, respect their explicit choice
    args = config.invocation_params.args
    for arg in args:
        if "test_grammar_based_fuzzing" in str(arg):
            return

    # Skip fuzz-marked tests in normal test runs
    skip_fuzz = pytest.mark.skip(
        reason="Fuzzing test - run with: ./scripts/run-property-tests.sh or pytest -m fuzz"
    )
    for item in items:
        if "fuzz" in item.keywords:
            item.add_marker(skip_fuzz)
