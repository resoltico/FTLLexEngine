"""Strategy metrics collection and reporting for Hypothesis tests.

Provides instrumentation to track strategy behavior similar to Atheris fuzzer metrics:
- Strategy invocation counts
- Weight distribution (intended vs actual)
- Event category coverage
- Performance characteristics
- Skew detection

Usage:
    # In conftest.py or test module:
    from tests.strategy_metrics import StrategyMetrics, metrics_collector

    # Enable collection (call once at session start):
    metrics_collector.enable()

    # After test run, generate report:
    report = metrics_collector.report()
    print(report.to_json())

    # Or check for issues:
    if report.weight_skew_detected:
        print(f"Skew in: {report.skew_patterns}")

Integration with pytest:
    Use the pytest plugin (tests/conftest.py) which auto-collects metrics
    and writes report to .hypothesis/strategy_metrics.json after each session.

Live Metrics (for --deep --metrics):
    # Start periodic reporting to console:
    metrics_collector.start_live_reporting(interval_seconds=10)

    # Stop when done:
    metrics_collector.stop_live_reporting()
"""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

# Thread-safe storage for metrics
_metrics_lock = threading.Lock()


@dataclass
class StrategyInvocation:
    """Single strategy invocation record."""

    strategy_name: str
    event_key: str
    event_value: str
    duration_ms: float
    timestamp: float


@dataclass
class StrategyReport:
    """Aggregated strategy metrics report.

    Attributes are consolidated into logical groups to keep under Pylint's
    max-attributes threshold while maintaining full metrics coverage.
    """

    # Invocation counts
    total_invocations: int = 0
    strategy_counts: dict[str, int] = field(default_factory=dict)
    event_counts: dict[str, int] = field(default_factory=dict)

    # Weight analysis (consolidated: intended, actual, skew info)
    weight_intended: dict[str, float] = field(default_factory=dict)
    weight_actual: dict[str, float] = field(default_factory=dict)
    weight_skew: dict[str, Any] = field(default_factory=lambda: {
        "detected": False,
        "patterns": [],
        "threshold": 0.15,
    })

    # Performance metrics (consolidated into single dict)
    perf_stats: dict[str, float] = field(default_factory=lambda: {
        "mean_ms": 0.0,
        "median_ms": 0.0,
        "p95_ms": 0.0,
        "p99_ms": 0.0,
        "max_ms": 0.0,
    })
    strategy_mean_cost_ms: dict[str, float] = field(default_factory=dict)
    wall_time_ms: dict[str, float] = field(default_factory=dict)

    # Coverage analysis (consolidated)
    coverage: dict[str, Any] = field(default_factory=lambda: {
        "expected": set(),
        "observed": set(),
        "gaps": [],
    })

    # Per-strategy breakdown (Atheris-style)
    per_strategy: dict[str, dict[str, float | int]] = field(default_factory=dict)

    # Convenience properties for backward compatibility
    @property
    def weight_skew_detected(self) -> bool:
        """Check if weight skew was detected."""
        return bool(self.weight_skew.get("detected", False))

    @property
    def skew_patterns(self) -> list[str]:
        """Get list of patterns with skew."""
        return list(self.weight_skew.get("patterns", []))

    @property
    def skew_threshold(self) -> float:
        """Get skew detection threshold."""
        return float(self.weight_skew.get("threshold", 0.15))

    @property
    def coverage_gaps(self) -> list[str]:
        """Get list of unobserved expected events."""
        return list(self.coverage.get("gaps", []))

    @property
    def expected_events(self) -> set[str]:
        """Get set of expected events."""
        return set(self.coverage.get("expected", set()))

    @property
    def observed_events(self) -> set[str]:
        """Get set of observed events."""
        return set(self.coverage.get("observed", set()))

    @property
    def perf_mean_ms(self) -> float:
        """Get mean performance in milliseconds."""
        return float(self.perf_stats.get("mean_ms", 0.0))

    @property
    def perf_median_ms(self) -> float:
        """Get median performance in milliseconds."""
        return float(self.perf_stats.get("median_ms", 0.0))

    @property
    def perf_p95_ms(self) -> float:
        """Get 95th percentile performance in milliseconds."""
        return float(self.perf_stats.get("p95_ms", 0.0))

    @property
    def perf_p99_ms(self) -> float:
        """Get 99th percentile performance in milliseconds."""
        return float(self.perf_stats.get("p99_ms", 0.0))

    @property
    def perf_max_ms(self) -> float:
        """Get maximum performance in milliseconds."""
        return float(self.perf_stats.get("max_ms", 0.0))

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "total_invocations": self.total_invocations,
            "strategy_counts": self.strategy_counts,
            "event_counts": self.event_counts,
            "weight_intended_pct": {
                k: round(v * 100, 2) for k, v in self.weight_intended.items()
            },
            "weight_actual_pct": {
                k: round(v * 100, 2) for k, v in self.weight_actual.items()
            },
            "weight_skew_detected": self.weight_skew_detected,
            "skew_patterns": self.skew_patterns,
            "skew_threshold_pct": round(self.skew_threshold * 100, 2),
            "perf_mean_ms": round(self.perf_mean_ms, 3),
            "perf_median_ms": round(self.perf_median_ms, 3),
            "perf_p95_ms": round(self.perf_p95_ms, 3),
            "perf_p99_ms": round(self.perf_p99_ms, 3),
            "perf_max_ms": round(self.perf_max_ms, 3),
            "strategy_mean_cost_ms": {
                k: round(v, 3) for k, v in self.strategy_mean_cost_ms.items()
            },
            "wall_time_ms": {k: round(v, 1) for k, v in self.wall_time_ms.items()},
            "coverage_gaps": self.coverage_gaps,
            "observed_event_categories": len(self.observed_events),
            "expected_event_categories": len(self.expected_events),
            "per_strategy": self.per_strategy,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# Strategy categories - for per-strategy metric grouping
