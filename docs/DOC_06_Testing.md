---
afad: "3.1"
version: "0.113.0"
domain: TESTING
updated: "2026-02-20"
route:
  keywords: [pytest, hypothesis, fuzz, marker, profile, conftest, fixture, test.sh, metrics]
  questions: ["how to run tests?", "how to skip fuzz tests?", "what hypothesis profiles exist?", "what test markers are available?", "how to see strategy metrics?"]
---

# DOC_06_Testing

Testing infrastructure reference. Pytest configuration, Hypothesis profiles, markers, scripts, contracts.

---

## Test Categories

### Categories

| Category | Location | Execution | Duration | Marker |
|:---------|:---------|:----------|:---------|:-------|
| Unit | `tests/test_*.py` | `uv run scripts/test.sh` | Seconds | N/A |
| Property | `tests/test_*_property.py` | `uv run scripts/test.sh` | Minutes | N/A |
| Fuzzing | `tests/fuzz/*.py` | `pytest -m fuzz` | 10+ min | `fuzz` |
| Oracle | `tests/fuzz/test_runtime_bundle_oracle.py` | `pytest -m fuzz` | 10+ min | `fuzz` |
| Depth | `tests/fuzz/test_core_depth_guard_exhaustion.py` | `pytest -m fuzz` | 5+ min | `fuzz` |

### Constraints
- Categories are mutually exclusive: No.
- Default category: Unit.
- Property tests use Hypothesis with moderate `max_examples` (50-500).
- Fuzzing tests use Hypothesis with high `max_examples` (500-1500).

---

## `pytest.mark.fuzz`

### Rationale
Fuzzing tests use high `max_examples` (500-1500) and take 10+ minutes to complete; excluding them from normal test runs keeps `uv run scripts/test.sh` fast while preserving the option for dedicated deep testing.

### Usage
```python
@pytest.mark.fuzz
def test_example() -> None: ...

# File-level:
pytestmark = pytest.mark.fuzz
```

### Behavior

| Trigger | Action |
|:--------|:-------|
| Normal test run (`pytest tests/`) | Test SKIPPED |
| Marker filter (`pytest -m fuzz`) | Test RUNS |
| Specific file (`pytest tests/fuzz/test_syntax_parser_grammar.py`) | Test RUNS (bypass) |

### Constraints
- Location: Defined in `tests/conftest.py`.
- Arguments: None.
- Run: `pytest -m fuzz` or `./scripts/fuzz_hypofuzz.sh --deep`.
- Skip: `uv run scripts/test.sh` (default behavior).

---

## `pytest_configure`

### Signature
```python
def pytest_configure(config: pytest.Config) -> None:
```

### Parameters

| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `config` | `pytest.Config` | Y | Pytest configuration object. |

### Behavior

| Phase | Action |
|:------|:-------|
| Configure | Registers `fuzz` marker via `addinivalue_line`. |

### Constraints
- Return: None.
- Location: `tests/conftest.py`.
- Hook Type: configure.

---

## `pytest_collection_modifyitems`

### Signature
```python
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item]
) -> None:
```

### Parameters

| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `config` | `pytest.Config` | Y | Pytest configuration object. |
| `items` | `list[pytest.Item]` | Y | Collected test items. |

### Behavior

| Phase | Action |
|:------|:-------|
| Collection | Adds skip marker to fuzz-tagged tests unless bypass condition met. |

### Constraints
- Return: None.
- Location: `tests/conftest.py`.
- Hook Type: collect.
- Bypass conditions: `-m fuzz` in args OR fuzz-related file patterns in args.

---

## `pytest_runtest_makereport`

### Signature
```python
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None]
) -> None:
```

### Parameters

| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `item` | `pytest.Item` | Y | Test item being reported on. |
| `call` | `pytest.CallInfo[None]` | Y | Call information with exception details. |

### Behavior

