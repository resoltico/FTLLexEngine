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

"1 bag" or "500 bags" - simple in English. Polish has 4 plural forms. Arabic has 6. FTLLexEngine handles them all so your code stays clean.

But it goes further: **bidirectional parsing**. Your buyer in Hamburg types `"12.450,00 EUR"`. Your seller in Bogota types `"45.000.000 COP"`. FTLLexEngine parses both to `Decimal` with currency code. Parse errors return as structured data, not raised exceptions.

Built on the [Fluent specification](https://projectfluent.org/) that powers Firefox. 200+ locales via Unicode CLDR. Thread-safe.

---

## Why FTLLexEngine?

- **Bidirectional** - Format data for display *and* parse user input back to Python types
- **Thread-safe** - No global state. Process 1000 concurrent trades without locale conflicts
- **Strict mode** - Opt-in fail-fast. Errors raise exceptions, not silent `{$amount}` fallbacks
- **Introspectable** - Query what variables a message needs before you call it
- **Declarative grammar** - Plurals, gender, cases in `.ftl` files. Code stays clean

---

## Quickstart

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
shipment = { $bags ->
    [one]   1 bag of coffee
   *[other] { $bags } bags of coffee
}
""")

result, _ = bundle.format_pattern("shipment", {"bags": 500})
# "500 bags of coffee"
```

**Parse user input back to Python types:**

```python
from ftllexengine.parsing import parse_currency

# German buyer enters a bid price
amount, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
# amount = (Decimal('12450.00'), 'EUR')

if errors:
    print(errors[0])  # Structured error with input, locale, parse type
```

---

## Table of Contents

- [Installation](#installation)
- [Your Operation Speaks Every Language](#your-operation-speaks-every-language)
- [Buyers and Sellers Type Prices. You Get Decimals.](#buyers-and-sellers-type-prices-you-get-decimals)
- [Concurrent Trades? No Problem.](#concurrent-trades-no-problem)
- [Know What Your Messages Need](#know-what-your-messages-need)
- [Your Operation Spans Continents](#your-operation-spans-continents)
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

**Requirements**: Python >= 3.13 | Babel >= 2.18

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

## Your Operation Speaks Every Language

You export specialty coffee. Your invoices go to Tokyo, Hamburg, and New York. "500 bags" - simple in English. But your documents go global.

**The problem:** Polish has four plural forms. Arabic has six. Your if-statements turn into spaghetti.

**The solution:** Move grammar rules to `.ftl` files. Your code just passes data.

**invoice.ftl**
```fluent
shipment-line = { $bags ->
    [0]     No bags shipped
    [one]   1 bag of { $origin } beans
   *[other] { $bags } bags of { $origin } beans
}

invoice-total = Total: { CURRENCY($amount, currency: "USD") }
```

```python
from pathlib import Path
from decimal import Decimal
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource(Path("invoice.ftl").read_text())

result, _ = bundle.format_pattern("shipment-line", {"bags": 500, "origin": "Colombian"})
# "500 bags of Colombian beans"

result, _ = bundle.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
# "Total: $187,500.00"
```

Now add German - your Hamburg buyer needs invoices in their language:

**invoice_de.ftl**
```fluent
shipment-line = { $bags ->
    [0]     Keine Säcke versandt
    [one]   1 Sack { $origin } Bohnen
   *[other] { $bags } Säcke { $origin } Bohnen
}

invoice-total = Gesamt: { CURRENCY($amount, currency: "EUR") }
```

```python
bundle = FluentBundle("de_DE")
bundle.add_resource(Path("invoice_de.ftl").read_text())

result, _ = bundle.format_pattern("shipment-line", {"bags": 500, "origin": "kolumbianische"})
# "500 Säcke kolumbianische Bohnen"

result, _ = bundle.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
# "Gesamt: 187.500,00 €"
```

Japanese for your Tokyo buyer:

**invoice_ja.ftl**
```fluent
shipment-line = { $bags ->
    [0]     出荷なし
   *[other] { $origin }豆 { $bags }袋
}

invoice-total = 合計: { CURRENCY($amount, currency: "JPY") }
```

```python
bundle = FluentBundle("ja_JP")
bundle.add_resource(Path("invoice_ja.ftl").read_text())

result, _ = bundle.format_pattern("shipment-line", {"bags": 500, "origin": "コロンビア"})
# "コロンビア豆 500袋"

result, _ = bundle.format_pattern("invoice-total", {"amount": Decimal("28125000")})
# "合計: ￥28,125,000"
```

Spanish for your origin operations in Colombia - same pattern. Translators edit `.ftl` files. Your trading platform ships features.

---

## Buyers and Sellers Type Prices. You Get Decimals.

A buyer in Germany enters their bid: `"12.450,00"`. A seller in Colombia enters their ask: `"45.000.000"`. Your system needs exact decimals for both.

Most libraries only format *outbound* - they turn your data into display strings. FTLLexEngine works *both directions*.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_decimal, parse_date

# German buyer enters a bid in EUR
bid_result, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
if not errors:
    bid_amount, bid_currency = bid_result  # (Decimal('12450.00'), 'EUR')

# Colombian seller enters an ask in COP
ask_result, errors = parse_currency("45.000.000 COP", "es_CO", default_currency="COP")
if not errors:
    ask_amount, ask_currency = ask_result  # (Decimal('45000000'), 'COP')

# Contract date from Japanese buyer
contract_date, errors = parse_date("2026年3月15日", "ja_JP")
# datetime.date(2026, 3, 15)
```

**When parsing fails, you get errors - not exceptions:**

```python
price, errors = parse_decimal("twelve thousand", "en_US")
# price = None
# errors = (FrozenFluentError(...),)

if errors:
    err = errors[0]
    print(err)  # "Failed to parse decimal 'twelve thousand' for locale 'en_US': ..."
```

### Commodity Calculations Stay Exact

You calculate contract values. Float math fails you: `0.1 + 0.2 = 0.30000000000000004`.

FTLLexEngine uses `Decimal` throughout:

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency

# Parse the contract price
price_result, errors = parse_currency("$4.25", "en_US", default_currency="USD")
if not errors:
    price_per_lb, currency = price_result  # (Decimal('4.25'), 'USD')

    bags = 500
    lbs_per_bag = Decimal("132")  # Standard 60kg bag
    total_lbs = bags * lbs_per_bag
    contract_value = total_lbs * price_per_lb
    # Decimal('280500.00') - exact, every time
```

### Strict Mode: No Silent Failures

Commodity trading cannot tolerate silent fallbacks. A missing variable returning `{$price}` instead of raising could display wrong data on a trade confirmation.

```python
from decimal import Decimal
from ftllexengine import FluentBundle
from ftllexengine.integrity import FormattingIntegrityError

# strict=True raises on ANY error instead of returning fallback
bundle = FluentBundle("en_US", strict=True, enable_cache=True)
bundle.add_resource('confirm = Contract: { $bags } bags at { CURRENCY($price, currency: "USD") }/lb')

# Works normally
result, _ = bundle.format_pattern("confirm", {"bags": 500, "price": Decimal("4.25")})
# "Contract: 500 bags at $4.25/lb"

# Missing variable? Raises immediately - no silent fallback
try:
    bundle.format_pattern("confirm", {"bags": 500})  # forgot $price
except FormattingIntegrityError as e:
    # e.message_id = "confirm"
    # e.fallback_value = "Contract: 500 bags at {!CURRENCY}/lb"
    # e.fluent_errors = (FrozenFluentError(...),)
    halt_trade(e)  # stop the trade, alert compliance
```

---

## Concurrent Trades? No Problem.

Your trading desk gets busy. Bids from Frankfurt, asks from Bogota, confirmations to Tokyo - concurrent requests, each in a different locale.

**The problem:** Python's `locale` module uses global state. Thread A sets German, Thread B reads it, chaos ensues.

**The solution:** FTLLexEngine bundles are isolated. No global state. No locks you manage. No race conditions.

```python
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from ftllexengine import FluentBundle

# Create locale-specific bundles (typically done once at startup)
de_bundle = FluentBundle("de_DE")
es_bundle = FluentBundle("es_CO")
ja_bundle = FluentBundle("ja_JP")

ftl_source = 'confirm = { CURRENCY($amount, currency: "USD") } per { $unit }'
de_bundle.add_resource(ftl_source)
es_bundle.add_resource(ftl_source)
ja_bundle.add_resource(ftl_source)

def format_confirmation(bundle, amount, unit):
    result, _ = bundle.format_pattern("confirm", {"amount": amount, "unit": unit})
    return result

with ThreadPoolExecutor(max_workers=100) as executor:
    futures = [
        executor.submit(format_confirmation, de_bundle, Decimal("4.25"), "lb"),
        executor.submit(format_confirmation, es_bundle, Decimal("4.25"), "lb"),
        executor.submit(format_confirmation, ja_bundle, Decimal("4.25"), "lb"),
    ]
    confirmations = [f.result() for f in futures]
    # ["4,25 $ per lb", "US$4,25 per lb", "$4.25 per lb"]
```

`FluentBundle` is thread-safe by design:
- Multiple threads can format messages simultaneously (read lock)
- Adding resources or functions acquires exclusive access (write lock)
- You don't manage any of this - it just works

---

## Know What Your Messages Need

Your trading platform generates contract confirmations. Before it calls `format_pattern()`, it needs to know: *what variables does this message require?*

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
contract = { $buyer } purchases { $bags ->
        [one] 1 bag
       *[other] { $bags } bags
    } of { $grade } from { $seller } at { CURRENCY($price, currency: "USD") }/lb.
    Shipment: { $port } by { DATETIME($ship_date) }.
""")

