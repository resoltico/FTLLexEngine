# FTLLexEngine — Fluent localization for Python

FTLLexEngine is a Python library for Fluent `.ftl` resources. It loads and validates Fluent
messages, formats locale-aware output, and parses localized user input back into exact Python
types.

It is designed for applications that want one locale contract for both directions:

- Format messages, currency, dates, and plural forms for 200+ locales through CLDR
- Parse localized input back into `Decimal`, `date`, `datetime`, and related typed values
- Validate `.ftl` resources and message-variable contracts before serving traffic
- Keep locale state inside `FluentBundle` and `FluentLocalization` instances instead of process-global state

## What It Does

Use FTLLexEngine when your application already uses Fluent for output and also needs to accept
localized input such as prices, dates, or quantities.

Typical fit:

- Web services that render localized messages and need to parse localized form input correctly
- Back-office or finance systems that must avoid float drift when reading user-entered amounts
- Applications that want boot-time validation of translation resources instead of discovering
  broken `.ftl` files during a live request
- Concurrent programs that need locale handling without shared mutable global state

## Example: Format Output And Parse Input With The Same Locale Rules

This example formats a German quote and parses a German currency value back to exact data:

```python
from decimal import Decimal
from ftllexengine import FluentBundle
from ftllexengine.parsing import parse_currency

bundle = FluentBundle("de_DE", use_isolating=False)
bundle.add_resource('quote = Angebot: { CURRENCY($amount, currency: "EUR") }')

text, _ = bundle.format_pattern("quote", {"amount": Decimal("12450.00")})
# → "Angebot: 12.450,00 €" (non-breaking space before €)

parsed, _ = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
# → (Decimal("12450.00"), "EUR")
```

The same locale rules produce the outbound text and parse the inbound value. You do not need one
library for formatting and a different parser for localized input.

## Install

Python 3.13 or newer.

Install `ftllexengine[babel]` for the full runtime. This includes Fluent formatting, locale-aware parsing,
and CLDR-backed locale data. Use this option if your application formats localized output or parses
localized user input.

```bash
uv add ftllexengine[babel]
# or: pip install "ftllexengine[babel]"
```

Install `ftllexengine` without extras for the parser-only build. This includes FTL syntax support,
AST types, serialization, and validation, with no Babel dependency. Use this option if you only
need to parse, inspect, validate, or serialize Fluent resources.

```bash
uv add ftllexengine
# or: pip install ftllexengine
```

## Documentation

- [Documentation index](docs/DOC_00_Index.md) — complete map of every Markdown document under `docs/`
- [Quick reference](docs/QUICK_REFERENCE.md) — short copy-paste recipes
- [Workflow tour](docs/WORKFLOW_TOUR.md) — end-to-end examples
- [Runtime and API reference](docs/DOC_00_Index.md) — symbol routing plus guide links
- [Release protocol](docs/RELEASE_PROTOCOL.md) — release and publication workflow
- [Runnable examples](examples/) — executable sample programs

## Legal

FTLLexEngine is MIT-licensed. The optional `[babel]` extra adds Babel under BSD-3-Clause.
FTLLexEngine is an independent implementation of the
[Fluent syntax specification](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf)
and is not affiliated with or endorsed by Mozilla.

[LICENSE](LICENSE) · [NOTICE](NOTICE) · [PATENTS.md](PATENTS.md)
