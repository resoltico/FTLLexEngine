---
afad: "4.0"
version: "0.165.0"
domain: PARSING
updated: "2026-04-24"
route:
  keywords: [parsing, parse_decimal, parse_currency, parse_date, parse_datetime, parse_fluent_number]
  questions: ["how do I parse localized user input?", "how do I do roundtrip formatting and parsing?", "what do parse errors look like?"]
---

# Parsing Guide

**Purpose**: Parse locale-formatted numbers, currency, dates, and datetimes back into Python values.
**Prerequisites**: Full runtime install (`ftllexengine[babel]`).

## Overview

The parsing API returns `(result, errors)` tuples. Success means `errors == ()`; failure means `result is None` and `errors` contains immutable `FrozenFluentError` objects.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_date, parse_decimal

amount, errors = parse_decimal("12.450,50", "de_DE")
assert errors == ()
assert amount == Decimal("12450.50")

money, errors = parse_currency("12.450,50 EUR", "de_DE", default_currency="EUR")
assert errors == ()
assert money == (Decimal("12450.50"), "EUR")

delivery_date, errors = parse_date("2026年3月15日", "ja_JP")
assert errors == ()
assert delivery_date.isoformat() == "2026-03-15"
```

## FluentNumber Parsing

`parse_fluent_number()` returns a `FluentNumber`, preserving both the numeric value and the localized display string.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_fluent_number

fnum, errors = parse_fluent_number("12.450,00", "de_DE")
assert errors == ()
assert fnum.value == Decimal("12450.00")
assert fnum.precision == 2
assert str(fnum) == "12.450,00"
```

## Type Guards

The `is_valid_*` helpers are useful when you want a boolean guard after parsing.

```python
from ftllexengine.parsing import is_valid_decimal, parse_decimal

value, errors = parse_decimal("not-a-number", "en_US")
assert not is_valid_decimal(value)
assert errors
```

## Roundtrip Rule

For format → parse workflows, use the same locale on both sides. That keeps separators, currency symbols, and CLDR patterns aligned.
