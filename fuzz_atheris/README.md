---
afad: "4.0"
version: "0.167.0"
domain: FUZZING
updated: "2026-05-15"
route:
  keywords: [atheris, fuzz inventory, fuzz targets, libfuzzer, corpus]
  questions: ["what do the Atheris fuzzers cover?", "which targets exist?", "how do I map a target name to a file?"]
---

# Atheris Target Inventory

The executable target registry lives in `targets.tsv`. This table is the human-readable mirror of that manifest.

## Summary

| Target | File | Concern |
|:-------|:-----|:--------|
| `bridge` | `fuzz_bridge.py` | FunctionRegistry bridge machinery |
| `builtins` | `fuzz_builtins.py` | Built-in function Babel boundary |
| `cache` | `fuzz_cache.py` | Cache concurrency plus debug-log and integrity-event behavior |
| `currency` | `fuzz_currency.py` | Currency formatting oracle |
| `cursor` | `fuzz_cursor.py` | Cursor and parse-position helpers |
| `dates` | `fuzz_dates.py` | Locale-aware date and datetime parsing |
| `diagnostics_formatter` | `fuzz_diagnostics_formatter.py` | Diagnostic formatter output and escaping |
| `graph` | `fuzz_graph.py` | Dependency graph algorithms |
| `integrity` | `fuzz_integrity.py` | Semantic validation and data integrity |
| `introspection` | `fuzz_introspection.py` | Message introspection and reference extraction |
| `iso` | `fuzz_iso.py` | ISO lookup and introspection APIs |
| `locale_context` | `fuzz_locale_context.py` | LocaleContext direct formatting API |
| `localization` | `fuzz_localization.py` | FluentLocalization orchestration |
| `lock` | `fuzz_lock.py` | RWLock contention behavior |
| `numbers` | `fuzz_numbers.py` | Number formatting oracle |
| `oom` | `fuzz_oom.py` | Parser object-density limits |
| `parse_currency` | `fuzz_parse_currency.py` | Currency parsing and symbol resolution |
| `parse_decimal` | `fuzz_parse_decimal.py` | Decimal parsing and FluentNumber parsing |
| `plural` | `fuzz_plural.py` | CLDR plural category boundaries |
| `roundtrip` | `fuzz_roundtrip.py` | Parser and serializer roundtrip |
| `runtime` | `fuzz_runtime.py` | End-to-end runtime behavior and strict mode |
| `scope` | `fuzz_scope.py` | Variable scoping invariants |
| `serializer` | `fuzz_serializer.py` | AST-construction serializer paths |
| `structured` | `fuzz_structured.py` | Structure-aware parser stress |

## How To Run

Inside a contributor devcontainer terminal:

- `./scripts/fuzz_atheris.sh --help`
- `./scripts/fuzz_atheris.sh --list`

From the host, use:

```bash
npx --yes @devcontainers/cli up --workspace-folder .
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --help
npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --list
```

For a concrete target run from the host:

- `npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh numbers --time 60`