# Maps event prefix to human-readable strategy name
STRATEGY_CATEGORIES: dict[str, str] = {
    "strategy=placeable_": "ftl_placeables",
    "strategy=select_selector_": "ftl_select_expressions",
    "strategy=message_": "ftl_message_nodes",
    "strategy=term_": "ftl_term_nodes",
    "strategy=comment_": "ftl_comment_nodes",
    "strategy=resource_entry_": "ftl_resources",
    "strategy=attribute": "ftl_attribute_nodes",
    "strategy=financial_": "ftl_financial_numbers",
    "strategy=multiline_chaos_": "ftl_multiline_chaos",
    "strategy=chaos_": "ftl_chaos_source",
    "strategy=pathological_": "ftl_pathological_nesting",
    "strategy=boundary_": "ftl_boundary_depth",
    "strategy=circular_": "ftl_circular_references",
    "strategy=semantic_": "ftl_semantically_broken",
    "currency_decimals=": "currency_by_decimals",
    "territory_region=": "territory_by_region",
    "locale_script=": "locale_by_script",
    "fiscal_delta=": "fiscal_delta_by_magnitude",
    "date_boundary=": "date_by_boundary",
    "fiscal_calendar=": "fiscal_calendar_by_type",
    "fiscal_boundary=": "fiscal_boundary_crossing_pair",
    "month_end_policy=": "month_end_policy_with_event",
}

