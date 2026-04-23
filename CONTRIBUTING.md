---
afad: "3.5"
version: "0.163.0"
domain: CONTRIBUTING
updated: "2026-04-23"
route:
  keywords: [contributing, development, uv, lint, test, fuzz, benchmark, release, virtualenv]
  questions: ["how do I set up development?", "how do I run lint and tests?", "how do I work on fuzzing?", "how do I prepare a release?"]
---

# Contributing to FTLLexEngine

**Purpose**: Set up a working development environment and run the same validation paths the repo expects.
**Prerequisites**: `uv`, Bash 5+, Python 3.13 available locally. Python 3.14 is recommended for forward-compat checks.

## Overview

This repository uses `uv` for dependency management and self-isolating shell scripts for the main quality gates. The root `.venv` is the manual development environment; the scripted gates pivot into versioned environments such as `.venv-3.13`, `.venv-3.14`, and `.venv-atheris` as needed.

The shortest reliable workflow is:

```bash
uv sync --group dev --group release
./check.sh
```

The default test gate enforces **100% line coverage and 100% branch coverage** for `src/ftllexengine`.

## Setup

```bash
git clone https://github.com/resoltico/FTLLexEngine.git
cd FTLLexEngine
uv sync --group dev --group release
uv sync --group fuzz
```

Optional environments:

- `PY_VERSION=3.14 ./scripts/lint.sh` and `PY_VERSION=3.14 ./scripts/test.sh` create or reuse `.venv-3.14`.
- `./scripts/fuzz_atheris.sh --help` bootstraps `.venv-atheris` on demand and requires Python 3.13.

## Daily Workflow

Run the repo gates directly; the scripts manage their own interpreter pivots.

```bash
./check.sh
```

Useful variants:

- `uv run python scripts/run_examples.py`
- `PY_VERSION=3.14 ./scripts/lint.sh`
- `PY_VERSION=3.14 ./scripts/test.sh`
- `./scripts/benchmark.sh`
- `./scripts/fuzz_hypofuzz.sh`
- `./scripts/fuzz_hypofuzz.sh --deep --time 300`
- `./scripts/fuzz_atheris.sh numbers --time 60`
- `./scripts/fuzz_atheris.sh --list` to inspect stored crashes and finding artifacts

## Documentation Work

Markdown changes should stay synchronized with the code and examples they describe.

```bash
uv run python scripts/validate_docs.py
uv run python scripts/validate_version.py
uv run python scripts/run_examples.py
```

Expectations:

- README and guide Python snippets should run as written.
- `examples/*.py` should execute cleanly under the dev environment.
- Source-code docstring transcripts are illustrative API notes, not an executable test suite. Keep runnable examples in Markdown or `examples/`, and mark any source `>>>` transcript with `# doctest: +SKIP`.
- Reference docs should describe current symbols, not removed or internal machinery.

## Type Checking Examples

The `examples/` directory has its own `mypy.ini` and does not rely on local stub overlays.

```bash
uv run mypy --config-file examples/mypy.ini examples
```

## Fuzzing

Two fuzzing surfaces are maintained:

- `./scripts/fuzz_hypofuzz.sh` for Hypothesis and HypoFuzz.
- `./scripts/fuzz_atheris.sh` for native Atheris/libFuzzer targets.

See:

- [docs/FUZZING_GUIDE.md](docs/FUZZING_GUIDE.md)
- [docs/FUZZING_GUIDE_HYPOFUZZ.md](docs/FUZZING_GUIDE_HYPOFUZZ.md)
- [docs/FUZZING_GUIDE_ATHERIS.md](docs/FUZZING_GUIDE_ATHERIS.md)

## Benchmarks

```bash
./scripts/benchmark.sh
./scripts/benchmark.sh --save baseline
./scripts/benchmark.sh --compare <baseline-id>
```

## Releases

Release work goes through a release branch and `gh`-driven verification.

Authoritative procedure:

- [docs/RELEASE_PROTOCOL.md](docs/RELEASE_PROTOCOL.md)

Support scripts:

- `./scripts/publish-github-release-assets.sh`
- `./scripts/verify-github-release.sh`

## Pull Requests

Before opening a PR, make sure the baseline gates pass:

```bash
./check.sh
```

`./scripts/test.sh` is expected to fail on any coverage regression below the repository's 100% line-and-branch baseline.

When the change touches runtime behavior or supported Python versions, also run the forward-compat pass:

```bash
PY_VERSION=3.14 ./scripts/lint.sh
PY_VERSION=3.14 ./scripts/test.sh
```
