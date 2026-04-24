# FTLLexEngine — Fluent runtime for real-world localization

FTLLexEngine is a Python runtime and parsing toolkit for Fluent `.ftl` resources, built for teams that need locale-aware text, money, dates, and user-input parsing without rebuilding the same rules in application code.

If you are still stitching this together with string interpolation, one-off parsers, and per-locale edge-case fixes, the same bug tends to get fixed in three places.

[![PyPI](https://img.shields.io/pypi/v/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![Python Versions](https://img.shields.io/pypi/pyversions/ftllexengine.svg)](https://pypi.org/project/ftllexengine/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

- Keep plural rules and locale formatting in `.ftl`, close to the messages themselves.
- Parse localized numbers, dates, and currency back into exact Python types.
- Fail startup early when resources or message schemas drift.
- Share internally synchronized bundles safely across concurrent requests.

The nearby alternative is a mix of hand-kept formatting rules, ad-hoc parsing helpers, and translation checks that only happen after a request is already live. FTLLexEngine turns that into one repeatable runtime.

[Try a working snippet](docs/QUICK_REFERENCE.md) · [Take the deeper workflow tour](docs/WORKFLOW_TOUR.md) · [Get the package on PyPI](https://pypi.org/project/ftllexengine/)

## One Small Workflow

For a coffee exporter, one invoice line and one buyer reply are enough to create drift: display logic in one place, parsing logic in another, validation nowhere. FTLLexEngine keeps that move in one stack.

```python
from decimal import Decimal
from ftllexengine import FluentBundle
from ftllexengine.parsing import parse_currency

bundle = FluentBundle("de_DE", use_isolating=False)
bundle.add_resource('quote = Angebot: { CURRENCY($amount, currency: "EUR") }')

text, errors = bundle.format_pattern("quote", {"amount": Decimal("12450.00")})
assert errors == ()
assert text == "Angebot: 12.450,00\u00a0€"

parsed, errors = parse_currency("12.450,00 EUR", "de_DE", default_currency="EUR")
assert errors == ()
assert parsed == (Decimal("12450.00"), "EUR")
```

The same locale-aware runtime formats the outgoing quote and parses the buyer’s reply back into an exact `Decimal`.

## Where It Fits

Use FTLLexEngine when the same message has to survive more than one locale, more than one direction, or more than one layer of your system.

- Good fit: Fluent-based apps, invoice and checkout flows, localized forms, startup validation for translation packs, and systems that care about exact decimals instead of float luck.
- Good fit: Teams that want message grammar, money formatting, and localized input parsing to stay consistent instead of drifting between templates, helpers, and validation code.
- Keep it simple: single-locale apps, plain string formatting, or projects that do not need Fluent at all.

## Start In Two Paths

Use the full runtime when you need formatting, localization orchestration, and localized parsing:

```bash
uv add ftllexengine[babel]
```

Use the parser-only install when you only need syntax parsing, AST work, validation, and zero-dependency helper surfaces:

```bash
uv add ftllexengine
```

Start from the path that matches your job:

- [Copy the smallest working examples](docs/QUICK_REFERENCE.md)
- [Run the shipped examples](examples/README.md)
- [Browse parsing, thread-safety, and boot-validation guides](docs/DOC_00_Index.md)

## Why It Feels Safe To Try

- Published on [PyPI](https://pypi.org/project/ftllexengine/) for Python 3.13+.
- Built around the [Fluent specification](https://projectfluent.org/) and CLDR-backed locale data via Babel.
- Fully typed, MIT-licensed, and shipped with runnable examples plus repository checks for docs, examples, and version sync.
- Supports parser-only installs for syntax and validation work when you do not need the Babel-backed runtime surface.
- Release and publishing steps live in [docs/RELEASE_PROTOCOL.md](docs/RELEASE_PROTOCOL.md).

## Legal

FTLLexEngine is MIT-licensed. The optional `babel` extra adds Babel under BSD-3-Clause terms. FTLLexEngine is an independent implementation of the [Fluent syntax specification](https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf) and is not affiliated with or endorsed by Mozilla.

[LICENSE](LICENSE) · [NOTICE](NOTICE) · [PATENTS.md](PATENTS.md)
