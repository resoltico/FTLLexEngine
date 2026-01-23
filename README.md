<!--
RETRIEVAL_HINTS:
  keywords: [ftllexengine, fluent, localization, i18n, l10n, ftl, translation, plurals, babel, cldr, python, parsing, currency, dates, thread-safe, fiscal, iso, territory, decimal-digits]
  answers: [what is ftllexengine, how to install, quick start, fluent python, localization library, currency parsing, date parsing, thread safety, fiscal calendar, iso introspection, territory currency]
  related: [docs/QUICK_REFERENCE.md, docs/DOC_00_Index.md, docs/PARSING_GUIDE.md, docs/TERMINOLOGY.md]
-->

[![FTLLexEngine Art](https://raw.githubusercontent.com/resoltico/FTLLexEngine/main/images/FTLLexEngine.jpg)](https://github.com/resoltico/FTLLexEngine)

-----

[![PyPI](https://img.shields.io/pypi/v/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![Python Versions](https://img.shields.io/pypi/pyversions/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![codecov](https://codecov.io/github/resoltico/FTLLexEngine/graph/badge.svg?token=Q5KUGU3S3U)](https://codecov.io/github/resoltico/FTLLexEngine)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

-----

# FTLLexEngine

**Declarative localization for Python. Plurals, grammar, and formatting in `.ftl` files - not your code.**

"1 coffee" or "5 coffees" - simple in English. Polish has 4 plural forms. Arabic has 6. FTLLexEngine handles them all so your code stays clean.

But it goes further: **bidirectional parsing**. Your customer types `"1 234,56"` in France or `"1,234.56"` in the US - FTLLexEngine parses both to `Decimal('1234.56')`. Parse errors return as structured data, not raised exceptions.

Built on the [Fluent specification](https://projectfluent.org/) that powers Firefox. 200+ locales via Unicode CLDR. Thread-safe.

---

## Why FTLLexEngine?

- **Bidirectional** - Format data for display *and* parse user input back to Python types
- **Thread-safe** - No global state. Serve 1000 concurrent requests without locale conflicts
- **Strict mode** - Opt-in fail-fast. Errors raise exceptions, not silent `{$amount}` fallbacks
- **Introspectable** - Query what variables a message needs before you call it
- **Declarative grammar** - Plurals, gender, cases in `.ftl` files. Code stays clean

---

## Quickstart

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
order = { $count ->
    [one]   1 coffee
   *[other] { $count } coffees
}
""")

result, _ = bundle.format_pattern("order", {"count": 5})
# "5 coffees"
```

**Parse user input back to Python types:**

```python
from ftllexengine.parsing import parse_decimal

# French customer enters a price
amount, errors = parse_decimal("1 234,56", "fr_FR")
# amount = Decimal('1234.56') - not a float, not an exception

if errors:
    print(errors[0])  # Structured error with input, locale, parse type
```

---

## Table of Contents

- [Installation](#installation)
- [Your Cafe Speaks Every Language](#your-cafe-speaks-every-language)
- [Customers Type Prices. You Get Decimals.](#customers-type-prices-you-get-decimals)
- [Concurrent Requests? No Problem.](#concurrent-requests-no-problem)
- [Know What Your Messages Need](#know-what-your-messages-need)
- [Your Cafe Expands Worldwide](#your-cafe-expands-worldwide)
- [When to Use FTLLexEngine](#when-to-use-ftllexengine)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

```bash
uv add ftllexengine[babel]
```

Or with pip:

```bash
pip install ftllexengine[babel]
```

**Requirements**: Python >= 3.13 | Babel >= 2.17

<details>
<summary>Parser-only installation (no Babel dependency)</summary>

```bash
uv add ftllexengine
```

Or: `pip install ftllexengine`

**Works without Babel:**
- FTL syntax parsing (`parse_ftl()`, `serialize_ftl()`)
- AST manipulation and transformation
- Validation and introspection

**Requires Babel:**
- `FluentBundle` (locale-aware formatting)
- `FluentLocalization` (multi-locale fallback)
- Bidirectional parsing (numbers, dates, currency)

</details>

---

## Your Cafe Speaks Every Language

You run a coffee shop. "1 coffee" or "5 coffees" - simple in English. But your app goes global.

**The problem:** Polish has four plural forms. Arabic has six. Your if-statements turn into spaghetti.

**The solution:** Move grammar rules to `.ftl` files. Your code just passes data.

**cafe.ftl**
```fluent
order-message = { $count ->
    [0]     no coffees ordered
    [one]   1 coffee ordered
   *[other] { $count } coffees ordered
}

total = Total: { CURRENCY($amount, currency: "USD") }
```

```python
from pathlib import Path
from decimal import Decimal
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource(Path("cafe.ftl").read_text())

result, _ = bundle.format_pattern("order-message", {"count": 5})
# "5 coffees ordered"

result, _ = bundle.format_pattern("total", {"amount": Decimal("18.75")})
# "Total: $18.75"
```

Now add Polish - four plural forms, zero code changes:

**cafe_pl.ftl**
```fluent
order-message = { $count ->
    [0]     brak kaw
    [one]   1 kawa
    [few]   { $count } kawy
    [many]  { $count } kaw
   *[other] { $count } kawy
}
```

```python
bundle = FluentBundle("pl_PL")
bundle.add_resource(Path("cafe_pl.ftl").read_text())

result, _ = bundle.format_pattern("order-message", {"count": 5})
# "5 kaw"

result, _ = bundle.format_pattern("order-message", {"count": 2})
# "2 kawy"
```

Japanese? Same pattern, different script:

**cafe_ja.ftl**
```fluent
order-message = { $count ->
    [0]     コーヒーの注文なし
    [one]   コーヒー1杯
   *[other] コーヒー{ $count }杯
}
```

```python
bundle = FluentBundle("ja_JP")
bundle.add_resource(Path("cafe_ja.ftl").read_text())

result, _ = bundle.format_pattern("order-message", {"count": 3})
# "コーヒー3杯"
```

German, Spanish, Arabic - same pattern. Translators edit `.ftl` files. Developers ship features.

---

## Customers Type Prices. You Get Decimals.

A customer in Germany types their tip: `"5,00"`. A customer in the US types `"5.00"`. Both mean five dollars.

Most libraries only format *outbound* - they turn your data into display strings. FTLLexEngine works *both directions*.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_decimal, parse_date

# American customer types a tip
tip_result, errors = parse_currency("$5.00", "en_US", default_currency="USD")
if not errors:
    tip, currency = tip_result  # (Decimal('5.00'), 'USD')

# German customer types a price
price, errors = parse_decimal("1.234,56", "de_DE")
# Decimal('1234.56')

# French format: space for thousands, comma for decimal
price, errors = parse_decimal("1 234,56", "fr_FR")
# Decimal('1234.56')

# Dates work too
date_val, errors = parse_date("Jan 15, 2026", "en_US")
# datetime.date(2026, 1, 15)
```

**When parsing fails, you get errors - not exceptions:**

```python
price, errors = parse_decimal("five fifty", "en_US")
# price = None
# errors = (FrozenFluentError(...),)

if errors:
    err = errors[0]
    print(err)  # "Failed to parse decimal 'five fifty' for locale 'en_US': ..."

    # Structured data for programmatic handling
    err.input_value   # "five fifty"
    err.locale_code   # "en_US"
    err.parse_type    # "decimal"
```

### Financial Calculations Stay Exact

Your cafe calculates bills. Float math fails you: `0.1 + 0.2 = 0.30000000000000004`.

FTLLexEngine uses `Decimal` throughout:

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency

tip_result, errors = parse_currency("$5.00", "en_US", default_currency="USD")
if not errors:
    tip, currency = tip_result  # (Decimal('5.00'), 'USD')

    subtotal = Decimal("13.50")  # 3 espressos at $4.50
    tax = subtotal * Decimal("0.08")  # 8% tax
    total = subtotal + tax + tip
    # Decimal('19.58') - exact, every time
```

### Strict Mode: No Silent Failures

Some applications cannot tolerate silent fallbacks. A missing variable returning `{$amount}` instead of raising could display wrong data.

```python
from decimal import Decimal
from ftllexengine import FluentBundle
from ftllexengine.integrity import FormattingIntegrityError

# strict=True raises on ANY error instead of returning fallback
bundle = FluentBundle("en_US", strict=True, enable_cache=True)
bundle.add_resource("balance = Account: { CURRENCY($amount, currency: \"USD\") }")

# Works normally
result, _ = bundle.format_pattern("balance", {"amount": Decimal("1234.56")})
# "Account: $1,234.56"

# Missing variable? Raises immediately - no silent fallback
try:
    bundle.format_pattern("balance", {})  # oops, forgot $amount
except FormattingIntegrityError as e:
    # e.message_id = "balance"
    # e.fallback_value = "Account: {$amount}"  <- what non-strict would return
    # e.fluent_errors = (FrozenFluentError(...),)
    handle_incident(e)  # log, alert, fail request
```

---

## Concurrent Requests? No Problem.

Your cafe gets busy. Flask, FastAPI, Django - concurrent requests, each customer in a different locale.

**The problem:** Python's `locale` module uses global state. Thread A sets German, Thread B reads it, chaos ensues.

**The solution:** FTLLexEngine bundles are isolated. No global state. No locks you manage. No race conditions.

```python
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from ftllexengine import FluentBundle

# Create locale-specific bundles (typically done once at startup)
us_bundle = FluentBundle("en_US")
de_bundle = FluentBundle("de_DE")
jp_bundle = FluentBundle("ja_JP")

ftl_source = "receipt = Total: { CURRENCY($amount, currency: \"USD\") }"
us_bundle.add_resource(ftl_source)
de_bundle.add_resource(ftl_source)
jp_bundle.add_resource(ftl_source)

def format_receipt(bundle, amount):
    result, _ = bundle.format_pattern("receipt", {"amount": amount})
    return result

with ThreadPoolExecutor(max_workers=100) as executor:
    futures = [
        executor.submit(format_receipt, us_bundle, Decimal("1234.50")),  # "Total: $1,234.50"
        executor.submit(format_receipt, de_bundle, Decimal("1234.50")),  # "Total: 1.234,50 $"
        executor.submit(format_receipt, jp_bundle, Decimal("1234.50")),  # "Total: $1,234.50"
    ]
    receipts = [f.result() for f in futures]
```

`FluentBundle` is thread-safe by design:
- Multiple threads can format messages simultaneously (read lock)
- Adding resources or functions acquires exclusive access (write lock)
- You don't manage any of this - it just works

---

## Know What Your Messages Need

Your AI agent generates order confirmations. Before it calls `format_pattern()`, it needs to know: *what variables does this message require?*

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

info.get_variable_names()
# frozenset({'customer_name', 'quantity', 'total'})

info.get_function_names()
# frozenset({'CURRENCY'})

info.has_selectors
# True (uses plural selection)

info.requires_variable("customer_name")
# True
```

**Use cases:**
- AI agents verify they have all required data before formatting
- Form builders auto-generate input fields from message templates
- Linters catch missing variables at build time, not runtime

---

## Your Cafe Expands Worldwide

Your cafe chain opens in Tokyo, London, and New York. Each country uses a different currency. Each has a different fiscal year.

**The problem:** Japan uses yen with no decimal places (no cents). Kuwait uses dinar with 3 decimal places. The UK fiscal year starts in April; the US federal government starts in October.

**The solution:** Query ISO standards data and calculate fiscal periods.

### Which Currency for Each Location?

```python
from ftllexengine.introspection.iso import get_territory_currency, get_currency

# New location in Japan - what currency?
currency_code = get_territory_currency("JP")
# "JPY"

# How many decimal places for yen?
jpy = get_currency("JPY")
jpy.decimal_digits
# 0 - no cents in Japan

# Compare to US dollar
usd = get_currency("USD")
usd.decimal_digits
# 2 - dollars and cents
```

Your receipts format correctly - no `$5.00` in Tokyo, just `¥500`.

### Quarterly Reports Across Time Zones

```python
from datetime import date
from ftllexengine.parsing.fiscal import FiscalCalendar

# UK cafe: fiscal year starts April
uk_calendar = FiscalCalendar(start_month=4)

# US cafe: calendar year
us_calendar = FiscalCalendar(start_month=1)

today = date(2026, 3, 15)

# Same calendar date, different fiscal years
uk_calendar.fiscal_year(today)
# 2026 (UK FY2026 runs Apr 2025 - Mar 2026)

us_calendar.fiscal_year(today)
# 2026

# When does UK Q4 end?
uk_calendar.quarter_end_date(2026, 4)
# date(2026, 3, 31)
```

Your accountants in London and New York see the correct fiscal periods for their jurisdiction.

---

## When to Use FTLLexEngine

### Use It When:

| Scenario | Why FTLLexEngine |
| :--- | :--- |
| **Parsing user input** | Errors as data, not exceptions. Show helpful feedback. |
| **Financial calculations** | `Decimal` precision. Strict mode available. |
| **Web servers** | Thread-safe. No global locale state. |
| **Complex plurals** | Polish has 4 forms. Arabic has 6. Handle them declaratively. |
| **Multi-locale apps** | 200+ locales. CLDR-compliant. |
| **Multi-currency apps** | ISO 4217 data. Territory-to-currency mapping. Decimal places. |
| **Fiscal calendar logic** | UK/Japan/Australia fiscal years. Quarter calculations. |
| **AI integrations** | Introspect messages before formatting. |
| **Content/code separation** | Translators edit `.ftl` files. Developers ship code. |

### Use Something Simpler When:

| Scenario | Why Skip It |
| :--- | :--- |
| **Single locale, no user input** | `f"{value:,.2f}"` is enough |
| **No grammar logic** | No plurals, no conditionals |
| **Zero dependencies required** | You need pure stdlib |

---

## Documentation

| Resource | Description |
|:---------|:------------|
| [Quick Reference](docs/QUICK_REFERENCE.md) | Copy-paste patterns for common tasks |
| [API Reference](docs/DOC_00_Index.md) | Complete class and function documentation |
| [Parsing Guide](docs/PARSING_GUIDE.md) | Bidirectional parsing deep-dive |
| [Data Integrity](docs/DATA_INTEGRITY_ARCHITECTURE.md) | Strict mode, checksums, immutable errors |
| [Terminology](docs/TERMINOLOGY.md) | Fluent and FTLLexEngine concepts |
| [Examples](examples/) | Working code you can run |

---

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and guidelines.

---

## License

MIT License - See [LICENSE](LICENSE).

Implements the [Fluent Specification](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf) (Apache 2.0).

**Legal**: [PATENTS.md](PATENTS.md) | [NOTICE](NOTICE)