| Phase | Action |
|:------|:-------|
| Report | Detects Hypothesis failures via "Falsifying example" in exception. |
| Report | Generates standalone `repro_crash_<timestamp>_<hash>.py` script. |
| Report | Writes JSON metadata to `.hypothesis/crashes/`. |

### Output Files

| File | Contents |
|:-----|:---------|
| `repro_crash_<ts>_<hash>.py` | Standalone reproduction script |
| `crash_<ts>_<hash>.json` | Machine-readable crash metadata |

### Constraints
- Return: None.
- Location: `tests/conftest.py`.
- Hook Type: runtest.
- Trigger: Only on test failures containing "Falsifying example".

---

## Strategy Metrics Collection

### Hooks

Two session hooks in `tests/conftest.py` manage strategy metrics:

| Hook | Phase | Action |
|:-----|:------|:-------|
| `pytest_sessionstart` | Start | Enable metrics, install event hook |
| `pytest_sessionfinish` | End | Write JSON report, stop live reporter |

### Enabling Conditions

Metrics are automatically enabled when any of:
- `STRATEGY_METRICS=1` environment variable
- `HYPOTHESIS_PROFILE=hypofuzz`
- Running with `-m fuzz` marker

### Event Interception

The `_install_event_hook()` function patches `hypothesis.event()` to also record to the metrics collector:

```python
_original_event = hypothesis.event
hypothesis.event = _wrapped_event  # Calls original + records metrics
```

This enables automatic metrics capture from all event-emitting strategies without modifying strategy code.

### Output Files

| File | When Generated | Contents |
|:-----|:---------------|:---------|
| `.hypothesis/strategy_metrics.json` | Every session | Full metrics report |
| `.hypothesis/strategy_metrics_summary.txt` | If issues detected | Human-readable summary |

### Per-Strategy Metrics

With `--metrics` flag (or `STRATEGY_METRICS_DETAILED=1`), tracks per strategy:
- `invocations`: Total event count
- `wall_time_ms`: Total execution time
- `mean_cost_ms`: Average time per invocation
- `weight_pct`: Percentage of total events

### Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `STRATEGY_METRICS` | `0` | Enable collection |
| `STRATEGY_METRICS_LIVE` | `0` | Enable live console output |
| `STRATEGY_METRICS_DETAILED` | `0` | Show per-strategy table |
| `STRATEGY_METRICS_INTERVAL` | `10` | Live reporting interval (seconds) |

---

## Hypothesis Profiles

### Registration
```python
from hypothesis import settings, Phase, Verbosity

settings.register_profile(
    name,
    max_examples=N,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    derandomize=bool,
    verbosity=Verbosity.X,
)
```

### Registered Profiles

| Profile | `max_examples` | `derandomize` | `deadline` | Use Case |
|:--------|---------------:|:--------------|:-----------|:---------|
| `dev` | 500 | False | default | Local development |
| `ci` | 50 | True | default | GitHub Actions |
| `verbose` | 100 | False | default | Debugging |
| `hypofuzz` | 10000 | False | None | Coverage-guided --deep runs |
| `stateful_fuzz` | 500 | False | None | RuleBasedStateMachine tests |

### Selection Logic

| Priority | Condition | Profile |
|---------:|:----------|:--------|
| 1 | `HYPOTHESIS_PROFILE=<name>` env var | Explicit override |
| 2 | `CI=true` env var | `ci` |
| 3 | Default | `dev` |

### Constraints
- Location: `tests/conftest.py`.
- Override: `HYPOTHESIS_PROFILE=verbose pytest tests/`.
- Note: Individual `@settings(max_examples=N)` overrides profile.

---

## `scripts/test.sh`

### Purpose
Run full test suite with coverage enforcement.

### Invocation
```bash
uv run scripts/test.sh [--quick] [--ci] [--no-clean] [-- pytest-args]
```

### Options

| Option | Default | Description |
|:-------|:--------|:------------|
| `--quick` | Off | Skip coverage measurement |
| `--ci` | Off | CI mode, verbose output |
| `--no-clean` | Off | Preserve pytest caches |
| `--` | N/A | Pass remaining args to pytest |

