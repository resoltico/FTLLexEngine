---
afad: "3.1"
version: "0.96.0"
domain: fuzzing
updated: "2026-01-28"
route:
  keywords: [fuzzing, testing, hypothesis, hypofuzz, atheris, property-based, coverage, crash, security, iso, fiscal, introspection]
  questions: ["how to run fuzzing?", "how to fuzz the parser?", "how to find bugs with fuzzing?", "how to fuzz ISO introspection?", "how to fuzz fiscal calendar?"]
---

# Fuzzing Guide

**Purpose**: Run and understand the parser fuzzing infrastructure.
**Prerequisites**: Basic pytest knowledge.

---

## Quick Start (30 Seconds)

Run fuzzing with one command:

```bash
./scripts/fuzz_hypofuzz.sh
```

You will see either:

- **[PASS]** - All tests passed. Your code is good.
- **[FINDING]** - A bug was found. Follow the "Next steps" shown.

That's it. For deeper testing, read on.

---

## Testing Pyramid Overview

FTLLexEngine uses a layered testing approach, with fuzzing at the top for comprehensive coverage:

```
┌─────────────────────────────────────────────────────────────┐
│                    FUZZING LAYER                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ./scripts/fuzz_hypofuzz.sh --deep (HypoFuzz)             │    │
│  │  - Continuous property-based testing              │    │
│  │  - Coverage-guided exploration                     │    │
│  │  - Finds logic errors, edge cases                 │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ./scripts/fuzz_atheris.sh native (Atheris)             │    │
│  │  - Byte-level mutation chaos                      │    │
│  │  - Crash detection via libFuzzer                 │    │
│  │  - Finds memory corruption, crashes              │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                   UNIT TEST LAYER                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  uv run scripts/test.sh                           │    │
│  │  - Comprehensive unit test suite                  │    │
│  │  - 95%+ coverage requirement                      │    │
│  │  - Deterministic, fast execution                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

Fuzzing finds issues that traditional unit tests miss by exploring vast input spaces automatically.

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

## Understanding the Interface

All fuzzing operations are now split into two specialized scripts:
1.  **Hypothesis/HypoFuzz**: `./scripts/fuzz_hypofuzz.sh` (Python 3.13+)
2.  **Atheris**: `./scripts/fuzz_atheris.sh` (Python 3.11-3.13, Isolated Environment)

| Command | Purpose | Test Selection | Time | Python Support |
|---------|---------|---------------|------|----------------|
| `./scripts/fuzz_hypofuzz.sh` | Quick property tests | `tests/` (pytest) | CPU-dependent | 3.13, 3.14 |
| `./scripts/fuzz_hypofuzz.sh --deep` | Continuous deep fuzzing (HypoFuzz) | **All Hypothesis tests** in `tests/` | Until Ctrl+C | 3.13, 3.14 |
| `./scripts/fuzz_hypofuzz.sh --repro FILE` | Reproduce a failure (Hypothesis) | — | Quick | 3.13, 3.14 |
| `./scripts/fuzz_hypofuzz.sh --list` | List captured failures (Hypothesis) | — | Quick | 3.13, 3.14 |
| | | | | |
| `./scripts/fuzz_atheris.sh TARGET` | Native fuzzing modes | Dynamically discovered `fuzz/fuzz_TARGET.py` | Until Ctrl+C | 3.11-3.13 |
| `./scripts/fuzz_atheris.sh --list` | List captured crashes (Atheris) | — | Quick | 3.11-3.13 |
| `./scripts/fuzz_atheris.sh --corpus` | Check seed corpus health | — | Quick | 3.11-3.13 |

Common options:

| Option | Effect |
|--------|--------|
| `--verbose` | Show detailed progress |
| `--time N` | Run for N seconds |
| `--workers N` | Use N parallel workers |

The structured fuzzing uses grammar-aware fuzzing for better coverage. The `--repro` command reproduces failures and generates `@example` decorators.

---

## Adding New Fuzzers (Dynamic Plugin System)

FTLLexEngine uses a dynamic plugin system for Atheris fuzzers. New fuzzers are automatically discovered from `fuzz/fuzz_*.py` files without editing scripts.

### How It Works
- Each `fuzz/fuzz_*.py` file must start with a standardized plugin header.
- The script scans for headers and extracts the target name and description.
- Targets are listed dynamically in `./scripts/fuzz_atheris.sh --help`.

### Plugin Header Schema
All fuzz_*.py files must include this exact header:

```
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: <name> - <description>
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
```

- `<name>`: The argument name (must match `fuzz_<name>.py`).
- `<description>`: Brief summary for help text.

### Adding a New Fuzzer
1. Create `fuzz/fuzz_myfuzzer.py` with the header.
2. Implement the fuzzer logic.
3. Run `./scripts/fuzz_atheris.sh --help` to verify discovery.
4. Execute with `./scripts/fuzz_atheris.sh myfuzzer`.

This system ensures AI agents can't accidentally alter headers and allows easy extension.

---

## Workflow 1: Quick Check (Recommended)

Use this before committing changes. Takes about 2 minutes.

### Step 1: Run the Check

```bash
./scripts/fuzz_hypofuzz.sh
```

For verbose output showing what's being tested:

```bash
./scripts/fuzz_hypofuzz.sh --verbose
```

### Step 2: Interpret Results

**If you see [PASS]:**
```
[PASS] All property tests passed.

