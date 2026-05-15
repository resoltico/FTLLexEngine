---
afad: "4.0"
version: "0.167.0"
domain: FUZZING
updated: "2026-05-15"
route:
  keywords: [atheris, libfuzzer, fuzz_atheris.sh, replay, minimize, corpus]
  questions: ["how do I run an Atheris target?", "how do I replay a finding?", "how does the Atheris environment get created?"]
---

# Atheris Guide

**Purpose**: Run and manage the native Atheris/libFuzzer targets in `fuzz_atheris/`.
**Prerequisites**: The committed contributor devcontainer.

## Common Commands

Inside a contributor devcontainer terminal:

- `./scripts/fuzz_atheris.sh --help`
- `./scripts/fuzz_atheris.sh --list`

From the host, run the same entrypoint through the devcontainer wrapper:

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --help
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --list
```

## Environment

The script pivots into the dedicated `.venv-devcontainer-atheris` uv environment inside the devcontainer.
Native toolchain ownership lives in the devcontainer image, which provides `CLANG_BIN=/usr/local/bin/clang`
and the LLVM 19 libFuzzer archives that Atheris needs to build; target discovery lives in
`fuzz_atheris/targets.tsv`.

## Useful Operations

- `--list` to inspect captured findings.
- Target names live in [../fuzz_atheris/README.md](../fuzz_atheris/README.md).
- `--replay` to replay stored findings without starting a fresh fuzz run.
- `--minimize TARGET FILE` to shrink a failing input for one target.
- `--corpus` to run the corpus health check.
- `--smoke-all` to run a bounded manifest-driven sweep across every registered target.
