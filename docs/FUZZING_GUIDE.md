---
afad: "3.1"
version: "0.57.0"
domain: fuzzing
updated: "2026-01-06"
route:
  keywords: [fuzzing, testing, hypothesis, hypofuzz, atheris, property-based, coverage, crash, security]
  questions: ["how to run fuzzing?", "how to fuzz the parser?", "how to find bugs with fuzzing?"]
---

# Fuzzing Guide

**Purpose**: Run and understand the parser fuzzing infrastructure.
**Prerequisites**: Basic pytest knowledge.

---

## Quick Start (30 Seconds)

Run fuzzing with one command:

```bash
./scripts/fuzz.sh
```

You will see either:

- **[PASS]** - All tests passed. Your code is good.
- **[FINDING]** - A bug was found. Follow the "Next steps" shown.

That's it. For deeper testing, read on.

---

## What is Fuzzing?

Fuzzing generates thousands of test inputs automatically, feeding them to your code and watching for problems. Instead of writing test cases by hand, the fuzzer explores the input space for you.

| Problem Type | How Fuzzing Finds It |
|--------------|---------------------|
| Crash on malformed input | Generates garbage until something crashes |
| Infinite loop (hang) | Detects when parsing takes too long |
| ReDoS vulnerability | Finds inputs causing exponential slowdown |
| Logic error | Compares parse-serialize-parse results |

---

## Understanding the Unified Interface

All fuzzing operations use `./scripts/fuzz.sh`:

| Command | Purpose | Time |
|---------|---------|------|
| `./scripts/fuzz.sh` | Quick property tests | CPU-dependent |
| `./scripts/fuzz.sh --deep` | Continuous deep fuzzing (HypoFuzz) | Until Ctrl+C |
| `./scripts/fuzz.sh --native` | Native Atheris byte-level chaos | Until Ctrl+C |
| `./scripts/fuzz.sh --structured` | Structure-aware fuzzing (better coverage) | Until Ctrl+C |
| `./scripts/fuzz.sh --perf` | Performance/ReDoS detection | Until Ctrl+C |
| `./scripts/fuzz.sh --repro FILE` | Reproduce a crash file | Instant |
| `./scripts/fuzz.sh --list` | List captured failures (with ages) | Instant |
| `./scripts/fuzz.sh --clean` | Remove all failure artifacts | Instant |
| `./scripts/fuzz.sh --corpus` | Check seed corpus health | Instant |

Common options:

| Option | Effect |
|--------|--------|
| `--verbose` | Show detailed progress |
| `--time N` | Run for N seconds |
| `--workers N` | Use N parallel workers |
| `--json` | Output JSON (for CI) |

The `--structured` mode uses grammar-aware fuzzing for better coverage. The `--repro` mode reproduces crash files and generates `@example` decorators.

---

## Workflow 1: Quick Check (Recommended)

Use this before committing changes. Takes about 2 minutes.

### Step 1: Run the Check

```bash
./scripts/fuzz.sh
```

For verbose output showing what's being tested:

```bash
./scripts/fuzz.sh --verbose
```

### Step 2: Interpret Results

**If you see [PASS]:**
```
[PASS] All property tests passed.

Tests passed: 12

Next: Run './scripts/fuzz.sh --deep' for deeper testing.
```

Your code is good. You can commit.

**If you see [FINDING]:**
```
[FINDING] Failures detected!

Hypothesis failures: 1

Next steps:
  1. Review the 'Falsifying example:' output above
  2. Add @example(failing_input) decorator to the test
  3. Fix the bug in the parser code
  4. Run: ./scripts/fuzz.sh (to verify fix)
```

A bug was found. Continue to Step 3.

### Step 3: Fix a Finding

1. **Locate the failing input.** Look for "Falsifying example:" in the output:
   ```
   Falsifying example: test_roundtrip(source='message = { $var }')
   ```

2. **Add an @example decorator** to preserve the bug as a regression test:
   ```python
   @example(source='message = { $var }')  # Add this line
   @given(ftl_resource())
   def test_roundtrip(self, source: str) -> None:
       ...
   ```

3. **Fix the bug** in the parser code.

