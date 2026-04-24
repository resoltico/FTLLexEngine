---
afad: "4.0"
version: "0.165.0"
domain: EXAMPLES
updated: "2026-04-24"
route:
  keywords: [examples, mypy, type checking, strict, explicit ownership, thread safety]
  questions: ["how do I type-check the examples?", "what mypy config do the examples use?", "how do the examples stay strict without local stubs?"]
---

# Example Type Checking

**Purpose**: Explain how the example scripts are type-checked and how they stay strict without local stub overlays.
**Prerequisites**: Dev environment synced with `uv sync --group dev`.

## Overview

The `examples/` directory uses its own `mypy.ini` so the example code stays strict and self-contained. The examples now model explicit object ownership directly in Python instead of relying on dynamic per-thread attributes, so they type-check cleanly with standard library types alone.

Run the examples type check from the repository root:

```bash
uv run mypy --config-file examples/mypy.ini examples
```

## Files

| Path | Role |
|:-----|:-----|
| `examples/mypy.ini` | Strict mypy configuration for example code |
| `examples/thread_safety.py` | Thread-safety examples that keep worker-owned state explicit |

## Why No Local Stub Is Needed

The examples avoid patterns that depend on dynamic attributes or implicit shared mutation. That keeps the scripts easier to reason about, easier to audit, and naturally compatible with strict type checking.

When per-worker customization is needed, build the owned object directly inside the worker or pass it explicitly. That approach matches the project’s architecture guidance and removes the need for local stub maintenance.
