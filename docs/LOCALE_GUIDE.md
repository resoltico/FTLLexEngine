---
afad: "3.1"
version: "0.101.0"
domain: locale
updated: "2026-01-31"
route:
  keywords: [locale, NUMBER, DATETIME, CURRENCY, formatting, BCP-47, locale normalization, str vs NUMBER]
  questions: ["why isn't my number formatted?", "how does locale formatting work?", "NUMBER vs raw variable?", "how to format numbers with locale?", "how to format currency?"]
---

# Locale Formatting Guide

**Purpose**: Understand Fluent's locale-aware formatting behavior and common misconceptions.
**Prerequisites**: Basic FluentBundle usage.

## Overview

Fluent uses **explicit formatting functions** for locale-aware output. Raw variable interpolation produces unformatted strings. This is **by design** per the Fluent specification.

**Key Insight**: If your numbers don't have grouping separators, you need `NUMBER()`. This is not a bug.

---

## Raw Interpolation vs. Formatted Output

| Pattern | Input | Output (de_DE) | Reason |
|:--------|:------|:---------------|:-------|
| `{ $count }` | `1000` | `1000` | Raw interpolation via `str()` |
| `{ NUMBER($count) }` | `1000` | `1.000` | Locale-aware via `NUMBER()` |
| `{ $date }` | `datetime(...)` | `2026-01-12 14:30:00` | Raw `str()` representation |
| `{ DATETIME($date) }` | `datetime(...)` | `12.01.2026, 14:30` | Locale-aware via `DATETIME()` |

---

## Why This Design?

The Fluent specification intentionally separates:

1. **Raw interpolation** (`{ $var }`): Developer controls formatting
2. **Locale-aware formatting** (`{ NUMBER($var) }`): Locale determines format

**Rationale**:
- Not all numbers need locale formatting (IDs, codes, versions)
- Explicit is better than implicit (Python Zen)
- Developers choose when localization applies
- Consistent behavior across implementations

