---
afad: "3.3"
version: "0.117.0"
domain: fuzzing
updated: "2026-02-21"
route:
  keywords: [fuzzing, hypothesis, hypofuzz, property-based, testing, coverage, metrics, workers]
  questions: ["how to run hypothesis tests?", "how to use hypofuzz?", "how to reproduce hypothesis failures?", "how to see strategy metrics?", "why does --metrics use pytest instead of hypofuzz?"]
---

# HypoFuzz Guide (Hypothesis Property-Based Testing)

**Purpose**: Run and understand Hypothesis/HypoFuzz property-based testing.
**Prerequisites**: Basic pytest knowledge.

---

## Quick Start

```bash
# Quick property test check
./scripts/fuzz_hypofuzz.sh

# Continuous deep fuzzing
./scripts/fuzz_hypofuzz.sh --deep

# Reproduce a specific failing test
./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py::test_roundtrip
```

---

## How Hypothesis Works

Hypothesis is a property-based testing framework that:

1. **Generates** inputs based on type strategies
2. **Tests** properties you define (e.g., "parsing then serializing round-trips")
3. **Shrinks** failing inputs to minimal reproducible examples
4. **Stores** examples in `.hypothesis/examples/` for regression testing

Key difference from Atheris: Hypothesis generates **Python objects** via strategies, not raw bytes.

---

## Command Reference

| Command | Description |
|---------|-------------|
| `./scripts/fuzz_hypofuzz.sh` | Quick property tests (default mode) |
| `./scripts/fuzz_hypofuzz.sh --deep` | Continuous HypoFuzz fuzzing (until Ctrl+C) |
| `./scripts/fuzz_hypofuzz.sh --deep --metrics` | Single-pass pytest with strategy metrics |
| `./scripts/fuzz_hypofuzz.sh --preflight` | Audit test infrastructure (events, strategies) |
| `./scripts/fuzz_hypofuzz.sh --list` | Show reproduction info and failures |
| `./scripts/fuzz_hypofuzz.sh --repro TEST` | Reproduce failing test with verbose output |
| `./scripts/fuzz_hypofuzz.sh --clean` | Remove .hypothesis/ database |
| `./scripts/fuzz_hypofuzz.sh --verbose` | Show detailed progress |
| `./scripts/fuzz_hypofuzz.sh --metrics` | Enable periodic per-strategy metrics |
| `./scripts/fuzz_hypofuzz.sh --workers N` | Parallel workers (default: 4; see Workers section) |
| `./scripts/fuzz_hypofuzz.sh --time N` | Time limit in seconds (--deep mode) |

---

## Workflow 1: Quick Check (Recommended)

Run before committing:

```bash
./scripts/fuzz_hypofuzz.sh
```

**Interpreting Results:**

- `[PASS]` - All property tests passed
- `[FAIL]` - Failures detected with falsifying examples shown
- `[STOPPED]` - Run interrupted by user (Ctrl+C)

---

## Workflow 2: Deep Fuzzing

For thorough exploration:

```bash
# Run for 5 minutes
./scripts/fuzz_hypofuzz.sh --deep --time 300

# Run until Ctrl+C
./scripts/fuzz_hypofuzz.sh --deep
```

HypoFuzz uses coverage-guided fuzzing to explore new code paths. It runs all Hypothesis tests continuously, learning which inputs increase coverage.

### Deep Mode with Metrics

Adding `--metrics` changes the behavior:

```bash
# Single-pass with strategy metrics (NOT continuous)
./scripts/fuzz_hypofuzz.sh --deep --metrics
```

**Trade-off**: `--metrics` uses pytest instead of HypoFuzz because HypoFuzz's multiprocessing prevents metrics collection across workers. This runs all fuzz tests once with 10,000 examples per test (hypofuzz profile) and emits live metrics every 10 seconds.

For continuous fuzzing, use `--deep` without `--metrics`.

**Session Log:**

HypoFuzz output is logged to `.hypothesis/hypofuzz.log`. View failures:

```bash
./scripts/fuzz_hypofuzz.sh --list
```

