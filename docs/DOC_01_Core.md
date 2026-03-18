---
afad: "3.3"
version: "0.158.0"
domain: CORE
updated: "2026-03-18"
route:
  keywords: [AsyncFluentBundle, FluentBundle, FluentLocalization, add_resource, add_resource_stream, format_pattern, has_message, has_attribute, require_clean, validate_message_schemas, validate_message_variables, require_locale_code, require_non_empty_str, require_positive_int, require_int, require_non_negative_int, coerce_tuple, validate_resource, introspect_message, introspect_term, get_cache_audit_log, strict, CacheConfig, IntegrityCache, CacheStats, LocalizationCacheStats, CacheAuditLogEntry, LocaleCode, normalize_locale, get_system_locale, LoadStatus, LoadSummary, ResourceLoadResult, FallbackInfo, ResourceLoader, PathResourceLoader, incremental, streaming, line iterator, async, asyncio, event loop, thread pool, CurrencyCode, TerritoryCode, NewType]
  questions: ["how to format message?", "how to add translations?", "how to validate ftl?", "how do I validate one message schema at boot?", "how do I validate localization at boot?", "how to check message exists?", "how do I canonicalize a locale code?", "is bundle thread safe?", "how to use strict mode?", "how to enable cache audit?", "how do I get the cache audit log?", "how do I coerce a list to tuple?", "how do I validate a non-negative int?", "how do I validate any int type?"]
---

# Core API Reference

---

## `CacheConfig`

`CacheConfig` is a frozen dataclass that encapsulates all cache configuration parameters for `FluentBundle` and `FluentLocalization`.

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

### Parameters
| Field | Type | Default | Description |
|:------|:-----|:--------|:------------|
| `size` | `int` | 1000 | Maximum cache entries (LRU eviction). |
| `write_once` | `bool` | False | Reject updates to existing keys (data race prevention). |
| `integrity_strict` | `bool` | True | Raise on checksum mismatch and write-once violations. |
| `enable_audit` | `bool` | False | Maintain audit log of cache operations. |
| `max_audit_entries` | `int` | 10000 | Maximum audit log entries before oldest eviction. |
| `max_entry_weight` | `int` | 10000 | Maximum memory weight for cached results. |
| `max_errors_per_entry` | `int` | 50 | Maximum errors per cache entry. |

### Constraints
- Immutable: Frozen dataclass; fields cannot be modified after construction.
- Validation: `__post_init__` rejects non-positive `size`, `max_entry_weight`, `max_errors_per_entry`, `max_audit_entries`.
- Independence: `integrity_strict` controls cache corruption response independently of `FluentBundle.strict` (formatting behavior).
- Import: `from ftllexengine import CacheConfig` or `from ftllexengine.runtime.cache_config import CacheConfig`.
- Usage: Pass `cache=CacheConfig()` to enable caching with defaults; `cache=None` (default) disables caching.

---

## `FluentBundle`

### Signature
```python
class FluentBundle:
    def __init__(
        self,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | BCP 47 locale code (positional-only, ASCII alphanumeric only). |
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `cache` | `CacheConfig \| None` | N | Cache configuration. `None` disables caching (default). `CacheConfig()` enables with defaults. |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry (must be `FunctionRegistry`, not `dict`). |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters (default: 10,000,000). |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth (default: 100). |
| `max_expansion_size` | `int \| None` | N | Maximum total characters produced during resolution (default: 1,000,000). Prevents Billion Laughs DoS. |
| `strict` | `bool` | N | Fail-fast mode (default `True`): raises `FormattingIntegrityError` on ANY error; raises `SyntaxIntegrityError` when `add_resource` produces junk. Pass `False` for soft-error recovery (returns `(fallback, errors)` tuple). |

### Constraints
- Return: FluentBundle instance.
- Raises: `ValueError` on invalid locale format (must be ASCII alphanumeric with underscore/hyphen separators) or locale code exceeding 1000 characters (DoS prevention).
- State: Creates internal message/term registries.
- Thread: Always thread-safe via internal RWLock.
- Import: `FunctionRegistry` from `ftllexengine.runtime.function_bridge`. `FluentValue` from `ftllexengine.core.value_types`.
- Strict: Default `strict=True` raises `FormattingIntegrityError` on any resolution error and `SyntaxIntegrityError` on junk FTL. Use `strict=False` for soft-error recovery; errors are then returned as a tuple. Errors are cached before raising; subsequent cache hits re-raise without re-resolution.
- Cache: Security parameters expose `IntegrityCache` features for financial-grade applications.

---

## `FluentBundle.for_system_locale`

### Signature
```python
@classmethod
def for_system_locale(
    cls,
    *,
    use_isolating: bool = True,
    cache: CacheConfig | None = None,
    functions: FunctionRegistry | None = None,
    max_source_size: int | None = None,
    max_nesting_depth: int | None = None,
    max_expansion_size: int | None = None,
    strict: bool = True,
) -> FluentBundle:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `cache` | `CacheConfig \| None` | N | Cache configuration. `None` disables (default). |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry (must be `FunctionRegistry`, not `dict`). |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters (default: 10,000,000). |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth (default: 100). |
| `max_expansion_size` | `int \| None` | N | Maximum total characters during resolution (default: 1,000,000). |
| `strict` | `bool` | N | Fail-fast mode (default `True`): raises on errors. Pass `False` for soft-error recovery. |

