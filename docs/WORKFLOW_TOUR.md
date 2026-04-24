---
afad: "4.0"
version: "0.165.0"
domain: GUIDE
updated: "2026-04-24"
route:
  keywords: [workflow tour, deeper readme material, multi-locale, streaming resources, async bundle, boot validation, introspection]
  questions: ["where did the deeper README workflows move?", "how do I see FTLLexEngine end-to-end workflows?", "which docs cover streaming, async, and boot validation together?"]
---

# FTLLexEngine Workflow Tour

**Purpose**: Preserve the deeper workflows that do not belong in the storefront `README.md` while keeping them easy to find and grounded in runnable examples.
**Prerequisites**: Full runtime install (`ftllexengine[babel]`) for formatting, localization, localized parsing, and ISO metadata lookups.

## Overview

The root `README.md` is the front window: short promise, shortest credible example, and quick next steps. This guide keeps the richer material that matters once you want to evaluate FTLLexEngine as a real working stack instead of a headline.

The library is strongest when you need one coherent path for:

- formatting Fluent messages with locale-aware numbers, dates, and currency,
- parsing localized user input back into exact Python values,
- validating resources before traffic,
- and keeping those operations safe in threaded or asyncio applications.

## Where The Deeper Material Lives

| Topic moved out of the storefront | Best current home |
|:----------------------------------|:------------------|
| Smallest working setup | [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| Multi-locale fallback chains | [examples/locale_fallback.py](../examples/locale_fallback.py) and [LOCALE_GUIDE.md](LOCALE_GUIDE.md) |
| Parsing localized input | [PARSING_GUIDE.md](PARSING_GUIDE.md) and [examples/bidirectional_formatting.py](../examples/bidirectional_formatting.py) |
| Thread-safe shared bundles | [THREAD_SAFETY.md](THREAD_SAFETY.md) and [examples/thread_safety.py](../examples/thread_safety.py) |
| Async applications | [examples/async_bundle.py](../examples/async_bundle.py) |
| Streaming resource loading | [examples/streaming_resources.py](../examples/streaming_resources.py) and [DOC_03_Parsing.md](DOC_03_Parsing.md) |
| Message introspection | [examples/parser_only.py](../examples/parser_only.py) and [DOC_04_Introspection.md](DOC_04_Introspection.md) |
| Startup and schema validation | [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) and [QUICK_REFERENCE.md](QUICK_REFERENCE.md) |
| Currency and territory metadata | [DOC_04_Introspection.md](DOC_04_Introspection.md) |
| Symbol-by-symbol API routing | [DOC_00_Index.md](DOC_00_Index.md) |

## One Runtime For Format And Parse

The core value proposition from the old root README still stands: the same locale theory can format outbound text and parse inbound user input, so the invoice you emit and the reply you accept do not drift into separate rule systems.

- For the fastest copy-paste path, use [QUICK_REFERENCE.md](QUICK_REFERENCE.md).
- For a fuller parsing walkthrough, use [PARSING_GUIDE.md](PARSING_GUIDE.md).
- For runnable end-to-end examples, use [examples/quickstart.py](../examples/quickstart.py) and [examples/bidirectional_formatting.py](../examples/bidirectional_formatting.py).

## Stream Resources Without Building One Giant String

`add_resource_stream()` and `parse_stream_ftl()` let you work from line iterators instead of pre-assembling the entire source in memory first.

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from ftllexengine import FluentBundle, parse_stream_ftl

with TemporaryDirectory() as tmp:
    source_path = Path(tmp) / "messages.ftl"
    source_path.write_text(
        "hello = Hello from orbit\n"
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

For a runnable script that also shows streamed localization loads, use [examples/streaming_resources.py](../examples/streaming_resources.py).

## Use Async Bundles In Event-Loop Applications

`AsyncFluentBundle` keeps the Fluent runtime behavior but offloads mutation and formatting work through `asyncio.to_thread()`, which is the right fit when your application is already organized around async request handling.

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

For a fuller runnable script, use [examples/async_bundle.py](../examples/async_bundle.py).

## Introspect Message Contracts Before Formatting

The message-introspection APIs are the pre-flight surface: inspect required variables and called functions before a live format call, or use the same metadata to generate forms, validation rules, or build-time checks.

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
```

If you only need parsing, validation, and introspection without the Babel-backed runtime, start with [examples/parser_only.py](../examples/parser_only.py).

## Validate Before Traffic

The fail-fast startup path also remains important. `LocalizationBootConfig.boot()` is the canonical way to prove that required resources loaded cleanly and that required message contracts exist before the application starts serving requests.

- Use [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) for the startup pattern.
- Use [DATA_INTEGRITY_ARCHITECTURE.md](DATA_INTEGRITY_ARCHITECTURE.md) for the underlying fail-fast model.
- Use [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for the shortest runnable boot snippet.

## Query Territory And Currency Metadata

The ISO and CLDR-backed helper layer stays useful when product decisions depend on territory defaults or currency precision.

```python
from ftllexengine.introspection import get_currency, get_territory_currencies

assert get_territory_currencies("JP") == ("JPY",)

yen = get_currency("JPY")
assert yen is not None
assert yen.decimal_digits == 0
```

For the full set of helpers, use [DOC_04_Introspection.md](DOC_04_Introspection.md).

## Surface Map

| Surface | Use it for | Install mode |
|:--------|:-----------|:-------------|
| Syntax and validation | Parse, transform, serialize, and validate `.ftl` resources | Parser-only |
| Runtime | `FluentBundle`, built-in functions, locale-aware formatting | Full runtime |
| Localization | `FluentLocalization`, fallback chains, loaders, boot validation | Mixed |
| Parsing | Localized numbers, dates, datetimes, and currency back to Python values | Full runtime |
| Introspection and analysis | Message variables, references, dependency graphs, ISO helpers | Mixed |
| Diagnostics and integrity | Structured errors, strict mode, audit evidence, immutable failure data | Parser-only |

Use [DOC_00_Index.md](DOC_00_Index.md) when you need the exact symbol home instead of the high-level subsystem map.

## Good Fit Versus Simpler Fit

- Strong fit: Fluent-based applications, invoice and checkout flows, localized forms, startup validation for translation packs, and systems that care about exact decimals.
- Strong fit: Teams that want message grammar, formatting rules, parsing rules, and startup checks to stay in one coherent runtime instead of drifting between template helpers and request-time patches.
- Simpler fit: single-locale applications, plain string formatting, or projects that do not need Fluent resources at all.