---

## Workflow 3: Reproducing Failures

When Hypothesis finds a failing example:

1. It prints the "Falsifying example" to the terminal
2. It stores the shrunk example in `.hypothesis/examples/<sha384_hash>`
3. On re-run, it **automatically replays** the failure

**To reproduce with verbose output:**

```bash
./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py::test_roundtrip
```

**To extract @example decorator:**

```bash
uv run python scripts/fuzz_hypofuzz_repro.py --example tests/fuzz/test_syntax_parser_property.py::test_roundtrip
```

This parses the failure output and generates a copy-paste ready `@example` decorator.

**JSON output for automation:**

```bash
uv run python scripts/fuzz_hypofuzz_repro.py --json tests/fuzz/test_syntax_parser_property.py::test_roundtrip
```

Output format:

```json
{
  "test_path": "tests/fuzz/test_syntax_parser_property.py::test_roundtrip",
  "status": "fail",
  "exit_code": 1,
  "timestamp": "2026-02-04T10:30:00+00:00",
  "error_type": "AssertionError",
  "traceback": "E   AssertionError: ...",
  "example": {"ftl": "msg = { $x"},
  "example_decorator": "@example(ftl='msg = { $x')",
  "hypothesis_seed": 12345
}
```

---

## Crash Recording

When a Hypothesis test fails, the `conftest.py` hook automatically:

1. Extracts the falsifying example from the failure
2. Generates a standalone `repro_crash_<timestamp>_<hash>.py` script
3. Saves it to `.hypothesis/crashes/` with a companion JSON file

**Benefits:**
- Crashes are never lost (even if `.hypothesis/examples/` is cleared)
- Each crash has a portable, standalone reproduction script
- Crash files can be shared between developers

**Run a crash reproduction:**

```bash
uv run python .hypothesis/crashes/repro_crash_20260204_103000_a1b2c3d4.py
```

---

## Database Structure

Hypothesis stores data in `.hypothesis/`:

```
.hypothesis/
├── examples/           # Coverage database (SHA-384 hashed filenames)
│   ├── a1b2c3d4...    # Stored example (pickled Python objects)
│   └── ...
├── crashes/            # Portable crash reproduction files
│   ├── repro_crash_20260204_103000_a1b2c3d4.py   # Standalone repro script
│   ├── crash_20260204_103000_a1b2c3d4.json       # Machine-readable details
│   └── ...
└── hypofuzz.log       # Session log from --deep runs
```

**Key Points:**

- Examples are **pickled Python objects**, not text files
- Filenames are SHA-384 hashes of the test function signature
- Hypothesis automatically replays stored examples on test re-runs
- The `crashes/` directory contains portable reproduction scripts (auto-generated on failure)
- There is NO `.hypothesis/failures/` directory (this is a common misconception)

---

## Promoting Failures to @example

When a bug is found and fixed, promote the failing example to a permanent regression test:

```python
from hypothesis import given, example
from tests.strategies.ftl import valid_ftl

@example(ftl="edge-case = { $var }")  # Promoted from Hypothesis failure
@given(ftl=valid_ftl())
def test_roundtrip(ftl: str) -> None:
    """Parse-serialize-parse produces identical AST."""
    ...
```

This ensures the edge case is tested deterministically in every run.

---

## Oracle Testing (Differential Fuzzing)

The `tests/fuzz/` directory contains oracle-based fuzzers that compare `FluentBundle` against a reference implementation:

```
tests/fuzz/
├── __init__.py
├── shadow_bundle.py                     # Reference implementation (unoptimized, simple)
├── test_runtime_bundle_oracle.py        # State machine oracle fuzzer
├── test_core_depth_guard_exhaustion.py  # MAX_DEPTH boundary testing
└── ...                                  # Additional fuzz modules (grammar, serializer, etc.)
```

**ShadowBundle** is a deliberately simple implementation for differential testing:
- No caching (computes everything fresh)
- No optimizations (simple recursive traversal)
- Explicit error handling (no silent failures)

**Run oracle tests:**