Tests passed: 12

Next: Run './scripts/fuzz_hypofuzz.sh --deep' for deeper testing.
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
  4. Run: ./scripts/fuzz_hypofuzz.sh (to verify fix)
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
   ./scripts/fuzz_hypofuzz.sh
   ```

5. **Commit both** the test file and the fix.

---

## Workflow 2: Deep Fuzzing

Use this for thorough testing before releases or after major changes. Runs **all Hypothesis tests** in the `tests/` directory using HypoFuzz for continuous coverage-guided exploration.

### Step 1: Run Continuous Fuzzing

**Timed run (5 minutes):**
```bash
./scripts/fuzz_hypofuzz.sh --deep --time 300
```

**Endless run (until Ctrl+C):**
```bash
./scripts/fuzz_hypofuzz.sh --deep
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
./scripts/fuzz_hypofuzz.sh --list
```

Then follow the same fix process as Workflow 1.

---

## Workflow 3: Native Fuzzing (Atheris) - Optional

Use this for security audits. Atheris uses raw byte mutation, finding crashes that grammar-aware fuzzing misses.

**Note:** Atheris is optional. Most bugs are found by Hypothesis. Use Atheris only for security-critical releases or when you specifically need byte-level mutation testing.

### Prerequisites: macOS Setup

Atheris requires LLVM and a custom build. We use an **isolated virtual environment** (`.venv-fuzzing`) to prevent other tasks (like multi-version linting) from breaking your fuzzing setup.

> **Note:** Building Atheris from source can take a while to build (± 15 minutes on Apple Mac mini M4) as it compiles LLVM/libFuzzer components.

> **Why this works:** The `fuzz_atheris.sh` script automatically detects ABI mismatches and performs a "Binary Surgery" (reinstall with `-Wl,-rpath` flags). This ensures that when Atheris runs, it finds the modern C++ symbols it needs without interfering with the rest of your system libraries. Using a dedicated `.venv-fuzzing` environment ensures this custom build is not wiped when you switch Python versions for linting or testing.

#### Verification

After setup, verify Atheris works:
```bash
./scripts/fuzz_atheris.sh native --time 10
```

This should run for 10 seconds without errors.

### Common Issues & Troubleshooting

#### `ImportError: symbol not found: __ZNSt3__1...`
This is a C++ ABI mismatch. It happens when Atheris is linked against LLVM but tries to use Apple's system library at runtime. 
**Solution:** Follow the 3-step reinstall above (especially the `uv cache clean` and `--no-binary :all:` parts).

#### `dyld[...]: Symbol not found: ... Referenced from: ... node`
This happens if you exported `DYLD_LIBRARY_PATH` globally in your shell. **This is dangerous and will break other programs like Node.js and system tools.**
**Solution:**
1. Run `unset DYLD_LIBRARY_PATH` immediately.
2. Remove any such exports from your `.zshrc` or `.bash_profile`.
3. Use the **Permanent Fix** above (RPATH) instead of environment variables.

#### `WARNING: Failed to find function "__sanitizer_..."`
You may see 3-4 warnings about missing `__sanitizer_` functions when Atheris starts.
**Status:** **Harmless.** This occurs because the standard Python interpreter is not compiled with AddressSanitizer (ASan). These warnings do not affect coverage collection or fuzzer performance. If you need full ASan support (detecting memory errors in C extensions), you would need a custom ASan-compiled Python, which is generally not required for fuzzing `FTLLexEngine`.


### Native Fuzzing Modes

Targets are dynamically discovered from `fuzz/fuzz_*.py` files (see Adding New Fuzzers section). Current targets include:

| Target | Mode | Focus |
|--------|------|-------|
| `native` | Stability | Crashes, hangs, and memory safety in the FTL parser. |
| `runtime` | End-to-End | Runtime stack, `FluentBundle`, `IntegrityCache`, and **Strict Mode**. |
| `structured` | Structured | Syntactically plausible FTL to explore deeper grammar code paths. |
| `perf` | Performance | Algorithmic complexity issues and ReDoS vulnerabilities. |
| `iso` | Introspection | ISO 3166/4217 territory and currency lookups, type guards, cache. |
| `fiscal` | Fiscal | FiscalCalendar, FiscalDelta, date arithmetic, boundary conditions. |

Run `./scripts/fuzz_atheris.sh --help` to see all available targets.

### Step 1: Run Stability or Runtime Fuzzing

**Check parser stability:**
```bash
./scripts/fuzz_atheris.sh native --time 60
```

**Check runtime and Strict Mode integrity:**
```bash
./scripts/fuzz_atheris.sh runtime --time 60
```

> **Tip:** The `--runtime` fuzzer specifically verifies that `strict=True` bundles correctly raise `FormattingIntegrityError` on any failure and that the `IntegrityCache` remains consistent.

**Endless run:**
```bash
./scripts/fuzz_atheris.sh runtime
```

> **Tip:** You can stop the endless run at any time with `Ctrl+C`. Findings are saved **instantly** to the `.fuzz_corpus` directory as they are discovered. Stopping the script will not lose any previously found crashes.

**Check ISO introspection (requires Babel):**
```bash
./scripts/fuzz_atheris.sh iso --time 60
```

> **Tip:** The `--iso` fuzzer tests ISO 3166-1 territory and ISO 4217 currency lookups via Babel's CLDR data. It verifies type guard consistency, cache integrity, and data class invariants.

**Check fiscal calendar arithmetic:**
```bash
./scripts/fuzz_atheris.sh fiscal --time 60
```

> **Tip:** The `--fiscal` fuzzer tests FiscalCalendar, FiscalDelta, and FiscalPeriod operations including month-end policies, quarter boundaries, and date arithmetic edge cases. No Babel required.


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

**Minimize the crash first** (reduces noise, faster debugging):
```bash
./scripts/fuzz_atheris.sh --minimize .fuzz_corpus/crash_abc123
```

Output:
```
[PASS] Crash minimized successfully.

