---
afad: "4.0"
version: "0.164.0"
domain: REFERENCE
updated: "2026-04-24"
route:
  keywords: [quick reference, cheat sheet, fluentbundle, fluentlocalization, parsing, validation, boot]
  questions: ["show me the common commands", "what is the smallest working example?", "how do I boot localization safely?"]
---

# FTLLexEngine Quick Reference

## Install

```bash
# Full runtime (locale formatting, localization, parsing)
uv add ftllexengine[babel]

# Parser-only (syntax, AST, validation, introspection)
uv add ftllexengine
```

## Format One Message

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource("welcome = Hello, { $name }!")
result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
assert errors == ()
assert result == "Hello, Alice!"
```

## Multi-Locale Fallback

```python
from ftllexengine import FluentLocalization

l10n = FluentLocalization(["lv_LV", "en_US"])
l10n.add_resource("en_US", "checkout = Checkout")
l10n.add_resource("lv_LV", "checkout = Apmaksa")
result, errors = l10n.format_value("checkout")
assert errors == ()
assert result == "Apmaksa"
```

## Parse Localized Input

```python
from decimal import Decimal
from ftllexengine.parsing import parse_currency, parse_decimal

amount, errors = parse_decimal("12,450.50", "en_US")
assert errors == ()
assert amount == Decimal("12450.50")

money, errors = parse_currency("12.450,50 EUR", "de_DE", default_currency="EUR")
assert errors == ()
assert money == (Decimal("12450.50"), "EUR")
```

## Validate FTL Before Loading

```python
from ftllexengine import validate_resource

result = validate_resource("welcome = Hello, { $name }!")
assert result.is_valid
assert result.error_count == 0
```

## Boot Validation

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
    l10n, summary, schema_results = cfg.boot()
    assert summary.all_clean
    assert schema_results[0].is_valid
```

## Register A Custom Function

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

## Clear Module Caches

```python
from ftllexengine import clear_module_caches

clear_module_caches()
clear_module_caches(frozenset({"parsing.dates", "locale"}))
# Unknown selector names raise ValueError instead of being ignored.
```
