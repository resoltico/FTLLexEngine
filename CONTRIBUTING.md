---
afad: "3.1"
version: "0.107.0"
domain: contributing
updated: "2026-03-10"
route:
  keywords: [contributing, development, setup, pull request, code style, workflow, pivot]
  questions: ["how to contribute?", "how to set up development?", "how to submit PR?"]
---

# Contributing to FTLLexEngine

## Setup

FTLLexEngine uses `uv` for ultra-fast, deterministic dependency management. We employ a **Pivot** architecture that isolates your IDE environment from the validation silos.

```bash
git clone https://github.com/resoltico/FTLLexEngine.git
cd ftllexengine

# 1. Setup your "IDE Sanctuary" (.venv)
# This environment is for your editor, LSP, and manual exploration.
uv sync --all-groups

# 2. Verify and Initialize Atheris (macOS)
# This sets up the isolated .venv-fuzzing environment.
./scripts/check-atheris.sh --install
```

---

## Environment Hierarchy

To ensure data integrity and zero "environment stomping," the project is strictly siloed:

| Environment | Purpose | Managed By |
|-------------|---------|------------|
| `.venv` (Root) | **IDE Sanctuary** - Autocomplete, LSP, manual runs. | You (`uv sync`) |
| `.venv-3.14` | **Validation Silo** - Clean-room lint/test baseline (Python 3.14, declared minimum). | `scripts/lint.sh`, `scripts/test.sh` |
| `.venv-atheris` | **Atheris Fuzzing** - Python 3.13 venv; INACTIVE until Atheris supports Python 3.14+. | `scripts/fuzz_atheris.sh --setup` |

---

## Automated Scripts (The Pivot)

All validation scripts are **self-isolating**. They automatically "pivot" into `.venv-3.14`, ensuring a clean, reproducible baseline independent of your IDE venv or Atheris toolchain.

| Script | Purpose | Preferred Command |
|--------|---------|-------------------|
| `scripts/lint.sh` | Quality checks (ruff, mypy, pylint) | `./scripts/lint.sh` |
| `scripts/test.sh` | Test suite with coverage | `./scripts/test.sh` |
| `scripts/check-atheris.sh` | Atheris/LLVM health check | `./scripts/check-atheris.sh` |
| `scripts/fuzz_hypofuzz.sh` | Hypothesis/HypoFuzz fuzzing | `./scripts/fuzz_hypofuzz.sh` |
| `scripts/fuzz_atheris.sh` | Atheris/libFuzzer fuzzing | `./scripts/fuzz_atheris.sh` |
| `scripts/benchmark.sh` | Performance benchmarks | `./scripts/benchmark.sh` |

**Optimization**: Do not use `uv run --python X.Y` with these scripts. The scripts handle their internally versioned `uv run` pivots silently to avoid noise and environment overlap.

---

## Multi-Version Development

Python 3.14 is the declared minimum. Python 3.15 is the forward-compatibility target (N+1 policy).

### The Master Control: `PY_VERSION`

The `PY_VERSION` environment variable selects the target Python version. The default is 3.14.

| Task | Command | Target Silo |
|------|---------|-------------|
| **Lint (default)** | `./scripts/lint.sh` | `.venv-3.14` |
| **Lint (3.15 forward-compat)** | `PY_VERSION=3.15 ./scripts/lint.sh` | `.venv-3.15` |
| **Test (default)** | `./scripts/test.sh` | `.venv-3.14` |
| **Test (3.15 forward-compat)** | `PY_VERSION=3.15 ./scripts/test.sh` | `.venv-3.15` |
| **Benchmark (default)** | `./scripts/benchmark.sh` | `.venv-3.14` |
| **Benchmark (3.15 forward-compat)** | `PY_VERSION=3.15 ./scripts/benchmark.sh` | `.venv-3.15` |

### Why this works
- **Zero Stomping**: Running 3.15 checks will **never** wipe your 3.14 environment.
- **Instant Switching**: Switching between 3.14 and 3.15 is instant (no `uv sync` overhead).
- **Parallel Testing**: You can run 3.14 tests in one terminal and 3.15 tests in another simultaneously.

---

## Code Standards

Style:
- **PEP 8** adherence via Ruff.
- **100 char** line limit.
- **Strict Typing**: Type hints are mandatory.
- **Immutability**: Preference for `frozen=True, slots=True` dataclasses.

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class LocaleContext:
    """Context-aware locale container."""
    tag: str
    is_clobbered: bool = False
```

---

## Testing & Coverage

All logic must be verified via deterministic unit tests and non-deterministic property tests.

```bash
./scripts/test.sh           # Full suite (95%+ requirement)
./scripts/test.sh --quick   # Fast mode (no coverage)
```

### Property-Based Testing (Hypothesis)
If you see `HYPOTHESIS DETECTED A LOGIC FLAW`, an edge case has been found.
1. The failing input is saved to `.hypothesis/examples/`.
2. Review the `Falsifying example:` output.
3. Fix the bug and re-run `./scripts/test.sh`.

---

## Pull Requests

### Mandatory Pre-Flight
Before submitting a PR, ensure both versions pass verification:

```bash
# Verify Baseline (Python 3.14)
./scripts/lint.sh && ./scripts/test.sh

# Verify Tomorrow (Python 3.15 forward-compat)
PY_VERSION=3.15 ./scripts/lint.sh && PY_VERSION=3.15 ./scripts/test.sh
```

### CI Requirements
- Parallel matrix testing on 3.14 and 3.15.
- Coverage >= 95.00%.
- Strict type checking (mypy) on all targets.
- Successful documentation validation (`scripts/validate_docs.py`).

---

## Versioning

**Single Source of Truth**: The version is managed exclusively in `pyproject.toml`. Do not manually edit `__version__` in `src/`. It is auto-derived from package metadata at runtime to prevent version drift.

Standard workflow:
1. Update version in pyproject.toml
2. Sync to refresh package metadata

```bash
uv sync
```
