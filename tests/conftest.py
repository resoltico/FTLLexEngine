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
Tests marked with @pytest.mark.fuzz at class level are excluded from normal runs.
This allows test files to contain both essential tests (unmarked, run in CI) and
intensive property tests (fuzz-marked, run with dedicated fuzzing).

Marker pattern:
- Essential tests: No marker, run in every CI build
- Intensive tests: @pytest.mark.fuzz at class level, skipped in normal runs

Run fuzz-marked tests: ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
"""

from datetime import UTC

import pytest
from hypothesis import HealthCheck, Phase, Verbosity, settings

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

# HypoFuzz profile: optimized for coverage-guided fuzzing (--deep runs)
settings.register_profile(
    "hypofuzz",
    max_examples=10000,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    deadline=None,  # No per-example timeout for intensive fuzzing
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    derandomize=False,
)

# Stateful fuzzing profile: for RuleBasedStateMachine tests
settings.register_profile(
    "stateful_fuzz",
    max_examples=500,
    stateful_step_count=50,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    deadline=None,
    derandomize=False,
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

    Available profiles: dev, ci, verbose, hypofuzz, stateful_fuzz
    """
    import os

    # Explicit override via env var
    explicit = os.environ.get("HYPOTHESIS_PROFILE")
    if explicit in ("dev", "ci", "verbose", "hypofuzz", "stateful_fuzz"):
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

    # Check if user is running a specific fuzz file (not the full test suite)
    # In this case, respect their explicit choice
    args = config.invocation_params.args
    for arg in args:
        arg_str = str(arg)
        # Match all fuzz-related test files by common patterns
        fuzz_patterns = ("_fuzzing", "test_concurrent", "test_resolver_cycles")
        if any(p in arg_str for p in fuzz_patterns):
            return

    # Skip fuzz-marked tests in normal test runs
    # Standardized reason prefix: "FUZZ:" enables reliable skip categorization
    skip_fuzz = pytest.mark.skip(
        reason="FUZZ: run with ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz"
    )
    fuzz_skip_count = 0
    for item in items:
        if "fuzz" in item.keywords:
            item.add_marker(skip_fuzz)
            fuzz_skip_count += 1

    # Store count on config for terminal summary hook
    config._fuzz_skip_count = fuzz_skip_count  # type: ignore[attr-defined]


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter,
    exitstatus: int,  # noqa: ARG001
    config: pytest.Config,
) -> None:
    """Emit structured fuzz-skip count for test runner parsing."""
    fuzz_count: int = getattr(config, "_fuzz_skip_count", 0)
    total_skipped = len(terminalreporter.stats.get("skipped", []))
    other_count = total_skipped - fuzz_count
    terminalreporter.write_line(
        f"[SKIP-BREAKDOWN] fuzz={fuzz_count} other={other_count}"
    )


# =============================================================================
# CRASH RECORDING INFRASTRUCTURE
# =============================================================================


def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> None:
    """Record Hypothesis failures to portable crash files.

    When a Hypothesis test fails, this hook:
    1. Extracts the falsifying example from the failure
    2. Generates a standalone repro_crash_<hash>.py script
    3. Saves it to .hypothesis/crashes/ for later analysis

    This ensures that:
    - Crashes are never lost (even if .hypothesis/examples is cleared)
    - Each crash has a portable, standalone reproduction script
    - Crash files can be shared between developers
    """
    import hashlib
    import re
    import textwrap
    from datetime import datetime
    from pathlib import Path

    # Only process failures
    if call.excinfo is None:
        return

    # Only process test phase failures (not setup/teardown)
    if call.when != "call":
        return

    exc_str = str(call.excinfo.value)
    exc_repr = call.excinfo.getrepr(style="short")

    # Check if this is a Hypothesis failure
    if "Falsifying example" not in exc_str and "Falsifying example" not in str(
        exc_repr
    ):
        return

    # Extract the falsifying example
    full_output = str(exc_repr)
    example_match = re.search(
        r"Falsifying example: (\w+)\((.*?)\)",
        full_output,
        re.DOTALL,
    )

    if not example_match:
        return

    test_name = example_match.group(1)
    example_args = example_match.group(2).strip()

    # Generate unique hash for this crash
    crash_content = f"{item.nodeid}:{example_args}"
    crash_hash = hashlib.sha256(crash_content.encode()).hexdigest()[:12]

    # Create crash directory
    crash_dir = Path(".hypothesis/crashes")
    crash_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Build the crash file
    crash_file = crash_dir / f"repro_crash_{timestamp}_{crash_hash}.py"

    # Generate standalone reproduction script
    module = getattr(item, "module", None)
    module_path = module.__name__ if module else "unknown"
    crash_script = textwrap.dedent(f'''\
        #!/usr/bin/env python3
        """Standalone crash reproduction script.

        Generated: {datetime.now(UTC).isoformat()}
        Test: {item.nodeid}
        Hash: {crash_hash}

        Run with: uv run python {crash_file}
        """

        from hypothesis import given, settings, reproduce_failure

        # Import the test module
        # You may need to adjust this import based on your environment
        try:
            from {module_path} import {test_name}
        except ImportError:
            print("Could not import test function. Manual reproduction:")
            print("  Test: {item.nodeid}")
            print("  Example: {test_name}({example_args})")
            raise SystemExit(1)

        # Reproduce the failure
        if __name__ == "__main__":
            print("Reproducing crash...")
            print(f"  Test: {item.nodeid}")
            print(f"  Example: {test_name}({example_args})")
            print()

            try:
                # Call with the falsifying example
                {test_name}({example_args})
                print("[PASS] No failure - bug may have been fixed")
            except Exception as e:
                print(f"[FAIL] Reproduced: {{type(e).__name__}}: {{e}}")
                raise
    ''')

    # Write the crash file
    crash_file.write_text(crash_script)

    # Also write a JSON summary for machine parsing
    import json

    json_file = crash_dir / f"crash_{timestamp}_{crash_hash}.json"
    crash_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "test_nodeid": item.nodeid,
        "test_name": test_name,
        "example_args": example_args,
        "hash": crash_hash,
        "error_type": type(call.excinfo.value).__name__,
        "error_message": str(call.excinfo.value)[:500],
        "repro_script": str(crash_file),
    }
    json_file.write_text(json.dumps(crash_data, indent=2))
