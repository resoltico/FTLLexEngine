---
afad: "3.5"
version: "0.164.0"
domain: CORE
updated: "2026-04-23"
route:
  keywords: [FluentBundle, AsyncFluentBundle, FluentLocalization, LocalizationBootConfig, PathResourceLoader, LoadSummary, ResourceLoadResult, LocalizationCacheStats, require_clean, get_load_summary]
  questions: ["how do I format messages?", "how do I load multiple locales?", "how do I inspect localization load results?", "how do I boot localization safely?"]
---

# Core API Reference

Availability note:
- Full runtime only: `FluentBundle`, `AsyncFluentBundle`, `FluentLocalization`, `LocalizationBootConfig`, and `LocalizationCacheStats`
- Parser-only safe: `PathResourceLoader`, `ResourceLoader`, `LoadStatus`, `ResourceLoadResult`, `LoadSummary`, and `FallbackInfo`

---

## `FluentBundle`

Class that formats FTL messages for one locale.

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
    ) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locale` | Y | Locale code for bundle |
| `use_isolating` | N | Enable bidi isolation |
| `cache` | N | Cache configuration |
| `functions` | N | Custom function registry |
| `max_source_size` | N | FTL input bound |
| `max_nesting_depth` | N | Nesting safety bound |
| `max_expansion_size` | N | Expansion safety bound |
| `strict` | N | Raise on integrity failures |

### Constraints
- Return: Bundle with normalized locale and empty resource store
- Raises: `ValueError` on invalid or unknown locale; `TypeError` on invalid registry
- State: Mutable resources/functions; optional cache
- Thread: Safe
- Main methods: `add_resource()`, `add_resource_stream()`, `format_pattern()`, `add_function()`, `validate_resource()`
- Availability: full-runtime only

---

## `AsyncFluentBundle`

Class that exposes the `FluentBundle` API for asyncio callers.

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
    ) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locale` | Y | Locale code for bundle |
| `use_isolating` | N | Enable bidi isolation |
| `cache` | N | Cache configuration |
| `functions` | N | Custom function registry |
| `max_source_size` | N | FTL input bound |
| `max_nesting_depth` | N | Nesting safety bound |
| `max_expansion_size` | N | Expansion safety bound |
| `strict` | N | Raise on integrity failures |

### Constraints
- Return: Async wrapper around the same runtime semantics as `FluentBundle`
- State: Delegates to an internal bundle instance
- Thread: Safe
- Async: Formatting and mutation paths run through `asyncio.to_thread()`
- Availability: full-runtime only

---

## `FluentLocalization`

Class that orchestrates multiple locale bundles with fallback chains.

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
    ) -> None:
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locales` | Y | Fallback-ordered locale chain |
| `resource_ids` | N | Resource identifiers to load |
| `resource_loader` | N | Loader for startup resources |
| `use_isolating` | N | Enable bidi isolation |
| `cache` | N | Per-bundle cache config |
| `on_fallback` | N | Fallback callback hook |
| `strict` | N | Raise on integrity failures |

### Constraints
- Return: Multi-locale runtime with canonicalized locale chain
- Raises: `ValueError` on empty locales, invalid or unknown locales, or inconsistent loader inputs
- State: Eager resource loading when `resource_loader` and `resource_ids` are supplied; bundles materialize on the first successful load for a locale, while locales with no successful loads stay unmaterialized until a later access path needs them
- Thread: Safe
- Main methods: `format_value()`, `format_pattern()`, `add_resource()`, `add_function()`, `get_load_summary()`, `require_clean()`, `validate_message_schemas()`, `get_cache_stats()`
- Availability: full-runtime only

---

## `LocalizationBootConfig`

Dataclass that composes strict localization startup into one boot contract.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LocalizationBootConfig:
    locales: tuple[str, ...]
    resource_ids: tuple[str, ...]
    loader: ResourceLoader | None = None
    base_path: str | None = None
    message_schemas: Mapping[MessageId, frozenset[str] | set[str]] | None = None
    required_messages: frozenset[str] | None = None
    strict: bool = True
    use_isolating: bool = True
    cache: CacheConfig | None = None
    on_fallback: Callable[[FallbackInfo], None] | None = None
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `locales` | Y | Fallback locale chain |
| `resource_ids` | Y | Required resource list |
| `loader` | N | Custom resource loader |
| `base_path` | N | Loader path template |
| `message_schemas` | N | Expected message variables |
| `required_messages` | N | Presence contract set |
| `strict` | N | Runtime strict mode |
| `use_isolating` | N | Enable bidi isolation |
| `cache` | N | Bundle cache config |
| `on_fallback` | N | Fallback callback hook |

### Constraints
- Return: Immutable boot plan object
- Raises: `ValueError` when loader/base_path invariants are broken
- Raises: `RuntimeError` if `boot()` or `boot_simple()` is called more than once on the same instance
- State: One-shot boot coordinator
- Thread: Safe
- Main methods: `boot()`, `boot_simple()`, `from_path()`
- Availability: full-runtime only

---

## `PathResourceLoader`

Dataclass that loads FTL source from a locale-substituted path template.

### Signature
```python
@dataclass(frozen=True, slots=True)
class PathResourceLoader:
    base_path: str
    root_dir: str | None = None