### Constraints
- Return: FluentBundle with system locale.
- Raises: `RuntimeError` if locale cannot be determined.
- State: Delegates to `get_system_locale(raise_on_failure=True)`.
- Thread: Safe.

---

## `FluentBundle.add_resource`

### Signature
```python
def add_resource(
    self,
    source: str,
    /,
    *,
    source_path: str | None = None
) -> tuple[Junk, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code (positional-only). |
| `source_path` | `str \| None` | N | Path for error messages. |

### Constraints
- Return: Tuple of Junk entries (syntax errors). Empty if parse succeeded.
- Raises: `TypeError` if source is not a str. `SyntaxIntegrityError` in strict mode if parsing produces any Junk.
- State: Mutates internal message/term registries. Clears cache.
- Thread: Safe (RWLock). Parse occurs outside write lock; only registration requires exclusive access.

---

## `FluentBundle.add_resource_stream`

### Signature
```python
def add_resource_stream(
    self,
    lines: Iterable[str],
    /,
    *,
    source_path: str | None = None
) -> tuple[Junk, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `lines` | `Iterable[str]` | Y | FTL source as a line iterator (positional-only). |
| `source_path` | `str \| None` | N | Path for error messages. |

### Constraints
- Return: Tuple of Junk entries. Empty if parse succeeded.
- Purpose: Identical semantics to `add_resource()` but accepts a line iterator instead of a full string. Memory usage is proportional to the largest single FTL entry in the stream, not the total resource size.
- Raises: `SyntaxIntegrityError` in strict mode if parsing produces any Junk.
- State: Mutates internal message/term registries. Clears cache.
- Thread: Safe (RWLock). Stream is consumed and parsed outside write lock.
- Import: `from ftllexengine.runtime import FluentBundle` (method on `FluentBundle`).

---

## `AsyncFluentBundle`

`AsyncFluentBundle` is an asyncio-native wrapper around `FluentBundle` that offloads all CPU-bound operations to a thread pool via `asyncio.to_thread()`, keeping the event loop unblocked.

### Signature
```python
class AsyncFluentBundle:
    def __init__(
        self,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | BCP 47 locale code (positional-only). |
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `cache` | `CacheConfig \| None` | N | Cache configuration. `None` disables (default). |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry. |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters. |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth. |
| `max_expansion_size` | `int \| None` | N | Maximum total characters during resolution. |
| `strict` | `bool` | N | Fail-fast mode (default `True`). |

### Constraints
- Return: `AsyncFluentBundle` instance. Supports `async with` (no cleanup required on exit).
- Async: `add_resource`, `add_resource_stream`, `format_pattern`, `add_function` are `async def`; offload to `asyncio.to_thread()`.
- Sync: `has_message`, `has_attribute`, `get_message_ids`, `get_message`, `get_term`, `introspect_message`, `clear_cache`, `get_cache_stats`, `get_cache_audit_log` are synchronous (O(1) dict lookups, hold read lock for nanoseconds).
- Concurrency: Underlying `FluentBundle` handles all thread safety via `RWLock`. No additional locking in `AsyncFluentBundle`.
- Strict: Same strict/soft-error semantics as `FluentBundle`. `strict=True` raises `FormattingIntegrityError`/`SyntaxIntegrityError`; `strict=False` returns `(fallback, errors)`.
- Import: `from ftllexengine import AsyncFluentBundle` or `from ftllexengine.runtime import AsyncFluentBundle`.

```python
async with AsyncFluentBundle("en_US") as bundle:
    await bundle.add_resource("greeting = Hello, { $name }!")
    result, errors = await bundle.format_pattern("greeting", {"name": "Alice"})
```

---

## `AsyncFluentBundle.for_system_locale`

### Signature
```python
@classmethod
def for_system_locale(
    cls,
    *,
    use_isolating: bool = True,
    cache: CacheConfig | None = None,
    functions: FunctionRegistry | None = None,
    max_source_size: int | None = None,
    max_nesting_depth: int | None = None,
    max_expansion_size: int | None = None,
    strict: bool = True,
) -> AsyncFluentBundle:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `cache` | `CacheConfig \| None` | N | Cache configuration. `None` disables (default). |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry. |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters. |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth. |
| `max_expansion_size` | `int \| None` | N | Maximum total characters during resolution. |
| `strict` | `bool` | N | Fail-fast mode (default `True`). |

### Constraints
- Return: `AsyncFluentBundle` for the detected system locale.
- Raises: `RuntimeError` if locale cannot be determined from OS environment.
- State: Reads locale from `LANG`, `LC_ALL`, `LC_MESSAGES` environment variables.

---

## `FluentBundle.format_pattern`

### Signature
```python
def format_pattern(
    self,
    message_id: str,
    /,
    args: Mapping[str, FluentValue] | None = None,
    *,
    attribute: str | None = None,
) -> tuple[str, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier (positional-only). |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |
| `attribute` | `str \| None` | N | Attribute name to format. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: `FormattingIntegrityError` in strict mode (default) if ANY error occurs. In non-strict mode (`strict=False`), never raises; all errors collected in tuple.
- State: Read-only (may update cache).
- Thread: Safe for concurrent reads.
- Duplicate Attributes: When message has duplicate attributes with same name, last attribute wins (per Fluent spec).

---

## `FluentBundle.validate_resource`

### Signature
```python
def validate_resource(self, source: str) -> ValidationResult:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `source` | `str` | Y | FTL source code to validate. |

### Constraints
- Return: ValidationResult with errors and warnings.
- Cross-Resource: References to existing bundle messages/terms do not produce undefined warnings.
- Raises: `TypeError` if source is not a str.
- State: None. Does not modify bundle.
- Thread: Safe.

---

## `FluentBundle.has_message`

### Signature
```python
def has_message(self, message_id: str) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier to check. |

### Constraints
- Return: True if message exists.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.has_attribute`

### Signature
```python
def has_attribute(self, message_id: str, attribute: str) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier to check. |
| `attribute` | `str` | Y | Attribute name to check. |

### Constraints
- Return: True if message exists AND has the specified attribute.
- Raises: None.
- State: Read-only.
- Thread: Safe.
- Duplicate Attributes: Checks existence only; does not indicate which definition will be used if duplicates exist (see format_pattern for last-wins resolution).

---

## `FluentBundle.get_message_ids`

### Signature
```python
def get_message_ids(self) -> list[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: List of all message identifiers.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.get_message_variables`

### Signature
```python
def get_message_variables(self, message_id: str) -> frozenset[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |

### Constraints
- Return: Frozen set of variable names (without $ prefix).
- Raises: `KeyError` if message not found.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.get_all_message_variables`

### Signature
```python
def get_all_message_variables(self) -> dict[str, frozenset[str]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Dict mapping message IDs to variable sets.
- Raises: None.
- State: Read-only. Acquires single read lock for atomic snapshot.
- Thread: Safe. Provides consistent snapshot during concurrent mutations.

---

## `FluentBundle.introspect_message`

### Signature
```python
def introspect_message(self, message_id: str) -> MessageIntrospection:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |

### Constraints
- Return: MessageIntrospection with complete metadata.
- Raises: `KeyError` if message not found.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.introspect_term`

### Signature
```python
def introspect_term(self, term_id: str) -> MessageIntrospection:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `term_id` | `str` | Y | Term identifier (without leading dash). |

### Constraints
- Return: MessageIntrospection with complete metadata.
- Raises: `KeyError` if term not found.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.add_function`

### Signature
```python
def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name (UPPERCASE convention). |
| `func` | `Callable[..., FluentValue]` | Y | Python function returning FluentValue. |

### Constraints
- Return: None.
- Raises: `TypeError` if registry is frozen or if callable has no inspectable signature.
- State: Mutates function registry. Clears cache.
- Thread: Safe (RWLock).

---

## `FluentBundle.clear_cache`

### Signature
```python
def clear_cache(self) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: None.
- Raises: None.
- State: Clears format cache.
- Thread: Safe.

---

## `FluentBundle.get_cache_stats`

### Signature
```python
def get_cache_stats(self) -> CacheStats | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: `CacheStats` TypedDict snapshot, or `None` if caching disabled. See `CacheStats` for all 19 fields with precise per-field types.
- Import: `from ftllexengine.runtime.cache import CacheStats`
- Raises: Never.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.get_cache_audit_log`

### Signature
```python
def get_cache_audit_log(self) -> tuple[CacheAuditLogEntry, ...] | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Tuple of immutable `CacheAuditLogEntry` snapshots, or `None` if caching disabled. Audit-disabled caches return `()`.
- Import: `from ftllexengine.localization import CacheAuditLogEntry`
- Raises: Never.
- State: Read-only.
- Thread: Safe.

---

## `FluentBundle.locale`

### Signature
```python
@property
def locale(self) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Canonical lowercase underscore `LocaleCode`.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.use_isolating`

### Signature
```python
@property
def use_isolating(self) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Boolean indicating bidi isolation enabled.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.cache_enabled`

### Signature
```python
@property
def cache_enabled(self) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: True if caching enabled.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.cache_config`

### Signature
```python
@property
def cache_config(self) -> CacheConfig | None:
```

### Constraints
- Return: `CacheConfig` when caching enabled; `None` when `cache=None` was passed to constructor.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.strict`

### Signature
```python
@property
def strict(self) -> bool:
```

### Constraints
- Return: True if strict mode enabled (fail-fast on any error).
- Raises: None.
- State: Read-only property.
- Thread: Safe.
- Note: When True, any formatting error raises FormattingIntegrityError. Errors are cached before raising; cache hits re-raise without re-resolution.

---

## `FluentBundle.cache_usage`

### Signature
```python
@property
def cache_usage(self) -> int:
```

### Constraints
- Return: Current number of cached format results.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.max_expansion_size`

### Signature
```python
@property
def max_expansion_size(self) -> int:
```

### Constraints
- Return: Maximum total characters produced during resolution.
- Raises: None.
- State: Read-only property.
- Thread: Safe.
- Default: 1000000.

---

## `FluentBundle.max_nesting_depth`

### Signature
```python
@property
def max_nesting_depth(self) -> int:
```

### Constraints
- Return: Maximum placeable nesting depth.
- Raises: None.
- State: Read-only property.
- Thread: Safe.
- Default: 100.

---

## `FluentBundle.max_source_size`

### Signature
```python
@property
def max_source_size(self) -> int:
```

### Constraints
- Return: Maximum FTL source size in characters.
- Raises: None.
- State: Read-only property.
- Thread: Safe.
- Default: 10,000,000.

---

## `FluentBundle.function_registry`

### Signature
```python
@property
def function_registry(self) -> FunctionRegistry:
```

### Constraints
- Return: The `FunctionRegistry` for this bundle.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentBundle.get_babel_locale`

### Signature
```python
def get_babel_locale(self) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Babel locale identifier string.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization`

### Signature
```python
class FluentLocalization:
    def __init__(
        self,
        locales: Iterable[LocaleCode],
        resource_ids: Iterable[ResourceId] | None = None,
        resource_loader: ResourceLoader | None = None,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
        strict: bool = True,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locales` | `Iterable[LocaleCode]` | Y | Locale codes in fallback order. |
| `resource_ids` | `Iterable[ResourceId] \| None` | N | FTL files to auto-load. |
| `resource_loader` | `ResourceLoader \| None` | N | Loader for FTL files. |
| `use_isolating` | `bool` | N | Wrap interpolated values in bidi marks. |
| `cache` | `CacheConfig \| None` | N | Cache configuration. `None` disables (default). |
| `on_fallback` | `Callable[[FallbackInfo], None] \| None` | N | Callback on fallback locale resolution. |
| `strict` | `bool` | N | Fail-fast mode (default `True`): raises `FormattingIntegrityError` on errors. Pass `False` for soft-error recovery. |

### Constraints
- Return: FluentLocalization instance.
- Raises: `ValueError` if locales empty, invalid locale format, or resource_ids without loader. Locale codes must match `[a-zA-Z0-9]+([_-][a-zA-Z0-9]+)*` (BCP 47 subset).
- State: Lazy bundle initialization. Bundles created on first access. Locale format validated eagerly at construction.
- Thread: Safe (RWLock-protected; concurrent reads, exclusive writes).
- Fallback: `on_fallback` invoked when message resolved from non-primary locale.
- Strict: When True, all underlying FluentBundle instances use strict mode. `_handle_message_not_found` raises `FormattingIntegrityError`.

---

## `FluentLocalization.add_resource`

### Signature
```python
def add_resource(self, locale: LocaleCode, ftl_source: FTLSource) -> tuple[Junk, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Target locale boundary value; canonicalized before fallback-chain lookup. |
| `ftl_source` | `FTLSource` | Y | FTL source code. |

### Constraints
- Return: Tuple of Junk entries (syntax errors). Empty if parse succeeded.
- Raises: `ValueError` if locale is not in the fallback chain after canonicalization, or if the locale boundary is blank/invalid.
- State: Mutates target bundle.
- Thread: Safe (RWLock write lock).

---

## `FluentLocalization.add_resource_stream`

### Signature
```python
def add_resource_stream(
    self,
    locale: LocaleCode,
    lines: Iterable[str],
    *,
    source_path: str | None = None
) -> tuple[Junk, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Target locale; canonicalized before fallback-chain lookup. |
| `lines` | `Iterable[str]` | Y | FTL source as a line iterator. |
| `source_path` | `str \| None` | N | Path for error messages. |

### Constraints
- Return: Tuple of Junk entries. Empty if parse succeeded.
- Purpose: Identical semantics to `add_resource()` but accepts a line iterator instead of a full string.
- Raises: `ValueError` if locale is not in the fallback chain.
- State: Mutates target bundle.
- Thread: Safe (RWLock write lock).

---

## `FluentLocalization.format_value`

### Signature
```python
def format_value(
    self,
    message_id: MessageId,
    args: Mapping[str, FluentValue] | None = None
) -> tuple[str, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: `FormattingIntegrityError` when strict mode enabled.
- State: Read-only.
- Thread: Safe (RWLock read lock).

---

## `FluentLocalization.format_pattern`

### Signature
```python
def format_pattern(
    self,
    message_id: MessageId,
    args: Mapping[str, FluentValue] | None = None,
    *,
    attribute: str | None = None,
) -> tuple[str, tuple[FrozenFluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |
| `attribute` | `str \| None` | N | Attribute name. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: `FormattingIntegrityError` when strict mode enabled.
- State: Read-only.
- Thread: Safe (RWLock read lock).

---

## `FluentLocalization.has_message`

### Signature
```python
def has_message(self, message_id: MessageId) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |

### Constraints
- Return: True if message exists in any locale.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.has_attribute`

### Signature
```python
def has_attribute(self, message_id: MessageId, attribute: str) -> bool:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |
| `attribute` | `str` | Y | Attribute name to check. |

### Constraints
- Return: True if message exists in any locale AND has the specified attribute.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.get_message_ids`

### Signature
```python
def get_message_ids(self) -> list[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: List of all message identifiers across all locales.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.get_message_variables`

### Signature
```python
def get_message_variables(self, message_id: MessageId) -> frozenset[str]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |

### Constraints
- Return: Frozen set of variable names (without $ prefix).
- Raises: `KeyError` if message not found in any locale.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.get_all_message_variables`

### Signature
```python
def get_all_message_variables(self) -> dict[str, frozenset[str]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Dict mapping message IDs to variable sets across all locales.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.introspect_term`

### Signature
```python
def introspect_term(self, term_id: str) -> MessageIntrospection | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `term_id` | `str` | Y | Term identifier (without leading dash). |

### Constraints
- Return: MessageIntrospection from first bundle with term, or None.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.add_function`

### Signature
```python
def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `name` | `str` | Y | Function name. |
| `func` | `Callable[..., FluentValue]` | Y | Python function returning FluentValue. |

### Constraints
- Return: None.
- Raises: None.
- State: Stores function for existing and future bundles.
- Thread: Safe (RWLock write lock).
- Behavior: Preserves lazy bundle initialization. Functions are stored and applied when bundles are first accessed.

---

## `FluentLocalization.get_bundles`

### Signature
```python
def get_bundles(self) -> Generator[FluentBundle]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Generator yielding bundles in fallback order.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.locales`

### Signature
```python
@property
def locales(self) -> tuple[LocaleCode, ...]:
```

### Constraints
- Return: Immutable tuple of canonical lowercase underscore `LocaleCode` values.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentLocalization.get_load_summary`

### Signature
```python
def get_load_summary(self) -> LoadSummary:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: LoadSummary with aggregated load results from initialization.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.require_clean`

Method that enforces a clean initialization `LoadSummary`.

### Signature
```python
def require_clean(self) -> LoadSummary:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Initialization `LoadSummary` when `all_clean` is true.
- Raises: `IntegrityCheckFailedError` when initialization had missing resources, load errors, or junk entries.
- State: Read-only.
- Thread: Safe.
- Scope: Checks only loader-driven initialization results. Dynamic `add_resource()` calls are excluded, matching `get_load_summary()`.

---

## `FluentLocalization.validate_message_schemas`

Method that enforces exact message-variable schemas across the fallback chain.

### Signature
```python
def validate_message_schemas(
    self,
    expected_schemas: Mapping[MessageId, frozenset[str] | set[str]],
) -> tuple[MessageVariableValidationResult, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `expected_schemas` | `Mapping[MessageId, frozenset[str] \| set[str]]` | Y | Expected variables per message ID. |

### Constraints
- Return: Immutable tuple of `MessageVariableValidationResult` values in input mapping order when every schema matches exactly.
- Raises: `IntegrityCheckFailedError` when a message is missing or its declared variables differ from the expected set.
- State: Read-only.
- Thread: Safe.
- Exactness: Declared variables must equal the expected set; both missing and extra variables fail validation.
- Scope: Resolves each message through the fallback chain via `get_message()`. Terms remain available through `get_term()` plus `validate_message_variables()`.

---

## `FluentLocalization.validate_message_variables`

Method that enforces an exact variable schema for a single fallback-resolved message.

### Signature
```python
def validate_message_variables(
    self,
    message_id: str,
    expected_variables: frozenset[str] | set[str],
) -> MessageVariableValidationResult:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message ID to resolve through the fallback chain. |
| `expected_variables` | `frozenset[str] \| set[str]` | Y | Exact variable set expected for that message. |

### Constraints
- Return: Immutable `MessageVariableValidationResult` when the message exists and declares exactly the expected variables.
- Raises: `IntegrityCheckFailedError` when the message is missing or its declared variables differ from `expected_variables`.
- State: Read-only.
- Thread: Safe.
- Scope: Uses the same fallback lookup semantics as `get_message()`.

---

## `FallbackInfo`

Dataclass providing fallback event metadata when FluentLocalization resolves a message from a non-primary locale.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FallbackInfo:
    requested_locale: LocaleCode
    resolved_locale: LocaleCode
    message_id: MessageId
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `requested_locale` | `LocaleCode` | Primary locale that was requested. |
| `resolved_locale` | `LocaleCode` | Locale that actually contained the message. |
| `message_id` | `MessageId` | Message identifier that triggered fallback. |

### Constraints
- Return: Frozen dataclass instance.
- State: Immutable.
- Thread: Safe.
- Usage: Passed to `on_fallback` callback in FluentLocalization.
- Import: `from ftllexengine import FallbackInfo` or `from ftllexengine.localization import FallbackInfo`.

---

## `LoadStatus`

### Signature
```python
class LoadStatus(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"
```

### Parameters
| Value | Description |
|:------|:------------|
| `SUCCESS` | Resource loaded successfully. |
| `NOT_FOUND` | Resource file not found (expected for optional locales). |
| `ERROR` | Resource load failed with error. |

### Constraints
- StrEnum: Members ARE strings.
- Babel: NOT required. Defined in `ftllexengine.enums`; no Babel import chain.
- Import: `from ftllexengine import LoadStatus` or `from ftllexengine.localization import LoadStatus`.

---

## `ResourceLoadResult`

### Signature
```python
@dataclass(frozen=True, slots=True)
class ResourceLoadResult:
    locale: LocaleCode
    resource_id: ResourceId
    status: LoadStatus
    error: Exception | None = None
    source_path: str | None = None
    junk_entries: tuple[Junk, ...] = ()

    @property
    def is_success(self) -> bool: ...
    @property
    def is_not_found(self) -> bool: ...
    @property
    def is_error(self) -> bool: ...
    @property
    def has_junk(self) -> bool: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `locale` | `LocaleCode` | Locale code for this resource. |
| `resource_id` | `ResourceId` | Resource identifier (e.g., 'main.ftl'). |
| `status` | `LoadStatus` | Load status (success, not_found, error). |
| `error` | `Exception \| None` | Exception if status is ERROR. |
| `source_path` | `str \| None` | Full path to resource (if available). |
| `junk_entries` | `tuple[Junk, ...]` | Unparseable content found during parsing. |

### Constraints
- Return: Immutable load result record.
- State: Frozen dataclass.
- Junk: `has_junk` property returns True if any Junk entries present.
- Import: `from ftllexengine import ResourceLoadResult` or `from ftllexengine.localization import ResourceLoadResult`.

---

## `LoadSummary`

### Signature
```python
@dataclass(frozen=True, slots=True)
class LoadSummary:
    results: tuple[ResourceLoadResult, ...]  # sole dataclass field

    @property
    def total_attempted(self) -> int: ...
    @property
    def successful(self) -> int: ...
    @property
    def not_found(self) -> int: ...
    @property
    def errors(self) -> int: ...
    @property
    def junk_count(self) -> int: ...
    @property
    def has_errors(self) -> bool: ...
    @property
    def all_successful(self) -> bool: ...
    @property
    def all_clean(self) -> bool: ...
    @property
    def has_junk(self) -> bool: ...

    def get_errors(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_not_found(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_successful(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_by_locale(self, locale: LocaleCode) -> tuple[ResourceLoadResult, ...]: ...
    def get_with_junk(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_all_junk(self) -> tuple[Junk, ...]: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `results` | `tuple[ResourceLoadResult, ...]` | All individual load results (sole constructor field). |

### Constraints
- Return: Immutable summary record.
- State: Frozen dataclass. Statistics (`total_attempted`, `successful`, `not_found`, `errors`, `junk_count`) are `@property` methods computed from `results`; not constructor parameters.
- Junk: `get_with_junk()` returns results with Junk; `get_all_junk()` aggregates all Junk.
- Import: `from ftllexengine import LoadSummary` or `from ftllexengine.localization import LoadSummary`.

---

## `LoadSummary.all_clean`

Property checking if all resources loaded successfully without Junk entries.

### Signature
```python
@property
def all_clean(self) -> bool:
```

### Constraints
- Return: True if errors == 0 and not_found == 0 and junk_count == 0.
- State: Read-only property.
- Purpose: Stricter validation than all_successful. Use for validation workflows requiring zero unparseable content.
- Contrast: `all_successful` ignores Junk (only checks I/O success), `all_clean` requires perfect parse.

---

## `FluentLocalization.cache_enabled`

### Signature
```python
@property
def cache_enabled(self) -> bool:
```

### Constraints
- Return: True if format caching enabled for all bundles.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentLocalization.cache_config`

### Signature
```python
@property
def cache_config(self) -> CacheConfig | None:
```

### Constraints
- Return: The `CacheConfig` instance passed to this localization, or `None` if caching disabled.
- Raises: None.
- State: Read-only property.
- Thread: Safe.

---

## `FluentLocalization.get_babel_locale`

### Signature
```python
def get_babel_locale(self) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Babel locale identifier from the primary bundle's canonical locale.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `FluentLocalization.validate_resource`

### Signature
```python
def validate_resource(self, ftl_source: FTLSource) -> ValidationResult:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `ftl_source` | `FTLSource` | Y | FTL source code to validate. |

### Constraints
- Return: ValidationResult with errors and warnings.
- Raises: `TypeError` if ftl_source is not a str (propagated from primary bundle).
- State: None. Does not modify bundles.
- Thread: Safe.

---

## `FluentLocalization.clear_cache`

### Signature
```python
def clear_cache(self) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: None.
- Raises: None.
- State: Clears format cache on all bundles.
- Thread: Safe.

---

## `FluentLocalization.get_cache_stats`

### Signature
```python
def get_cache_stats(self) -> LocalizationCacheStats | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: `LocalizationCacheStats` TypedDict with 20 aggregated fields, or `None` if caching disabled. Extends `CacheStats` with `bundle_count`. See `LocalizationCacheStats` for all fields.
- Note: Numeric fields summed across all bundles; boolean fields reflect first bundle's `CacheConfig`.
- Note: `bundle_count` reflects only initialized bundles, not total locales.
- Import: `from ftllexengine import LocalizationCacheStats` or `from ftllexengine.localization import LocalizationCacheStats`.
- Raises: None.
- State: Reads cache statistics from all initialized bundles.
- Thread: Safe.

---

## `FluentLocalization.get_cache_audit_log`

### Signature
```python
def get_cache_audit_log(self) -> dict[LocaleCode, tuple[CacheAuditLogEntry, ...]] | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Per-locale mapping of immutable `CacheAuditLogEntry` tuples, or `None` if caching disabled.
- Note: Only initialized bundles are included; this method does not create lazy bundles.
- Note: Audit-disabled bundles return `()`.
- Import: `from ftllexengine.runtime import CacheAuditLogEntry`
- Raises: Never.
- State: Reads audit logs from initialized bundles.
- Thread: Safe.

---

## `LocalizationCacheStats`

TypedDict representing aggregate cache statistics across all bundles in a `FluentLocalization`.

### Signature
```python
class LocalizationCacheStats(CacheStats, total=True):
    bundle_count: int
```

### Constraints
- Purpose: Extends `CacheStats` with `bundle_count` for multi-bundle monitoring. All 19 `CacheStats` fields are inherited with the same semantics; numeric fields are summed across all bundles.
- `bundle_count`: number of initialized bundles contributing to the aggregated statistics.
- Import: `from ftllexengine import LocalizationCacheStats` or `from ftllexengine.localization import LocalizationCacheStats`.
- Boolean fields: `write_once`, `strict`, `audit_enabled` reflect the first bundle's `CacheConfig` (all bundles share one config).

---

## `FluentLocalization.introspect_message`

### Signature
```python
def introspect_message(self, message_id: MessageId) -> MessageIntrospection | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |

### Constraints
- Return: MessageIntrospection from first bundle with message, or None.
- Raises: None.
- State: Read-only.
- Thread: Safe.

---

## `PathResourceLoader`

### Signature
```python
@dataclass(frozen=True, slots=True)
class PathResourceLoader:
    base_path: str
    root_dir: str | None = None

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `base_path` | `str` | Y | Path template with {locale} placeholder. |
| `root_dir` | `str \| None` | N | Fixed root directory for path traversal validation. |

### Constraints
- Return: FTL source string from file.
- Raises: `FileNotFoundError` if file missing, `OSError` on read error, `ValueError` on path traversal attempt.
- State: None. Immutable dataclass.
- Thread: Safe.
- Security:
  - Validates `locale` parameter against directory traversal attacks (rejects "..", "/", "\\").
  - Validates `resource_id` against directory traversal attacks (rejects "..", absolute paths).
  - Empty locale codes are rejected.
  - `root_dir` provides fixed anchor unaffected by locale parameter.
- Import: `from ftllexengine import PathResourceLoader` or `from ftllexengine.localization import PathResourceLoader`.

---

## `ResourceLoader`

### Signature
```python
class ResourceLoader(Protocol):
    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource: ...
    def describe_path(self, locale: LocaleCode, resource_id: ResourceId) -> str: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Locale code. |
| `resource_id` | `ResourceId` | Y | Resource identifier. |

### Constraints
- Return (`load`): FTL source string.
- Return (`describe_path`): Human-readable path string for diagnostics; default `"{locale}/{resource_id}"`.
- Raises: Implementation-dependent.
- State: Protocol. No implementation.
- Thread: Implementation-dependent.
- Import: `from ftllexengine import ResourceLoader` or `from ftllexengine.localization import ResourceLoader`.

---

## `normalize_locale`

### Signature
```python
def normalize_locale(locale_code: str) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale_code` | `str` | Y | BCP-47 or POSIX locale code. |

### Constraints
- Return: Lowercase POSIX-formatted locale code (hyphens to underscores, lowercased).
- State: None. Pure function.
- Thread: Safe.
- Babel: NOT required. Pure string manipulation.
- Import: `from ftllexengine import normalize_locale` or `from ftllexengine.core.locale_utils import normalize_locale`.

---

## `LocaleCode`

Type alias for BCP-47 / POSIX locale codes.

### Signature
```python
type LocaleCode = str
```

### Constraints
- Value: Any `str`; narrowed by context to a BCP-47 or POSIX locale code (e.g., `"en_US"`, `"de"`).
- Babel: NOT required. Defined in `ftllexengine.localization.types`; no Babel import chain.
- Import: `from ftllexengine import LocaleCode` or `from ftllexengine.localization.types import LocaleCode`.

---

## `require_non_empty_str`

Validate that a boundary value is a non-blank string, stripping surrounding whitespace.

### Signature
```python
def require_non_empty_str(value: object, field_name: str) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to validate. Any Python object; non-str always raises TypeError. |
| `field_name` | `str` | Y | Human-readable field label used in error messages. |

### Constraints
- Return: Stripped, non-empty string. Whitespace at boundaries is removed; internal whitespace is preserved.
- Raises: `TypeError` if `value` is not a `str` instance.
- Raises: `ValueError` if `value` is empty or contains only whitespace after stripping.
- State: Pure function; no side effects, no external dependencies.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import require_non_empty_str` or `from ftllexengine.core.validators import require_non_empty_str`.

---

## `require_positive_int`

Validate that a boundary value is a positive integer, rejecting bool, non-int types, zero, and negative values.

### Signature
```python
def require_positive_int(value: object, field_name: str) -> int:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to validate. Any Python object; non-int and bool always raise TypeError. |
| `field_name` | `str` | Y | Human-readable field label used in error messages. |

### Constraints
- Return: The validated integer, identical to the input value.
- Raises: `TypeError` if `value` is not an `int` instance, or if it is `bool` (bool is an int subtype but is rejected as semantically wrong for numeric-quantity fields).
- Raises: `ValueError` if `value` is zero or negative.
- State: Pure function; no side effects, no external dependencies.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import require_positive_int` or `from ftllexengine.core.validators import require_positive_int`.

---

## `require_int`

Validate that a boundary value is an integer, with no range constraint.

### Signature
```python
def require_int(value: object, field_name: str) -> int:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to validate. Any Python object; non-int and bool always raise TypeError. |
| `field_name` | `str` | Y | Human-readable field label used in error messages. |

### Constraints
- Return: The validated integer, identical to the input value. No range check applied.
- Raises: `TypeError` if `value` is not an `int` instance, or if it is `bool`.
- State: Pure function; no side effects, no external dependencies.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import require_int` or `from ftllexengine.core.validators import require_int`.

---

## `require_non_negative_int`

Validate that a boundary value is a non-negative integer (>= 0).

### Signature
```python
def require_non_negative_int(value: object, field_name: str) -> int:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to validate. Any Python object; non-int and bool always raise TypeError. |
| `field_name` | `str` | Y | Human-readable field label used in error messages. |

### Constraints
- Return: The validated non-negative integer, identical to the input value.
- Raises: `TypeError` if `value` is not an `int` instance, or if it is `bool`.
- Raises: `ValueError` if `value` is negative (`< 0`). Zero is valid.
- State: Pure function; no side effects, no external dependencies.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import require_non_negative_int` or `from ftllexengine.core.validators import require_non_negative_int`.

---

## `coerce_tuple`

Coerce a non-str Sequence to an immutable tuple. Generic over element type T.

### Signature
```python
def coerce_tuple[T](value: object, field_name: str) -> tuple[T, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to coerce. Any non-str Sequence accepted; str and non-Sequence raise TypeError. |
| `field_name` | `str` | Y | Human-readable field label used in error messages. |

### Constraints
- Return: An immutable `tuple` containing the elements of `value`.
- Raises: `TypeError` if `value` is `str` (str is a Sequence but is rejected as semantically a scalar at this boundary).
- Raises: `TypeError` if `value` is not a `Sequence` (int, None, generator, set, etc.).
- Element type T: Caller-asserted unchecked coercion. No runtime element type verification.
- State: Pure function; no side effects, no external dependencies.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import coerce_tuple` or `from ftllexengine.core.validators import coerce_tuple`.

---

## `require_locale_code`

Validate and canonicalize a locale code at a system boundary.

### Signature
```python
def require_locale_code(value: object, field_name: str) -> LocaleCode:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `value` | `object` | Y | Raw boundary value to validate. |
| `field_name` | `str` | Y | Field label used in error messages. |

### Constraints
- Return: Lowercase POSIX-formatted locale code (hyphens to underscores, lowercased).
- Raises: `TypeError` if `value` is not a string.
- Raises: `ValueError` if `value` is blank, too long, or structurally invalid.
- State: Trims surrounding whitespace and normalizes the accepted locale.
- Thread: Safe.
- Babel: NOT required.
- Import: `from ftllexengine import require_locale_code` or `from ftllexengine.core.locale_utils import require_locale_code`.

---

## `get_babel_locale`

### Signature
```python
def get_babel_locale(locale_code: str) -> Locale:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale_code` | `str` | Y | BCP-47 or POSIX locale code. Normalized before cache lookup. |

### Constraints
- Return: Babel Locale object. Results are cached; semantically equivalent locale codes (e.g., `"en-US"` and `"en_US"`) share a single cache entry.
- Raises: `BabelImportError` if Babel not installed.
- Raises: `TypeError` / `ValueError` if the locale boundary value is not a valid locale string.
- Raises: `babel.core.UnknownLocaleError` when the canonical locale is structurally valid but unknown to Babel.
- State: Normalizes `locale_code` before delegating to the internal cache.
- Thread: Safe (internal LRU cache uses its own locking).
- Babel: REQUIRED. Install with `pip install ftllexengine[babel]`.
- Import: `from ftllexengine.core.locale_utils import get_babel_locale`

---

## `get_system_locale`

### Signature
```python
def get_system_locale(*, raise_on_failure: bool = False) -> str:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `raise_on_failure` | `bool` | N | Raise RuntimeError if locale cannot be determined. |

### Constraints
- Return: Detected locale code in normalized POSIX format (lowercase), or "en_us" if not determinable.
- Raises: `RuntimeError` if raise_on_failure=True and locale cannot be determined.
- State: Reads OS locale via locale.getlocale() and env vars LC_ALL, LC_MESSAGES, LANG.
- Thread: Safe.
- Babel: NOT required. Uses only stdlib.
- Import: `from ftllexengine import get_system_locale` or `from ftllexengine.core.locale_utils import get_system_locale`.

---

## `clear_module_caches`

Function that clears all module-level caches in the library.

### Signature
```python
def clear_module_caches() -> None:
```

### Constraints
- Return: None.
- Raises: Never.
- State: Clears currency caches, date caches, locale cache, LocaleContext cache, message introspection cache, and ISO introspection cache.
- Thread: Safe (each cache has internal thread safety).
- Babel: Clears Babel-related caches only if Babel was used.
- Import: `from ftllexengine import clear_module_caches`

---

## `clear_locale_cache`

Function that clears the Babel locale object cache.

### Signature
```python
def clear_locale_cache() -> None:
```

### Constraints
- Return: None.
- Raises: Never.
- State: Clears the internal locale object cache shared by `get_babel_locale`.
- Thread: Safe (functools.cache internal locking).
- Babel: REQUIRED. Install with `pip install ftllexengine[babel]`.
- Import: `from ftllexengine.core.locale_utils import clear_locale_cache`

---