### Environment

| Variable | Default | Description |
|:---------|:--------|:------------|
| `CI` | `false` | Triggers `ci` Hypothesis profile |
| `HYPOTHESIS_PROFILE` | auto | Override profile selection |

### Exit Codes

| Code | Meaning |
|-----:|:--------|
| 0 | All tests passed, coverage >= 95% |
| 1 | Test failures or coverage below threshold |

### Output

| Format | Location |
|:-------|:---------|
| JSON summary | stdout (`[SUMMARY-JSON-BEGIN]...[SUMMARY-JSON-END]`) |
| Coverage XML | `coverage.xml` |

---

## `scripts/fuzz_hypofuzz.sh` (HypoFuzz Interface)

### Purpose
Entry point for HypoFuzz-based fuzzing operations.

### Invocation
```bash
./scripts/fuzz_hypofuzz.sh [MODE] [OPTIONS]
```

### Modes

| Mode | Description |
|:-----|:------------|
| (default) | Fast property tests (500 examples) |
| `--deep` | Continuous HypoFuzz (until Ctrl+C) |
| `--preflight` | Audit test infrastructure (events, strategies) |
| `--repro FILE` | Reproduce crash file |
| `--list` | List captured failures (with ages) |
| `--clean` | Remove all failure artifacts |

### Options

| Option | Default | Description |
|:-------|:--------|:------------|
| `--json` | Off | Output JSON for CI |
| `--verbose` | Off | Detailed progress |
| `--metrics` | Off | Single-pass pytest mode with per-strategy metrics (10s interval) |
| `--workers N` | 4 | Parallel workers |
| `--time N` | Endless | Time limit (seconds) |

### Exit Codes

| Code | Meaning |
|-----:|:--------|
| 0 | All tests passed, no findings |
| 1 | Findings detected |
| 2 | Error (environment/script) |
| 3 | Python version incompatible (Atheris requires 3.11-3.13) |

---

## `scripts/fuzz_atheris.sh`

### Purpose
Byte-level mutation fuzzing with Atheris/libFuzzer.

### Invocation
```bash
./scripts/fuzz_atheris.sh [MODE] [OPTIONS]
```

### Modes

| Mode | Description |
|:-----|:------------|
| (default) | Interactive target selection |
| `--target NAME` | Run specific target |
| `--repro FILE` | Reproduce crash file |
| `--list` | List available targets |

### Options

| Option | Default | Description |
|:-------|:--------|:------------|
| `--workers N` | 4 | Number of parallel workers |
| `--time N` | Endless | Time limit (seconds) |

### Available Targets

| Target | Strategy | Use Case |
|:-------|:---------|:---------|
| `fuzz_roundtrip` | Parse-serialize roundtrip | Parser/serializer consistency |
| `fuzz_structured` | Grammar-aware generation | Deep logic bugs |
| `fuzz_oom` | Memory exhaustion | Resource limits |
| `fuzz_serializer` | Serializer edge cases | Whitespace/escaping correctness |
| `fuzz_runtime` | Bundle format operations | Runtime resolution bugs |
| `fuzz_builtins` | Built-in functions | NUMBER/DATETIME/CURRENCY edge cases |
| `fuzz_numbers` | Number formatting | Locale-aware number handling |
| `fuzz_currency` | Currency parsing | Symbol detection, ambiguity |
| `fuzz_fiscal` | Fiscal calendar | Date arithmetic correctness |
| `fuzz_plural` | Plural rules | CLDR plural category selection |
| `fuzz_iso` | ISO introspection | Territory/currency lookups |
| `fuzz_integrity` | Data integrity | Cache, error immutability |
| `fuzz_cache` | IntegrityCache | Checksum, write-once, eviction |
| `fuzz_bridge` | Function bridge | Custom function invocation |
| `fuzz_graph` | Dependency graph | Cycle detection, chain analysis |
| `fuzz_lock` | RWLock | Concurrency, timeout behavior |
| `fuzz_scope` | Scope resolution | Variable/term scoping |