```bash
# Run all oracle fuzz tests
uv run pytest tests/fuzz/ -v -m fuzz

# Run state machine fuzzer
uv run pytest tests/fuzz/test_runtime_bundle_oracle.py -v -m fuzz
```

The state machine fuzzer generates random sequences of operations and verifies both implementations produce consistent results.

---

## Depth Exhaustion Testing

`test_core_depth_guard_exhaustion.py` tests behavior at the `MAX_DEPTH` boundary (100 in `constants.py`):

- **99-deep nesting**: Should succeed normally
- **100-deep nesting**: Should hit limit gracefully
- **101-deep nesting**: Should fail cleanly (no crash)

```bash
uv run pytest tests/fuzz/test_core_depth_guard_exhaustion.py -v -m fuzz
```

This ensures the resolver handles pathological inputs without stack overflow or infinite recursion.

---

## Test Markers

FTLLexEngine uses pytest markers to categorize tests:

| Marker | Purpose | When Run |
|--------|---------|----------|
| `@pytest.mark.hypothesis` | Standard Hypothesis tests | CI and fuzzing |
| `@pytest.mark.fuzz` | Intensive fuzz tests | --deep mode only |

Tests marked with `@pytest.mark.fuzz` are skipped in normal runs:

```python
pytestmark = pytest.mark.fuzz  # Module-level marker

@given(ftl=valid_ftl())
@settings(max_examples=10000)
def test_intensive_fuzzing(ftl: str) -> None:
    ...
```

---

## Troubleshooting

### "AF_UNIX path too long" Error

macOS limits Unix socket paths. The script sets `TMPDIR=/tmp` automatically. If running HypoFuzz directly:

```bash
TMPDIR=/tmp uv run hypothesis fuzz tests/
```

### Failures Not Reproducing

Hypothesis stores failures in `.hypothesis/examples/`. If a test passes when you expect failure:

1. The bug may have been fixed
2. The example database may be stale

Try clearing and re-running:

```bash
./scripts/fuzz_hypofuzz.sh --clean
./scripts/fuzz_hypofuzz.sh
```

### Finding the Falsifying Example

The failing example is printed to stdout. Look for:

```
Falsifying example: test_roundtrip(
    ftl='problematic input here',
)
```

Use `--repro` with `--verbose` for full output.

---

## Workers and Metrics

### Multi-Worker Mode (Default for --deep)

HypoFuzz uses Python `multiprocessing` to run N worker processes in
parallel (default: `--workers 4`). Each worker is a separate Python
process with its own memory space. This provides high throughput for
continuous coverage-guided fuzzing.

However, the strategy metrics collector (`tests/strategy_metrics.py`)
runs in-process and cannot aggregate events across worker boundaries.
Each worker accumulates its own event counts independently, and there
is no cross-process shared state.

### --metrics Forces Single-Process Mode

When `--metrics` is enabled, the script bypasses HypoFuzz entirely
and runs `pytest -m fuzz` in a single process. This ensures all
`hypothesis.event()` calls are captured by the same metrics collector:

```bash
# Continuous fuzzing (multi-worker, no detailed metrics)
./scripts/fuzz_hypofuzz.sh --deep

# Single-pass with reliable metrics (single-process pytest)
./scripts/fuzz_hypofuzz.sh --deep --metrics
```

**Trade-off**: `--metrics` mode runs a finite pass (10,000 examples
per test via the `hypofuzz` profile) instead of continuous fuzzing.
Use `--deep` for throughput and `--deep --metrics` for diagnostics.

### Comparison with Atheris

Both fuzzing systems face the same fundamental constraint: metrics
collected in process-local state cannot be shared across forked or
spawned workers. Each system handles it differently:

| Aspect | HypoFuzz | Atheris |
|--------|----------|---------|
| Worker model | Python `multiprocessing` | libFuzzer `fork()` |
| Default workers | 4 (throughput-oriented) | 1 (metrics-reliable) |
| Metrics mode | `--metrics` forces single-process pytest | `--workers 1` (default) |
| Multi-worker metrics | Not collected (bypassed) | Per-worker only, last writer wins |

