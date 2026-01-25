---
afad: "3.1"
version: "0.90.0"
domain: fuzzing
updated: "2026-01-24"
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

## Understanding the Interface

All fuzzing operations use `./scripts/fuzz.sh`:

| Command | Purpose | Test Selection | Time |
|---------|---------|---------------|------|
| `./scripts/fuzz.sh` | Quick property tests | `test_grammar_based_fuzzing.py` only | CPU-dependent |
| `./scripts/fuzz.sh --deep` | Continuous deep fuzzing (HypoFuzz) | **All Hypothesis tests** in `tests/` | Until Ctrl+C |
| `./scripts/fuzz.sh --native` | Native fuzzing with Atheris | Custom targets in `fuzz/stability.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --runtime` | End-to-end runtime fuzzing | Custom targets in `fuzz/runtime.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --structured` | Structure-aware fuzzing with Atheris | Custom targets in `fuzz/structured.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --perf` | Performance fuzzing to detect ReDoS | Custom targets in `fuzz/perf.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --iso` | ISO 3166/4217 introspection fuzzing | Custom targets in `fuzz/iso.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --fiscal` | Fiscal calendar arithmetic fuzzing | Custom targets in `fuzz/fiscal.py` | Until Ctrl+C |
| `./scripts/fuzz.sh --repro FILE` | Reproduce a crash file | — | Quick |
| `./scripts/fuzz.sh --minimize FILE` | Minimize crash to smallest reproducer | — | Quick |
| `./scripts/fuzz.sh --list` | List captured failures (with ages) | — | Quick |
| `./scripts/fuzz.sh --clean` | Remove all failure artifacts | — | Quick |
| `./scripts/fuzz.sh --corpus` | Check seed corpus health | — | Quick |

Common options:

| Option | Effect |
|--------|--------|
| `--verbose` | Show detailed progress |
| `--time N` | Run for N seconds |
| `--workers N` | Use N parallel workers |
| `--json` | Output JSON (for CI) |

The `--structured` mode uses grammar-aware fuzzing for better coverage. The `--repro` mode reproduces crash files and generates `@example` decorators. The `--minimize` mode uses libFuzzer to reduce a crash file to the smallest input that still triggers the crash.

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

Use this for thorough testing before releases or after major changes. Runs **all Hypothesis tests** in the `tests/` directory using HypoFuzz for continuous coverage-guided exploration.

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

Atheris requires LLVM and a custom build. We use an **isolated virtual environment** (`.venv-fuzzing`) to prevent other tasks (like multi-version linting) from breaking your fuzzing setup.

Run the check script:

```bash
./scripts/check-atheris.sh
```

If Atheris is missing or identifies an ABI mismatch, run with the `--install` flag:

```bash
./scripts/check-atheris.sh --install
```

This will automatically:
1. Install LLVM via Homebrew (if missing).
2. Create/update the isolated `.venv-fuzzing` environment.
3. Build Atheris from source with the correct `RPATH` settings.

#### Manual Fail-safe (If Script Fails)

If the script fails, you can run the build command manually. Ensure you target the correct environment:

```bash
# 1. Clean cache
uv cache clean atheris

# 2. Build with LLVM toolchain
CLANG_BIN="$(brew --prefix llvm)/bin/clang" \
CC="$(brew --prefix llvm)/bin/clang" \
CXX="$(brew --prefix llvm)/bin/clang++" \
LDFLAGS="-L$(brew --prefix llvm)/lib/c++ -L$(brew --prefix llvm)/lib -Wl,-rpath,$(brew --prefix llvm)/lib/c++" \
CPPFLAGS="-I$(brew --prefix llvm)/include" \
UV_PROJECT_ENVIRONMENT=".venv-fuzzing" \
uv pip install --reinstall --no-cache-dir --no-binary :all: atheris

# 3. Verify
./scripts/check-atheris.sh
```

> **Note:** Building Atheris from source can take a while to build (± 15 minutes on Apple Mac mini M4) as it compiles LLVM/libFuzzer components.

> **Why this works:** The `-Wl,-rpath` flag embeds the location of LLVM's libc++ directly into the Atheris binary. This ensures that when Atheris runs, it finds the modern C++ symbols it needs without interfering with the rest of your system libraries. Using a dedicated `.venv-fuzzing` environment ensures this custom build is not wiped when you switch Python versions for linting or testing.

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

