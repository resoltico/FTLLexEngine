---
afad: "3.1"
version: "0.107.0"
domain: architecture
updated: "2026-01-31"
route:
  keywords: [thread safety, concurrency, async, thread-local, contextvars, race condition, WeakKeyDictionary, timeout, TimeoutError]
  questions: ["is FTLLexEngine thread-safe?", "can I use FluentBundle in async?", "what are the thread-safety guarantees?", "how to set lock timeout?"]
---

# Thread Safety Reference

**Purpose**: Document thread-safety architectural decisions and guarantees.
**Prerequisites**: Basic concurrency concepts.

## Overview

FTLLexEngine provides explicit thread-safety guarantees for different components. This document consolidates all architectural decisions related to concurrency.

**Quick Reference**:

| Component | Thread-Safe | Async-Safe | Notes |
|:----------|:------------|:-----------|:------|
| `FluentBundle` | Yes (all ops) | Yes | RWLock-protected reads and writes |
| `FluentParserV1` | Yes | Yes | Stateless parsing |
| `IntegrityCache` | Yes | Yes | RLock-protected |
| `FunctionRegistry` | Copy-on-write | Copy-on-write | Copied on bundle init |
| Introspection cache | Accepted race | Accepted race | Redundant computation, no corruption |
| Parse error context | Thread-local | Requires clear | Call `clear_parse_error()` before parse |

---

## FluentBundle Thread Safety

`FluentBundle` is **fully thread-safe** for all operations via internal RWLock.

**Guarantees**:
- All read operations (`format_pattern()`, `has_message()`, introspection) acquire read lock (concurrent)
- All write operations (`add_resource()`, `add_function()`) acquire write lock (exclusive)
- `format_pattern()` creates isolated `ResolutionContext` per call
- `IntegrityCache` uses `RLock` for internal synchronization
- `FunctionRegistry` is copied on initialization (copy-on-write)
- Batch operations (`get_all_message_variables()`) acquire single read lock for atomic snapshot

**Write Operations**:
- `add_resource()` - Parses outside lock (stateless parser), acquires write lock for registration only
- `add_function()` - Acquires write lock for registry mutation

**Write-to-Read Downgrading**:
A thread holding the write lock can acquire read locks without blocking. When the write lock is released, held read locks convert to regular reader locks. This enables write-then-read validation patterns.

**Reentrancy Limitation**:
Calling write operations (`add_resource()`, `add_function()`) from within format operations raises `RuntimeError`. This includes calls from custom functions invoked during formatting. The RWLock does not support read-to-write lock upgrading (deadlock prevention).

If you need lazy-loading patterns, load resources before formatting or use a separate bundle instance.

**Timeout Support**:
`RWLock.read()` and `RWLock.write()` accept an optional `timeout` parameter (seconds). `None` (default) waits indefinitely. `0.0` attempts non-blocking acquisition. Positive float sets a deadline. Raises `TimeoutError` on expiry. Reentrant and downgrading acquisitions never wait, so timeout is irrelevant in those paths. On write timeout, the internal `_waiting_writers` counter is correctly decremented (via `try/finally`), preventing reader starvation from abandoned writes.

```python
lock = RWLock()
try:
    with lock.write(timeout=5.0):
        # Acquired within 5 seconds
        ...
except TimeoutError:
    # Lock contention exceeded deadline
    ...
```

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
            raise FrozenFluentError(...)  # category=RESOLUTION
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

**Location**: `src/ftllexengine/introspection/message.py:59-83`

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
    def __init__(self, locale: str, /, *, functions: FunctionRegistry | None = None):
        # Always copy to prevent external mutation affecting this bundle
        if functions is not None:
            self._functions = functions.copy()
        else:
            self._functions = get_shared_registry().copy()
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
