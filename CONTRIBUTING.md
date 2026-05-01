---
afad: "4.0"
version: "0.166.0"
domain: CONTRIBUTING
updated: "2026-05-01"
route:
  keywords: [contributing, development, uv, lint, test, fuzz, benchmark, release, virtualenv]
  questions: ["how do I set up development?", "how do I run lint and tests?", "how do I work on fuzzing?", "how do I prepare a release?"]
---

# Contributing to FTLLexEngine

**Purpose**: Set up a working development environment and run the same validation paths the repo expects.
**Prerequisites**: Docker plus either the Dev Containers IDE integration or `npx --yes @devcontainers/cli`. Direct host `uv` use is optional; direct host execution of the repository shell gates also requires a Bash 5.0+ `bash` on `PATH`.

## Overview

This repository uses a committed contributor devcontainer for the canonical engineering workflow. Repository shell gates continue to use `uv`-managed environments internally, but the supported path for full verification and native Atheris work is the devcontainer described in [docs/DEVELOPER_DEVCONTAINER.md](docs/DEVELOPER_DEVCONTAINER.md).

The shortest reliable workflow is:

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./check.sh
```

The default test gate enforces the repository coverage floor declared in `pyproject.toml`.

## Setup

```bash
git clone https://github.com/resoltico/FTLLexEngine.git
cd FTLLexEngine
npx --yes @devcontainers/cli up --workspace-folder .
```

Optional direct host setup:

- `uv sync --group dev --group release`
- `uv sync --group fuzz`
- Host shell gates create or reuse `.venv-3.13` and `.venv-3.14`; the devcontainer uses `.venv-devcontainer-*` names to avoid cross-platform contamination of the bind-mounted workspace.
- Stock macOS `/bin/bash` 3.2 is not sufficient for the repo shell entrypoints. Use the devcontainer path or install a Bash 5.0+ `bash` before invoking `./scripts/*.sh` directly from the host.

## Daily Workflow

Run the repo gates inside the devcontainer. If you are already in a devcontainer terminal, use the script directly; from the host, use `devcontainers exec`.

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
- Inside a devcontainer terminal: `./scripts/fuzz_atheris.sh graph --time 60`
- Inside a devcontainer terminal: `./scripts/fuzz_atheris.sh --list` to inspect stored crashes and finding artifacts

## Documentation Work

Markdown changes should stay synchronized with the code and examples they describe.

```bash
uv run python scripts/validate_docs.py
uv run python scripts/validate_version.py
uv run python scripts/run_examples.py
```

Expectations:

- README and guide Python snippets should run as written.
- Canonical shell quick-start blocks in the fuzzing guides should execute as written from the documented host-with-devcontainer-wrapper context.
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
- `./scripts/fuzz_atheris.sh` for native Atheris/libFuzzer targets inside the contributor devcontainer.

See:

- [docs/DEVELOPER_DEVCONTAINER.md](docs/DEVELOPER_DEVCONTAINER.md)
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

`./scripts/test.sh` is expected to fail on any coverage regression below the repository policy declared in `pyproject.toml`.

When the change touches runtime behavior or supported Python versions, also run the forward-compat pass:

```bash
PY_VERSION=3.14 ./scripts/lint.sh
PY_VERSION=3.14 ./scripts/test.sh
```
