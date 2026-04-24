---
afad: "4.0"
version: "0.165.0"
domain: EXAMPLES
updated: "2026-04-24"
route:
  keywords: [examples, quickstart, parser-only, localization, custom functions, thread safety, benchmarks]
  questions: ["what examples are available?", "how do I run the examples?", "which example should I start with?"]
---

# FTLLexEngine Examples

**Purpose**: Show which runnable example scripts ship with the repository and what each one demonstrates.
**Prerequisites**: Development environment synced with `uv sync --group dev`.

## Overview

Every `examples/*.py` script is intended to run directly from the repository root. The command below exercises the full shipped example set under the project’s Python 3.13 environment.

Run one example:

```bash
uv run --python 3.13 python examples/quickstart.py
```

Run all examples:

```bash
uv run --python 3.13 python scripts/run_examples.py
```

## Example Map

| Script | Focus |
|:-------|:------|
| `quickstart.py` | Single-locale bundle usage, variables, plurals, parsing handoff |
| `parser_only.py` | Parser-only install surface: zero-dependency helper facades, parse, validate, inspect, serialize |
| `locale_fallback.py` | `FluentLocalization`, fallback chains, disk and custom loaders |
| `bidirectional_formatting.py` | Locale-aware parsing for numbers, dates, currency |
| `async_bundle.py` | `AsyncFluentBundle`, concurrent formatting, streamed loads in asyncio apps |
| `custom_functions.py` | `FunctionRegistry`, `bundle.add_function()`, `@fluent_function` |
| `function_introspection.py` | Introspection APIs and function metadata |
| `ftl_transform.py` | AST transforms and serialization |
| `ftl_linter.py` | Validation and custom lint-style checks |
| `streaming_resources.py` | `add_resource_stream()`, `parse_stream_ftl()`, streamed localization loads |
| `thread_safety.py` | Shared bundle and task-local patterns |
| `property_based_testing.py` | Hypothesis-oriented usage examples |
| `benchmark_loaders.py` | Loader micro-benchmarks |

## Picking A Starting Point

- New to the runtime: start with `examples/quickstart.py`.
- Working in a parser-only install: start with `examples/parser_only.py`.
- Building a multi-locale app: use `examples/locale_fallback.py`.
- Accepting localized user input: use `examples/bidirectional_formatting.py`.
- Building asyncio handlers: use `examples/async_bundle.py`.
- Loading large or streamed FTL resources: use `examples/streaming_resources.py`.

## Type Checking

The examples have a dedicated mypy configuration:

```bash
uv run mypy --config-file examples/mypy.ini examples
```

Related guide:

- [README_TYPE_CHECKING.md](README_TYPE_CHECKING.md)
