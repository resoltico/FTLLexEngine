---
afad: "4.0"
version: "0.167.0"
domain: RUNTIME
updated: "2026-05-15"
route:
  keywords: [CacheConfig, FunctionRegistry, fluent_function, number_format, currency_format, select_plural_category, clear_module_caches]
  questions: ["how do I configure runtime formatting?", "how do custom functions and registries work?", "where are cache debug and integrity event types documented?"]
---

# Runtime Reference

This reference covers cache configuration, function registries, built-in formatters, plural selection, cache debug/integrity evidence types, and the root-level `clear_module_caches()` helper.
Runtime-adjacent utilities, validators, and package metadata constants are documented in [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md).

Parser-only facade note:
- `CacheConfig`, `FunctionRegistry`, `fluent_function`, `make_fluent_number`, `CacheDebugLogEntry`, `CacheIntegrityEvent`, `CacheIntegrityEventKind`, and `ValidationResult` remain importable in parser-only installs.
- `create_default_registry`, `get_shared_registry`, `number_format`, `datetime_format`, `currency_format`, `select_plural_category`, `FluentBundle`, and `AsyncFluentBundle` require the full runtime install. In parser-only installs they resolve to lazy placeholders that raise `BabelImportError` on first use.
- `clear_module_caches()` is a root-level helper that works in both parser-only and full-runtime installs.

Facade ownership note:
- The stable contract is the facade import path (`ftllexengine.runtime`, plus the root and localization facades where noted), not the internal helper module that implements a detail today.
- Smaller internal runtime modules exist to keep cache, bundle, function-registry, and diagnostic responsibilities partitioned; callers should continue importing from the documented facades.

## `CacheConfig`

Dataclass that configures optional format-result caching.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CacheConfig:
    size: int = 1000
    write_once: bool = False
    enable_debug_log: bool = False
    max_debug_entries: int = 10000
    max_entry_payload_bytes: int = 10000
    max_errors_per_entry: int = 50
    integrity_event_sink: IntegrityEventSink | None = None
    debug_fingerprint_key: bytes | None = None
```

### Constraints
- Purpose: Single cache configuration object for bundle/localization runtime
- State: Immutable
- Thread: Safe
- Integrity boundary: Cache corruption, key confusion, and write-once conflicts are system
  integrity failures regardless of `FluentBundle.strict`; formatting softness does not downgrade
  cache-integrity exceptions into fallback results

---

## `FunctionRegistry`

Class that maps Python callables onto FTL function names and argument conventions.

### Signature
```python
class FunctionRegistry:
    def __init__(self) -> None:
```

### Constraints
- Purpose: Register, freeze, copy, and dispatch custom functions
- State: Mutable until `freeze()`
- Thread: Safe for normal runtime use after registration
- Main methods: `register()`, `call()`, `get_callable()`, `list_functions()`, `copy()`
- Cache contract: `register(..., cacheable=False)` is the safe default for custom functions; opt in with `cacheable=True` only for pure functions whose output depends solely on the cache key inputs

---

## `fluent_function`

Decorator that attaches Fluent-specific metadata to a Python callable.

### Signature
```python
def fluent_function(
    func: F | None = None,
    *,
    inject_locale: bool = False,
) -> F | Callable[[F], F]:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `func` | N | Callable to decorate |
| `inject_locale` | N | Append locale argument |

### Constraints
- Purpose: Mark custom functions for locale injection behavior
- Ownership: attaches the locale-injection metadata that `FunctionRegistry` reads during registration
- State: Pure decorator
- Thread: Safe

---

## `create_default_registry`

Function that returns a mutable registry seeded with built-in functions.

### Signature
```python
def create_default_registry() -> FunctionRegistry:
```

### Constraints
- Return: New mutable registry
- State: Fresh object on each call
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `get_shared_registry`

Function that returns the shared frozen registry of built-in functions.

### Signature
```python
def get_shared_registry() -> FunctionRegistry:
```

### Constraints
- Return: Shared frozen registry
- State: Shared singleton-style object
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `number_format`

Function that formats a numeric value as `FluentNumber`.

### Signature
```python
def number_format(
    value: int | Decimal,
    locale_code: str = "en-US",
    *,
    minimum_fraction_digits: int = 0,
    maximum_fraction_digits: int = 3,
    use_grouping: bool = True,
    pattern: str | None = None,
    numbering_system: str = "latn",
) -> FluentNumber:
```

### Constraints
- Return: `FluentNumber`
- Raises: Locale/value boundary errors
- State: Pure
- Thread: Safe
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `datetime_format`

Function that formats a date or datetime value for a locale.