4. **Verify the fix:**
   ```bash
   ./scripts/fuzz.sh
   ```

5. **Commit both** the test file and the fix.

---

## Workflow 2: Deep Fuzzing

Use this for thorough testing before releases or after major changes.

### Step 1: Run Continuous Fuzzing

**Timed run (5 minutes):**
```bash
./scripts/fuzz.sh --deep --time 300
```

**Endless run (until Ctrl+C):**
```bash
./scripts/fuzz.sh --deep
```

Press Ctrl+C when you want to stop. Results are saved automatically.

### Step 2: Interpret Results

The fuzzer shows coverage progress. When stopped, you see:

```
[PASS] Fuzzing completed. No violations detected.

Examples in database: 12847
```

Or if findings were detected:

```
[FINDING] Property violations detected!

Violations found: 2
```

### Step 3: Handle Findings

Findings are saved to `.hypothesis/failures/`. To review:

```bash
./scripts/fuzz.sh --list
```

Then follow the same fix process as Workflow 1.

---

## Workflow 3: Native Fuzzing (Atheris) - Optional

Use this for security audits. Atheris uses raw byte mutation, finding crashes that grammar-aware fuzzing misses.

**Note:** Atheris is optional. Most bugs are found by Hypothesis. Use Atheris only for security-critical releases or when you specifically need byte-level mutation testing.

### Prerequisites: macOS Setup

Atheris requires LLVM. Run this once:

```bash
./scripts/check-atheris.sh
```

If not installed, follow these steps:

```bash
# 1. Install LLVM
brew install llvm

# 2. Build Atheris with LLVM
CLANG_BIN="$(brew --prefix llvm)/bin/clang" \
CC="$(brew --prefix llvm)/bin/clang" \
CXX="$(brew --prefix llvm)/bin/clang++" \
LDFLAGS="-L$(brew --prefix llvm)/lib/c++ -L$(brew --prefix llvm)/lib" \
CPPFLAGS="-I$(brew --prefix llvm)/include" \
uv pip install --reinstall --no-binary atheris atheris

# 3. Verify
uv run python -c "import atheris; print('Atheris OK')"
```

### Step 1: Run Stability Fuzzing

**Timed run (60 seconds):**
```bash
./scripts/fuzz.sh --native --time 60
```

**Endless run:**
```bash
./scripts/fuzz.sh --native
```

### Step 2: Interpret Results

```
Mode:    Native Stability Fuzzing
Engine:  Atheris (libFuzzer)
Workers: 4
```

If a crash is found:
```
[FINDING] STABILITY BREACH DETECTED
Exception: KeyError: 'unexpected_key'
Input size: 42 chars
```

### Step 3: Investigate Crashes

Crash inputs are saved to `.fuzz_corpus/crash_*`.

**View crash content:**
```bash
xxd .fuzz_corpus/crash_* | head -20
```

**Reproduce the crash:**
```python
from ftllexengine.syntax.parser import FluentParserV1
data = open('.fuzz_corpus/crash_abc123', 'rb').read()
FluentParserV1().parse(data.decode('utf-8', errors='replace'))
```

**Create a regression test:**
```python
def test_crash_repro_abc123():
    parser = FluentParserV1()
    data = b'...'  # Paste crash bytes here
    parser.parse(data.decode('utf-8', errors='replace'))
```

---

## Workflow 4: Performance Fuzzing

Use this to find ReDoS and algorithmic complexity bugs.

### Step 1: Run Performance Fuzzer

**Timed run (60 seconds):**
```bash
./scripts/fuzz.sh --perf --time 60
```

**Endless run:**
```bash
./scripts/fuzz.sh --perf
```

### Step 2: Interpret Results

Performance breaches show:
```
[FINDING] PERFORMANCE BREACH DETECTED
Duration: 0.5432s (threshold: 0.1200s)
Input size: 150 chars
Ratio: 4.53x threshold
```

The threshold is 100ms + 20ms per KB. Inputs exceeding this are flagged.

### Step 3: Investigate Slow Inputs

1. Find the slow input in `.fuzz_corpus/crash_*`
2. Profile the parser with that input
3. Identify the bottleneck (usually in parsing loops)
4. Fix the algorithm
5. Re-run to verify

