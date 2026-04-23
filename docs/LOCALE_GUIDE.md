---
afad: "3.5"
version: "0.164.0"
domain: LOCALE
updated: "2026-04-23"
route:
  keywords: [locale, NUMBER, DATETIME, CURRENCY, normalize_locale, get_system_locale, use_isolating]
  questions: ["why did my number not format?", "what locale string should I use?", "what does use_isolating do?"]
---

# Locale Guide

**Purpose**: Explain how locale normalization and locale-aware formatting work in FTLLexEngine.
**Prerequisites**: Basic Fluent syntax. The formatting examples use the full runtime install; `normalize_locale()` and `get_system_locale()` also work in parser-only installs.

## Overview

Raw Fluent variable interpolation does not perform locale formatting. Locale-aware rendering only happens when the message explicitly calls `NUMBER()`, `DATETIME()`, or `CURRENCY()`.

```python
from decimal import Decimal
from ftllexengine import FluentBundle

bundle = FluentBundle("de_DE", use_isolating=False)
bundle.add_resource("""
raw = { $amount }
fmt = { CURRENCY($amount, currency: "EUR") }
""")
raw, _ = bundle.format_pattern("raw", {"amount": Decimal("1234.50")})
fmt, _ = bundle.format_pattern("fmt", {"amount": Decimal("1234.50")})
assert raw == "1234.50"
assert fmt == "1.234,50\u00a0€"
```

## Locale Codes

- Public runtime APIs normalize locale codes to the canonical internal form.
- `normalize_locale()` is useful when you need the exact canonical string yourself, but it only canonicalizes spelling and separators.
- Public formatting and localization entry points validate against Babel/CLDR and raise `ValueError` for unknown locales.
- `get_system_locale()` reads the OS and environment variables for a default locale and falls back to `"en_us"` unless `raise_on_failure=True` is used.

```python
from ftllexengine import FluentBundle, get_system_locale, normalize_locale

assert normalize_locale("de-DE") == "de_de"
try:
    FluentBundle("xx_INVALID")
except ValueError:
    pass
else:
    raise AssertionError("Unknown locales must raise ValueError")
detected = get_system_locale()
assert isinstance(detected, str)
assert detected
```

## Bidi Isolation

`use_isolating=True` is the default on bundle and localization classes. It wraps placeables with Unicode bidi isolation marks so interpolated values do not corrupt surrounding RTL/LTR text. Keep it enabled for UI output unless you know the output will stay LTR-only and you need plain strings for logging or snapshot assertions.
