<!--
RETRIEVAL_HINTS:
  keywords: [ftllexengine, fluent, localization, i18n, l10n, ftl, translation, plurals, babel, cldr, python, parsing, currency, dates, thread-safe]
  answers: [what is ftllexengine, how to install, quick start, fluent python, localization library, currency parsing, date parsing, thread safety]
  related: [docs/QUICK_REFERENCE.md, docs/DOC_00_Index.md, docs/PARSING_GUIDE.md, docs/TERMINOLOGY.md]
-->

[![FTLLexEngine Art](https://raw.githubusercontent.com/resoltico/FTLLexEngine/main/images/FTLLexEngine.jpg)](https://github.com/resoltico/FTLLexEngine)

-----

[![PyPI](https://img.shields.io/pypi/v/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![codecov](https://codecov.io/github/resoltico/FTLLexEngine/graph/badge.svg?token=Q5KUGU3S3U)](https://codecov.io/github/resoltico/FTLLexEngine)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

-----

# FTLLexEngine

FTLLexEngine helps you write clean text messages that correctly handle counts like "1 coffee" or "5 coffees". It also lets you accept real user input for numbers, dates, and prices - returning useful errors when the input is not quite right, so you can give clear feedback.

It follows the [Fluent specification](https://projectfluent.org/) used by projects like Firefox.

You can use it for single-language apps or for apps that support many languages.

---

## Table of Contents

- [Installation](#installation)
- [For Apps in One Language](#for-apps-in-one-language)
- [For Cafe Billing and Financial Calculations](#for-cafe-billing-and-financial-calculations)
- [For Apps in Many Languages](#for-apps-in-many-languages)
- [For Busy Web Servers](#for-busy-web-servers)
- [Check What a Message Needs](#check-what-a-message-needs)
- [When to Use FTLLexEngine](#when-to-use-ftllexengine)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

```bash
# Parser-only (no external dependencies)
uv add ftllexengine

# Full runtime with locale formatting (requires Babel)
uv add ftllexengine[babel]
```

**Requirements**: Python >= 3.13 | Babel >= 2.17 (optional for locale formatting)

**What works without Babel:**
- FTL syntax parsing (`parse_ftl()`)
- AST serialization (`serialize_ftl()`)
- AST manipulation and transformation
- Validation and introspection

**What requires Babel:**
- `FluentBundle` (locale-aware message formatting)
- `FluentLocalization` (multi-locale fallback chains)
- Bidirectional parsing (numbers, dates, currency)

### Python Version Support

| Version | Tests | Linting | Fuzzing |
|:--------|:------|:--------|:--------|
| 3.13    | Full  | Full    | Full    |
| 3.14    | Full  | Full    | Limited (Atheris incompatible) |

---

## For Apps in One Language

You are building a cafe app in English. Customers order coffees, and you need to show messages like "1 coffee" or "5 coffees".

Normally you would write if-statements in many places:

```python
if count == 0:
    text = "no coffees"
elif count == 1:
    text = "1 coffee"
else:
    text = f"{count} coffees"
```

With FTLLexEngine you move the rules to a separate file:

**cafe.ftl**
```fluent
order-message = { $count ->
    [0]     no coffees ordered
    [one]   1 coffee ordered
   *[other] { $count } coffees ordered
}

total-message = Total: { CURRENCY($amount, currency: "USD") }
```

In Python:

```python
from ftllexengine import FluentBundle
from decimal import Decimal

bundle = FluentBundle("en_US")
bundle.add_resource(open("cafe.ftl").read())

result, _ = bundle.format_pattern("order-message", {"count": 5})
# "5 coffees ordered"

result, _ = bundle.format_pattern("total-message", {"amount": Decimal("18.75")})
# "Total: $18.75"
```

Your code only passes data. The text rules stay in one place.

Customers also enter dates (for delivery) or prices (for custom tips). People type these in different ways:

```python
from ftllexengine.parsing import parse_date, parse_decimal

date_val, errors = parse_date("Jan 15, 2026", "en_US")
# date(2026, 1, 15), ()

price_val, errors = parse_decimal("5.50", "en_US")
# Decimal('5.50'), ()

# If input is unclear
price_val, errors = parse_decimal("five fifty", "en_US")
# None, (FluentParseError(...),)
```

You can show a helpful message like "Please enter a number like 5.50".

---

## For Cafe Billing and Financial Calculations

Your cafe app now calculates bills. A customer orders 3 espressos at $4.50 each and adds a tip.

You need exact math (no float rounding errors) and correct display.

Parse the tip amount the customer types:

```python
from ftllexengine.parsing import parse_currency
from decimal import Decimal

tip_result, errors = parse_currency("$5.00", "en_US", default_currency="USD")
if not errors:
    tip, currency = tip_result  # (Decimal('5.00'), 'USD')

subtotal = Decimal("13.50")  # 3 x 4.50
tax = subtotal * Decimal("0.08")  # 8% tax
total = subtotal + tax + tip

# All Decimal - exact result
```

Display with a message file:

**bill.ftl**
```fluent
bill-summary =
    { $count } espressos: { CURRENCY($subtotal, currency: "USD") }
    Tax: { CURRENCY($tax, currency: "USD") }
    { $tip ->
        [0] (no tip)
       *[other] Tip: { CURRENCY($tip, currency: "USD") }
    }
    Total: { CURRENCY($total, currency: "USD") }
```

The same file works for any currency or locale later.

---

## For Apps in Many Languages

Your cafe app now serves customers worldwide. Plural rules differ - Polish has special forms for 2-4 and 5+.

You keep the same Python code. Only the message files change.

**cafe_de.ftl** (German)
```fluent
order-message = { $count ->
    [0]     keine Kaffees bestellt
    [one]   1 Kaffee bestellt
   *[other] { $count } Kaffees bestellt
}
```

**cafe_pl.ftl** (Polish)
```fluent
order-message = { $count ->
    [0]     brak kaw
    [one]   1 kawa
    [few]   { $count } kawy
    [many]  { $count } kaw
   *[other] { $count } kawy
}
```

In Python:

```python
bundle = FluentBundle(user_locale)  # e.g. "pl_PL"
bundle.add_resource(open(f"cafe_{user_locale[:2]}.ftl").read())

result, _ = bundle.format_pattern("order-message", {"count": 5})
# Polish: "5 kaw"
```

Input parsing automatically uses the user's locale:

```python
from ftllexengine.parsing import parse_decimal

# German format: comma for decimal
price, errors = parse_decimal("13,50", "de_DE")
# Decimal('13.50')

# Latvian format: space for thousands, comma for decimal
price, errors = parse_decimal("1 234,56", "lv_LV")
# Decimal('1234.56')
```

---

## For Busy Web Servers

Many customers order at once in different locales. Standard Python locale settings are global and can conflict.

FTLLexEngine uses separate contexts:

```python
from ftllexengine.runtime.locale_context import LocaleContext
from concurrent.futures import ThreadPoolExecutor

us_ctx = LocaleContext.create("en_US")
de_ctx = LocaleContext.create("de_DE")

def format_total(amount, ctx):
    return ctx.format_currency(amount, currency="USD")

# Safe even with many simultaneous requests
with ThreadPoolExecutor() as executor:
    futures = [
        executor.submit(format_total, 1234.50, us_ctx),  # "$1,234.50"
        executor.submit(format_total, 1234.50, de_ctx),  # "1.234,50 $"
    ]
    results = [f.result() for f in futures]
```

Each `LocaleContext` is a frozen dataclass. No global state is mutated.

`FluentBundle` is also thread-safe. All public methods (`format_pattern()`, `add_resource()`, `add_function()`) are synchronized via internal RWLock (readers-writer lock). You can safely call any method from multiple threads concurrently.

---

## Check What a Message Needs

If you use AI or build tools to generate messages, you can check required variables first:

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
order-confirmation = { $customer_name }, your order of { $quantity }
    { $quantity ->
        [one] coffee
       *[other] coffees
    } is ready. Total: { CURRENCY($total, currency: "USD") }
""")

info = bundle.introspect_message("order-confirmation")

print(info.get_variable_names())
# frozenset({'customer_name', 'quantity', 'total'})

print(info.get_function_names())
# frozenset({'CURRENCY'})

print(info.has_selectors)
# True

print(info.requires_variable("customer_name"))
# True
```

**Use cases:**
- AI agents verify they have all required variables before formatting
- Form builders auto-generate input fields
- Linters validate template completeness

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
