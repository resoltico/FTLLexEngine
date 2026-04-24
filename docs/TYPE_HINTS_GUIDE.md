---
afad: "4.0"
version: "0.165.0"
domain: TYPE_HINTS
updated: "2026-04-24"
route:
  keywords: [type hints, mypy, FluentValue, ParseResult, TypeIs, LocaleCode]
  questions: ["what types does the library expose?", "how do I type parse results?", "which helpers are type guards?"]
---

# Type Hints Guide

**Purpose**: Show the main public typing surfaces exposed by FTLLexEngine.
**Prerequisites**: Python typing basics and mypy or another static checker.

## Overview

The package is fully typed and exposes useful public aliases and guard-style helpers.

Common surfaces:

- `FluentValue`: values accepted by formatting functions.
- `ParseResult[T]`: standard `(value | None, tuple[FrozenFluentError, ...])` parsing return type.
- `LocaleCode`, `MessageId`, `ResourceId`, `FTLSource`: semantic aliases for localization boundaries.
- `is_valid_decimal()`, `is_valid_date()`, `is_valid_datetime()`, `is_valid_currency()`: `TypeIs` guards for parse results.
- `CurrencyCode` and `TerritoryCode`: typed ISO identifiers.

## ParseResult Pattern

```python
from decimal import Decimal
from ftllexengine import ParseResult

def parse_amount(raw: str) -> ParseResult[Decimal]:
    from ftllexengine.parsing import parse_decimal
    return parse_decimal(raw, "en_US")
```

## Mypy

Project-wide mypy configuration lives in `pyproject.toml`. The examples directory has its own strict config in `examples/mypy.ini`.