**Note:** False positives can occur if your machine is under load. Re-run on an idle machine.

---

## Corpus Management

The seed corpus at `fuzz/seeds/` provides starting points for fuzzing.

### Check Corpus Health

```bash
./scripts/fuzz.sh --corpus
```

Output shows coverage of grammar features:

```
Feature coverage: 92.3%
  Covered:  attribute, comment, message, select_expression...
  Missing:  deeply_nested

[PASS] Corpus is healthy.
```

### Add New Seeds

When the grammar changes, add new seed files:

1. Create a `.ftl` file in `fuzz/seeds/`:
   ```ftl
   # fuzz/seeds/21_new_feature.ftl
   new-feature = { $arg ->
       [case1] Value 1
      *[other] Default
   }
   ```

2. Verify the corpus:
   ```bash
   ./scripts/fuzz.sh --corpus
   ```

### Remove Duplicate Seeds

```bash
uv run python scripts/corpus-health.py --dedupe
```

This shows which seeds are duplicates. Add `--execute` to actually remove them.

---

## System Architecture

```
scripts/
  fuzz.sh                  <- Unified entry point (use this)
  corpus-health.py         <- Corpus management
  fuzz-hypothesis.sh       <- Internal: HypoFuzz runner
  fuzz-atheris.sh          <- Internal: Atheris runner
  check-atheris.sh         <- Verify Atheris installation

tests/
  test_grammar_based_fuzzing.py    <- Parser property tests
  test_metamorphic_properties.py   <- Metamorphic self-consistency tests
  test_runtime_fuzzing.py          <- Runtime resolution tests
  test_resolver_cycles.py          <- Cycle detection tests
  test_serializer_ast_fuzzing.py   <- AST-first serializer tests
  test_locale_fuzzing.py           <- Locale/plural rule tests
  test_concurrent_access.py        <- Thread safety tests
  strategies.py                    <- Hypothesis strategies

fuzz/
  seeds/                   <- Seed corpus (git tracked)
  stability.py             <- Atheris crash detector (byte-level chaos)
  structured.py            <- Atheris crash detector (grammar-aware)
  perf.py                  <- Atheris performance detector

.hypothesis/               <- Hypothesis data (git ignored)
  examples/                <- Coverage database
  failures/                <- Extracted failing examples

.fuzz_corpus/              <- Atheris corpus (git ignored)
  crash_*                  <- Crash artifacts
```

### The @pytest.mark.fuzz System

Tests marked with `@pytest.mark.fuzz` are excluded from normal test runs:

```python
pytestmark = pytest.mark.fuzz  # All tests in file are fuzz tests
```

This separation exists because fuzz tests:
- Run thousands of examples (slow)
- May find new bugs each run (non-deterministic)
- Are designed for dedicated fuzzing, not CI

**To run fuzz tests explicitly:**
```bash
./scripts/fuzz.sh                    # Via unified interface
uv run pytest -m fuzz tests/         # Direct pytest
```

**Normal tests skip fuzz-marked tests:**
```bash
uv run scripts/test.sh               # Skips fuzz tests
```

---

## Troubleshooting

### Is it hanging?

No. The default profile runs silently and, depending on hardware, can take a long time to complete. Use verbose mode:
```bash
./scripts/fuzz.sh --verbose
```

### Atheris won't install?

Run the verification script:
```bash
./scripts/check-atheris.sh
```

Common issues:
- Python 3.14+: Atheris requires Python 3.11-3.13 (see Python Version Requirements below)
- Missing LLVM (`brew install llvm`)
- Using Apple Clang instead of LLVM Clang

### Found a failure, now what?

1. Read the "Falsifying example:" output
2. Add `@example(...)` decorator to the test
3. Fix the bug
4. Run `./scripts/fuzz.sh` to verify

### Too many failures to handle?

List all captured failures:
```bash
./scripts/fuzz.sh --list
```

Focus on fixing one at a time. Each fix may resolve others.

### Coverage isn't improving?

Add more seeds to `fuzz/seeds/`. Check what's missing:
```bash
./scripts/fuzz.sh --corpus
```

### "AF_UNIX path too long" error?

