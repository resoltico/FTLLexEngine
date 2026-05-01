[![FTLLexEngine Art](https://raw.githubusercontent.com/resoltico/FTLLexEngine/main/images/FTLLexEngine.jpg)](https://github.com/resoltico/FTLLexEngine)

[![PyPI](https://img.shields.io/pypi/v/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![Python Versions](https://img.shields.io/pypi/pyversions/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

# FTLLexEngine — Fluent localization runtime and parser for Python

FTLLexEngine is a Python library for the Fluent `.ftl` specification: format locale-aware prices,
dates, and messages for 200+ locales, then parse localized user input back to exact Python types
in the same stack.

Most setups handle the two directions separately — one library brews the outbound message,
something hand-rolled to parse the reply back. Locale rules drift between them. FTLLexEngine runs
both from the same locale, validates `.ftl` resources at boot before the first request, and keeps
threads isolated without touching global state.

- Format currency, dates, and plural messages correctly for 200+ locales via CLDR
- Parse localized user input back to `Decimal`, `date`, or typed values — no float drift
- Validate `.ftl` resources and message schemas at boot, before the first request
- Thread-safe bundles, no global locale state

[Copy-paste patterns](docs/QUICK_REFERENCE.md) · [Workflow tour](docs/WORKFLOW_TOUR.md) · [PyPI](https://pypi.org/project/ftllexengine/)

## Both Ends of the Counter

A specialty coffee exporter invoices buyers in German. Buyers reply in their local number format.
One runtime handles both ends:

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

Same locale rules write the invoice and read the buyer's reply. No separate parser. No float
approximation.

## Where It Fits

Python apps using Fluent `.ftl` for messages, plural rules, and locale-aware formatting —
especially when users send localized prices, dates, or quantities that need to come back as exact
typed values. Systems that validate `.ftl` resources before accepting traffic, and concurrent apps
that need locale isolation without shared mutable state.

## Install

Full runtime — formatting, bidirectional parsing, CLDR locale data:

```bash
uv add ftllexengine[babel]
# or: pip install "ftllexengine[babel]"
```

Parser only — FTL syntax, AST, validation, zero Babel dependency:

```bash
uv add ftllexengine
# or: pip install ftllexengine
```

Python 3.13+. Fully typed. Built on the [Fluent specification](https://projectfluent.org/) with
CLDR data via Babel.

- [Copy-paste patterns](docs/QUICK_REFERENCE.md)
- [Workflow tour](docs/WORKFLOW_TOUR.md)
- [API reference](docs/DOC_00_Index.md)
- [Runnable examples](examples/)

Maintainers: [Release protocol](docs/RELEASE_PROTOCOL.md).

## Legal

MIT-licensed. The optional `[babel]` extra adds Babel under BSD-3-Clause. FTLLexEngine is an
independent implementation of the [Fluent syntax specification](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf)
and is not affiliated with or endorsed by Mozilla.

[LICENSE](LICENSE) · [NOTICE](NOTICE) · [PATENTS.md](PATENTS.md)