See [FUZZING_GUIDE.md](FUZZING_GUIDE.md) for the cross-system overview.

---

## Strategy Reference

Custom strategies in `tests/strategies/ftl.py` generate valid FTL constructs:

| Strategy | Description |
|----------|-------------|
| `ftl_identifiers()` | Valid FTL identifiers (`[a-zA-Z][a-zA-Z0-9_-]*`) |
| `ftl_simple_messages()` | Simple message definitions (`id = value`) |
| `ftl_simple_text()` | Text without FTL special characters |
| `ftl_terms()` | Term definitions (`-id = value`) |
| `ftl_placeables()` | Placeable expressions (variables, literals, nested) |
| `ftl_function_references()` | Function calls (`{ NUMBER($x) }`) |
| `ftl_message_references()` | Message references (`{ other-msg }`) |
| `ftl_term_references()` | Term references (`{ -brand }`) |
| `ftl_select_expressions()` | Select expressions with variants |
| `resolver_mixed_args()` | Mixed argument dictionaries for formatting |

**Chaos mode strategies** (for parser stress testing):

| Strategy | Description |
|----------|-------------|
| `ftl_chaos_text()` | Text including FTL structural characters |
| `ftl_boundary_depth_placeables()` | Placeables at MAX_DEPTH boundary |
| `ftl_circular_references()` | A -> B -> A reference patterns |
| `ftl_invalid_ftl()` | Structurally invalid FTL for error handling |
| `ftl_semantically_broken()` | Parses successfully but fails at runtime |

**Usage:**

```python
from hypothesis import given
from tests.strategies.ftl import ftl_simple_messages, resolver_mixed_args

@given(source=ftl_simple_messages(), args=resolver_mixed_args())
def test_bundle_format(source: str, args: dict) -> None:
    bundle = FluentBundle("en_US")
    bundle.add_resource(source)
    # ... assertions
```

---

## Semantic Coverage with Events

HypoFuzz uses code coverage to guide mutation. But code coverage cannot see *semantic* differences - two inputs that execute the same lines but test different logical cases appear identical to the fuzzer.

`hypothesis.event()` creates "virtual branches" that guide HypoFuzz toward semantically interesting inputs even when code paths are identical.

### Why Events Matter

Consider a currency formatting test:

```python
# Without events - fuzzer sees same coverage for JPY and USD
@given(currency=currency_codes)
def test_format_currency(currency: str) -> None:
    result = format_currency(1000, currency)
    assert isinstance(result, str)
```

```python
# With events - fuzzer actively seeks 0, 2, and 3 decimal currencies
from hypothesis import event

@given(currency=currency_by_decimals())  # Strategy emits events
def test_format_currency(currency: str) -> None:
    result = format_currency(1000, currency)
    assert isinstance(result, str)
```

The `currency_by_decimals()` strategy emits `currency_decimals=0`, `currency_decimals=2`, or `currency_decimals=3` events, telling HypoFuzz these are distinct semantic cases to explore.

### Event Taxonomy

Use consistent event naming across the codebase:

| Category | Format | Examples |
|:---------|:-------|:---------|
| Strategy choice | `strategy={variant}` | `strategy=placeable_variable`, `strategy=chaos_prefix_brace` |
| Domain classification | `{domain}={variant}` | `currency_decimals=2`, `territory_region=europe` |
| Boundary/depth | `boundary={name}`, `depth={n}` | `boundary=at_max_depth`, `depth=99` |
| Unicode category | `unicode={category}` | `unicode=emoji`, `unicode=cjk` |
| Property outcome | `outcome={result}` | `outcome=roundtrip_success`, `outcome=immutability_enforced` |
| Test parameter | `{param}={value}` | `thread_count=20`, `cache_size=50`, `reentry_depth=3` |
| State machine | `rule={name}`, `invariant={name}` | `rule=add_simple_message`, `invariant=cache_stats_consistent` |

**Strategy events vs test events:**

