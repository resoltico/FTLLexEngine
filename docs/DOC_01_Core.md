---
afad: "3.1"
version: "0.52.0"
domain: CORE
updated: "2026-01-03"
route:
  keywords: [FluentBundle, FluentLocalization, add_resource, format_pattern, format_value, has_message, has_attribute, validate_resource, introspect_message, introspect_term]
  questions: ["how to format message?", "how to add translations?", "how to validate ftl?", "how to check message exists?", "is bundle thread safe?"]
---

# Core API Reference

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
        enable_cache: bool = False,
        cache_size: int = 1000,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `str` | Y | BCP 47 locale code (positional-only). |
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `enable_cache` | `bool` | N | Enable format result caching. |
| `cache_size` | `int` | N | Maximum cache entries. |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry. |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters (default: 10M). |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth (default: 100). |

### Constraints
- Return: FluentBundle instance.
- Raises: `ValueError` on invalid locale format.
- State: Creates internal message/term registries.
- Thread: Always thread-safe via internal RLock.
- Context: Supports context manager protocol (__enter__/__exit__).
- Import: `FunctionRegistry` from `ftllexengine.runtime.function_bridge`.

---

## `FluentBundle.for_system_locale`

### Signature
```python
@classmethod
def for_system_locale(
    cls,
    *,
    use_isolating: bool = True,
    enable_cache: bool = False,
    cache_size: int = 1000,
    functions: FunctionRegistry | None = None,
    max_source_size: int | None = None,
    max_nesting_depth: int | None = None,
) -> FluentBundle:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `use_isolating` | `bool` | N | Wrap interpolated values in Unicode bidi marks. |
| `enable_cache` | `bool` | N | Enable format result caching. |
| `cache_size` | `int` | N | Maximum cache entries. |
| `functions` | `FunctionRegistry \| None` | N | Custom function registry. |
| `max_source_size` | `int \| None` | N | Maximum FTL source length in characters (default: 10M). |
| `max_nesting_depth` | `int \| None` | N | Maximum placeable nesting depth (default: 100). |

### Constraints
- Return: FluentBundle with system locale.
- Raises: `RuntimeError` if locale cannot be determined.
- State: Delegates to `get_system_locale(raise_on_failure=True)`.
- Thread: Safe.

---

## `FluentBundle.__enter__`

### Signature
```python
def __enter__(self) -> FluentBundle:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Self (FluentBundle instance).
- Raises: None.
- State: None.
- Thread: Safe.

---

## `FluentBundle.__exit__`