macOS limits Unix socket paths. The scripts set `TMPDIR=/tmp` automatically. If running directly:
```bash
TMPDIR=/tmp uv run hypothesis fuzz ...
```

---

## Python Version Requirements

Different fuzzing tools have different Python version requirements:

| Fuzzing Mode | Python Versions | Tool | Notes |
|--------------|-----------------|------|-------|
| `./scripts/fuzz.sh` | 3.13, 3.14 | Hypothesis | Property-based tests |
| `./scripts/fuzz.sh --deep` | 3.13, 3.14 | HypoFuzz | Coverage-guided |
| `./scripts/fuzz.sh --native` | 3.11-3.13 | Atheris | libFuzzer-based |
| `./scripts/fuzz.sh --structured` | 3.11-3.13 | Atheris | Grammar-aware |
| `./scripts/fuzz.sh --perf` | 3.11-3.13 | Atheris | ReDoS detection |

### Why Atheris Requires Python 3.13 or Earlier

Atheris uses libFuzzer which is compiled against specific Python ABIs. The Atheris project has not yet released a version supporting Python 3.14.

### Running Native Fuzzing on Python 3.14

If your default Python is 3.14, switch to 3.13 for native fuzzing:

```bash
# Run native fuzzing with Python 3.13
uv run --python 3.13 ./scripts/fuzz.sh --native

# Property-based fuzzing works on Python 3.14
./scripts/fuzz.sh          # Works on 3.14
./scripts/fuzz.sh --deep   # Works on 3.14
```

---

## Command Reference

| Task | Command |
|------|---------|
| Quick check | `./scripts/fuzz.sh` |
| Verbose check | `./scripts/fuzz.sh --verbose` |
| Deep fuzzing (5 min) | `./scripts/fuzz.sh --deep --time 300` |
| Deep fuzzing (endless) | `./scripts/fuzz.sh --deep` |
| Native fuzzing (1 min) | `./scripts/fuzz.sh --native --time 60` |
| Performance fuzzing | `./scripts/fuzz.sh --perf --time 60` |
| List failures | `./scripts/fuzz.sh --list` |
| Clean all artifacts | `./scripts/fuzz.sh --clean` |
| Reproduce crash | `./scripts/fuzz.sh --repro .fuzz_corpus/crash_*` |
| Check corpus | `./scripts/fuzz.sh --corpus` |
| Replay failures | `uv run pytest tests/ -x -v` |

---

## For AI Agents

All fuzzing outputs include JSON summaries for automation:

```bash
./scripts/fuzz.sh --json
```

Output (pass):
```json
{"mode":"check","status":"pass","tests_passed":"12","tests_failed":"0","hypothesis_failures":"0"}
```

Output (finding):
```json
{
  "mode": "check",
  "status": "finding",
  "tests_passed": "11",
  "tests_failed": "1",
  "hypothesis_failures": "1",
  "first_failure": {
    "test": "tests/test_grammar_based_fuzzing.py::test_roundtrip",
    "input": "ftl='msg = { $x }'",
    "error": "AssertionError"
  }
}
```

The `first_failure` object is included when failures are detected, containing:
- `test`: Full test path (file::function)
- `input`: Falsifying example (truncated to 200 chars)
- `error`: Exception type

### Crash Reproduction JSON

The repro script also supports JSON output:

```bash
uv run python scripts/repro.py --json .fuzz_corpus/crash_*
```

Output (finding):
```json
{
  "result": "finding",
  "file": ".fuzz_corpus/crash_abc123",
  "input_length": 42,
  "has_invalid_utf8": false,
  "exception_type": "KeyError",
  "exception_message": "unexpected_key",
  "example_decorator": "@example(ftl='...')"
}
```

Output (pass):
```json
{
  "result": "pass",
  "file": "fuzz/seeds/01_simple.ftl",
  "input_length": 150,
  "has_invalid_utf8": false,
  "entry_count": 5,
  "message_count": 4
}
```

Parse the summary to detect findings programmatically. Exit codes:
- `0`: Pass (no findings)
- `1`: Finding (failures detected)
- `2`: Error (script failed to run)
- `3`: Python version incompatible (Atheris modes require Python 3.11-3.13)
