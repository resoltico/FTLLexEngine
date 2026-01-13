---
afad: "3.1"
version: "0.71.0"
domain: architecture
updated: "2026-01-13"
route:
  keywords: [thread safety, concurrency, async, thread-local, contextvars, race condition, WeakKeyDictionary]
  questions: ["is FTLLexEngine thread-safe?", "can I use FluentBundle in async?", "what are the thread-safety guarantees?"]
---

# Thread Safety Reference

**Purpose**: Document thread-safety architectural decisions and guarantees.
**Prerequisites**: Basic concurrency concepts.

## Overview

FTLLexEngine provides explicit thread-safety guarantees for different components. This document consolidates all architectural decisions related to concurrency.

**Quick Reference**:

| Component | Thread-Safe | Async-Safe | Notes |
|:----------|:------------|:-----------|:------|
| `FluentBundle` | Yes (reads) | Yes | Immutable after construction |
| `FluentParserV1` | Yes | Yes | Stateless parsing |
| `FormatCache` | Yes | Yes | RLock-protected |
| `FunctionRegistry` | Copy-on-write | Copy-on-write | Copied on bundle init |
| Introspection cache | Accepted race | Accepted race | Redundant computation, no corruption |
| Parse error context | Thread-local | Requires clear | Call `clear_parse_error()` before parse |

---

## FluentBundle Thread Safety

`FluentBundle` is **safe for concurrent reads** from multiple threads.

**Guarantees**:
- All public properties are immutable after construction
- `format_pattern()` creates isolated `ResolutionContext` per call
- `FormatCache` uses `RLock` for internal synchronization
- `FunctionRegistry` is copied on initialization (copy-on-write)
- Batch operations (`get_all_message_variables()`) acquire single read lock for atomic snapshot

**Immutable References**:
```python
# These references never change after __init__:
bundle._locale       # str, immutable
bundle._messages     # dict, populated once
bundle._terms        # dict, populated once
bundle._cache        # FormatCache, same instance forever
bundle._registry     # FunctionRegistry, copied from input
```

**Not Thread-Safe**:
- `add_resource()` - Mutates internal state; serialize calls externally
- `add_function()` - Mutates registry; complete before concurrent reads

---

## Resolution Context (Explicit State)

The resolver uses **explicit context passing** instead of thread-local state.

**Design**:
```python
@dataclass(slots=True)
class ResolutionContext:
    """Per-resolution state, isolated per call."""
    stack: list[str]        # Cycle detection path
    _seen: set[str]         # O(1) membership check
    max_depth: int          # Stack overflow protection
    depth_guard: DepthGuard # Per-call depth tracking
```

**Why Explicit**:
- Thread-safe without locks
- Async framework compatible (no thread-local conflicts)
- Easier testing (no state reset needed)
- Clear dependency flow

**Instance Lifecycle**:
Each `format_pattern()` call creates a fresh `ResolutionContext`. This ensures complete isolation between concurrent resolutions. Object pooling is intentionally avoided to prevent synchronization overhead.

---

## Global Depth Guard (Contextvars)

Global resolution depth uses `contextvars` for async-safe per-task state.

**Purpose**: Prevent custom functions from bypassing depth limits by calling back into `bundle.format_pattern()`.

```python
from contextvars import ContextVar

_global_resolution_depth: ContextVar[int] = ContextVar(
    "fluent_resolution_depth", default=0
)

class GlobalDepthGuard:
    """Track depth across format_pattern calls."""
    def __enter__(self):
        current = _global_resolution_depth.get()
        if current >= self._max_depth:
            raise FluentResolutionError(...)
        self._token = _global_resolution_depth.set(current + 1)
```

**Security Model**:
Without global tracking, a malicious custom function could:
1. Receive control during resolution
2. Call `bundle.format_pattern()` (creates fresh context)
3. Repeat recursively, bypassing per-context limits
4. Cause stack overflow

`GlobalDepthGuard` prevents this by tracking depth across all contexts per async task.

---

## Introspection Cache (Accepted Race)

The introspection module uses `WeakKeyDictionary` **without locking**.

**Architectural Decision**: This is an **intentional trade-off** accepting potential race conditions for better common-case performance.

**Location**: `src/ftllexengine/introspection.py:59-81`

**Trade-off Analysis**:

| Alternative | Overhead | Benefit |
|:------------|:---------|:--------|
| RLock | Synchronization on every read | Full thread safety |
| Thread-local cache | Memory duplication | No contention |
| **Current (lock-free)** | **None** | **Best read performance** |

**Why Acceptable**:
- Introspection is a **pure read operation** on immutable AST nodes
- Worst case: redundant computation (cache miss), **never data corruption**
- Typical usage: read-mostly workload, concurrent introspection is rare
- Cache entries are computed identically regardless of which thread wins

**Explicit Documentation**:
```python
# Thread Safety (Accepted Race Condition):
# WeakKeyDictionary is NOT thread-safe for concurrent writes. Concurrent
# introspection of the same Message/Term from multiple threads may cause
# race conditions during cache write operations.
#
# Trade-off: Lock-free reads provide better performance than synchronized access.
```

**When This Matters**: Only if multiple threads simultaneously introspect the same `Message`/`Term` object for the first time. The only consequence is both threads compute and cache the same result.

---

## Parse Error Context (Thread-Local)

Parser primitives use **thread-local storage** for error context.

**Architectural Decision**: This is an **intentional trade-off** prioritizing hot-path performance.

**Location**: `src/ftllexengine/syntax/parser/primitives.py:10-38`

**Why Thread-Local**:
- Primitive functions called 100+ times per parse operation
- Explicit context parameter would require ~10 signature changes
- Parameter marshaling overhead degrades microsecond-scale operations

```python
from threading import local as thread_local

_error_context = thread_local()

def _set_parse_error(error: ParseError) -> None:
    _error_context.last_error = error
```

**Async Framework Requirement**:
For frameworks that reuse threads across parse operations:

```python
from ftllexengine.syntax.parser.primitives import clear_parse_error

async def parse_ftl_async(source: str) -> Resource:
    clear_parse_error()  # REQUIRED: Prevent error context leakage
    parser = FluentParserV1()
    return parser.parse(source)
```

**Automatic Clearing**: `FluentParserV1.parse()` calls `clear_parse_error()` at entry point. Manual clearing is only needed when using primitive functions directly.

---

## Copy-on-Write Registry

`FluentBundle` copies any registry passed to the constructor.

**Purpose**: Prevent shared mutable state between bundles.

```python
class FluentBundle:
    def __init__(self, locale: str, registry: FunctionRegistry | None = None):
        # Always copy to prevent external mutation affecting this bundle
        if registry is not None:
            self._registry = registry.copy()
        else:
            self._registry = get_builtin_registry().copy()
```

**Guarantees**:
- No bundle shares a mutable registry with another bundle
- Modifications to the original registry after bundle creation have no effect
- The built-in registry is frozen and copied if `add_function()` is called

---

## Summary

| Pattern | Rationale |
|:--------|:----------|
| Explicit `ResolutionContext` | Thread isolation without locks |
| `contextvars` for depth | Async-safe global state |
| Lock-free introspection cache | Performance over perfect synchronization |
| Thread-local parse errors | Hot-path optimization |
| Copy-on-write registry | Prevent shared mutable state |

**Key Principle**: FTLLexEngine optimizes for the common case (single-threaded or read-heavy concurrent workloads) while documenting explicit requirements for edge cases (async thread reuse, concurrent cache writes).
