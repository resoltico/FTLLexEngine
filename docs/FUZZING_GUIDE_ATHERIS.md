---
afad: "3.1"
version: "0.101.0"
domain: fuzzing
updated: "2026-02-03"
route:
  keywords: [fuzzing, atheris, libfuzzer, native, crash, security, corpus]
  questions: ["how to run atheris?", "how to do native fuzzing?", "how to reproduce crashes?", "how to manage corpus?"]
---

# Atheris Guide (Native Fuzzing with libFuzzer)

**Purpose**: Run byte-level mutation fuzzing for crash and security testing.
**Prerequisites**: macOS with LLVM, isolated virtualenv.

---

## Quick Start

```bash
# Run native fuzzing on parser
./scripts/fuzz_atheris.sh native

# List crashes and findings
./scripts/fuzz_atheris.sh --list

# Check corpus health
./scripts/fuzz_atheris.sh --corpus

# Reproduce a crash
uv run python scripts/fuzz_atheris_repro.py .fuzz_atheris_corpus/crash_xxx
```

---

## How Atheris Works

Atheris is a coverage-guided Python fuzzer built on libFuzzer:

1. **Mutates** raw bytes using libFuzzer's mutation strategies
2. **Instruments** Python code for coverage feedback
3. **Crashes** are captured as binary files in `.fuzz_atheris_corpus/`
4. **Minimizes** crash inputs automatically

Key difference from Hypothesis: Atheris works with **raw bytes**, not Python objects.

---

## Prerequisites (macOS)

Atheris requires LLVM and a custom Python build. Use the isolated virtualenv:

```bash
# The script manages its own environment
./scripts/fuzz_atheris.sh --help
```

The script uses `.venv-atheris` to avoid conflicts with the main project environment.

### Verification

```bash
./scripts/fuzz_atheris.sh --help
```

Should list all available fuzzing targets.

---

## Command Reference

| Command | Description |
|---------|-------------|
| `./scripts/fuzz_atheris.sh native` | Stability fuzzing (crash detection) |
| `./scripts/fuzz_atheris.sh runtime` | Runtime stack fuzzing |
| `./scripts/fuzz_atheris.sh structured` | Grammar-aware FTL fuzzing |
| `./scripts/fuzz_atheris.sh perf` | Performance/ReDoS fuzzing |
| `./scripts/fuzz_atheris.sh iso` | ISO introspection fuzzing |
| `./scripts/fuzz_atheris.sh fiscal` | Fiscal calendar fuzzing |
| `./scripts/fuzz_atheris.sh --list` | List crashes and findings |
| `./scripts/fuzz_atheris.sh --corpus` | Check seed corpus health |
| `./scripts/fuzz_atheris.sh --replay TARGET` | Replay findings without Atheris |
| `./scripts/fuzz_atheris.sh --clean TARGET` | Clean corpus for target |
| `./scripts/fuzz_atheris.sh --workers N` | Parallel workers |
| `./scripts/fuzz_atheris.sh --time N` | Time limit in seconds |

---

## Fuzzing Targets

Targets are dynamically discovered from `fuzz_atheris/fuzz_*.py` files:

| Target | Mode | Focus |
|--------|------|-------|
| `native` | Stability | Crashes, hangs, memory safety in FTL parser |
| `runtime` | End-to-End | FluentBundle, IntegrityCache, Strict Mode |
| `structured` | Structured | Syntactically plausible FTL for deeper paths |
| `perf` | Performance | Algorithmic complexity, ReDoS vulnerabilities |
| `iso` | Introspection | ISO 3166/4217 lookups, type guards, cache |
| `fiscal` | Arithmetic | Fiscal calendar date operations |
| `integrity` | Validation | IntegrityCache hash verification |
| `lock` | Concurrency | RWLock timeout and contention paths |
| `roundtrip` | Convergence | Parser-serializer round-trip consistency |

---

## Workflow 1: Crash Detection

```bash
# Run stability fuzzing
./scripts/fuzz_atheris.sh native --time 300

# Or until Ctrl+C
./scripts/fuzz_atheris.sh native
```

**Interpreting Output:**

```
#12345 REDUCE cov: 1234 ft: 567 corp: 89/10Kb exec/s: 456
```

- `#12345` - Iteration count
- `cov:` - Code coverage (edges)
- `ft:` - Feature count
- `corp:` - Corpus size
- `exec/s` - Executions per second

**Crash Detected:**

```
==12345== ERROR: libFuzzer: deadly signal
```

Crash file saved to `.fuzz_atheris_corpus/crash_*`.

---

## Workflow 2: Reproducing Crashes

When a crash is found:

```bash
# List all crashes
./scripts/fuzz_atheris.sh --list

# Reproduce a specific crash
uv run python scripts/fuzz_atheris_repro.py .fuzz_atheris_corpus/crash_abc123

# Generate @example decorator
uv run python scripts/fuzz_atheris_repro.py --example .fuzz_atheris_corpus/crash_abc123
```

**Output:**

```
[FINDING] Parser crashed with ValueError: ...

Full traceback:
------------------------------------------------------------
...
------------------------------------------------------------

Next steps:
  1. Add @example decorator to preserve this case:
     @example(ftl='...')
  2. Fix the bug in the parser
  3. Re-run fuzzing to verify
```

---

## Workflow 3: Structured Fuzzing

