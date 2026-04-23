---
afad: "3.5"
version: "0.164.0"
domain: RUNTIME
updated: "2026-04-23"
route:
  keywords: [CacheConfig, FunctionRegistry, fluent_function, number_format, currency_format, select_plural_category, clear_module_caches]
  questions: ["how do I configure runtime formatting?", "how do custom functions and registries work?", "where are cache config and write-log entry types documented?"]
---

# Runtime Reference

This reference covers cache configuration, function registries, built-in formatters, plural selection, cache/audit entry types, and the root-level `clear_module_caches()` helper.
Runtime-adjacent utilities, validators, and package metadata constants are documented in [DOC_04_RuntimeUtilities.md](DOC_04_RuntimeUtilities.md).

Parser-only facade note:
- `CacheConfig`, `FunctionRegistry`, `fluent_function`, `make_fluent_number`, `CacheAuditLogEntry`, `WriteLogEntry`, and `ValidationResult` remain importable in parser-only installs.
- `create_default_registry`, `get_shared_registry`, `number_format`, `datetime_format`, `currency_format`, `select_plural_category`, `FluentBundle`, and `AsyncFluentBundle` require the full runtime install and are absent from `ftllexengine.runtime` in parser-only installs.
- `clear_module_caches()` is a root-level helper that works in both parser-only and full-runtime installs.

## `CacheConfig`

Dataclass that configures optional format-result caching.

### Signature
```python
@dataclass(frozen=True, slots=True)
class CacheConfig:
    size: int = 1000
    write_once: bool = False
    integrity_strict: bool = True
    enable_audit: bool = False
    max_audit_entries: int = 10000
    max_entry_weight: int = 10000
    max_errors_per_entry: int = 50
```

### Constraints
- Purpose: Single cache configuration object for bundle/localization runtime
- State: Immutable
- Thread: Safe

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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
- Availability: full-runtime only; absent from `ftllexengine.runtime` in parser-only installs

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

## `CacheAuditLogEntry`

Public alias for the cache audit-log record type.

### Signature
```python
CacheAuditLogEntry = WriteLogEntry
```

### Constraints
- Purpose: Stable public alias returned by bundle/localization cache-audit APIs
- Underlying type: `WriteLogEntry`
- Import: `from ftllexengine.runtime import CacheAuditLogEntry` or `from ftllexengine.localization import CacheAuditLogEntry`

---

## `WriteLogEntry`

Immutable dataclass that represents one cache audit-log record.

### Signature
```python
@dataclass(frozen=True, slots=True)
class WriteLogEntry:
    operation: str
    key_hash: str
    timestamp: float
    sequence: int
    checksum_hex: str
    wall_time_unix: float
```

### Constraints
- Purpose: Underlying runtime cache dataclass behind the `CacheAuditLogEntry` public alias
- State: Immutable
- Thread: Safe

---
