---
afad: "4.0"
version: "0.166.0"
domain: TESTING
updated: "2026-05-01"
route:
  keywords: [testing, lint, pytest, fuzz, HypoFuzz, Atheris, test.sh, lint.sh, check.sh, devcontainer]
  questions: ["how do I run lint and tests?", "what is the fuzz marker for?", "which scripts drive testing?", "how do I validate the contributor container?"]
---

# Testing Reference

Repository shell entrypoints assume a Bash 5.0+ `bash` on `PATH`. The committed
contributor devcontainer satisfies that automatically; stock macOS `/bin/bash`
3.2 does not.

---

## `scripts/validate_docs.py`

Repository script that validates runnable Markdown examples against the live package behavior.

### Signature
```bash
uv run python scripts/validate_docs.py
```

### Constraints
- Purpose: parse repository Markdown, run configured Python fences, execute canonical bash/sh quick-start blocks, and validate FTL fences with the project parser
- Coverage: executes the runnable example set configured in `pyproject.toml`
- Shell execution: resolves the shell from the active `PATH` and avoids login-shell path rewrites so repo shebangs hit the same toolchain as a human invocation
- Failure mode: exits non-zero on invalid snippets, parser errors, failing Python blocks, or failing shell workflow blocks
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

## `scripts/validate-devcontainer.sh`

Repository script that validates the committed contributor devcontainer contract.

### Signature
```bash
./scripts/validate-devcontainer.sh
```

### Constraints
- Purpose: verify `.devcontainer/devcontainer.json`, build the contributor image, and smoke-test the required toolchain and writable cache repair
- Coverage: checks the committed devcontainer image rather than a local shell assumption
- Failure mode: exits non-zero when the committed contributor container drifts from the repo's supported native-tooling contract

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
- Purpose: canonical full-repository quality gate; runs version/docs validation, examples, lint, tests, HypoFuzz preflight, and bounded Atheris checks in one command
- Environment: must run inside the committed contributor devcontainer and validates that contract before the other gates
- Fuzzing scope: includes corpus health plus a short live Atheris smoke sweep across every target declared in `fuzz_atheris/targets.tsv`

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
- Purpose: run Ruff, mypy, the bare-`noqa` audit, and the explicit repository static validators under the repo's expected isolated environment pivot
- Behavior: Pivots to `.venv-3.13` on the host and `.venv-devcontainer-3.13` inside the contributor container; `PY_VERSION` overrides target
- Import mode: keeps `PYTHONPATH` unset so tooling resolves the installed package surface
- Output: Quiet-on-success, log-on-fail, agent-oriented summary markers
- Failure mode: exits non-zero on any lint, static-validator, or audit violation

---

## `scripts/test.sh`

Repository test runner script for the main correctness gate.

### Signature
```bash
./scripts/test.sh [--quick] [--ci] [--verbose] [-- ...pytest args]
```

### Constraints
- Purpose: Run pytest with the project’s expected environment pivot and reporting
- Behavior: Pivots to `.venv-3.13` on the host and `.venv-devcontainer-3.13` inside the contributor container; `PY_VERSION` overrides target
- Import mode: keeps `PYTHONPATH` unset so tests exercise the installed package surface
- Coverage: Enforces the coverage threshold declared in `pyproject.toml` for `src/ftllexengine` in normal full mode
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
./scripts/fuzz_atheris.sh [TARGET | --setup [TARGET] | --list | --corpus | --minimize TARGET FILE | --replay TARGET [DIR] | --report TARGET | --clean TARGET] [OPTIONS]
```

### Constraints
- Purpose: Run, replay, list, and minimize Atheris findings
- Behavior: Requires the contributor devcontainer for native execution, pivots into `.venv-devcontainer-atheris`, and loads targets from `fuzz_atheris/targets.tsv`
- Output: Target-oriented CLI workflow around the `fuzz_atheris/` tree
- `--list`: shows stored crashes and finding artifacts; use [fuzz_atheris/README.md](../fuzz_atheris/README.md) for the target inventory
