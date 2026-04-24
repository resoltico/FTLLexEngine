---
afad: "4.0"
version: "0.164.0"
domain: FUZZING
updated: "2026-04-24"
route:
  keywords: [hypofuzz, hypothesis, fuzz_hypofuzz.sh, deep mode, preflight, repro]
  questions: ["how do I run HypoFuzz?", "what does --deep do?", "how do I reproduce a Hypothesis failure?"]
---

# HypoFuzz Guide

**Purpose**: Run the property-testing and HypoFuzz entry points shipped by the repository.
**Prerequisites**: `uv sync --group dev --group fuzz`.

## Common Commands

```bash
./scripts/fuzz_hypofuzz.sh
./scripts/fuzz_hypofuzz.sh --deep --time 300
./scripts/fuzz_hypofuzz.sh --preflight
./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_runtime_bundle_state_machine.py::test_state_machine
```

## Modes

- Default mode runs the standard Hypothesis-backed checks.
- `--deep` runs the intensive fuzz surface.
- `--preflight` audits event instrumentation and strategy coverage.
- `--repro` replays a known failing target.

## Notes

- The script pivots into `.venv-3.13` by default.
- `--metrics` is intended for metric-focused runs rather than indefinite continuous fuzzing.
