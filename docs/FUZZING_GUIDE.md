---
afad: "3.1"
version: "0.107.0"
domain: fuzzing
updated: "2026-02-10"
route:
  keywords: [fuzzing, testing, hypothesis, hypofuzz, atheris, property-based, coverage, crash, security, metrics, workers]
  questions: ["how to run fuzzing?", "how to fuzz the parser?", "how to find bugs with fuzzing?", "which fuzzer to use?", "how do workers affect metrics?"]
---

# Fuzzing Guide

**Purpose**: Overview of FTLLexEngine's fuzzing infrastructure.
**Prerequisites**: Basic pytest knowledge.

FTLLexEngine uses two complementary fuzzing systems:

| System | Script | Best For |
|--------|--------|----------|
| **HypoFuzz** (Hypothesis) | `fuzz_hypofuzz.sh` | Logic errors, property violations, edge cases |
| **Atheris** (libFuzzer) | `fuzz_atheris.sh` | Crashes, security issues, memory safety |

**Detailed Guides:**
- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md) - Hypothesis/HypoFuzz property testing
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md) - Native fuzzing with Atheris

---

## Quick Start (30 Seconds)

```bash
# Quick property test check (recommended before committing)
./scripts/fuzz_hypofuzz.sh
```

You will see either:
- **[PASS]** - All tests passed
- **[FAIL]** - A bug was found. Follow the "Next steps" shown.

---

## Testing Pyramid

```
+---------------------------------------------------------------+
|                      FUZZING LAYER                            |
|  +---------------------------+  +---------------------------+ |
|  | fuzz_hypofuzz.sh --deep   |  | fuzz_atheris.sh native    | |
|  | - Property-based testing  |  | - Byte-level mutation     | |
|  | - Coverage-guided         |  | - Crash detection         | |
|  | - Logic errors            |  | - Security issues         | |
|  +---------------------------+  +---------------------------+ |
+---------------------------------------------------------------+
|                      UNIT TEST LAYER                          |
|  +----------------------------------------------------------+ |
|  | uv run scripts/test.sh                                   | |
|  | - Comprehensive unit tests (95%+ coverage)               | |
|  +----------------------------------------------------------+ |
+---------------------------------------------------------------+
```

Fuzzing finds issues that traditional unit tests miss by exploring vast input spaces automatically.

---

## Choosing a Fuzzer

### Use HypoFuzz (Hypothesis) When:

- Testing **properties** (e.g., "parse then serialize equals original")
- Finding **logic errors** and **edge cases**
- Working with **typed data structures** (strategies generate valid Python objects)
- You want **automatic shrinking** to minimal failing examples
- Running **before every commit** (fast, no special setup)

```bash
./scripts/fuzz_hypofuzz.sh              # Quick check
./scripts/fuzz_hypofuzz.sh --deep       # Continuous fuzzing (until Ctrl+C)
./scripts/fuzz_hypofuzz.sh --deep --metrics  # Single-pass with metrics
```

### Use Atheris (libFuzzer) When:

- Testing **crash resistance** and **memory safety**
- Looking for **security vulnerabilities**
- Testing **byte-level parsing** robustness
- Doing **security audits** before releases
- You need **raw mutation** that ignores grammar rules

```bash
./scripts/fuzz_atheris.sh native        # Crash detection
./scripts/fuzz_atheris.sh structured    # Grammar-aware fuzzing
```

---

## Command Reference

### HypoFuzz Commands

| Command | Description |
|---------|-------------|
| `./scripts/fuzz_hypofuzz.sh` | Quick property tests |
| `./scripts/fuzz_hypofuzz.sh --deep` | Continuous HypoFuzz (until Ctrl+C) |
| `./scripts/fuzz_hypofuzz.sh --deep --metrics` | Single-pass pytest with strategy metrics |
| `./scripts/fuzz_hypofuzz.sh --preflight` | Audit test infrastructure |
| `./scripts/fuzz_hypofuzz.sh --list` | Show reproduction info |
| `./scripts/fuzz_hypofuzz.sh --repro TEST` | Reproduce failing test |
| `./scripts/fuzz_hypofuzz.sh --clean` | Remove .hypothesis/ |

