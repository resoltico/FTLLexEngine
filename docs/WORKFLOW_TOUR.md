---
afad: "4.0"
version: "0.166.0"
domain: GUIDE
updated: "2026-05-01"
route:
  keywords: [workflow tour, multi-locale, bidirectional parsing, boot validation, thread safety, async, introspection, streaming]
  questions: ["how do I use FTLLexEngine end-to-end?", "multi-locale formatting example", "how do I parse localized user input?", "boot validation example", "thread-safe formatting", "async bundle example"]
---

# FTLLexEngine Workflow Tour

This guide shows FTLLexEngine working as a full stack — format outbound, parse inbound, validate at boot — across the scenarios where it earns its place. Prerequisites: full runtime install (`uv add ftllexengine[babel]`) for all sections except introspection and validation, which work with the parser-only install.

---

## Format for multiple locales

Same message template, three markets. Translators maintain one `.ftl` file per locale. Your code stays the same.

**English — New York buyer:**

```python
from decimal import Decimal
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource("""
shipment-line = { $bags ->
    [0]     No bags shipped
    [one]   1 bag of { $origin } coffee
   *[other] { $bags } bags of { $origin } coffee
}

invoice-total = Total: { CURRENCY($amount, currency: "USD") }
""")

result, _ = bundle.format_pattern("shipment-line", {"bags": 500, "origin": "Colombian"})
assert result == "500 bags of Colombian coffee"

result, _ = bundle.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
assert result == "Total: $187,500.00"
```

**German — Hamburg buyer:**

```python
from decimal import Decimal
from ftllexengine import FluentBundle

bundle_de = FluentBundle("de_DE", use_isolating=False)
bundle_de.add_resource("""
shipment-line = { $bags ->
    [0]     Keine Saecke versandt
    [one]   1 Sack { $origin } Kaffee
   *[other] { $bags } Saecke { $origin } Kaffee
}

invoice-total = Gesamt: { CURRENCY($amount, currency: "EUR") }
""")

result, _ = bundle_de.format_pattern("shipment-line", {"bags": 500, "origin": "kolumbianischer"})
assert result == "500 Saecke kolumbianischer Kaffee"

result, _ = bundle_de.format_pattern("invoice-total", {"amount": Decimal("187500.00")})
assert result == "Gesamt: 187.500,00\u00a0€"  # CLDR: non-breaking space before symbol
```

**Japanese — Tokyo buyer:**

```python
from decimal import Decimal
from ftllexengine import FluentBundle

bundle_ja = FluentBundle("ja_JP", use_isolating=False)
bundle_ja.add_resource("""
shipment-line = { $bags ->
    [0]     出荷なし
   *[other] { $origin }コーヒー { $bags }袋
}

invoice-total = 合計：{ CURRENCY($amount, currency: "JPY") }
""")

result, _ = bundle_ja.format_pattern("shipment-line", {"bags": 500, "origin": "コロンビア"})
assert result == "コロンビアコーヒー 500袋"

result, _ = bundle_ja.format_pattern("invoice-total", {"amount": Decimal("28125000")})
assert result == "合計：￥28,125,000"
```

Add a new market: add one `.ftl` file. Zero code changes.

→ See [LOCALE_GUIDE.md](LOCALE_GUIDE.md) for fallback chains and multi-locale orchestration.

---

## Parse localized user input

Most libraries only format outbound data. FTLLexEngine also parses inbound user input back to exact Python types.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_date, parse_decimal

# German user enters a bid price
bid, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
if not errors:
    amount, currency = bid  # (Decimal("12450.00"), "EUR")

# Colombian user enters an ask
ask, errors = parse_currency("45.000.000 COP", "es_CO", default_currency="COP")
if not errors:
    amount, currency = ask  # (Decimal("45000000"), "COP")

# Japanese user enters a delivery date
date, errors = parse_date("2026年3月15日", "ja_JP")
assert not errors
assert date.isoformat() == "2026-03-15"

# US user enters a weight
weight, errors = parse_decimal("12,450.50", "en_US")
assert not errors
assert weight == Decimal("12450.50")
```

Parse errors come back as structured data, not exceptions:

```python
from ftllexengine.parsing import parse_decimal

price, errors = parse_decimal("twelve thousand", "en_US")
assert price is None
assert errors
print(errors[0])  # "Failed to parse decimal 'twelve thousand' for locale 'en_US': ..."
```

**Decimal precision throughout.** Float math fails for money: `0.1 + 0.2 = 0.30000000000000004`. FTLLexEngine uses `Decimal` everywhere — parse, format, and arithmetic stay exact.

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency

price, _ = parse_currency("$4.25", "en_US", default_currency="USD")
price_per_lb, _ = price  # Decimal("4.25")

bags, lbs_per_bag = 500, Decimal("132")
contract_value = bags * lbs_per_bag * price_per_lb
assert contract_value == Decimal("280500.00")  # exact, every time
```