Original size:  1247 bytes
Minimized size: 42 bytes
Reduction:      97%

Minimized crash saved to: .fuzz_corpus/crash_abc123.minimized

Next steps:
  1. Reproduce: ./scripts/fuzz_hypofuzz.sh --repro .fuzz_corpus/crash_abc123.minimized
  2. Add @example() to test and fix the bug
```

**Reproduce the minimized crash:**
```bash
./scripts/fuzz_hypofuzz.sh --repro .fuzz_corpus/crash_abc123.minimized
```

This generates an `@example()` decorator you can paste into a test.

**View crash content (if needed):**
```bash
xxd .fuzz_corpus/crash_abc123.minimized | head -20
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
./scripts/fuzz_atheris.sh perf --time 60
```

**Endless run:**
```bash
./scripts/fuzz_atheris.sh perf
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

The seed corpus at `fuzz/seeds/` provides high-quality starting points for all fuzzer modes.

### How Seeds Are Used

**Automatic Loading**: All Atheris-based fuzzing modes (`--native`, `--runtime`, `--structured`, `--perf`, `--iso`, `--fiscal`) automatically load seeds from `fuzz/seeds/` at startup. You do not need to pass any additional flags.

**libFuzzer Mechanics**: Under the hood, libFuzzer receives two corpus directories:

```
fuzzer .fuzz_corpus fuzz/seeds [options]
        │            │
        │            └── Read-only seed corpus (curated starting points)
        └── Read-write working corpus (new interesting inputs saved here)
```

At startup, libFuzzer:
1. Loads ALL files from `fuzz/seeds/` as raw bytes
2. Loads any previously-saved inputs from `.fuzz_corpus/`
3. Runs each input through the fuzzer target
4. Keeps inputs that increase code coverage
5. Uses coverage-increasing inputs as mutation bases
6. Saves newly-discovered interesting inputs to `.fuzz_corpus/`

