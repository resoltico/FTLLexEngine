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

from collections.abc import Callable
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
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
    derandomize=False,
)

# CI profile: fast feedback for GitHub Actions (50 examples)
settings.register_profile(
    "ci",
    max_examples=50,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
    derandomize=True,
    print_blob=True,
)

# Verbose profile: debug mode with progress visibility (100 examples)
settings.register_profile(
    "verbose",
    max_examples=100,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
    derandomize=False,
    verbosity=Verbosity.verbose,
)

# HypoFuzz profile: optimized for coverage-guided fuzzing (--deep runs)
settings.register_profile(
    "hypofuzz",
    max_examples=10000,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
    deadline=None,  # No per-example timeout for intensive fuzzing
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    derandomize=False,
)

# Stateful fuzzing profile: for RuleBasedStateMachine tests
settings.register_profile(
    "stateful_fuzz",
    max_examples=500,
    stateful_step_count=50,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
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
        fuzz_patterns = ("_fuzzing", "test_concurrent", "test_resolver_depth_cycles")
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


# =============================================================================
# STRATEGY METRICS COLLECTION
# =============================================================================
#
# Metrics work with BOTH pytest and HypoFuzz CLI:
# - Environment-based: Enable at import time via STRATEGY_METRICS=1
# - atexit: Write report on process exit (works with HypoFuzz)
# - pytest hooks: Additional integration for pytest runs
#
# =============================================================================

# Type alias for hypothesis.event signature
type EventFn = Callable[[str, str | int | float], None]

_original_event: EventFn | None = None  # Store original hypothesis.event
_metrics_initialized: bool = False  # Track if already initialized


def _install_event_hook() -> None:
    """Install a wrapper around hypothesis.event to capture metrics.

    This patches hypothesis.event to also record to our metrics collector,
    enabling automatic metrics capture without modifying strategy code.

    IMPORTANT: Must be called at conftest import time (before test modules
    import ``from hypothesis import event``). If installed later (e.g. in
    pytest_sessionstart), test modules already hold references to the
    original function and the wrapper is never invoked.
    """
    global _original_event  # noqa: PLW0603  # pylint: disable=global-statement

    import hypothesis

    from tests.strategy_metrics import metrics_collector

    if _original_event is not None:
        return  # Already installed

    _original_event = hypothesis.event

    def _wrapped_event(value: str, payload: str | int | float = "") -> None:
        """Wrapper that calls both original event and metrics collector."""
        assert _original_event is not None  # For type narrowing
        _original_event(value, payload)
        # Only record when metrics collection is active
        if metrics_collector.is_enabled():
            metrics_collector.record_event(value)

    hypothesis.event = _wrapped_event


def _uninstall_event_hook() -> None:
    """Restore original hypothesis.event function."""
    global _original_event  # noqa: PLW0603  # pylint: disable=global-statement

    if _original_event is None:
        return

    import hypothesis

    hypothesis.event = _original_event  # type: ignore[assignment]
    _original_event = None


def _write_metrics_report() -> None:
    """Write strategy metrics report (shared by atexit and pytest hook)."""
    import json
    import sys
    from pathlib import Path

    from tests.strategy_metrics import metrics_collector

    # Stop live reporting if running
    metrics_collector.stop_live_reporting()

    # Restore original hypothesis.event
    _uninstall_event_hook()

    if not metrics_collector.is_enabled():
        return

    report = metrics_collector.report()

    # Print final summary to console (always, so user sees metrics at end)
    print("\n" + "=" * 70, file=sys.stderr)
    print("[METRICS] FINAL SUMMARY", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"Total events:      {report.total_invocations:,}", file=sys.stderr)
    cats_obs = len(report.observed_events)
    cats_exp = len(report.expected_events)
    print(f"Categories:        {cats_obs} observed / {cats_exp} expected", file=sys.stderr)
    if report.weight_skew_detected:
        skew_count = len(report.skew_patterns)
        print(f"[WARN] Skew:       {skew_count} patterns", file=sys.stderr)
    if report.coverage_gaps:
        gap_count = len(report.coverage_gaps)
        gap_lines = [f"  - {g}" for g in report.coverage_gaps]
        print(f"[WARN] Gaps:       {gap_count} uncovered", file=sys.stderr)
        print("\n".join(gap_lines), file=sys.stderr)
    mean_ms = report.perf_mean_ms
    p95_ms = report.perf_p95_ms
    print(f"Performance:       mean={mean_ms:.2f}ms p95={p95_ms:.2f}ms", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)

    # Write JSON report
    metrics_dir = Path(".hypothesis")
    metrics_dir.mkdir(exist_ok=True)
    metrics_file = metrics_dir / "strategy_metrics.json"

    report_data = report.to_dict()
    metrics_file.write_text(json.dumps(report_data, indent=2))

    # Also write a human-readable summary if there are issues
    if report.weight_skew_detected or report.coverage_gaps:
        summary_file = metrics_dir / "strategy_metrics_summary.txt"
        lines = [
            "STRATEGY METRICS SUMMARY",
            "=" * 60,
            f"Total invocations: {report.total_invocations}",
            f"Event categories observed: {len(report.observed_events)}",
            f"Event categories expected: {len(report.expected_events)}",
            "",
        ]

        if report.weight_skew_detected:
            lines.append("[WARN] Weight skew detected:")
            for pattern in report.skew_patterns:
                lines.append(f"  - {pattern}")
            lines.append("")

        if report.coverage_gaps:
            lines.append("[WARN] Coverage gaps (unobserved events):")
            for gap in report.coverage_gaps:
                lines.append(f"  - {gap}")
            lines.append("")

        lines.extend([
            "Performance:",
            f"  Mean: {report.perf_mean_ms:.3f}ms",
            f"  P95:  {report.perf_p95_ms:.3f}ms",
            f"  P99:  {report.perf_p99_ms:.3f}ms",
            f"  Max:  {report.perf_max_ms:.3f}ms",
        ])

        summary_file.write_text("\n".join(lines))


def _init_metrics_from_env() -> None:
    """Initialize metrics based on environment variables.

    Called at module import time to support HypoFuzz CLI which bypasses
    pytest session hooks. Uses atexit to ensure report is written.

    The event hook is ALWAYS installed here (before test modules import
    ``from hypothesis import event``) so that late enablement via
    ``pytest_sessionstart`` (e.g. ``-m fuzz``) still captures events.
    The wrapper is a no-op when metrics collection is disabled.
    """
    global _metrics_initialized  # noqa: PLW0603  # pylint: disable=global-statement

    if _metrics_initialized:
        return

    _metrics_initialized = True

    # Always install the event hook early. Test modules bind
    # ``from hypothesis import event`` at import time; if we wait
    # until pytest_sessionstart the wrapper is never called.
    _install_event_hook()

    import atexit
    import os

    from tests.strategy_metrics import metrics_collector

    profile = os.environ.get("HYPOTHESIS_PROFILE", "")
    enable_metrics = (
        os.environ.get("STRATEGY_METRICS") == "1"
        or profile == "hypofuzz"
    )

    if not enable_metrics:
        return

    metrics_collector.enable()
    metrics_collector.reset()

    # Enable live reporting if requested
    enable_live = (
        os.environ.get("STRATEGY_METRICS_LIVE") == "1"
        or profile == "hypofuzz"
    )
    if enable_live:
        interval = float(os.environ.get("STRATEGY_METRICS_INTERVAL", "10"))
        show_detailed = os.environ.get("STRATEGY_METRICS_DETAILED") == "1"
        metrics_collector.start_live_reporting(
            interval_seconds=interval,
            show_per_strategy=show_detailed,
        )

    # Register atexit handler to write report (for HypoFuzz CLI)
    atexit.register(_write_metrics_report)


# Initialize metrics at import time (for HypoFuzz CLI support)
_init_metrics_from_env()


def pytest_sessionstart(session: pytest.Session) -> None:
    """Enable strategy metrics collection at session start.

    Metrics are collected when:
    - Running with -m fuzz (dedicated fuzzing)
    - STRATEGY_METRICS=1 environment variable
    - HYPOTHESIS_PROFILE=hypofuzz

    Live reporting (console output every 30s) enabled when:
    - STRATEGY_METRICS_LIVE=1 environment variable
    - HYPOTHESIS_PROFILE=hypofuzz (deep fuzzing sessions)

    This tracks:
    - Strategy invocation distribution (intended vs actual weights)
    - Performance characteristics per strategy
    - Coverage gaps in event categories
    """
    import os

    from tests.strategy_metrics import metrics_collector

    # Hook is always installed at conftest import time by
    # _init_metrics_from_env(). Here we only need to enable the
    # collector for runs that weren't detectable from env vars
    # (e.g. pytest -m fuzz without STRATEGY_METRICS=1).
    if _metrics_initialized:
        args_str = " ".join(
            str(a) for a in session.config.invocation_params.args
        )
        if "-m fuzz" in args_str and not metrics_collector.is_enabled():
            metrics_collector.enable()
            metrics_collector.reset()
        return

    # Defensive: _init_metrics_from_env() should have run at import
    # time, but handle the edge case where it didn't.
    _install_event_hook()

    profile = os.environ.get("HYPOTHESIS_PROFILE", "")
    enable_metrics = (
        os.environ.get("STRATEGY_METRICS") == "1"
        or profile == "hypofuzz"
        or "-m fuzz" in " ".join(
            str(a) for a in session.config.invocation_params.args
        )
    )

    if enable_metrics:
        metrics_collector.enable()
        metrics_collector.reset()

        enable_live = (
            os.environ.get("STRATEGY_METRICS_LIVE") == "1"
            or profile == "hypofuzz"
        )
        if enable_live:
            interval = float(
                os.environ.get("STRATEGY_METRICS_INTERVAL", "10")
            )
            show_detailed = (
                os.environ.get("STRATEGY_METRICS_DETAILED") == "1"
            )
            metrics_collector.start_live_reporting(
                interval_seconds=interval,
                show_per_strategy=show_detailed,
            )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write strategy metrics report at session end.

    Generates .hypothesis/strategy_metrics.json with:
    - Weight distribution analysis (skew detection)
    - Performance percentiles
    - Coverage gap identification
    """
    import json
    from pathlib import Path

    from tests.strategy_metrics import metrics_collector

    # Stop live reporting if running
    metrics_collector.stop_live_reporting()

    # Restore original hypothesis.event
    _uninstall_event_hook()

    if not metrics_collector.is_enabled():
        return

    report = metrics_collector.report()

    # Write JSON report
    metrics_dir = Path(".hypothesis")
    metrics_dir.mkdir(exist_ok=True)
    metrics_file = metrics_dir / "strategy_metrics.json"

    report_data = report.to_dict()
    report_data["session_exitstatus"] = exitstatus
    report_data["tests_collected"] = session.testscollected

    metrics_file.write_text(json.dumps(report_data, indent=2))

    # Also write a human-readable summary if there are issues
    if report.weight_skew_detected or report.coverage_gaps:
        summary_file = metrics_dir / "strategy_metrics_summary.txt"
        lines = [
            "STRATEGY METRICS SUMMARY",
            "=" * 60,
            f"Total invocations: {report.total_invocations}",
            f"Event categories observed: {len(report.observed_events)}",
            f"Event categories expected: {len(report.expected_events)}",
            "",
        ]

        if report.weight_skew_detected:
            lines.append("[WARN] Weight skew detected:")
            for pattern in report.skew_patterns:
                lines.append(f"  - {pattern}")
            lines.append("")

        if report.coverage_gaps:
            lines.append("[WARN] Coverage gaps (unobserved events):")
            for gap in report.coverage_gaps:
                lines.append(f"  - {gap}")
            lines.append("")

        lines.extend([
            "Performance:",
            f"  Mean: {report.perf_mean_ms:.3f}ms",
            f"  P95:  {report.perf_p95_ms:.3f}ms",
            f"  P99:  {report.perf_p99_ms:.3f}ms",
            f"  Max:  {report.perf_max_ms:.3f}ms",
        ])

        summary_file.write_text("\n".join(lines))