### Environment

| Variable | Default | Description |
|:---------|:--------|:------------|
| `TMPDIR` | `/tmp` | Temp directory |

### Exit Codes

| Code | Meaning |
|-----:|:--------|
| 0 | Completed without crashes |
| 1+ | Crash detected |
| 3 | Python version incompatible |

### Output

| Format | Location |
|:-------|:---------|
| JSON summary | stdout (`[SUMMARY-JSON-BEGIN]...[SUMMARY-JSON-END]`) |
| Crash files | `.fuzz_atheris_corpus/<target>/crash_*` |

---

## Fuzz Exclusion Behavior

### Normal Test Run

```
pytest tests/
    |
    +-- test_syntax_parser.py              [RUN]
    +-- test_syntax_parser_property.py     [RUN]
    +-- tests/fuzz/test_syntax_parser_grammar.py
    |       +-- has pytestmark = fuzz
    |       +-- conftest adds skip marker  [SKIP]
    +-- tests/fuzz/test_runtime_bundle_oracle.py
            +-- has pytestmark = fuzz
            +-- conftest adds skip marker  [SKIP]
```

### Explicit Fuzz Run

```
pytest -m fuzz
    |
    +-- test_syntax_parser.py              [SKIP - no fuzz marker]
    +-- tests/fuzz/test_syntax_parser_grammar.py
    |       +-- has pytestmark = fuzz      [RUN]
    +-- tests/fuzz/test_runtime_bundle_oracle.py
            +-- has pytestmark = fuzz      [RUN]
```

### Specific File Bypass

```
pytest tests/fuzz/test_runtime_bundle_oracle.py
    |
    +-- conftest detects tests/fuzz/ path prefix
    +-- Bypass skip logic
    +-- All tests in file                  [RUN]
```

### Constraints
- Logic location: `tests/conftest.py:pytest_collection_modifyitems`.
- Bypass: Target file explicitly or use `-m fuzz`.
- Fuzz patterns: `tests/fuzz/` directory (any file directly invoked from this path prefix).

---

## Parser Exception Contract

### Rule
Parser must only raise `ValueError`, `RecursionError`, or `MemoryError` on invalid input.

### Allowed

| Exception | Condition |
|:----------|:----------|
| `ValueError` | Invalid syntax, malformed input |
| `RecursionError` | Deeply nested expressions exceeding stack |
| `MemoryError` | Extremely large input exhausting memory |

### Violation

| Trigger | Result |
|:--------|:-------|
| Any other exception type | `pytest.fail()` with exception details |

### Location
- Enforced in: `src/ftllexengine/syntax/parser/`.
- Tested by: `tests/fuzz/test_syntax_parser_grammar.py:test_random_input_stability`.

---

## Performance Contract

### Rule
Parser must complete in adaptive time threshold based on input size.

### Allowed

| Input Size | Threshold |
|-----------:|----------:|
| 1 KB | 120ms |
| 10 KB | 300ms |
| 50 KB | 1100ms |

Formula: `threshold = 100ms + (20ms * input_size_kb)`

### Violation

| Trigger | Result |
|:--------|:-------|
| Exceeds threshold | `SlowParsing` exception from Atheris target |

### Location
- Enforced in: `fuzz_atheris/fuzz_perf.py`.
- Tested by: `./scripts/fuzz_atheris.sh perf`.

---

## Test Artifact Storage