### Signature
```python
def datetime_format(
    value: date | datetime | str,
    locale_code: str = "en-US",
    *,
    date_style: Literal["short", "medium", "long", "full"] = "medium",
    time_style: Literal["short", "medium", "long", "full"] | None = None,
    pattern: str | None = None,
) -> str:
```

### Constraints
- Return: Formatted string
- Raises: Locale/value boundary errors
- State: Pure
- Thread: Safe
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `currency_format`

Function that formats a monetary value as `FluentNumber`.

### Signature
```python
def currency_format(
    value: int | Decimal,
    locale_code: str = "en-US",
    *,
    currency: str,
    currency_display: Literal["symbol", "code", "name"] = "symbol",
    pattern: str | None = None,
    use_grouping: bool = True,
    currency_digits: bool = True,
    numbering_system: str = "latn",
) -> FluentNumber:
```

### Constraints
- Return: `FluentNumber`
- Raises: Locale/value boundary errors
- State: Pure
- Thread: Safe
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `select_plural_category`

Function that resolves a CLDR plural category for a locale-aware number.

### Signature
```python
def select_plural_category(
    n: int | Decimal,
    locale: str,
    precision: int | None = None,
    *,
    ordinal: bool = False,
) -> str:
```

### Constraints
- Return: CLDR plural category string
- State: Pure
- Thread: Safe
- Availability: full-runtime only; parser-only installs expose a lazy placeholder that raises `BabelImportError` on first use

---

## `make_fluent_number`

Function that constructs a `FluentNumber` from an `int` or `Decimal`.

### Signature
```python
def make_fluent_number(value: int | Decimal, *, formatted: str | None = None) -> FluentNumber:
```

### Constraints
- Return: `FluentNumber`
- State: Pure
- Thread: Safe

---

## `clear_module_caches`

Function that clears selected module-level caches or all of them.

### Signature
```python
def clear_module_caches(components: frozenset[str] | None = None) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `components` | N | Specific cache components |

### Constraints
- Import: `from ftllexengine import clear_module_caches`
- Raises: `ValueError` on unknown cache selectors
- Selectors: `"parsing.currency"`, `"parsing.dates"`, `"locale"`, `"runtime.locale_context"`, `"introspection.message"`, `"introspection.iso"`
- State: Mutates module cache state
- Thread: Safe

---

## `CacheDebugLogEntry`

Immutable dataclass that represents one bounded cache debug-log record.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CacheDebugLogEntry:
    operation: str
    key_fingerprint: str
    timestamp_monotonic: float
    wall_time_unix: float
    debug_sequence: int
    cache_sequence: int
    cache_generation: int
    checksum_hex: str
```

### Constraints
- Purpose: Recent-operation debug evidence for hits, misses, puts, evictions, and write-once outcomes
- State: Immutable
- Thread: Safe
- Import: `from ftllexengine.runtime import CacheDebugLogEntry` or `from ftllexengine.localization import CacheDebugLogEntry`
- `debug_sequence`: Monotonic debug-ring order across cache operations
- `cache_sequence`: Cache-entry sequence observed at the time of the event
- `cache_generation`: Cache-clear generation active when the event was recorded
- `key_fingerprint`: Keyed privacy-preserving fingerprint, not the raw cache key

---

## `CacheIntegrityEvent`

Immutable dataclass that represents one critical cache-integrity event.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CacheIntegrityEvent:
    kind: CacheIntegrityEventKind
    message_id: str
    locale_code: str
    attribute: str | None
    use_isolating: bool
    key_fingerprint: str | None
    event_sequence: int
    cache_sequence: int
    cache_generation: int
    correlation_id: str | None
    thread_id: int
    task_name: str | None
    detail: str
    timestamp_monotonic: float
    wall_time_unix: float
```

### Constraints
- Purpose: Critical evidence for corruption, write conflicts, key-contract failures, and immediate verification failures
- State: Immutable
- Thread: Safe
- Import: `from ftllexengine.runtime import CacheIntegrityEvent` or `from ftllexengine.localization import CacheIntegrityEvent`

---

## `CacheIntegrityEventKind`

String enum that classifies critical cache-integrity event types.

### Signature
```python
class CacheIntegrityEventKind(StrEnum):
    ENTRY_CORRUPTION = "entry_corruption"
    KEY_CONFUSION = "key_confusion"
    WRITE_CONFLICT = "write_conflict"
    KEY_SERIALIZATION_FAILED = "key_serialization_failed"
    ENTRY_VERIFICATION_FAILED = "entry_verification_failed"
```

### Constraints
- Purpose: Stable event-category vocabulary for `CacheIntegrityEvent.kind`
- State: Immutable enum values
- Thread: Safe
- Import: `from ftllexengine.runtime import CacheIntegrityEventKind`

---
