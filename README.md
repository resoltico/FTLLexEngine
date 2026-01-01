<!--
RETRIEVAL_HINTS:
  keywords: [ftllexengine, fluent, localization, i18n, l10n, ftl, translation, plurals, babel, cldr, python, parsing, currency, dates, thread-safe]
  answers: [what is ftllexengine, how to install, quick start, fluent python, localization library, currency parsing, date parsing, thread safety]
  related: [docs/QUICK_REFERENCE.md, docs/DOC_00_Index.md, docs/PARSING_GUIDE.md, docs/TERMINOLOGY.md]
-->

[![FTLLexEngine Device, A Steampunk-Inspired Concept Render](https://raw.githubusercontent.com/resoltico/FTLLexEngine/main/images/FTLLexEngine_device.png)](https://github.com/resoltico/FTLLexEngine)

-----

[![PyPI](https://img.shields.io/pypi/v/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/github/resoltico/FTLLexEngine/graph/badge.svg?token=Q5KUGU3S3U)](https://codecov.io/github/resoltico/FTLLexEngine)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

-----

# FTLLexEngine

**A logic engine for text and a parsing gateway.**

FTLLexEngine solves three problems that appear in every application that handles numbers, dates, currency, or user input:

1. **Grammar spaghetti**: `if count == 1... elif count == 0... else...` scattered throughout code
2. **Fragile parsing**: `strptime()` and `Decimal()` crash on imperfect user input
3. **Thread-unsafe formatting**: Python's `locale.setlocale()` is process-global

The library can serve you well as **single-language infrastructure** or as a full **internationalization engine** (it is an independent implementation of the [Fluent Specification](https://projectfluent.org/)).

---

## Table of Contents

- [Installation](#installation)
- [What Problems Does This Solve?](#what-problems-does-this-solve)
- [The Babel Question](#the-babel-question)
- [Core Capabilities](#core-capabilities)
  - [1. Declarative Text Logic](#1-declarative-text-logic)
  - [2. Robust Input Parsing](#2-robust-input-parsing)
  - [3. Thread-Safe Formatting](#3-thread-safe-formatting)
  - [4. Template Introspection](#4-template-introspection)
- [Quick Start](#quick-start)
- [When to Use FTLLexEngine](#when-to-use-ftllexengine)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

```bash
uv add ftllexengine
```

**Requirements**: Python >= 3.13, Babel >= 2.17

### Python Version Support

| Version | Tests | Linting | Fuzzing |
|:--------|:------|:--------|:--------|
| 3.13    | Full  | Full    | Full    |
| 3.14    | Full  | Full    | Limited (Atheris incompatible) |

Both versions run the complete test suite (4,600+ tests) and full static analysis (Ruff, Mypy, Pylint) in CI.

---

## What Problems Does This Solve?

### Problem 1: Grammar Logic in Application Code

Every application that displays counts has code like this:

```python
# Scattered throughout the codebase
def format_order(espresso_count, latte_count):
    # Espresso pluralization
    if espresso_count == 0:
        espresso_text = "no espressos"
    elif espresso_count == 1:
        espresso_text = "1 espresso"
    else:
        espresso_text = f"{espresso_count} espressos"

    # Latte pluralization (same pattern, repeated)
    if latte_count == 0:
        latte_text = "no lattes"
    elif latte_count == 1:
        latte_text = "1 latte"
    else:
        latte_text = f"{latte_count} lattes"

    return f"Order: {espresso_text}, {latte_text}"
```

This pattern repeats for every countable item. In Polish, or Arabic, the rules are more complex (Polish has 4 plural forms). The logic multiplies.

### Problem 2: User Input Crashes Your Application

```python
from decimal import Decimal
from datetime import datetime

# User enters European-format price: "1.234,50"
price = Decimal("1.234,50")  # InvalidOperation exception

# User enters US-format date: "12/25/2025"
date = datetime.strptime("12/25/2025", "%d/%m/%Y")  # ValueError exception

# Your API endpoint returns 500 Internal Server Error
```

Standard library parsing functions raise exceptions on format mismatches. In web forms, CSV imports, or chatbot input, this causes crashes.

### Problem 3: Concurrent Formatting is Broken

```python
import locale
from concurrent.futures import ThreadPoolExecutor

def format_for_user(amount, user_locale):
    locale.setlocale(locale.LC_ALL, user_locale)  # DANGER: Process-global!
    return locale.currency(amount)

# In a web server handling concurrent requests:
with ThreadPoolExecutor() as executor:
    # User A (Germany) and User B (USA) request simultaneously
    # Race condition: both might get German OR American formatting
    future_a = executor.submit(format_for_user, 1234.50, "de_DE")
    future_b = executor.submit(format_for_user, 1234.50, "en_US")
```

Python's `locale` module uses process-global state. In Flask, FastAPI, or Django with multiple threads, `setlocale()` affects all threads. This is documented in [Python's locale module documentation](https://docs.python.org/3/library/locale.html#background-details-hints-tips-and-caveats).

---

## The Babel Question

**"Why not just use Babel directly?"**

Babel provides CLDR data (locale definitions, number patterns, plural rules). FTLLexEngine uses Babel internally. The distinction:

| Aspect | Babel | FTLLexEngine |
| :--- | :--- | :--- |
| **Purpose** | Data layer (formatting functions) | Logic layer (grammar + parsing) |
| **Plurals** | `Locale('en').plural_form(n)` returns category | `.ftl` file encodes the entire decision tree |
| **Parsing** | `parse_decimal()` raises `NumberFormatError` | `parse_decimal()` returns `(result, errors)` |
| **Grammar** | None | Select expressions, terms, attributes |
| **Thread safety** | Safe | Safe (wraps Babel with immutable contexts) |

**When Babel alone is sufficient:**
- You only format output (never parse input)
- You handle one locale at a time
- You have no complex plural or grammatical logic

**When FTLLexEngine adds value:**
- You parse user-entered numbers, dates, or currency
- You need grammar logic separated from code
- You serve multiple locales concurrently
- You want templates that tools can introspect

---

## Core Capabilities

### 1. Declarative Text Logic

Move grammar logic from Python code to declarative resources.

**Before (Python):**
```python
def order_summary(coffees):
    if coffees == 0:
        return "Your order is empty"
    elif coffees == 1:
        return "Your order: 1 coffee"
    else:
        return f"Your order: {coffees} coffees"
```

**After (FTL resource + Python):**

*Resource file (`cafe.ftl`):*
```fluent
order-summary = { $coffees ->
    [0] Your order is empty
    [one] Your order: 1 coffee
   *[other] Your order: { $coffees } coffees
}
```

*Python (data only):*
```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource(open("cafe.ftl").read())

result, _ = bundle.format_pattern("order-summary", {"coffees": 0})
# "Your order is empty"

result, _ = bundle.format_pattern("order-summary", {"coffees": 1})
# "Your order: 1 coffee"

result, _ = bundle.format_pattern("order-summary", {"coffees": 5})
# "Your order: 5 coffees"
```

The `[one]` selector uses CLDR plural rules. For Polish (`pl_PL`), `[few]` and `[many]` categories are also available. The same Python code works; only the `.ftl` file changes.

### 2. Robust Input Parsing

Parsing functions return `(result, errors)` tuples. They never raise exceptions.

**Currency Parsing (Financial Applications):**
```python
from ftllexengine.parsing import parse_currency, parse_decimal
from decimal import Decimal

# Parse European invoice amount: "1.234,50 EUR"
result, errors = parse_currency("1.234,50 EUR", "de_DE")
if result:
    amount, currency_code = result  # (Decimal('1234.50'), 'EUR')
    vat = amount * Decimal("0.19")  # Decimal('234.555') - no float precision loss

# Parse ambiguous symbol with explicit currency
result, errors = parse_currency("$99.99", "en_US", default_currency="USD")
# (Decimal('99.99'), 'USD')

# Malformed input returns errors, not exceptions
result, errors = parse_currency("not a price", "en_US")
# result is None, errors contains FluentParseError with details
```

**Date Parsing (Forms, CSV Import):**
```python
from ftllexengine.parsing import parse_date, parse_datetime

# ISO 8601 (machine format) - always tried first
result, errors = parse_date("2025-12-25", "en_US")
# datetime.date(2025, 12, 25)

# US locale short format (M/d/yy per CLDR)
result, errors = parse_date("12/25/25", "en_US")
# datetime.date(2025, 12, 25)

# US locale medium format (MMM d, y per CLDR)
result, errors = parse_date("Dec 25, 2025", "en_US")
# datetime.date(2025, 12, 25)

# German locale format (dd.MM.y per CLDR medium)
result, errors = parse_date("25.12.2025", "de_DE")
# datetime.date(2025, 12, 25)

# Invalid date returns error, not exception
result, errors = parse_date("not-a-date", "en_US")
# result is None, errors[0].input_value == "not-a-date"
```

**Number Parsing (User Input):**
```python
from ftllexengine.parsing import parse_number, parse_decimal

# German format: period for thousands, comma for decimal
result, errors = parse_decimal("1.234,56", "de_DE")
# Decimal('1234.56')

# Latvian format: space for thousands, comma for decimal
result, errors = parse_decimal("1 234,56", "lv_LV")
# Decimal('1234.56')

# US format
result, errors = parse_decimal("1,234.56", "en_US")
# Decimal('1234.56')
```

### 3. Thread-Safe Formatting

`LocaleContext` provides immutable, thread-safe locale configuration.

```python
from ftllexengine.runtime.locale_context import LocaleContext
from concurrent.futures import ThreadPoolExecutor

# Create immutable contexts (cached internally)
ctx_us = LocaleContext.create("en_US")
ctx_de = LocaleContext.create("de_DE")
ctx_jp = LocaleContext.create("ja_JP")

def format_price(amount, ctx):
    return ctx.format_currency(amount, currency="EUR")

# Safe concurrent formatting - no race conditions
with ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(format_price, 1234.50, ctx_us),  # "€1,234.50"
        executor.submit(format_price, 1234.50, ctx_de),  # "1.234,50 €"
        executor.submit(format_price, 1234.50, ctx_jp),  # "€1,234.50"
    ]
    results = [f.result() for f in futures]
```

Each `LocaleContext` is a frozen dataclass. No global state is mutated. The same context can be shared across threads.

**Note**: `FluentBundle` is fully thread-safe. All public methods (`format_pattern()`, `add_resource()`, `add_function()`) are synchronized via internal RLock. You can safely call any method from multiple threads concurrently.

### 4. Template Introspection

Extract metadata from templates at runtime. Useful for form builders, linters, and AI agents.

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
order-confirmation = { $customer_name }, your order of { $quantity }
    { $quantity ->
        [one] { $drink_type }
       *[other] { $drink_type }s
    } is ready. Total: { CURRENCY($total, currency: "USD") }
""")

info = bundle.introspect_message("order-confirmation")

print(info.get_variable_names())
# frozenset({'customer_name', 'quantity', 'drink_type', 'total'})

print(info.get_function_names())
# frozenset({'CURRENCY'})

print(info.has_selectors)
# True

# Check if specific variable is required
print(info.requires_variable("customer_name"))
# True
```

**Use cases:**
- AI agents verify they have all required variables before formatting
- Form builders auto-generate input fields
- Linters validate template completeness

---

## Quick Start

### Single-Language App (English Only)

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
# Cafe order system
drink-order = { $count ->
    [0] No drinks ordered
    [one] 1 { $drink }
   *[other] { $count } { $drink }s
}

price-display = Total: { CURRENCY($amount, currency: "USD") }

order-time = Order placed: { DATETIME($timestamp, dateStyle: "medium", timeStyle: "short") }
""")

# Format order
result, _ = bundle.format_pattern("drink-order", {"count": 3, "drink": "espresso"})
print(result)  # "3 espressos"

# Format price
from decimal import Decimal
result, _ = bundle.format_pattern("price-display", {"amount": Decimal("12.50")})
print(result)  # "Total: $12.50"

# Format timestamp
from datetime import datetime
result, _ = bundle.format_pattern("order-time", {"timestamp": datetime.now()})
print(result)  # "Order placed: Jan 15, 2025, 2:30 PM"
```

### Parsing User Input

```python
from ftllexengine.parsing import parse_currency, parse_date

# Web form: user enters price
user_input = "$15.99"
result, errors = parse_currency(user_input, "en_US", default_currency="USD")

if errors:
    print(f"Invalid price: {errors[0]}")
else:
    amount, currency = result
    print(f"Parsed: {amount} {currency}")  # "Parsed: 15.99 USD"

# Web form: user enters date (CLDR short format: M/d/yy)
user_date = "1/15/25"
result, errors = parse_date(user_date, "en_US")

if errors:
    print(f"Invalid date: {errors[0]}")
else:
    print(f"Parsed: {result}")  # "Parsed: 2025-01-15"
```

### Multi-Locale Application

```python
from ftllexengine import FluentBundle

# Same message, different locales
resources = {
    "en_US": "coffee-count = { $n -> [one] 1 coffee *[other] { $n } coffees }",
    "de_DE": "coffee-count = { $n -> [one] 1 Kaffee *[other] { $n } Kaffees }",
    "pl_PL": """coffee-count = { $n ->
        [one] 1 kawa
        [few] { $n } kawy
        [many] { $n } kaw
       *[other] { $n } kawy
    }""",
}

for locale, resource in resources.items():
    bundle = FluentBundle(locale)
    bundle.add_resource(resource)

    for n in [1, 2, 5, 22]:
        result, _ = bundle.format_pattern("coffee-count", {"n": n})
        print(f"{locale}: {n} -> {result}")

# Output:
# en_US: 1 -> 1 coffee
# en_US: 2 -> 2 coffees
# en_US: 5 -> 5 coffees
# en_US: 22 -> 22 coffees
# de_DE: 1 -> 1 Kaffee
# de_DE: 2 -> 2 Kaffees
# ...
# pl_PL: 1 -> 1 kawa
# pl_PL: 2 -> 2 kawy      (few)
# pl_PL: 5 -> 5 kaw       (many)
# pl_PL: 22 -> 22 kawy    (few)
```

---

## When to Use FTLLexEngine

### Use FTLLexEngine When:

| Scenario | Reason |
| :--- | :--- |
| **Parsing user input** | Errors returned as data, not exceptions |
| **Financial calculations** | `Decimal` precision, locale-aware currency parsing |
| **Web servers (Flask/FastAPI/Django)** | Thread-safe concurrent formatting |
| **Complex plural/grammar rules** | Declarative logic in `.ftl` files |
| **Multi-locale applications** | 200+ locales, CLDR-compliant |
| **AI/LLM integrations** | Introspection API for template validation |
| **Content/code separation** | Non-developers can edit `.ftl` files |

### Use Standard Library or Babel Directly When:

| Scenario | Reason |
| :--- | :--- |
| **Simple single-locale formatting** | `f"{value:,.2f}"` is sufficient |
| **No user input parsing** | You only format known-good data |
| **No grammar logic needed** | No plurals, no conditionals |
| **Minimal dependencies** | You want zero external packages |

---

## Documentation

| Resource | Description |
|:---------|:------------|
| [Quick Reference](docs/QUICK_REFERENCE.md) | Copy-paste patterns for common tasks |
| [API Reference](docs/DOC_00_Index.md) | Complete class and function documentation |
| [Parsing Guide](docs/PARSING_GUIDE.md) | Locale-aware input parsing |
| [Terminology](docs/TERMINOLOGY.md) | Fluent/FTLLexEngine concept definitions |
| [Examples](examples/) | Working code examples |

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and pull request guidelines.

---

## License

MIT License - See [LICENSE](LICENSE).

Implementation of [Fluent Specification](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf) (Apache 2.0).

**Legal**: [PATENTS.md](PATENTS.md) | [NOTICE](NOTICE)
