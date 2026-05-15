---
afad: "4.0"
version: "0.167.0"
domain: CONTRIBUTING
updated: "2026-05-15"
route:
  keywords: [devcontainer, contributor workflow, docker, check.sh, atheris]
  questions: ["how do I open the contributor container?", "how do I run the full repo gate?", "how do I run Atheris in the supported environment?"]
---

# Contributor Devcontainer

**Purpose**: Run the repository's canonical contributor workflow inside a committed, reproducible container surface.
**Prerequisites**: Docker plus either the Dev Containers IDE integration or `npx --yes @devcontainers/cli`.

## Canonical Workflow

From the host:

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./check.sh
```

From an already-open devcontainer terminal:

```bash
./check.sh
```

`./check.sh` is intentionally container-owned. It validates the container contract, runs docs and examples, executes lint and pytest, runs HypoFuzz preflight, and performs bounded live Atheris smoke checks.

## What The Container Owns

- Python 3.13 as the canonical contributor interpreter
- `uv` for dependency and environment orchestration
- LLVM 19 plus the compiler-rt/libFuzzer archives required by Atheris native builds
- `shellcheck` and the shell-based quality gates
- Writable cache mounts for repeatable dependency resolution
- `UV_LINK_MODE=copy` so bind-mounted workspace installs do not emit hardlink fallback warnings

The container is a contributor environment, not a published runtime image. The repository checkout stays on the host and is bind-mounted into the container with immediate read visibility for in-progress edits.
Repository shell gates use `.venv-devcontainer-*` names inside that bind-mounted workspace so Linux container environments do not overwrite host macOS virtual environments.

## Daily Commands

Inside the devcontainer:

```bash
./scripts/lint.sh
./scripts/test.sh
./scripts/fuzz_hypofuzz.sh --preflight
./scripts/fuzz_atheris.sh --smoke-all --time 3
```

From the host without opening an interactive shell:

```bash
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_hypofuzz.sh --preflight
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --smoke-all --time 3
npx --yes @devcontainers/cli exec --workspace-folder . env PY_VERSION=3.14 ./scripts/lint.sh
npx --yes @devcontainers/cli exec --workspace-folder . env PY_VERSION=3.14 ./scripts/test.sh
```

## Validation

The committed container contract is verified by:

```bash
./scripts/validate-devcontainer.sh
```

That script validates `devcontainer.json`, builds the image defined by `.devcontainer/Dockerfile`, checks the required toolchain, and verifies the writable cache-repair hook.
It also verifies that the image exposes a working `CLANG_BIN` and a discoverable libFuzzer archive for Atheris.

## Host-Only Work

Direct host execution remains available for non-container-native tasks when you need it, such as ad hoc `uv` commands or forward-compat runs with `PY_VERSION=3.14`. Host invocations of the repository shell entrypoints require a Bash 5.0+ `bash` on `PATH`; stock macOS `/bin/bash` 3.2 is unsupported. The container is the canonical path for contributor verification and the required path for native Atheris work.
