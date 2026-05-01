---
afad: "4.0"
version: "0.166.0"
domain: FUZZING
updated: "2026-05-01"
route:
  keywords: [fuzzing, HypoFuzz, Atheris, Hypothesis, fuzz_hypofuzz.sh, fuzz_atheris.sh]
  questions: ["which fuzzer should I use?", "how do I start fuzzing?", "how do I reproduce a fuzz failure?"]
---

# Fuzzing Guide

**Purpose**: Choose the right fuzzing entry point and run it with the repo-supported scripts.
**Prerequisites**: Contributor devcontainer for the canonical path. Optional direct host HypoFuzz work also needs `uv sync --group dev --group fuzz` plus a Bash 5.0+ `bash` on `PATH`.

## Overview

Use:

- `./scripts/fuzz_hypofuzz.sh` for Hypothesis and HypoFuzz property exploration.
- `./scripts/fuzz_atheris.sh` for native Atheris/libFuzzer targets inside the contributor devcontainer.

## Fast Start

From the host, use the contributor container for the canonical quick start:

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_hypofuzz.sh --preflight
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --help
```

Inside an already-open contributor devcontainer, drop the wrapper and run
`./scripts/fuzz_hypofuzz.sh --preflight` or `./scripts/fuzz_atheris.sh --help`
directly.

Optional direct-host HypoFuzz runs use `./scripts/fuzz_hypofuzz.sh ...` and
therefore require a Bash 5.0+ `bash` on `PATH`; stock macOS `/bin/bash` 3.2 is
not enough.

## Choosing A Surface

- Prefer HypoFuzz when you are exploring Python-level invariants and stateful/property-based tests.
- Prefer Atheris when you need native-style mutation, corpus management, or target-specific replay/minimization inside the contributor devcontainer.
- Inside the devcontainer, `./scripts/fuzz_atheris.sh --list` inspects stored crashes and finding artifacts; it does not enumerate target names.

## Related Guides

- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md)
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md)
- [DOC_06_Testing.md](DOC_06_Testing.md)