info = bundle.introspect_message("contract")

info.get_variable_names()
# frozenset({'buyer', 'bags', 'grade', 'seller', 'price', 'port', 'ship_date'})

info.get_function_names()
# frozenset({'CURRENCY', 'DATETIME'})

info.has_selectors
# True (uses plural selection for bags)

info.requires_variable("price")
# True
```

**Use cases:**
- Trading systems verify all required data before generating confirmations
- Form builders auto-generate input fields from contract templates
- Compliance tools catch missing variables at build time, not during live trading

---

## Your Operation Spans Continents

You source beans from Colombia, Ethiopia, and Brazil. You sell to importers in Japan, Germany, and the US. Each country uses different currencies. Each has different fiscal years for reporting.

**The problem:** Japanese yen has no decimal places (no cents). Kuwaiti dinar has 3 decimal places. The UK fiscal year starts in April; Colombia's starts in January; Japan's corporate fiscal year often starts in April.

**The solution:** Query ISO standards data and calculate fiscal periods.

### Which Currency for Each Market?

```python
from ftllexengine.introspection.iso import get_territory_currencies, get_currency

# New buyer in Japan - what currency?
currencies = get_territory_currencies("JP")
# ("JPY",)

# How many decimal places for yen?
jpy = get_currency("JPY")
jpy.decimal_digits
# 0 - no decimal places for yen

