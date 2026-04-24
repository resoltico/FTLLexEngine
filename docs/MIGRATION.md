---
afad: "4.0"
version: "0.164.0"
domain: MIGRATION
updated: "2026-04-24"
route:
  keywords: [migration, fluent.runtime, FluentBundle, FluentLocalization, strict mode]
  questions: ["how do I migrate from fluent.runtime?", "what changes when I switch to FTLLexEngine?"]
---

# Migration From `fluent.runtime`

**Purpose**: Highlight the main API and behavior differences when moving to FTLLexEngine.
**Prerequisites**: Familiarity with `fluent.runtime` and the FTLLexEngine full runtime install (`ftllexengine[babel]`).

## High-Level Differences

- `FluentBundle.format_pattern()` takes a message id directly; you do not fetch a message object first.
- `FluentLocalization` is the multi-locale orchestration layer for fallback chains.
- Strict mode is the default. Formatting and resource-integrity problems raise immediately unless you opt into `strict=False`.
- Boot validation is built in through `LocalizationBootConfig`.

## Example

```python
from ftllexengine import FluentBundle

bundle = FluentBundle("en_US", use_isolating=False)
bundle.add_resource("welcome = Hello, { $name }!")
result, errors = bundle.format_pattern("welcome", {"name": "Alice"})
assert errors == ()
assert result == "Hello, Alice!"
```

## Recommended Migration Order

1. Replace message-object lookup flows with direct message-id formatting calls.
2. Decide whether you need single-locale `FluentBundle` or multi-locale `FluentLocalization`.
3. Make strict-mode behavior explicit in tests.
4. Add startup validation with `LocalizationBootConfig` if resources come from disk or another loader.
