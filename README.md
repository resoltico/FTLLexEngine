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

**Declarative localization for Python. Bidirectional parsing, thread-safe formatting, and Decimal precision -- in `.ftl` files, not your code.**

## Why FTLLexEngine?

- **Bidirectional** -- Format data for display *and* parse user input back to Python types
- **Thread-safe** -- No global state. 100 concurrent requests, zero locale conflicts
- **Strict mode** -- Opt-in fail-fast. Errors raise exceptions, not silent `{$amount}` fallbacks
- **Introspectable** -- Query what variables a message needs before you call it
- **Declarative grammar** -- Plurals, gender, cases in `.ftl` files. Code stays clean
- **Decimal precision** -- `Decimal` throughout. No float math, no rounding surprises

---

Meet **Alice** and **Bob**.

**Alice** exports specialty coffee. Her invoices ship to buyers in Tokyo, Hamburg, and New York. Three languages, three currency formats, zero tolerance for rounding errors. "1 bag" in English, "1 Sack" in German, "1袋" in Japanese -- and Polish has four plural forms, Arabic has six. She moved grammar rules to `.ftl` files and never looked back.

**Bob** runs supply operations at Mars Colony 1. Personnel from Germany, Japan, and Colombia order provisions in their own locale. A German engineer types `"12.450,00 EUR"`. A Japanese technician enters `"￥1,245,000"`. Bob's system needs exact `Decimal` values from both. One parsing error on a cargo manifest means delayed shipments for 200 colonists.