# Known strategy weight distributions (intended weights)
# Key is event prefix, value is dict mapping suffix to intended fraction
INTENDED_WEIGHTS: dict[str, dict[str, float]] = {
    # ftl.py strategies
    "strategy=placeable_": {
        "variable": 0.40,
        "function_ref": 0.20,
        "term_ref": 0.20,
        "string": 0.10,
        "number": 0.10,
    },
    "strategy=select_selector_": {
        "variable": 0.40,
        "number": 0.20,
        "function": 0.20,
        "string": 0.10,
        "term_ref": 0.10,
    },
    "strategy=message_": {
        "with_attrs": 0.30,
        "no_attrs": 0.70,
    },
    "strategy=term_": {
        "with_attrs": 0.30,
        "no_attrs": 0.70,
    },
    "strategy=comment_": {
        "comment": 0.60,
        "group": 0.20,
        "resource": 0.20,
    },
    "strategy=resource_entry_": {
        "message": 0.60,
        "term": 0.20,
        "comment": 0.20,
    },
    "strategy=financial_": {
        "small": 0.25,
        "medium": 0.25,
        "large": 0.25,
        "huge": 0.25,
    },
    "strategy=financial_decimals_": {
        "0": 0.25,
        "2": 0.25,
        "3": 0.25,
        "4": 0.25,
    },
    # iso.py strategies
    "currency_decimals=": {
        "0": 0.25,
        "2": 0.25,
        "3": 0.25,
        "4": 0.25,
    },
    "territory_region=": {
        "g7": 1 / 7,
        "brics": 1 / 7,
        "baltic": 1 / 7,
        "middle_east": 1 / 7,
        "africa": 1 / 7,
        "pacific": 1 / 7,
        "small": 1 / 7,
    },
    "locale_script=": {
        "latin": 0.20,
        "cjk": 0.20,
        "cyrillic": 0.20,
        "arabic": 0.20,
        "other": 0.20,
    },
    # fiscal.py strategies
    "fiscal_delta=": {
        "zero": 0.25,
        "small": 0.25,
        "medium": 0.25,
        "large": 0.25,
    },
    "date_boundary=": {
        "month_end": 0.20,
        "year_end": 0.20,
        "leap_feb": 0.20,
        "quarter_end": 0.20,
        "normal": 0.20,
    },
    "fiscal_calendar=": {
        "calendar_year": 0.20,
        "uk_japan": 0.20,
        "australia": 0.20,
        "us_federal": 0.20,
        "other": 0.20,
    },
    "fiscal_boundary=": {
        "year_end": 0.50,
        "quarter_end": 0.50,
    },
    "month_end_policy=": {
        "preserve": 1 / 3,
        "clamp": 1 / 3,
        "strict": 1 / 3,
    },
}

# Expected event categories (for coverage gap detection)
EXPECTED_EVENTS: set[str] = {
    # FTL strategy events
    "strategy=placeable_variable",
    "strategy=placeable_function_ref",
    "strategy=placeable_term_ref",
    "strategy=placeable_string",
    "strategy=placeable_number",
    "strategy=select_selector_variable",
    "strategy=select_selector_number",
    "strategy=select_selector_function",
    "strategy=select_selector_string",
    "strategy=select_selector_term_ref",
    "strategy=message_with_attrs",
    "strategy=message_no_attrs",
    "strategy=term_with_attrs",
    "strategy=term_no_attrs",
    "strategy=comment_comment",
    "strategy=comment_group",
    "strategy=comment_resource",
    "strategy=resource_entry_message",
    "strategy=resource_entry_term",
    "strategy=resource_entry_comment",
    "strategy=attribute",
    "strategy=financial_small",
    "strategy=financial_medium",
    "strategy=financial_large",
    "strategy=financial_huge",
    "strategy=financial_decimals_0",
    "strategy=financial_decimals_2",
    "strategy=financial_decimals_3",
    "strategy=financial_decimals_4",
    "strategy=multiline_chaos_mid_identifier",
    "strategy=multiline_chaos_mid_placeable",
    "strategy=multiline_chaos_between_eq_value",
    "strategy=multiline_chaos_unclosed_multiline",
    "strategy=multiline_chaos_bad_continuation",
    # ISO strategy events
    "currency_decimals=0",
    "currency_decimals=2",
    "currency_decimals=3",
    "currency_decimals=4",
    "territory_region=g7",
    "territory_region=brics",
    "territory_region=baltic",
    "territory_region=middle_east",
    "territory_region=africa",
    "territory_region=pacific",
    "territory_region=small",
    "locale_script=latin",
    "locale_script=cjk",
    "locale_script=cyrillic",
    "locale_script=arabic",
    "locale_script=other",
    # Fiscal strategy events
    "fiscal_delta=zero",
    "fiscal_delta=small",
    "fiscal_delta=medium",
    "fiscal_delta=large",
    "date_boundary=month_end",
    "date_boundary=year_end",
    "date_boundary=leap_feb",
    "date_boundary=quarter_end",
    "date_boundary=normal",
    "fiscal_calendar=calendar_year",
    "fiscal_calendar=uk_japan",
    "fiscal_calendar=australia",
    "fiscal_calendar=us_federal",
    "fiscal_calendar=other",
    "fiscal_boundary=year_end",
    "fiscal_boundary=quarter_end",
    "month_end_policy=preserve",
    "month_end_policy=clamp",
    "month_end_policy=strict",
}