### Atheris Commands

| Command | Description |
|---------|-------------|
| `./scripts/fuzz_atheris.sh native` | Stability fuzzing |
| `./scripts/fuzz_atheris.sh structured` | Grammar-aware fuzzing |
| `./scripts/fuzz_atheris.sh --list` | List crashes/findings |
| `./scripts/fuzz_atheris.sh --corpus` | Check seed health |
| `./scripts/fuzz_atheris.sh --replay TARGET` | Replay findings |

---

## Key Differences

| Aspect | HypoFuzz | Atheris |
|--------|----------|---------|
| Input type | Python objects | Raw bytes |
| Grammar awareness | Yes (via strategies) | No (mutations) |
| Storage | `.hypothesis/examples/` | `.fuzz_atheris_corpus/` |
| Filename format | SHA-384 hashes | `crash_*`, `finding_p{PID}_*` |
| Reproduction | Automatic pytest replay | Manual via repro script |
| Corpus | Implicit (coverage DB) | Explicit (seeds/) |
| Workers | Multiprocessing (metrics need single-worker) | fork() (metrics need `--workers 1`) |
| Best for | Logic bugs | Crashes, security |

---

## Parallelism and Metrics

Both fuzzing systems use multiprocessing, which fragments in-process
metrics across worker processes. Each system handles this differently:

| System | Worker Model | Metrics Constraint |
|--------|-------------|-------------------|
| HypoFuzz | Python `multiprocessing` | `--metrics` forces single-process pytest |
| Atheris | libFuzzer `fork()` | `--workers 1` (default) for reliable metrics |

**Root cause:** Both systems accumulate metrics (iterations, coverage,
performance history) in process-local state. Forked/spawned workers each
get independent copies. There is no cross-process aggregation.

**Recommendation:** Use single-worker mode for metrics-sensitive runs
(debugging, performance analysis, weight skew detection). Use
multi-worker mode only for throughput-oriented crash detection.

See [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md) for details on
Atheris worker behavior under `fork()`.

---

## Data Directories

| Directory | System | Git Tracked | Contents |
|-----------|--------|-------------|----------|
| `.hypothesis/examples/` | HypoFuzz | No | Coverage database |
| `.hypothesis/hypofuzz.log` | HypoFuzz | No | Session log |
| `.fuzz_atheris_corpus/` | Atheris | No | Working corpus, crashes |
| `fuzz_atheris/seeds/` | Atheris | Yes | Seed corpus |

---

## Workflow Summary

### Daily Development

```bash
# Before committing
./scripts/fuzz_hypofuzz.sh
```

### Deep Testing

```bash
# Run HypoFuzz for extended period
./scripts/fuzz_hypofuzz.sh --deep --time 300
```

### Security Audit

```bash
# Run all Atheris modes
./scripts/fuzz_atheris.sh native --time 300
./scripts/fuzz_atheris.sh structured --time 300
./scripts/fuzz_atheris.sh perf --time 300
```

### Reproducing Failures

```bash
# HypoFuzz failures (automatic replay)
./scripts/fuzz_hypofuzz.sh --repro test_parser_hypothesis::test_roundtrip

# Atheris crashes (manual)
uv run python scripts/fuzz_atheris_repro.py .fuzz_atheris_corpus/crash_xxx
```

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/fuzz_hypofuzz.sh` | HypoFuzz entry point |
| `scripts/fuzz_hypofuzz_repro.py` | Reproduce Hypothesis failures |
| `scripts/fuzz_atheris.sh` | Atheris entry point |
| `scripts/fuzz_atheris_repro.py` | Reproduce Atheris crashes |
| `scripts/fuzz_atheris_corpus_health.py` | Seed corpus health check |

---

## See Also

- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md) - Full HypoFuzz documentation
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md) - Full Atheris documentation
- [DOC_06_Testing.md](DOC_06_Testing.md) - Testing overview