**Cross-Mode Compatibility**: All seeds are passed to all fuzzing modes. libFuzzer intelligently handles this:
- **Text seeds (`.ftl`)**: For parser fuzzers, decoded as UTF-8 FTL source. For binary fuzzers, the text bytes are interpreted as structured data (this is fine - the fuzzer learns what's useful).
- **Binary seeds (`.bin`)**: For binary fuzzers, interpreted as `FuzzedDataProvider` input. For parser fuzzers, decoded as UTF-8 with surrogateescape (produces garbled but processable text).

This cross-pollination is intentional. libFuzzer discovers which seeds are useful for which target through coverage feedback.

### Seed Categories

| Pattern | Purpose | Used By |
|---------|---------|---------|
| `01-20_*.ftl` | FTL grammar features (messages, terms, selects) | All modes |
| `21-29_*.ftl` | Pathological cases (deep nesting, cycles, Unicode) | All modes |
| `runtime_*.bin` | Runtime config (strict mode, caching, corruption) | `--runtime` primarily |
| `iso_*.bin` | ISO 3166/4217 codes (valid, invalid, mixed) | `--iso` primarily |
| `fiscal_*.bin` | Fiscal calendar dates (boundaries, leap years) | `--fiscal` primarily |

### Check Corpus Health

```bash
./scripts/fuzz_atheris.sh --corpus
```

This validates that FTL seeds parse correctly and reports grammar feature coverage.

### Add New Seeds

When the grammar changes or new edge cases are discovered:

1. Create a seed file in `fuzz/seeds/`:
   ```ftl
   # fuzz/seeds/30_new_feature.ftl
   new-feature = { $arg ->
       [case1] Value 1
      *[other] Default
   }
   ```

2. Verify the corpus:
   ```bash
   ./scripts/fuzz_atheris.sh --corpus
   ```

3. Seeds are automatically used in the next fuzzing run.

### Creating Binary Seeds

For `--runtime`, `--iso`, or `--fiscal` modes, you can create targeted binary seeds:

```python
# Example: Create an ISO seed for cache stress testing
import struct

# FuzzedDataProvider expects raw bytes
# iso.py interprets: locale_len(1) + locale + code_len(1) + code + flags(1)
seed = bytes([
    5,                           # locale length
    *b"en_US",                   # locale string
    3,                           # code length
    *b"USD",                     # currency code
    0b00000011,                  # flags: check_territory=True, use_cache=True
])

with open("fuzz/seeds/iso_custom.bin", "wb") as f:
    f.write(seed)

# Verify the seed works
./scripts/fuzz_atheris.sh --corpus
```

### Remove Duplicate Seeds

```bash
uv run python scripts/fuzz_corpus_health.py --dedupe
```

Shows duplicate seeds. Add `--execute` to remove them.

### Working Corpus vs Seed Corpus

| Directory | Purpose | Git Tracked | Persistent |
|-----------|---------|-------------|------------|
| `fuzz/seeds/` | Curated starting points | Yes | Yes |
| `.fuzz_corpus/` | Fuzzer-discovered inputs | No (.gitignore) | Between runs |

The working corpus (`.fuzz_corpus/`) grows as the fuzzer discovers new coverage-increasing inputs. This is normal and beneficial - these discovered inputs are used as starting points in subsequent runs.

---

## Fuzzing Architecture

FTLLexEngine uses a multi-layered fuzzing architecture designed for comprehensive testing of parsing, resolution, and runtime components.

### Test Categorization & Markers

Tests are categorized by purpose and execution characteristics:

| Marker | Purpose | Execution | Included In |
|--------|---------|-----------|-------------|
| `@pytest.mark.property` | Property-based tests using Hypothesis | Normal CI runs | All modes |
| `@pytest.mark.survivability` | Runtime crash/hang detection | Normal CI runs | All modes |
| `@pytest.mark.survivability_extreme` | Extreme load survivability (manual) | Manual execution only | `--deep` only |
| `@pytest.mark.hypofuzz` | Continuous fuzzing targets | Normal CI runs | All modes |
| `@pytest.mark.fuzz` | Dedicated fuzz tests (excluded from CI) | Manual fuzzing only | `--deep` only |

**Key Points:**
- **No marker filtering**: All tests run by default unless explicitly marked with `@pytest.mark.fuzz`
- **Hypothesis requirement**: Only tests using `@given` decorators can be fuzzed
- **CI inclusion**: Tests without `@pytest.mark.fuzz` run in normal CI pipelines

### HypoFuzz Selection Criteria

**HypoFuzz Selection Criteria:**
```bash
# Runs ALL tests in tests/ that use @given decorators
uv run hypothesis fuzz --no-dashboard -n "$WORKERS" -- tests/
```

This means `--deep` mode includes:
- Grammar-based fuzzing tests (`test_grammar_based_fuzzing.py`)
- Runtime survivability tests (`test_runtime_survivability.py`)
- Metamorphic property tests (`test_metamorphic_properties.py`)
- All other Hypothesis tests in the `tests/` directory

### HypoFuzz Integration

**Why HypoFuzz for `--deep` mode:**
- **Coverage-guided**: Learns from execution paths to find new code
- **Continuous**: Runs indefinitely, exploring edge cases
- **Database-driven**: Saves examples and failures for regression testing
- **Multi-worker**: Parallel execution for faster exploration

**Database Files:**
- `.hypothesis/examples/` - Coverage database (preserved across runs)
- `.hypothesis/failures/` - Captured failing examples
- `fuzz/seeds/` - Seed corpus for starting exploration

### Atheris Integration

**Why Atheris for `--native`/`--structured`/`--perf`:**
- **libFuzzer backend**: Industry-standard fuzzing engine
- **Corpus management**: Automatic minimization and corpus evolution
- **Crash isolation**: Precise crash reproduction and minimization
- **Performance profiling**: ReDoS detection with timing analysis

**Corpus Files:**
- `.fuzz_corpus/crash_*` - Crash artifacts
- `fuzz/seeds/` - Grammar seeds for structured fuzzing

### Marker Usage Guidelines

**When to use each marker:**

- `@pytest.mark.property`: Standard Hypothesis property tests that should run in CI
- `@pytest.mark.survivability`: Runtime safety tests (crashes, hangs, memory issues)
- `@pytest.mark.survivability_extreme`: Tests that may be too slow/resource-intensive for CI
- `@pytest.mark.hypofuzz`: Tests specifically designed for continuous fuzzing
- `@pytest.mark.fuzz`: Tests that should ONLY run during dedicated fuzzing sessions

**Example usage:**
```python
# Runs in CI and fuzzing
@pytest.mark.survivability
@given(...)
def test_cache_survives_extreme_conditions(self, ...):
    # Test that may take seconds per example
    pass

# Runs ONLY in dedicated fuzzing (--deep mode)
@pytest.mark.fuzz
@given(...)
def test_parser_fuzz_chaos(self, ...):
    # May take minutes per example, too slow for CI
    pass
```

---

## System Architecture

```
scripts/
  fuzz_hypofuzz.sh       <- Property testing & HypoFuzz
  fuzz_atheris.sh        <- Native Atheris fuzzing & corpus management
  fuzz_corpus_health.py  <- Corpus utility (used by fuzz_atheris.sh)
  fuzz_repro.py          <- Failure reproduction utility

tests/
  test_grammar_based_fuzzing.py    <- Parser property tests
  test_metamorphic_properties.py   <- Metamorphic self-consistency tests
  test_runtime_fuzzing.py          <- Runtime resolution tests
  test_resolver_cycles.py          <- Cycle detection tests
  test_serializer_ast_fuzzing.py   <- AST-first serializer tests
  test_locale_fuzzing.py           <- Locale/plural rule tests
  test_concurrent_access.py        <- Thread safety tests
  strategies/                 <- Hypothesis strategies (ftl.py, iso.py, fiscal.py)

fuzz/
  seeds/                   <- Seed corpus (git tracked)
  stability.py             <- Atheris crash detector (byte-level chaos)
  structured.py            <- Atheris crash detector (grammar-aware)
  perf.py                  <- Atheris performance detector
  runtime.py               <- Atheris runtime stack fuzzer
  iso.py                   <- Atheris ISO 3166/4217 introspection fuzzer
  fiscal.py                <- Atheris fiscal calendar arithmetic fuzzer

.hypothesis/               <- Hypothesis data (git ignored)
  examples/                <- Coverage database
  failures/                <- Extracted failing examples

.fuzz_corpus/              <- Atheris corpus (git ignored)
  crash_*                  <- Crash artifacts
```

---

## Troubleshooting

### Is it hanging?

No. The default profile runs silently and, depending on hardware, can take a long time to complete. Use verbose mode:
```bash
./scripts/fuzz_hypofuzz.sh --verbose
```

### Atheris won't install?

Run the verification script:
```bash
./scripts/fuzz_atheris.sh native
```

Common issues:
- Python 3.14+: Atheris requires Python 3.11-3.13 (see Python Version Requirements below)
- Missing LLVM (`brew install llvm`)
- Using Apple Clang instead of LLVM Clang

### Found a failure, now what?

1. Read the "Falsifying example:" output
2. Add `@example(...)` decorator to the test
3. Fix the bug
4. Run `./scripts/fuzz_hypofuzz.sh` to verify

### Too many failures to handle?

List all captured failures:
```bash
./scripts/fuzz_hypofuzz.sh --list
```

Focus on fixing one at a time. Each fix may resolve others.

### Coverage isn't improving?

Add more seeds to `fuzz/seeds/`. Check what's missing:
```bash
./scripts/fuzz_atheris.sh --corpus
```

### "AF_UNIX path too long" error?

macOS limits Unix socket paths. The scripts set `TMPDIR=/tmp` automatically. If running directly:
```bash
TMPDIR=/tmp uv run hypothesis fuzz ...
```

### Minimization failed or didn't reduce size?

The `--minimize` mode may fail if:
- The crash isn't deterministic (race condition, random state)
- The input is already minimal
- The wrong fuzzer script is being used

Try specifying more time:
```bash
./scripts/fuzz_atheris.sh --minimize .fuzz_corpus/crash_* --time 120
```

If minimization fails consistently, use `--repro` directly on the original crash file.

---

## Python Version Requirements

Different fuzzing tools have different Python version requirements:

| Fuzzing Mode | Python Versions | Tool | Notes |
|--------------|-----------------|------|-------|
| `./scripts/fuzz_hypofuzz.sh` | 3.13, 3.14 | Hypothesis | Property-based tests |
| `./scripts/fuzz_hypofuzz.sh --deep` | 3.13, 3.14 | HypoFuzz | Coverage-guided |
| `./scripts/fuzz_atheris.sh native` | 3.11-3.13 | Atheris | libFuzzer-based |
| `./scripts/fuzz_atheris.sh runtime` | 3.11-3.13 | Atheris | Runtime/Strict Mode |
| `./scripts/fuzz_atheris.sh structured` | 3.11-3.13 | Atheris | Grammar-aware |
| `./scripts/fuzz_atheris.sh perf` | 3.11-3.13 | Atheris | ReDoS detection |
| `./scripts/fuzz_atheris.sh iso` | 3.11-3.13 | Atheris | ISO introspection |
| `./scripts/fuzz_atheris.sh fiscal` | 3.11-3.13 | Atheris | Fiscal calendar |
| `./scripts/fuzz_atheris.sh --minimize` | 3.11-3.13 | Atheris | Crash minimization |

### Why Atheris Requires Python 3.13 or Earlier

Atheris uses libFuzzer which is compiled against specific Python ABIs. The Atheris project has not yet released a version supporting Python 3.14.

### Running Native Fuzzing on Python 3.14

If your default Python is 3.14, switch to 3.13 for native fuzzing:

```bash
# Run native/minimize fuzzing with Python 3.13
./scripts/fuzz_atheris.sh native

# Property-based fuzzing works on Python 3.14
./scripts/fuzz_hypofuzz.sh          # Works on 3.14
./scripts/fuzz_hypofuzz.sh --deep   # Works on 3.14
```

---

## Command Reference

| Task | Command |
|------|---------|
| Quick check | `./scripts/fuzz_hypofuzz.sh` |
| Verbose check | `./scripts/fuzz_hypofuzz.sh --verbose` |
| Deep fuzzing (5 min) | `./scripts/fuzz_hypofuzz.sh --deep --time 300` |
| Deep fuzzing (endless) | `./scripts/fuzz_hypofuzz.sh --deep` |
| Native fuzzing | `./scripts/fuzz_atheris.sh native` |
| Runtime fuzzing | `./scripts/fuzz_atheris.sh runtime` |
| Structured fuzzing | `./scripts/fuzz_atheris.sh structured` |
| Performance fuzzing | `./scripts/fuzz_atheris.sh perf` |
| ISO fuzzing | `./scripts/fuzz_atheris.sh iso` |
| Fiscal fuzzing | `./scripts/fuzz_atheris.sh fiscal` |
| List failures (Hypothesis) | `./scripts/fuzz_hypofuzz.sh --list` |
| List crashes (Atheris) | `./scripts/fuzz_atheris.sh --list` |
| Clean all artifacts | `./scripts/fuzz_hypofuzz.sh --clean && ./scripts/fuzz_atheris.sh --clean` |
| Check corpus | `./scripts/fuzz_atheris.sh --corpus` |
| Replay failures | `uv run pytest tests/ -x -v` |

---


