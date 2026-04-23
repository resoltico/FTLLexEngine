---
afad: "3.5"
version: "0.164.0"
domain: ARCHITECTURE
updated: "2026-04-23"
route:
  keywords: [thread safety, concurrency, FluentBundle, FluentLocalization, AsyncFluentBundle, shared bundle]
  questions: ["is FluentBundle thread-safe?", "can I share a localization object across threads?", "what does AsyncFluentBundle do?"]
---

# Thread Safety

**Purpose**: Describe the concurrency guarantees of the public runtime classes.
**Prerequisites**: Full runtime install (`ftllexengine[babel]`).

## Overview

`FluentBundle` and `FluentLocalization` are designed for concurrent use. Read operations can run concurrently, while resource and function mutations take exclusive access internally. Callers do not need to provide their own external lock around normal formatting calls.

## Practical Rules

- Share a `FluentBundle` across threads when all requests use the same locale.
- Share a `FluentLocalization` across threads when the locale fallback chain is fixed.
- Use `AsyncFluentBundle` in asyncio handlers when you want bundle work offloaded through `asyncio.to_thread()`.
- Do not try to mutate a bundle from inside a custom function triggered by that same bundle’s formatting call.

## Async

`AsyncFluentBundle` is not a separate resolver implementation. It wraps the same runtime behavior in an async-facing API and delegates the heavy work to worker threads so the event loop stays responsive.
