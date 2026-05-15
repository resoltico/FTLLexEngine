---
afad: "4.0"
version: "0.167.0"
domain: FUZZING
updated: "2026-05-15"
route:
  keywords: [hypofuzz, hypothesis, fuzz_hypofuzz.sh, deep mode, preflight, repro]
  questions: ["how do I run HypoFuzz?", "what does --deep do?", "how do I reproduce a Hypothesis failure?"]
---

# HypoFuzz Guide

**Purpose**: Run the property-testing and HypoFuzz entry points shipped by the repository.
**Prerequisites**: Contributor devcontainer for the canonical path, or `uv sync --group dev --group fuzz` plus a Bash 5.0+ `bash` on `PATH` for direct host work.

## Common Commands

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_hypofuzz.sh --help
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_hypofuzz.sh --preflight
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_hypofuzz.sh --list
```

## Modes

- Default mode runs the standard Hypothesis-backed checks.
- `--deep` runs the intensive fuzz surface.
- `--preflight` audits event instrumentation and strategy coverage.
- `--repro` replays a known failing target.

## Notes

- Inside an already-open contributor devcontainer terminal, drop the wrapper and run `./scripts/fuzz_hypofuzz.sh ...` directly.
- Optional direct host invocations of `./scripts/fuzz_hypofuzz.sh ...` require a Bash 5.0+ `bash` on `PATH`; stock macOS `/bin/bash` 3.2 is unsupported.
- The script pivots into `.venv-3.13` on the host and `.venv-devcontainer-3.13` inside the contributor container.
- `--metrics` is intended for metric-focused runs rather than indefinite continuous fuzzing.