## Wire a request flow without ambient locale tricks

For request-driven apps, treat locale selection as startup wiring, not as a per-call flag on
one global localization object.

- One `FluentLocalization` instance owns one fallback chain.
- Build or cache one localization per supported chain, then choose the instance from the
  request locale.
- For ambiguous money inputs such as `"$4.25"`, use `infer_from_locale=True` or an
  explicit `default_currency`.

→ See [PARSING_GUIDE.md](PARSING_GUIDE.md) for the full parsing API and locale-specific edge cases.

---

## Validate at startup, not at request time

`LocalizationBootConfig` loads all resources, checks that required messages exist, and validates message schemas before the application accepts any traffic. If anything is wrong, it raises before the first request — not during one.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ftllexengine import LocalizationBootConfig

with TemporaryDirectory() as tmp:
    base = Path(tmp) / "locales"
    for locale, label in {"en_us": "Total", "de_de": "Gesamt", "ja_jp": "合計"}.items():
        locale_dir = base / locale
        locale_dir.mkdir(parents=True)
        (locale_dir / "invoice.ftl").write_text(
            f'invoice-total = {label}: {{ CURRENCY($amount, currency: "USD") }}\n',
            encoding="utf-8",
        )
        (locale_dir / "shipment.ftl").write_text(
            'shipment-line = { $bags } bags of { $origin }\n',
            encoding="utf-8",
        )

    cfg = LocalizationBootConfig.from_path(
        locales=("en_US", "de_DE", "ja_JP"),
        resource_ids=("invoice.ftl", "shipment.ftl"),
        base_path=base / "{locale}",
        message_schemas={
            "invoice-total": {"amount"},
            "shipment-line": {"bags", "origin"},
        },
        required_messages=frozenset({"invoice-total", "shipment-line"}),
    )

    l10n, summary, schema_results = cfg.boot()
    assert summary.all_clean
    assert all(r.is_valid for r in schema_results)
```

Use `boot_simple()` when you only need the localization object:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ftllexengine import LocalizationBootConfig

with TemporaryDirectory() as tmp:
    base = Path(tmp) / "locales"
    locale_dir = base / "en_us"
    locale_dir.mkdir(parents=True)
    (locale_dir / "main.ftl").write_text("welcome = Hello\n", encoding="utf-8")

    cfg = LocalizationBootConfig.from_path(
        locales=("en_US",),
        resource_ids=("main.ftl",),
        base_path=base / "{locale}",
        required_messages=frozenset({"welcome"}),
    )
    l10n = cfg.boot_simple()
    assert l10n is not None
```

→ See [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) and [DATA_INTEGRITY_ARCHITECTURE.md](DATA_INTEGRITY_ARCHITECTURE.md).

---

## Handle concurrent requests

Python's `locale` module uses global state. Setting a locale in one thread affects every other thread. FTLLexEngine bundles are isolated — no global state, no locks you manage.

```python
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from ftllexengine import FluentBundle

de_bundle = FluentBundle("de_DE", use_isolating=False)
es_bundle = FluentBundle("es_CO", use_isolating=False)
ja_bundle = FluentBundle("ja_JP", use_isolating=False)

ftl = 'confirm = { CURRENCY($amount, currency: "USD") } per { $unit }'
for b in (de_bundle, es_bundle, ja_bundle):
    b.add_resource(ftl)

def format_confirmation(bundle, amount, unit):
    result, _ = bundle.format_pattern("confirm", {"amount": amount, "unit": unit})
    return result

with ThreadPoolExecutor(max_workers=100) as executor:
    futures = [
        executor.submit(format_confirmation, de_bundle, Decimal("4.25"), "lb"),
        executor.submit(format_confirmation, es_bundle, Decimal("4.25"), "lb"),
        executor.submit(format_confirmation, ja_bundle, Decimal("4.25"), "lb"),
    ]
    results = [f.result() for f in futures]
    # de_DE: "4,25 $ per lb", es_CO: "US$4,25 per lb", ja_JP: "$4.25 per lb"
```

Multiple threads can format messages simultaneously. Adding resources or functions acquires exclusive access briefly. You do not manage any of this.

→ See [THREAD_SAFETY.md](THREAD_SAFETY.md) and [examples/thread_safety.py](../examples/thread_safety.py).