**Reference**: [Project Fluent Guide - Variables](https://projectfluent.org/fluent/guide/variables.html)

---

## NUMBER() Function

Formats numeric values with locale-appropriate separators and decimal points.

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("de_DE")
bundle.add_resource("""
raw-count = Count: { $count }
formatted-count = Count: { NUMBER($count) }
""")

# Raw interpolation
result, _ = bundle.format_pattern("raw-count", {"count": 1234567})
# → "Count: 1234567"

# Locale-aware formatting
result, _ = bundle.format_pattern("formatted-count", {"count": 1234567})
# → "Count: 1.234.567"
```

**NUMBER() Options**:

```python
bundle.add_resource("""
decimal = { NUMBER($value, minimumFractionDigits: 2) }
no-grouping = { NUMBER($value, useGrouping: false) }
custom = { NUMBER($value, minimumFractionDigits: 2, maximumFractionDigits: 4) }
""")
```

| Option | Values | Effect |
|:-------|:-------|:-------|
| `minimumFractionDigits` | integer | Minimum decimal places |
| `maximumFractionDigits` | integer | Maximum decimal places |
| `useGrouping` | boolean | Thousands separators (default: true) |
| `pattern` | string | Custom Babel number pattern |

---

## CURRENCY() Function

Formats monetary values with currency symbol and locale-appropriate formatting.

```python
bundle = FluentBundle("de_DE")
bundle.add_resource("""
price = { CURRENCY($amount, currency: "EUR") }
price-code = { CURRENCY($amount, currency: "EUR", currencyDisplay: "code") }
""")

result, _ = bundle.format_pattern("price", {"amount": 1234.56})
# → "1.234,56 €"

result, _ = bundle.format_pattern("price-code", {"amount": 1234.56})
# → "1.234,56 EUR"
```

**CURRENCY() Options**:

| Option | Values | Effect |
|:-------|:-------|:-------|
| `currency` | ISO 4217 code | Required. Currency code (e.g., "EUR", "USD") |
| `currencyDisplay` | `"symbol"`, `"code"`, `"name"` | Display style (default: "symbol") |
| `pattern` | string | Custom CLDR currency pattern |

---

## DATETIME() Function

Formats date/datetime values with locale-appropriate patterns.

```python
from datetime import datetime
from ftllexengine import FluentBundle

bundle = FluentBundle("lv_LV")
bundle.add_resource("""
raw-date = Date: { $date }
formatted-date = Date: { DATETIME($date) }
""")

now = datetime(2026, 1, 12, 14, 30)

# Raw interpolation
result, _ = bundle.format_pattern("raw-date", {"date": now})
# → "Date: 2026-01-12 14:30:00"

# Locale-aware formatting
result, _ = bundle.format_pattern("formatted-date", {"date": now})
# → "Date: 2026. gada 12. janv."
```

**DATETIME() Options**:

```python
bundle.add_resource("""
short = { DATETIME($date, dateStyle: "short") }
long = { DATETIME($date, dateStyle: "long", timeStyle: "short") }
date-only = { DATETIME($date, dateStyle: "medium") }
""")
```

| Option | Values | Effect |
|:-------|:-------|:-------|
| `dateStyle` | `"full"`, `"long"`, `"medium"`, `"short"` | Preset date format (default: "medium") |
| `timeStyle` | `"full"`, `"long"`, `"medium"`, `"short"` | Preset time format (omit for date-only) |
| `pattern` | string | Custom Babel datetime pattern |

---

## Common Misconceptions

### "My numbers should auto-format"

**Misconception**: `{ $count }` should produce locale-formatted output.

**Reality**: Raw variables use `str()`. Use `NUMBER($count)` for locale formatting.

**Why**: Fluent is explicit by design. Not all numbers need localization (IDs, version numbers, codes).

### "This must be a bug"

**Misconception**: Seeing `1000` instead of `1,000` means something is broken.

**Reality**: This is spec-compliant behavior. The Fluent specification explicitly requires `NUMBER()` for locale-aware number formatting.

### "Other i18n libraries auto-format"

**Misconception**: Because ICU MessageFormat auto-formats, Fluent should too.

**Reality**: Fluent made a deliberate design choice for explicit formatting. This matches Mozilla's implementation and the official specification.

---

## Locale Handling

### Locale Property vs. Babel Locale

`FluentBundle` provides two locale-related properties:

```python
bundle = FluentBundle("en-US")

# Returns input as-is (preserves original)
bundle.locale  # → "en-US"

# Returns normalized Babel identifier
bundle.get_babel_locale()  # → "en_US"
```

**Design Rationale**:
- `locale`: Preserves original for debugging/display
- `get_babel_locale()`: Returns normalized form for Babel operations

### Locale Normalization

Internally, locales are normalized for consistent cache keys:

```python
# All of these produce the same Babel locale:
"en-US"   → "en_US"
"en_US"   → "en_US"
"EN-US"   → "en_US"
"en-us"   → "en_US"
```

BCP-47 is case-insensitive by specification, so all variants are equivalent.

### Locale Context Caching

`LocaleContext` normalizes and caches Babel locale objects:

```python
# Internal: cache key uses normalized form
cache_key = normalize_locale(locale_code)  # "en_US"

# But original is preserved for display
ctx.locale_code  # Returns original input
```

---

## Troubleshooting

### Numbers Not Formatted

**Symptom**: `{ $count }` produces `1000` instead of `1,000`.

**Solution**: Use `{ NUMBER($count) }`.

```python
# Before
bundle.add_resource("count = { $count }")
# Output: "1000"

# After
bundle.add_resource("count = { NUMBER($count) }")
# Output: "1,000" (for en_US)
```

### Dates Not Formatted

**Symptom**: `{ $date }` produces `2026-01-12 14:30:00`.

**Solution**: Use `{ DATETIME($date) }`.

```python
# Before
bundle.add_resource("date = { $date }")
# Output: "2026-01-12 14:30:00"

# After
bundle.add_resource("date = { DATETIME($date, dateStyle: 'long') }")
# Output: "January 12, 2026" (for en_US)
```

### Wrong Locale Format

**Symptom**: Numbers/dates formatted for wrong locale.

**Check**:
1. Verify bundle locale: `bundle.locale`
2. Verify Babel locale: `bundle.get_babel_locale()`
3. Ensure Babel is installed: `pip install ftllexengine[babel]`

---

## Bi-Directional Localization

For parsing locale-formatted user input back to Python types, see [PARSING_GUIDE.md](PARSING_GUIDE.md).

```python
from ftllexengine import FluentBundle
from ftllexengine.parsing import parse_decimal

# Format for display
bundle = FluentBundle("de_DE")
bundle.add_resource("price = { NUMBER($amount) } EUR")
formatted, _ = bundle.format_pattern("price", {"amount": 1234.56})
# → "1.234,56 EUR"

# Parse user input back
result, errors = parse_decimal("1.234,56", "de_DE")
# → Decimal('1234.56')
```

---

## Summary

| Concept | Behavior |
|:--------|:---------|
| `{ $var }` | Raw `str()` interpolation |
| `{ NUMBER($var) }` | Locale-aware number formatting |
| `{ DATETIME($var) }` | Locale-aware date/time formatting |
| `{ CURRENCY($var, currency: "XXX") }` | Locale-aware currency formatting |
| `bundle.locale` | Original input, preserved for display |
| `bundle.get_babel_locale()` | Normalized Babel identifier |

**Remember**: Fluent's explicit formatting is a feature, not a bug. When in doubt, check the [Fluent specification](https://projectfluent.org/fluent/guide/).