| Location | Contents | Git Status | Distinguishable? |
|:---------|:---------|:-----------|:-----------------|
| `.hypothesis/` | Entire Hypothesis database | Ignored | N/A |
| `.hypothesis/examples/` | Coverage + failures mixed | Ignored | No |
| `.hypothesis/crashes/` | Portable crash reproduction files | Ignored | Yes (auto-generated) |
| `.hypothesis/hypofuzz.log` | HypoFuzz session log | Ignored | N/A |
| `.hypothesis/strategy_metrics.json` | Strategy metrics report | Ignored | N/A |
| `.hypothesis/strategy_metrics_summary.txt` | Human-readable summary | Ignored | N/A |
| `.pytest_cache/` | Pytest cache | Ignored | N/A |
| `.fuzz_atheris_corpus/` | Atheris working corpus | Ignored | N/A |
| `.fuzz_atheris_corpus/*/crash_*` | Crash artifacts | Ignored | Yes (prefix) |
| `fuzz_atheris/seeds/` | Atheris seed corpus | Tracked | N/A |
| `coverage.xml` | Coverage report | Ignored | N/A |

### Automatic Failure Capture

The `pytest_runtest_makereport` hook in `conftest.py` automatically generates crash files:

```bash
./scripts/fuzz_hypofuzz.sh --list  # List captured failures
```

### Hypothesis Bug Preservation

When Hypothesis finds a failing input:

1. **Automatic**: `pytest_runtest_makereport` hook generates `.hypothesis/crashes/repro_crash_*.py`
2. **Manual**: Promote the failing example to an `@example()` decorator

```python
from hypothesis import example, given
from hypothesis import strategies as st

@given(st.text())
@example("the_failing_input")  # Preserved in version control
def test_parser_handles_input(text: str) -> None:
    ...
```

**Crash reproduction:**
```bash
# Run auto-generated reproduction script
uv run python .hypothesis/crashes/repro_crash_20260204_103000_a1b2c3d4.py

# Or use the repro tool for JSON output
uv run python scripts/fuzz_hypofuzz_repro.py --json test_module::test_name
```

**Rationale**: HypoFuzz stores 100k+ coverage examples in `.hypothesis/examples/`. Committing would add 100MB+ to git. Instead:
1. Keep corpus local to each machine
2. Auto-capture crashes to `.hypothesis/crashes/` (portable, shareable)
3. Promote failures to `@example()` decorators (version controlled)
4. Each machine rebuilds its own coverage corpus

### Atheris Bug Preservation

When Atheris finds a crash, use the replay script for reproduction:

| Step | Action |
|:-----|:-------|
| 1 | Reproduce: `uv run python fuzz_atheris/fuzz_atheris_replay_finding.py .fuzz_atheris_corpus/<target>/crash_*` |
| 2 | Add `@example(...)` decorator to relevant test function |
| 3 | Fix the bug, run tests to confirm |
| 4 | Delete crash file after committing test |

**Crash-proof reporting**: Fuzz targets emit `[SUMMARY-JSON-BEGIN]...[SUMMARY-JSON-END]`
on exit via atexit handler, ensuring metadata is never lost on crash.

**Rationale**: `.fuzz_atheris_corpus/` is git-ignored (contains binary seeds, machine-specific).
Unit tests with literal inputs are permanent, readable, and version-controlled.

---

## File Pattern Reference

| Pattern | Category | Marker | Notes |
|:--------|:---------|:-------|:------|
| `tests/test_*.py` | Unit | N/A | Standard tests |
| `tests/test_*_property.py` | Property | N/A | Hypothesis property-based |
| `tests/fuzz/*.py` | Fuzzing | `fuzz` | Excluded from normal runs |
| `tests/fuzz/test_runtime_bundle_oracle.py` | Oracle | `fuzz` | Differential testing vs ShadowBundle |
| `tests/fuzz/test_core_depth_guard_exhaustion.py` | Depth | `fuzz` | MAX_DEPTH boundary testing |
| `tests/fuzz/shadow_bundle.py` | Support | N/A | Reference implementation (not a test) |

---

## Hypothesis Precedence

| Priority | Source | Example | Notes |
|---------:|:-------|:--------|:------|
| 1 (highest) | `@settings` decorator | `@settings(max_examples=1500)` | Per-test override |
| 2 | `@settings` with profile | `@settings(settings.get_profile("dev"))` | Explicit profile use |
| 3 | Loaded profile | `settings.load_profile("dev")` | From conftest.py |
| 4 (lowest) | Default | `max_examples=100` | Hypothesis default |