---

## Use async bundles in event-loop applications

`AsyncFluentBundle` keeps the same strict-mode guarantees but offloads mutations and formatting through `asyncio.to_thread()`, keeping the event loop free.

```python
import asyncio
from decimal import Decimal
from ftllexengine import AsyncFluentBundle

async def main() -> None:
    async with AsyncFluentBundle("en_US", use_isolating=False) as bundle:
        await bundle.add_resource(
            'price = Total: { CURRENCY($amount, currency: "USD") }\n'
            "counter = Count: { $n }"
        )

        price, errors = await bundle.format_pattern("price", {"amount": Decimal("99.99")})
        assert errors == ()
        assert price == "Total: $99.99"

        results = await asyncio.gather(
            *(bundle.format_pattern("counter", {"n": i}) for i in range(3))
        )
        assert [text for text, _ in results] == ["Count: 0", "Count: 1", "Count: 2"]

asyncio.run(main())
```

→ See [examples/async_bundle.py](../examples/async_bundle.py).

---

## Stream resources without loading the whole file

`add_resource_stream()` and `parse_stream_ftl()` accept any line iterator. Useful for large `.ftl` files or network streams where building one giant string first is not practical.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ftllexengine import FluentBundle, parse_stream_ftl

with TemporaryDirectory() as tmp:
    source_path = Path(tmp) / "messages.ftl"
    source_path.write_text(
        "hello = Hello\n"
        "status = Cargo ready\n",
        encoding="utf-8",
    )

    bundle = FluentBundle("en_US", use_isolating=False)
    with source_path.open(encoding="utf-8") as handle:
        junk = bundle.add_resource_stream(handle, source_path=str(source_path))
    assert junk == ()

    status, errors = bundle.format_pattern("status")
    assert errors == ()
    assert status == "Cargo ready"

    with source_path.open(encoding="utf-8") as handle:
        entry_ids = [entry.id.name for entry in parse_stream_ftl(handle)]
    assert entry_ids == ["hello", "status"]
```

→ See [examples/streaming_resources.py](../examples/streaming_resources.py).

---

## Inspect message contracts before formatting

Query what variables and functions a message requires before you call `format_pattern()`. Useful for pre-flight checks, auto-generating input fields, or catching missing variables at build time.

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource(
    'contract = { $buyer } pays { CURRENCY($amount, currency: "USD") } on { DATETIME($ship_date) }'
)

info = bundle.introspect_message("contract")
assert info.get_variable_names() == frozenset({"buyer", "amount", "ship_date"})
assert info.get_function_names() == frozenset({"CURRENCY", "DATETIME"})
assert info.has_selectors is False
assert info.requires_variable("amount") is True
```

→ See [DOC_04_Introspection.md](DOC_04_Introspection.md) and [examples/parser_only.py](../examples/parser_only.py).

---

## Query territory and currency metadata

```python
from ftllexengine.introspection import get_currency, get_territory_currencies

# What currency does Japan use?
assert get_territory_currencies("JP") == ("JPY",)

# How many decimal places for yen?
yen = get_currency("JPY")
assert yen.decimal_digits == 0  # no decimal places

# Compare to Colombian peso
cop = get_currency("COP")
assert cop.decimal_digits == 2

# Multi-currency territories
assert get_territory_currencies("PA") == ("PAB", "USD")
```

→ See [DOC_04_Introspection.md](DOC_04_Introspection.md).

---

## Go deeper

| Topic | Best home |
|:------|:----------|
| Copy-paste patterns | [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| Locale fallback chains | [LOCALE_GUIDE.md](LOCALE_GUIDE.md) · [examples/locale_fallback.py](../examples/locale_fallback.py) |
| Full parsing API | [PARSING_GUIDE.md](PARSING_GUIDE.md) · [examples/bidirectional_formatting.py](../examples/bidirectional_formatting.py) |
| Thread safety details | [THREAD_SAFETY.md](THREAD_SAFETY.md) · [examples/thread_safety.py](../examples/thread_safety.py) |
| Boot validation and strict mode | [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) · [DATA_INTEGRITY_ARCHITECTURE.md](DATA_INTEGRITY_ARCHITECTURE.md) |
| Symbol-by-symbol API | [DOC_00_Index.md](DOC_00_Index.md) |
| Custom functions | [CUSTOM_FUNCTIONS_GUIDE.md](CUSTOM_FUNCTIONS_GUIDE.md) |
| Type hints | [TYPE_HINTS_GUIDE.md](TYPE_HINTS_GUIDE.md) |