FTLLexEngine keeps their systems coherent. Built on the [Fluent specification](https://projectfluent.org/) that powers Firefox. 200+ locales via Unicode CLDR. Thread-safe by default.

---

## Quick Start

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
result, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
if not errors:
    amount, currency = result  # (Decimal('12450.00'), 'EUR')
```

---

## Table of Contents

- [Installation](#installation)
- [Multi-Locale Formatting — Alice Ships to Every Port](#multi-locale-formatting--alice-ships-to-every-port)
- [Bidirectional Parsing — Bob Parses Every Input](#bidirectional-parsing--bob-parses-every-input)
- [Thread-Safe Concurrency — 100 Threads, Zero Race Conditions](#thread-safe-concurrency--100-threads-zero-race-conditions)
- [Message Introspection — Pre-Flight Checks](#message-introspection--pre-flight-checks)
- [Currency and Fiscal Data — Operations Across Borders](#currency-and-fiscal-data--operations-across-borders)
- [Architecture at a Glance](#architecture-at-a-glance)
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

## Multi-Locale Formatting — Alice Ships to Every Port

Alice's invoices go to Tokyo, Hamburg, and New York. Same data, different languages, different number formats. She maintains one `.ftl` file per locale. Translators edit the files. Her trading platform ships features.

**English (New York buyer):**

```python
from decimal import Decimal
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US")
bundle.add_resource("""
shipment-line = { $bags ->
    [0]     No bags shipped
    [one]   1 bag of { $origin } beans
   *[other] { $bags } bags of { $origin } beans
}

invoice-total = Total: { CURRENCY($amount, currency: "USD") }
""")

result, _ = bundle.format_pattern("shipment-line", {"bags": 500, "origin": "Colombian"})
# "500 bags of Colombian beans"

result, _ = bundle.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
# "Total: $187,500.00"
```

**German (Hamburg buyer):**

```python
bundle_de = FluentBundle("de_DE")
bundle_de.add_resource("""
shipment-line = { $bags ->
    [0]     Keine Saecke versandt
    [one]   1 Sack { $origin } Bohnen
   *[other] { $bags } Saecke { $origin } Bohnen
}

invoice-total = Gesamt: { CURRENCY($amount, currency: "EUR") }
""")

result, _ = bundle_de.format_pattern("shipment-line", {"bags": 500, "origin": "kolumbianische"})
# "500 Saecke kolumbianische Bohnen"

result, _ = bundle_de.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
# "Gesamt: 187.500,00 €"  (CLDR: locale-specific symbol with non-breaking space)
```

**Japanese (Tokyo buyer):**

```python
bundle_ja = FluentBundle("ja_JP")
bundle_ja.add_resource("""
shipment-line = { $bags ->
    [0]     出荷なし
   *[other] { $origin }豆 { $bags }袋
}

invoice-total = 合計：{ CURRENCY($amount, currency: "JPY") }
""")

result, _ = bundle_ja.format_pattern("shipment-line", {"bags": 500, "origin": "コロンビア"})
# "コロンビア豆 500袋"

result, _ = bundle_ja.format_pattern("invoice-total", {"amount": Decimal("28125000")})
# "合計：￥28,125,000"
```

Bob uses the same pattern at Mars Colony 1. Spanish for the Colombian agronomists? Add one `.ftl` file. Zero code changes.

> In production, translators maintain separate `.ftl` files per locale. Your code loads them with `Path("invoice_de.ftl").read_text()`.

---

## Bidirectional Parsing — Bob Parses Every Input

Most libraries only format outbound data. That's a one-way trip.

Bob's colonists type orders and quantities in their local format. A German engineer enters `"12.450,00 EUR"`. A Colombian agronomist enters `"45.000.000 COP"`. A Japanese technician files a delivery date as `"2026年3月15日"`. FTLLexEngine parses them all to exact Python types.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_decimal, parse_date

# German engineer enters a bid in EUR
bid_result, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
if not errors:
    bid_amount, bid_currency = bid_result  # (Decimal('12450.00'), 'EUR')

# Colombian agronomist enters an ask in COP
ask_result, errors = parse_currency("45.000.000 COP", "es_CO", default_currency="COP")
if not errors:
    ask_amount, ask_currency = ask_result  # (Decimal('45000000'), 'COP')

# Japanese technician enters a delivery date
contract_date, errors = parse_date("2026年3月15日", "ja_JP")
# datetime.date(2026, 3, 15)
```

```mermaid
flowchart TB
    A["German Engineer<br>`12.450,00 EUR`"] --> PA["`parse_currency()`<br>de_DE"]
    B["Colombian Agronomist<br>`45.000.000 COP`"] --> PB["`parse_currency()`<br>es_CO"]
    C["Japanese Technician<br>`2026年3月15日`"] --> PC["`parse_date()`<br>ja_JP"]

    PA --> RA["`Decimal('12450.00')`<br>EUR"]
    PB --> RB["`Decimal('45000000')`<br>COP"]
    PC --> RC["`date(2026, 3, 15)`"]

    RA & RB & RC --> SYS[("Inventory System<br>Exact Python types")]

    style PA fill:#f9f,stroke:#333,stroke-width:2px
    style PB fill:#f9f,stroke:#333,stroke-width:2px
    style PC fill:#f9f,stroke:#333,stroke-width:2px
```

**When parsing fails, you get structured errors -- not exceptions:**

```python
price, errors = parse_decimal("twelve thousand", "en_US")
# price = None
# errors = (FrozenFluentError(...),)

if errors:
    err = errors[0]
    print(err)  # "Failed to parse decimal 'twelve thousand' for locale 'en_US': ..."
```

### Decimal Precision

Alice calculates contract values. Float math fails: `0.1 + 0.2 = 0.30000000000000004`.

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

### No Silent Failures in Space

> [!NOTE]
> A missing variable normally returns a fallback string like `"Contract: 500 bags at {!CURRENCY}/lb"`. In financial systems or mission-critical operations, displaying this to a user is unacceptable.

Enable `strict=True`. FTLLexEngine raises immediately -- no bad data reaches the user.

```python
from decimal import Decimal
from ftllexengine import FluentBundle
from ftllexengine.integrity import FormattingIntegrityError
from ftllexengine.runtime.cache_config import CacheConfig

# strict=True raises on ANY formatting error instead of returning fallback
# integrity_strict=True (default) raises on cache corruption/write conflicts
bundle = FluentBundle("en_US", strict=True, cache=CacheConfig())
bundle.add_resource('confirm = Contract: { $bags } bags at { CURRENCY($price, currency: "USD") }/lb')

# Works normally
result, _ = bundle.format_pattern("confirm", {"bags": 500, "price": Decimal("4.25")})
# "Contract: 500 bags at $4.25/lb"

# Missing variable? Raises immediately
try:
    bundle.format_pattern("confirm", {"bags": 500})  # forgot $price
except FormattingIntegrityError as e:
    print(f"HALT: {e.message_id} failed")
    # e.fallback_value = "Contract: 500 bags at {!CURRENCY}/lb"
    # e.fluent_errors = (FrozenFluentError(...),)
```

---

## Thread-Safe Concurrency — 100 Threads, Zero Race Conditions

Alice's trading desk gets busy. Bids from Frankfurt, asks from Bogota, confirmations to Tokyo -- concurrent requests, each in a different locale. Bob's colony runs the same pattern: 200 settlers, simultaneous orders, mixed locales.

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
    # ["4,25 $ per lb", "US$4,25 per lb", "$4.25 per lb"]  (CLDR locale symbols)
```

`FluentBundle` and `FluentLocalization` are thread-safe by design:
- Multiple threads can format messages simultaneously (read lock)
- Adding resources or functions acquires exclusive access (write lock)
- You don't manage any of this -- it just works

---

## Message Introspection — Pre-Flight Checks

Bob's systems generate cargo manifests. Before calling `format_pattern()`, they verify: *what variables does this message require? Are all of them available?*

Alice's compliance team uses the same introspection to catch missing variables at build time, not during live operations.

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
- Verify all required data before generating manifests or confirmations
- Auto-generate input fields from message templates
- Catch missing variables at build time, not during live operations

---

## Currency and Fiscal Data — Operations Across Borders

Alice sources beans from Colombia, Ethiopia, and Brazil. She sells to importers in Japan, Germany, and the US. Each country uses different currencies with different decimal places. Each has different fiscal years for compliance reporting.

Bob faces the same complexity on Mars: colony expenditures reported to three national space agencies, each with its own fiscal calendar.

### Currency Data

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

Alice's invoices format correctly: JPY 28,125,000 in Tokyo, $187,500.00 in New York.

### Fiscal Calendars

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

Alice's compliance team in London, New York, and Tokyo each see the correct fiscal periods for their jurisdiction. Bob reports colony expenditures on all three calendars simultaneously.

---

## Architecture at a Glance

| Component | What It Does | Requires Babel? |
|:----------|:-------------|:----------------|
| **Syntax** — `ftllexengine.syntax` | FTL parser, AST, serializer, visitor pattern | No |
| **Runtime** — `ftllexengine.runtime` | `FluentBundle`, message resolution, thread-safe formatting, built-in functions (CURRENCY, DATETIME) | Yes |
| **Localization** — `ftllexengine.localization` | `FluentLocalization` multi-locale fallback chains | Yes |
| **Parsing** — `ftllexengine.parsing` | Bidirectional parsing: numbers, dates, currency back to Python types | Yes |
| **Fiscal** — `ftllexengine.parsing.fiscal` | Fiscal calendar arithmetic, quarter calculations | No |
| **Introspection** — `ftllexengine.introspection` | Message variable/function extraction, ISO 3166/4217 territory and currency data | Partial |
| **Validation** — `ftllexengine.validation` | Cycle detection, reference validation, semantic checks | No |
| **Diagnostics** — `ftllexengine.diagnostics` | Structured error types, error codes, formatting | No |
| **Integrity** — `ftllexengine.integrity` | BLAKE2b checksums, strict mode, immutable exceptions | No |

---

## When to Use FTLLexEngine

### Use It When:

| Scenario | Why FTLLexEngine |
| :--- | :--- |
| **Parsing user input** | Errors as data, not exceptions. Show helpful feedback. |
| **Financial calculations** | `Decimal` precision. Strict mode available. |
| **Concurrent systems** | Thread-safe. No global locale state. |
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
