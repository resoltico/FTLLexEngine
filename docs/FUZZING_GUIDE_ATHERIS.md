---
afad: "3.5"
version: "0.164.0"
domain: FUZZING
updated: "2026-04-23"
route:
  keywords: [atheris, libfuzzer, fuzz_atheris.sh, replay, minimize, corpus]
  questions: ["how do I run an Atheris target?", "how do I replay a finding?", "how does the Atheris environment get created?"]
---

# Atheris Guide

**Purpose**: Run and manage the native Atheris/libFuzzer targets in `fuzz_atheris/`.
**Prerequisites**: Python 3.13 available locally.

## Common Commands

```bash
./scripts/fuzz_atheris.sh --help
./scripts/fuzz_atheris.sh numbers --time 60
./scripts/fuzz_atheris.sh --list   # stored crashes/findings, not target names
./scripts/fuzz_atheris.sh --replay runtime path/to/finding
```

## Environment

The script manages `.venv-atheris` itself and keeps it separate from the normal project venvs. If the Atheris environment is missing or built with the wrong Python version, the script recreates it automatically.

## Useful Operations

- `--list` to inspect captured findings.
- Target names live in [../fuzz_atheris/README.md](../fuzz_atheris/README.md).
- `--replay` to replay stored findings without starting a fresh fuzz run.
- `--minimize TARGET FILE` to shrink a failing input for one target.
- `--corpus` to run the corpus health check.