# Compare to Colombian peso
cop = get_currency("COP")
cop.decimal_digits
# 2 - but typically displayed without decimals for large amounts

# Multi-currency territories
panama_currencies = get_territory_currencies("PA")
# ("PAB", "USD") - Panama uses both Balboa and US Dollar
```

Your invoices format correctly - `￥28,125,000` in Tokyo, `$187,500.00` in New York.

### Quarterly Reports Across Jurisdictions

```python
from datetime import date
from ftllexengine.parsing.fiscal import FiscalCalendar, fiscal_year, fiscal_quarter

# UK importer: fiscal year starts April
uk_calendar = FiscalCalendar(start_month=4)

# US operations: calendar year
us_calendar = FiscalCalendar(start_month=1)

# Japan operations: fiscal year starts April
jp_calendar = FiscalCalendar(start_month=4)

today = date(2026, 3, 15)

# Same calendar date, different fiscal years
uk_calendar.fiscal_year(today)  # 2026 (UK FY2026 runs Apr 2025 - Mar 2026)
us_calendar.fiscal_year(today)  # 2026
jp_calendar.fiscal_year(today)  # 2026

# Quick lookups without creating calendar objects
fiscal_quarter(today, start_month=4)  # 4 (Q4 of fiscal year)
fiscal_quarter(today, start_month=1)  # 1 (Q1 of calendar year)

# When does UK Q4 end for filing?
uk_calendar.quarter_end_date(2026, 4)
# date(2026, 3, 31)
```

Your compliance team in London, New York, and Tokyo each see the correct fiscal periods for their jurisdiction.

---

## When to Use FTLLexEngine

### Use It When:

| Scenario | Why FTLLexEngine |
| :--- | :--- |
| **Parsing user input** | Errors as data, not exceptions. Show helpful feedback. |
| **Financial calculations** | `Decimal` precision. Strict mode available. |
| **Trading systems** | Thread-safe. No global locale state. |
| **Complex plurals** | Polish has 4 forms. Arabic has 6. Handle them declaratively. |
| **Multi-locale apps** | 200+ locales. CLDR-compliant. |
| **Multi-currency operations** | ISO 4217 data. Territory-to-currency mapping. Decimal places. |
| **Cross-border compliance** | UK/Japan/US fiscal years. Quarter calculations. |
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