```bash
uv run --python 3.13 ./scripts/fuzz.sh --native
```

#### `WARNING: Failed to find function "__sanitizer_..."`
You may see 3-4 warnings about missing `__sanitizer_` functions when Atheris starts.
**Status:** **Harmless.** This occurs because the standard Python interpreter is not compiled with AddressSanitizer (ASan). These warnings do not affect coverage collection or fuzzer performance. If you need full ASan support (detecting memory errors in C extensions), you would need a custom ASan-compiled Python, which is generally not required for fuzzing `FTLLexEngine`.


### Native Fuzzing Modes

| Mode | Script | Target | Focus |
|------|--------|--------|-------|
| `--native` | `fuzz/stability.py` | Parser Core | Crashes, hangs, and memory safety in the FTL parser. |
| `--runtime` | `fuzz/runtime.py` | Runtime stack | `FluentBundle`, `IntegrityCache`, and **Strict Mode**. |
| `--structured` | `fuzz/structured.py` | Parser & Grammar | Syntactically plausible FTL to explore deeper grammar code paths. |
| `--perf` | `fuzz/perf.py` | Performance Regress | Algorithmic complexity issues and ReDoS vulnerabilities. |
| `--iso` | `fuzz/iso.py` | ISO Introspection | ISO 3166/4217 territory and currency lookups, type guards, cache. |
| `--fiscal` | `fuzz/fiscal.py` | Fiscal Calendar | FiscalCalendar, FiscalDelta, date arithmetic, boundary conditions. |

### Step 1: Run Stability or Runtime Fuzzing

**Check parser stability:**
```bash
./scripts/fuzz.sh --native --time 60
```

**Check runtime and Strict Mode integrity:**
```bash
./scripts/fuzz.sh --runtime --time 60
```

> **Tip:** The `--runtime` fuzzer specifically verifies that `strict=True` bundles correctly raise `FormattingIntegrityError` on any failure and that the `IntegrityCache` remains consistent.

**Endless run:**
```bash
./scripts/fuzz.sh --runtime
```

> **Tip:** You can stop the endless run at any time with `Ctrl+C`. Findings are saved **instantly** to the `.fuzz_corpus` directory as they are discovered. Stopping the script will not lose any previously found crashes.

**Check ISO introspection (requires Babel):**
```bash
./scripts/fuzz.sh --iso --time 60
```

> **Tip:** The `--iso` fuzzer tests ISO 3166-1 territory and ISO 4217 currency lookups via Babel's CLDR data. It verifies type guard consistency, cache integrity, and data class invariants.

**Check fiscal calendar arithmetic:**
```bash
./scripts/fuzz.sh --fiscal --time 60
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
./scripts/fuzz.sh --minimize .fuzz_corpus/crash_abc123
```

Output:
```
[PASS] Crash minimized successfully.

Original size:  1247 bytes
Minimized size: 42 bytes
Reduction:      97%

Minimized crash saved to: .fuzz_corpus/crash_abc123.minimized

Next steps:
  1. Reproduce: ./scripts/fuzz.sh --repro .fuzz_corpus/crash_abc123.minimized
  2. Add @example() to test and fix the bug
```

**Reproduce the minimized crash:**
```bash
./scripts/fuzz.sh --repro .fuzz_corpus/crash_abc123.minimized
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
./scripts/fuzz.sh --corpus
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
   ./scripts/fuzz.sh --corpus
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
```

### Remove Duplicate Seeds