class StrategyMetrics:
    """Collector for strategy invocation metrics.

    Thread-safe singleton that aggregates strategy usage data.
    """

    _instance: StrategyMetrics | None = None
    _init_lock = threading.Lock()

    def __new__(cls) -> StrategyMetrics:
        """Singleton pattern for global metrics collection."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize metrics storage (only once)."""
        if getattr(self, "_initialized", False):
            return

        self._enabled = False
        self._invocations: list[StrategyInvocation] = []
        self._event_counter: Counter[str] = Counter()
        self._strategy_durations: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._live_reporter: threading.Timer | None = None
        self._live_interval: float = 30.0
        self._start_time: float = 0.0
        self._last_invocation_count: int = 0
        self._show_per_strategy: bool = False
        self._initialized = True

    def enable(self) -> None:
        """Enable metrics collection."""
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        """Disable metrics collection."""
        with self._lock:
            self._enabled = False

    def reset(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._invocations.clear()
            self._event_counter.clear()
            self._strategy_durations.clear()

    def is_enabled(self) -> bool:
        """Check if collection is enabled."""
        return self._enabled

    def start_live_reporting(
        self,
        interval_seconds: float = 10.0,
        show_per_strategy: bool = False,
    ) -> None:
        """Start periodic live metrics reporting to console.

        Args:
            interval_seconds: How often to print stats (default 10s)
            show_per_strategy: Include per-strategy table in output (default False)
        """
        with self._lock:
            self._live_interval = interval_seconds
            self._start_time = time.time()
            self._last_invocation_count = 0
            self._show_per_strategy = show_per_strategy

        self._schedule_live_report()

    def stop_live_reporting(self) -> None:
        """Stop the periodic live reporter."""
        with self._lock:
            if self._live_reporter is not None:
                self._live_reporter.cancel()
                self._live_reporter = None

    def _count_skewed_categories(self, min_samples: int = 100) -> int:
        """Count categories with weight skew (must hold lock)."""
        skew_count = 0
        for prefix, intended in INTENDED_WEIGHTS.items():
            matching = {
                k: v for k, v in self._event_counter.items()
                if k.startswith(prefix)
            }
            if not matching:
                continue
            match_total = sum(matching.values())
            if match_total < min_samples:
                continue
            skew_count += self._count_skewed_in_category(
                matching, intended, prefix, match_total
            )
        return skew_count

    def _count_skewed_in_category(
        self,
        matching: dict[str, int],
        intended: dict[str, float],
        prefix: str,
        match_total: int,
    ) -> int:
        """Count skewed events in a single category."""
        count = 0
        for event, evt_count in matching.items():
            suffix = event[len(prefix):]
            if suffix not in intended:
                continue
            actual = evt_count / match_total
            if abs(actual - intended[suffix]) > 0.15:
                count += 1
        return count

    def dump_stats_line(self) -> str:
        """Return a one-line stats summary for live display.

        Returns:
            Formatted string like "[METRICS] 1234 events | 5 categories | 0 skew"
        """
        with self._lock:
            total = sum(self._event_counter.values())
            categories = len(self._event_counter)
            skew_count = self._count_skewed_categories()

        skew_str = f"{skew_count} skew" if skew_count == 0 else f"[WARN] {skew_count} skew"
        return f"[METRICS] {total:,} events | {categories} categories | {skew_str}"

    def dump_per_strategy_table(self) -> list[str]:
        """Return per-strategy breakdown as formatted table lines.

        Returns:
            List of formatted lines for console output
        """
        per_strat = self.per_strategy_report()
        if not per_strat:
            return ["[METRICS] No strategy data collected yet"]

        header = (
            f"{'Strategy':<30} {'Invocations':>12} "
            f"{'Wall Time':>12} {'Mean Cost':>12} {'Weight':>8}"
        )
        lines = [
            "",
            "[METRICS] Per-Strategy Breakdown:",
            header,
            "-" * 78,
        ]

        # Sort by invocations descending
        sorted_strats = sorted(
            per_strat.items(),
            key=lambda x: x[1]["invocations"],
            reverse=True,
        )

        for name, metrics in sorted_strats:
            invoc = metrics["invocations"]
            wall = metrics["wall_time_ms"]
            mean = metrics["mean_cost_ms"]
            weight = metrics["weight_pct"]
            lines.append(
                f"{name:<30} {invoc:>12,} {wall:>10.1f}ms {mean:>10.3f}ms {weight:>7.1f}%"
            )

        lines.append("-" * 78)
        return lines

    def _schedule_live_report(self) -> None:
        """Schedule the next live report."""
        self._live_reporter = threading.Timer(
            self._live_interval,
            self._emit_live_report,
        )
        self._live_reporter.daemon = True
        self._live_reporter.start()

    def _emit_live_report(self) -> None:
        """Emit a live metrics summary to console."""
        if not self._enabled:
            return

        with self._lock:
            total = sum(self._event_counter.values())
            elapsed = time.time() - self._start_time
            rate = total / elapsed if elapsed > 0 else 0
            delta = total - self._last_invocation_count
            self._last_invocation_count = total

            # Top event categories
            top_events = self._event_counter.most_common(5)

            # Check for skew (min_samples=0 for live reporting)
            skew_detected = self._count_skewed_categories(min_samples=0) > 0
            show_per_strategy = self._show_per_strategy

        # Print to stderr to not interfere with pytest output
        lines = [
            "",
            f"[METRICS] {elapsed:.0f}s | {total:,} events | {rate:.0f}/s | +{delta:,} since last",
        ]
        if top_events:
            top_str = ", ".join(f"{e[0]}={e[1]}" for e in top_events[:3])
            lines.append(f"[METRICS] Top: {top_str}")
        if skew_detected:
            lines.append("[METRICS] [WARN] Weight skew detected - check distribution")

        # Per-strategy breakdown if enabled
        if show_per_strategy:
            lines.extend(self.dump_per_strategy_table())

        # Use sys.__stderr__ to bypass pytest capture (original stderr before redirection)
        # Combined with flush=True ensures live output even during long test runs
        for line in lines:
            print(line, file=sys.__stderr__, flush=True)

        # Schedule next report
        self._schedule_live_report()

    def record_event(self, event_string: str, duration_ms: float = 0.0) -> None:
        """Record a strategy event.

        Args:
            event_string: The event string (e.g., "strategy=placeable_variable")
            duration_ms: Time taken for this generation in milliseconds
        """
        if not self._enabled:
            return

        with self._lock:
            self._event_counter[event_string] += 1

            # Extract strategy name from event
            if "=" in event_string:
                prefix, value = event_string.split("=", 1)
                strategy_name = f"{prefix}={value}"

                if strategy_name not in self._strategy_durations:
                    self._strategy_durations[strategy_name] = []
                self._strategy_durations[strategy_name].append(duration_ms)

    def record_invocation(
        self,
        strategy_name: str,
        event_key: str,
        event_value: str,
        duration_ms: float,
    ) -> None:
        """Record a detailed strategy invocation.

        Args:
            strategy_name: Name of the strategy function
            event_key: Event category (e.g., "strategy")
            event_value: Event value (e.g., "placeable_variable")
            duration_ms: Time taken in milliseconds
        """
        if not self._enabled:
            return

        with self._lock:
            invocation = StrategyInvocation(
                strategy_name=strategy_name,
                event_key=event_key,
                event_value=event_value,
                duration_ms=duration_ms,
                timestamp=time.time(),
            )
            self._invocations.append(invocation)
            self._event_counter[f"{event_key}={event_value}"] += 1

    def per_strategy_report(self) -> dict[str, dict[str, float | int]]:
        """Generate per-strategy breakdown like Atheris fuzzer targets.

        Groups events by strategy category using STRATEGY_CATEGORIES mapping.
        Each strategy gets:
        - invocations: Total event count for this strategy
        - wall_time_ms: Total time spent in this strategy
        - mean_cost_ms: Average time per invocation
        - weight_pct: Percentage of total invocations

        Returns:
            Dict mapping strategy name to its metrics
        """
        with self._lock:
            if not self._event_counter:
                return {}

            total_events = sum(self._event_counter.values())
            result: dict[str, dict[str, float | int]] = {}

            for prefix, strategy_name in STRATEGY_CATEGORIES.items():
                # Find all events matching this prefix
                matching = {
                    k: v for k, v in self._event_counter.items()
                    if k.startswith(prefix)
                }
                if not matching:
                    continue

                invocations = sum(matching.values())

                # Aggregate durations for this strategy
                wall_time = 0.0
                duration_count = 0
                for event_key in matching:
                    if event_key in self._strategy_durations:
                        wall_time += sum(self._strategy_durations[event_key])
                        duration_count += len(self._strategy_durations[event_key])

                mean_cost = wall_time / duration_count if duration_count > 0 else 0.0

                result[strategy_name] = {
                    "invocations": invocations,
                    "wall_time_ms": round(wall_time, 1),
                    "mean_cost_ms": round(mean_cost, 3),
                    "weight_pct": round(100 * invocations / total_events, 2),
                }

            return result

    def report(self) -> StrategyReport:
        """Generate aggregated metrics report.

        Returns:
            StrategyReport with all computed metrics
        """
        with self._lock:
            report = StrategyReport()
            report.coverage["expected"] = EXPECTED_EVENTS.copy()

            if not self._event_counter:
                return report

            # Basic counts
            report.total_invocations = sum(self._event_counter.values())
            report.event_counts = dict(self._event_counter)
            report.coverage["observed"] = set(self._event_counter.keys())

            # Coverage gaps
            report.coverage["gaps"] = sorted(
                report.coverage["expected"] - report.coverage["observed"]
            )

            # Weight analysis per category
            skew_threshold = report.weight_skew["threshold"]
            for prefix, intended in INTENDED_WEIGHTS.items():
                # Find matching events
                matching_events = {
                    k: v
                    for k, v in self._event_counter.items()
                    if k.startswith(prefix)
                }

                if not matching_events:
                    continue

                total = sum(matching_events.values())
                if total == 0:
                    continue

                # Calculate actual weights
                for event, count in matching_events.items():
                    suffix = event[len(prefix) :]
                    actual_weight = count / total

                    report.weight_actual[event] = actual_weight

                    # Check if we have intended weight
                    if suffix in intended:
                        report.weight_intended[event] = intended[suffix]

                        # Skew detection
                        deviation = abs(actual_weight - intended[suffix])
                        if deviation > skew_threshold:
                            report.weight_skew["detected"] = True
                            report.weight_skew["patterns"].append(
                                f"{event} (intended={intended[suffix]:.2%}, "
                                f"actual={actual_weight:.2%}, "
                                f"deviation={deviation:.2%})"
                            )

            # Performance metrics
            all_durations: list[float] = []
            for strategy, durations in self._strategy_durations.items():
                if durations:
                    all_durations.extend(durations)
                    report.strategy_mean_cost_ms[strategy] = statistics.mean(durations)
                    report.wall_time_ms[strategy] = sum(durations)

            if all_durations:
                all_durations_sorted = sorted(all_durations)
                n = len(all_durations_sorted)

                report.perf_stats["mean_ms"] = statistics.mean(all_durations)
                report.perf_stats["median_ms"] = statistics.median(all_durations)
                report.perf_stats["max_ms"] = max(all_durations)

                # Percentiles
                p95_idx = int(n * 0.95)
                p99_idx = int(n * 0.99)
                report.perf_stats["p95_ms"] = all_durations_sorted[min(p95_idx, n - 1)]
                report.perf_stats["p99_ms"] = all_durations_sorted[min(p99_idx, n - 1)]

            # Strategy counts from invocations
            strategy_counter: Counter[str] = Counter()
            for inv in self._invocations:
                strategy_counter[inv.strategy_name] += 1
            report.strategy_counts = dict(strategy_counter)

        # Per-strategy breakdown (calls per_strategy_report which acquires lock)
        report.per_strategy = self.per_strategy_report()

        return report


# Global singleton instance
metrics_collector = StrategyMetrics()


def timed_event(event_string: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to time strategy execution and record event.

    Usage:
        @composite
        @timed_event("strategy=my_strategy")
        def my_strategy(draw: st.DrawFn) -> SomeType:
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000
            metrics_collector.record_event(event_string, duration_ms)
            return result

        return wrapper

    return decorator


def event_with_metrics(event_string: str) -> None:
    """Replacement for hypothesis.event() that also records metrics.

    Call this instead of hypothesis.event() to get both HypoFuzz guidance
    and metrics collection.

    Args:
        event_string: The event string to record
    """
    from hypothesis import event  # noqa: PLC0415

    event(event_string)
    metrics_collector.record_event(event_string)