* **Strategy events** are emitted by strategy functions in `tests/strategies/`. They are tracked by `EXPECTED_EVENTS` in `tests/strategy_metrics.py` and drive strategy-level coverage metrics.
* **Test events** are emitted by individual `@given` test functions and `@rule`/`@invariant` methods. They guide HypoFuzz per-test but are NOT tracked by `EXPECTED_EVENTS`.

### Writing Event-Aware Tests

**Option 1: Use event-emitting strategies**

Pre-built strategies in `tests/strategies/` emit events automatically:

```python
from tests.strategies.ftl import ftl_placeables  # Emits strategy=placeable_*
from tests.strategies.iso import currency_by_decimals  # Emits currency_decimals=*
from tests.strategies.fiscal import date_by_boundary  # Emits date_boundary=*

@given(source=ftl_placeables())
def test_placeables(source: str) -> None:
    ...
```

**Option 2: Emit events in tests**

For test-specific semantic categories:

```python
from hypothesis import given, event

@given(ftl=valid_ftl())
def test_parser_coverage(ftl: str) -> None:
    result = parse(ftl)

    # Emit events based on parse result characteristics
    if result.errors:
        event("parse_result=has_errors")
    else:
        event("parse_result=clean")

    for entry in result.body:
        event(f"entry_type={type(entry).__name__}")
```

**Option 3: Composite strategies with events**

Create domain-specific strategies:

```python
from hypothesis import event
from hypothesis.strategies import composite

@composite
def ftl_by_complexity(draw):
    complexity = draw(st.sampled_from(["minimal", "moderate", "complex"]))

    match complexity:
        case "minimal":
            source = draw(ftl_simple_messages())
        case "moderate":
            source = draw(ftl_with_placeables())
        case "complex":
            source = draw(ftl_with_selects())

    event(f"ftl_complexity={complexity}")
    return source
```

### Checking Event Diversity

After a `--deep` fuzzing session, the script reports event diversity:

```bash
./scripts/fuzz_hypofuzz.sh --deep --time 300

# Output includes:
# [EVENT DIVERSITY]
# Top 15 events observed:
#   1247  expr_type=Message
#    892  expr_type=Term
#    456  strategy=placeable_variable
#    ...
```

**Good diversity**: Events are distributed across categories, indicating the fuzzer explored varied semantic paths.

**Poor diversity**: One event dominates (e.g., 95% `expr_type=Message`), indicating the fuzzer is stuck in a narrow region.

**Fix poor diversity**: Add more event-emitting strategies or adjust strategy weights to guide exploration.

### Event-Enabled Strategies Reference

| Module | Strategy | Events Emitted |
|:-------|:---------|:---------------|
| `ftl.py` | `ftl_placeables()` | `strategy=placeable_{variable,literal,nested,...}` |
| `ftl.py` | `ftl_chaos_source()` | `strategy=chaos_{prefix_brace,unbalanced,...}` |
| `ftl.py` | `ftl_pathological_nesting()` | `boundary={under,at,over}_max_depth`, `depth={N}` |
| `ftl.py` | `ftl_circular_references()` | `strategy=circular_{self_ref,two_way,...}` |
| `ftl.py` | `ftl_invalid_ftl()` | `strategy=invalid_{unclosed,missing_id,...}` |
| `ftl.py` | `ftl_unicode_stress_text()` | `unicode={bidi,combining,emoji,surrogate,...}` |
| `iso.py` | `currency_by_decimals()` | `currency_decimals={0,2,3}` |
| `iso.py` | `territory_by_region()` | `territory_region={g7,brics,baltic,...}` |
| `iso.py` | `locale_by_script()` | `locale_script={latin,cjk,cyrillic,arabic,other}` |
| `fiscal.py` | `fiscal_delta_by_magnitude()` | `fiscal_delta={zero,small,medium,large}` |
| `fiscal.py` | `date_by_boundary()` | `date_boundary={month_end,year_end,leap_feb,...}` |
| `fiscal.py` | `fiscal_calendar_by_type()` | `fiscal_calendar={calendar_year,uk_japan,...}` |
| `fiscal.py` | `month_end_policy_with_event()` | `month_end_policy={preserve,clamp,strict}` |