```bash
uv run python scripts/corpus-health.py --dedupe
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

### Fuzzing Mode Test Selection

| Mode | Engine | Test Selection | Purpose |
|------|--------|----------------|---------|
| `./scripts/fuzz.sh` | Hypothesis | `tests/test_grammar_based_fuzzing.py` only | Fast property checks |
| `./scripts/fuzz.sh --deep` | HypoFuzz | **All Hypothesis tests** in `tests/` | Continuous coverage-guided fuzzing |
| `./scripts/fuzz.sh --native` | Atheris | Custom fuzz targets in `fuzz/stability.py` | Byte-level chaos testing |
| `./scripts/fuzz.sh --runtime` | Atheris | Custom fuzz targets in `fuzz/runtime.py` | Runtime/Strict Mode testing |
| `./scripts/fuzz.sh --structured` | Atheris | Custom fuzz targets in `fuzz/structured.py` | Grammar-aware chaos testing |
| `./scripts/fuzz.sh --perf` | Atheris | Custom fuzz targets in `fuzz/perf.py` | Performance/ReDoS detection |
| `./scripts/fuzz.sh --iso` | Atheris | Custom fuzz targets in `fuzz/iso.py` | ISO 3166/4217 introspection |
| `./scripts/fuzz.sh --fiscal` | Atheris | Custom fuzz targets in `fuzz/fiscal.py` | Fiscal calendar arithmetic |

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

### Testing Pyramid

```
┌─────────────────────────────────────────────────────────────┐
│                    FUZZING LAYER                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ./scripts/fuzz.sh --deep (HypoFuzz)             │    │
│  │  - Continuous property-based testing              │    │
│  │  - Coverage-guided exploration                     │    │
│  │  - Finds logic errors, edge cases                 │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ./scripts/fuzz.sh --native (Atheris)             │    │
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

### Minimization failed or didn't reduce size?

The `--minimize` mode may fail if:
- The crash isn't deterministic (race condition, random state)
- The input is already minimal
- The wrong fuzzer script is being used

Try specifying more time:
```bash
./scripts/fuzz.sh --minimize .fuzz_corpus/crash_* --time 120
```

If minimization fails consistently, use `--repro` directly on the original crash file.

---

## Python Version Requirements

Different fuzzing tools have different Python version requirements:

| Fuzzing Mode | Python Versions | Tool | Notes |
|--------------|-----------------|------|-------|
| `./scripts/fuzz.sh` | 3.13, 3.14 | Hypothesis | Property-based tests |
| `./scripts/fuzz.sh --deep` | 3.13, 3.14 | HypoFuzz | Coverage-guided |
| `./scripts/fuzz.sh --native` | 3.11-3.13 | Atheris | libFuzzer-based |
| `./scripts/fuzz.sh --runtime` | 3.11-3.13 | Atheris | Runtime/Strict Mode |
| `./scripts/fuzz.sh --structured` | 3.11-3.13 | Atheris | Grammar-aware |
| `./scripts/fuzz.sh --perf` | 3.11-3.13 | Atheris | ReDoS detection |
| `./scripts/fuzz.sh --iso` | 3.11-3.13 | Atheris | ISO introspection |
| `./scripts/fuzz.sh --fiscal` | 3.11-3.13 | Atheris | Fiscal calendar |
| `./scripts/fuzz.sh --minimize` | 3.11-3.13 | Atheris | Crash minimization |

### Why Atheris Requires Python 3.13 or Earlier

Atheris uses libFuzzer which is compiled against specific Python ABIs. The Atheris project has not yet released a version supporting Python 3.14.

### Running Native Fuzzing on Python 3.14

If your default Python is 3.14, switch to 3.13 for native fuzzing:

```bash
# Run native/minimize fuzzing with Python 3.13
uv run --python 3.13 ./scripts/fuzz.sh --native
uv run --python 3.13 ./scripts/fuzz.sh --minimize .fuzz_corpus/crash_*

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
| Runtime fuzzing | `./scripts/fuzz.sh --runtime --time 60` |
| Structured fuzzing | `./scripts/fuzz.sh --structured --time 60` |
| Performance fuzzing | `./scripts/fuzz.sh --perf --time 60` |
| ISO introspection fuzzing | `./scripts/fuzz.sh --iso --time 60` |
| Fiscal calendar fuzzing | `./scripts/fuzz.sh --fiscal --time 60` |
| Minimize crash | `./scripts/fuzz.sh --minimize .fuzz_corpus/crash_*` |
| Reproduce crash | `./scripts/fuzz.sh --repro .fuzz_corpus/crash_*` |
| List failures | `./scripts/fuzz.sh --list` |
| Clean all artifacts | `./scripts/fuzz.sh --clean` |
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

### Crash Minimization JSON

```bash
./scripts/fuzz.sh --minimize .fuzz_corpus/crash_abc123 --json
```

Output (success):
```json
{
  "mode": "minimize",
  "status": "ok",
  "original_size": "1247",
  "minimized_size": "42",
  "output_file": ".fuzz_corpus/crash_abc123.minimized"
}
```

Output (failure):
```json
{"mode":"minimize","status":"error","error":"minimization_failed"}
```

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