```

### Parameters
| Name | Req | Semantics |
|:-----|:----|:----------|
| `base_path` | Y | Path template with `{locale}` |
| `root_dir` | N | Root for path safety checks |

### Constraints
- Raises: `ValueError` if `base_path` lacks `{locale}`
- Security: Rejects absolute paths and traversal-style `resource_id` values
- State: Immutable
- Thread: Safe

---

## `ResourceLoader`

Protocol that supplies FTL source for a locale and resource id pair.

### Signature
```python
class ResourceLoader(Protocol):
    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource: ...
    def describe_path(self, locale: LocaleCode, resource_id: ResourceId) -> str: ...
```

### Constraints
- Purpose: Loader contract for `FluentLocalization` and `LocalizationBootConfig`
- State: Implementation-defined
- Thread: Implementation-defined

---

## `LoadStatus`

Enumeration of resource-load outcomes.

### Signature
```python
class LoadStatus(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"
```

### Constraints
- Purpose: Classify startup load attempts
- Type: `StrEnum`

---

## `ResourceLoadResult`

Dataclass representing one locale/resource load attempt.

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
```

### Constraints
- Purpose: Immutable startup/load evidence record
- State: Immutable
- Thread: Safe
- Key properties: `is_success`, `is_not_found`, `is_error`, `has_junk`

---

## `LoadSummary`

Dataclass aggregating all startup load results.

### Signature
```python
@dataclass(frozen=True, slots=True)
class LoadSummary:
    results: tuple[ResourceLoadResult, ...]
```

### Constraints
- Purpose: Summarize boot cleanliness and resource outcomes
- State: Immutable
- Thread: Safe
- Key properties: `total_attempted`, `successful`, `not_found`, `errors`, `junk_count`, `has_errors`, `has_junk`, `all_successful`, `all_clean`
- Helper methods: `get_errors()`, `get_not_found()`, `get_successful()`, `get_by_locale()`, `get_with_junk()`, `get_all_junk()`

---

## `FallbackInfo`

Dataclass describing one fallback-resolution event.

### Signature
```python
@dataclass(frozen=True, slots=True)
class FallbackInfo:
    requested_locale: LocaleCode
    resolved_locale: LocaleCode
    message_id: MessageId
```

### Constraints
- Purpose: Callback payload for fallback observability
- State: Immutable
- Thread: Safe

---

## `LocalizationCacheStats`

Typed dict representing aggregate cache metrics across localization bundles.

### Signature
```python
class LocalizationCacheStats(CacheStats, total=True):
    bundle_count: int
```

### Constraints
- Purpose: Summarize per-locale cache state from `FluentLocalization.get_cache_stats()`
- Fields: Includes all `CacheStats` fields aggregated across initialized bundles, plus `bundle_count`
- State: Read-only result object
- Availability: full-runtime only
