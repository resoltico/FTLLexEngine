---
afad: "4.0"
version: "0.165.0"
domain: CUSTOM_FUNCTIONS
updated: "2026-04-24"
route:
  keywords: [custom functions, fluent_function, FunctionRegistry, locale injection, add_function]
  questions: ["how do I add a custom function?", "how does locale injection work?", "should I use a registry or add_function?"]
---

# Custom Functions Guide

**Purpose**: Add domain-specific functions to `FluentBundle` or `FluentLocalization`.
**Prerequisites**: Full runtime install (`ftllexengine[babel]`) plus familiarity with `FluentBundle.format_pattern()` and FTL function calls.

## Overview

FTLLexEngine supports two patterns:

- `bundle.add_function("NAME", func)` for one bundle or one localization object.
- `FunctionRegistry` for reusable or shared function sets.
- This guide assumes the full runtime because the examples attach functions to `FluentBundle` and use `create_default_registry()`.

FTL uses uppercase function names by convention. Python callables can keep normal snake_case parameter names; the bridge maps FTL camelCase named arguments onto Python snake_case parameters automatically.

## Single-Bundle Function

```python
from ftllexengine import FluentBundle

def FILESIZE(value: int) -> str:
    return f"{value / 1_000_000:.2f} MB"

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_function("FILESIZE", FILESIZE)
bundle.add_resource("attachment = Size: { FILESIZE($bytes) }")
result, errors = bundle.format_pattern("attachment", {"bytes": 15_000_000})
assert errors == ()
assert result == "Size: 15.00 MB"
```

## Reusable Registry

```python
from ftllexengine import FluentBundle
from ftllexengine.runtime import create_default_registry

registry = create_default_registry()

def UPPER(value: str) -> str:
    return value.upper()

registry.register(UPPER, ftl_name="UPPER")
bundle = FluentBundle("en_US", functions=registry, use_isolating=False)
```

## Locale Injection

Use `@fluent_function(inject_locale=True)` when the callable needs the bundle’s locale code appended as the last positional argument.

```python
from ftllexengine import FluentBundle
from ftllexengine.runtime import fluent_function

@fluent_function(inject_locale=True)
def GREETING(name: str, locale_code: str) -> str:
    return "Sveiki" if locale_code.startswith("lv") else "Hello"

bundle = FluentBundle("lv_LV", use_isolating=False)
bundle.add_function("GREETING", GREETING)
bundle.add_resource("msg = { GREETING($name) }, { $name }!")
result, errors = bundle.format_pattern("msg", {"name": "Anna"})
assert errors == ()
assert result == "Sveiki, Anna!"
```

## Guidance

- Prefer readable fallback values to raising exceptions from custom functions.
- Do not mutate a bundle from inside a formatting callback.
- Use a registry when the same function set must be reused across many bundles.
