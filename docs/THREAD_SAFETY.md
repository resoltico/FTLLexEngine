---
afad: "4.0"
version: "0.167.0"
domain: ARCHITECTURE
updated: "2026-05-15"
route:
  keywords: [thread safety, concurrency, FluentBundle, FluentLocalization, AsyncFluentBundle, shared bundle]
  questions: ["is FluentBundle thread-safe?", "can I share a localization object across threads?", "what does AsyncFluentBundle do?"]
---

# Thread Safety

**Purpose**: Describe the concurrency guarantees of the public runtime classes.
**Prerequisites**: Full runtime install (`ftllexengine[babel]`).

## Overview

`FluentBundle` and `FluentLocalization` are designed for concurrent use. Read operations can run concurrently, while resource and function mutations take exclusive access internally. Callers do not need to provide their own external lock around normal formatting calls.

These guarantees come from the runtime's own synchronization boundaries. They are not documented as a CPython-only or GIL-dependent property.

## Practical Rules

- Share a `FluentBundle` across threads when all requests use the same locale.
- Share a `FluentLocalization` across threads when the locale fallback chain is fixed.
- Use `AsyncFluentBundle` in asyncio handlers when you want bundle work offloaded through its owned worker pool and bounded async admission gate.
- Treat custom functions as external code: if they share mutable process state outside the bundle, that state still needs its own synchronization.
- Do not try to mutate or re-enter a bundle from a new thread inside a custom function triggered by that same bundle’s formatting call.

## Async

`AsyncFluentBundle` is not a separate resolver implementation. It wraps the same runtime behavior in an async-facing API, owns its executor lifecycle, and bounds queued work so event-loop callers have an explicit concurrency contract instead of ambient `asyncio.to_thread()` behavior.

The repository verifies these guarantees against both the normal supported interpreter set and a dedicated Python 3.13 free-threaded lane in CI.
