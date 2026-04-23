---
afad: "3.5"
version: "0.163.0"
domain: FUZZING
updated: "2026-04-23"
route:
  keywords: [fuzzing, HypoFuzz, Atheris, Hypothesis, fuzz_hypofuzz.sh, fuzz_atheris.sh]
  questions: ["which fuzzer should I use?", "how do I start fuzzing?", "how do I reproduce a fuzz failure?"]
---

# Fuzzing Guide

**Purpose**: Choose the right fuzzing entry point and run it with the repo-supported scripts.
**Prerequisites**: Dev environment synced with `uv`; Python 3.13 available locally for Atheris.

## Overview

Use:

- `./scripts/fuzz_hypofuzz.sh` for Hypothesis and HypoFuzz property exploration.
- `./scripts/fuzz_atheris.sh` for native Atheris/libFuzzer targets.

## Fast Start

```bash
./scripts/fuzz_hypofuzz.sh
./scripts/fuzz_hypofuzz.sh --deep --time 300
./scripts/fuzz_atheris.sh numbers --time 60
```

## Choosing A Surface

- Prefer HypoFuzz when you are exploring Python-level invariants and stateful/property-based tests.
- Prefer Atheris when you need native-style mutation, corpus management, or target-specific replay/minimization.
- `./scripts/fuzz_atheris.sh --list` inspects stored crashes and finding artifacts; it does not enumerate target names.

## Related Guides

- [FUZZING_GUIDE_HYPOFUZZ.md](FUZZING_GUIDE_HYPOFUZZ.md)
- [FUZZING_GUIDE_ATHERIS.md](FUZZING_GUIDE_ATHERIS.md)
- [DOC_06_Testing.md](DOC_06_Testing.md)