### Interaction Rules
- Decorator `@settings(max_examples=N)` ALWAYS overrides profile.
- Fuzzing tests intentionally hardcode high values to ensure deep exploration.
- Profile-based testing only works when tests don't specify their own settings.

---

## Design Decisions

### Marker-Based Exclusion
**Question**: How to separate fast unit tests from slow fuzzing tests?
**Decision**: `tests/fuzz/` subdirectory + `@pytest.mark.fuzz` marker + conftest.py skip logic.
**Rationale**: Directory isolates fuzz tests visually and structurally; marker integrates with
pytest `-m` filter; conftest enforces skipping in normal runs while allowing direct file bypass.
**Alternatives Rejected**:
- Naming convention only: No enforcement mechanism, easily forgotten.
- Environment variable check in tests: Invisible, hard to audit.

### Profile Auto-Detection
**Question**: How to configure Hypothesis for different environments?
**Decision**: Auto-detect CI vs local via environment variables.
**Rationale**: Zero-config for common cases; explicit override available.
**Alternatives Rejected**:
- Always use same settings: CI would be slow, local would miss bugs.
- Require explicit configuration: Developer friction, easy to forget.

### File Bypass Logic
**Question**: What if developer wants to run fuzz tests directly?
**Decision**: Detect specific file in pytest args and bypass skip.
**Rationale**: Allows `pytest tests/fuzz/test_syntax_parser_grammar.py` without `-m fuzz`.
**Alternatives Rejected**:
- Always require `-m fuzz`: Extra typing, breaks muscle memory.
- Never skip if any fuzz file mentioned: Too broad, confusing.

---

## Quirks

| Quirk | Behavior | Reason |
|:------|:---------|:-------|
| File bypass | `pytest tests/fuzz/test_syntax_parser_grammar.py` runs despite fuzz marker | Detected in `pytest_collection_modifyitems` via `config.invocation_params.args` |
| String matching | Bypass uses substring match, not exact | Allows both absolute and relative paths |
| Profile load timing | Profiles loaded at import time in conftest.py | Must happen before any test collection |
| `pytestmark` position | Must be before any `from` imports in file | Python module-level variable ordering |

---

## Pitfalls

| Mistake | Consequence | Correct Approach |
|:--------|:------------|:-----------------|
| Commit `.hypothesis/` | 100MB+ git bloat from HypoFuzz corpus | Keep ignored; use `.hypothesis/crashes/` for portable repros |
| Rely on `.fuzz_atheris_corpus/*/crash_*` | Bug lost when files cleaned up | Create unit test with crash input as literal |
| Hardcode `@settings(max_examples=N)` | Overrides profile, CI takes forever | Omit decorator or use profile-based settings for fuzz-only |
| Forget `pytestmark` in new fuzz file | Tests run in normal suite, slow | Add `pytestmark = pytest.mark.fuzz` at top of file |
| Run `pytest tests/` expecting fuzz tests | Fuzz tests silently skipped | Use `pytest -m fuzz` or `./scripts/fuzz_hypofuzz.sh --deep` |
| Set `HYPOTHESIS_PROFILE` wrong | Unexpected example counts | Valid values: `dev`, `ci`, `verbose` |
| Long socket paths in fuzzing | `AF_UNIX path too long` error | Scripts set `TMPDIR=/tmp` automatically |
| Ignore `.hypothesis/crashes/` | Miss portable crash reproductions | Check for auto-generated `repro_crash_*.py` scripts |

---

## See Also

- [FUZZING_GUIDE.md](FUZZING_GUIDE.md): Overview and comparison of fuzzing approaches
- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md): HypoFuzz operational guide
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md): Atheris operational guide
- [tests/conftest.py](../tests/conftest.py): Profile, marker, and crash recording configuration
- [tests/fuzz/](../tests/fuzz/): Oracle and depth exhaustion fuzz tests