For grammar-aware fuzzing that generates syntactically valid FTL:

```bash
./scripts/fuzz_atheris.sh structured --time 300
```

Structured fuzzing finds issues in deeper parser code paths that random bytes cannot reach.

**Finding Artifacts:**

Structured fuzzing saves finding details to `.fuzz_atheris_corpus/<target>/findings/`:

```
.fuzz_atheris_corpus/structured/findings/
├── finding_001/
│   ├── source.ftl      # Original FTL
│   ├── s1.ftl          # Serialized once
│   ├── s2.ftl          # Serialized twice
│   └── meta.json       # Finding metadata
```

---

## Corpus Management

### Seed Corpus

Seeds are stored in `fuzz_atheris/seeds/` and are **git tracked**:

```
fuzz_atheris/seeds/
├── 00_minimal.ftl        # Minimal valid FTL
├── 01_message.ftl        # Basic message
├── 10_select.ftl         # Select expressions
├── 20_terms.ftl          # Terms and references
├── 30_complex.ftl        # Complex nested structures
└── iso_baseline.bin      # Binary seed for ISO fuzzer
```

### Working Corpus

The working corpus in `.fuzz_atheris_corpus/` is **not git tracked**:

```
.fuzz_atheris_corpus/
├── crash_abc123         # Crash artifacts
├── native/              # Native fuzzer corpus
├── structured/          # Structured fuzzer corpus
│   └── findings/        # Finding artifacts
└── ...
```

### Health Check

```bash
./scripts/fuzz_atheris.sh --corpus
```

Reports:
- Total seeds and byte count
- Parse success/failure rate
- Grammar feature coverage
- Duplicate detection

### Adding Seeds

1. Create seed file:
   ```ftl
   # fuzz_atheris/seeds/40_new_feature.ftl
   new-feature = { $arg ->
       [case1] Value 1
      *[other] Default
   }
   ```

2. Verify:
   ```bash
   ./scripts/fuzz_atheris.sh --corpus
   ```

### Binary Seeds

For ISO/fiscal fuzzers that expect structured binary input:

```python
# Example: ISO seed
seed = bytes([
    5,              # locale length
    *b"en_US",      # locale string
    3,              # code length
    *b"USD",        # currency code
    0b00000011,     # flags
])

with open("fuzz_atheris/seeds/iso_custom.bin", "wb") as f:
    f.write(seed)
```

### Removing Duplicates

```bash
uv run python scripts/fuzz_atheris_corpus_health.py --dedupe
```

Shows duplicates. Add `--execute` to remove them.

---

## Adding New Fuzzers

FTLLexEngine uses a dynamic plugin system. New fuzzers are automatically discovered.

### Plugin Header Schema

All `fuzz_atheris/fuzz_*.py` files must include:

```python
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: <name> - <description>
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
```

### Creating a New Fuzzer

1. Create `fuzz_atheris/fuzz_myfuzzer.py` with the header
2. Implement the fuzzer target function
3. Run `./scripts/fuzz_atheris.sh --help` to verify discovery
4. Execute with `./scripts/fuzz_atheris.sh myfuzzer`

---

## Troubleshooting

### ImportError: symbol not found

LLVM version mismatch. Ensure Atheris and Python are built with the same LLVM:

```bash
brew install llvm
export LLVM_CONFIG=$(brew --prefix llvm)/bin/llvm-config
pip install atheris
```

### WARNING: Failed to find function "__sanitizer_..."

Harmless. This occurs because Python isn't compiled with AddressSanitizer. Coverage collection still works.

### Slow Execution

Check corpus size:

```bash
ls -la .fuzz_atheris_corpus/<target>/ | wc -l
```

Large corpus (100k+) slows startup. Clean periodically:

```bash
./scripts/fuzz_atheris.sh --clean native
```

### Timeout/Hang Detection

For performance fuzzing:

```bash
./scripts/fuzz_atheris.sh perf --time 600
```

Perf fuzzing detects ReDoS and algorithmic complexity issues.

---

## Architecture

### Directory Structure

```
fuzz_atheris/
├── seeds/               # Seed corpus (git tracked)
│   ├── *.ftl           # FTL text seeds
│   └── *.bin           # Binary seeds
├── fuzz_native.py      # Stability fuzzer
├── fuzz_runtime.py     # Runtime fuzzer
├── fuzz_structured.py  # Grammar-aware fuzzer
├── fuzz_perf.py        # Performance fuzzer
├── fuzz_iso.py         # ISO introspection fuzzer
├── fuzz_fiscal.py      # Fiscal calendar fuzzer
├── fuzz_atheris_replay_finding.py   # Finding replay utility
└── mypy.ini            # Type checking config

.fuzz_atheris_corpus/            # Working corpus (gitignored)
├── crash_*             # Crash artifacts
└── <target>/           # Per-target corpus
    └── findings/       # Finding artifacts
```

### libFuzzer Integration

Atheris wraps libFuzzer, providing:

- **Corpus management**: Automatic minimization and evolution
- **Coverage tracking**: Inline 8-bit counters
- **Crash isolation**: Precise reproduction via crash files
- **Parallel fuzzing**: Multi-worker support

---

## See Also

- [FUZZING_GUIDE.md](FUZZING_GUIDE.md) - Overview and comparison
- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md) - Hypothesis property testing
- [DOC_06_Testing.md](DOC_06_Testing.md) - Full testing documentation