### Signature
```python
def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: object | None,
) -> None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `exc_type` | `type[BaseException] \| None` | N | Exception type. |
| `exc_val` | `BaseException \| None` | N | Exception value. |
| `exc_tb` | `object \| None` | N | Traceback object. |

### Constraints
- Return: None (does not suppress exceptions).
- Raises: None.
- State: Clears format cache only. Messages and terms preserved.
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
- Raises: `FluentSyntaxError` on critical parse error.
- State: Mutates internal message/term registries. Clears cache.
- Thread: Safe (RLock).

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
) -> tuple[str, tuple[FluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier (positional-only). |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |
| `attribute` | `str \| None` | N | Attribute name to format. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: Never. All errors collected in tuple.
- State: Read-only (may update cache).
- Thread: Safe for concurrent reads.

---

## `FluentBundle.format_value`

### Signature
```python
def format_value(
    self,
    message_id: str,
    args: Mapping[str, FluentValue] | None = None
) -> tuple[str, tuple[FluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `str` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: Never.
- State: Read-only.
- Thread: Safe.

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
- Raises: Never.
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
- State: Read-only.
- Thread: Safe.

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
- Version: Added in v0.42.0.

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
- Raises: None.
- State: Mutates function registry. Clears cache.
- Thread: Safe (RLock).

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
def get_cache_stats(self) -> dict[str, int | float] | None:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|

### Constraints
- Return: Dict with size/hits/misses (int) and hit_rate (float 0.0-100.0), or None if disabled.
- Raises: None.
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
- Return: Locale code string.
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

## `FluentBundle.cache_size`

### Signature
```python
@property
def cache_size(self) -> int:
```

### Constraints
- Return: Configured maximum cache entries.
- Raises: None.
- State: Read-only property. Returns configured value regardless of cache_enabled.
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
        enable_cache: bool = False,
        cache_size: int = 1000,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
    ) -> None: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locales` | `Iterable[LocaleCode]` | Y | Locale codes in fallback order. |
| `resource_ids` | `Iterable[ResourceId] \| None` | N | FTL files to auto-load. |
| `resource_loader` | `ResourceLoader \| None` | N | Loader for FTL files. |
| `use_isolating` | `bool` | N | Wrap interpolated values in bidi marks. |
| `enable_cache` | `bool` | N | Enable format caching. |
| `cache_size` | `int` | N | Max cache entries per bundle. |
| `on_fallback` | `Callable[[FallbackInfo], None] \| None` | N | Callback on fallback locale resolution. |

### Constraints
- Return: FluentLocalization instance.
- Raises: `ValueError` if locales empty or resource_ids without loader.
- State: Lazy bundle initialization. Bundles created on first access.
- Thread: Safe (RLock).
- Fallback: `on_fallback` invoked when message resolved from non-primary locale.

---

## `FluentLocalization.add_resource`

### Signature
```python
def add_resource(self, locale: LocaleCode, ftl_source: FTLSource) -> tuple[Junk, ...]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Target locale (must be in chain). |
| `ftl_source` | `FTLSource` | Y | FTL source code. |

### Constraints
- Return: Tuple of Junk entries (syntax errors). Empty if parse succeeded.
- Raises: `ValueError` if locale not in fallback chain.
- Raises: `FluentSyntaxError` if FTL source contains critical syntax errors.
- State: Mutates target bundle.
- Thread: Safe (RLock).

---

## `FluentLocalization.format_value`

### Signature
```python
def format_value(
    self,
    message_id: MessageId,
    args: Mapping[str, FluentValue] | None = None
) -> tuple[str, tuple[FluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: Never.
- State: Read-only.
- Thread: Safe.

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
) -> tuple[str, tuple[FluentError, ...]]:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `message_id` | `MessageId` | Y | Message identifier. |
| `args` | `Mapping[str, FluentValue] \| None` | N | Variable arguments. |
| `attribute` | `str \| None` | N | Attribute name. |

### Constraints
- Return: Tuple of (formatted_string, errors).
- Raises: Never.
- State: Read-only.
- Thread: Safe.

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
- Thread: Safe (RLock).
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
- Return: Immutable tuple of locale codes.
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
- Import: `from ftllexengine.localization import FallbackInfo`

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
- Import: `from ftllexengine.localization import LoadStatus`

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
- Import: `from ftllexengine.localization import ResourceLoadResult`

---

## `LoadSummary`

### Signature
```python
@dataclass(frozen=True, slots=True)
class LoadSummary:
    results: tuple[ResourceLoadResult, ...]
    total_attempted: int  # computed
    successful: int  # computed
    not_found: int  # computed
    errors: int  # computed
    junk_count: int  # computed

    def get_errors(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_not_found(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_successful(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_by_locale(self, locale: LocaleCode) -> tuple[ResourceLoadResult, ...]: ...
    def get_with_junk(self) -> tuple[ResourceLoadResult, ...]: ...
    def get_all_junk(self) -> tuple[Junk, ...]: ...
    @property
    def has_errors(self) -> bool: ...
    @property
    def all_successful(self) -> bool: ...
    @property
    def has_junk(self) -> bool: ...
```

### Parameters
| Field | Type | Description |
|:------|:-----|:------------|
| `results` | `tuple[ResourceLoadResult, ...]` | All individual load results. |
| `total_attempted` | `int` | Total number of load attempts. |
| `successful` | `int` | Number of successful loads. |
| `not_found` | `int` | Number of resources not found. |
| `errors` | `int` | Number of load errors. |
| `junk_count` | `int` | Total Junk entries across all resources. |

### Constraints
- Return: Immutable summary record.
- State: Frozen dataclass. Statistics computed in __post_init__.
- Junk: `get_with_junk()` returns results with Junk; `get_all_junk()` aggregates all Junk.
- Import: `from ftllexengine.localization import LoadSummary`

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

## `FluentLocalization.cache_size`

### Signature
```python
@property
def cache_size(self) -> int:
```

### Constraints
- Return: Configured maximum cache entries per bundle.
- Raises: None.
- State: Read-only property. Returns configured value regardless of cache_enabled.
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
- Return: Babel locale identifier from primary bundle.
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
- Raises: Never.
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

---

## `ResourceLoader`

### Signature
```python
class ResourceLoader(Protocol):
    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource: ...
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale` | `LocaleCode` | Y | Locale code. |
| `resource_id` | `ResourceId` | Y | Resource identifier. |

### Constraints
- Return: FTL source string.
- Raises: Implementation-dependent.
- State: Protocol. No implementation.
- Thread: Implementation-dependent.

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
- Import: `from ftllexengine.locale_utils import normalize_locale`

---

## `get_babel_locale`

### Signature
```python
@functools.lru_cache(maxsize=128)
def get_babel_locale(locale_code: str) -> Locale:
```

### Parameters
| Parameter | Type | Req | Description |
|:----------|:-----|:----|:------------|
| `locale_code` | `str` | Y | BCP-47 or POSIX locale code. |

### Constraints
- Return: Babel Locale object (cached).
- Raises: `ImportError` if Babel not installed.
- Raises: `babel.core.UnknownLocaleError` on invalid locale.
- State: None. Cached pure function.
- Thread: Safe (lru_cache internal locking).
- Babel: REQUIRED. Install with `pip install ftllexengine[babel]`.
- Import: `from ftllexengine.locale_utils import get_babel_locale`

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
- Return: Detected locale code in POSIX format, or "en_US" if not determinable.
- Raises: `RuntimeError` if raise_on_failure=True and locale cannot be determined.
- State: Reads OS locale via locale.getlocale() and env vars LC_ALL, LC_MESSAGES, LANG.
- Thread: Safe.
- Babel: NOT required. Uses only stdlib.
- Import: `from ftllexengine.locale_utils import get_system_locale`

---
