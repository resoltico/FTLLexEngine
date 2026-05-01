---
afad: "4.0"
version: "0.165.0"
domain: REFERENCE
updated: "2026-04-25"
route:
  keywords: [quick reference, cheat sheet, fluentbundle, fluentlocalization, parsing, validation, boot, strict mode]
  questions: ["show me the common patterns", "smallest working example", "how do I boot localization safely?", "strict vs soft mode"]
---

# FTLLexEngine Quick Reference

Common patterns, copy-paste ready. For full workflows and explanations, see [WORKFLOW_TOUR.md](WORKFLOW_TOUR.md).

---

## Install

```bash
# Full runtime (locale formatting, localization, bidirectional parsing)
uv add ftllexengine[babel]
# or: pip install "ftllexengine[babel]"

# Parser only (syntax, AST, validation, introspection — zero Babel dependency)
uv add ftllexengine
# or: pip install ftllexengine
```

---

## Format one message

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource("welcome = Hello, { $name }!")
result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
assert errors == ()
assert result == "Hello, Alice!"
```

---

## Multi-locale fallback

```python
from ftllexengine import FluentLocalization

l10n = FluentLocalization(["lv_LV", "en_US"])
l10n.add_resource("en_US", "checkout = Checkout")
l10n.add_resource("lv_LV", "checkout = Apmaksa")
result, errors = l10n.format_value("checkout")
assert errors == ()
assert result == "Apmaksa"
```

---

## Parse localized user input

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_decimal, parse_date

# Number
amount, errors = parse_decimal("12,450.50", "en_US")
assert errors == ()
assert amount == Decimal("12450.50")

# Currency
money, errors = parse_currency("12.450,50 EUR", "de_DE", default_currency="EUR")
assert errors == ()
assert money == (Decimal("12450.50"), "EUR")

# Date
date, errors = parse_date("2026年3月15日", "ja_JP")
assert errors == ()
assert date.isoformat() == "2026-03-15"
```

### Ambiguous currency symbols

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency

money, errors = parse_currency("$4.25", "en_US")
assert money is None
assert errors

money, errors = parse_currency("$4.25", "en_US", infer_from_locale=True)
assert errors == ()
assert money == (Decimal("4.25"), "USD")
```

Use `infer_from_locale=True` when the request locale is authoritative, or pass a fixed
`default_currency="USD"` when the field contract is already known.

---

## Strict mode vs soft mode

```python
from ftllexengine import FluentBundle, FormattingIntegrityError

# Default strict=True: raises on any resolution error
bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource('confirm = { $bags } bags at { CURRENCY($price, currency: "USD") }/lb')

try:
    bundle.format_pattern("confirm", {"bags": 500})  # $price missing
except FormattingIntegrityError as e:
    print(e.message_id)       # "confirm"
    print(e.fallback_value)   # "500 bags at {!CURRENCY}/lb"

# strict=False: errors returned as data, not raised
soft = FluentBundle("en_US", strict=False, use_isolating=False)
soft.add_resource("confirm = { $bags } bags")
result, errors = soft.format_pattern("confirm", {})
assert errors  # structured error list
```

---

## Validate FTL before loading

```python
from ftllexengine import validate_resource

result = validate_resource("welcome = Hello, { $name }!")
assert result.is_valid
assert result.error_count == 0
```

---

## Boot validation

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from ftllexengine import LocalizationBootConfig

with TemporaryDirectory() as tmp:
    base = Path(tmp) / "locales" / "en_us"
    base.mkdir(parents=True)
    (base / "main.ftl").write_text("welcome = Hello, { $name }!\n", encoding="utf-8")

    cfg = LocalizationBootConfig.from_path(
        locales=("en_US",),
        resource_ids=("main.ftl",),
        base_path=Path(tmp) / "locales" / "{locale}",
        message_schemas={"welcome": {"name"}},
        required_messages=frozenset({"welcome"}),
    )

    # Full boot: returns localization object, load summary, and schema results
    l10n, summary, schema_results = cfg.boot()
    assert summary.all_clean
    assert schema_results[0].is_valid

    # Simple boot: returns only the localization object
    # l10n = cfg.boot_simple()
```

---

## Register a custom function

```python
from ftllexengine import FluentBundle

def UPPER(value: str) -> str:
    return value.upper()

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_function("UPPER", UPPER)
bundle.add_resource("headline = { UPPER($text) }")
result, errors = bundle.format_pattern("headline", {"text": "coffee"})
assert errors == ()
assert result == "COFFEE"
```

---

## Introspect a message contract

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource(
    'order = { $buyer } buys { $bags } bags at { CURRENCY($price, currency: "USD") }/lb'
)

info = bundle.introspect_message("order")
assert info.get_variable_names() == frozenset({"buyer", "bags", "price"})
assert info.get_function_names() == frozenset({"CURRENCY"})
assert info.requires_variable("price") is True
```
