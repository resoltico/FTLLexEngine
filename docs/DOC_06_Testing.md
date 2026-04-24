---
afad: "4.0"
version: "0.165.0"
domain: TESTING
updated: "2026-04-24"
route:
  keywords: [testing, lint, pytest, fuzz, HypoFuzz, Atheris, test.sh, lint.sh, check.sh]
  questions: ["how do I run lint and tests?", "what is the fuzz marker for?", "which scripts drive testing?"]
---

# Testing Reference

---

## `scripts/validate_docs.py`

Repository script that validates runnable Markdown examples against the live package behavior.

### Signature
```bash
uv run python scripts/validate_docs.py
```

### Constraints
- Purpose: parse repository Markdown, run configured Python fences, and validate FTL fences with the project parser
- Coverage: executes the runnable example set configured in `pyproject.toml`
- Failure mode: exits non-zero on invalid snippets, parser errors, or failing Python blocks
- Related guard: `tests/test_documentation_tooling.py` verifies the validator configuration

---

## `scripts/validate_version.py`

Repository script that enforces package-version sync across code, metadata, and documentation frontmatter.

### Signature
```bash
uv run python scripts/validate_version.py
```

### Constraints
- Purpose: verify `pyproject.toml`, runtime version exports, and configured Markdown frontmatter stay synchronized
- Coverage: enforces the AFAD `version:` contract over the configured Markdown set
- Failure mode: exits non-zero on version drift or metadata mismatch
- Related guard: `tests/test_documentation_tooling.py` verifies the frontmatter key contract

---

## `scripts/run_examples.py`

Repository script that executes every shipped example under the active project interpreter.

### Signature
```bash
uv run python scripts/run_examples.py [--pattern '*.py'] [--list]
```

### Constraints
- Purpose: keep `examples/*.py` runnable and semantically self-checking as a supported, repeatable gate
- Import mode: clears `PYTHONPATH` so examples run against the installed package contract
- Output contracts: every shipped example must register a stdout contract so semantic regressions cannot hide behind exit code `0`
- Failure mode: exits non-zero when any example script fails, omits expected contract markers, or is missing a registered contract

---

## `check.sh`

Top-level orchestration script for the repository's full quality surface.

### Signature
```bash
./check.sh
```

### Constraints
- Purpose: run version/docs validation, examples, lint, tests, HypoFuzz preflight, and bounded Atheris checks in one command
- Environment: uses the same Python-versioned uv environment contract as the repo shell gates
- Fuzzing scope: includes corpus health plus short live Atheris smoke runs for graph and introspection targets

---

## `pytest.mark.fuzz`

Pytest marker indicating an intensive fuzz-only test surface.

### Signature
```python
@pytest.mark.fuzz
```

### Constraints
- Purpose: Separate slow or open-ended fuzz tests from default test runs
- Behavior: Normal `./scripts/test.sh` runs skip these tests
- Location: Declared in `pyproject.toml`

---

## `scripts/lint.sh`

Repository lint runner script for the main static-analysis gate.

### Signature
```bash
./scripts/lint.sh [--verbose]
```

### Constraints
- Purpose: Run Ruff then mypy under the repo's expected isolated environment pivot
- Behavior: Pivots to `.venv-3.13` by default; `PY_VERSION` overrides target
- Import mode: keeps `PYTHONPATH` unset so tooling resolves the installed package surface
- Output: Quiet-on-success, log-on-fail, agent-oriented summary markers
- Failure mode: exits non-zero on any Ruff or mypy violation

---

## `scripts/test.sh`

Repository test runner script for the main correctness gate.

### Signature
```bash
./scripts/test.sh [--quick] [--ci] [--verbose] [-- ...pytest args]
```

### Constraints
- Purpose: Run pytest with the project’s expected environment pivot and reporting
- Behavior: Pivots to `.venv-3.13` by default; `PY_VERSION` overrides target
- Import mode: keeps `PYTHONPATH` unset so tests exercise the installed package surface
- Coverage: Enforces 100% line coverage and 100% branch coverage for `src/ftllexengine` in normal full mode
- Output: Log-on-fail summary plus structured status markers

---

## `scripts/fuzz_hypofuzz.sh`

Repository script for Hypothesis and HypoFuzz workflows.

### Signature
```bash
./scripts/fuzz_hypofuzz.sh [--deep | --preflight | --repro TEST | --list | --clean] [OPTIONS]
```

### Constraints
- Purpose: Run default property checks, deep fuzzing, preflight audits, and repro flows
- Behavior: Supports `--deep`, `--preflight`, `--repro`, `--metrics`
- Output: Structured heartbeat and summary markers

---

## `scripts/fuzz_atheris.sh`

Repository script for native Atheris/libFuzzer targets.

### Signature
```bash
./scripts/fuzz_atheris.sh [TARGET | --setup | --list | --corpus | --minimize TARGET FILE | --replay TARGET [DIR] | --report TARGET | --clean TARGET] [OPTIONS]
```

### Constraints
- Purpose: Run, replay, list, and minimize Atheris findings
- Behavior: Manages `.venv-atheris` separately from the main project venvs
- Output: Target-oriented CLI workflow around the `fuzz_atheris/` tree
- `--list`: shows stored crashes and finding artifacts; use [fuzz_atheris/README.md](../fuzz_atheris/README.md) for the target inventory
