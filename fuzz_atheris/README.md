---
afad: "3.5"
version: "0.164.0"
domain: FUZZING
updated: "2026-04-23"
route:
  keywords: [atheris, fuzz inventory, fuzz targets, libfuzzer, corpus]
  questions: ["what do the Atheris fuzzers cover?", "which targets exist?", "how do I map a target name to a file?"]
---

# Atheris Target Inventory

## Summary

| Target | File | Concern |
|:-------|:-----|:--------|
| `bridge` | `fuzz_bridge.py` | Function bridge and registry |
| `builtins` | `fuzz_builtins.py` | Built-in formatting functions |
| `cache` | `fuzz_cache.py` | Cache concurrency and audit behavior |
| `currency` | `fuzz_currency.py` | Currency formatting oracle |
| `cursor` | `fuzz_cursor.py` | Cursor and parse-position helpers |
| `dates` | `fuzz_dates.py` | Locale-aware date/datetime parsing |
| `diagnostics_formatter` | `fuzz_diagnostics_formatter.py` | Diagnostic formatter output |
| `graph` | `fuzz_graph.py` | Dependency graph algorithms |
| `integrity` | `fuzz_integrity.py` | Integrity and validation surfaces |
| `introspection` | `fuzz_introspection.py` | Message introspection |
| `iso` | `fuzz_iso.py` | ISO lookup/introspection |
| `locale_context` | `fuzz_locale_context.py` | LocaleContext formatting paths |
| `localization` | `fuzz_localization.py` | `FluentLocalization` orchestration |
| `lock` | `fuzz_lock.py` | RWLock contention behavior |
| `numbers` | `fuzz_numbers.py` | Number formatting oracle |
| `oom` | `fuzz_oom.py` | Parser object-density limits |
| `parse_currency` | `fuzz_parse_currency.py` | Currency parsing and symbol resolution |
| `parse_decimal` | `fuzz_parse_decimal.py` | Decimal and FluentNumber parsing |
| `plural` | `fuzz_plural.py` | CLDR plural category boundaries |
| `roundtrip` | `fuzz_roundtrip.py` | Parser/serializer roundtrip |
| `runtime` | `fuzz_runtime.py` | End-to-end runtime behavior |
| `scope` | `fuzz_scope.py` | Variable scoping invariants |
| `serializer` | `fuzz_serializer.py` | AST-construction serializer paths |
| `structured` | `fuzz_structured.py` | Structure-aware parser stress |

## How To Run

```bash
./scripts/fuzz_atheris.sh numbers --time 60
./scripts/fuzz_atheris.sh --list   # stored crashes/findings, not target names
./scripts/fuzz_atheris.sh --replay runtime path/to/finding
```