---

## Strategy Metrics

The metrics system tracks per-strategy behavior during `--deep` runs, similar to Atheris fuzzer target metrics.

### Enabling Metrics

```bash
# Continuous HypoFuzz (no detailed metrics, multiprocessing)
./scripts/fuzz_hypofuzz.sh --deep

# Single-pass pytest with live metrics every 10 seconds
./scripts/fuzz_hypofuzz.sh --deep --metrics
```

**Note**: `--metrics` mode uses pytest instead of HypoFuzz because HypoFuzz's multiprocessing prevents metrics collection across workers. The trade-off is single-pass execution (10,000 examples) instead of continuous fuzzing.

### What Metrics Track

**Universal metrics:**
- Total event counts across all strategies
- Weight skew detection (intended vs actual distribution)
- Coverage gaps (expected events not observed)
- Performance percentiles (p95, p99, max)

**Per-strategy metrics (with `--metrics`):**

| Metric | Description |
|--------|-------------|
| `invocations` | Total event count for this strategy |
| `wall_time_ms` | Total time spent in this strategy |
| `mean_cost_ms` | Average time per invocation |
| `weight_pct` | Percentage of total invocations |

### Live Output Example

With `--metrics`, every 10 seconds you see:

```
[METRICS] 120s | 45,678 events | 380/s | +11,234 since last
[METRICS] Top: strategy=placeable_variable=1234, currency_decimals=2=890, ...

[METRICS] Per-Strategy Breakdown:
Strategy                       Invocations    Wall Time    Mean Cost   Weight
------------------------------------------------------------------------------
ftl_placeables                       1,234      456.7ms       0.370ms   15.2%
currency_by_decimals                   890      123.4ms       0.139ms   10.9%
fiscal_delta_by_magnitude              456       89.2ms       0.196ms    5.6%
...
------------------------------------------------------------------------------
```

### Output Files

After each session, metrics are saved to:

| File | Contents |
|------|----------|
| `.hypothesis/strategy_metrics.json` | Full metrics report (JSON) |
| `.hypothesis/strategy_metrics_summary.txt` | Human-readable summary (if issues detected) |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STRATEGY_METRICS` | `0` | Enable metrics collection (`1` to enable) |
| `STRATEGY_METRICS_LIVE` | `0` | Enable live console output (`1` to enable) |
| `STRATEGY_METRICS_DETAILED` | `0` | Show per-strategy table (`1` to enable) |
| `STRATEGY_METRICS_INTERVAL` | `10` | Reporting interval in seconds (with --metrics) |

### Weight Skew Detection

The system detects when actual strategy distribution deviates from intended weights by more than 15%. This indicates:

- Strategy filtering issues
- Biased random generation
- Dead code paths

Example skew warning:

```
[WARN] Weight skew detected:
  - strategy=placeable_variable (intended=40.00%, actual=72.00%, deviation=32.00%)
```

### Integration with Events

Strategy metrics work by intercepting `hypothesis.event()` calls. Event-emitting strategies (see Event-Enabled Strategies Reference above) automatically contribute to metrics collection without modification.

---

## Architecture

### How HypoFuzz Works

1. **Discovery**: Finds all `@given` decorated test functions
2. **Execution**: Runs tests with coverage instrumentation
3. **Learning**: Identifies which inputs increase code coverage
4. **Mutation**: Generates new inputs based on coverage feedback
5. **Shrinking**: When a failure is found, shrinks to minimal example

### Database Management

- `.hypothesis/examples/` grows as coverage increases
- Large databases (100k+ entries) are normal for HypoFuzz runs
- The database is gitignored (see `.gitignore`)
- Promote important failures to `@example` decorators for permanent regression tests

---

## See Also

- [FUZZING_GUIDE.md](FUZZING_GUIDE.md) - Overview and comparison
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md) - Native fuzzing with Atheris
- [DOC_06_Testing.md](DOC_06_Testing.md) - Full testing documentation
